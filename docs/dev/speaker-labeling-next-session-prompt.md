# Prompt cho phiên tiếp theo: gán nhãn người nói không dùng Qwen nhận dạng

Dán nguyên đoạn dưới vào phiên Claude Code mới trong repo này.

```text
Đọc README.md, mục mới nhất của status.md, docs/plans/speaker-labeling-2026-10.md,
docs/dev/speaker-naming-2026-10.md và docs/dev/ocr-vision-llm-2026-10.md.

Quyết định user (2026-10-07, cuối ngày): Qwen3-ASR nhận dạng giọng kém hơn Whisper trên video thật,
nên BỎ Qwen speech-to-text khỏi luồng gán nhãn người nói. Nguồn chữ từ nay:
- cần chính xác cao: OCR phụ đề cứng qua vision LLM (`ocr --vision-llm`, GUI OCR), hoặc
- Whisper (Whisper API / Faster-Whisper) khi video không có phụ đề cứng.
Nguồn tên nhân vật: ngữ cảnh do user đưa (ô Ngữ cảnh bộ phim, Ngữ cảnh xưng hô) và metadata video
Bilibili/YouTube (sidecar `<video>.context.json`). Cụm người nói vẫn lấy từ Community-1 trên audio
gốc; Soniox/Scribe chỉ dự phòng vì tốn phí. Lớp 1 (đặt tên cụm bằng LLM) đã xong và đã nghiệm thu
một request thật; không làm lại.

Mục tiêu phiên này:
1. Kiểm tra và sửa cho `local-diarize --name-speakers` chạy được trên JSON OCR (`captions.ocr.json`,
   có `ocr_metadata`/`visual_source`) và trên SRT/JSON Whisper với audio gốc: regroup cue trong
   `assemble_diarized_cues`/`native_cues` không được phá OCR metadata hay visual identity; nếu không
   gộp được thì dùng `associate` giữ nguyên cue. Test offline với fixture OCR tổng hợp.
2. GUI: một hành động "Gán người nói và đặt tên" trong tab phụ đề (More) cho tài liệu đang mở, chạy
   trong QThread: chọn/nhận audio gốc (video của task nếu có), Community-1 + đặt tên LLM, rồi nạp lại
   bảng và mở bảng Tên người nói (AI) nếu có đề xuất. Không bắt user ra CLI. Tôn trọng cue đã có
   speaker/context (guard `validate_source`).
3. Cho phép `--local-diarize` với Faster-Whisper local (hiện chỉ Qwen local và Whisper API), vì
   Whisper là engine nhận dạng mặc định của user; giữ luật một scope/một job, không nối nhãn chunk.
4. Lớp 2 nếu còn thời gian: hồ sơ nhân vật theo bộ phim (embedding Community-1/ECAPA, WAV mẫu, tên)
   trong `AppData/speakers/<series>/`, so cosine để tự gán tên cho tập sau; thiếu khớp thì quay lại
   lớp 1. Không đưa WAV/embedding vào Git.

Không làm: cải thiện Qwen nhận dạng, tách cue hai người (lớp 3), định tuyến giọng OmniVoice (lớp 4).
Ghi rõ phần chưa làm trong status.md.

Quy trình bàn giao như các phiên trước: gate ruff/pyright/pytest liên quan (chạy test_dubbing/
test_auto_timing.py riêng vì có thể kẹt ffmpeg), build nhẹ (không VC_TEST_MODELS_DIR), chép EXE +
_internal vào E:\Game\Translate video qua script deploy có mkdir + kiểm hash trước/sau (mẫu
.tools/speaker-naming-20261007/deploy2.py), xóa dist sau deploy, cập nhật status.md, commit và push
khi user yêu cầu. Bản E đang mở thì không chép; hỏi user đóng app.
```
