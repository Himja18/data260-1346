"""HW9 Part 2/3 - semantic response cache at the ingress of the HW8 agent pipeline.

Each cache entry is one Redis hash  s1346:semcache:<sha1(query)>  with
    query, embedding (float32 bytes, 384-d bge-small), answer (final pipeline answer),
    deps (incident codes the answer used), data_version (fingerprint of those s1346_rel rows),
    created_at, agent_ms
and a RediSearch vector index  s1346:idx:semcache  (HNSW, COSINE) over the embedding field.

ask(query):
  embed -> KNN 1 -> similarity = 1 - cosine distance
  similarity >= threshold  -> (version check) -> HIT: stored final answer, is_cached=True, no agent call
  otherwise                -> MISS: s1346_rel facts + question -> HW8 pipeline -> store -> is_cached=False
"""
import hashlib
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np

import hw09_config as cfg
from hw09_common import incident_codes, now_iso, short

sys.path.insert(0, str(cfg.CODE_DIR))
from tracing import write_span  # noqa: E402  (HW10 Part 4)

RETURN_FIELDS = ("query", "answer", "deps", "data_version", "created_at", "agent_ms")


def _s(value: Any) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else ("" if value is None else str(value))


@dataclass
class Match:
    """Nearest cached entry."""
    key: str
    similarity: float
    fields: dict


@dataclass
class CacheResult:
    """What the ingress returns alongside each answer."""
    query: str
    answer: str
    is_cached: bool
    similarity: Optional[float]
    latency_ms: float
    threshold: float
    matched_query: Optional[str] = None
    reason: str = ""   # hit | miss:no-match | miss:below-threshold | miss:entity-mismatch | miss:stale-version
    data_version: str = ""
    timings_ms: dict = field(default_factory=dict)
    trace_id: str = ""                  # HW10: = the HW8 correlation_id of the miss path

    def to_dict(self) -> dict:
        """JSON-able."""
        return asdict(self)


# ---------------------------------------------------------------- vector index ----
class RediSearchIndex:
    """RediSearch (Redis Stack) vector index over the s1346:semcache:* hashes."""

    def __init__(self, r: Any, dim: int) -> None:
        self.r = r
        self.dim = dim
        self.ft = r.ft(cfg.SEMCACHE_INDEX)

    def ensure(self) -> None:
        """Create the index once (FT.CREATE ... ON HASH PREFIX 1 s1346:semcache: SCHEMA ...)."""
        from redis.commands.search.field import TagField, TextField, VectorField
        from redis.exceptions import ResponseError
        try:
            from redis.commands.search.index_definition import IndexDefinition, IndexType
        except ImportError:                                # redis-py < 6
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType
        try:
            self.ft.info()
            return
        except ResponseError:
            pass
        schema = (TextField("query"), TagField("deps"), TagField("data_version"),
                  VectorField("embedding", "HNSW", {"TYPE": "FLOAT32", "DIM": self.dim,
                                                     "DISTANCE_METRIC": "COSINE"}))
        self.ft.create_index(schema, definition=IndexDefinition(prefix=[cfg.SEMCACHE_PREFIX],
                                                                index_type=IndexType.HASH))

    def nearest(self, vec: np.ndarray) -> Optional[Match]:
        """KNN 1 by cosine distance."""
        from redis.commands.search.query import Query
        q = (Query("*=>[KNN 1 @embedding $vec AS dist]").sort_by("dist")
             .return_fields("dist", *RETURN_FIELDS).paging(0, 1).dialect(2))
        res = self.ft.search(q, query_params={"vec": vec.astype(np.float32).tobytes()})
        if not res.docs:
            return None
        doc = res.docs[0]
        fields = {f: _s(getattr(doc, f, "")) for f in RETURN_FIELDS}
        return Match(key=_s(doc.id), similarity=1.0 - float(doc.dist), fields=fields)

    def info(self) -> dict:
        """num_docs and the vector field definition (for the report)."""
        raw = self.ft.info()
        return {"index": cfg.SEMCACHE_INDEX, "num_docs": _s(raw.get("num_docs")),
                "attributes": [[_s(x) for x in a] for a in raw.get("attributes", [])]}


class ScanIndex:
    """Offline tests only (plain Redis without RediSearch): brute-force cosine over the same hashes."""

    def __init__(self, r: Any, dim: int) -> None:
        self.r = r
        self.dim = dim

    def ensure(self) -> None:
        """Nothing to create."""

    def nearest(self, vec: np.ndarray) -> Optional[Match]:
        """Scan every entry."""
        best: Optional[Match] = None
        for key in self.r.scan_iter(match=cfg.SEMCACHE_PREFIX + "*"):
            h = self.r.hgetall(key)
            emb = np.frombuffer(h[b"embedding"], dtype=np.float32)
            sim = float(np.dot(vec, emb))
            if best is None or sim > best.similarity:
                best = Match(key=_s(key), similarity=sim,
                             fields={f: _s(h.get(f.encode())) for f in RETURN_FIELDS})
        return best

    def info(self) -> dict:
        """Entry count."""
        return {"index": "scan (offline)", "num_docs": sum(1 for _ in self.r.scan_iter(match=cfg.SEMCACHE_PREFIX + "*"))}


# --------------------------------------------------------------- the cache ----
class SemanticCache:
    """Ingress cache in front of the agent pipeline."""

    def __init__(self, r: Any, embedder: Any, facts: Any, agent: Any, log: Any,
                 threshold: float = cfg.DEFAULT_THRESHOLD, version_check: bool = True,
                 entity_guard: bool = cfg.ENTITY_GUARD) -> None:
        self.r = r
        self.embedder = embedder
        self.facts = facts                  # IncidentCache (s1346_rel access)
        self.agent = agent
        self.log = log
        self.threshold = threshold
        self.version_check = version_check
        self.entity_guard = entity_guard     # Part 3.4: a hit must name exactly the same incident codes
        backend = RediSearchIndex if cfg.VECTOR_BACKEND == "redisearch" else ScanIndex
        self.index = backend(r, embedder.dim)
        self.index.ensure()

    # -- primitives ------------------------------------------------------------
    @staticmethod
    def key_for(query: str) -> str:
        """s1346:semcache:<sha1 of the normalised query> (an exact duplicate overwrites its own entry)."""
        return cfg.SEMCACHE_PREFIX + hashlib.sha1(" ".join(query.lower().split()).encode()).hexdigest()[:16]

    def lookup(self, query: str) -> tuple[Optional[Match], np.ndarray, dict]:
        """Embed + KNN 1. Returns (best match or None, query vector, timings)."""
        t0 = time.perf_counter()
        vec = self.embedder.embed(query)
        t1 = time.perf_counter()
        match = self.index.nearest(vec)
        t2 = time.perf_counter()
        return match, vec, {"embed": round((t1 - t0) * 1000, 2), "search": round((t2 - t1) * 1000, 2)}

    def store(self, query: str, vec: np.ndarray, answer: str, deps: list[str], version: str,
              agent_ms: float) -> str:
        """HSET one entry (query, embedding, final answer, data-version marker)."""
        key = self.key_for(query)
        self.r.hset(key, mapping={"query": query, "embedding": vec.astype(np.float32).tobytes(),
                                  "answer": answer, "deps": ",".join(deps), "data_version": version,
                                  "created_at": now_iso(), "agent_ms": f"{agent_ms:.1f}"})
        return key

    def run_agent(self, query: str, trace_id: Optional[str] = None, inject_fault: Optional[str] = None,
                  timeout_s: Optional[float] = None) -> tuple[str, list[str], str, dict]:
        """MISS path: read the s1346_rel rows the question names, ask the HW8 pipeline."""
        timings: dict = {}
        codes = incident_codes(query)
        t0 = time.perf_counter()
        facts = self.facts.facts_for_codes(codes) if codes else {}
        version = self.facts.fingerprint(facts, codes)
        timings["db_facts"] = round((time.perf_counter() - t0) * 1000, 2)
        prompt = query
        if codes:
            prompt = (f"{query}\n\nRecords from the {cfg.PREFIX}_rel database (use these exact values):\n"
                      + self.facts.facts_text(facts, codes))
        out = self.agent.ask(prompt, trace_id=trace_id, inject_fault=inject_fault, timeout_s=timeout_s)
        timings["agent"] = out["agent_ms"]
        timings["status"] = out.get("status")          # reviewer verdict from s1346_final
        return out["answer"], codes, version, timings

    # -- the ingress -------------------------------------------------------------
    def ask(self, query: str, threshold: Optional[float] = None, version_check: Optional[bool] = None,
            store: bool = True, trace_id: Optional[str] = None, inject_fault: Optional[str] = None,
            agent_timeout_s: Optional[float] = None) -> CacheResult:
        """Serve from cache when similar enough (and still current), else run the agent pipeline.

        HW10: one trace_id per request (generated here, reused as the HW8 correlation_id on a miss);
        spans `cache_lookup` (status hit|miss) and the root `request` go to reports/hw10/spans.jsonl.
        """
        thr = self.threshold if threshold is None else threshold
        check = self.version_check if version_check is None else version_check
        trace_id = trace_id or str(uuid.uuid4())
        wall0 = time.time()
        started = time.perf_counter()
        match, vec, timings = self.lookup(query)
        sim = None if match is None else round(match.similarity, 4)

        reason = "miss:no-match" if match is None else "miss:below-threshold"
        match_ok = False
        if match is not None and match.similarity >= thr:
            deps = [c for c in match.fields["deps"].split(",") if c]
            if self.entity_guard and set(incident_codes(query)) != set(deps):
                reason = "miss:entity-mismatch"
                self.log.info("GUARD  sim=%.4f >= %.2f but incident codes differ (%s vs cached %s) -> miss",
                              match.similarity, thr, incident_codes(query) or "-", deps or "-")
                match_ok = False
            else:
                match_ok = True
        if match is not None and match.similarity >= thr and match_ok:
            stale = False
            if check and deps:
                t0 = time.perf_counter()
                current = self.facts.data_version(deps)
                timings["version_check"] = round((time.perf_counter() - t0) * 1000, 2)
                stale = current != match.fields["data_version"]
                if stale:
                    self.r.delete(match.key)       # invalidate: the stored answer was built from old data
                    reason = "miss:stale-version"
                    self.log.info("STALE  sim=%.4f  stored version %s != current %s for %s -> entry deleted, "
                                  "re-running the agent", match.similarity, match.fields["data_version"],
                                  current, ",".join(deps))
            if not stale:
                latency = (time.perf_counter() - started) * 1000
                t_end = time.time()
                write_span(trace_id, "cache_lookup", wall0, t_end, "hit", "semantic_cache", similarity=sim,
                           threshold=thr, matched_query=match.fields["query"], reason="hit")
                write_span(trace_id, "request", wall0, t_end, "ok", "semantic_cache", cache="hit", query=query)
                self.log.info("HIT    sim=%.4f >= %.2f  latency=%.1f ms  cached query=\"%s\"",
                              match.similarity, thr, latency, short(match.fields["query"], 90))
                return CacheResult(query=query, answer=match.fields["answer"], is_cached=True, similarity=sim,
                                   latency_ms=round(latency, 1), threshold=thr,
                                   matched_query=match.fields["query"], reason="hit",
                                   data_version=match.fields["data_version"], timings_ms=timings,
                                   trace_id=trace_id)

        if reason not in ("miss:stale-version", "miss:entity-mismatch"):
            self.log.info("MISS   best sim=%s < %.2f  -> HW8 agent pipeline", "none" if sim is None else f"{sim:.4f}", thr)
        write_span(trace_id, "cache_lookup", wall0, time.time(), "miss", "semantic_cache", similarity=sim,
                   threshold=thr, reason=reason,
                   matched_query=None if match is None else match.fields["query"])
        try:
            answer, codes, version, agent_t = self.run_agent(query, trace_id, inject_fault, agent_timeout_s)
        except BaseException as exc:  # noqa: BLE001 - also Ctrl+C, so every cache_lookup has its request span
            write_span(trace_id, "request", wall0, time.time(), "error", "semantic_cache",
                       error=f"{exc.__class__.__name__}: {exc or 'interrupted before the final answer'}",
                       cache="miss", query=query)
            raise
        timings.update(agent_t)
        if store and agent_t.get("status") in (None, "approved"):
            t0 = time.perf_counter()
            self.store(query, vec, answer, codes, version, agent_t["agent"])
            timings["store"] = round((time.perf_counter() - t0) * 1000, 2)
        elif store:      # never cache an answer the Reviewer rejected - it would be served to every paraphrase
            self.log.info("NOT STORED: reviewer status=%s", agent_t.get("status"))
        latency = (time.perf_counter() - started) * 1000
        self.log.info("%s latency=%.1f ms (agent %.0f ms, reviewer=%s)  data_version=%s",
                      "STORED" if "store" in timings else "ANSWERED", latency, agent_t["agent"],
                      agent_t.get("status"), version)
        write_span(trace_id, "request", wall0, time.time(), "ok", "semantic_cache", cache="miss", query=query,
                   reviewer_status=agent_t.get("status"))
        return CacheResult(query=query, answer=answer, is_cached=False, similarity=sim,
                           latency_ms=round(latency, 1), threshold=thr,
                           matched_query=None if match is None else match.fields["query"],
                           reason=reason, data_version=version, timings_ms=timings, trace_id=trace_id)

    def clear(self) -> int:
        """Delete every s1346:semcache:* entry (the index stays and empties itself)."""
        keys = list(self.r.scan_iter(match=cfg.SEMCACHE_PREFIX + "*"))
        if keys:
            self.r.delete(*keys)
        return len(keys)
