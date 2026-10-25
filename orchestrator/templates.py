"""Code templates used by the deterministic implementation generator.

Each template yields a small, real module plus a real unit-test file. The testing agent
executes those tests with pytest, so a defect in a template fails the workflow for real.
"""

PYTEST_INI = "[pytest]\npythonpath = src\ntestpaths = tests\n"

_SHORTCODE = '''"""Short code generation with bounded collision handling."""

import secrets
import string

ALPHABET = string.ascii_letters + string.digits


class CodeAllocationError(RuntimeError):
    """Raised when a unique code cannot be allocated within the attempt budget."""


def generate_code(length: int = 7) -> str:
    if length < 4 or length > 16:
        raise ValueError("length must be between 4 and 16")
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def allocate_code(exists, length: int = 7, max_attempts: int = 10) -> str:
    for _ in range(max_attempts):
        code = generate_code(length)
        if not exists(code):
            return code
    raise CodeAllocationError(f"no unique code after {max_attempts} attempts")
'''

_SHORTCODE_TEST = """import pytest

from shortcode import ALPHABET, CodeAllocationError, allocate_code, generate_code


def test_generate_code_uses_alphabet_and_length():
    code = generate_code(8)
    assert len(code) == 8
    assert set(code) <= set(ALPHABET)


def test_generate_code_rejects_invalid_length():
    with pytest.raises(ValueError):
        generate_code(2)


def test_allocate_code_retries_on_collision():
    calls = {"n": 0}

    def exists(_code):
        calls["n"] += 1
        return calls["n"] < 4

    assert allocate_code(exists)
    assert calls["n"] == 4


def test_allocate_code_gives_up_after_bounded_attempts():
    with pytest.raises(CodeAllocationError):
        allocate_code(lambda _code: True, max_attempts=3)
"""

_EXPIRATION = '''"""Optional URL expiration rules."""

from datetime import UTC, datetime, timedelta


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_expired(expires_at: datetime | None, now: datetime | None = None) -> bool:
    """URLs without an expiry never expire (backward compatible)."""
    if expires_at is None:
        return False
    current = _aware(now) if now else datetime.now(UTC)
    return _aware(expires_at) <= current


def validate_expiry(
    expires_at: datetime | None, now: datetime | None = None, max_days: int = 365
) -> datetime | None:
    if expires_at is None:
        return None
    current = _aware(now) if now else datetime.now(UTC)
    value = _aware(expires_at)
    if value <= current:
        raise ValueError("expiry must be in the future")
    if value - current > timedelta(days=max_days):
        raise ValueError(f"expiry must be within {max_days} days")
    return value


def default_expiry(days: int, now: datetime | None = None) -> datetime:
    if days <= 0:
        raise ValueError("days must be positive")
    current = _aware(now) if now else datetime.now(UTC)
    return current + timedelta(days=days)
'''

_EXPIRATION_TEST = """from datetime import UTC, datetime, timedelta

import pytest

from expiration import default_expiry, is_expired, validate_expiry

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_no_expiry_never_expires():
    assert is_expired(None, NOW) is False


def test_past_expiry_is_expired():
    assert is_expired(NOW - timedelta(seconds=1), NOW) is True


def test_future_expiry_is_not_expired():
    assert is_expired(NOW + timedelta(days=1), NOW) is False


def test_naive_datetimes_are_treated_as_utc():
    assert is_expired(datetime(2025, 12, 31), NOW) is True


def test_validate_rejects_past_and_far_future():
    with pytest.raises(ValueError):
        validate_expiry(NOW - timedelta(days=1), NOW)
    with pytest.raises(ValueError):
        validate_expiry(NOW + timedelta(days=400), NOW, max_days=365)


def test_validate_allows_none_and_valid_values():
    assert validate_expiry(None, NOW) is None
    assert validate_expiry(NOW + timedelta(days=5), NOW) == NOW + timedelta(days=5)


def test_default_expiry_is_relative_to_now():
    assert default_expiry(7, NOW) == NOW + timedelta(days=7)
    with pytest.raises(ValueError):
        default_expiry(0, NOW)
"""

_CACHE = '''"""Bounded TTL cache for resolved redirects."""

import time
from collections import OrderedDict
from threading import Lock


class RedirectCache:
    def __init__(self, max_entries: int = 1000, ttl_seconds: float = 60.0, clock=time.monotonic):
        if max_entries <= 0 or ttl_seconds <= 0:
            raise ValueError("max_entries and ttl_seconds must be positive")
        self._max = max_entries
        self._ttl = ttl_seconds
        self._clock = clock
        self._data: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, code: str) -> str | None:
        with self._lock:
            entry = self._data.get(code)
            if entry is None or entry[1] <= self._clock():
                self._data.pop(code, None)
                self._misses += 1
                return None
            self._data.move_to_end(code)
            self._hits += 1
            return entry[0]

    def set(self, code: str, url: str) -> None:
        with self._lock:
            self._data[code] = (url, self._clock() + self._ttl)
            self._data.move_to_end(code)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def invalidate(self, code: str) -> bool:
        with self._lock:
            return self._data.pop(code, None) is not None

    def stats(self) -> dict:
        with self._lock:
            return {"entries": len(self._data), "hits": self._hits, "misses": self._misses}
'''

_CACHE_TEST = """import pytest

from redirect_cache import RedirectCache


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_hit_and_miss_are_counted():
    cache = RedirectCache(clock=FakeClock())
    assert cache.get("abc") is None
    cache.set("abc", "https://example.com")
    assert cache.get("abc") == "https://example.com"
    assert cache.stats() == {"entries": 1, "hits": 1, "misses": 1}


def test_entries_expire_after_ttl():
    clock = FakeClock()
    cache = RedirectCache(ttl_seconds=10, clock=clock)
    cache.set("abc", "https://example.com")
    clock.now = 11
    assert cache.get("abc") is None


def test_cache_is_bounded_and_evicts_least_recently_used():
    cache = RedirectCache(max_entries=2, clock=FakeClock())
    cache.set("a", "1")
    cache.set("b", "2")
    cache.get("a")
    cache.set("c", "3")
    assert cache.get("b") is None
    assert cache.get("a") == "1"


def test_invalidate_removes_entry():
    cache = RedirectCache(clock=FakeClock())
    cache.set("abc", "https://example.com")
    assert cache.invalidate("abc") is True
    assert cache.invalidate("abc") is False
    assert cache.get("abc") is None


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        RedirectCache(max_entries=0)
"""

_ANALYTICS = '''"""Thread-safe click analytics."""

from datetime import UTC, datetime
from threading import Lock


class ClickCounter:
    def __init__(self):
        self._counts: dict[str, int] = {}
        self._last: dict[str, datetime] = {}
        self._lock = Lock()

    def record(self, code: str, at: datetime | None = None) -> int:
        stamp = at or datetime.now(UTC)
        with self._lock:
            self._counts[code] = self._counts.get(code, 0) + 1
            if code not in self._last or stamp > self._last[code]:
                self._last[code] = stamp
            return self._counts[code]

    def summary(self, code: str) -> dict:
        with self._lock:
            return {
                "code": code,
                "clicks": self._counts.get(code, 0),
                "last_clicked_at": self._last.get(code),
            }
'''

_ANALYTICS_TEST = """from datetime import UTC, datetime, timedelta
from threading import Thread

from click_counter import ClickCounter


def test_unknown_code_has_zero_clicks():
    assert ClickCounter().summary("none") == {
        "code": "none",
        "clicks": 0,
        "last_clicked_at": None,
    }


def test_last_click_is_the_latest_timestamp():
    counter = ClickCounter()
    early = datetime(2026, 1, 1, tzinfo=UTC)
    counter.record("abc", early + timedelta(minutes=5))
    counter.record("abc", early)
    assert counter.summary("abc")["last_clicked_at"] == early + timedelta(minutes=5)


def test_concurrent_clicks_are_all_counted():
    counter = ClickCounter()

    def work():
        for _ in range(250):
            counter.record("abc")

    threads = [Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert counter.summary("abc")["clicks"] == 2000
"""

_GENERIC = '''"""Traceable change record for requirements that map to no known capability."""

from dataclasses import dataclass

REQUIREMENT = {requirement!r}
ACCEPTANCE_CRITERIA = {criteria!r}


@dataclass(frozen=True)
class ChangeRecord:
    requirement: str
    acceptance_criteria: tuple[str, ...]

    def is_traceable(self) -> bool:
        return bool(self.requirement.strip()) and len(self.acceptance_criteria) > 0


def current_record() -> ChangeRecord:
    return ChangeRecord(REQUIREMENT, tuple(ACCEPTANCE_CRITERIA))
'''

_GENERIC_TEST = """from change_record import ACCEPTANCE_CRITERIA, REQUIREMENT, current_record


def test_record_is_traceable_to_requirement():
    record = current_record()
    assert record.requirement == REQUIREMENT
    assert record.is_traceable()


def test_every_criterion_is_non_empty():
    assert all(criterion.strip() for criterion in ACCEPTANCE_CRITERIA)
"""

TEMPLATES: dict[str, dict[str, str]] = {
    "shortening": {"src/shortcode.py": _SHORTCODE, "tests/test_shortcode.py": _SHORTCODE_TEST},
    "expiration": {"src/expiration.py": _EXPIRATION, "tests/test_expiration.py": _EXPIRATION_TEST},
    "caching": {"src/redirect_cache.py": _CACHE, "tests/test_redirect_cache.py": _CACHE_TEST},
    "analytics": {"src/click_counter.py": _ANALYTICS, "tests/test_click_counter.py": _ANALYTICS_TEST},
}  # fmt: skip


def render(capabilities: list[str], requirement: str, criteria: list[str]) -> dict[str, str]:
    files: dict[str, str] = {"pytest.ini": PYTEST_INI}
    for capability in capabilities:
        if capability in TEMPLATES:
            files.update(TEMPLATES[capability])
        else:
            files["src/change_record.py"] = _GENERIC.format(
                requirement=requirement, criteria=criteria
            )
            files["tests/test_change_record.py"] = _GENERIC_TEST
    return files
