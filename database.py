from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./shortener.db")

# Convert MySQL URL to async version
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+aiomysql://", 1)
elif DATABASE_URL.startswith("mysql+mysqlconnector://"):
    DATABASE_URL = DATABASE_URL.replace("mysql+mysqlconnector://", "mysql+aiomysql://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    from models import URL, Click, User, LoginLog, SiteVisit
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)