from typing import TypedDict, Dict, Any

banned_schema: Dict[str, Dict[str, Any]] = {
    "xUserId": {"type": "string", "unique": True},
}

drops_schema: Dict[str, Dict[str, Any]] = {
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
