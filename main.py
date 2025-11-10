import asyncio

from sqlalchemy import select

from config import Config
from database import create_tables, Session
from database.models import Economy, create_empty_economy_settings
from inline import main_loop
from kitikigram import KitikiClient


async def before_start(client: KitikiClient):
    await create_tables()
    async with Session() as session:
        economy_settings = (await session.execute(select(Economy))).scalar_one_or_none()
        if economy_settings is None:
            economy_settings = create_empty_economy_settings()
            session.add(economy_settings)
            await session.commit()

    asyncio.create_task(main_loop())


client = KitikiClient(Config.SESSION, Config.API_ID, Config.API_HASH, plugins=["plugins"], before_start=before_start,
                      device_model="KitikiBot Host", app_version="1.0.0")

client.start()
client.run_until_disconnected()
