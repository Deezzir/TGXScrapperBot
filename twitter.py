import aiohttp
import asyncio
import time
import requests
import re
import logging
import utils
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.methods import SendMessage
from aiogram import Bot
from aiogram.types import LinkPreviewOptions
from aiogram.exceptions import TelegramAPIError
from os import getenv
from dotenv import load_dotenv
from scoring import Scrapper
from typing import Dict, Optional
from db import MongoDB
from telethon import TelegramClient

load_dotenv()

INTERVAL = 4  # seconds
LATEST = int(time.time() - 60 * 1)
START_DATE = time.strftime("%Y-%m-%d", time.gmtime(LATEST))
LOGGER = logging.getLogger(__name__)
SUPERGROUP_ID2 = int(getenv("SUPERGROUP_ID2", "0"))
SUPERGROUP_ID3 = int(getenv("SUPERGROUP_ID3", "0"))
RESEND_TO = [
    SUPERGROUP_ID2,
    SUPERGROUP_ID3,
]

URL = "https://twitter154.p.rapidapi.com/search/search"

QUERY = {
    "query": "'pump.fun' filter:links",
    "section": "latest",
    "min_retweets": "0",
    "min_likes": "0",
    "limit": "20",
    "min_replies": "0",
    "start_date": START_DATE,
    "language": "en",
}

HEADERS = {
    "X-RapidAPI-Key": getenv("RAPIDAPI_KEY", ""),
    "X-RapidAPI-Host": "twitter154.p.rapidapi.com",
}


def determine_topic_id(follower_count: int) -> tuple[int, bool]:
    # if follower_count > 1_000_000:
    #     topic_id = 6
    if follower_count > 100_000:
        topic_id = 5
    elif follower_count > 10_000:
        topic_id = 4
    else:
        topic_id = 3

    return topic_id, follower_count > 1000


def determine_resend_number(score: float) -> int:
    if score >= 12.0:
        return 4
    elif score >= 9.0:
        return 3
    elif score >= 6.0:
        return 2
    elif score >= 3.0:
        return 1
    else:
        return 0


class TwitterScrapper:
    def __init__(self, bot: Bot, db: MongoDB, sc: Scrapper, cl: TelegramClient) -> None:
        self.bot = bot
        self.db = db
        self.sc = sc
        self.cl = cl
        self.tasks: dict[int, asyncio.Task] = {}

    async def start(self, chat_id: int) -> None:
        if chat_id in self.tasks:
            await self.bot.send_message(chat_id, "Scrapping is already running")
            return

        async with aiohttp.ClientSession() as session:
            task = asyncio.create_task(self._fetch_tweets(session, chat_id))
            self.tasks[chat_id] = task
            try:
                await self.bot.send_message(chat_id, "Starting Twitter scrapper...")
                await task
            except asyncio.CancelledError:
                LOGGER.info(f"Cancelling Twitter Scrapper Task for chat_id {chat_id}")

    async def stop(self, chat_id: int) -> None:
        task = self.tasks.get(chat_id)
        if task:
            await self.bot.send_message(chat_id, "Stopping Twitter scrapper...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                LOGGER.info(f"Task for chat_id {chat_id} was successfully cancelled")
            finally:
                del self.tasks[chat_id]
        else:
            await self.bot.send_message(chat_id, "Twitter scrapper is not running")

    async def _fetch_tweets(self, session: aiohttp.ClientSession, chat_id: int) -> None:
        global LATEST
        global INTERVAL

        while True:
            try:
                data = await self._fetch_tweets_data(session)

                if not data or not data.get("results"):
                    LOGGER.error("No results found.")
                    continue

                new_latest = data["results"][0]["timestamp"]

                for tweet in data.get("results", []):
                    if tweet["timestamp"] <= LATEST:
                        break

                    await self._process_tweet(tweet, chat_id)

                LATEST = new_latest

            except Exception as e:
                LOGGER.error(f"An error occurred: {e}")

            LOGGER.info(f"Latest Timestamp: {LATEST}. Sleeping...")
            await asyncio.sleep(INTERVAL)

    async def _process_tweet(self, tweet: Dict, chat_id: int) -> None:
        user_id = tweet["user"]["user_id"]
        user_name = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]

        if await self.db.check_banned(user_id):
            LOGGER.info(f"User {user_name} is banned")
            return

        drop = await self.db.get_drop(user_id)

        if drop:
            if tweet_id not in drop.get("postIds", []):
                await self.db.update_drop_posts(user_id, tweet_id)
            else:
                LOGGER.info(f"Tweet already exists: {tweet_id}")
                return
        else:
            await self.db.insert_drop(user_id, user_name, tweet_id)

        topic_id, to_score = determine_topic_id(tweet["user"]["follower_count"])
        score = 0.0
        if to_score:
            LOGGER.info(f"Calculating score for {user_name}")
            score = self.sc.calc_score(user_name)
            LOGGER.info(f"Score for {user_name}: {score}")
            await self.db.update_drop_score(user_id, score)

        LOGGER.info(f"New tweet found: {tweet_id}")
        await self._send_tweet(tweet, score, chat_id, topic_id)
        await asyncio.sleep(1)

    async def _send_tweet(
        self,
        tweet: Dict,
        score: float,
        chat_id: int,
        topic_id: int,
    ) -> None:
        user_id = tweet["user"]["user_id"]
        user_name = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]

        sanitazed_text = await utils.replace_short_urls(tweet["text"])
        pump_url = utils.extract_url_and_validate_mint_address(sanitazed_text)
        post_url = f"https://twitter.com/{user_name}/status/{tweet_id}"
        mc = 0.0

        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text="📁 Tweet",
                    url=f"https://twitter.com/{user_name}/status/{tweet_id}",
                ),
                InlineKeyboardButton(
                    text="🐤 Profile",
                    url=f"https://x.com/{user_name}",
                ),
                InlineKeyboardButton(
                    text="🚫 Block",
                    callback_data=f"block:{user_name}:{user_id}",
                ),
            ],
        ]

        mc = 0.0
        if pump_url:
            keyboard_buttons.append(
                [InlineKeyboardButton(text="💊 Pump", url=pump_url)]
            )
            mint = utils.extract_mint_from_url(pump_url)
            if mint:
                token_info = await utils.get_token_info(mint)
                if token_info:
                    mc = token_info.usd_market_cap

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        payload = (
            f"<b>- NEW TWEET -</b>\n\n"
            f"<blockquote>{await utils.replace_short_urls(tweet['text'])}</blockquote>\n\n"
            f"👨‍👩‍👦‍👦 <b>Followers:</b> {tweet['user']['follower_count']}\n"
            f"🪩 <b>Space Score:</b> {score}\n"
            + (f"🏛 <b>Market Cap:</b> ${'{:,.2f}'.format(mc)}\n" if mc > 0.0 else "")
            + (f"☎️ <b>CA:</b> <code>{mint}</code>" if pump_url else "")
        )

        attempts = 0
        max_attempts = 3

        msg = await utils.send_message(
            self.bot, chat_id, payload, topic_id, None, keyboard
        )
        if msg:
            await self.db.update_drop_messages(tweet["user"]["user_id"], msg.message_id)

        resend_number = determine_resend_number(score)

        if score > 0.0:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                topic_id=37874,
                post_url=None,
                keyboard=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
            )

        if resend_number == 0 or not pump_url:
            return

        attempts = 0
        mentions = await self._get_mentions_payload(chat_id)
        payload = mentions + payload
        resend_keyboard_buttons = keyboard_buttons.copy()
        del resend_keyboard_buttons[0][-1]

        for _ in range(resend_number):
            msg = await utils.send_message(
                self.bot, chat_id, payload, post_url=None, keyboard=keyboard
            )
            for resend_chat in RESEND_TO:
                await utils.send_message(
                    self.bot,
                    resend_chat,
                    payload,
                    post_url=None,
                    keyboard=InlineKeyboardMarkup(
                        inline_keyboard=resend_keyboard_buttons
                    ),
                )
            if msg:
                await self.db.update_drop_messages(
                    tweet["user"]["user_id"], msg.message_id
                )
            await asyncio.sleep(1)

    async def _get_mentions_payload(self, chat_id: int) -> str:
        LOGGER.info(f"Getting mentions for chat_id {chat_id}")
        notifies = []
        async for user in self.cl.iter_participants(chat_id):
            notifies.append(
                '<a href="tg://user?id=' + str(user.id) + '">\u206c\u206f</a>'
            )
        return "\u206c\u206f".join(notifies)

    async def _fetch_tweets_data(
        self, session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        LOGGER.info("Fetching data...")
        try:
            async with session.get(URL, headers=HEADERS, params=QUERY) as response:
                data = await response.json()
                return data
        except Exception as e:
            LOGGER.error(f"Error fetching data: {e}")
            return None
