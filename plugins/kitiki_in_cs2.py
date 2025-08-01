import asyncio
import random

from sqlalchemy import select
from telethon import events, types
from telethon.tl import functions
from telethon.tl.custom import Message
from telethon.tl.types import UpdateEditChannelMessage, InputMessagesFilterEmpty, ChannelParticipantsAdmins

from config import Config
from database import Session
from database.models import EscortBotDictionary, EscortBotPhrase, EscortBotAdminCall, Emotion, Reply
from kitikigram import KitikiClient, KitikiINCS2Chats
from plugins.kitikiai import ai_reply, reset_memory


async def is_admin(client: KitikiClient, event: Message) -> bool:
    admins = await client.get_participants(event.chat, filter=ChannelParticipantsAdmins)
    if get_from_id(event) in Config.ADMINS:
        return True
    for user in admins:
        if user.id == get_from_id(event):
            return True
    return False


@KitikiClient.on(events.Raw(UpdateEditChannelMessage))
async def on_reaction(client: KitikiClient, event: UpdateEditChannelMessage):
    if event.message.reactions is not None and event.message.peer_id.channel_id is not None:
        if event.message.peer_id.channel_id in [2607018830, 1280394480]:
            reactions = await client.get_reactions(event.message.peer_id.channel_id, event.message.id)
            if len(reactions.reactions) > 0:
                await client.send_react(event.message.peer_id.channel_id, event.message.id,
                                        reactions.reactions[0].reaction)


rare_chance = 7.5
epic_chance = 2.5

send_ids = {"stickers": False, "gifs": False}
ai_disabled = False


@KitikiClient.on(KitikiINCS2Chats(from_users=[955018156], pattern="/stickers"))
async def stickers(client: KitikiClient, event: Message):
    global send_ids
    send_ids["stickers"] = not send_ids["stickers"]
    message = await event.reply(f"Отладка стикеров {'включена' if send_ids['stickers'] else 'отключена'}.")
    await asyncio.sleep(3)
    await message.delete()


@KitikiClient.on(KitikiINCS2Chats(pattern="/reset"))
async def reset(client: KitikiClient, event: Message):
    if await is_admin(client, event):
        reset_memory()
        await event.reply("Память очищена.")

@KitikiClient.on(KitikiINCS2Chats(pattern="/ai"))
async def ai_toggle(client: KitikiClient, event: Message):
    if await is_admin(client, event):
        global ai_disabled
        ai_disabled = not ai_disabled
        await event.reply(f"ИИ {'выключен' if ai_disabled else 'включен'}.")


@KitikiClient.on(KitikiINCS2Chats(from_users=[955018156], pattern="/gifs"))
async def gifs(client: KitikiClient, event: Message):
    global send_ids
    send_ids["gifs"] = not send_ids["gifs"]
    message = await event.reply(f"Отладка GIF {'включена' if send_ids['gifs'] else 'отключена'}.")
    await asyncio.sleep(3)
    await message.delete()


async def escortbot_message_translate(message: str):
    result = []
    cache = {}
    async with Session() as session:
        for char in message:
            cached_char = cache.get(char, None)
            if cached_char is None:
                escortbot_char = (await session.execute(
                    select(EscortBotDictionary).where(EscortBotDictionary.escortbot_char == char))).scalar_one_or_none()
                if escortbot_char is None:
                    escortbot_char = char
                else:
                    escortbot_char = escortbot_char.russian_char
                    cache[char] = escortbot_char
            else:
                escortbot_char = cached_char
            result.append(escortbot_char)
    return "".join(result)


async def check_spam(client: KitikiClient, event: Message):
    detect = False
    try:
        messages = await client(
            functions.messages.SearchRequest(event.chat_id, "", InputMessagesFilterEmpty(), None, None, 0, 0, 10, 0, 0,
                                             0, event.from_id))
        detect = len(messages.messages) <= 5
    except:
        detect = True
    if detect:
        translated = await escortbot_message_translate(event.raw_text.lower())
        phrase_count = 0
        async with Session() as session:
            phrases = (await session.execute(select(EscortBotPhrase))).scalars().all()
            escortbot_phrases = list(map(lambda x: x.escortbot_phrase, phrases))
            for phrase in escortbot_phrases:
                if phrase in translated:
                    phrase_count += 1
            if phrase_count >= 2 or "казино" in translated or event.fwd_from is not None:
                mods = ["@vladik4il", "@big_pank_cs"]
                random.shuffle(mods)
                calls = (await session.execute(select(EscortBotAdminCall))).scalars().all()
                admin_calls = list(map(lambda x: x.escortbot_admin_call, calls))
                call = random.choice(admin_calls)
                await event.reply(f'{" ".join(mods)} {call}')
                await client.send_react_emoticon(event.chat, event.id, "🤡")
                return True
    return False


def get_from_id(message: Message):
    from_id = message.from_id
    if isinstance(from_id, types.PeerUser):
        from_id = from_id.user_id
    elif isinstance(from_id, types.PeerChannel):
        from_id = from_id.channel_id
    return from_id


@KitikiClient.on(KitikiINCS2Chats())
async def woof_woof_woof_woof(client: KitikiClient, event: Message):
    from_id = get_from_id(event)
    if from_id == client.me.id: return
    message = None
    await event.mark_read()
    if await check_spam(client, event):
        return
    if send_ids["stickers"] and await is_admin(client, event) and event.sticker is not None:
        await event.reply(str(event.sticker.id))
        return
    if send_ids["gifs"] and await is_admin(client, event) and event.gif is not None:
        await event.reply(str(event.gif.id))
        return
    if event.reply_to is not None:
        message = await client.get_messages(event.chat, ids=event.reply_to.reply_to_msg_id)
        if get_from_id(message) == client.me.id and "здравствуйте" in event.raw_text.lower():
            await event.reply("Здравствуйте!")
            return
    if "@kitikichatbot" in event.raw_text.lower() and "здравствуйте" in event.raw_text.lower():
        await event.reply("Здравствуйте!")
        return
    chance = random.random() * 100
    choice = None
    if chance < rare_chance:
        choice = "rare"
    elif chance < epic_chance:
        choice = "epic"
    if event.sticker is not None or event.gif is not None:
        async with Session() as session:
            media = event.sticker if event.sticker is not None else event.gif
            emote = (await session.execute(select(Emotion).where(Emotion.media_id == media.id))).scalar_one_or_none()
            if emote is not None:
                await client.send_react_emoticon(event.chat, event.id, emote.emoticon)
            reply = (await session.execute(select(Reply).where(Reply.media_id == media.id))).scalar_one_or_none()
            if reply is not None:
                if reply.rare is not None and reply.epic is not None:
                    emoticon = '😁'
                    reply_text = None
                    if choice is not None:
                        emoticon = '🤯'
                        reply_text = reply.rare
                    if choice == "epic":
                        emoticon = '😱'
                        reply_text = reply.epic
                    await client.send_react_emoticon(event.chat, event.id, emoticon)
                    if reply_text is not None:
                        await event.reply(reply_text)
                elif reply.gif_id is not None and event.reply_to is None:
                    await client.send_file(event.chat, event.media, reply_to=event.id)
                return
    if event.text is not None and event.text != "" and not ai_disabled:
        await client(functions.messages.SetTypingRequest(
                peer=event.chat_id,
                action=types.SendMessageTypingAction()
            ))
        force = False
        if message is not None:
            if get_from_id(message) == client.me.id:
                force = True
        reply = await ai_reply(event, client, is_admin, message, force)
        if reply is not None:
            await event.reply(reply, parse_mode="Markdown")
        await client(functions.messages.SetTypingRequest(
            peer=event.chat_id,
            action=types.SendMessageCancelAction()
        ))
