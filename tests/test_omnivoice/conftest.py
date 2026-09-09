"""Small local transport fixtures; no remote model or dependency downloads."""

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from videocaptioner.core.tts.omnivoice import config, prepare


@pytest.fixture
def loopback_download():
    state = SimpleNamespace(
        payload=b"fixture-model\0" * 170000, mode="complete", requests=[], slow=False,
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            range_header = self.headers.get("Range")
            offset = int(range_header.removeprefix("bytes=").removesuffix("-")) if range_header else 0
            status = 206 if offset else 200
            body = state.payload[offset:]
            content_range = f"bytes {offset}-{len(state.payload) - 1}/{len(state.payload)}" if offset else ""
            if state.mode == "ignore-range":
                status, body, content_range = 200, state.payload, ""
            elif state.mode == "bad-range":
                content_range = f"bytes {offset + 1}-{len(state.payload) - 1}/{len(state.payload)}"
            elif state.mode == "bad-range-end":
                content_range = f"bytes {offset}-{len(state.payload)}/{len(state.payload)}"
            elif state.mode == "bad-range-length":
                content_range = f"bytes {offset}-{len(state.payload) - 2}/{len(state.payload)}"
            elif state.mode == "corrupt":
                body = b"x" * len(body)
            if offset >= len(state.payload):
                status, body, content_range = 416, b"", f"bytes */{len(state.payload)}"
            state.requests.append({"range": range_header, "status": status, "content_range": content_range})
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            if content_range:
                self.send_header("Content-Range", content_range)
            self.end_headers()
            if state.mode == "interrupt":
                body = body[:1024 * 1024 + 137]
            try:
                for start in range(0, len(body), 64 * 1024):
                    self.wfile.write(body[start:start + 64 * 1024])
                    self.wfile.flush()
                    if state.slow:
                        time.sleep(0.005)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}/model"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture
def staged_runtime(tmp_path, monkeypatch, loopback_download):
    """Keep dependency installation out of scope; exercise the real model downloader."""
    if prepare.os.name != "nt":
        pytest.skip("The managed installer targets Windows")
    root = tmp_path / "staged"
    python = root / "env/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    owner = {"schema": "omnivoice-runtime-v1", "code_revision": config.CODE_REVISION,
             "model_revision": config.MODEL_REVISION}
    for name in ("owner.json", "dependencies-ready.json"):
        (root / name).write_text(json.dumps(owner), encoding="utf-8")
    (root / "source.zip").write_bytes(b"already downloaded source fixture")
    (root / f"OmniVoice-{config.CODE_REVISION}").mkdir()
    spec = {"source_sha256": prepare.digest(root / "source.zip"),
            "requirements_sha256": prepare.digest(prepare.resources() / "requirements.lock"),
            "files": [{"path": "weights.bin", "size": len(loopback_download.payload),
                       "sha256": hashlib.sha256(loopback_download.payload).hexdigest(), "blob_id": ""}]}
    monkeypatch.setattr(prepare, "recipe", lambda: spec)
    monkeypatch.setattr(config, "recipe", lambda: spec)
    monkeypatch.setattr(prepare.shutil, "which", lambda name: "fixture-uv-never-run")

    def no_subprocess(*args, **kwargs):
        pytest.fail("Staged fixture must not install dependencies or run inference")

    monkeypatch.setattr(prepare.subprocess, "Popen", no_subprocess)
    download = prepare.download

    def local_download(url, path, expected, **kwargs):
        return download(loopback_download.url, path, expected, **kwargs)

    monkeypatch.setattr(prepare, "download", local_download)
    return root


@pytest.fixture(scope="session")
def omni_qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
