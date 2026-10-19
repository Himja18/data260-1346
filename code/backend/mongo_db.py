"""PyMongo connection for DATA-260 HW6 (database s1346_doc).

One MongoClient per process. Collections are created with $jsonSchema
validators so MongoDB itself enforces the schema (Pydantic is the first
line of defence in the API, the validator is the backstop).
"""
import logging
import os
from typing import Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, OperationFailure

from hw06_config import EPISODES, INCIDENT_DOCS, MESSAGES, MONGO_DB, MONGO_URI, SUMMARIES

log = logging.getLogger("s1346.mongo")

INCIDENT_STATUSES = ["Reported", "Investigating", "Resolved", "Closed"]
INCIDENT_CATEGORIES = ["Delay", "Breakdown", "Accident", "Service Change"]

# ---- $jsonSchema validators ---------------------------------------------------
INCIDENT_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["title", "status", "category", "occurred_at", "created_at", "updated_at"],
    "properties": {
        "title": {"bsonType": "string", "minLength": 1, "maxLength": 100,
                  "description": "required short text, max 100 chars"},
        "description": {"bsonType": ["string", "null"], "maxLength": 2000},
        "location": {"bsonType": ["string", "null"], "maxLength": 100},
        "status": {"enum": INCIDENT_STATUSES, "description": "status enum, default Reported"},
        "category": {"enum": INCIDENT_CATEGORIES, "description": "fixed category set"},
        "occurred_at": {"bsonType": "date", "description": "required date/time"},
        "created_at": {"bsonType": "date"},
        "updated_at": {"bsonType": "date"},
    },
}}

MESSAGE_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["user_id", "session_id", "role", "content", "created_at"],
    "properties": {
        "user_id": {"bsonType": "string"},
        "session_id": {"bsonType": "string"},
        "role": {"enum": ["user", "assistant"]},
        "content": {"bsonType": "string"},
        "created_at": {"bsonType": "date"},
    },
}}

SUMMARY_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["user_id", "scope", "text", "created_at"],
    "properties": {
        "user_id": {"bsonType": "string"},
        "session_id": {"bsonType": ["string", "null"]},   # null for the lifetime summary
        "scope": {"enum": ["session", "user"]},
        "text": {"bsonType": "string"},
        "created_at": {"bsonType": "date"},
    },
}}

EPISODE_VALIDATOR = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
    "properties": {
        "user_id": {"bsonType": "string"},
        "session_id": {"bsonType": "string"},
        "fact": {"bsonType": "string", "maxLength": 300},
        "importance": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
        "embedding": {"bsonType": "array", "items": {"bsonType": "double"}},
        "created_at": {"bsonType": "date"},
    },
}}

COLLECTIONS = {
    INCIDENT_DOCS: (INCIDENT_VALIDATOR, [[("status", ASCENDING), ("category", ASCENDING)],
                                         [("occurred_at", DESCENDING)]]),
    MESSAGES: (MESSAGE_VALIDATOR, [[("user_id", ASCENDING), ("session_id", ASCENDING),
                                    ("created_at", DESCENDING)],
                                   [("user_id", ASCENDING), ("created_at", DESCENDING)]]),
    SUMMARIES: (SUMMARY_VALIDATOR, [[("user_id", ASCENDING), ("scope", ASCENDING),
                                     ("session_id", ASCENDING), ("created_at", DESCENDING)]]),
    EPISODES: (EPISODE_VALIDATOR, [[("user_id", ASCENDING), ("created_at", DESCENDING)]]),
}

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """Return the process-wide MongoClient (mongomock when MONGO_MOCK=1, for offline tests)."""
    global _client
    if _client is None:
        if os.getenv("MONGO_MOCK") == "1":
            import mongomock
            _client = mongomock.MongoClient(tz_aware=True)
        else:
            _client = MongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=3000)
    return _client


def get_mongo_db() -> Database:
    """FastAPI dependency: the s1346_doc database."""
    return get_client()[MONGO_DB]


def _ensure_collection(db: Database, name: str, validator: dict) -> None:
    """Create the collection with its validator, or update the validator if it exists."""
    try:
        if name in db.list_collection_names():
            db.command("collMod", name, validator=validator, validationLevel="strict",
                       validationAction="error")
        else:
            db.create_collection(name, validator=validator, validationLevel="strict",
                                 validationAction="error")
    except (CollectionInvalid, OperationFailure, NotImplementedError, TypeError) as exc:
        # mongomock does not implement validators; a real server always takes this path cleanly.
        log.warning("validator not applied to %s: %s", name, exc)
        if name not in db.list_collection_names():
            db.create_collection(name)


def init_mongo(db: Optional[Database] = None) -> Database:
    """Create all HW6 collections, validators and indexes (idempotent)."""
    db = db if db is not None else get_mongo_db()
    for name, (validator, indexes) in COLLECTIONS.items():
        _ensure_collection(db, name, validator)
        for keys in indexes:
            db[name].create_index(keys)
    log.info("MongoDB %s ready: %s", db.name, sorted(COLLECTIONS))
    return db
