import os
import io
import jwt
import qrcode
import secrets
import logging
import json
import hashlib
from user_agents import parse
from PIL import Image
from typing import Dict, Literal, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import RedirectResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import psycopg2

from database import init_db, get_db, get_daily_salt, redis_client, db_pool
import clicks
import geo
import stats
import analytics_utils as au
import mcp_server
import oauth
from links import (
    RESERVED_ALIASES, URLCreate, LinkUpdate, LinkError, KEEP, LINK_COLUMNS,
    cache_ttl, create_short_link, delete_link, is_expired, link_dict, resolve_expiry, update_link,
)
from pages import expired_page, not_found_page
from security import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM

# 1. Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 2. Rate Limiter Key Func (X-Forwarded-For support)
def get_real_ip(request: Request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=get_real_ip)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up server...")
    init_db()
    logger.info("Database initialised")
    # The MCP transport needs its session manager running for the app's lifetime.
    async with mcp_server.session_manager().run():
        yield
    logger.info("Shutting down server...")

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 4. Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal Server Error"}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0]["msg"].removeprefix("Value error, ") if errors else "Validation Error"
    return JSONResponse(
        status_code=422,
        content={"success": False, "message": msg}
    )

# OAuth 2.1 authorization server for the MCP endpoint, under /oauth so POST /register and POST /token stay as they are.
app.mount("/oauth", oauth.oauth_app)

@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/oauth-authorization-server/oauth")
def oauth_as_metadata(request: Request):
    return JSONResponse(oauth.authorization_server_metadata(oauth.public_origin(request.headers, request.url.scheme)))

@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
def oauth_resource_metadata(request: Request):
    return JSONResponse(oauth.protected_resource_metadata(oauth.public_origin(request.headers, request.url.scheme)))

# MCP endpoint (API key or OAuth access token). Registered before /{short_id} so it is not read as a short ID.
app.add_route("/mcp", mcp_server.asgi_app, methods=["GET", "POST", "DELETE"])

app.mount("/static", StaticFiles(directory="static"), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# RESERVED_ALIASES and URLCreate live in links.py (shared with the MCP server).

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)

def get_user_id(conn, username: str) -> int:
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return row[0]

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)

MAX_ACTIVE_API_KEYS = 5

@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")
    
@app.get("/health")
def health_check():
    return {"success": True, "message": "Healthy"}

@app.post("/register")
@limiter.limit("5/minute")
def register(request: Request, user: UserCreate, conn=Depends(get_db)):
    cursor = conn.cursor()
    hashed_pw = get_password_hash(user.password)
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (user.username, hashed_pw))
        conn.commit()
        logger.info(f"New user registered: {user.username}")
        return {"success": True, "message": "User registered successfully"}
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/token")
@limiter.limit("10/minute")
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password FROM users WHERE username=%s", (form_data.username,))
    user = cursor.fetchone()
    if user is None or not verify_password(form_data.password, user[2]):
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/shorten")
@limiter.limit("20/minute")
def shorten(request: Request, url: URLCreate, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    user_id = get_user_id(conn, current_username)
    try:
        created = create_short_link(conn, user_id, url)
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    data = {"Long Url": created.long_url, "Short_ID": created.short_id, "expires_at": au.iso_utc(created.expires_at) or None}
    if created.already_existed:
        return {"success": True, "data": data, "message": "Already existed!"}
    return {"success": True, "data": data}

@app.get("/dashboard")
def get_dashboard(current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_id = cursor.fetchone()[0]
    cursor.execute(f"SELECT {LINK_COLUMNS} FROM urls WHERE user_id = %s ORDER BY id DESC", (user_id,))
    urls = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM click_events WHERE is_bot IS NOT TRUE AND short_id IN (SELECT short_id FROM urls WHERE user_id = %s)", (user_id,))
    total_clicks_result = cursor.fetchone()
    total_clicks = total_clicks_result[0] if total_clicks_result else 0

    dashboard_data = [
        {"Short ID": u[0], "Long URL": u[1], "Total Clicks": u[2], **{k: v for k, v in link_dict(u).items() if k in ("created_at", "expires_at", "updated_at", "expired")}}
        for u in urls
    ]
    return {"success": True, "data": {"Total Network Clicks": total_clicks, "Dashboard": dashboard_data}}

def _edit_link(short_id: str, body: LinkUpdate, current_username: str, conn):
    user_id = get_user_id(conn, current_username)
    expires = KEEP
    if "expires_at" in body.model_fields_set:
        expires = resolve_expiry(body.expires_at)  # None removes the expiry
    try:
        link = update_link(conn, user_id, short_id, str(body.long_url) if body.long_url else None, expires)
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"success": True, "data": link}

def _remove_link(short_id: str, current_username: str, conn):
    user_id = get_user_id(conn, current_username)
    try:
        delete_link(conn, user_id, short_id)
    except LinkError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"success": True, "message": "Link deleted"}

# Changing the alias is not supported: printed links and QR codes would break.
@app.patch("/links/{short_id}")
@limiter.limit("30/minute")
def patch_link(short_id: str, request: Request, body: LinkUpdate, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    return _edit_link(short_id, body, current_username, conn)

# POST twins exist because the bundled nginx only forwards GET, POST and HEAD.
@app.post("/links/{short_id}/update")
@limiter.limit("30/minute")
def update_link_post(short_id: str, request: Request, body: LinkUpdate, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    return _edit_link(short_id, body, current_username, conn)

@app.delete("/links/{short_id}")
@limiter.limit("30/minute")
def delete_link_route(short_id: str, request: Request, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    return _remove_link(short_id, current_username, conn)

@app.post("/links/{short_id}/delete")
@limiter.limit("30/minute")
def delete_link_post(short_id: str, request: Request, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    return _remove_link(short_id, current_username, conn)

@app.post("/api-keys")
@limiter.limit("10/minute")
def create_api_key(request: Request, body: ApiKeyCreate, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    user_id = get_user_id(conn, current_username)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM api_keys WHERE user_id = %s AND revoked_at IS NULL", (user_id,))
    if cursor.fetchone()[0] >= MAX_ACTIVE_API_KEYS:
        raise HTTPException(status_code=400, detail=f"You can have at most {MAX_ACTIVE_API_KEYS} active API keys. Revoke one first.")
    key = au.generate_api_key()
    name = body.name.strip()
    cursor.execute(
        "INSERT INTO api_keys (user_id, name, key_prefix, key_hash) VALUES (%s, %s, %s, %s) RETURNING id, created_at",
        (user_id, name, au.key_display_prefix(key), au.hash_api_key(key)),
    )
    key_id, created_at = cursor.fetchone()
    conn.commit()
    # The full key is returned only here and cannot be retrieved again.
    return {"success": True, "data": {"id": key_id, "name": name, "prefix": au.key_display_prefix(key), "key": key, "created_at": au.iso_utc(created_at)}}

@app.get("/api-keys")
def list_api_keys(current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    user_id = get_user_id(conn, current_username)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, key_prefix, created_at, last_used_at FROM api_keys WHERE user_id = %s AND revoked_at IS NULL ORDER BY created_at DESC",
        (user_id,),
    )
    keys = [
        {"id": r[0], "name": r[1], "prefix": r[2], "created_at": au.iso_utc(r[3]), "last_used_at": au.iso_utc(r[4]) or None}
        for r in cursor.fetchall()
    ]
    return {"success": True, "data": keys}

def _revoke_api_key(key_id: int, current_username: str, conn):
    user_id = get_user_id(conn, current_username)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE api_keys SET revoked_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s AND revoked_at IS NULL",
        (key_id, user_id),
    )
    revoked = cursor.rowcount
    conn.commit()
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True, "message": "API key revoked"}

@app.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: int, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    return _revoke_api_key(key_id, current_username, conn)

# The bundled nginx only forwards GET, POST and HEAD, so the web UI revokes with POST.
@app.post("/api-keys/{key_id}/revoke")
def revoke_api_key_post(key_id: int, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    return _revoke_api_key(key_id, current_username, conn)

@app.get("/connected-apps")
def list_connected_apps(current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    user_id = get_user_id(conn, current_username)
    return {"success": True, "data": oauth.list_grants(user_id)}

@app.post("/connected-apps/{client_id}/revoke")
@limiter.limit("30/minute")
def revoke_connected_app(client_id: str, request: Request, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    user_id = get_user_id(conn, current_username)
    if not oauth.revoke_grant(user_id, client_id):
        raise HTTPException(status_code=404, detail="Connected app not found")
    return {"success": True, "message": "Access revoked"}

def _export_rows(short_id: str):
    """Yield every click for a link, newest first, on its own pooled connection with a server-side cursor."""
    conn = db_pool.getconn()
    try:
        cursor = conn.cursor(name="export_" + secrets.token_hex(6))
        cursor.itersize = 2000
        cursor.execute(
            f"SELECT {au.CLICK_SELECT} FROM click_events WHERE short_id = %s ORDER BY timestamp DESC, id DESC",
            (short_id,),
        )
        for row in cursor:
            yield au.click_record(row)
        cursor.close()
    finally:
        conn.rollback()
        db_pool.putconn(conn)

def _json_chunks(records):
    yield "["
    first = True
    for rec in records:
        yield ("" if first else ",") + json.dumps(rec)
        first = False
    yield "]"

@app.get("/analytics/{short_id}/export")
@limiter.limit("10/minute")
def export_clicks(short_id: str, request: Request, format: Literal["csv", "json"] = "csv", current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    user_id = get_user_id(conn, current_username)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM urls WHERE short_id = %s AND user_id = %s", (short_id, user_id))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Url Not Found or You don't own the Url")
    conn.rollback()  # end this read transaction before the stream takes its own connection
    headers = {"Content-Disposition": f'attachment; filename="hop-{short_id}-clicks.{format}"'}
    if format == "csv":
        return StreamingResponse(au.csv_chunks(_export_rows(short_id)), media_type="text/csv; charset=utf-8", headers=headers)
    return StreamingResponse(_json_chunks(_export_rows(short_id)), media_type="application/json", headers=headers)

def record_click_in_background(short_id: str, ip_address: str, user_agent: str, referer: Optional[str],
                               accept_language: Optional[str] = None, utm: Optional[dict] = None):
    """Runs after the redirect has been sent. The raw IP is used in memory only (visitor hash and
    city-level lookup) and is never stored or logged."""
    conn = db_pool.getconn()
    try:
        cursor = conn.cursor()
        ua = parse(user_agent)
        bot = clicks.is_bot_user_agent(user_agent) or bool(ua.is_bot)
        device_type = "Bot" if bot else "Mobile" if ua.is_mobile else "Tablet" if ua.is_tablet else "PC" if ua.is_pc else "Unknown"
        host, source = clicks.referrer_info(referer)
        utm = utm or {}

        visitor_id = None
        place = dict(geo.EMPTY)
        language = locale = None
        if not bot:  # bots and link previews get no visitor id or location
            visitor_id = clicks.visitor_hash(get_daily_salt(conn), ip_address, user_agent, short_id)
            place = geo.lookup(ip_address)
            language, locale = clicks.parse_language(accept_language)

        cursor.execute(
            "INSERT INTO click_events (short_id, visitor_id, browser, os, device_type, referer, "
            "country_code, country, region, city, language, locale, is_bot, "
            "utm_source, utm_medium, utm_campaign, referrer_host, referrer_source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (short_id, visitor_id, ua.browser.family, ua.os.family, device_type, clicks.referer_origin(referer),
             place["country_code"], place["country"], place["region"], place["city"], language, locale, bot,
             utm.get("utm_source"), utm.get("utm_medium"), utm.get("utm_campaign"), host, source),
        )
        if not bot:
            cursor.execute("UPDATE urls SET clicks = clicks + 1 WHERE short_id = %s", (short_id,))
        conn.commit()
        cursor.close()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error recording click: {type(e).__name__}")
    finally:
        db_pool.putconn(conn)

@app.get("/{short_id}")
def redirect_to_url(short_id: str, request: Request, background_tasks: BackgroundTasks, conn=Depends(get_db)):
    if short_id in RESERVED_ALIASES:
        # Fallback to frontend if accidentally hit directly
        return FileResponse("static/index.html")

    # Only capture request data here; the work happens in the background task.
    ip_address = get_real_ip(request)
    user_agent = request.headers.get("user-agent", "Unknown")
    referer = request.headers.get("referer")
    accept_language = request.headers.get("accept-language")
    utm = clicks.extract_utm(request.query_params)

    cached_url = redis_client.get(short_id)
    if cached_url:
        background_tasks.add_task(record_click_in_background, short_id, ip_address, user_agent, referer, accept_language, utm)
        return RedirectResponse(url=cached_url)

    cursor = conn.cursor()
    cursor.execute("SELECT long_url, expires_at FROM urls WHERE short_id=%s", (short_id,))
    long_url_row = cursor.fetchone()

    if not long_url_row:
        return not_found_page()

    long_url, expires_at = long_url_row
    if is_expired(expires_at):
        # No redirect and no click is recorded for an expired link.
        return expired_page()
    ttl = cache_ttl(expires_at)  # min(1 hour, time until expiry)
    if ttl:
        redis_client.setex(short_id, ttl, long_url)

    background_tasks.add_task(record_click_in_background, short_id, ip_address, user_agent, referer, accept_language, utm)
    
    return RedirectResponse(url=long_url)

@app.get("/analytics/{short_id}")
@limiter.limit("20/minute")
def get_analytics(short_id: str, request: Request, current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_id = cursor.fetchone()[0]
    cursor.execute("SELECT clicks, long_url FROM urls WHERE short_id = %s AND user_id = %s", (short_id, user_id))
    result = cursor.fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Url Not Found or You don't own the Url")

    cursor.execute(
        "SELECT timestamp, visitor_id, device_type, os, browser, referer, country_code, city, referrer_source, language "
        f"FROM click_events WHERE short_id = %s AND {stats.NOT_BOT} ORDER BY timestamp DESC LIMIT 500",
        (short_id,),
    )
    events = cursor.fetchall()
    click_data = [{
        "timestamp": au.iso_utc(e[0]) or None,
        "visitor_id": e[1],
        "device_type": e[2] or "Unknown",
        "os": e[3] or "Unknown",
        "browser": e[4] or "Unknown",
        "referer": e[5] or "Direct",
        "country_code": e[6],
        "city": e[7],
        "source": e[8],
        "language": e[9],
    } for e in events]

    scope_sql, scope_params = stats.link_scope(short_id)
    summary = stats.summary(cursor, scope_sql, scope_params)

    return {"success": True, "data": {"Short ID": short_id, "Long URL": result[1], "Total Clicks": result[0], "History": click_data, "Summary": summary}}

@app.get("/qrcode/{short_id}")
@limiter.limit("10/minute")
def get_qr_code(short_id: str, request: Request, conn=Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT long_url FROM urls WHERE short_id=%s", (short_id,))
    long_url = cursor.fetchone()
    if not long_url:
        raise HTTPException(status_code=404, detail="Url not found")
        
    host = request.headers.get("host", "127.0.0.1:8000")
    protocol = request.headers.get("X-Forwarded-Proto", "http")
    full_url = f"{protocol}://{host}/{short_id}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(full_url)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path)
            max_logo_size = int(qr_img.size[0] * 0.25)
            logo = logo.resize((max_logo_size, max_logo_size), Image.Resampling.LANCZOS)
            
            box = (
                (qr_img.size[0] - max_logo_size) // 2,
                (qr_img.size[1] - max_logo_size) // 2
            )
            logo = logo.convert("RGBA")
            qr_img.paste(logo, box, logo)
        except Exception as e:
            logger.error(f"Failed to add logo to QR code: {e}")

    img_byte_arr = io.BytesIO()
    qr_img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return StreamingResponse(img_byte_arr, media_type="image/png")