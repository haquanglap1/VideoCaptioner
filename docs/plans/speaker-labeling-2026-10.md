# Kế hoạch gán nhãn người nói tự động — 2026-10-07

Yêu cầu user (2026-10-07): nhãn thô dùng **Qwen local + Community-1** (Soniox/Scribe chỉ dự phòng
vì tốn phí); app tự gán tên nhân vật, càng ít thao tác tay càng tốt, chỉ hỏi khi thật sự thiếu ngữ
cảnh. Mục tiêu thực tế: đúng khoảng 90 % cue, phần còn lại vào hàng đợi review nhỏ.

## Trạng thái

- 2026-10-07: **lớp 1 đã làm** (`core/asr/local/speaker_naming.py`, prompt `asr/speaker_naming.md`, CLI
  `local-diarize --name-speakers`, card Settings + bảng review trong tab phụ đề). Contract và giới hạn:
  [speaker-naming-2026-10.md](../dev/speaker-naming-2026-10.md). Chưa gọi API thật; lớp 2–4 chưa làm.

## Hiện trạng (đã có)

- `--local-diarize`: pyannote Community-1 (`core/asr/local/diarization.py`) gom cụm ẩn danh
  SPEAKER_xx theo cửa sổ 10 s, giao vào cue với trạng thái assigned/ambiguous/overlap/unknown.
- Ngữ cảnh xưng hô S4 (`More → Ngữ cảnh xưng hô`): nhân vật/người nghe/quy tắc dịch, chưa định
  tuyến giọng TTS.
- Dubbing planner giữ ranh giới người nói (`dialogue-speaker-boundaries-2026-09.md`) nhưng một job
  OmniVoice vẫn một reference.

## Bốn lớp, làm theo thứ tự

1. **Đặt tên cụm bằng LLM (một request/tập).** Gửi toàn bộ hội thoại đã gắn SPEAKER_xx (và tên
   trong OCR nếu có) cho LLM; trả JSON mỗi cụm: `name`, `role`, `gender`, `age_group`, `confidence`,
   `evidence_cue_ids`. Lưu vào `ASRMetadata` speaker map và đồng bộ với Ngữ cảnh xưng hô. Không hỏi
   user khi `confidence ≥ 0.8`; dưới ngưỡng hiện một bảng "cụm → tên đề xuất" cho user xác nhận.
   Phạm vi: `core/asr/local/speaker_naming.py` (Qt-independent), prompt `.md` trong
   `core/prompts/`, CLI `local-diarize --name-speakers`, GUI bật mặc định khi có LLM.
2. **Hồ sơ nhân vật bền theo bộ phim.** Mỗi cụm đã đặt tên lưu embedding trung bình (ECAPA/
   pyannote embedding chạy CPU, kiểm tra model có sẵn trong runtime Community-1 trước khi thêm
   dependency), WAV mẫu sạch nhất 5–10 s (tách vocals nếu bật) và tên. Tập sau: cụm mới so cosine
   với hồ sơ (ngưỡng ~0,6; margin ≥ 0,1 so với hồ sơ gần nhì); khớp thì gán tên, không khớp thì quay
   lại lớp 1. Lưu `AppData/speakers/<series>/profile.json` + WAV; không đưa vào Git.
3. **Sửa ranh giới và chấm điểm.** Cue có hai người → tách tại điểm đổi speaker theo word
   timestamp; cue < 1 s thừa kế speaker của cue liền kề cùng lượt thoại nếu embedding thiếu dữ
   liệu; giới tính từ audio làm chốt chặn. Mỗi cue có `speaker_confidence`; chỉ cue dưới ngưỡng vào
   review ASR hiện có.
4. **Định tuyến giọng OmniVoice theo vai.** Hồ sơ → reference WAV; planner đã giữ ranh giới người
   nói nên chỉ cần map speaker → voice/reference trong `core/dubbing/presets.py` và engine. Mẫu
   clone sư phụ/đệ tử 2026-09-16 đang gán tay trở thành tự động.

Tín hiệu bổ trợ sau cùng: OCR tên nhân vật nếu phụ đề cứng có, LLM ngữ cảnh cho cue nhập nhằng.
Nhận diện người đang mấp máy môi trên hình để sau, vì là model local nặng.

## Gate đề xuất

- Offline: fixture cụm/hội thoại tổng hợp cho lớp 1 (JSON hợp lệ, ngưỡng confidence, không gửi
  path/audio); embedding/cosine với WAV tổng hợp cho lớp 2; planner/engine cho lớp 4.
- Thật: một tập BV1GFbk6LEVm với Qwen + Community-1, so nhãn tự động với gán tay trước đây; nghe
  mẫu dubbing hai giọng. Chưa coi diarization hoặc xưng hô là nghiệm thu nếu chưa có người đối
  chiếu.
