import json
import sys

from scripts import build_vieneu_one_app as builder


def test_builder_augments_pyinstaller_onedir_without_deleting_base_files(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    name = "VideoCaptioner-VieNeu-Test"
    package = tmp_path / "dist" / name
    package.mkdir(parents=True)
    exe = package / f"{name}.exe"
    exe.write_bytes(b"exe")
    internal = package / "_internal" / "runtime.dll"
    internal.parent.mkdir()
    internal.write_bytes(b"dll")

    runtime = tmp_path / "built-runtime"
    (runtime / "bridge").mkdir(parents=True)
    (runtime / "python.exe").write_bytes(b"python")
    (runtime / "bridge" / "vieneu_bridge.py").write_text("# bridge\n", encoding="utf-8")
    (runtime / "runtime-manifest.json").write_text(
        json.dumps(
            {
                "runtime_version": "test-runtime",
                "runtime_source_revision": "source-sha",
                "requirements_sha256": "requirements-sha",
                "vieneu_wheel_sha256": "wheel-sha",
            }
        ),
        encoding="utf-8",
    )

    model_root = tmp_path / "model-seed"
    references = {
        "active_snapshot": "hf/model/snapshots/" + "a" * 40,
        "tokenizer_snapshot": "hf/tokenizer/snapshots/" + "b" * 40,
        "codec_snapshot": "hf/codec/snapshots/" + "c" * 40,
    }
    for reference in references.values():
        snapshot = model_root / reference
        snapshot.mkdir(parents=True)
        (snapshot / "weights.bin").write_bytes(b"model")
    (model_root / "state.json").write_text(
        json.dumps(
            {
                "active_revision": "a" * 40,
                "tokenizer_revision": "b" * 40,
                "codec_revision": "c" * 40,
                **references,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_vieneu_one_app.py",
            "--name",
            name,
            "--runtime",
            str(runtime),
            "--model-root",
            str(model_root),
            "--skip-exe-build",
        ],
    )
    assert builder.main() == 0
    assert exe.read_bytes() == b"exe"
    assert internal.read_bytes() == b"dll"
    assert (package / "runtime" / "vieneu" / "python.exe").is_file()
    assert (package / "AppData" / "models" / "vieneu" / "state.json").is_file()
    manifest = json.loads((package / "distribution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["exe"]["sha256"] == builder.sha256(exe)
    assert manifest["runtime"]["runtime_version"] == "test-runtime"
    assert manifest["model_seed"]["active_revision"] == "a" * 40
