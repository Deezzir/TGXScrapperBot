from typing import Any, Dict, TypedDict

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
    x_user_id: str


class DropsSchema(TypedDict):
    x_user_id: str
    x_username: str
    x_score: int
    x_post_ids: list[str]
    message_ids: list[int]
