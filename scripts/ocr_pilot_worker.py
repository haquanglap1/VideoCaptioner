"""Isolated, network-disabled OCR pilot. Only this process imports OCR dependencies."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import socket
import sys
import time
import traceback
from pathlib import Path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    network_attempts = []

    def no_network(*_args, **_kwargs):
        network_attempts.append("blocked")
        raise RuntimeError("Network is disabled during OCR pilot inference")

    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network
    profile = json.loads((args.root / "profile.json").read_text(encoding="utf-8"))
    manifest = json.loads(args.inputs.read_text(encoding="utf-8"))
    for name, version in profile["packages"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Runtime package version mismatch")
    for model in profile["models"].values():
        if digest(args.root / "weights" / model["file"]) != model["sha256"]:
            raise ValueError("Model hash mismatch")
    verified_s = time.perf_counter() - started

    import psutil
    from omegaconf import OmegaConf
    from rapidocr import EngineType, LangCls, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
    from rapidocr.utils.download_file import DownloadFile

    DownloadFile.run = no_network
    import_s = time.perf_counter() - started - verified_s
    params = dict(profile["params"])
    for section, model_type, version, language in (
        ("Det", ModelType.MOBILE, OCRVersion.PPOCRV5, LangDet.CH),
        ("Rec", ModelType.SERVER, OCRVersion.PPOCRV5, LangRec.CH),
        ("Cls", ModelType.MOBILE, OCRVersion.PPOCRV4, LangCls.CH),
    ):
        params.update({f"{section}.engine_type": EngineType.ONNXRUNTIME,
                       f"{section}.model_type": model_type, f"{section}.ocr_version": version,
                       f"{section}.lang_type": language,
                       f"{section}.model_path": str(args.root / "weights" / profile["models"][section.lower()]["file"])})
    load_start = time.perf_counter()
    engine = RapidOCR(params=params)
    load_s = time.perf_counter() - load_start
    effective = OmegaConf.to_container(engine.cfg, resolve=True, enum_to_str=True)
    effective["Global"]["model_root_dir"] = None
    for section in ("Det", "Rec", "Cls"):
        effective[section]["model_path"] = "weights/" + profile["models"][section.lower()]["file"]
        effective[section]["model_root_dir"] = None
    (args.output / "effective-config.json").write_text(json.dumps(effective, indent=2, default=str), encoding="utf-8")
    dictionary = engine.text_rec.session.get_character_list()
    dict_blob = json.dumps(dictionary, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if (len(dictionary) != profile["dictionary_count"]
            or hashlib.sha256(dict_blob).hexdigest() != profile["dictionary_sha256"]):
        raise ValueError("Recognizer dictionary mismatch")
    (args.output / "dictionary.json").write_bytes(dict_blob)
    providers = {name: getattr(engine, "text_" + name).session.session.get_providers()
                 for name in ("det", "rec", "cls")}
    if any(value != ["CPUExecutionProvider"] for value in providers.values()):
        raise ValueError("OCR pilot must run on CPU only")
    counts = {"det": 0, "rec": 0, "cls": 0}
    rec_regions = 0
    for name in counts:
        session = getattr(engine, "text_" + name).session.session
        original = session.run

        def counted(*values, _name=name, _original=original, **kwargs):
            counts[_name] += 1
            return _original(*values, **kwargs)

        session.run = counted
    rows = []
    inference_start = time.perf_counter()
    with (args.output / "raw.jsonl").open("x", encoding="utf-8") as stream:
        for item in manifest["crops"]:
            path = args.inputs.parent / item["file"]
            if digest(path) != item["sha256"]:
                raise ValueError("Input crop hash mismatch")
            begun = time.perf_counter()
            row = {"id": item["id"], "crop_sha256": item["sha256"], "cache": "fresh"}
            try:
                result = engine(path, use_cls=False, text_score=0.0)
                row.update({"texts": list(result.txts) if result.txts is not None else [],
                            "scores": [float(v) for v in result.scores] if result.scores is not None else [],
                            "boxes": result.boxes.tolist() if result.boxes is not None else [],
                            "stage_s": [float(v) if v is not None else None for v in result.elapse_list],
                            "error": None})
                rec_regions += len(row["texts"])
            except Exception as exc:
                row.update({"texts": [], "scores": [], "boxes": [], "error": type(exc).__name__})
                (args.output / (item["id"] + ".error.log")).write_text(traceback.format_exc(), encoding="utf-8")
            row["wall_s"] = time.perf_counter() - begun
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            print(json.dumps({"id": row["id"], "lines": len(row["texts"]), "error": row["error"]}), flush=True)
    memory = psutil.Process().memory_info()
    metrics = {"schema": "ocr-pilot-metrics-v1", "profile": profile["id"],
               "input_manifest_sha256": digest(args.inputs), "profile_sha256": digest(args.root / "profile.json"),
               "verify_s": verified_s, "import_s": import_s, "load_s": load_s,
               "inference_loop_s": time.perf_counter() - inference_start,
               "worker_wall_s": time.perf_counter() - started,
               "crops": len(rows), "inference_calls": counts, "recognized_regions": rec_regions,
               "fresh_crops": len(rows), "cache_hits": 0, "warmup_calls": 0,
               "errors": sum(row["error"] is not None for row in rows),
               "empty_crops": sum(not row["texts"] for row in rows),
               "rss_bytes": memory.rss, "peak_wset_bytes": getattr(memory, "peak_wset", None),
               "providers": providers, "network_attempts": len(network_attempts),
               "vision_api_calls": 0, "provider_usage": None, "provider_cost": None,
               "dictionary_count": len(dictionary), "dictionary_sha256": hashlib.sha256(dict_blob).hexdigest(),
               "python": sys.version.split()[0],
               "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
               "timing_accuracy_ms": None, "boundary_policy": "Inherited prototype; not remeasured"}
    (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if metrics["errors"] or network_attempts:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
