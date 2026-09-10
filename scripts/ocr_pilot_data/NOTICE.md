# OCR pilot sources and licenses

The runtime uses RapidOCR 3.9.2 (Apache-2.0) and ONNX Runtime CPU 1.29.0 (MIT).
Dependencies retain their installed distribution license files. Source packages
and all dependencies are pinned in requirements.lock with artifact hashes.

- RapidOCR source/license: https://github.com/RapidAI/RapidOCR/tree/v3.9.2
- Official model catalog: https://rapidai.github.io/RapidOCRDocs/main/en/model_list/
- ONNX CPU runtime: https://onnxruntime.ai/docs/get-started/with-python.html
- Upstream detector: https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det
- Upstream recognizer: https://huggingface.co/PaddlePaddle/PP-OCRv5_server_rec

Both upstream PaddlePaddle model cards identify Apache-2.0. The ONNX conversions
come from RapidAI/RapidOCR on ModelScope, revision v3.9.2. Exact URLs and published
SHA-256 values are in profile.json, checked against the downloaded bytes. The
recognizer dictionary is embedded in that ONNX file, not downloaded independently.
The exported dictionary is hashed as UTF-8 JSON with ensure_ascii=False and compact
separators, before inserting the CTC blank and trailing space.

RapidOCR initializes its bundled PP-OCRv4 orientation classifier even with
classification disabled. Its explicit file/hash are recorded, with zero classifier
inference calls. Unused v6 models arrive inside the upstream wheel but are never
selected by this profile. No model family sweep is performed.

The repository README links to MODEL_LICENSES.md, but that linked file returned
404 during this pilot. Model attribution is therefore recorded against the
official upstream model cards and the RapidAI catalog/manifest, not an invented
conversion provenance document.
