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

scores_schema = {
    "xUserId": {"type": "string", "unique": True},
    "score": {"type": "number"},
}

db = client[COLLECTION_NAME]
BANNED_COLLECTION = db["banned"]
SCORES_COLLECTION = db["scores"]


class BannedSchema(TypedDict):
    xUserId: str


class ScoresSchema(TypedDict):
    xUserId: str
    score: int


async def insert_banned(xUserId: str):
    existing = BANNED_COLLECTION.find_one({"xUserId": xUserId})
    if existing:
        return
    banned: BannedSchema = {"xUserId": xUserId}
    BANNED_COLLECTION.insert_one(banned)


async def insert_update_score(xUserId: str, score: int):
    scores: ScoresSchema = {"xUserId": xUserId, "score": score}
    SCORES_COLLECTION.update_one({"xUserId": xUserId}, {"$set": scores}, upsert=True)


async def check_banned(xUserId: str):
    return BANNED_COLLECTION.find_one({"xUserId": xUserId}) is not None
