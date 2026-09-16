# Hoàn thiện ASR/OmniVoice theo session — 2026-09-09

Yêu cầu hiện tại: hoàn thành phần còn lại của [plan ASR](asr-completion-2026-09.md),
chia thành session nhỏ, sau đó commit và push `origin/codex/asr-s3-native`.
Quyền commit/push mới thay các ghi chú chưa có quyền trong lịch sử bàn giao.
Không merge master, tạo tag/release hoặc đưa artifact/media/model vào Git.

Nền bắt đầu là `f510846` cộng sửa handoff SRT hiển thị và tài liệu/test chưa commit.
Giữ các thay đổi đó. Kế thừa nghiệm thu ASR thực dụng, bản dịch 180 cue, video
151 group đã được user chấp nhận và GUI tải Qwen/ForcedAligner đã đo.

| Session | Phạm vi | Gate kết thúc | Trạng thái |
| --- | --- | --- | --- |
| 1 | Core review/resume kế hoạch lời đọc | Giữ wording/cue/group; kiểm tra nguồn và provider; cache phần không đổi; từ chối mismatch | Hoàn tất; 118 test dubbing pass |
| 2 | GUI sửa lời đọc và tiếp tục | Review → sửa một group → resume; giữ SRT hiển thị; báo lỗi/hủy đúng | Hoàn tất code, 35 test hành vi pass gồm cache riêng và layout 950/1050×800 |
| 3 | OmniVoice chuẩn bị model và phục hồi lỗi | GUI hủy/resume; HTTP Range; file lỗi/thiếu disk/mất mạng không thành ready; reuse | Hoàn tất; 27 test pass và model thật reuse |
| 4 | Tích hợp, EXE và Git | Test phù hợp, Ruff/pyright/sync, build/smoke/workflow đóng gói, review diff, commit/push | R6 build/startup/CLI/pipeline GUI pass; track song ngữ đúng thứ tự. Chốt Git theo yêu cầu user |

Mỗi session ghi kết quả và giới hạn riêng; session điều phối cập nhật bảng sau
khi nhận và kiểm tra thay đổi. Các session sửa phạm vi file riêng, dùng checkout
hiện tại và môi trường Python 3.12 đã có, không đồng bộ dependency.

## Phạm vi nghiệm thu

- Review/resume ưu tiên ngay trong tab Lồng tiếng. Không đổi schema editor hoặc
  tự gán lời đọc của một group cho từng cue khi thiếu ánh xạ rõ ràng.
- Test offline dùng nguồn/âm thanh tổng hợp và cache riêng; fixture HTTP loopback
  kiểm tra transport thật nhưng không được gọi là tải remote model thật.
- Sau code thay đổi mới build tên riêng bằng spec duy nhất, giữ onedir cũ. Báo
  build exit/warnings, size/time/hash, GUI startup và workflow thành các gate riêng.
- Không gọi lại ASR/LLM/TTS hoặc render bài giảng đã chốt chỉ để lặp nghiệm thu.
  Không tìm key cũ. Nghiệm thu online đã có được kế thừa đúng phạm vi đã đo.
- Người nói/gated model là bổ sung; quality/RTF corpus khó vẫn giữ kết quả lịch sử.
  Không mở lại benchmark sâu, OCR hoặc sửa bản lồng tiếng được chấp nhận.

## Kết quả

[Báo cáo triển khai và nghiệm thu](../dev/dubbing-review-resume-2026-09.md) ghi
gate source, checkpoint thật 151 WAV và các giới hạn được kế thừa.

User đã cho phép tiếp tục Computer Use sau checkpoint Escape. Đã khởi động
fixture HTTP riêng với receipt mới, giữ các receipt cũ. Các phần đã complete
được dùng lại; chỉ test/build lại vì lỗi bố cục được phát hiện trong GUI thật.

R6 là bản cuối của lượt này. Kiểm tra GUI đã đóng hai khoảng trống bổ sung:
layout tràn ngang và áp layout phụ đề hai lần. Các giới hạn quality/RTF, model
gated/người nói và fresh online inference giữ đúng phạm vi lịch sử phía trên;
không đổi chúng thành pass từ fixture. Commit/push được thực hiện theo yêu cầu
snapshot hiện tại, không merge master hoặc tạo tag/release.
