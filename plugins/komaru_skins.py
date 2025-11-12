import asyncio
import random
from datetime import datetime, timedelta
from string import ascii_lowercase, digits

from sqlalchemy import select
from telethon.events import NewMessage
from telethon.tl.custom import Message
from telethon.tl.types import DocumentAttributeVideo

from config import Config
from database import Session
from database.models import Economy, create_empty_economy_settings, User, Case, UserItem, CaseItem
from kitikigram import KitikiClient, KitikiINCS2Chats
from plugins.kitiki_in_cs2 import get_from_id

white_list_symbols = list(ascii_lowercase + digits + "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")

economy_settings: Economy | None = None
economy_update_time = datetime.now()

openings = {}


def format_number(num):
    if num == int(num):
        return str(int(num))
    return str(round(num, 2))


async def get_or_create_user_by_id(user_id: int, session=None) -> User:
    close_session = False
    if session is None:
        session = Session()
        close_session = True
    user = (await session.execute(select(User).where(User.tg_id == user_id))).scalar_one_or_none()
    if user is None:
        user = User(tg_id=user_id, balance=economy_settings.start_balance)
        session.add(user)
    if close_session:
        await session.close()
    return user


async def get_or_create_user(message: Message, session=None) -> User:
    return await get_or_create_user_by_id(message.sender_id, session)


async def update_economy_settings():
    global economy_settings, economy_update_time
    if economy_settings is None or ((datetime.now() - economy_update_time) > timedelta(minutes=5)):
        async with Session() as session:
            economy_settings = (await session.execute(select(Economy))).scalar_one_or_none()
            if economy_settings is None:
                economy_settings = create_empty_economy_settings()
                session.add(economy_settings)
                await session.commit()
            economy_update_time = datetime.now()


@KitikiClient.on(KitikiINCS2Chats(chats=[Config.INCS2, Config.KITIKI_BOT_FAMILY_ID]))
async def on_message(client: KitikiClient, message: Message):
    await message.mark_read()
    await update_economy_settings()
    message_length = len(
        [i for i in list(message.text) if i.lower() in white_list_symbols]) if message.text is not None else 0
    if message.forward is not None or message.sender_id == client.me.id:
        return
    if message.text is not None:
        if message.text.startswith("/"):
            return
    # print(message_length, "VIDEO", message.video, "PHOTO", message.photo, "VOICE", message.voice, "AUDIO", message.audio, "STICKER", message.sticker, "GIF", message.gif, message.grouped_id, sep="\n")
    if not (
            economy_settings.min_message_length <= message_length) and \
            message.video is None and message.photo is None and message.voice is None \
            and message.sticker is None and message.gif is None and message.dice is None:
        return
    bubs = min(message_length * economy_settings.symbol_coast,
               economy_settings.symbol_coast * economy_settings.max_message_length)
    if message.video is not None and message.gif is None and message.sticker is None:
        round_message = False
        for attribute in message.video.attributes:
            if isinstance(attribute, DocumentAttributeVideo):
                if attribute.round_message:
                    round_message = True
        if not round_message:
            bubs += economy_settings.video_coast
        else:
            bubs += economy_settings.video_message_coast
    if message.photo is not None:
        bubs += economy_settings.photo_coast
    if message.voice is not None:
        bubs += economy_settings.voice_message_coast
    if message.sticker is not None:
        bubs += economy_settings.sticker_coast
    if message.gif is not None:
        bubs += economy_settings.gif_coast

    chance = random.random() * 100
    if message.dice is not None:
        if message.dice.emoticon == "🎰" and message.dice.value == 64:
            if chance <= economy_settings.casino_chance:
                bubs += economy_settings.casino_coast
                await message.reply(f"Поздравляем! Вам выпало {format_number(economy_settings.casino_coast)} БУБ!")

    async with Session() as session:
        user = await get_or_create_user(message, session)
        user.balance = round(user.balance + bubs, 2)
        await session.commit()


@KitikiClient.on(KitikiINCS2Chats(chats=[Config.INCS2, Config.KITIKI_BOT_FAMILY_ID], pattern="/balance"))
async def balance(client: KitikiClient, message: Message):
    user = await get_or_create_user(message)
    await message.reply(f"Ваш баланс: {format_number(user.balance)} БУБ")


def get_roulette_message(emojis: list[str], prefix: str | None = None):
    prefix = prefix + '\n' if prefix is not None else ''
    return f"""{prefix}`|🎰 🎲 ⬇️ 🎲 🎰|`
    
`|{" ".join(emojis)}|`

`|🎲 🎰 ⬆️ 🎰 🎲|`"""


async def send_roulette(client: KitikiClient, entity, emojis: list[str], prefix: str | None = None,
                        reply_to: Message | None = None):
    i = 0
    while len(emojis) < 5:
        emojis.append(emojis[i])
        i = i + 1
    random.shuffle(emojis)
    i = 0
    emojis = emojis * 4
    orig_msg = get_roulette_message(emojis[i:i + 5], prefix)
    message = await client.send_message(entity, orig_msg, parse_mode="md", reply_to=reply_to)
    spin = 0
    while spin < 5:
        i = i + 1
        msg = get_roulette_message(emojis[i:i + 5], prefix)
        spin = spin + 1
        if msg != orig_msg: await client.edit_message(message.peer_id, message, msg, parse_mode="md")
        await asyncio.sleep(0.25)
    win_emoji = emojis[i + 2]
    return win_emoji, message


async def komaru_limit(user: User):
    return len([item for item in user.items if not item.sold]) >= economy_settings.komaru_limit


@KitikiClient.on(KitikiINCS2Chats(chats=[Config.INCS2, Config.KITIKI_BOT_FAMILY_ID], pattern="/multi"))
async def multi_case(client: KitikiClient, message: Message):
    case_id = message.text.split(" ")
    if len(case_id) < 2:
        return
    try:
        count = int(case_id[1])
    except:
        return
    if not (2 <= count <= 5):
        await message.reply("Можно открыть от 2 до 5 кейсов за раз")
        return
    if len(case_id) == 3:
        try:
            case_id = int(case_id[2])
            if case_id == 999:
                return
        except:
            return
    else:
        case_id = 1

    async with Session() as session:
        case = (await session.execute(select(Case).where(Case.id == case_id))).scalar()
        if case is None:
            return
        user = await get_or_create_user(message, session)
        current_count = len([item for item in user.items if not item.sold])
        count = min(count, economy_settings.komaru_limit-current_count)

        if await komaru_limit(user):
            # del openings[message.sender_id]
            await message.reply(f"У вас достигнут лимит в {economy_settings.komaru_limit} комару!")
            return
        if user.balance - (case.price*count) < 0:
            # del openings[message.sender_id]
            await message.reply(
                f"У вас недостаточно средств для покупки кейса! Кейсы стоят: {format_number(case.price*count)} БУБ")
            return
        user.balance = user.balance - (case.price*count)
        items = case.items

        win_items = {}
        msg = []
        total_price = 0

        for i in range(count):
            win_item = random.choice(items)
            win_items[win_item.emoticon] = win_item
            user_item = UserItem(user_id=user.id, case_item_id=win_item.id)
            session.add(user_item)
            total_price += win_item.price
            msg.append(f"{win_item.emoticon} {win_item.name} - {format_number(win_item.price)} БУБ")
        msg = "\n".join(msg)
        await message.reply(f"Поздравляем! Вам выпали из кейсов общей стоимостью {format_number(case.price*count)} БУБ:\n\n{msg}\nОбщая сумма выигрыша: {format_number(total_price)} БУБ")

        if case.owner_id is not None:
            case.owner.balance = case.owner.balance + ((case.price*10/100)*5)

        await session.commit()



@KitikiClient.on(KitikiINCS2Chats(chats=[Config.INCS2, Config.KITIKI_BOT_FAMILY_ID], pattern="/case"))
async def case(client: KitikiClient, message: Message):
    case_id = message.text.split(" ")
    if len(case_id) == 1:
        case_id = 1
    else:
        try:
            case_id = int(case_id[1])
            if case_id == 999:
                return
        except:
            return
    if openings.get(message.sender_id, None) is not None:
        return
    # openings[message.sender_id] = True
    async with Session() as session:
        case = (await session.execute(select(Case).where(Case.id == case_id))).scalar()
        if case is None:
            return
        user = await get_or_create_user(message, session)
        if await komaru_limit(user):
            # del openings[message.sender_id]
            await message.reply(f"У вас достигнут лимит в {economy_settings.komaru_limit} комару!")
            return
        if user.balance - case.price < 0:
            # del openings[message.sender_id]
            await message.reply(
                f"У вас недостаточно средств для покупки кейса! Кейс стоит: {format_number(case.price)} БУБ")
            return
        user.balance = user.balance - case.price
        items = {item.emoticon: item for item in case.items}
        item, new_message = await send_roulette(client, message.chat_id, list(items.keys()),
                                                f"Открываем {case.name} за {format_number(case.price)} БУБ", message)
        item = items[item]
        # del openings[message.sender_id]
        await client.delete_messages(new_message.peer_id, new_message)
        if case.owner_id is not None:
            case.owner.balance = case.owner.balance + (case.price/100)
        msg = await client.get_messages(item.gif_message_chat_id, ids=item.gif_message_id)
        doc = msg.media
        await client.send_file(message.chat_id, doc, reply_to=message, caption=f"Поздравляем! Вам выпала GIF {item.name} за {format_number(item.price)} БУБ\nТекущий баланс: {format_number(user.balance)} БУБ")
        user_item = UserItem(user_id=user.id, case_item_id=item.id)
        session.add(user_item)
        await session.commit()


def capitalize(s):
    s = s[0].upper() + s[1:] if s else s
    return s


@KitikiClient.on(KitikiINCS2Chats(chats=[Config.INCS2, Config.KITIKI_BOT_FAMILY_ID], pattern="/profile"))
async def profile(client: KitikiClient, message: Message):
    target_user = message.sender_id
    who = "вас"
    if message.reply_to is not None:
        user_message = await client.get_messages(message.chat, ids=message.reply_to.reply_to_msg_id)
        target_user = get_from_id(user_message)
        who = "пользователя"
    async with Session() as session:
        user = await get_or_create_user_by_id(target_user, session)
        items = [item for item in user.items if not item.sold]
        if len(items) == 0:
            await message.reply(f"У {who} отсутствуют Комару :(")
            return
        user = await client.get_entity(target_user)
        if user.username is not None:
            username = "@" + user.username
        else:
            username = user.first_name
            if user.last_name is not None:
                username = f"{username} {user.last_name}"
        msg = f"Список Комару в профиле {username}:\n\n" + "\n".join([
            f"{item.case_item.emoticon} {capitalize(item.case_item.name)} (`{item.id}`) - {format_number(item.case_item.price)} БУБ"
            for item in
            items if
            not item.sold]) + f"\nОбщая стоимость профиля: {format_number(sum([item.case_item.price for item in items if not item.sold]))} БУБ"
        await message.reply(msg, parse_mode="md")


@KitikiClient.on(KitikiINCS2Chats(pattern=r"^\/showitem (.)"))
async def show_item(client: KitikiClient, message: Message):
    emoticon = message.text.removeprefix("/showitem ")
    async with Session() as session:
        item = (await session.execute(select(CaseItem).where(CaseItem.emoticon == emoticon))).scalar_one_or_none()
        if item is None:
            await message.reply("Не нашли такую гиф!")
            return
        msg = await client.get_messages(item.gif_message_chat_id, ids=item.gif_message_id)
        doc = msg.media
        await client.send_file(message.chat_id, doc,
                               caption=f"{item.emoticon} {item.name} - {format_number(item.price)} БУБ",
                               reply_to=message)


@KitikiClient.on(NewMessage(pattern=r"^\/trade ([0-9]*)"))
async def trade(client: KitikiClient, message: Message):
    if message.reply_to is None:
        await message.reply("Ответьте на сообщение человека, которому хотите отправить обмен")
        return
    item_id = int(message.text.removeprefix("/trade "))
    async with Session() as session:
        item = (await session.execute(
            select(UserItem).where(UserItem.id == item_id, UserItem.sold == False))).scalar_one_or_none()
        if item is None:
            await message.reply(f"Комару с таким ID не найдена!")
            return
        if item.user.tg_id != message.sender_id:
            await message.reply(f"Эта Комару не ваша!")
            return
        if item.trade_confirmed is not None:
            await message.reply(f"Эта Комару уже участвует в обмене!")
            return
        user_message = await client.get_messages(message.chat, ids=message.reply_to.reply_to_msg_id)
        user = await client.get_entity(get_from_id(user_message))
        if user.id == message.from_id:
            await message.reply("Вы не можете отправить Комару себе!")
            return
        if user.username is not None:
            username = "@" + user.username
        else:
            username = user.first_name
            if user.last_name is not None:
                username = f"{username} {user.last_name}"

        sender = await client.get_entity(message.sender_id)
        if sender.username is not None:
            my_username = "@" + sender.username
        else:
            my_username = sender.first_name
            if sender.last_name is not None:
                my_username = f"{my_username} {sender.last_name}"

        new_user = await get_or_create_user_by_id(user.id, session)
        if await komaru_limit(new_user):
            await message.reply(
                f"Получатель не может получить ваш обмен, так как владеет максимальным количеством Комару!")
            return
        item.new_user_id = new_user.id
        item.trade_confirmed = False
        await message.reply(
            f"Обмен на {item.case_item.name} стоимостью {format_number(item.case_item.price)} БУБ отправлен {username}!")
        await client.send_message(user,
                                  f"Поступил обмен на {item.case_item.name} стоимостью {format_number(item.case_item.price)} БУБ от {my_username}\nДля того, чтобы принять, отправьте `/accept {item.id}`\nДля отказа: `/decline {item.id}`",
                                  parse_mode="md")
        await session.commit()


async def trade_check(message: Message, item_id: int, session, for_trade: bool = True):
    item = (await session.execute(
        select(UserItem).where(UserItem.id == item_id, UserItem.sold == False))).scalar_one_or_none()
    if item is None:
        await message.reply(f"Комару с таким ID не найдена!")
        return None
    if for_trade and item.trade_confirmed is None:
        await message.reply(f"Эта Комару не участвует в обмене!")
        return None
    if for_trade:
        user = await get_or_create_user(message, session)
        if item.new_user_id != user.id:
            await message.reply(f"Эта Комару отправлена не вам!")
            return None
    else:
        if item.user.tg_id != message.sender_id:
            await message.reply(f"Эта Комару не ваша!")
            return
    return item


@KitikiClient.on(NewMessage(pattern=r"^\/accept ([0-9]*)"))
async def accept(client: KitikiClient, message: Message):
    item_id = message.text.removeprefix("/accept ")
    async with Session() as session:
        item = await trade_check(message, item_id, session)
        if item is None:
            return
        item.user_id = item.new_user_id
        item.new_user_id = None
        item.trade_confirmed = None
        await message.reply(f"Поздравляем! Теперь {item.case_item.name} в вашем инвентаре!")
        await session.commit()


@KitikiClient.on(NewMessage(pattern=r"^\/decline ([0-9]*)"))
async def decline(client: KitikiClient, message: Message):
    item_id = message.text.removeprefix("/decline ")
    async with Session() as session:
        item = await trade_check(message, item_id, session)
        if item is None:
            return
        item.new_user_id = None
        item.trade_confirmed = None
        await message.reply(f"Вы успешно отказались от обмена.")
        await session.commit()


@KitikiClient.on(NewMessage(pattern=r"^\/sell ([0-9]*)"))
async def sell(client: KitikiClient, message: Message):
    item_ids = list(map(int, message.text.removeprefix("/sell ").split(" ")))
    async with Session() as session:
        msg = []
        for item_id in item_ids:
            item = await trade_check(message, item_id, session, False)
            if item is None:
                return
            if item.new_user_id is not None:
                return
            item.sold = True
            item.user.balance = item.user.balance + item.case_item.price
            msg.append(f"{capitalize(item.case_item.name)} продана за {format_number(item.case_item.price)} БУБ!")
        await message.reply("\n".join(msg)+f"\nТекущий баланс: {format_number(item.user.balance)} БУБ")
        await session.commit()


@KitikiClient.on(KitikiINCS2Chats(pattern="/top"))
async def top(client: KitikiClient, message: Message):
    async with Session() as session:
        top_users = (await session.execute(select(User)
                                           .order_by(User.balance.desc())
                                           .limit(15))).scalars().all()
        msg = []
        skip = 0
        for index, user in enumerate(top_users):
            balance = user.balance
            user = await client.get_entity(user.tg_id)
            if user.username is not None:
                username = user.username
            else:
                username = user.first_name
                if user.last_name is not None:
                    username = f"{username} {user.last_name}"
            if username is None:
                skip += 1
                continue
            index = index - skip
            if index == 0:
                msg.append(f"{index + 1}. 🥇 {username} - {balance} БУБ")
            elif index == 1:
                msg.append(f"{index + 1}. 🥈 {username} - {balance} БУБ")
            elif index == 2:
                msg.append(f"{index + 1}. 🥉 {username} - {balance} БУБ")
            else:
                msg.append(f"{index + 1}. {username} - {balance} БУБ")
        await message.reply("Топ 10 игроков:\n\n" + "\n".join(msg[:10]))


@KitikiClient.on(KitikiINCS2Chats(pattern="/sell_all"))
async def sell_all(client: KitikiClient, message: Message):
    async with Session() as session:
        user = await get_or_create_user(message, session)
        items = user.items
        for item in items:
            if item.sold:
                continue
            if item.new_user_id is not None:
                continue
            user.balance = user.balance + item.case_item.price
            item.sold = True
        await message.reply(f"Весь инвентарь был продан! Текущий баланс: {format_number(user.balance)} БУБ")
        await session.commit()


@KitikiClient.on(NewMessage(chats=[Config.GIF_CHAT]))
async def on_gif(client: KitikiClient, message: Message):
    if message.gif is None:
        return
    await message.reply(f"{message.id} {message.chat_id}")
