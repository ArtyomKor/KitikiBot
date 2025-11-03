from os import getenv

from dotenv import load_dotenv

load_dotenv()


class Config:
    API_ID = int(getenv('API_ID'))
    API_HASH = getenv('API_HASH')
    SESSION = getenv('SESSION')
    DB_NAME = getenv("DB_NAME")
    DB_LOGIN = getenv("DB_LOGIN")
    DB_HOST = getenv("DB_HOST")
    DB_PORT = int(getenv("DB_PORT"))
    DB_PASSWORD = getenv("DB_PASSWORD")
    CHATS = list(map(int, getenv("CHATS").split(",")))
    ADMINS = list(map(int, getenv("ADMINS").split(",")))
    ADMIN_USERNAMES = list(map(lambda x: x.lower(), getenv("ADMIN_USERNAMES").split(",")))
    INLINE_TOKEN = getenv("INLINE_TOKEN")
    STEAM_API_KEY = getenv("STEAM_API_KEY")
    IO_API_KEY = getenv("IO_API_KEY")
    NOTIFY_ADMINS = list(map(int, getenv("NOTIFY_ADMINS").split(",")))
    KITIKI_BOT_FAMILY_ID = int(getenv("KITIKI_BOT_FAMILY_ID"))
