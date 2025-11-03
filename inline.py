import dataclasses
import datetime as dt
import traceback
from dataclasses import dataclass
from typing import NamedTuple
from zoneinfo import ZoneInfo

import aiohttp
from babel.dates import format_datetime as babel_format_datetime
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, Message

from config import Config

bot = AsyncTeleBot(Config.INLINE_TOKEN)


@bot.inline_handler(lambda query: not query.query.startswith("mute;"))
async def default_query(inline_query):
    print("ALO")
    try:
        await default_inline(inline_query)
    except Exception as e:
        traceback.print_exc()


class State(NamedTuple):
    literal: str
    l10n_key: str


class States:
    LOW = State('low', "низкая")
    MEDIUM = State('medium', "средняя")
    HIGH = State('high', "высокая")
    FULL = State('full', "полная")
    NORMAL = State('normal', "в норме")
    SURGE = State('surge', "помехи")
    DELAYED = State('delayed', "задержка")
    IDLE = State('idle', "бездействие")
    OFFLINE = State('offline', "офлайн")
    CRITICAL = State('critical', "критическая")
    INTERNAL_SERVER_ERROR = State('internal server error', "внутренняя ошибка сервера")
    INTERNAL_BOT_ERROR = State('internal bot error', "внутренняя ошибка бота")
    RELOADING = State('reloading', "перезагрузка")
    INTERNAL_STEAM_ERROR = State('internal Steam error', "внутренняя ошибка Steam")
    UNKNOWN = State('unknown', "Сиберяк всё сломал")

    @classmethod
    def get(cls, data, default=None) -> State | None:
        data = str(data).replace(' ', '_').upper()

        return getattr(cls, data, default)

    @classmethod
    def get_or_unknown(cls, data: str | None) -> State:
        return cls.get(data, States.UNKNOWN)


@dataclass(frozen=True, slots=True)
class BasicServerStatusData:
    info_requested_datetime: dt.datetime
    sessions_logon_state: State

    def is_maintenance(self):
        now = dt.datetime.now(dt.UTC)

        between_tuesday_and_wednesday = (now.weekday() == 1 and now.hour > 21) or (now.weekday() == 2 and now.hour < 4)
        sessions_logon_is_fine = (self.sessions_logon_state is States.NORMAL)
        return between_tuesday_and_wednesday and not sessions_logon_is_fine

    def asdict(self):
        return dataclasses.asdict(self)


@dataclass(frozen=True, slots=True)
class ServerStatusData(BasicServerStatusData):
    matchmaking_scheduler_state: State
    steam_community_state: State
    webapi_state: State


@dataclass(frozen=True, slots=True)
class MatchmakingStatsData(BasicServerStatusData):
    graph_url: str
    online_servers: int
    active_players: int
    searching_players: int
    average_search_time: int


class GameVersionData(NamedTuple):
    cs2_client_version: int | str
    cs2_server_version: int | str
    cs2_patch_version: str
    cs2_version_timestamp: float | str

    def asdict(self):
        return self._asdict()


def format_datetime(datetime: dt.datetime):
    tz = f"{datetime:%Z}"
    return f'{babel_format_datetime(datetime, "HH:mm:ss, dd MMM", locale="RU").title()}' + f" ({tz})" if tz != '' else ''


def format_server_status(data: ServerStatusData) -> str:
    if data is States.UNKNOWN:
        return "🧐 Извините, что-то пошло не так. Пожалуйста, попробуйте позже."

    tick = '✅' if (data.sessions_logon_state
                   == data.matchmaking_scheduler_state == States.NORMAL) else '❌'
    states = tuple(state.l10n_key for state in (data.webapi_state, data.sessions_logon_state,
                                                data.matchmaking_scheduler_state,
                                                data.steam_community_state))

    game_servers_dt = format_datetime(data.info_requested_datetime)

    status_text = """{} **Состояние служб Counter-Strike:**

• Counter-Strike API: {}
• Авторизация сессий: {}
• Планировщик матчмейкинга: {}
• Инвентари игроков: {}""".format(tick, *states)

    text = (
        f'{status_text}'
        f'\n\n'
        f'{"Последнее обновление данных: {}".format(game_servers_dt)}'
    )

    if data.is_maintenance():
        text += f'\n\n🛠️ **Steam отключается на плановое техобслуживание каждый вторник.**'

    return text


def format_matchmaking_stats(data: MatchmakingStatsData) -> str:
    if data is States.UNKNOWN:
        return "🧐 Извините, что-то пошло не так. Пожалуйста, попробуйте позже."

    game_servers_dt = format_datetime(data.info_requested_datetime)

    packed = (data.online_servers,
              data.active_players, data.searching_players, data.average_search_time)

    stats_matchmaking_text = """📊 **Статистика матчмейкинга:**
    
• Серверов в сети: {:,}
• Активных игроков: {:,}
• Игроков в поиске: {:,}
• Примерное время поиска: {} с."""

    text = (
        f'{stats_matchmaking_text.format(*packed)}'
        f'\n\n'
        f'{"Последнее обновление данных: {}".format(game_servers_dt)}'
    )

    if data.is_maintenance():
        text += f'\n\n🛠️ **Steam отключается на плановое техобслуживание каждый вторник.**'

    return text


def format_game_version_info(data: GameVersionData) -> str:
    cs2_version_dt = (dt.datetime.fromtimestamp(data.cs2_version_timestamp)
                      .replace(tzinfo=VALVE_TIMEZONE).astimezone(dt.UTC))

    cs2_version_dt = format_datetime(cs2_version_dt)

    game_version_text = """⚙️ Текущая версия игры: `{}` `({})`
    
Последнее обновление: {}"""

    return game_version_text.format(data.cs2_patch_version, data.cs2_client_version, cs2_version_dt)


CLOCKS = ('🕛', '🕐', '🕑', '🕒', '🕓', '🕔',
          '🕕', '🕖', '🕗', '🕘', '🕙', '🕚')
VALVE_TIMEZONE = ZoneInfo('America/Los_Angeles')
MINUTE = 60
HOUR = 60 * MINUTE


def format_valve_hq_time() -> str:
    valve_hq_datetime = dt.datetime.now(tz=VALVE_TIMEZONE)

    valve_hq_dt_formatted = format_datetime(valve_hq_datetime)

    return "{} Время в Белвью (штаб-кв. Valve): {}".format(CLOCKS[valve_hq_datetime.hour % 12], valve_hq_dt_formatted)


def drop_cap_reset_timer() -> tuple[int, int, int, int]:
    """Get drop cap reset time"""

    wanted_weekday = 1
    wanted_time = 18

    now = dt.datetime.now(tz=VALVE_TIMEZONE)
    # if is_pdt(now):
    #     wanted_time += 1

    days_until_wanted_weekday = (wanted_weekday - now.weekday()) % 7

    wanted_datetime = now + dt.timedelta(days=days_until_wanted_weekday)
    wanted_datetime = wanted_datetime.replace(hour=wanted_time, minute=0, second=0, microsecond=0)

    time_left = wanted_datetime - now

    days_left = time_left.days % 7
    hours_left = time_left.seconds // HOUR
    minutes_left = time_left.seconds % HOUR // MINUTE
    seconds_left = time_left.seconds % MINUTE
    return days_left, hours_left, minutes_left, seconds_left


async def steam_webapi_method(interface: str, method: str, version: int, params: dict = None):
    params = params.copy() if params else {}
    params['key'] = Config.STEAM_API_KEY
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.steampowered.com/{interface}/{method}/v{version}/', params=params,
                               headers={}, timeout=15) as response:
            try:
                return await response.json()
            except aiohttp.ContentTypeError:
                return response


cache = {"server_status": {"dt": 0, "data": None}, "matchmaking_status": {"dt": 0, "data": None},
         "version_data": {"dt": 0, "data": None}}


async def get_server_status():
    if cache["server_status"]["dt"] < (dt.datetime.now() - dt.timedelta(minutes=5)).timestamp() or \
            cache["server_status"]["data"] is None:
        response = await steam_webapi_method('ICSGOServers_730', 'GetGameServersStatus', 1)
        if not isinstance(response, dict):
            return States.UNKNOWN
        result = response['result']
        services = result['services']
        matchmaking = result['matchmaking']
        data = ServerStatusData(dt.datetime.now(dt.UTC), States.get(services['SessionsLogon']),
                                States.get(matchmaking['scheduler']), States.get(services['SteamCommunity']),
                                States.NORMAL)
        cache["server_status"]["dt"] = dt.datetime.now().timestamp()
        cache["server_status"]["data"] = data
    else:
        data = cache["server_status"]["data"]
    return data


async def get_matchmaking_stats():
    if cache["matchmaking_status"]["dt"] < (dt.datetime.now() - dt.timedelta(minutes=5)).timestamp() or \
            cache["matchmaking_status"]["data"] is None:
        response = await steam_webapi_method('ICSGOServers_730', 'GetGameServersStatus', 1)
        if not isinstance(response, dict):
            return States.UNKNOWN
        result = response['result']
        services = result['services']
        matchmaking = result['matchmaking']
        data = MatchmakingStatsData(dt.datetime.now(dt.UTC), States.get(services['SessionsLogon']), None,
                                    matchmaking['online_servers'] or 0, matchmaking['online_players'] or 0,
                                    matchmaking['searching_players'] or 0, matchmaking['search_seconds_avg'] or 0)
        cache["matchmaking_status"]["dt"] = dt.datetime.now().timestamp()
        cache["matchmaking_status"]["data"] = data
    else:
        data = cache["matchmaking_status"]["data"]
    return data


async def get_version_data():
    if cache["version_data"]["dt"] < (dt.datetime.now() - dt.timedelta(minutes=5)).timestamp() or \
            cache["version_data"]["data"] is None:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    "https://raw.githubusercontent.com/SteamDatabase/GameTracking-CS2/master/game/csgo/steam.inf") as response:
                cs2_data = await response.text()
                config_entries = (line for line in cs2_data.split('\n') if line)

                options = {}
                for entry in config_entries:
                    key, val = entry.split('=')
                    options[key] = val

                version_datetime = dt.datetime.strptime(f'{options["VersionDate"]} {options["VersionTime"]}',
                                                        '%b %d %Y %H:%M:%S')

                cs2_client_version = int(options['ClientVersion']) - 2000000
                cs2_server_version = int(options['ServerVersion']) - 2000000
                cs2_patch_version = options['PatchVersion']
                cs2_version_timestamp = version_datetime.timestamp()

                data = GameVersionData(cs2_client_version,
                                       cs2_server_version,
                                       cs2_patch_version,
                                       cs2_version_timestamp)
                cache["version_data"]["dt"] = dt.datetime.now().timestamp()
                cache["version_data"]["data"] = data
    else:
        data = cache["version_data"]["data"]
    return data


def parse_tg_markdown(text):
    return text.replace("-", r"\-").replace(".", r"\.").replace("(", r"\(").replace(")", r"\)").replace("=",
                                                                                                        r"\=").replace(
        ">", r"\>")


async def default_inline(inline_query: InlineQuery):
    servers_status_data = await get_server_status()
    matchmaking_stats_data = await get_matchmaking_stats()
    game_version_data = await get_version_data()

    server_status_text = parse_tg_markdown(format_server_status(servers_status_data))
    matchmaking_stats_text = parse_tg_markdown(format_matchmaking_stats(matchmaking_stats_data))
    valve_hq_time_text = parse_tg_markdown(format_valve_hq_time())
    drop_cap_reset_timer_text = parse_tg_markdown(
        "⏳ Время до сброса ограничений опыта и дропа: {} д. {} ч. {} мин. {} сек.".format(
            *drop_cap_reset_timer()))
    game_version_text = parse_tg_markdown(format_game_version_info(game_version_data))

    server_status = InlineQueryResultArticle("0", "Состояние серверов",
                                             InputTextMessageContent(server_status_text, parse_mode="MarkdownV2"),
                                             description="Проверить доступность серверов",
                                             thumbnail_url="https://telegra.ph/file/8b640b85f6d62f8ed2900.jpg")
    matchmaking_stats = InlineQueryResultArticle("1", "Статистика ММ",
                                                 InputTextMessageContent(matchmaking_stats_text,
                                                                         parse_mode="MarkdownV2"),
                                                 description="Посмотреть количество онлайн игроков",
                                                 thumbnail_url="https://telegra.ph/file/57ba2b279c53d69d72481.jpg")
    valve_hq_time = InlineQueryResultArticle("2", "Время в Белвью",
                                             InputTextMessageContent(valve_hq_time_text, parse_mode="MarkdownV2"),
                                             description="Время в штаб-кв. Valve",
                                             thumbnail_url="https://telegra.ph/file/24b05cea99de936fd12bf.jpg")
    drop_cap_reset = InlineQueryResultArticle("3", "Сброс ограничений",
                                              InputTextMessageContent(drop_cap_reset_timer_text,
                                                                      parse_mode="MarkdownV2"),
                                              description="Время до сброса ограничений опыта и дропа",
                                              thumbnail_url="https://telegra.ph/file/6948255408689d2f6a472.jpg")
    game_version = InlineQueryResultArticle("4", "Версия игры",
                                            InputTextMessageContent(game_version_text, parse_mode="MarkdownV2",
                                                                    disable_web_page_preview=True),
                                            description="Проверить последнюю версию игры",
                                            thumbnail_url="https://telegra.ph/file/82d8df1e9f5140da70232.jpg")

    results = [server_status, matchmaking_stats, valve_hq_time, drop_cap_reset, game_version]
    await bot.answer_inline_query(inline_query.id, results, cache_time=10)


@bot.message_handler(commands=["start"])
async def start_command(message: Message):
    await bot.reply_to(message, message.text)

async def main_loop():
    await bot.infinity_polling(skip_pending=True)
