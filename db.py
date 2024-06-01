from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from os import getenv
from dotenv import load_dotenv
from typing import TypedDict
import sys


load_dotenv()

MONGO_URI: str = getenv("MONGO_URI", "")
COLLECTION_NAME: str = getenv("COLLECTION_NAME", "twitter")

print("Connecting to MongoDB...")
client: MongoClient = MongoClient(MONGO_URI, server_api=ServerApi("1"))

try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
    sys.exit(1)

banned_schema = {
    "xUserId": {"type": "string", "unique": True},
}

drops_schema = {
    "xUserId": {"type": "string", "unique": True},
    "xUsername": {"type": "string"},
    "score": {"type": "number"},
    "postIds": {"type": "list", "schema": {"type": "string"}},
    "messageIds": {"type": "list", "schema": {"type": "string"}},
}

db = client[COLLECTION_NAME]
BANNED_COLLECTION = db["banned"]
DROPS_COLLECTION = db["drops"]


class BannedSchema(TypedDict):
    xUserId: str


class DropsSchema(TypedDict):
    xUserId: str
    xUsername: str
    score: int
    postIds: list[str]
    messageIds: list[int]


async def insert_banned(xUserId: str):
    existing = BANNED_COLLECTION.find_one({"xUserId": xUserId})
    if existing:
        return
    banned: BannedSchema = {"xUserId": xUserId}
    BANNED_COLLECTION.insert_one(banned)


async def insert_drop(xUserId: str, xUsername: str):
    scores: DropsSchema = {
        "xUserId": xUserId,
        "xUsername": xUsername,
        "score": 0,
        "postIds": [],
        "messageIds": [],
    }
    DROPS_COLLECTION.insert_one(scores)


async def update_drop_score(xUserId: str, score: int):
    DROPS_COLLECTION.update_one(
        {"xUserId": xUserId}, {"$set": {"score": score}}, upsert=True
    )


async def update_drop_posts(xUserId: str, postId: str):
    DROPS_COLLECTION.update_one(
        {"xUserId": xUserId}, {"$push": {"postIds": postId}}, upsert=True
    )


async def update_drop_messages(xUserId: str, messageId: int):
    DROPS_COLLECTION.update_one(
        {"xUserId": xUserId}, {"$push": {"messageIds": messageId}}, upsert=True
    )


async def get_drop(xUserId: str):
    return DROPS_COLLECTION.find_one({"xUserId": xUserId})


async def check_drop(xUserId: str):
    return DROPS_COLLECTION.find_one({"xUserId": xUserId}) is not None


async def check_banned(xUserId: str):
    return BANNED_COLLECTION.find_one({"xUserId": xUserId}) is not None
