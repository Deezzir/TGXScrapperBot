import asyncio
import json
import logging
import sys
from os import getenv
from typing import Optional

from bson import json_util
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

load_dotenv()
LOGGER: logging.Logger = logging.getLogger(__name__)


class MongoDB:
    def __init__(self):
        """Initialize MongoDB client."""
        self.MONGO_URI = getenv("MONGO_URI", "")
        self.COLLECTION_NAME = getenv("COLLECTION_NAME", "twitter")
        self.client = None
        self.db = None
        self.BANNED_COLLECTION = None
        self.DROPS_COLLECTION = None

    async def initialize(self) -> None:
        LOGGER.info("Connecting to MongoDB...")
        self.client = AsyncIOMotorClient(self.MONGO_URI, server_api=ServerApi("1"))
        self.db = self.client[self.COLLECTION_NAME]
        self.BANNED_COLLECTION = self.db["banned"]
        self.DROPS_COLLECTION = self.db["drops"]

        await self.check_db()

    async def check_db(self) -> None:
        try:
            await self.client.admin.command("ping")
            LOGGER.info("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            LOGGER.error(e)
            sys.exit(1)

    async def insert_banned(self, x_user_id: str) -> None:
        existing = await self.BANNED_COLLECTION.find_one({"xUserId": x_user_id})
        if existing:
            return
        banned = {"xUserId": x_user_id}
        await self.BANNED_COLLECTION.insert_one(banned)

    async def insert_drop(self, x_user_id: str, x_username: str, post_id: Optional[str] = None) -> None:
        scores = {
            "xUserId": x_user_id,
            "xUsername": x_username,
            "score": 0.0,
            "postIds": [post_id] if post_id else [],
            "messageIds": [],
        }
        await self.DROPS_COLLECTION.insert_one(scores)

    async def update_drop_score(self, x_user_id: str, score: float) -> None:
        await self.DROPS_COLLECTION.update_one({"xUserId": x_user_id}, {"$set": {"score": score}}, upsert=True)

    async def update_drop_posts(self, x_user_id: str, post_id: str) -> None:
        await self.DROPS_COLLECTION.update_one({"xUserId": x_user_id}, {"$push": {"postIds": post_id}}, upsert=True)

    async def update_drop_messages(self, x_user_id: str, message_id: int) -> None:
        await self.DROPS_COLLECTION.update_one(
            {"xUserId": x_user_id}, {"$push": {"messageIds": message_id}}, upsert=True
        )

    async def get_drop(self, x_user_id: str) -> dict:
        return await self.DROPS_COLLECTION.find_one({"xUserId": x_user_id})

    async def delete_drop(self, x_user_id: str) -> None:
        await self.DROPS_COLLECTION.delete_one({"xUserId": x_user_id})

    async def check_drop(self, x_user_id: str) -> bool:
        return await self.DROPS_COLLECTION.find_one({"xUserId": x_user_id}) is not None

    async def check_banned(self, x_user_id: str) -> bool:
        return await self.BANNED_COLLECTION.find_one({"xUserId": x_user_id}) is not None

    async def get_drops(self, condition: Optional[dict], projection: Optional[dict]) -> list[dict]:
        drops = self.DROPS_COLLECTION.find(condition, projection)
        return [drop async for drop in drops]


async def test() -> None:
    db = MongoDB()
    await db.initialize()

    drops = await db.get_drops(
        {"score": {"$gt": 0.0}},
        {
            "_id": 0,
            "messageIds": 0,
            "xUserId": 0,
        },
    )
    with open("output.json", "w") as f:
        drops_json = json.dumps(drops, indent=4, default=json_util.default)
        f.write(drops_json)


if __name__ == "__main__":
    asyncio.run(test())
