import asyncio

from config import Config
from database import create_tables
from inline import main_loop
from kitikigram import KitikiClient


async def before_start(client: KitikiClient):
    await create_tables()
    asyncio.create_task(main_loop())


client = KitikiClient(Config.SESSION, Config.API_ID, Config.API_HASH, plugins=["plugins"], before_start=before_start,
                      device_model="KitikiBot Host", app_version="1.0.0")

client.start()
client.run_until_disconnected()
