# Đặt tên người nói bằng LLM (lớp 1 của gán nhãn người nói) — 2026-10-07

Lớp 1 trong [kế hoạch gán nhãn người nói](../plans/speaker-labeling-2026-10.md): sau khi Community-1
(`--local-diarize`) hoặc Soniox/Scribe gắn cụm ẩn danh `SPEAKER_xx`, app gửi **một request** tới LLM đang
cấu hình để đặt tên, vai, giới tính và độ tuổi cho từng cụm. Tên đủ tin cậy được áp dụng tự động; tên
thấp hơn ngưỡng chờ user trong một bảng "cụm → tên đề xuất". Dùng cho mọi video (Bilibili, YouTube), không
riêng PV 清宵. Đây là contract/code đã kiểm thử offline bằng request giả; **chưa gọi API thật** và chưa đối
chiếu với gán tay trên tập BV1GFbk6LEVm.

## Hành vi

- **Cụm** (`core/asr/local/speaker_naming.py`, Qt-independent): một cụm là một `metadata.speaker_id`
  có `speaker` được gán (status `assigned`). Cue ambiguous/overlap/unknown hiện nhãn `?` trong transcript;
  cue có `speaker_override` của user được coi là đã đặt tên và chỉ là ngữ cảnh. Nhãn hiển thị lấy từ
  `metadata.speaker` (`SPEAKER_00`; nhãn số của Soniox/Scribe thành `SPEAKER_1`), trùng nhãn giữa hai
  scope thì thêm `#2`. Tối đa 40 cụm một request.
- **Request**: system prompt `core/prompts/asr/speaker_naming.md` (bundle cùng thư mục prompts trong
  EXE); user message gồm khối nền `compose_context_notes` (sidecar `<video>.context.json` + ô *Ngữ cảnh
  bộ phim* trong Settings), `CLUSTERS` (nhãn + số câu) và `TRANSCRIPT` dạng `số | nhãn | chữ`. Transcript
  quá 20.000 ký tự được lấy mẫu đầu/giữa/cuối theo ranh giới cue, thêm tối đa 3 câu của cụm bị thiếu, đánh
  dấu `...`. Không gửi đường dẫn, audio, API key hay cue ID; chỉ chữ, nhãn ẩn danh và số đếm.
  `max_completion_tokens = min(12000, 2000 + 200·số cụm)` để model suy luận còn chỗ trả JSON.
- **Reply JSON cứng**: `{"speakers":[{"label","name","role","gender","age_group","confidence",
  "evidence_cue_ids"}]}`. Validate: đúng số cụm theo thứ tự `CLUSTERS`, đúng tập khóa, `gender` ∈
  male/female/unknown, `age_group` ∈ child/teen/adult/senior/unknown, `confidence` là số 0..1 (không nhận
  bool/chuỗi), `evidence_cue_ids` là số dòng có trong transcript (map về cue ID thật, ≤ 20), tên ≤ 60 ký
  tự không có ký tự điều khiển. Reply sai → thử lại **một lần**; lỗi provider/timeout/hủy (RuntimeError
  từ `OwnedLLMRequest`) không thử lại. Model hết hạn mức vì reasoning ẩn báo rõ như OCR vision.
- **Lưu kết quả**: khối tài liệu `speaker_naming` (`speaker-naming-v1`: `model`, `prompt_sha256`,
  `cue_count`, `sampled`, `profiles[]` với `speaker_id`, `label`, `name`, `role`, `gender`, `age_group`,
  `confidence`, `evidence_cue_ids`, `status`) trong JSON `asr-native-v1` (`core/asr/metadata.py`:
  `SpeakerProfile`, `SpeakerNaming`). Cue giữ nguyên `speaker`/`SpeakerAssociation`; SRT/ASS/TXT không
  chèn tên.
- **Đồng bộ S4** (`apply_naming`): mỗi cụm có tên tạo `Character` + `SpeakerMapping` với ID tất định
  `ai-char-/ai-map-<sha256(speaker_id)[:12]>`, evidence `source="text"`. `status="confirmed"` khi
  `confidence ≥ 0,8`, có evidence do model dẫn và tên không trùng cụm khác; ngược lại `proposed` (S4 chỉ
  áp dụng confirmed/locked nên đề xuất không ảnh hưởng bản dịch cho tới khi user xác nhận). Tên rỗng →
  không tạo Character, profile ở trạng thái `proposed` để user điền. Tên trùng với Character đã có (kể cả
  do user tạo) thì map vào Character đó thay vì tạo mới. Mapping do user tạo hoặc đã confirmed/locked cho
  cùng `speaker_id` **không bị thay**; chạy lại chỉ thay đề xuất máy của lần trước. Evidence rỗng được
  thay bằng 3 cue đầu của cụm để thỏa ràng buộc "text proposals require cue evidence".
- **Review của user** (`apply_decisions`): tên user nhập → `Character`/`SpeakerMapping` evidence
  `source="user", status="confirmed"`, profile `confirmed`; để trống → profile `rejected`, không có
  Character. Trong GUI đi qua `ApplySpeakerNamesCommand` (`core/editor/commands.py`) trên stack ngữ cảnh
  của tab phụ đề nên có undo/redo.

## GUI

- **Cài đặt → Nhận dạng**: card **Đặt tên người nói bằng AI (LLM)** (`cfg.local_asr_name_speakers`, mặc
  định bật) cạnh *Phân biệt người nói tại máy*; hiện với Qwen local và Whisper API. Chỉ có hiệu lực khi
  diarization bật và dịch vụ LLM đã có key/model; thiếu LLM thì job báo "Speaker naming skipped" và giữ
  nhãn ẩn danh. `TaskFactory.create_transcribe_task` chụp credentials/model/timeout của dịch vụ LLM đang
  chọn và khối nền của video (`speaker_naming_settings`), không ghi vào `os.environ`.
- **Tab phụ đề**: kéo thả hoặc mở JSON (tab này nhận `.json` từ 2026-10-07; trước đó chỉ srt/ass/vtt). JSON có
  đề xuất chưa xác nhận → InfoBar "Cần xác nhận tên người nói". Bấm Bắt đầu với *Phân đoạn* đang bật: pipeline
  giữ nguyên câu và báo "Giữ nguyên câu: tài liệu đã có ngữ cảnh xưng hô" thay vì lỗi `Re-segmentation would
  change context associations`, vì Character/Mapping đang trỏ vào cue hiện tại. **More → Tên
  người nói (AI)** mở bảng (`ui/components/speaker_naming_dialog.py`): cụm, số câu, tên (sửa được), vai,
  giới tính, tuổi, độ tin cậy, trạng thái, câu mẫu; hàng `proposed` xếp trước. **Áp dụng tên** ghi quyết
  định; **Để sau** giữ nguyên. Lưu JSON để giữ map; Video Editor handoff/JSON export mang theo khối
  `speaker_naming`.

## CLI

```powershell
uv run --frozen videocaptioner local-diarize timed.json --audio episode.mp4 -o speakers.json --name-speakers
uv run --frozen videocaptioner local-diarize timed.json --audio episode.mp4 -o speakers.json --name-speakers --series-context notes.txt
uv run --frozen videocaptioner transcribe episode.mp4 --asr qwen-local --language zh --local-diarize --name-speakers -o episode.json
```

`--name-speakers` đọc `llm.api_key/api_base/model/request_timeout` từ config/GUI settings, khối nền từ
`--series-context FILE` (mặc định `translate.series_context`) và sidecar `<audio>.context.json` cạnh file
truyền vào `--audio` (truyền thẳng file video đã tải để có sidecar). Thiếu LLM → exit 2 trước khi nạp model.
Đặt tên lỗi → cảnh báo "Speakers remain anonymous", JSON cụm vẫn được lưu. `local_asr.name_speakers` mặc
định `false` trong CLI; GUI không được mirror sang CLI (như `local_asr.diarize`).

## Nghiệm thu

- Offline: `tests/test_asr/test_speaker_naming.py` (cụm/nhãn, message không có path/key, lấy mẫu,
  18 reply sai bị từ chối, retry một lần, không retry RuntimeError, ngưỡng tự xác nhận, trùng tên/thiếu
  evidence/tên rỗng, giữ quyết định user, chạy lại idempotent, round trip JSON + SRT không đổi, review
  user, hook trong `transcribe()` kể cả khi provider lỗi hoặc thiếu LLM); `tests/test_cli/test_local_asr.py`
  (+4: flag/config, `local-diarize --name-speakers` gửi chữ + nền và lưu map, lỗi provider giữ JSON, thiếu
  LLM dừng sớm); `tests/test_ui/test_speaker_naming.py` (4: card/config snapshot, TaskFactory chỉ chụp
  LLM khi đủ cấu hình, dialog, view áp dụng qua stack + undo/redo + export). Kết quả gate ghi ở `status.md`.
- Thật, 2026-10-07 trên bản E qua CLI `local-diarize --name-speakers` với SRT tiếng Việt đã dịch của
  BV1GFbk6LEVm P1 và model `gpt-6.1-sol`: Community-1 ra 52 cue/2 cụm (40 cue chưa rõ vì cue SRT rất
  ngắn), một request LLM trả JSON hợp lệ ngay lần đầu: `SPEAKER_00 → Thanh Tiêu` (confirmed, 0,80, vai
  "kiếm tu hướng dẫn tu hành"), `SPEAKER_01 → (unknown)` (proposed, vai "vãn bối được tiền bối hướng
  dẫn"). Đúng với nội dung PV; chưa so từng cue với gán tay, chưa đo trên phụ đề tiếng Trung gốc vì
  bước căn thời gian Qwen của tập này dừng ở vùng đệm `嗯。` (xem sửa fallback cùng ngày trong
  `status.md`). Chất lượng trên nhiều tập và chi phí token chưa nghiệm thu.

## Giới hạn và phần chưa làm

- Chưa làm lớp 2 (hồ sơ nhân vật theo bộ phim bằng embedding), lớp 3 (tách cue hai người, chấm điểm
  từng cue), lớp 4 (định tuyến giọng OmniVoice theo vai). `gender`/`age_group` đã lưu để lớp 4 dùng.
- Không cache kết quả đặt tên: mỗi lần `local-diarize --name-speakers` là một request.
- Project Video Editor (`editor-project-v1`) không giữ khối `speaker_naming`; Character/Mapping trong
  `conversation_context` vẫn còn nên tên không mất, chỉ mất bảng review.
- Soniox/Scribe: cụm lấy từ metadata native nên cũng đặt tên được, nhưng là đường dự phòng vì tốn phí.
- Tên chỉ suy từ chữ và khối nền; model không nghe audio nên giới tính/tuổi chỉ từ cách xưng hô hoặc nền.
