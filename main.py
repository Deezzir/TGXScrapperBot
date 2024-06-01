import asyncio
import logging
import sys
from os import getenv
from dotenv import load_dotenv
import twitter
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)
import db
import utils

load_dotenv()

TITLE = "🔰 XScrapper V1.0"
DESCRIPTION = "The ultimate bot for scrapping Pump.fun drops from Twitter"
TOKEN = getenv("BOT_TOKEN", "")
DB = db.MongoDB()
LOGGER = logging.getLogger(__name__)


COMMANDS = {
    "setup": "Setup the chat",
    "run": "Start Twitter scrapper",
    "stop": "Stop Twitter scrapper",
}

if not TOKEN:
    print("BOT_TOKEN is not provided!")
    sys.exit(1)

DISPATCHER = Dispatcher()
BOT = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


@DISPATCHER.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    if message.from_user is not None:
        inline_button = InlineKeyboardButton(
            text="Set me as admin",
            url="https://t.me/XCryptoScrapperBot?startgroup=start&amp;admin=can_invite_users",
            callback_data="add_admin",
        )
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[inline_button]])
        commands_string = "\n".join(
            [f"/{command} - {description}" for command, description in COMMANDS.items()]
        )
        payload = (
            f"{TITLE}\n\n" f"{DESCRIPTION}\n\n" f"Commands:\n" f"{commands_string}\n\n"
        )
        await message.answer(payload, reply_markup=inline_keyboard)


@DISPATCHER.message(Command("setup"))
async def command_setup_handler(message: Message) -> None:
    """
    This handler receives messages with `/setup` command
    """
    chat_info = await BOT.get_chat(message.chat.id)
    await message.answer("Setup is not available yet.")


@DISPATCHER.message(Command("run"))
async def command_run_handler(message: Message) -> None:
    """
    This handler receives messages with `/run` command
    """
    if message.chat.is_forum:
        chat_id = message.chat.id
        asyncio.create_task(twitter.run(chat_id, BOT, DB))
    else:
        await message.reply("This command is only available in groups with topics.")


@DISPATCHER.message(Command("stop"))
async def command_stop_handler(message: Message) -> None:
    """
    This handler receives messages with `/stop` command
    """
    chat_id = message.chat.id
    await twitter.stop(chat_id, BOT)


@DISPATCHER.callback_query(F.data == "add_admin")
async def callback_add_admin_handler(query: CallbackQuery) -> None:
    """
    This handler receives callback queries with `add_admin` callback_data
    """
    await query.answer("Adding admin...")


@DISPATCHER.callback_query(F.data.startswith("block:"))
async def callback_block_handler(query: CallbackQuery) -> None:
    """
    This handler receives callback queries with `block:` callback_data
    """
    if query.message is None or query.data is None or query.message is None:
        return

    member = await BOT.get_chat_member(query.message.chat.id, query.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await query.answer("You must be an admin to block users.", show_alert=True)
        return

    query_parts = query.data.split(":")
    if len(query_parts) != 3:
        LOGGER.error("Invalid query data format")
        return None
    action, username, user_id = query_parts

    await query.answer(f"Blocking {username}...")
    await DB.insert_banned(user_id)

    drop = await DB.get_drop(user_id)
    if drop:
        await utils.delete_message(
            BOT, query.message.chat.id, drop.get("messageIds", [])
        )
        await DB.delete_drop(user_id)

    if isinstance(query.message, Message):
        await BOT.send_message(
            chat_id=query.message.chat.id,
            message_thread_id=query.message.message_thread_id,
            text=f"<b>{username.upper()}</b> has been blocked",
            parse_mode=ParseMode.HTML,
        )


async def main() -> None:
    await DB.initialize()
    await DISPATCHER.start_polling(BOT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
