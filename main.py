import os
import io
import jwt
import qrcode
import secrets
import logging
from PIL import Image
from typing import Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import RedirectResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, HttpUrl, Field, field_validator

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import psycopg2

from database import init_db, get_db, redis_client, db_pool
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
    msg = errors[0]["msg"] if errors else "Validation Error"
    return JSONResponse(
        status_code=422,
        content={"success": False, "message": msg}
    )

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

RESERVED_ALIASES = {"privacy", "terms", "cookies", "disclaimer", "dashboard", "register", "token", "shorten", "analytics", "qrcode", "health", "static"}

# 5. Strict URL Validation
class URLCreate(BaseModel):
    long_url: HttpUrl
    custom_id: Optional[str] = Field(default=None, pattern="^[a-zA-Z0-9_-]+$")

    @field_validator('long_url')
    @classmethod
    def check_scheme(cls, v):
        if v.scheme not in ('http', 'https'):
            raise ValueError('Only HTTP and HTTPS URLs are allowed')
        return v

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)

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
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_row = cursor.fetchone()
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    user_id = user_row[0]
    
    url_str = str(url.long_url)
    
    cursor.execute("SELECT short_id FROM urls WHERE long_url = %s AND user_id = %s", (url_str, user_id))
    existing_url = cursor.fetchone()
    
    if existing_url and not url.custom_id:
        return {"success": True, "data": {"Long Url": url_str, "Short_ID": existing_url[0]}, "message": "Already existed!"}

    if url.custom_id:
        if url.custom_id.lower() in RESERVED_ALIASES:
            raise HTTPException(status_code=400, detail="That custom alias is reserved.")
        cursor.execute("SELECT short_id FROM urls WHERE short_id = %s", (url.custom_id,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="That custom alias is already taken!")
        short_id = url.custom_id
    else:
        while True:
            short_id = secrets.token_urlsafe(8)
            cursor.execute("SELECT short_id FROM urls WHERE short_id = %s", (short_id,))
            if cursor.fetchone() is None:
                break
                
    try:
        cursor.execute("INSERT INTO urls (short_id, long_url, user_id) VALUES (%s, %s, %s)", (short_id, url_str, user_id))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Failed to create short URL. Try again.")
        
    logger.info(f"URL shortened: {short_id} -> {url_str}")
    return {"success": True, "data": {"Long Url": url_str, "Short_ID": short_id}}

@app.get("/dashboard")
def get_dashboard(current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_id = cursor.fetchone()[0]
    cursor.execute("SELECT short_id, long_url, clicks FROM urls WHERE user_id = %s", (user_id,))
    urls = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM click_events WHERE short_id IN (SELECT short_id FROM urls WHERE user_id = %s)", (user_id,))
    total_clicks_result = cursor.fetchone()
    total_clicks = total_clicks_result[0] if total_clicks_result else 0
    
    dashboard_data = [{"Short ID": u[0], "Long URL": u[1], "Total Clicks": u[2]} for u in urls]
    return {"success": True, "data": {"Total Network Clicks": total_clicks, "Dashboard": dashboard_data}}

def record_click_in_background(short_id: str, ip_address: str, user_agent: str):
    conn = db_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO click_events (short_id, ip_address, user_agent) VALUES (%s, %s, %s)", (short_id, ip_address, user_agent))
        cursor.execute("UPDATE urls SET clicks = clicks + 1 WHERE short_id = %s", (short_id,))
        conn.commit()
        cursor.close()
    except Exception as e:
        logger.error(f"Error recording click: {e}")
    finally:
        db_pool.putconn(conn)

@app.get("/{short_id}")
def redirect_to_url(short_id: str, request: Request, background_tasks: BackgroundTasks, conn=Depends(get_db)):
    if short_id in RESERVED_ALIASES:
        # Fallback to frontend if accidentally hit directly
        return FileResponse("static/index.html")

    ip_address = get_real_ip(request)
    user_agent = request.headers.get("user-agent", "Unknown")

    cached_url = redis_client.get(short_id)
    if cached_url:
        background_tasks.add_task(record_click_in_background, short_id, ip_address, user_agent)
        return RedirectResponse(url=cached_url)

    cursor = conn.cursor()
    cursor.execute("SELECT long_url FROM urls WHERE short_id=%s", (short_id,))
    long_url_row = cursor.fetchone()
    
    if not long_url_row:
        raise HTTPException(status_code=404, detail="Url not found")
        
    long_url = long_url_row[0]
    redis_client.setex(short_id, 3600, long_url)

    background_tasks.add_task(record_click_in_background, short_id, ip_address, user_agent)
    
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

    cursor.execute("SELECT timestamp, ip_address, user_agent FROM click_events WHERE short_id = %s ORDER BY timestamp DESC LIMIT 50", (short_id,))
    events = cursor.fetchall()
    click_data = [{"timestamp": e[0].isoformat() if e[0] else None, "ip": e[1], "browser": e[2]} for e in events]

    return {"success": True, "data": {"Short ID": short_id, "Long URL": result[1], "Total Clicks": result[0], "History": click_data}}

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