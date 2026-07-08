from importlib import _bootstrap_external
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse, FileResponse
from typing import Dict, Optional
import uvicorn
from pydantic import BaseModel, HttpUrl, Field
import secrets
from contextlib import asynccontextmanager
from database import init_db
import psycopg2
from database import get_db
from security import get_password_hash
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends
from security import verify_password, create_access_token
from fastapi.security import OAuth2PasswordBearer
import jwt
from security import SECRET_KEY, ALGORITHM
import qrcode
import io
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from database import get_db, redis_client, db_pool
from PIL import Image
import os

from fastapi import Depends, BackgroundTasks

oauth2_scheme=OAuth2PasswordBearer(tokenUrl="token")


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


class URLCreate(BaseModel):
    long_url: HttpUrl
    custom_id: Optional[str] = Field(default=None, pattern="^[a-zA-Z0-9_-]+$")

class UserCreate(BaseModel):
    username:str
    password:str

class Token(BaseModel):
    access_token:str
    token_type:str


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    init_db()
    print("Database initialised")
    yield  

app = FastAPI(lifespan=lifespan)
limiter=Limiter(key_func=get_remote_address)
app.state.limiter=limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount the static directory for the Frontend UI
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")

@app.post("/register")
def register(user:UserCreate, conn=Depends(get_db)):
    
    cursor=conn.cursor()
    hashed_pw=get_password_hash(user.password)
    try:
        cursor.execute("INSERT INTO users (username,password) VALUES (%s,%s)",(user.username,hashed_pw))
        conn.commit()
        return {"message":"User registered successfully"}
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400,detail="Username already exists")

@app.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
    cursor=conn.cursor()
    cursor.execute("SELECT * FROM USERS where username=%s",(form_data.username,))
    user=cursor.fetchone()
    if user==None:
        raise HTTPException(status_code=401,detail="Incorrect username")
    if not verify_password(form_data.password,user[2]):
        raise HTTPException(status_code=401,detail="Incorrect password")
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token":access_token,"token_type":"bearer"}


@app.post("/shorten")
@limiter.limit("5/minute")
def shorten(request: Request, url:URLCreate, current_username: str=Depends(get_current_user), conn=Depends(get_db)):
    cursor=conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT short_id FROM urls WHERE long_url = %s AND user_id = %s", (str(url.long_url), user_id))
    existing_url = cursor.fetchone()
    
    if existing_url and not url.custom_id:
        return {"Long Url": str(url.long_url), "Short_ID": existing_url[0], "Message": "Already existed!"}

    
    if url.custom_id:
        cursor.execute("SELECT short_id FROM urls WHERE short_id = %s", (url.custom_id,))
        is_taken = cursor.fetchone()
        if is_taken:
            raise HTTPException(status_code=400, detail="That custom alias is already taken!")
        short_id = url.custom_id
    else:
        short_id = secrets.token_urlsafe(8)
        while True:
            cursor.execute("SELECT short_id FROM urls WHERE short_id = %s", (short_id,))
            if cursor.fetchone() is None:
                break
            short_id = secrets.token_urlsafe(8)
    cursor.execute("INSERT INTO urls (short_id, long_url, user_id) VALUES (%s, %s, %s)", (short_id, str(url.long_url), user_id))
    conn.commit()
    return {"Long Url": str(url.long_url), "Short_ID": short_id}

@app.get("/dashboard")
def get_dashboard(current_username: str = Depends(get_current_user), conn=Depends(get_db)):
    cursor=conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_id = cursor.fetchone()[0]
    cursor.execute("SELECT short_id, long_url, clicks FROM urls WHERE user_id = %s", (user_id,))
    urls = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM click_events WHERE short_id IN (SELECT short_id FROM urls WHERE user_id = %s)", (user_id,))
    total_clicks_result = cursor.fetchone()
    total_clicks = total_clicks_result[0] if total_clicks_result else 0
    
    dashboard_data = [{"Short ID": u[0], "Long URL": u[1], "Total Clicks": u[2]} for u in urls]
    return {"Total Network Clicks": total_clicks, "Dashboard": dashboard_data}

# This function runs silently in the background AFTER the user has already been redirected!
def record_click_in_background(short_id: str, ip_address: str, user_agent: str):
    conn = db_pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO click_events (short_id, ip_address, user_agent) VALUES (%s, %s, %s)", (short_id, ip_address, user_agent))
        cursor.execute("UPDATE urls SET clicks = clicks + 1 WHERE short_id = %s", (short_id,))
        conn.commit()
        cursor.close()
    finally:
        db_pool.putconn(conn)

@app.get("/{short_id}")
def redirect_to_url(short_id: str, request: Request, background_tasks: BackgroundTasks, conn=Depends(get_db)):
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent")

    cached_url = redis_client.get(short_id)
    if cached_url:
        print(f"CACHE HIT! Redirecting instantly to {cached_url}")
        background_tasks.add_task(record_click_in_background, short_id, ip_address, user_agent)
        return RedirectResponse(url=cached_url)

    print("CACHE MISS! Querying Postgres...")

    cursor = conn.cursor()
    cursor.execute("SELECT long_url FROM urls where short_id=%s", (short_id,))
    long_url_row = cursor.fetchone()
    
    if not long_url_row:
        raise HTTPException(status_code=404, detail="Url not found")
        
    long_url = long_url_row[0]
    
    redis_client.setex(short_id, 3600, long_url)

    background_tasks.add_task(record_click_in_background, short_id, ip_address, user_agent)
    
    return RedirectResponse(url=long_url)


@app.get("/analytics/{short_id}")
@limiter.limit("10/minute")
def get_analytics(short_id:str, request: Request, current_username: str= Depends(get_current_user), conn=Depends(get_db)):
    cursor=conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
    user_id = cursor.fetchone()[0]
    cursor.execute("SELECT clicks, long_url FROM urls WHERE short_id = %s AND user_id = %s", (short_id, user_id))
    result = cursor.fetchone()

    if not result:
        raise HTTPException(status_code=404,detail="Url Not Found or You don't own the Url")

    cursor.execute("SELECT timestamp, ip_address, user_agent FROM click_events WHERE short_id = %s", (short_id,))
    events = cursor.fetchall()
    click_data = [{"timestamp": e[0], "ip": e[1], "browser": e[2]} for e in events]

    return {"Short ID": short_id, "Long URL": result[1], "Total Clicks": result[0], "History":click_data}


@app.get("/qrcode/{short_id}")
@limiter.limit("10/minute")
def get_qr_code(short_id:str, request: Request, conn=Depends(get_db)):
    cursor=conn.cursor()
    cursor.execute("SELECT long_url FROM urls where short_id=%s",(short_id,))
    long_url=cursor.fetchone()
    if not long_url:
        raise HTTPException(status_code=404, detail="Url not found")
        
    full_url = f"http://127.0.0.1:8000/{short_id}"
    
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
        logo = Image.open(logo_path)
        # Calculate size for logo
        box = (
            (qr_img.size[0] - logo.size[0]) // 2,
            (qr_img.size[1] - logo.size[1]) // 2
        )
        # Resize logo if it's too big (max 25% of QR code size)
        max_logo_size = int(qr_img.size[0] * 0.25)
        logo = logo.resize((max_logo_size, max_logo_size), Image.Resampling.LANCZOS)
        
        # Recalculate position
        box = (
            (qr_img.size[0] - max_logo_size) // 2,
            (qr_img.size[1] - max_logo_size) // 2
        )
        # Convert logo to RGBA to handle transparency, then paste
        logo = logo.convert("RGBA")
        qr_img.paste(logo, box, logo)

    img_byte_arr = io.BytesIO()
    qr_img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return StreamingResponse(img_byte_arr, media_type="image/png")

    