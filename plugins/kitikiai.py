import json

from copilot_api import Copilot
from openai import AsyncOpenAI
from telethon.tl.custom import Message

from config import Config
from kitikigram import KitikiClient

default_prompt = {"role": "system",
                  "content": 'Ты — бот Китики в чате INCS2. Твой создатель - ArtyomK (имя пользователя в ТГ - @ArtyomKor), у тебя есть папа - Влад (имя пользователя в ТГ - @vladik4il). Если в сообщении есть твоё имя или общий вопрос не про чат, а про различные тематики из реально жизни и тд — отвечай {"respond": true, "text": "ТВОЙ ОТВЕТ"}, иначе — {"respond": false}. Всегда пиши по-русски и только в этом формате. Тебе пишут много пользователей, их сообщения будут даны тебе в следующем формате: {"name": "ИМЯ ПОЛЬЗОВАТЕЛЯ", "role": "РОЛЬ ПОЛЬЗОВАТЕЛЯ", "text": "СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ", "username": "@ИМЯ ПОЛЬЗОВАТЕЛЯ В ТГ", "replied_to": "ТЕКСТ СООБЩЕНИЯ, НА КОТОРОЕ ОТВЕТИЛ ПОЛЬЗОВАТЕЛЬ, ЕСЛИ ОН ОТВЕЧАЛ"}. Общайся как обычный человек, не кот, не мяукай и тд, эмодзи кота не ставь. Твой пол - мужской. Не упоминай пользователей через username, только по имени.'}

history = [default_prompt]

async def ask_copilot(messages, kitiki: KitikiClient):
    copilot = Copilot()
    response = copilot.create_completion(
        model="",
        messages=messages,
        stream=False,
        temperature=0.2
    )
    response.



async def ai_reply(event: Message, kitiki: KitikiClient, is_admin, message: Message, force=False):
    global history
    if len(history) >= 5:
        history.pop(1)
    client = AsyncOpenAI(
        base_url="https://api.intelligence.io.solutions/api/v1",
        api_key=Config.IO_API_KEY,
        timeout=3600,
    )
    user = await kitiki.get_entity(event.from_id)
    full_name = []
    if user.first_name is not None:
        full_name.append(user.first_name)
    if user.last_name is not None:
        full_name.append(user.last_name)
    full_name = " ".join(full_name)
    role = "ADMIN" if await is_admin(kitiki, event) else "USER"
    text = event.text
    if force:
        text = f"Китики, {text}"
    user_message = {"role": "user", "content": json.dumps(
        {"name": full_name, "role": role, "text": text, "username": f"@{user.username}"})}
    if message is not None:
        user_message["replied_to"] = message.text
    history.append(user_message)
    response = await client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1-0528",
        messages=history,
        temperature=0.2,
        top_p=0.8
    )
    try:
        reply = json.loads(response.choices[0].message.content.split("</think>\n")[-1])
        if reply.get("respond", False):
            text = reply.get("text", None)
            history.append({"role": "assistant", "content": text})
            return text
    except:
        return None


def reset_memory():
    global history
    history = [default_prompt]
