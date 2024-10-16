import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    ChatMemberAdministrator,
    ForceReply,
    InlineKeyboardMarkup,
    InputFile,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from solders.pubkey import Pubkey  # type: ignore
from telethon import TelegramClient  # type: ignore

LOGGER: logging.Logger = logging.getLogger(__name__)
ASSOCIATED_TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


def is_valid_pubkey(pubkey: str) -> bool:
    try:
        Pubkey.from_string(pubkey)
        return True
    except Exception:
        return False


def extract_mint_from_url(url: str) -> Optional[str]:
    mint_address = url.split("/")[-1]

    if not is_valid_pubkey(mint_address):
        return None
    return mint_address


def extract_url_and_validate_mint_address(text: str) -> Optional[str]:
    url_pattern = re.compile(r"https:\/\/(www\.)?pump\.fun\/[A-Za-z0-9]+")
    match = url_pattern.search(text)

    if not match:
        return None

    url = match.group(0)
    mint_address = url.split("/")[-1]

    if not is_valid_pubkey(mint_address):
        return None
    return url


def is_root_domain(url: str) -> bool:
    root_domain_regex = re.compile(r"^https:\/\/[^\/]+\/?$")
    return bool(root_domain_regex.match(url))


async def expand_url(short_url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(short_url, allow_redirects=True) as response:
                return str(response.url)
    except aiohttp.ClientError as e:
        LOGGER.error(f"Error expanding URL: {e}")
        return short_url


async def replace_short_urls(text: str) -> str:
    url_regex = re.compile(r"(https?://t\.co/\S+?)([\.,!?]*)(?:\s|$)")

    matches = url_regex.findall(text)
    tasks = [expand_url(url) for url, _ in matches]
    expanded_urls = await asyncio.gather(*tasks)

    for (short_url, punctuation), expanded_url in zip(matches, expanded_urls):
        text = text.replace(short_url, expanded_url + punctuation)

    return text


async def delete_message(bot: Bot, chat_id: int, messages: list[int]) -> bool:
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        try:
            await bot.delete_messages(chat_id, messages)
            return True
        except Exception as e:
            LOGGER.error(f"Error deleting message: {e}")
            attempts += 1

    return False


async def send_message(
    bot: Bot,
    chat_id: int,
    payload: str,
    topic_id: Optional[int] = None,
    post_url: Optional[str] = None,
    keyboard: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]] = None,
    parse_mode: ParseMode = ParseMode.HTML,
) -> Optional[Message]:
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic_id,
                text=payload,
                parse_mode=parse_mode,
                reply_markup=keyboard,
                link_preview_options=((LinkPreviewOptions(url=post_url)) if post_url else None),
                disable_web_page_preview=not bool(post_url),
            )
            return msg
        except TelegramAPIError as e:
            LOGGER.error(f"Failed to send message: {e}")
            attempts += 1
            await asyncio.sleep(1)
    return None


async def send_photo(
    bot: Bot,
    chat_id: int,
    photo: Union[InputFile, str],
    caption: str,
    topic_id: Optional[int] = None,
    keyboard: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]] = None,
    parse_mode: ParseMode = ParseMode.HTML,
) -> Optional[Message]:
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        try:
            msg = await bot.send_photo(
                chat_id=chat_id,
                message_thread_id=topic_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=keyboard,
            )
            return msg
        except TelegramAPIError as e:
            LOGGER.error(f"Failed to send photo: {e}")
            attempts += 1
            await asyncio.sleep(1)
    return None


@dataclass
class TokenInfo:
    dev: Pubkey
    created_timestamp: str
    usd_market_cap: float
    bonding_curve: Pubkey
    symbol: str
    raydium_pool: Optional[Pubkey] = None


async def get_token_info(mint: str) -> Optional[TokenInfo]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://frontend-api.pump.fun/coins/{mint}") as response:
                data = await response.json()
                if (
                    data
                    and "creator" in data
                    and "created_timestamp" in data
                    and "usd_market_cap" in data
                    and "bonding_curve" in data
                    and "symbol" in data
                    and "raydium_pool" in data
                ):
                    dev_pubkey = Pubkey.from_string(data["creator"])
                    created_timestamp = data["created_timestamp"]
                    usd_market_cap = data["usd_market_cap"]
                    bonding_curve = Pubkey.from_string(data["bonding_curve"])
                    raydium_pool = None if not data["raydium_pool"] else Pubkey.from_string(data["raydium_pool"])
                    symbol = data["symbol"]
                    return TokenInfo(
                        dev_pubkey,
                        created_timestamp,
                        usd_market_cap,
                        bonding_curve,
                        symbol,
                        raydium_pool,
                    )
    except Exception as e:
        LOGGER.error(f"Error fetching token info: {e}")
        return None
    return None


def calculate_timespan(timestamp: int) -> str:
    timestamp_seconds = timestamp / 1000.0

    current_time_seconds = datetime.now().timestamp()

    time_difference_seconds = current_time_seconds - timestamp_seconds

    if time_difference_seconds >= 86400:
        time_difference_days = time_difference_seconds / 86400
        return f"{int(time_difference_days)} days" if time_difference_days > 1 else "1 day"
    elif time_difference_seconds >= 3600:
        time_difference_hours = time_difference_seconds / 3600
        return f"{int(time_difference_hours)} hours" if time_difference_hours > 1 else "1 hour"
    else:
        time_difference_minutes = time_difference_seconds / 60
        return f"{int(time_difference_minutes)} minutes" if time_difference_minutes > 1 else "1 minute"


def get_token_wallet(owner: Pubkey, mint: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )[0]


async def setup_ticker_scrapper(bot: Bot, chat_id: int) -> Dict[str, int]:
    tweets_topic = await bot.create_forum_topic(chat_id, "TWEETS", icon_color=7322096)
    replies_topic = await bot.create_forum_topic(chat_id, "REPLIES", icon_color=16766590)
    scores_topic = await bot.create_forum_topic(chat_id, "WIF SCORE", icon_color=13338331)

    return {
        "tweets": tweets_topic.message_thread_id,
        "replies": replies_topic.message_thread_id,
        "scores": scores_topic.message_thread_id,
    }


async def clear_x_scrapper(bot: Bot, chat_id: int, topic_ids: Dict[str, int]) -> None:
    for topic_id in topic_ids.values():
        await bot.delete_forum_topic(chat_id, topic_id)


async def run_ticker_handler_validate(message: Message, group_id: int, bot: Bot, allowed_users: List[int]) -> bool:
    if not message.from_user:
        return False

    if message.chat.id == group_id:
        await message.reply("This command is only available outside of the CALL CENTER.")
        return False

    if not message.chat.is_forum:
        await message.reply("This command is only available in groups with topics.")
        return False

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        await message.answer("You must be an admin to start the ticker scrapper.", show_alert=True)
        return False

    bot_member = await bot.get_chat_member(message.chat.id, bot.id)
    if isinstance(bot_member, ChatMemberAdministrator):
        if not bot_member.can_manage_topics:
            await message.answer(
                "The bot must have permission to manage topics to start the ticker scrapper.",
            )
            return False
    else:
        await message.answer("The bot must be an admin to start the ticker scrapper.", show_alert=True)
        return False

    if member.user.id not in allowed_users:
        await message.answer("You are not allowed to start the ticker scrapper.", show_alert=True)
        return False

    return True


def has_solscan_url(entities: List[Any] | None) -> bool:
    if entities is None:
        return False

    for entity in entities:
        if hasattr(entity, 'url') and 'solscan' in entity.url:
            return True

    return False
