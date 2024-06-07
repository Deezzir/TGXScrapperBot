from telethon import TelegramClient
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

BOT_APP_ID = os.getenv("BOT_APP_ID")
BOT_APP_HASH = os.getenv("BOT_APP_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")


class TagAll:
    def __init__(self):
        self.client = TelegramClient("tagall", BOT_APP_ID, BOT_APP_HASH)

    async def start(self):
        if not self.client.is_connected():
            await self.client.start(bot_token=BOT_TOKEN)

    async def tagall(self, chat_id: int):
        notifies = []
        async for user in self.client.iter_participants(chat_id):
            notifies.append(f"<a href='tg://user?id={str(user.id)}'>\u206c\u206f</a>")
        return "\u206c\u206f".join(notifies)

    async def stop(self):
        await self.client.disconnect()
