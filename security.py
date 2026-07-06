from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "my_super_secret_key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_password_hash(password: str) -> str:
    """Takes a plain text password and returns a securely hashed version."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a plain text password matches the hashed version."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    """Takes a dictionary of data (like user_id) and creates a secure 30-minute JWT."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
