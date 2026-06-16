"""
Redis-backed weighted rate limiting for RAG/LLM usage.

Only expensive paths (RAG answers, audio transcription + LLM) consume quota.
FAQ endpoint and manual override answers are free and never touch this module.

Configuration (all via environment variables or .env):
  RATE_LIMIT_ENABLED         true/false (default true)
  REDIS_URL                  redis://localhost:6379/0
  RATE_LIMIT_LLM_PER_MINUTE  max weighted units per 60-second window (default 10)
  RATE_LIMIT_LLM_PER_DAY     max weighted units per calendar day UTC (default 100)
  RATE_LIMIT_TEXT_COST       cost for a normal text LLM answer (default 1)
  RATE_LIMIT_LONG_TEXT_CHARS character threshold for "long" text (default 800)
  RATE_LIMIT_LONG_TEXT_COST  cost for a long text LLM answer (default 2)
  RATE_LIMIT_AUDIO_COST      cost for an audio+LLM answer (default 3)
  RATE_LIMIT_FAIL_OPEN       true = allow requests when Redis is unavailable (default true)
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost constants (public so callers can reference them by name)
# ---------------------------------------------------------------------------
COST_TEXT: int = 0          # resolved at load time from env
COST_LONG_TEXT: int = 0
COST_AUDIO: int = 0
LONG_TEXT_CHARS: int = 0


def _int_env(key: str, default: int) -> int:
    try:
        return int((os.getenv(key) or "").strip() or default)
    except ValueError:
        return default


def _bool_env(key: str, default: bool) -> bool:
    v = (os.getenv(key) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _reload_env() -> None:
    """Re-read cost constants from environment.  Called once at import time."""
    global COST_TEXT, COST_LONG_TEXT, COST_AUDIO, LONG_TEXT_CHARS
    COST_TEXT = _int_env("RATE_LIMIT_TEXT_COST", 1)
    COST_LONG_TEXT = _int_env("RATE_LIMIT_LONG_TEXT_COST", 2)
    COST_AUDIO = _int_env("RATE_LIMIT_AUDIO_COST", 3)
    LONG_TEXT_CHARS = _int_env("RATE_LIMIT_LONG_TEXT_CHARS", 800)


_reload_env()

# ---------------------------------------------------------------------------
# Redis client (lazy singleton)
# ---------------------------------------------------------------------------
_redis_client = None
_redis_ok: bool = False  # set to True after first successful ping


def _get_redis():
    """
    Return a Redis-compatible client, or None if Redis is unavailable / disabled.

    Set REDIS_URL=fakeredis to use an in-process FakeRedis instance —
    no server required, ideal for local dev and demo environments.
    """
    global _redis_client, _redis_ok

    if not _bool_env("RATE_LIMIT_ENABLED", True):
        return None

    if _redis_client is not None:
        return _redis_client

    redis_url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()

    if redis_url.lower() == "fakeredis":
        try:
            import fakeredis  # type: ignore
            _redis_client = fakeredis.FakeRedis(decode_responses=True)
            _redis_ok = True
            logger.info("Rate limiter: using fakeredis (in-process, no server required)")
            return _redis_client
        except ImportError:
            logger.warning(
                "Rate limiter: REDIS_URL=fakeredis but 'fakeredis' is not installed. "
                "Run: pip install fakeredis"
            )
            return None

    try:
        import redis  # type: ignore
        client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        _redis_client = client
        _redis_ok = True
        logger.info("Rate limiter: connected to Redis at %s", redis_url)
        return _redis_client
    except Exception as exc:
        logger.warning("Rate limiter: cannot connect to Redis (%s). Fail-open=%s.", exc,
                       _bool_env("RATE_LIMIT_FAIL_OPEN", True))
        return None


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def _hash_id(raw: str) -> str:
    """SHA-256 truncated to 16 hex chars — anonymises phone numbers / sender IDs."""
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_identity(channel: str, user_id: str) -> str:
    """
    Return a stable, privacy-safe Redis key fragment.

    channel   one of: 'web', 'telegram', 'whatsapp', 'messenger'
    user_id   raw identifier (chat_id, phone, session_id, …)
    """
    return f"{channel}:{_hash_id(str(user_id))}"


# ---------------------------------------------------------------------------
# Decision dataclass
# ---------------------------------------------------------------------------

@dataclass
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int   # 0 when allowed
    remaining_minute: int      # units left in current minute window
    remaining_day: int         # units left in current day window

    @property
    def as_json(self) -> dict:
        return {
            "rate_limited": not self.allowed,
            "retry_after_seconds": self.retry_after_seconds,
            "remaining_minute": self.remaining_minute,
            "remaining_day": self.remaining_day,
        }


# ---------------------------------------------------------------------------
# Core check-and-consume function
# ---------------------------------------------------------------------------

def check_and_consume(identity: str, cost: int) -> RateLimitDecision:
    """
    Atomically check whether *identity* can afford *cost* quota units and,
    if so, deduct them from both the per-minute and per-day counters.

    If Redis is unreachable:
      - RATE_LIMIT_FAIL_OPEN=true  → allow (return allowed=True, remaining=-1)
      - RATE_LIMIT_FAIL_OPEN=false → block conservatively

    Windows:
      - Per-minute: 60-second fixed window anchored to wall-clock minute.
      - Per-day:    UTC calendar day (resets at 00:00 UTC).
    """
    per_minute = _int_env("RATE_LIMIT_LLM_PER_MINUTE", 10)
    per_day = _int_env("RATE_LIMIT_LLM_PER_DAY", 100)

    client = _get_redis()

    if client is None:
        fail_open = _bool_env("RATE_LIMIT_FAIL_OPEN", True)
        if fail_open:
            logger.warning("Rate limiter: Redis unavailable, failing open for identity=%s", identity)
            return RateLimitDecision(allowed=True, retry_after_seconds=0,
                                     remaining_minute=-1, remaining_day=-1)
        else:
            logger.warning("Rate limiter: Redis unavailable, failing closed for identity=%s", identity)
            return RateLimitDecision(allowed=False, retry_after_seconds=60,
                                     remaining_minute=0, remaining_day=0)

    now = time.time()
    now_dt = datetime.fromtimestamp(now, tz=timezone.utc)

    # Fixed-window keys
    minute_bucket = int(now // 60)
    day_str = now_dt.strftime("%Y%m%d")
    min_key = f"rl:{identity}:min:{minute_bucket}"
    day_key = f"rl:{identity}:day:{day_str}"

    # TTLs for key expiry
    min_ttl = 120          # keep for 2 minutes so TTL always covers the window
    day_ttl = 86400 + 3600 # keep for 25 hours to survive day rollover

    try:
        pipe = client.pipeline()
        pipe.get(min_key)
        pipe.get(day_key)
        current_min_raw, current_day_raw = pipe.execute()

        current_min = int(current_min_raw or 0)
        current_day = int(current_day_raw or 0)

        remaining_min = max(0, per_minute - current_min)
        remaining_day = max(0, per_day - current_day)

        if current_min + cost > per_minute:
            # Minute window exhausted
            seconds_until_next_minute = 60 - int(now % 60)
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=seconds_until_next_minute,
                remaining_minute=remaining_min,
                remaining_day=remaining_day,
            )

        if current_day + cost > per_day:
            # Daily quota exhausted
            next_midnight = (now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                             .replace(tzinfo=timezone.utc))
            from datetime import timedelta
            next_midnight += timedelta(days=1)
            seconds_until_midnight = int((next_midnight.timestamp() - now))
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=seconds_until_midnight,
                remaining_minute=remaining_min,
                remaining_day=remaining_day,
            )

        # Quota available — deduct atomically
        pipe = client.pipeline()
        pipe.incrby(min_key, cost)
        pipe.expire(min_key, min_ttl)
        pipe.incrby(day_key, cost)
        pipe.expire(day_key, day_ttl)
        pipe.execute()

        return RateLimitDecision(
            allowed=True,
            retry_after_seconds=0,
            remaining_minute=max(0, per_minute - current_min - cost),
            remaining_day=max(0, per_day - current_day - cost),
        )

    except Exception as exc:
        logger.error("Rate limiter: Redis error during check_and_consume: %s", exc)
        fail_open = _bool_env("RATE_LIMIT_FAIL_OPEN", True)
        return RateLimitDecision(
            allowed=fail_open,
            retry_after_seconds=0 if fail_open else 60,
            remaining_minute=-1,
            remaining_day=-1,
        )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def cost_for_text(text: str) -> int:
    """Return the quota cost for a plain text RAG/LLM answer."""
    if len(text) >= LONG_TEXT_CHARS:
        return COST_LONG_TEXT
    return COST_TEXT


def cost_for_audio() -> int:
    """Return the quota cost for an audio message that proceeds to RAG/LLM."""
    return COST_AUDIO


def _format_duration_ar(seconds: int) -> str:
    """Format a duration in seconds into a human-readable Arabic string."""
    if seconds <= 0:
        return "لحظة"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ساعة")
    if minutes:
        parts.append(f"{minutes} دقيقة")
    if secs and not hours:  # drop seconds once we're showing hours
        parts.append(f"{secs} ثانية")
    return " و ".join(parts)


def _format_duration_en(seconds: int) -> str:
    """Format a duration in seconds into a human-readable English string."""
    if seconds <= 0:
        return "a moment"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if secs and not hours:  # drop seconds once we're showing hours
        parts.append(f"{secs} {'second' if secs == 1 else 'seconds'}")
    return " and ".join(parts)


def rate_limited_message(retry_after_seconds: int = 0) -> str:
    """
    Return a bilingual (Arabic + English) rate-limit message that includes
    a human-readable countdown until the quota window resets.
    """
    ar_time = _format_duration_ar(retry_after_seconds)
    en_time = _format_duration_en(retry_after_seconds)
    ar = f"عذراً، لقد تجاوزت الحد المسموح به من الأسئلة مؤقتاً. يرجى المحاولة مجدداً بعد {ar_time}."
    en = f"Sorry, you have reached the request limit temporarily. Please try again in {en_time}."
    return f"{ar}\n\n{en}"


# Keep a no-time fallback for import compatibility
RATE_LIMITED_MESSAGE_BILINGUAL = rate_limited_message(0)
