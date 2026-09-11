"""Persistent raw-read cache contracts using synthetic data and isolated SQLite files."""

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from videocaptioner.cli.main import main
from videocaptioner.core.ocr.cache import (
    RawReadStore,
    cache_limit_bytes,
    manage_cache,
    read_cache,
)
from videocaptioner.core.ocr.codec import encode
from videocaptioner.core.ocr.consensus import CacheScope
from videocaptioner.core.ocr.models import OcrError

from .test_document import make_document
from .test_tracking import frame

SCOPE = CacheScope("a" * 64, "b" * 64, "c" * 64)
RAW = make_document().cues[0].candidates[0].raw
KEY = "d" * 64


def test_reopen_raw_reads_with_scope_separation_and_no_review(tmp_path, text_image):
    image = frame(text_image(), 0)
    with read_cache(SCOPE, tmp_path, 4096) as cache:
        key, _ = cache.key(image)
        cache.put(key, RAW)
    with read_cache(SCOPE, tmp_path, 4096) as cache:
        assert cache.get(key) == RAW
    for field in ("source_sha256", "profile_sha256", "policy_sha256"):
        with read_cache(replace(SCOPE, **{field: "f" * 64}), tmp_path, 4096) as cache:
            changed_key, _ = cache.key(image)
            assert cache.get(changed_key) is None
    with sqlite3.connect(tmp_path / "reads.sqlite3") as connection:
        value = json.loads(connection.execute("SELECT payload FROM reads").fetchone()[0])
        assert value == {"schema": "ocr-raw-cache-v1", "key": key, "read": encode(RAW)}


def test_lru_quota_and_auto_vacuum_release_space(tmp_path):
    store = RawReadStore(tmp_path, 2048)
    store.open()
    try:
        store.put(KEY, RAW)
        entry_size = store.info().payload_bytes
        store.max_bytes = entry_size * 2
        second, third = "e" * 64, "f" * 64
        store.put(second, RAW)
        assert store.get(KEY, RAW.revision) == RAW
        store.put(third, RAW)
        assert store.get(second, RAW.revision) is None
        assert store.get(KEY, RAW.revision) == RAW
        assert store.info().entries == 2 and store.info().payload_bytes <= store.max_bytes
        store.max_bytes = 1024 * 1024
        larger = replace(RAW, lines=(replace(RAW.lines[0], text="synthetic " * 400),))
        for index in range(100):
            store.put(hashlib.sha256(str(index).encode()).hexdigest(), larger)
        before = store.info()
        assert before.database_bytes > 200000
        assert store.clear() == before.entries
        assert store.info().entries == 0 and store.info().payload_bytes == 0
        assert store.info().database_bytes < before.database_bytes / 4
    finally:
        store.close()


@pytest.mark.parametrize("damage", ["checksum", "revision", "schema", "nan", "oversized"])
def test_damaged_entry_is_a_miss_never_a_fabricated_read(tmp_path, damage):
    store = RawReadStore(tmp_path, 4096)
    store.open()
    try:
        store.put(KEY, RAW)
        payload = json.dumps({"schema": "ocr-raw-cache-v1", "key": KEY, "read": encode(RAW)}).encode()
        if damage == "revision":
            payload = payload.replace(b'b' * 64, b'a' * 64)
        elif damage == "schema":
            payload = payload.replace(b'ocr-raw-cache-v1', b'unknown-v1')
        elif damage == "nan":
            payload = payload.replace(b'0.98', b'NaN')
        elif damage == "oversized":
            payload = b' ' * (1024 * 1024 + 1)
        checksum = "bad" if damage == "checksum" else hashlib.sha256(payload).hexdigest()
        with sqlite3.connect(store.path) as connection:
            connection.execute("UPDATE reads SET payload=?, checksum=? WHERE key=?", (payload, checksum, KEY))
        assert store.get(KEY, RAW.revision) is None
        assert store.info().entries == 0
    finally:
        store.close()


def test_unknown_file_preserved_and_disk_failure_falls_back(tmp_path):
    path = tmp_path / "reads.sqlite3"
    path.write_bytes(b"preserve unrelated file")
    notices = []
    with read_cache(SCOPE, tmp_path, 4096, warning=notices.append) as cache:
        cache.put(KEY, RAW)
        assert cache.get(KEY) == RAW
    assert len(notices) == 1 and str(tmp_path) not in notices[0]
    assert path.read_bytes() == b"preserve unrelated file"


def test_lock_contention_is_bounded_and_uses_memory(tmp_path):
    store = RawReadStore(tmp_path, 4096)
    store.open()
    try:
        assert store.connection is not None
        store.connection.execute("BEGIN EXCLUSIVE")
        notices = []
        with read_cache(SCOPE, tmp_path, 4096, warning=notices.append) as cache:
            cache.put(KEY, RAW)
            assert cache.get(KEY) == RAW
        assert len(notices) == 1
        store.connection.rollback()
        assert store.info().entries == 0
    finally:
        store.close()


def test_cancel_during_cache_get_remains_cancelled(tmp_path):
    cancelled = False

    def check():
        if cancelled:
            raise OcrError("synthetic cancellation")

    with read_cache(SCOPE, tmp_path, 4096, check=check) as cache:
        cancelled = True
        with pytest.raises(OcrError, match="cancellation"):
            cache.get(KEY)


def test_disk_full_keeps_current_read_in_memory_and_warns_once(tmp_path, monkeypatch):
    notices = []
    with read_cache(SCOPE, tmp_path, 4096, warning=notices.append) as cache:
        def fail(*_):
            raise sqlite3.OperationalError("synthetic disk full")
        monkeypatch.setattr(RawReadStore, "put", fail)
        cache.put(KEY, RAW)
        cache.put("e" * 64, RAW)
        assert cache.get(KEY) == RAW
        assert len(notices) == 1


def test_reduced_limit_evicts_on_open_without_new_inference(tmp_path):
    store = RawReadStore(tmp_path, 4096)
    store.open()
    store.put(KEY, RAW)
    store.put("e" * 64, RAW)
    limit = store.info().payload_bytes // 2
    store.close()
    reduced = RawReadStore(tmp_path, limit)
    reduced.open()
    try:
        assert reduced.info().entries == 1 and reduced.info().payload_bytes <= limit
        assert reduced.get(KEY, RAW.revision) is None
    finally:
        reduced.close()


def test_disabled_cache_creates_no_files(tmp_path):
    root = tmp_path / "absent"
    with read_cache(SCOPE, root, 0) as cache:
        cache.put(KEY, RAW)
        assert cache.get(KEY) == RAW
    assert not root.exists()


@pytest.mark.parametrize("value", [-1, 513, True, 1.5])
def test_invalid_limits(value):
    with pytest.raises(OcrError):
        cache_limit_bytes(value)


def test_concurrent_jobs_share_one_quota(tmp_path):
    initial = RawReadStore(tmp_path, 4096)
    initial.open()
    initial.close()

    def job(index):
        with read_cache(SCOPE, tmp_path, 4096) as cache:
            for number in range(20):
                key = hashlib.sha256(f"{index}:{number}".encode()).hexdigest()
                cache.put(key, RAW)
                assert cache.get(key) == RAW

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(job, range(3)))
    check = RawReadStore(tmp_path, 4096)
    check.open()
    try:
        assert 0 < check.info().payload_bytes <= 4096
    finally:
        check.close()


def test_management_preserves_models_reviews_and_unknown_cache_files(tmp_path, monkeypatch):
    root = tmp_path / "ocr-cache"
    monkeypatch.setattr("videocaptioner.core.ocr.cache.cache_directory", lambda: root)
    assert manage_cache().entries == 0 and not root.exists()
    with read_cache(SCOPE, root, 4096) as cache:
        cache.put(KEY, RAW)
    preserved = [tmp_path / "review.json", tmp_path / "model.bin", root / "unrelated.txt"]
    for path in preserved:
        path.write_bytes(b"keep")
    assert main(["ocr-cache", "status"]) == 0
    assert manage_cache().entries == 1
    assert main(["ocr-cache", "clear"]) == 0
    assert manage_cache().entries == 0
    assert all(path.read_bytes() == b"keep" for path in preserved)


def test_hardlinked_database_is_never_modified(tmp_path):
    source = tmp_path / "source"
    store = RawReadStore(source, 4096)
    store.open()
    store.put(KEY, RAW)
    store.close()
    before = store.path.read_bytes()
    linked = tmp_path / "linked"
    linked.mkdir()
    os.link(store.path, linked / "reads.sqlite3")
    with pytest.raises(OcrError, match="ordinary"):
        RawReadStore(linked, 4096).open()
    assert store.path.read_bytes() == before
