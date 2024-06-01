from typing import TypedDict

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


class BannedSchema(TypedDict):
    xUserId: str


class DropsSchema(TypedDict):
    xUserId: str
    xUsername: str
    score: int
    postIds: list[str]
    messageIds: list[int]
