"""HW6 Part 2: MongoDB access for the messages, summaries and episodes collections.

All memory reads/writes go through MemoryStore so the chat logic can be tested
with any pymongo-compatible database. The Part 1 incident_reports collection is
never touched here.
"""
from datetime import UTC, datetime
from typing import Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from hw06_config import EPISODES, MESSAGES, SUMMARIES


def utc_now() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def _clean(doc: Optional[dict], drop: tuple = ()) -> Optional[dict]:
    """Make a Mongo document JSON-friendly: _id -> id, drop bulky fields."""
    if doc is None:
        return None
    doc = {k: v for k, v in doc.items() if k not in drop}
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


class MemoryStore:
    """Thin repository over the three memory collections."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.messages = db[MESSAGES]
        self.summaries = db[SUMMARIES]
        self.episodes = db[EPISODES]

    # ---- messages --------------------------------------------------------------
    def save_message(self, user_id: str, session_id: str, role: str, content: str) -> dict:
        """Insert one chat message."""
        doc = {"user_id": user_id, "session_id": session_id, "role": role,
               "content": content, "created_at": utc_now()}
        doc["_id"] = self.messages.insert_one(doc).inserted_id
        return doc

    def session_window(self, user_id: str, session_id: str, n: int, exclude_id=None) -> list:
        """Last n messages of a session, oldest first (optionally excluding one message)."""
        if n <= 0:
            return []
        query = {"user_id": user_id, "session_id": session_id}
        if exclude_id is not None:
            query["_id"] = {"$ne": exclude_id}
        docs = list(self.messages.find(query).sort([("created_at", DESCENDING), ("_id", DESCENDING)])
                    .limit(n))
        return list(reversed(docs))

    def count_user_messages(self, user_id: str, session_id: str) -> int:
        """Number of user messages in a session (drives the summary trigger)."""
        return self.messages.count_documents({"user_id": user_id, "session_id": session_id,
                                              "role": "user"})

    def recent_user_messages(self, user_id: str, limit: int = 16) -> list:
        """Last `limit` messages of a user across sessions, oldest first."""
        docs = list(self.messages.find({"user_id": user_id})
                    .sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(limit))
        return [_clean(d) for d in reversed(docs)]

    # ---- summaries ---------------------------------------------------------------
    def latest_summary(self, user_id: str, scope: str, session_id: Optional[str] = None) -> Optional[dict]:
        """Newest summary for a session (scope='session') or the lifetime summary (scope='user')."""
        query = {"user_id": user_id, "scope": scope}
        query["session_id"] = session_id if scope == "session" else None
        return _clean(self.summaries.find_one(query, sort=[("created_at", DESCENDING), ("_id", DESCENDING)]))

    def latest_session_summary_any(self, user_id: str) -> Optional[dict]:
        """Newest session-scope summary of the user, whatever the session."""
        return _clean(self.summaries.find_one({"user_id": user_id, "scope": "session"},
                                              sort=[("created_at", DESCENDING), ("_id", DESCENDING)]))

    def add_summary(self, user_id: str, session_id: Optional[str], scope: str, text: str) -> dict:
        """Insert a new summary version (older versions are kept as history)."""
        doc = {"user_id": user_id, "session_id": session_id if scope == "session" else None,
               "scope": scope, "text": text, "created_at": utc_now()}
        doc["_id"] = self.summaries.insert_one(doc).inserted_id
        return _clean(doc)

    def count_session_summaries(self, user_id: str) -> int:
        """How many session summaries the user has (drives the lifetime trigger)."""
        return self.summaries.count_documents({"user_id": user_id, "scope": "session"})

    def latest_summary_per_session(self, user_id: str, max_sessions: int = 5) -> list:
        """Newest summary text of each of the user's most recent sessions."""
        seen, out = set(), []
        for doc in self.summaries.find({"user_id": user_id, "scope": "session"}).sort(
                [("created_at", DESCENDING), ("_id", DESCENDING)]):
            if doc["session_id"] in seen:
                continue
            seen.add(doc["session_id"])
            out.append(_clean(doc))
            if len(out) == max_sessions:
                break
        return out

    def recent_summaries(self, user_id: str, limit: int = 5) -> list:
        """Most recent summaries of either scope."""
        return [_clean(d) for d in self.summaries.find({"user_id": user_id})
                .sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(limit)]

    # ---- episodes -----------------------------------------------------------------
    def add_episodes(self, user_id: str, session_id: str, facts: list) -> list:
        """Insert facts ({fact, importance, embedding}); returns them without embeddings."""
        if not facts:
            return []
        now = utc_now()
        docs = [{"user_id": user_id, "session_id": session_id, "fact": f["fact"],
                 "importance": float(f["importance"]),
                 "embedding": [float(x) for x in f["embedding"]], "created_at": now}
                for f in facts]
        self.episodes.insert_many(docs)
        return [_clean(d, drop=("embedding",)) for d in docs]

    def user_episodes(self, user_id: str, limit: int = 500) -> list:
        """The user's episodes with embeddings (for retrieval), newest first."""
        return list(self.episodes.find({"user_id": user_id})
                    .sort([("created_at", DESCENDING), ("_id", DESCENDING)]).limit(limit))

    def recent_episodes(self, user_id: str, limit: int = 20) -> list:
        """Last `limit` episodic facts without embedding arrays."""
        out = []
        for d in self.user_episodes(user_id, limit):
            clean = _clean(d, drop=("embedding",))
            clean["embedding_dim"] = len(d.get("embedding", []))
            out.append(clean)
        return out

    # ---- aggregate --------------------------------------------------------------
    def daily_message_counts(self, user_id: str) -> list:
        """Messages per calendar day (UTC), split by role, via an aggregation pipeline."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "total": {"$sum": 1},
                "user": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
                "assistant": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}},
                "sessions": {"$addToSet": "$session_id"},
            }},
            {"$sort": {"_id": ASCENDING}},
        ]
        return [{"date": r["_id"], "messages": r["total"], "user_messages": r["user"],
                 "assistant_messages": r["assistant"], "sessions": len(r["sessions"])}
                for r in self.messages.aggregate(pipeline)]

    def delete_user(self, user_id: str) -> dict:
        """Remove every memory document of a user (used for fresh experiment runs)."""
        return {name: self.db[name].delete_many({"user_id": user_id}).deleted_count
                for name in (MESSAGES, SUMMARIES, EPISODES)}
