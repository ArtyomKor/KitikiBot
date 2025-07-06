from sqlalchemy import NullPool
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.session import async_sessionmaker

from config import Config
from database.model_base import Base

DB_URL = URL.create(
    drivername="mysql+asyncmy",
    username=Config.DB_LOGIN,
    password=Config.DB_PASSWORD,
    host=Config.DB_HOST,
    port=Config.DB_PORT,
    database=Config.DB_NAME,
)

engine = create_async_engine(
    url=DB_URL, poolclass=NullPool
)
Session = async_sessionmaker(bind=engine)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all(engine))
