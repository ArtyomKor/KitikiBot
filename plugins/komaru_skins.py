import asyncio
import random
import traceback
from datetime import datetime, timedelta
from string import ascii_lowercase, digits

from sqlalchemy import select
from telebot.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, \
    InlineKeyboardButton, CallbackQuery
from telethon.events import NewMessage
from telethon.tl.custom import Message
from telethon.tl.types import DocumentAttributeVideo

from config import Config
from database import Session
from database.models import Economy, create_empty_economy_settings, User, Case, UserItem, CaseItem, Trade
from inline import bot
from kitikigram import KitikiClient, KitikiINCS2Chats
from plugins.kitiki_in_cs2 import get_from_id

white_list_symbols = list(ascii_lowercase + digits + "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")

economy_settings: Economy | None = None
economy_update_time = datetime.now()

openings = {}

text_sold = 'Все ваши старые GIF были автоматически проданы\n'

kitiki_client: KitikiClient = None


def format_number(num):
    if num == int(num):
        return str(int(num))
    return str(round(num, 2))


def get_fullname(user):
    if user.username is not None:
        fullname = "@" + user.username
    else:
        fullname = user.first_name
        if user.last_name is not None:
            fullname = f"{fullname} {user.last_name}"
    return fullname


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
    global kitiki_client
    kitiki_client = client
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


async def komaru_limit(client, message, user: User, sell=True, new_count=0):
    limit = len([item for item in user.items if not item.sold]) + new_count >= economy_settings.komaru_limit
    if limit and sell:
        new_balance = await sell_all(client, message, False)
        return new_balance
    return limit


@KitikiClient.on(KitikiINCS2Chats(chats=[Config.INCS2, Config.KITIKI_BOT_FAMILY_ID], pattern="/multi"))
async def multi_case(client: KitikiClient, message: Message):
    case_id = message.text.split(" ")
    if len(case_id) < 2:
        return
    try:
        count = int(case_id[1])
    except:
        return
    if not (2 <= count <= 10):
        await message.reply("Можно открыть от 2 до 10 кейсов за раз")
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

        new_balance = await komaru_limit(client, message, user, True, count - 1)
        if isinstance(new_balance, bool):
            new_balance = user.balance
        if new_balance - (case.price * count) < 0:
            # del openings[message.sender_id]
            await message.reply(
                f"У вас недостаточно средств для покупки кейсов! Кейсы стоят: {format_number(case.price * count)} БУБ")
            return
        user.balance = new_balance - (case.price * count)
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
        await message.reply(
            f"Поздравляем! Вам выпали из кейсов общей стоимостью {format_number(case.price * count)} БУБ:\n\n{msg}\nОбщая сумма выигрыша: {format_number(total_price)} БУБ\n{text_sold if isinstance(new_balance, int) else ''}Текущий баланс: {format_number(user.balance)}")

        if case.owner_id is not None:
            case.owner.balance = case.owner.balance + ((case.price * 10 / 100) * 5)

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
        new_balance = await komaru_limit(client, message, user, True)
        if isinstance(new_balance, bool):
            new_balance = user.balance
        if new_balance - case.price < 0:
            # del openings[message.sender_id]
            await message.reply(
                f"У вас недостаточно средств для покупки кейса! Кейсы стоит: {format_number(case.price)} БУБ")
            return
        user.balance = new_balance - case.price
        items = {item.emoticon: item for item in case.items}
        item, new_message = await send_roulette(client, message.chat_id, list(items.keys()),
                                                f"Открываем {case.name} за {format_number(case.price)} БУБ", message)
        item = items[item]
        # del openings[message.sender_id]
        await client.delete_messages(new_message.peer_id, new_message)
        if case.owner_id is not None:
            case.owner.balance = case.owner.balance + (case.price * 10 / 100)
        msg = await client.get_messages(item.gif_message_chat_id, ids=item.gif_message_id)
        doc = msg.media
        await client.send_file(message.chat_id, doc, reply_to=message,
                               caption=f"Поздравляем! Вам выпала GIF {item.name} за {format_number(item.price)} БУБ\n{text_sold if isinstance(new_balance, int) else ''}Текущий баланс: {format_number(user.balance)} БУБ")
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
        msg = f"Список Комару в профиле {get_fullname(user)}:\n\n" + "\n".join([
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


# @KitikiClient.on(NewMessage(pattern=r"^\/trade(?:\s+\d+)+$"))
# async def trade(client: KitikiClient, message: Message):
#     if message.reply_to is None:
#         await message.reply("Ответьте на сообщение человека, которому хотите отправить обмен")
#         return
#     item_ids = map(int, message.text.removeprefix("/trade ").split())
#     user_message = await client.get_messages(message.chat, ids=message.reply_to.reply_to_msg_id)
#     user = await client.get_entity(get_from_id(user_message))
#     if user.id == message.from_id:
#         await message.reply("Вы не можете отправить Комару себе!")
#         return
#
#     async with Session() as session:
#         if user.username is not None:
#             username = "@" + user.username
#         else:
#             username = user.first_name
#             if user.last_name is not None:
#                 username = f"{username} {user.last_name}"
#
#         sender = await client.get_entity(message.sender_id)
#         if sender.username is not None:
#             my_username = "@" + sender.username
#         else:
#             my_username = sender.first_name
#             if sender.last_name is not None:
#                 my_username = f"{my_username} {sender.last_name}"
#
#         new_user = await get_or_create_user_by_id(user.id, session)
#         if await komaru_limit(client, message, new_user, False, len(item_ids)):
#             await message.reply(
#                 f"Получатель не может получить ваш обмен, так как владеет максимальным количеством GIF!")
#             return
#
#         for item_id in item_ids:
#             item = (await session.execute(
#                 select(UserItem).where(UserItem.id == item_id, UserItem.sold == False))).scalar_one_or_none()
#             if item is None:
#                 await message.reply(f"GIF {item_id} не найдена!")
#                 continue
#             if item.user.tg_id != message.sender_id:
#                 await message.reply(f"GIF {item.id} не ваша!")
#                 continue
#             if item.trade_confirmed is not None:
#                 await message.reply(f"GIF {item.id} уже участвует в обмене!")
#                 continue
#             item.new_user_id = new_user.id
#             item.trade_confirmed = False
#             await client.send_message(user,
#                                       f"Поступил обмен на {item.case_item.name} стоимостью {format_number(item.case_item.price)} БУБ от {my_username}\nДля того, чтобы принять, отправьте `/accept {item.id}`\nДля отказа: `/decline {item.id}`",
#                                       parse_mode="md")
#         await message.reply(
#             f"Обмен отправлен {username}!")
#         await session.commit()


processing = []


@bot.callback_query_handler(func=lambda call: call.data.startswith("accept;"))
async def accept_callback(call: CallbackQuery):
    trade_id = call.data.split(";")
    if len(trade_id) == 1:
        await bot.answer_callback_query(call.id)
        return
    try:
        trade_id = int(trade_id[1])
    except:
        return
    if trade_id in processing:
        await bot.answer_callback_query(call.id)
        return
    processing.append(trade_id)
    async with Session() as session:
        trade = (await session.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
        if trade is None:
            await bot.answer_callback_query(call.id)
            return
        if trade.new_user.tg_id != call.from_user.id:
            await bot.answer_callback_query(call.id, "Этот подарок не ваш!")
            return
        if trade.completed:
            await bot.answer_callback_query(call.id)
            return
        msg = []
        for item_id in trade.items:
            item = (await session.execute(select(UserItem).where(UserItem.id == item_id))).scalar_one_or_none()
            item.user_id = trade.new_user_id
            item.in_trade = False
            msg.append(f"{item.case_item.emoticon} {item.case_item.name} - {item.case_item.price} БУБ")
        trade.completed = True
        tg_user = await kitiki_client.get_entity(trade.user.tg_id)
        await bot.edit_message_text(
            f"Подарок от {get_fullname(tg_user)} успешно принят!" + "\nСодержимое:\n" + "\n".join(msg),
            inline_message_id=call.inline_message_id, reply_markup=InlineKeyboardMarkup())
        await session.commit()
        processing.remove(trade_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("decline;"))
async def decline_callback(call: CallbackQuery):
    trade_id = call.data.split(";")
    if len(trade_id) == 1:
        await bot.answer_callback_query(call.id)
        return
    try:
        trade_id = int(trade_id[1])
    except:
        return
    if trade_id in processing:
        await bot.answer_callback_query(call.id)
        return
    processing.append(trade_id)
    async with Session() as session:
        trade = (await session.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
        if trade is None:
            await bot.answer_callback_query(call.id)
            return
        if trade.new_user.tg_id != call.from_user.id:
            await bot.answer_callback_query(call.id, "Этот подарок не ваш!")
            return
        if trade.completed:
            await bot.answer_callback_query(call.id)
            return
        msg = []
        for item_id in trade.items:
            item = (await session.execute(select(UserItem).where(UserItem.id == item_id))).scalar_one_or_none()
            item.in_trade = False
            msg.append(f"{item.case_item.emoticon} {item.case_item.name} - {item.case_item.price} БУБ")
        trade.completed = True
        tg_user = await kitiki_client.get_entity(trade.user.tg_id)
        await bot.edit_message_text(
            f"Подарок от {get_fullname(tg_user)} отклонён!" + "\nСодержимое:\n" + "\n".join(msg),
            inline_message_id=call.inline_message_id, reply_markup=InlineKeyboardMarkup())
        await session.commit()
        processing.remove(trade_id)


@bot.inline_handler(func=lambda query: query.query.startswith("trade;"))
async def send_trade(query: InlineQuery):
    if query.from_user.id != kitiki_client.me.id:
        await bot.answer_inline_query(query.id, [], cache_time=0)
        return
    trade_id = int(query.query.split(";")[1])
    async with Session() as session:
        trade = (await session.execute(select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
        if trade is None:
            await bot.answer_inline_query(query.id, [], cache_time=0)
            return
        tg_user = await kitiki_client.get_entity(trade.user.tg_id)
        items = []
        for item_id in trade.items:
            item = (await session.execute(select(UserItem).where(UserItem.id == item_id))).scalar_one_or_none()
            items.append(item)
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton("❌ Отказаться", callback_data=f"decline;{trade_id}"),
                     InlineKeyboardButton("✅ Принять", callback_data=f"accept;{trade_id}"))
        result = [InlineQueryResultArticle(f"trade;{trade_id}", "KITIKI_BOT_TRADE", InputTextMessageContent(
            f"Поступил новый подарок от {get_fullname(tg_user)} со следующим содержимым:\n\n" + "\n".join(
                [f"{item.case_item.emoticon} {item.case_item.name} - {item.case_item.price} БУБ" for item in items])),
                                           reply_markup=keyboard)]
        await bot.answer_inline_query(query.id, result, cache_time=0)
        await session.commit()


@KitikiClient.on(NewMessage(pattern=r"^\/gift(?:\s+\d+)+$"))
async def trade(client: KitikiClient, message: Message):
    if bot.user is None:
        await message.reply("Повторите попытку через 5 секунд")
        return
    if message.reply_to is None:
        await message.reply("Ответьте на сообщение человека, которому хотите отправить подарок")
        return
    item_ids = list(map(int, message.text.removeprefix("/gift ").split()))
    if not 1 <= len(item_ids) <= 10:
        await message.reply("Вы можете отправить от 1 до 10 GIF за раз!")
        return
    user_message = await client.get_messages(message.chat, ids=message.reply_to.reply_to_msg_id)
    new_user = await client.get_entity(get_from_id(user_message))
    fullname = get_fullname(new_user)
    if new_user.id == message.from_id:
        await message.reply("Вы не можете отправить GIF себе!")
        return
    success = []
    error = []
    async with Session() as session:
        user = await get_or_create_user(message, session)
        new_user = await get_or_create_user_by_id(new_user.id, session)
        trade = Trade(user_id=user.id, new_user_id=new_user.id, items=[])
        if await komaru_limit(client, message, new_user, False, len(item_ids) - 1) == True:
            await message.reply(
                f"Получатель не может получить ваш обмен, так как владеет максимальным количеством GIF!")
            return
        for item_id in item_ids:
            item = (await session.execute(select(UserItem).where(UserItem.id == item_id))).scalar_one_or_none()
            if item is None:
                error.append(item)
                continue
            if item.user.tg_id != get_from_id(message):
                error.append(item)
                continue
            if item.in_trade or item.sold:
                error.append(item)
                continue
            if item.case_item.collection:
                error.append(item)
                continue

            item.in_trade = True
            success.append(item)
        if len(success) > 0:
            trade.items = [item.id for item in success]
            session.add(trade)
            await session.flush()
            await session.refresh(trade)
            trade_id = trade.id
            msg = "Трейд на:\n" + "\n".join(
                [f"{item.case_item.emoticon} {item.case_item.name} - {format_number(item.case_item.price)} БУБ" for item
                 in
                 success]) + "\n" + f"Общей стоимостью: {format_number(sum([item.case_item.price for item in success]))} БУБ успешно отправлен {fullname}"
            try:
                recv_id = new_user.tg_id
                await session.commit()
                result = (await client.inline_query(bot.user.id, f"trade;{trade_id}", entity=recv_id))
                if len(result) == 0:
                    async with Session() as session_rollback:
                        c_trade = (await session_rollback.execute(
                            select(Trade).where(Trade.id == trade_id))).scalar_one_or_none()
                        if c_trade is not None:
                            c_trade.completed = True
                            for item_id in c_trade.items:
                                c_item = (await session_rollback.execute(
                                    select(UserItem).where(UserItem.id == item_id))).scalar_one_or_none()
                                if c_item is not None:
                                    c_item.in_trade = False
                        await session_rollback.commit()
                    await message.reply("Произошла ошибка при отправке подарка!")
                else:
                    await (result[0]).click()
                    await message.reply(msg)
            except:
                traceback.print_exc()
                await session.rollback()
        else:
            await message.reply(f"В вашем подарке отсутствуют предметы, которые возможно отправить!")


async def trade_check(message: Message, item_id: int, session, for_trade: bool = True):
    item = (await session.execute(
        select(UserItem).where(UserItem.id == item_id, UserItem.sold == False))).scalar_one_or_none()
    if item is None:
        await message.reply(f"GIF с таким ID не найдена!")
        return None
    if for_trade and item.trade_confirmed is None:
        await message.reply(f"Эта GIF не участвует в обмене!")
        return None
    if for_trade:
        user = await get_or_create_user(message, session)
        if item.new_user_id != user.id:
            await message.reply(f"Эта GIF отправлена не вам!")
            return None
    else:
        if item.user.tg_id != message.sender_id:
            await message.reply(f"Эта GIF не ваша!")
            return
    return item


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
        await message.reply("\n".join(msg) + f"\nТекущий баланс: {format_number(item.user.balance)} БУБ")
        await session.commit()


@KitikiClient.on(KitikiINCS2Chats(pattern="/top"))
async def top(client: KitikiClient, message: Message):
    type = message.text.split(" ")
    available_types = ["balance", "profile"]
    if len(type) == 1:
        type = "balance"
    else:
        type = type[1]
    if type not in available_types:
        await message.reply(f"Введите тип из доступных: {', '.join(available_types)}")
        return
    async with Session() as session:
        if type == "balance":
            top_users = (await session.execute(select(User)
                                               .order_by(User.balance.desc())
                                               .limit(15))).scalars().all()
        elif type == "profile":
            items = (await session.execute(select(UserItem).where(UserItem.sold == False))).scalars().all()
            top_users = {}
            for item in items:
                balance = top_users.get(item.user_id, (0,))
                top_users[item.user_id] = (balance[0] + item.case_item.price, item.user)
            top_users = sorted(list(top_users.values()), key=lambda item: item[0], reverse=True)
        msg = []
        skip = 0
        for index, user in enumerate(top_users):
            if type == "balance":
                balance = user.balance
                user = await client.get_entity(user.tg_id)
            elif type == "profile":
                balance = user[0]
                user = await client.get_entity(user[1].tg_id)
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
async def sell_all(client: KitikiClient, message: Message, send: bool = True):
    async with Session() as session:
        user = await get_or_create_user(message, session)
        items = user.items
        new_balance = 0
        for item in items:
            if item.sold or item.in_trade:
                continue
            if item.case_item.collection:
                continue
            user.balance = user.balance + item.case_item.price
            item.sold = True
        new_balance = user.balance
        if send: await message.reply(f"Весь инвентарь был продан! Текущий баланс: {format_number(user.balance)} БУБ")
        await session.commit()
        return new_balance


@KitikiClient.on(NewMessage(chats=[Config.GIF_CHAT]))
async def on_gif(client: KitikiClient, message: Message):
    if message.gif is None:
        return
    await message.reply(f"{message.id} {message.chat_id}")
