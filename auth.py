import bcrypt
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException
from sqlalchemy import select
from database import AsyncSessionLocal
from models import User
import os

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-123")
serializer = URLSafeTimedSerializer(SECRET_KEY)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_session_token(user_id: int) -> str:
    return serializer.dumps(user_id, salt="session")

def decode_session_token(token: str):
    try:
        return serializer.loads(token, salt="session", max_age=86400 * 7)
    except Exception:
        return None

async def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    user_id = decode_session_token(token)
    if not user_id:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

async def require_login(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user