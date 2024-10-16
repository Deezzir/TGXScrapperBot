import asyncio
import logging
import os
import re
import sys
from typing import Dict, List

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatMemberAdministrator, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from telethon import TelegramClient, events  # type: ignore
from telethon.sessions import StringSession  # type: ignore
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto  # type: ignore

import db
import pools
import scoring
import twitter
import utils

load_dotenv()

RPC: str = os.getenv("RPC", "")
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
USER_BOT_APP_HASH: str = os.getenv("USER_BOT_APP_HASH", "")
USER_BOT_APP_ID: str = os.getenv("USER_BOT_APP_ID", "")
USER_BOT_SESSION: str = os.getenv("USER_BOT_SESSION", "")
MAIN_GROUP_ID: int = int(os.getenv("MAIN_GROUP_ID", "0"))
WALLET_TRACK_BOT_NAME: str = os.getenv("WALLET_TRACK_BOT_NAME", "")
WALLET_TRACK_GROUP_ID: int = int(os.getenv("WALLET_TRACK_GROUP_ID", 0))
ALLOWED_USERS: List[int] = [int(user) for user in os.getenv("ALLOWED_USERS", "").split(",")]

HANDLE: str = "@xcryptoscrapper_bot"
TITLE: str = "🔰 XScrapper V1.0"
NAME: str = "XCryptoScrapperBot"
DESCRIPTION: str = "The ultimate bot for scrapping Pump.fun drops"
SCORER: scoring.Scrapper = scoring.Scrapper()
LOGGER: logging.Logger = logging.getLogger(__name__)

TARGET_CHANNELS: List[dict] = [
    {"id": -1002158735564, "name": "Qwerty", "link": "https://t.me/QwertysQuants"},
    {"id": -1002089676082, "name": "joji", "link": "https://t.me/jojiinnercircle"},
    {"id": -1002001411256, "name": "Borovik", "link": "https://t.me/borovikTG"},
    {"id": -1002047101414, "name": "Orangie", "link": "https://t.me/orangiealpha"},
]

COMMANDS: Dict[str, str] = {
    "run": "Start Twitter scrapper",
    "stop": "Stop Twitter scrapper",
    "runpools": "Start new Pump.fun Bonds scrapper",
    "stoppools": "Stop Pump.fun Bonds scrapper",
    "runticker": "Start Twitter Scrapper by a ticker and CA",
}

DISPATCHER: Dispatcher = Dispatcher()
DB: db.MongoDB = db.MongoDB()
BOT: Bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
USER_BOT_CLIENT: TelegramClient = TelegramClient(StringSession(USER_BOT_SESSION), USER_BOT_APP_ID, USER_BOT_APP_HASH)
NEW_POOLS: pools.NewPoolsScrapper = pools.NewPoolsScrapper(RPC, BOT)
TWITTER: twitter.TwitterScrapper = twitter.TwitterScrapper(BOT, DB, SCORER)


@DISPATCHER.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Handle messages with `/start` command."""
    if message.from_user is not None:
        inline_button = InlineKeyboardButton(
            text="Set me as admin",
            url=f"https://t.me/{NAME}?startgroup=start&amp;admin=can_invite_users",
            callback_data="add_admin",
        )
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[inline_button]])
        commands_string = "\n".join([f"/{command} - {description}" for command, description in COMMANDS.items()])
        payload = f"{TITLE}\n\n" f"{DESCRIPTION}\n\n" f"Commands:\n" f"{commands_string}\n\n"
        await message.answer(payload, reply_markup=inline_keyboard)


@DISPATCHER.message(Command("run"))
async def command_run_handler(message: Message) -> None:
    """Handle messages with `/run` command."""
    if message.chat.id != MAIN_GROUP_ID:
        await message.reply("This command is only available in the CALL CENTER.")
    if not message.chat.is_forum:
        await message.reply("This command is only available in groups with topics.")
        return

    chat_id = message.chat.id
    if not message.from_user:
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        await message.answer("The bot must be an admin to start the ticker scrapper.", show_alert=True)
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer("You must be an admin to start the scrapper.", show_alert=True)
        return

    topic_ids = {"100": 5, "10": 4, "0": 3, "scores": 37874}
    options = twitter.ScrapperOptions(
        queries=[twitter.PUMP_QUERY],
        topic_ids=topic_ids,
        type=twitter.ScrapperType.PUMP,
    )
    asyncio.create_task(TWITTER.start(chat_id, options=options))


@DISPATCHER.message(Command("runpools"))
async def command_run_pools_handler(message: Message) -> None:
    """Handle messages with `/runpools` command."""
    if message.chat.id != MAIN_GROUP_ID:
        await message.reply("This command is only available in the CALL CENTER.")

    if not message.chat.is_forum:
        await message.reply("This command is only available in groups with topics.")
        return

    if not message.from_user:
        return

    bot_member = await BOT.get_chat_member(message.chat.id, BOT.id)
    if not isinstance(bot_member, ChatMemberAdministrator):
        await message.answer("The bot must be an admin to start the ticker scrapper.", show_alert=True)
        return

    member = await BOT.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer("You must be an admin to start the scrapper.", show_alert=True)
        return

    asyncio.create_task(NEW_POOLS.start(message.chat.id))


@DISPATCHER.message(Command("runticker"))
async def command_run_ticker_handler(message: Message, command: CommandObject) -> None:
    """Handle messages with `/runticker` command."""
    if not utils.run_ticker_handler_validate(message, MAIN_GROUP_ID, BOT, ALLOWED_USERS):
        return

    err_msg = (
        "Please provide a Ticker and CA to start the scrapper.\n\n"
        "Example: /runticker $WSOL So11111111111111111111111111111111111111112"
    )

    input = command.args

    if not input:
        await message.answer(err_msg)
        return

    args = input.strip().split(" ")
    if len(args) != 2:
        await message.answer(err_msg)
        return

    ticker = args[0]
    if not re.match(r"^\$[A-Za-z]+$", ticker):
        await message.answer("Invalid Ticker. Please provide a valid ticker. Example: $WSOL")
        return

    mint = args[1]
    if not utils.is_valid_pubkey(mint):
        await message.answer(
            "Invalid CA. Please provide a valid CA. " "Example: So11111111111111111111111111111111111111112"
        )
        return

    queries = [ticker, mint]
    token_info = await utils.get_token_info(mint)
    if token_info:
        if ticker.replace("$", "") != token_info.symbol:
            await message.answer(
                "Invalid Ticker. The provided Ticker does not match the " f"Ticker of the token with CA {mint}"
            )
            return
        queries.append(f"https://pump.fun/{mint}")
        if token_info.raydium_pool:
            queries.append(f"https://dexscreener.com/solana/{str(token_info.raydium_pool)}")

    topic_ids = await utils.setup_ticker_scrapper(BOT, message.chat.id)
    options = twitter.ScrapperOptions(queries=queries, topic_ids=topic_ids, type=twitter.ScrapperType.TOKEN)
    asyncio.create_task(TWITTER.start(message.chat.id, options=options))


@DISPATCHER.message(Command("stoppools"))
async def command_stop_pools_handler(message: Message) -> None:
    """Handle messages with `/stoppools` command."""
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
        await message.answer("You must be an admin to stop the scrapper.", show_alert=True)
        return

    await NEW_POOLS.stop()


@DISPATCHER.message(Command("stop"))
async def command_stop_handler(message: Message) -> None:
    """Handle messages with `/stop` command."""
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
        await message.answer("You must be an admin to stop the scrapper.", show_alert=True)
        return

    chat_id = message.chat.id
    result = await TWITTER.stop(chat_id)
    if result and result.type == twitter.ScrapperType.TOKEN:
        await utils.clear_x_scrapper(BOT, chat_id, result.topic_ids)


@DISPATCHER.callback_query(F.data == "add_admin")
async def callback_add_admin_handler(query: CallbackQuery) -> None:
    """Handle callback queries with `add_admin` callback_data."""
    await query.answer("Adding as admin...")


@DISPATCHER.callback_query(F.data.startswith("block:"))
async def callback_block_handler(query: CallbackQuery) -> None:
    """Handle callback queries with `block:` callback_data."""
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
        await utils.delete_message(BOT, query.message.chat.id, drop.get("messageIds", []))
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
    """Handle callback queries with `report:` callback_data."""
    if query.message is None or query.data is None or query.message is None:
        return

    query_parts = query.data.split(":")
    if len(query_parts) != 3:
        LOGGER.error("Invalid query data format")
        return None
    _, username, user_id = query_parts

    await query.answer("Reporting is WIP...")


@USER_BOT_CLIENT.on(events.NewMessage(chats=WALLET_TRACK_BOT_NAME))
async def handler(event) -> None: # type: ignore
    if not event.out:
        text = event.message.message
        entities = event.message.entities
        if utils.has_solscan_url(entities):
            await USER_BOT_CLIENT.send_message(WALLET_TRACK_GROUP_ID, text, entities=entities)


@USER_BOT_CLIENT.on(events.NewMessage(chats=[ch["id"] for ch in TARGET_CHANNELS]))
async def handle_message(event: events.NewMessage) -> None:
    """Handle messages from the influencers."""
    message_text = event.message.message
    message_id = event.message.id
    channel = next((ch for ch in TARGET_CHANNELS if ch["id"] == event.chat_id), None)

    if not channel:
        return

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
                await USER_BOT_CLIENT.send_file(
                    MAIN_GROUP_ID,
                    media.photo,
                    caption=message_with_link,
                    reply_to=165503,
                    parse_mode="html",
                )
            elif isinstance(media, MessageMediaDocument):
                await USER_BOT_CLIENT.send_file(
                    MAIN_GROUP_ID,
                    media.document,
                    caption=message_with_link,
                    reply_to=165503,
                    parse_mode="html",
                )
            else:
                await USER_BOT_CLIENT.send_message(
                    MAIN_GROUP_ID,
                    message_with_link,
                    reply_to=165503,
                    parse_mode="html",
                    link_preview=False,
                )
        else:
            await USER_BOT_CLIENT.send_message(
                MAIN_GROUP_ID,
                message_with_link,
                reply_to=165503,
                parse_mode="html",
                link_preview=False,
            )


async def main() -> None:
    async with USER_BOT_CLIENT:
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
