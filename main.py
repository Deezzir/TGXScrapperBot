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

load_dotenv()

TITLE = "🔰 XScrapper V1.0"
DESCRIPTION = "The ultimate bot for scrapping Pump.fun drops from Twitter"
TOKEN = getenv("BOT_TOKEN", "")

COMMANDS = {
    "setup": "Setup the chat",
    "run": "Start Twitter scrapper",
    "stop": "Stop Twitter scrapper",
}

if not TOKEN:
    print("BOT_TOKEN is not provided!")
    sys.exit(1)

dp = Dispatcher()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


@dp.message(CommandStart())
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


@dp.message(Command("setup"))
async def command_setup_handler(message: Message) -> None:
    """
    This handler receives messages with `/setup` command
    """
    chat_info = await bot.get_chat(message.chat.id)
    await message.answer("Setup is not available yet.")


@dp.message(Command("run"))
async def command_run_handler(message: Message) -> None:
    """
    This handler receives messages with `/run` command
    """
    if message.chat.is_forum:
        chat_id = message.chat.id
        asyncio.create_task(twitter.run(chat_id, bot))
    else:
        await message.reply("This command is only available in groups with topics.")


@dp.message(Command("stop"))
async def command_stop_handler(message: Message) -> None:
    """
    This handler receives messages with `/stop` command
    """
    chat_id = message.chat.id
    await twitter.stop(chat_id, bot)


@dp.callback_query(F.data == "add_admin")
async def callback_add_admin_handler(query: CallbackQuery) -> None:
    """
    This handler receives callback queries with `add_admin` callback_data
    """
    await query.answer("Adding admin...")


@dp.callback_query(F.data.startswith("block:"))
async def callback_block_handler(query: CallbackQuery) -> None:
    """
    This handler receives callback queries with `block:` callback_data
    """
    if query.message is None or query.data is None or query.message is None:
        return

    member = await bot.get_chat_member(query.message.chat.id, query.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await query.answer("You must be an admin to block users.", show_alert=True)
        return

    query_data = query.data.split(":")
    if len(query_data) != 3:
        return
    username = query_data[1]
    user_id = query_data[2]

    await query.answer(f"Blocking {username}...")
    await db.insert_banned(user_id)

    await bot.edit_message_text(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=f"<b>{username.upper()} IS BANNED</b>",
        parse_mode=ParseMode.HTML,
    )


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
