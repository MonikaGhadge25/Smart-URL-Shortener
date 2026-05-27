import asyncio
from sqlalchemy import select
from database import AsyncSessionLocal, init_db
from models import User

async def make_admin():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "admin25@gmail.com"))
        user = result.scalar_one_or_none()
        if user:
            user.is_admin = True
            await db.commit()
            print(f"✓ {user.email} is now admin!")
        else:
            print("User not found.")

asyncio.run(make_admin())