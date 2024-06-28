import asyncio
import logging
import sys
import re
from dotenv import load_dotenv
import twitter
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, CommandObject
import scoring
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
    ChatMemberAdministrator,
)
import db
import utils
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from typing import List
import os
import pools

load_dotenv()

BOT_APP_ID = os.getenv("BOT_APP_ID")
RPC = os.getenv("RPC", "")
BOT_APP_HASH = os.getenv("BOT_APP_HASH")
TOKEN = os.getenv("BOT_TOKEN", "")
SUPERGROUP_ID = int(os.getenv("SUPERGROUP_ID", "0"))
BOT_SESSION = os.getenv("BOT_SESSION", "")
ALLOWED_USERS: List[int] = [
    int(user) for user in os.getenv("ALLOWED_USERS", "").split(",")
]

load_dotenv()

HANDLE = "@XCryptoScrapperBot"
TITLE = "🔰 XScrapper V1.0"
NAME = "XCryptoScrapperBot"
DESCRIPTION = "The ultimate bot for scrapping Pump.fun drops"
SCORER = scoring.Scrapper()
LOGGER = logging.getLogger(__name__)

TARGET_CHANNELS = [
    {"id": -1001999456751, "name": "ferb’s", "link": "https://t.me/ferbsfriends"},
    {"id": -1002158735564, "name": "Qwerty", "link": "https://t.me/QwertysQuants"},
    {"id": -1002089676082, "name": "joji", "link": "https://t.me/jojiinnercircle"},
    {"id": -1002001411256, "name": "Borovik", "link": "https://t.me/borovikTG"},
    {"id": -1002047101414, "name": "Orangie", "link": "https://t.me/orangiealpha"},
    {
        "id": -1002204873147,
        "name": "STARIY YESRT",
        "link": "https://t.me/edrfgthyujiko",
    },
]

COMMANDS = {
    "run": "Start Twitter scrapper",
    "stop": "Stop Twitter scrapper",
    "runpools": "Start new Pump.fun Bonds scrapper",
    "stoppools": "Stop Pump.fun Bonds scrapper",
}

if not TOKEN:
    LOGGER.error("BOT_TOKEN is not provided!")
    sys.exit(1)

DISPATCHER = Dispatcher()
DB = db.MongoDB()
BOT = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
CLIENT = TelegramClient(StringSession(BOT_SESSION), BOT_APP_ID, BOT_APP_HASH)
NEW_POOLS = pools.NewPoolsScrapper(RPC, BOT)
TWITTER = twitter.TwitterScrapper(BOT, DB, SCORER, CLIENT)


@DISPATCHER.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    if message.from_user is not None:
        inline_button = InlineKeyboardButton(
            text="Set me as admin",
            url=f"https://t.me/{NAME}?startgroup=start&amp;admin=can_invite_users",
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


@DISPATCHER.message(Command("run"))
async def command_run_handler(message: Message) -> None:
    """
    This handler receives messages with `/run` command
    """
    if message.chat.id != SUPERGROUP_ID:
        await message.reply("This command is only available in the CALL CENTER.")
    if not message.chat.is_forum:
        await message.reply("This command is only available in groups with topics.")
        return

    chat_id = message.chat.id
    if not message.from_user:
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        await message.answer(
            "The bot must be an admin to start the ticker scrapper.", show_alert=True
        )
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer(
            "You must be an admin to start the scrapper.", show_alert=True
        )
        return

    asyncio.create_task(TWITTER.start(chat_id))


@DISPATCHER.message(Command("runpools"))
async def command_run_pools_handler(message: Message) -> None:
    """
    This handler receives messages with `/runpools` command
    """
    if message.chat.id != SUPERGROUP_ID:
        await message.reply("This command is only available in the CALL CENTER.")

    if not message.chat.is_forum:
        await message.reply("This command is only available in groups with topics.")
        return

    if not message.from_user:
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        await message.answer(
            "The bot must be an admin to start the ticker scrapper.", show_alert=True
        )
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer(
            "You must be an admin to start the scrapper.", show_alert=True
        )
        return

    asyncio.create_task(NEW_POOLS.start(message.chat.id))


@DISPATCHER.message(Command("runticker"))
async def command_run_ticker_handler(message: Message, command: CommandObject) -> None:
    """
    This handler receives messages with `/runticker` command
    """
    if not message.from_user:
        return

    if message.chat.id == SUPERGROUP_ID:
        await message.reply(
            "This command is only available outside of the CALL CENTER."
        )
        return

    if not message.chat.is_forum:
        await message.reply("This command is only available in groups with topics.")
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer(
            "You must be an admin to start the ticker scrapper.", show_alert=True
        )
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if isinstance(bot_member, ChatMemberAdministrator):
        if not bot_member.can_manage_topics:
            await message.answer(
                "The bot must have permission to manage topics to start the ticker scrapper.",
            )
            return
    else:
        await message.answer(
            "The bot must be an admin to start the ticker scrapper.", show_alert=True
        )
        return

    if member.user.id not in ALLOWED_USERS:
        await message.answer(
            "You are not allowed to start the ticker scrapper.", show_alert=True
        )
        return

    arg = command.args
    if not arg:
        await message.answer("Please provide a ticker to start the scrapper.")
        return

    if not re.match(r"^\$[A-Za-z]+$", arg):
        await message.answer("Invalid ticker format. Please provide a valid ticker.")
        return

    topic_ids = await utils.setup_ticker_scrapper(BOT, message.chat.id)
    options = utils.ScrapperOptions(query=arg, topic_ids=topic_ids)
    asyncio.create_task(TWITTER.start(message.chat.id, options=options))


@DISPATCHER.message(Command("stoppools"))
async def command_stop_pools_handler(message: Message) -> None:
    """
    This handler receives messages with `/stoppools` command
    """
    if not message.from_user:
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        await message.answer(
            "The bot must have permission to manage topics to stop the scrapper.",
        )
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer(
            "You must be an admin to stop the scrapper.", show_alert=True
        )
        return

    await NEW_POOLS.stop()


@DISPATCHER.message(Command("stop"))
async def command_stop_handler(message: Message) -> None:
    """
    This handler receives messages with `/stop` command
    """
    if not message.from_user:
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        await message.answer(
            "The bot must have permission to manage topics to stop the scrapper.",
        )
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer(
            "You must be an admin to stop the scrapper.", show_alert=True
        )
        return

    chat_id = message.chat.id
    result = await TWITTER.stop(message.chat.id)
    if result:
        await utils.clear_x_scrapper(BOT, chat_id, result.topic_ids)


@DISPATCHER.callback_query(F.data == "add_admin")
async def callback_add_admin_handler(query: CallbackQuery) -> None:
    """
    This handler receives callback queries with `add_admin` callback_data
    """
    await query.answer("Adding as admin...")


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
    _, username, user_id = query_parts

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


@DISPATCHER.callback_query(F.data.startswith("report:"))
async def callback_report_handler(query: CallbackQuery) -> None:
    """
    This handler receives callback queries with `report:` callback_data
    """
    if query.message is None or query.data is None or query.message is None:
        return

    query_parts = query.data.split(":")
    if len(query_parts) != 3:
        LOGGER.error("Invalid query data format")
        return None
    _, username, user_id = query_parts

    await query.answer(f"Reporting is WIP...")


@CLIENT.on(events.NewMessage(chats=[ch["id"] for ch in TARGET_CHANNELS]))
async def handle_message(event):
    message_text = event.message.message
    message_id = event.message.id
    channel = next((ch for ch in TARGET_CHANNELS if ch["id"] == event.chat_id), None)

    LOGGER.info(f"Received Influencer message from {channel['name']}")

    if channel:
        group_link = channel["link"]
        message_with_link = (
            f"<b>- NEW POST BY {channel['name'].upper()} -</b>\n\n"
            f"<blockquote>{message_text}</blockquote>\n\n"
            f"<a href='{group_link}/{message_id}'>🔗 Source</a>"
        )

        media = event.message.media

        if media:
            if isinstance(media, MessageMediaPhoto):
                await CLIENT.send_file(
                    SUPERGROUP_ID,
                    media.photo,
                    caption=message_with_link,
                    reply_to=14775,
                    parse_mode="html",
                )
            elif isinstance(media, MessageMediaDocument):
                await CLIENT.send_file(
                    SUPERGROUP_ID,
                    media.document,
                    caption=message_with_link,
                    reply_to=14775,
                    parse_mode="html",
                )
            else:
                await CLIENT.send_message(
                    SUPERGROUP_ID,
                    message_with_link,
                    reply_to=14775,
                    parse_mode="html",
                    link_preview=False,
                )
        else:
            await CLIENT.send_message(
                SUPERGROUP_ID,
                message_with_link,
                reply_to=14775,
                parse_mode="html",
                link_preview=False,
            )


async def main() -> None:
    async with CLIENT:
        SCORER.login()
        await DB.initialize()
        await DISPATCHER.start_polling(BOT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
