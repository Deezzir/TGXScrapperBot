import sys
import asyncio
from os import getenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import json
from bson import json_util
import logging
from typing import Optional

load_dotenv()
LOGGER = logging.getLogger(__name__)


class MongoDB:
    def __init__(self):
        self.MONGO_URI = getenv("MONGO_URI", "")
        self.COLLECTION_NAME = getenv("COLLECTION_NAME", "twitter")
        self.client = None
        self.db = None
        self.BANNED_COLLECTION = None
        self.DROPS_COLLECTION = None

    async def initialize(self):
        LOGGER.info("Connecting to MongoDB...")
        self.client = AsyncIOMotorClient(self.MONGO_URI, server_api=ServerApi("1"))
        self.db = self.client[self.COLLECTION_NAME]
        self.BANNED_COLLECTION = self.db["banned"]
        self.DROPS_COLLECTION = self.db["drops"]

        await self.check_db()

    async def check_db(self) -> None:
        try:
            await self.client.admin.command("ping")
            LOGGER.info(
                "Pinged your deployment. You successfully connected to MongoDB!"
            )
        except Exception as e:
            LOGGER.error(e)
            sys.exit(1)

    async def insert_banned(self, xUserId: str) -> None:
        existing = await self.BANNED_COLLECTION.find_one({"xUserId": xUserId})
        if existing:
            return
        banned = {"xUserId": xUserId}
        await self.BANNED_COLLECTION.insert_one(banned)

    async def insert_drop(
        self, xUserId: str, xUsername: str, postId: Optional[str] = None
    ) -> None:
        scores = {
            "xUserId": xUserId,
            "xUsername": xUsername,
            "score": 0.0,
            "postIds": [postId] if postId else [],
            "messageIds": [],
        }
        await self.DROPS_COLLECTION.insert_one(scores)

    async def update_drop_score(self, xUserId: str, score: float) -> None:
        await self.DROPS_COLLECTION.update_one(
            {"xUserId": xUserId}, {"$set": {"score": score}}, upsert=True
        )

    async def update_drop_posts(self, xUserId: str, postId: str) -> None:
        await self.DROPS_COLLECTION.update_one(
            {"xUserId": xUserId}, {"$push": {"postIds": postId}}, upsert=True
        )

    async def update_drop_messages(self, xUserId: str, messageId: int) -> None:
        await self.DROPS_COLLECTION.update_one(
            {"xUserId": xUserId}, {"$push": {"messageIds": messageId}}, upsert=True
        )

    async def get_drop(self, xUserId: str):
        return await self.DROPS_COLLECTION.find_one({"xUserId": xUserId})

    async def delete_drop(self, xUserId: str) -> None:
        await self.DROPS_COLLECTION.delete_one({"xUserId": xUserId})

    async def check_drop(self, xUserId: str) -> bool:
        return await self.DROPS_COLLECTION.find_one({"xUserId": xUserId}) is not None

    async def check_banned(self, xUserId: str) -> bool:
        return await self.BANNED_COLLECTION.find_one({"xUserId": xUserId}) is not None

    async def get_drops(
        self, condition: Optional[dict], projection: Optional[dict]
    ) -> list[dict]:
        drops = self.DROPS_COLLECTION.find(condition, projection)
        return [drop async for drop in drops]


async def main():
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
    asyncio.run(main())
