"""HW5 Part 3: timeouts + bounded exponential-backoff retries for storage calls.

RetryPolicy                      the knobs (attempts, per-attempt timeout, backoff)
call_with_retry(fn, policy)      runs fn with a timeout per attempt and retries
                                 transient failures; returns a CallReport
ResilientRepository(repo)        wraps any repository so every method goes
                                 through call_with_retry (used by domain_tools)
FaultInjectingRepository(repo)   seeded fault injection for the 150-call experiment

Only *transient* errors are retried (timeouts, connection/operational errors,
injected faults). Bad input is never retried - it fails immediately.
"""
import concurrent.futures as cf
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("s1346_rel.retry")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)                     # stderr only (STDIO-safe)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s retry: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False                                     # avoid duplicate lines


class TransientError(Exception):
    """A failure worth retrying (injected fault, dropped connection, ...)."""


class RetriesExhausted(Exception):
    def __init__(self, report: "CallReport"):
        self.report = report
        super().__init__(f"failed after {report.attempts} attempt(s): {report.last_error}")


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (TransientError, TimeoutError, cf.TimeoutError, ConnectionError)):
        return True
    # SQLAlchemy OperationalError covers lost connections / server gone away.
    # Access-denied (1045) is a config error, not transient - retrying won't help.
    name = exc.__class__.__name__
    return name == "OperationalError" and "1045" not in str(exc)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3            # 1 try + 2 retries
    attempt_timeout_s: float = 2.0   # per-attempt ceiling
    base_delay_s: float = 0.1        # backoff: 0.1s, 0.2s, 0.4s ... (x2 each retry)
    multiplier: float = 2.0
    max_delay_s: float = 1.0         # cap on any single backoff wait

    def delay_before(self, attempt: int) -> float:
        """Wait before attempt N (N >= 2)."""
        return min(self.base_delay_s * self.multiplier ** (attempt - 2), self.max_delay_s)


INTERACTIVE = RetryPolicy()
BATCH = RetryPolicy(max_attempts=6, attempt_timeout_s=10.0, base_delay_s=1.0,
                    multiplier=2.0, max_delay_s=30.0)


@dataclass
class CallReport:
    ok: bool = False
    value: Any = None
    attempts: int = 0
    attempt_outcomes: list = field(default_factory=list)   # e.g. ["fault", "ok"]
    latency_ms: float = 0.0
    last_error: str | None = None


_pool = cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool-call")


def call_with_retry(fn: Callable[[], Any], policy: RetryPolicy = INTERACTIVE,
                    sleep: Callable[[float], None] = time.sleep, label: str = "call") -> CallReport:
    rep = CallReport()
    t0 = time.perf_counter()
    for attempt in range(1, policy.max_attempts + 1):
        if attempt > 1:
            d = policy.delay_before(attempt)
            log.info("%s: retry %d/%d after %.2fs backoff", label, attempt, policy.max_attempts, d)
            sleep(d)
        rep.attempts = attempt
        fut = _pool.submit(fn)
        try:
            rep.value = fut.result(timeout=policy.attempt_timeout_s)
            rep.ok = True
            rep.attempt_outcomes.append("ok")
            break
        except cf.TimeoutError:
            rep.attempt_outcomes.append("timeout")
            rep.last_error = f"attempt timed out after {policy.attempt_timeout_s:.1f}s"
            log.warning("%s: attempt %d %s", label, attempt, rep.last_error)
        except Exception as e:                            # noqa: BLE001
            transient = _is_transient(e)
            rep.attempt_outcomes.append("fault" if transient else "error")
            rep.last_error = f"{e.__class__.__name__}: {str(e).splitlines()[0][:160]}"
            log.warning("%s: attempt %d failed (%s): %s", label, attempt,
                        "transient" if transient else "permanent", rep.last_error)
            if not transient:
                break                                     # don't retry permanent errors
    rep.latency_ms = (time.perf_counter() - t0) * 1000
    return rep


class ResilientRepository:
    """Proxy: every repository method call goes through call_with_retry."""

    def __init__(self, repo, policy: RetryPolicy = INTERACTIVE):
        self._repo, self.policy = repo, policy
        self.last_report: CallReport | None = None

    def __getattr__(self, name):
        target = getattr(self._repo, name)
        if not callable(target):
            return target

        def wrapped(*args, **kwargs):
            rep = call_with_retry(lambda: target(*args, **kwargs), self.policy, label=name)
            self.last_report = rep
            if not rep.ok:
                raise RetriesExhausted(rep)
            return rep.value
        return wrapped


class FaultInjectingRepository:
    """Before each underlying attempt, fail with probability `rate`.
    The draws come from random.Random(seed), so the same seed always
    produces the same success/failure sequence."""

    def __init__(self, repo, rate: float, seed: int):
        self._repo, self.rate = repo, rate
        self.rng = random.Random(seed)
        self.draws: list[bool] = []                       # True = injected failure

    def __getattr__(self, name):
        target = getattr(self._repo, name)
        if not callable(target):
            return target

        def wrapped(*args, **kwargs):
            fail = self.rng.random() < self.rate
            self.draws.append(fail)
            if fail:
                raise TransientError(f"injected fault (rate={self.rate:.0%})")
            return target(*args, **kwargs)
        return wrapped
