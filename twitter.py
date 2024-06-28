import aiohttp
import asyncio
import time
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
from dataclasses import dataclass
from telethon import TelegramClient

load_dotenv()

INTERVAL = 2  # seconds
LOGGER = logging.getLogger(__name__)
SUPERGROUP_ID2 = int(getenv("SUPERGROUP_ID2", "0"))
SUPERGROUP_ID3 = int(getenv("SUPERGROUP_ID3", "0"))
RESEND_TO = [
    SUPERGROUP_ID2,
    SUPERGROUP_ID3,
]

URL = "https://twitter154.p.rapidapi.com/search/search"

QUERY_STRING = "'pump.fun' filter:links"

QUERY = {
    "query": QUERY_STRING,
    "section": "latest",
    "min_retweets": "0",
    "min_likes": "0",
    "limit": "20",
    "min_replies": "0",
    "start_date": time.strftime("%Y-%m-%d", time.gmtime(int(time.time()))),
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


@dataclass
class ScrapperTask:
    task: asyncio.Task
    options: Optional[utils.ScrapperOptions] = None


class TwitterScrapper:
    def __init__(self, bot: Bot, db: MongoDB, sc: Scrapper, cl: TelegramClient) -> None:
        self.bot = bot
        self.db = db
        self.sc = sc
        self.cl = cl
        self.tasks: dict[int, ScrapperTask] = {}
        self.lock = asyncio.Lock()

    async def start(
        self, chat_id: int, options: Optional[utils.ScrapperOptions] = None
    ) -> None:
        if chat_id in self.tasks:
            await self.bot.send_message(chat_id, "Scrapping is already running")
            return

        async with aiohttp.ClientSession() as session:
            task = asyncio.create_task(self._fetch_tweets(session, chat_id, options))
            self.tasks[chat_id] = ScrapperTask(task, options)
            try:
                start_msg = (
                    "Starting Twitter scrapper with query: " + options.query
                    if options
                    else "Starting Twitter scrapper..."
                )
                await self.bot.send_message(chat_id, start_msg)
                await task
            except asyncio.CancelledError:
                LOGGER.info(f"Cancelling Twitter Scrapper Task for chat_id {chat_id}")

    async def stop(self, chat_id: int) -> Optional[utils.ScrapperOptions]:
        task_options = self.tasks.get(chat_id)
        if task_options:
            await self.bot.send_message(chat_id, "Stopping Twitter scrapper...")
            task_options.task.cancel()
            try:
                await task_options.task
            except asyncio.CancelledError:
                LOGGER.info(f"Task for chat_id {chat_id} was successfully cancelled")
            finally:
                del self.tasks[chat_id]
            return task_options.options
        else:
            await self.bot.send_message(chat_id, "Twitter scrapper is not running")
            return None

    async def _fetch_tweets(
        self,
        session: aiohttp.ClientSession,
        chat_id: int,
        options: Optional[utils.ScrapperOptions] = None,
    ) -> None:
        global INTERVAL
        latest_timestamp = int(time.time() - 60 * 1)

        while True:
            try:
                data = await self._fetch_tweets_data(
                    session, query=options.query if options else None
                )

                if not data or not data.get("results"):
                    LOGGER.error("No results found.")
                    continue

                new_latest = data["results"][0]["timestamp"]

                tasks = []
                for tweet in data.get("results", []):
                    if tweet["timestamp"] <= latest_timestamp:
                        break

                    if not options:
                        tasks.append(self._process_tweet(tweet, chat_id))
                    else:
                        tasks.append(
                            self._process_send_ticker_tweet(tweet, chat_id, options)
                        )
                if tasks:
                    await asyncio.gather(*tasks)

                latest_timestamp = new_latest
            except Exception as e:
                LOGGER.error(f"An error occurred: {e}")

            LOGGER.info(
                f"Latest Timestamp: {latest_timestamp}. Sleeping..."
                + (" QUERY" if not options else " TICKER")
            )
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
            # Enter Critical Section
            async with self.lock:
                score = self.sc.calc_score(user_name)
            LOGGER.info(f"Score for {user_name}: {score}")
            await self.db.update_drop_score(user_id, score)

        LOGGER.info(f"New tweet found: {tweet_id} for query: {QUERY_STRING}")
        await self._send_tweet(tweet, score, chat_id, topic_id)

    async def _process_send_ticker_tweet(
        self, tweet: Dict, chat_id: int, options: utils.ScrapperOptions
    ) -> None:
        if len(options.topic_ids) != 3:
            LOGGER.error("Invalid topic_ids for ticker scrapper")

        user_name = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]
        follower_count = tweet["user"]["follower_count"]
        is_reply = tweet["in_reply_to_status_id"] is not None
        score = 0.0
        ticker_query = options.query

        sanitized_text = await utils.replace_short_urls(tweet["text"])
        if ticker_query.lower() not in sanitized_text.lower():
            return

        LOGGER.info(f"New Ticker tweet found: {tweet_id} for query: {ticker_query}")
        if follower_count > 1000:
            LOGGER.info(f"Calculating score for {user_name}, Ticker: {ticker_query}")
            # Enter Critical Section
            async with self.lock:
                score = self.sc.calc_score(user_name)
            LOGGER.info(f"Score for {user_name}: {score}, Ticker: {ticker_query}")

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
            ],
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        payload = (
            (
                f"<b>- NEW TWEET -</b>\n\n"
                if not is_reply
                else f"<b>- NEW REPLY -</b>\n\n"
            )
            + f"<blockquote>{await utils.replace_short_urls(tweet['text'])}</blockquote>\n\n"
            f"👤 @{user_name}\n"
            f"👨‍👩‍👦‍👦 <b>Followers:</b> {follower_count}\n"
            f"🪩 <b>Space Score:</b> {score}\n"
        )

        if not is_reply:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                keyboard=keyboard,
                topic_id=options.topic_ids[0],
            )
        else:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                keyboard=keyboard,
                topic_id=options.topic_ids[1],
            )
        if score > 0.0:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                keyboard=keyboard,
                topic_id=options.topic_ids[2],
            )

    async def _send_tweet(
        self,
        tweet: Dict,
        score: float,
        chat_id: int,
        topic_id: int,
    ) -> None:
        user_id = tweet["user"]["user_id"]
        username = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]

        sanitized_text = await utils.replace_short_urls(tweet["text"])
        pump_url = utils.extract_url_and_validate_mint_address(sanitized_text)
        mc = 0.0

        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text="📁 Tweet",
                    url=f"https://twitter.com/{username}/status/{tweet_id}",
                ),
                InlineKeyboardButton(
                    text="🐤 Profile",
                    url=f"https://x.com/{username}",
                ),
                InlineKeyboardButton(
                    text="🚫 Block",
                    callback_data=f"block:{username}:{user_id}",
                ),
            ],
        ]

        mc = 0.0
        if pump_url:
            mint = utils.extract_mint_from_url(pump_url)
            if mint:
                token_info = await utils.get_token_info(mint)
                if token_info:
                    keyboard_buttons.append(
                        [
                            InlineKeyboardButton(text="💊 Pump", url=pump_url),
                            InlineKeyboardButton(
                                text="🐃 BullX",
                                url=f"https://bullx.io/terminal?chainId=1399811149&address={mint}",
                            ),
                            InlineKeyboardButton(
                                text="🛸 Photon",
                                url=f"https://photon-sol.tinyastro.io/en/lp/{token_info.bonding_curve}",
                            ),
                        ]
                    )
                    mc = token_info.usd_market_cap

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        payload = (
            f"<b>- NEW TWEET -</b>\n\n"
            f"<blockquote>{await utils.replace_short_urls(tweet['text'])}</blockquote>\n\n"
            f"👤 @{username}\n"
            f"👨‍👩‍👦‍👦 <b>Followers:</b> {tweet['user']['follower_count']}\n"
            f"🪩 <b>Space Score:</b> {score}\n"
            + (f"🏛 <b>Market Cap:</b> ${'{:,.2f}'.format(mc)}\n" if mc > 0.0 else "")
            + (f"☎️ <b>CA:</b> <code>{mint}</code>" if pump_url else "")
        )

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
        self, session: aiohttp.ClientSession, query: Optional[str] = None
    ) -> Optional[Dict]:
        LOGGER.info("Fetching data...")
        try:
            params = QUERY.copy()
            if query:
                params["query"] = query

            async with session.get(URL, headers=HEADERS, params=params) as response:
                data = await response.json()
                return data
        except Exception as e:
            LOGGER.error(f"Error fetching data: {e}")
            return None
