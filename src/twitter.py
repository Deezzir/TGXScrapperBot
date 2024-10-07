import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from os import getenv
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

import utils
from db import MongoDB
from scoring import Scrapper

load_dotenv()

INTERVAL: int = 3  # seconds
LOGGER: logging.Logger = logging.getLogger(__name__)
RESEND_TO: List[int] = [int(user) for user in getenv("RESEND_GROUP_IDS", "").split(",")]

URL: str = "https://twitter154.p.rapidapi.com/search/search"

PUMP_QUERY: str = "'pump.fun' filter:links"

FETCH_PARAMS: Dict[str, Any] = {
    "query": "scrapper",
    "section": "latest",
    "min_retweets": "0",
    "min_likes": "0",
    "limit": "20",
    "min_replies": "0",
    "start_date": time.strftime("%Y-%m-%d", time.gmtime(int(time.time()))),
    "language": "en",
}

HEADERS_MAIN: Dict[str, str] = {
    "X-RapidAPI-Key": getenv("RAPIDAPI_KEY1", ""),
    "X-RapidAPI-Host": "twitter154.p.rapidapi.com",
}

HEADERS_SECONDARY: Dict[str, str] = {
    "X-RapidAPI-Key": getenv("RAPIDAPI_KEY2", ""),
    "X-RapidAPI-Host": "twitter154.p.rapidapi.com",
}


def determine_topic_id(follower_count: int, topic_ids: Dict[str, int]) -> int:
    if follower_count > 100_000:
        topic_id = topic_ids["100"]
    elif follower_count > 10_000:
        topic_id = topic_ids["10"]
    else:
        topic_id = topic_ids["0"]
    return topic_id


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


class ScrapperType(Enum):
    PUMP = "PUMP"
    TOKEN = "TICKER"


@dataclass
class ScrapperOptions:
    queries: List[str]
    type: ScrapperType
    topic_ids: Dict[str, int]


@dataclass
class ScrapperTask:
    task: asyncio.Task
    options: ScrapperOptions


class TwitterScrapper:
    def __init__(self, bot: Bot, db: MongoDB, sc: Scrapper) -> None:
        """Initialize Twitter Scrapper."""
        self.bot = bot
        self.db = db
        self.sc = sc
        self.tasks: dict[int, ScrapperTask] = {}
        self.lock = asyncio.Lock()

    async def start(self, chat_id: int, options: ScrapperOptions) -> None:
        if chat_id in self.tasks:
            await self.bot.send_message(chat_id, "Scrapping is already running")
            return

        if len(options.queries) == 0:
            await self.bot.send_message(chat_id, "Something went wrong. Please try again.")
            return

        async with aiohttp.ClientSession() as session:
            task = asyncio.create_task(self._process_tweets(session, chat_id, options))
            self.tasks[chat_id] = ScrapperTask(task, options)
            try:
                start_msg = "Starting Twitter scrapper"
                await self.bot.send_message(chat_id, start_msg)
                await task
            except asyncio.CancelledError:
                LOGGER.info(f"Cancelling Twitter Scrapper Task for chat_id {chat_id}")

    async def stop(self, chat_id: int) -> Optional[ScrapperOptions]:
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
        process_func: Callable[[Dict, int, str, Dict[str, int]], Awaitable[None]],
        query: str,
        chat_id: int,
        topic_ids: Dict[str, int],
        is_secondary: bool = False,
    ) -> None:
        global INTERVAL
        latest_timestamp = int(time.time() - 60 * 1)

        while True:
            try:
                data = await self._fetch_tweets_data(session, query, is_secondary=is_secondary)

                if not data or not data.get("results"):
                    LOGGER.error("No results found.")
                    continue

                new_latest = data["results"][0]["timestamp"]

                tasks = []
                for tweet in data.get("results", []):
                    if tweet["timestamp"] <= latest_timestamp:
                        break
                    tasks.append(process_func(tweet, chat_id, query, topic_ids))

                if tasks:
                    await asyncio.gather(*tasks)

                latest_timestamp = new_latest
            except Exception as e:
                LOGGER.error(f"An error occurred: {e}")

            LOGGER.info(f"Latest Timestamp: {latest_timestamp}. Query: '{query}' Sleeping...")
            await asyncio.sleep(INTERVAL)

    async def _process_tweets(self, session: aiohttp.ClientSession, chat_id: int, options: ScrapperOptions) -> None:
        process_func: Optional[Callable[[Dict, int, str, Dict[str, int]], Awaitable[None]]] = None
        is_secondary = False
        if options.type == ScrapperType.PUMP:
            if {"100", "10", "0", "scores"} > options.topic_ids.keys():
                LOGGER.error("Invalid topic_ids for pump scrapper")
                return
            process_func = self._process_send_pump_tweet
        elif options.type == ScrapperType.TOKEN:
            if {"tweets", "replies", "scores"} > options.topic_ids.keys():
                LOGGER.error("Invalid topic_ids for ticker scrapper")
                return
            process_func = self._process_send_ticker_tweet
            is_secondary = True

        generated_query = self._generate_query(options.queries)
        await self._fetch_tweets(
            session,
            process_func,
            generated_query,
            chat_id,
            options.topic_ids,
            is_secondary,
        )

    async def _process_send_pump_tweet(self, tweet: Dict, chat_id: int, query: str, topic_ids: Dict[str, int]) -> None:
        if len(topic_ids) != 4:
            LOGGER.error("Invalid topic_ids for pump scrapper")
            return

        user_id = tweet["user"]["user_id"]
        user_name = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]
        follower_count = tweet["user"]["follower_count"]

        drop = await self.db.get_drop(user_id)

        if drop:
            if tweet_id not in drop.get("postIds", []):
                await self.db.update_drop_posts(user_id, tweet_id)
            else:
                LOGGER.info(f"Tweet already exists: {tweet_id}")
                return
        else:
            await self.db.insert_drop(user_id, user_name, tweet_id)

        if await self.db.check_banned(user_id):
            LOGGER.info(f"User {user_name} is banned")
            return

        score = 0.0
        if follower_count > 1000:
            LOGGER.info(f"Calculating score for {user_name}. Query: {query}")
            # Enter Critical Section
            async with self.lock:
                score = self.sc.calc_score(user_name)
            LOGGER.info(f"Score for {user_name}: {score}")
            await self.db.update_drop_score(user_id, score)

        LOGGER.info(f"New Tweet found: {tweet_id}. Query: {query}")
        await self._send_pump_tweet(
            tweet,
            chat_id,
            score,
            topic_ids,
        )

    async def _process_send_ticker_tweet(
        self, tweet: Dict, chat_id: int, query: str, topic_ids: Dict[str, int]
    ) -> None:
        if len(topic_ids) != 3:
            LOGGER.error("Invalid topic_ids for ticker scrapper")

        user_name = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]
        tweet_url = f"https://twitter.com/{user_name}/status/{tweet_id}"
        follower_count = tweet["user"]["follower_count"]
        is_reply = tweet["in_reply_to_status_id"] is not None
        sanitized_text = await utils.replace_short_urls(tweet["text"])
        score = 0.0

        LOGGER.info(f"New Tweet found: {tweet_id}. Query: {query}")

        if follower_count > 1000:
            LOGGER.info(f"Calculating score for {user_name}. Query: {query}")
            # Enter Critical Section
            async with self.lock:
                score = self.sc.calc_score(user_name)
            LOGGER.info(f"Score for {user_name}: {score}. Query: {query}")

        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text="📁 Tweet",
                    url=tweet_url,
                ),
                InlineKeyboardButton(
                    text="🐤 Profile",
                    url=f"https://x.com/{user_name}",
                ),
            ],
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        payload = (
            ("<b>- NEW TWEET -</b>\n\n" if not is_reply else "<b>- NEW REPLY -</b>\n\n")
            + f"<blockquote>{sanitized_text}</blockquote>\n\n"
            f"👤 @{user_name}\n"
            f"👨‍👩‍👦‍👦 <b>Followers:</b> {follower_count}\n"
            f"🪩 <b>Space Score:</b> {score}\n\n"
            f"<code>/raid {tweet_url}</code>"
        )

        if not is_reply:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                keyboard=keyboard,
                topic_id=topic_ids["tweets"],
            )
        else:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                keyboard=keyboard,
                topic_id=topic_ids["replies"],
            )
        if score > 0.0:
            await utils.send_message(
                self.bot,
                chat_id,
                payload,
                keyboard=keyboard,
                topic_id=topic_ids["scores"],
            )

    async def _send_pump_tweet(
        self,
        tweet: Dict,
        chat_id: int,
        score: float,
        topic_ids: Dict[str, int],
    ) -> None:
        user_id = tweet["user"]["user_id"]
        user_name = tweet["user"]["username"]
        tweet_id = tweet["tweet_id"]

        topic_id = determine_topic_id(tweet["user"]["follower_count"], topic_ids)

        sanitized_text = await utils.replace_short_urls(tweet["text"])
        pump_url = utils.extract_url_and_validate_mint_address(sanitized_text)
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
            f"👤 @{user_name}\n"
            f"👨‍👩‍👦‍👦 <b>Followers:</b> {tweet['user']['follower_count']}\n"
            f"🪩 <b>Space Score:</b> {score}\n"
            + (f"🏛 <b>Market Cap:</b> ${'{:,.2f}'.format(mc)}\n" if mc > 0.0 else "")
            + (f"☎️ <b>CA:</b> <code>{mint}</code>" if pump_url else "")
        )

        msg = await utils.send_message(self.bot, chat_id, payload, topic_id, None, keyboard)
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

        resend_keyboard_buttons = keyboard_buttons.copy()
        del resend_keyboard_buttons[0][-1]

        for _ in range(resend_number):
            msg = await utils.send_message(self.bot, chat_id, payload, post_url=None, keyboard=keyboard)
            for resend_chat in RESEND_TO:
                await utils.send_message(
                    self.bot,
                    resend_chat,
                    payload,
                    post_url=None,
                    keyboard=InlineKeyboardMarkup(inline_keyboard=resend_keyboard_buttons),
                )
            if msg:
                await self.db.update_drop_messages(tweet["user"]["user_id"], msg.message_id)
            await asyncio.sleep(1)

    # async def _get_mentions_payload(self, chat_id: int) -> str:
    #     LOGGER.info(f"Getting mentions for chat_id {chat_id}")
    #     notifies = []
    #     async for user in self.cl.iter_participants(chat_id):
    #         notifies.append(
    #             '<a href="tg://user?id=' + str(user.id) + '">\u206c\u206f</a>'
    #         )
    #     return "\u206c\u206f".join(notifies)

    async def _fetch_tweets_data(
        self, session: aiohttp.ClientSession, query: str, is_secondary: bool = False
    ) -> Optional[Dict]:
        LOGGER.info(f"Fetching data. Query: '{query}'")
        try:
            params = FETCH_PARAMS.copy()
            params["query"] = query

            async with session.get(
                URL,
                headers=HEADERS_SECONDARY if is_secondary else HEADERS_MAIN,
                params=params,
            ) as response:
                data = await response.json()
                return data
        except Exception as e:
            LOGGER.error(f"Error fetching data: {e}")
            return None

    def _generate_query(self, queries: List[str]) -> str:
        if len(queries) == 1:
            return queries[0]
        return f"({' OR '.join(queries)})"
