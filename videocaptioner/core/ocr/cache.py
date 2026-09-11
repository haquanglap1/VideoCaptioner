"""Bounded local raw OCR reads; saved review documents never enter this cache."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .codec import decode, encode, sha256
from .consensus import CacheScope, ReadCache, validate_read
from .models import Check, EngineRead, OcrError

DEFAULT_CACHE_MIB = 64
MAX_CACHE_MIB = 512
MAX_ENTRY_BYTES = 1024 * 1024
MAX_ENTRIES = 4096
APPLICATION_ID = 0x4F435231
UNAVAILABLE = "Cache OCR không dùng được; tiếp tục đọc bằng CPU và chỉ nhớ trong phiên này."


def cache_directory() -> Path:
    from videocaptioner.config import APPDATA_PATH

    return Path(APPDATA_PATH) / "ocr" / "cache" / "raw-v1"


def cache_limit_bytes(mib: int) -> int:
    if type(mib) is not int or not 0 <= mib <= MAX_CACHE_MIB:
        raise OcrError(f"OCR cache limit must be an integer from 0 to {MAX_CACHE_MIB} MiB")
    return mib * 1024 * 1024


def _regular_path(path: Path) -> None:
    # Refuse junctions as well as symlinks before SQLite touches its journal files.
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OcrError("OCR cache cannot use linked paths")
        if item == path and not stat.S_ISDIR(info.st_mode):
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OcrError("OCR cache requires an ordinary private file")


@dataclass(frozen=True)
class CacheInfo:
    entries: int = 0
    payload_bytes: int = 0
    database_bytes: int = 0


class RawReadStore:
    """One connection per job thread; transactions serialize writers across processes.

    The quota covers serialized raw reads, keys and checksums. SQLite metadata is
    reported separately; FULL auto-vacuum releases unused pages after eviction.
    """

    def __init__(self, root: Path, max_bytes: int, *, check: Check = lambda: None):
        if type(max_bytes) is not int or max_bytes <= 0:
            raise OcrError("Invalid OCR disk cache limit")
        self.root = Path(os.path.abspath(root))
        self.path = self.root / "reads.sqlite3"
        self.max_bytes, self.check = max_bytes, check
        self.connection: sqlite3.Connection | None = None

    def _paths(self) -> None:
        _regular_path(self.root)
        for suffix in ("", "-journal", "-wal", "-shm"):
            _regular_path(self.path.with_name(self.path.name + suffix))

    def open(self, *, create: bool = True, trim: bool = True) -> bool:
        self.check()
        self._paths()
        if not create and not self.path.exists():
            return False
        self.root.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with self.path.open("xb"):
                created = True
        except FileExistsError:
            pass
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=0.1)
        self.connection = connection
        try:
            if created:
                connection.execute("PRAGMA auto_vacuum=FULL")
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute("PRAGMA user_version=1")
                    connection.execute("CREATE TABLE reads (key TEXT PRIMARY KEY, payload BLOB NOT NULL, "
                                       "checksum TEXT NOT NULL, accessed INTEGER NOT NULL)")
                    connection.execute("CREATE INDEX reads_lru ON reads(accessed, key)")
            elif (connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                  or connection.execute("PRAGMA user_version").fetchone()[0] != 1
                  or connection.execute("PRAGMA auto_vacuum").fetchone()[0] != 1):
                raise OcrError("Unrecognized OCR cache; existing data was kept")
            connection.execute("PRAGMA journal_mode=DELETE")
            if trim:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._trim(connection)
            return True
        except BaseException:
            self.close()
            raise

    def _db(self) -> sqlite3.Connection:
        self.check()
        self._paths()
        if self.connection is None:
            raise OcrError("OCR cache is closed")
        return self.connection

    def _trim(self, connection: sqlite3.Connection) -> None:
        count, size = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(length(payload)+length(key)+length(checksum)),0) FROM reads"
        ).fetchone()
        if count <= MAX_ENTRIES and size <= self.max_bytes:
            return
        rows = connection.execute("SELECT key, length(payload)+length(key)+length(checksum) "
                                  "FROM reads ORDER BY accessed, key").fetchall()
        for key, length in rows:
            self.check()
            if count <= MAX_ENTRIES and size <= self.max_bytes:
                break
            connection.execute("DELETE FROM reads WHERE key=?", (key,))
            count, size = count - 1, size - length

    def get(self, key: str, revision: str) -> EngineRead | None:
        sha256(key)
        connection = self._db()
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT CASE WHEN length(payload)<=? THEN payload END, checksum "
                                     "FROM reads WHERE key=?", (MAX_ENTRY_BYTES, key)).fetchone()
            if row is None:
                return None
            payload, checksum = row
            try:
                if (not isinstance(payload, bytes) or len(payload) > MAX_ENTRY_BYTES
                        or hashlib.sha256(payload).hexdigest() != checksum):
                    raise ValueError
                value = json.loads(payload)
                if (not isinstance(value, dict) or set(value) != {"schema", "key", "read"}
                        or value["schema"] != "ocr-raw-cache-v1" or value["key"] != key):
                    raise ValueError
                raw = decode(EngineRead, value["read"])
                validate_read(raw)
                if raw.revision != revision:
                    raise ValueError
            except (ValueError, TypeError, OverflowError, RecursionError):
                connection.execute("DELETE FROM reads WHERE key=?", (key,))
                return None
            connection.execute("UPDATE reads SET accessed=? WHERE key=?", (time.time_ns(), key))
            return raw

    def put(self, key: str, raw: EngineRead) -> None:
        sha256(key)
        validate_read(raw)
        payload = json.dumps({"schema": "ocr-raw-cache-v1", "key": key, "read": encode(raw)},
                             ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_ENTRY_BYTES or len(payload) + len(key) + 64 > self.max_bytes:
            return
        connection = self._db()
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR REPLACE INTO reads VALUES (?,?,?,?)",
                               (key, payload, hashlib.sha256(payload).hexdigest(), time.time_ns()))
            self._trim(connection)

    def info(self) -> CacheInfo:
        connection = self._db()
        count, size = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(length(payload)+length(key)+length(checksum)),0) FROM reads"
        ).fetchone()
        return CacheInfo(count, size, self.path.stat().st_size)

    def clear(self) -> int:
        connection = self._db()
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT COUNT(*) FROM reads").fetchone()[0]
            connection.execute("DELETE FROM reads")
        return count

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class PersistentReadCache(ReadCache):
    def __init__(self, scope: CacheScope, store: RawReadStore,
                 warning: Callable[[str], None] = lambda _: None):
        super().__init__(scope)
        self.store, self.warning = store, warning
        self.disabled = False

    def _disable(self) -> None:
        self.disabled = True
        self.warning(UNAVAILABLE)

    def get(self, key: str) -> EngineRead | None:
        raw = super().get(key)
        if raw is None and not self.disabled:
            try:
                raw = self.store.get(key, self.scope.profile_sha256)
            except (OSError, sqlite3.Error, OcrError):
                self.store.check()  # Cancellation must not turn into a cache miss.
                self._disable()
            if raw is not None:
                super().put(key, raw)
        return raw

    def put(self, key: str, read: EngineRead) -> None:
        if read.revision != self.scope.profile_sha256:
            raise OcrError("OCR read does not match the selected profile")
        super().put(key, read)
        if not self.disabled:
            try:
                self.store.put(key, read)
            except (OSError, sqlite3.Error, OcrError):
                self.store.check()
                self._disable()


@contextmanager
def read_cache(scope: CacheScope, root: Path | None, max_bytes: int, *,
               check: Check = lambda: None, warning: Callable[[str], None] = lambda _: None
               ) -> Iterator[ReadCache]:
    if root is None or max_bytes == 0:
        yield ReadCache(scope)
        return
    store = RawReadStore(root, max_bytes, check=check)
    try:
        try:
            store.open()
        except (OSError, sqlite3.Error, OcrError):
            check()
            warning(UNAVAILABLE)
            cache = ReadCache(scope)
        else:
            cache = PersistentReadCache(scope, store, warning)
        yield cache
    finally:
        store.close()


def manage_cache(*, clear: bool = False, check: Check = lambda: None) -> CacheInfo:
    # Management never walks/deletes a directory or opens model/review files.
    store = RawReadStore(cache_directory(), MAX_CACHE_MIB * 1024 * 1024, check=check)
    try:
        if not store.open(create=False, trim=False):
            return CacheInfo()
        before = store.info()
        if clear:
            store.clear()
        return before
    except (OSError, sqlite3.Error):
        raise OcrError("Không truy cập được cache OCR; dữ liệu khác được giữ nguyên.") from None
    finally:
        store.close()
