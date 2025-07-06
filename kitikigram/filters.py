from telethon.events import NewMessage

from config import Config

class KitikiINCS2Chats(NewMessage):
    def __init__(self, chats: list[int] = None, **kwargs):
        if chats is None:
            chats = Config.CHATS
        else:
            chats.append(*Config.CHATS)
        kwargs.pop("chats", None)
        super().__init__(chats=chats, **kwargs)
