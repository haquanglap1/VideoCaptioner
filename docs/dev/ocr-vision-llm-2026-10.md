# OCR bằng vision LLM qua tờ ảnh ghép — 2026-10-07

User yêu cầu thay OCR local (chất lượng kém, nặng máy) bằng cách cắt chữ tự động rồi gửi thẳng cho
LLM qua API đang cấu hình, càng ít thao tác tay càng tốt. Lượt này thêm đường `vision-sheet-v1`
cho cả CLI và GUI; đường CPU PP-OCR, PaddleOCR-VL, vạch chọn dòng và character tracking giữ nguyên.

## Hành vi

- **Local chỉ còn decode + theo dõi.** `RoiDecoder` giải mã ROI như cũ; policy tracking mới
  `text-strokes-v1` (`core/ocr/tracking.py`) tìm nét chữ sáng/mảnh bằng top-hat (opening 7 px ở
  bề rộng 960) trong **một dải ngang** có nhiều nhóm nét, so hai frame bằng **độ chồng nét (IoU ≥
  0,55)** thay vì tile cạnh, và giữ frame fade-in trong 150 ms đầu (`settle_ms`) thay vì tách cue.
  Không ONNX, không model.
- **Một crop nét nhất mỗi cue** (`candidate_limit=1`, `TrackedRegion.best_pts`); `--vision-crops 2`
  thêm frame biên để đối chiếu. Crop được **thu về dải chữ** (`focus_crop`/`text_bounds`) rồi phóng
  tối đa 3× tới bề rộng tờ (mặc định 1024 px) nên chữ lớn, rõ.
- **Tờ ảnh ghép** (`render_sheet`): tối đa 16 crop (1–40) xếp dọc, lề trái trắng ghi số thứ tự,
  vách xám; cao tối đa 3600 px, tự chia tờ. Một request = một tờ: system prompt cố định (`PROMPT`,
  hash vào identity), user gồm `Rows: N. Subtitle language: zh.` và ảnh `data:image/png;base64`.
  `max_completion_tokens = min(12000, 3000 + 120·N)`: lượt chạy thật đầu tiên của user với
  `gpt-6-luna` (model suy luận) cho thấy hạn mức cũ `200 + 80·N = 1480` bị tiêu hết vào
  reasoning tokens, reply rỗng, `finish_reason=length`; app giờ báo rõ khi hết hạn mức vì suy luận
  và khuyên chọn model không suy luận hoặc giảm số crop.
- **Reply JSON cứng** `{"rows":[{"index":i,"text":"…"}]}`: đúng số dòng, đúng thứ tự, chỉ hai
  field, ≤ 1024 ký tự, không ký tự điều khiển; cho phép bọc ```. Sai schema, bị cắt hoặc lỗi mạng
  → **thử lại đúng một lần** cho tờ đó rồi dừng job bằng `OcrError` đã lọc (không mang HTTP body).
  Ngân sách request mặc định 400 (`--max-requests`), đếm cả lượt lỗi.
- **Dòng rỗng** (`""`) → `drop_empty`: cue bị loại, đếm `dropped_empty_cues`; vùng ngắn hơn 100 ms
  bị bỏ trước khi gửi (`dropped_short_cues`). Khi xuất, `document_to_subtitles` **gộp cue liên tiếp
  cùng chữ cách ≤ 150 ms** thành một segment (`merged_cue_id`, metadata giữ đủ observation); bảng
  trong cửa sổ OCR vẫn hiện cue thô.
- **Identity**: `OcrConfig.vision = VisionProfile(id, model, rows, width, crops, prompt_sha256)`
  (omit_none, document cũ không đổi byte/ID); `profile_sha256 = digest(profile)`,
  `bridge_sha256 = digest([sheet version, prompt hash])`, không `profile_snapshot`;
  `read_revision = digest([profile_sha256, vision])` nên cache đĩa/RAM tách theo model + prompt +
  cỡ tờ. `OcrMetadata`, `_collect_issues`, `validate_resume` chấp nhận document vision không có
  snapshot. Resume so khớp cue cuối bằng đúng tập crop đã chọn (`select_candidates`).
- **Pipeline batch**: `OcrPipeline` nhận `BatchRecognizer` (`rows_per_request`, `recognize_many`),
  đệm vùng tới đủ hàng, tra cache trước, gộp crop trùng SHA trong cùng lượt, rồi gán kết quả.
  `_emit` áp dụng drop_empty; checkpoint chỉ gồm cue đã đọc xong.
- **CLI**: `ocr --vision-llm [--vision-model M] [--vision-rows N] [--vision-width W]
  [--vision-crops 1|2] [--vision-sheets-dir DIR] [--tracking strokes|edges]`; credentials/model/
  timeout từ config hợp nhất (`llm.*`), `--max-requests` làm ngân sách. `ocr-resume` tự nhận
  checkpoint vision, từ chối `--vision-model` khác. `--tracking strokes` cũng dùng được cho CPU.
- **GUI**: ô **Đọc chữ bằng AI qua API LLM trong Cài đặt** (cfg `OCR/VisionLLM`, mặc định bật) và
  **Số crop mỗi lượt gửi AI** (cfg `OCR/VisionRows`, 16). Bật thì vô hiệu runtime/PaddleOCR-VL/vạch
  chọn/ổn định nhóm; `capture_vision_settings` đọc LLM trên GUI thread rồi `OcrThread.scan_vision`
  gọi `run_vision_ocr`. Mở checkpoint vision tự bật ô; Tiếp tục quét yêu cầu đúng model đã lưu.
- **Riêng tư/log**: chỉ gửi crop, số dòng, ngôn ngữ; `OwnedLLMRequest(log_content=False)` ghi
  metadata/usage/số ảnh, không base64. `--vision-sheets-dir` lưu PNG + reply (không key, không
  path). Context stage `ocr-vision`, không tên file.

## Đo trên video thật (không gọi API)

Clip `BV1GFbk6LEVm-P1-zh.mp4` 107–127 s, ROI `0.05,0.86,0.90,0.12`, endpoint giả để chỉ render tờ:

| Tracker | Vùng / 600 frame | Ghi chú |
| --- | --- | --- |
| `edge-tiles-ocr2-v1` | 16 vùng trong 1 s đầu | nền pan làm tách mỗi 1–3 frame |
| strokes + outline (bỏ) | 217 | nét nền sáng cạnh tối vẫn đổi theo frame |
| strokes 1600 px + band chặt (bỏ) | 314 | mask chi tiết hơn càng nhiễu, 64 s/600 frame |
| **strokes v3 (IoU, settle)** | **24 (18 ≥ 100 ms)** | mọi phụ đề đều thành vùng; 8/18 hàng là cảnh không chữ |
| band + coverage ≥ 35 % (bỏ) | 30 | mất hẳn câu đầu |

Tờ 18 hàng (`.tools/ocr-vision-20261007/evidence/sheets/`): 10 hàng có chữ lớn, rõ (một câu
lặp 5 hàng do cắt cảnh, sẽ gộp khi xuất nếu AI đọc giống nhau); 8 hàng cảnh không chữ sẽ bị AI trả
`""` và loại. Chi phí phụ đó chấp nhận được thay vì siết heuristic làm mất chữ.

## Nghiệm thu

- Source: `tests/test_ocr/test_vision.py` (25 test: profile/identity, sheet, parse, recognizer
  retry/budget/hủy, pipeline batch/dedup/drop, run_vision_ocr round-trip/resume/failure, CLI
  scan/resume/thiếu key, stroke tracker trên nền chuyển động, text_bounds); GUI
  `tests/test_ui/test_ocr.py::test_vision_mode_sends_configured_llm_settings_and_resume_checks_model`;
  hai test GUI cũ bật lại chế độ CPU tường minh. OCR + GUI OCR + CLI **556 pass/7 skipped**;
  Ruff pass, Pyright 0/0, translations in sync. Fixture mới `isolated_ocr_cache` cũng cô lập
  `vision.cache_directory` (lượt chạy đầu đã ghi 2 bản đọc giả vào cache OCR thật của máy dev,
  khóa theo SHA video tổng hợp nên không ảnh hưởng dữ liệu thật).
- Chưa gọi API thật: chất lượng đọc của model, chi phí thực và hành vi gateway với ảnh **chưa
  nghiệm thu**; user kiểm bằng `--vision-sheets-dir` hoặc GUI với video thật.
- Build/EXE/deploy ghi ở phần cuối `status.md` mục 2026-10-07.

## Giới hạn và việc tiếp theo

- Chữ không sáng (phụ đề màu tối, chữ đen nền sáng) không tạo nét → không có cue; dùng
  `--tracking edges` hoặc đường CPU.
- Hàng cảnh không chữ vẫn tốn token; nếu nhiều, giảm ROI hoặc tăng hạn mức cache.
- Ngôn ngữ vẫn cố định `zh` ở prompt; prompt đổi làm đổi identity/cache.
- Chế độ dán vào chat (không key) chưa làm; tờ PNG đã có sẵn qua `--vision-sheets-dir`.
