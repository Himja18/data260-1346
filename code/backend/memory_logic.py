"""HW6 Part 2/3: memory logic - window policy, episode extraction, summaries,
retrieval and prompt assembly. Model calls go through the HW1 ModelClient.

Prompt layout (order required by the brief):
  1. system  : primer + long-term summaries (lifetime, then current session)
  2. history : short-term window (last N messages of this session)
  3. user    : current message, followed by the retrieved episodic facts
"""
import json
import re
from typing import Optional

from embeddings import cosine_scores
from hw06_config import (COMPRESS_KEEP_RECENT, COMPRESS_MAX_CHARS, EPISODE_DEDUP_SCORE,
                         MAX_FACTS_PER_MESSAGE)

SYSTEM_PRIMER = (
    "You are TransitDesk, the assistant of the s1346 Municipal Transit Incidents system. "
    "You help dispatchers log, triage and follow up transit incidents (delays, breakdowns, "
    "accidents, service changes). Use the memory sections below when they are relevant. "
    "If remembered facts conflict, trust the most recent statement from the user. "
    "If you do not know something, say so instead of guessing. Answer in at most 120 words."
)

EXTRACT_PROMPT = (
    "Extract up to {k} short, durable facts about the USER from the message below "
    "(identity, role, preferences, assignments, vehicles, places, people, decisions). "
    "Only use information that is written in the MESSAGE itself; never invent names or "
    "details. Questions, greetings and general knowledge contain no facts. Each fact must "
    "be one short sentence in the third person that starts with \"The user\". Rate "
    "importance from 0 to 1 (1 = must never be forgotten).\n"
    "Return ONLY JSON: {{\"facts\": [{{\"fact\": \"...\", \"importance\": 0.8}}]}} "
    "and {{\"facts\": []}} if there is nothing worth remembering.\n\nMESSAGE:\n{message}"
)

SESSION_SUMMARY_PROMPT = (
    "Update the running summary of this conversation. Write 3-8 concise bullet points "
    "('- ' prefix) keeping every concrete fact the user stated (names, numbers, routes, "
    "vehicles, preferences, corrections). If the user corrected something, keep only the "
    "corrected value and mark it '(updated)'. No introduction.\n\n"
    "PREVIOUS SUMMARY:\n{previous}\n\nRECENT MESSAGES:\n{transcript}"
)

LIFETIME_PROMPT = (
    "Condense these per-session summaries into one lifetime profile of the user: at most "
    "10 bullet points ('- ' prefix), durable facts and preferences only, newest value wins "
    "when two sessions disagree. No introduction.\n\n"
    "PREVIOUS LIFETIME SUMMARY:\n{previous}\n\nSESSION SUMMARIES (newest first):\n{sessions}"
)

POLICIES = ("none", "compress_assistant")


# ---- short-term window --------------------------------------------------------
def _first_sentence(text: str, max_chars: int) -> str:
    """First sentence of a text, cut to max_chars."""
    text = " ".join(text.split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    first = match.group(1) if match else text
    return first if len(first) <= max_chars else first[: max_chars - 1].rstrip() + "…"


def apply_window_policy(window: list, policy: str = "none",
                        keep_recent: int = COMPRESS_KEEP_RECENT,
                        max_chars: int = COMPRESS_MAX_CHARS) -> list:
    """Return the window as [{role, content}] after the memory-saving policy.

    compress_assistant: the newest `keep_recent` messages stay verbatim; older
    assistant replies are cut to their first sentence (<= max_chars). User
    messages are never compressed because they carry the user's own facts.
    """
    out = []
    cutoff = len(window) - keep_recent
    for i, msg in enumerate(window):
        content = msg["content"]
        if policy == "compress_assistant" and i < cutoff and msg["role"] == "assistant":
            content = _first_sentence(content, max_chars)
        out.append({"role": msg["role"], "content": content})
    return out


# ---- JSON helpers --------------------------------------------------------------
def extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of the first JSON object in a model reply."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ---- episodic memory --------------------------------------------------------------
def parse_facts(reply: str, max_facts: int = MAX_FACTS_PER_MESSAGE) -> list:
    """Validate extracted facts: non-empty text <= 300 chars, importance clamped to 0..1."""
    data = extract_json(reply) or {}
    facts = []
    for item in data.get("facts", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact", "")).strip()
        if not fact or len(fact) > 300:
            continue
        try:
            importance = float(item.get("importance", 0.5))
        except (TypeError, ValueError):
            importance = 0.5
        facts.append({"fact": fact, "importance": round(min(max(importance, 0.0), 1.0), 2)})
    return facts[:max_facts]


def extract_episodes(client, message: str, options: Optional[dict] = None) -> tuple:
    """Ask the model for up to 3 facts in the user message. Returns (facts, CompletionResult)."""
    prompt = EXTRACT_PROMPT.format(k=MAX_FACTS_PER_MESSAGE, message=message)
    result = client.complete([{"role": "user", "content": prompt}],
                             options={"temperature": 0, "num_predict": 200, **(options or {})})
    return parse_facts(result.content), result


def dedup_facts(facts: list, existing: list, threshold: float = EPISODE_DEDUP_SCORE) -> list:
    """Drop facts whose embedding is a near-duplicate of a stored or earlier new fact."""
    kept = []
    known = [e["embedding"] for e in existing]
    for f in facts:
        scores = cosine_scores(f["embedding"], known)
        if len(scores) and float(scores.max()) >= threshold:
            continue
        kept.append(f)
        known.append(f["embedding"])
    return kept


def retrieve_episodes(query_vec: list, episodes: list, k: int, min_score: float) -> list:
    """Top-k episodes by cosine similarity to the current message (score >= min_score)."""
    if not episodes or k <= 0:
        return []
    scores = cosine_scores(query_vec, [e["embedding"] for e in episodes])
    ranked = sorted(zip(scores.tolist(), episodes), key=lambda p: p[0], reverse=True)
    return [{"fact": e["fact"], "importance": e["importance"], "score": round(s, 3),
             "session_id": e["session_id"], "created_at": e["created_at"]}
            for s, e in ranked[:k] if s >= min_score]


# ---- summaries ------------------------------------------------------------------
def should_summarize(user_message_count: int, every: int) -> bool:
    """True on every `every`-th user message of a session."""
    return every > 0 and user_message_count > 0 and user_message_count % every == 0


def should_condense_lifetime(session_summary_count: int, every: int) -> bool:
    """True on every `every`-th session summary of the user."""
    return every > 0 and session_summary_count > 0 and session_summary_count % every == 0


def transcript(messages: list) -> str:
    """Render messages as 'role: content' lines."""
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


def summarize_session(client, previous: Optional[str], messages: list) -> tuple:
    """Produce an updated session summary. Returns (text, CompletionResult)."""
    prompt = SESSION_SUMMARY_PROMPT.format(previous=previous or "(none)", transcript=transcript(messages))
    result = client.complete([{"role": "user", "content": prompt}],
                             options={"temperature": 0, "num_predict": 300})
    return result.content.strip(), result


def condense_lifetime(client, previous: Optional[str], session_summaries: list) -> tuple:
    """Produce an updated lifetime summary. Returns (text, CompletionResult)."""
    sessions = "\n\n".join(f"[session {s['session_id']}]\n{s['text']}" for s in session_summaries)
    prompt = LIFETIME_PROMPT.format(previous=previous or "(none)", sessions=sessions)
    result = client.complete([{"role": "user", "content": prompt}],
                             options={"temperature": 0, "num_predict": 300})
    return result.content.strip(), result


# ---- prompt assembly --------------------------------------------------------------
def build_prompt(session_summary: Optional[str], lifetime_summary: Optional[str],
                 window: list, message: str, facts: list,
                 primer: str = SYSTEM_PRIMER) -> tuple:
    """Compose the model messages. Returns (messages, component_texts) for token accounting."""
    long_term = ""
    if lifetime_summary or session_summary:
        parts = ["## Long-term memory"]
        if lifetime_summary:
            parts.append("What you know about this user from earlier sessions:\n" + lifetime_summary)
        if session_summary:
            parts.append("Summary of this session so far:\n" + session_summary)
        long_term = "\n\n".join(parts)
    episodic = ""
    if facts:
        episodic = ("[Memory: facts the user told you earlier that may be relevant]\n"
                    + "\n".join(f"- {f['fact']}" for f in facts))
    system = primer + ("\n\n" + long_term if long_term else "")
    user = message + ("\n\n" + episodic if episodic else "")
    messages = [{"role": "system", "content": system}, *window, {"role": "user", "content": user}]
    components = {"system_primer": primer, "long_term_summary": long_term,
                  "short_term_window": transcript(window), "current_message": message,
                  "episodic_facts": episodic}
    return messages, components
