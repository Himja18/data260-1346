"""HW9 - show what is in Redis: every s1346:* key, the vector index, one cache entry.

    python code/hw09/run_hw09_inspect.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw09_config as cfg  # noqa: E402
from hw09_common import banner, get_redis, setup_logging, short  # noqa: E402


def main() -> None:
    """Print keys, index info and one entry."""
    log = setup_logging("inspect")
    banner(log, "Redis contents")
    r = get_redis()
    log.info("redis_version=%s modules=%s", r.info("server").get("redis_version"),
             [m.get(b"name", m.get("name")) for m in r.module_list()] if hasattr(r, "module_list") else "?")
    keys = sorted(k.decode() for k in r.scan_iter(match="*"))
    other = [k for k in keys if not k.startswith(cfg.PREFIX)]
    log.info("%d keys, %d start with '%s', %d do not %s", len(keys), len(keys) - len(other), cfg.PREFIX, len(other),
             other[:5])
    for k in keys:
        if not k.startswith(cfg.PREFIX + ":semcache:"):
            log.info("  %-40s %-6s %s", k, r.type(k).decode(), r.get(k).decode() if r.type(k) == b"string" else "")
    sem = [k for k in keys if k.startswith(cfg.SEMCACHE_PREFIX)]
    log.info("  %s* : %d hashes (one per cached query)", cfg.SEMCACHE_PREFIX, len(sem))
    try:
        info = r.ft(cfg.SEMCACHE_INDEX).info()
        dec = {(k.decode() if isinstance(k, bytes) else k): v for k, v in info.items()}
        attrs = [[x.decode() if isinstance(x, bytes) else x for x in a] for a in dec.get("attributes", [])]
        log.info("index %s: num_docs=%s", cfg.SEMCACHE_INDEX, dec.get("num_docs"))
        for a in attrs:
            log.info("   field %s", " ".join(str(x) for x in a))
    except Exception as exc:  # noqa: BLE001
        log.info("index %s: not available (%s)", cfg.SEMCACHE_INDEX, exc)
    if sem:
        h = r.hgetall(sem[0])
        log.info("example entry %s:", sem[0])
        for f, v in h.items():
            name = f.decode()
            shown = f"<{len(v)} bytes = {len(v) // 4} float32>" if name == "embedding" else short(v.decode(), 140)
            log.info("   %-13s %s", name, shown)


if __name__ == "__main__":
    main()
