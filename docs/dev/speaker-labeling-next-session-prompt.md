# Prompt cho phiên tiếp theo: gán nhãn người nói tự động

Dán nguyên đoạn dưới vào phiên Claude Code mới trong repo này.

```text
Đọc README.md, mục mới nhất của status.md, docs/plans/speaker-labeling-2026-10.md và
docs/dev/series-context-2026-10.md. Mục tiêu phiên này là lớp 1 của kế hoạch gán nhãn người nói:
đặt tên cụm SPEAKER_xx bằng LLM, tự động, chỉ hỏi user khi độ tin cậy thấp.

Yêu cầu user (2026-10-07): nhãn thô dùng Qwen local + Community-1 (`--local-diarize`), Soniox/Scribe
chỉ dự phòng vì tốn phí; càng ít thao tác tay càng tốt; phải dùng được cho mọi video (Bilibili,
YouTube), không riêng PV 清宵.

Phạm vi:
1. `core/asr/local/speaker_naming.py` (Qt-independent): nhận ASRData có speaker ẩn danh, gửi một request
   LLM với toàn bộ hội thoại đã gắn nhãn cụm (sample đầu/giữa/cuối nếu dài), kèm khối nền
   `compose_context_notes` (sidecar video + Ngữ cảnh bộ phim trong Settings). Reply JSON cứng mỗi cụm:
   name, role, gender, age_group, confidence (0..1), evidence_cue_ids. Validate chặt, không retry vô hạn,
   không gửi path/audio/key. Prompt .md đặt trong core/prompts/ (phải có trong EXE).
2. Lưu kết quả vào metadata speaker hiện có (xem core/asr/metadata.py, SpeakerAssociation) và đồng bộ
   với Ngữ cảnh xưng hô S4 (core/translate/conversation.py) bằng Character + SpeakerMapping có
   evidence source="text", status "proposed"; cụm confidence >= 0.8 tự xác nhận, thấp hơn hiện bảng
   "cụm -> tên đề xuất" trong GUI review ASR để user sửa.
3. CLI `local-diarize --name-speakers`, GUI bật mặc định khi có LLM (ô trong Settings), SRT không chèn
   tên; JSON giữ map.
4. Test offline với fixture cụm/hội thoại tổng hợp và request giả; không gọi API thật.

Không làm trong phiên này: hồ sơ nhân vật theo series bằng embedding (lớp 2), tách cue hai người
(lớp 3), định tuyến giọng OmniVoice theo vai (lớp 4). Ghi rõ phần chưa làm trong status.md.

Quy trình bàn giao: gate ruff/pyright/pytest liên quan, build nhẹ (không VC_TEST_MODELS_DIR), chép
EXE + _internal vào E:\Game\Translate video qua script deploy có backup (xem .tools/ocr-vision-fix-20261007/
làm mẫu), xóa dist sau deploy, cập nhật status.md, commit và push khi user yêu cầu.
```
