import re
from solders.pubkey import Pubkey
import aiohttp
import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    Message,
    LinkPreviewOptions,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ForceReply,
    InputFile,
)
from typing import Optional, Union
import logging

LOGGER = logging.getLogger(__name__)


def extract_mint_from_url(url: str) -> Optional[str]:
    mint_address = url.split("/")[-1]

    try:
        Pubkey.from_string(mint_address)
        return mint_address
    except Exception as e:
        return None


def extract_url_and_validate_mint_address(text: str) -> Optional[str]:
    url_pattern = re.compile(r"https:\/\/(www\.)?pump\.fun\/[A-Za-z0-9]+")
    match = url_pattern.search(text)

    if not match:
        return None

    url = match.group(0)
    mint_address = url.split("/")[-1]

    try:
        Pubkey.from_string(mint_address)
        return url
    except Exception as e:
        return None


def is_root_domain(url: str):
    ROOT_DOMAIN_PATTERN = re.compile(r"^https:\/\/[^\/]+\/?$")
    return bool(ROOT_DOMAIN_PATTERN.match(url))


async def expand_url(short_url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(short_url, allow_redirects=True) as response:
                return str(response.url)
    except aiohttp.ClientError as e:
        LOGGER.error(f"Error expanding URL: {e}")
        return short_url


async def replace_short_urls(text: str) -> str:
    URL_PATTERN = re.compile(r"(https?://t\.co/\S+?)([\.,!?]*)(?:\s|$)")

    matches = URL_PATTERN.findall(text)
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
    keyboard: Optional[
        Union[
            InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply
        ]
    ] = None,
    parse_mode: str = "HTML",
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
                link_preview_options=(LinkPreviewOptions(url=post_url)),
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
    keyboard: Optional[
        Union[
            InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply
        ]
    ] = None,
    parse_mode: str = "HTML",
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


async def get_token_info(url: str) -> float:
    mint = extract_mint_from_url(url)
    if not mint:
        return 0.0

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://frontend-api.pump.fun/coins/{mint}"
        ) as response:
            data = await response.json()
            usd_market_cap = float(data["usd_market_cap"])
            if usd_market_cap > 0:
                return usd_market_cap
    return 0.0
