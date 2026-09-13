# Prompt phiên tiếp theo — OCR xuất thẳng và trường hợp video 2

Tiếp tục worktree **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**.
Tìm bằng `git worktree list`, không làm ở checkout master. User yêu cầu
commit/push snapshot bỏ review và chuẩn bị prompt này. Đọc `git log -1`,
`git status --short --branch` và đối chiếu `origin/codex/asr-s3-native`.
Baseline trước snapshot là **2ed7ae1**, không phải HEAD cần quay về.
Không reset/merge hoặc bỏ thay đổi mới. Quyền submit của phiên bàn giao
không tự cấp commit/push/tag/release hoặc API cho công việc tiếp theo.

## Yêu cầu user đang có hiệu lực

**Không cần review OCR và không cần bản chữ gốc để tiếp tục.** User đã nói
rõ bỏ bước này: quét xong có thể xuất phụ đề hoặc mở bảng phụ đề/dịch ngay.
Không yêu cầu user tìm SRT, chấm từng câu Trung hoặc bổ sung nhãn độc lập
như điều kiện chặn phát triển/sử dụng. Các chỉ dẫn cũ đòi nhãn và khóa export
vì chưa duyệt đã bị yêu cầu này thay thế.

Vẫn giữ raw/candidates/PTS/IDs/source và các quyết định cũ. Không tự ghi một
quyết định reviewed/accepted, bù chữ/dấu hoặc chuẩn hóa raw để giả chữ đúng.
Scan dở, thiếu chữ, sai nguồn/profile hoặc timing không hợp lệ vẫn là lỗi
xử lý; không xuất phần thiếu rồi báo toàn bộ thành công. Bỏ bước duyệt là
thay đổi luồng sử dụng, không phải bằng chứng nhận dạng chính xác hơn.

## Đọc trước khi tiếp tục

Đọc AGENTS.md, README.md, mục mới nhất status.md, sau đó:

1. `docs/dev/ocr-direct-export-2026-09.md`.
2. Phần cập nhật mới nhất của `docs/plans/video-subtitle-ocr-integration-plan.md`.
3. Evidence local `build/ocr-pilot-20260910/ocr-direct-export-32/`:
   `binary-plan.json`, `binary-receipt.json`, `video-inputs.json`,
   `video-2.ocr.json`, `video-2-receipt.json`, `video-2.stdout.log` và
   `video-2.stderr.log`.

Hai video do user chỉ định được ánh xạ thành video 1/2 trong
`video-inputs.json`; lấy đường dẫn và SHA ở đó, không đoán từ tên video,
không quét toàn máy hoặc tự mở corpus khác. Nội dung/path riêng, ảnh và raw
chỉ ở evidence local, không đưa vào Git hoặc gửi ra ngoài.

## Việc ưu tiên tiếp theo

1. **Chẩn đoán trường hợp video 2 từ dữ liệu đã lưu trước.** Đoạn dự kiến
   14–16 s, ROI `0.28,0.90,0.44,0.065`; mới 12 frame đã có 5 cue,
   8 worker request/8 det/73 rec. Harness đặt trần 8 nên lần gọi thứ 9 bị
   chặn trước gửi worker: checkpoint `complete=false`, exit5, không subtitle.
   `fresh_calls=9` không phải 9 worker request. Giữ assertion fail/log/raw.
2. **Trần 8 là giới hạn riêng của lượt smoke**, không phải cap do user áp
   lâu dài, giới hạn engine hay mặc định CLI (1000). Không coi nó là blocker
   cần user cấp lại quyền. Cũng không chỉ tăng số rồi gọi việc nhận dạng
   nhiều vùng/cue rất ngắn là đã sửa: đối chiếu ROI/PTS, bbox/line và tracking
   để biết vùng đang lấy có lẫn chữ giao diện/chuyển cảnh hoặc nhóm bị vỡ.
   Hiện chưa xác nhận nguyên nhân; không gán lỗi model/decoder chỉ từ số rec.
3. Nếu cần lượt local tiếp theo để kiểm giả thuyết cụ thể, chốt phạm vi,
   điểm đo và giới hạn phù hợp trước khi chạy; dùng runtime hiện có, ưu tiên
   checkpoint/cache và không ghi đè lượt lỗi. Không quét lại toàn hai video,
   chạy sweep ROI/preprocessing hoặc chỉ rerun để đổi exit5 thành exit0.
   Chạy đầy đủ video khi có cơ sở về luồng/chi phí và phạm vi nhiệm vụ yêu cầu.
4. Chỉ sửa khi có hành vi cần đổi hoặc lỗi cụ thể; đặt regression gần chỗ sửa,
   giữ nguồn/raw/IDs/schema và phân biệt lỗi xử lý với thông tin nhận dạng.
   Làm liên tục phần đủ thông tin, không mở lại yêu cầu review/ground truth.
   Dịch/TTS/vision và xác nhận độ chính xác sản phẩm vẫn chưa được nghiệm thu.

Nếu user giao hướng khác, theo yêu cầu mới. Không tự mở toàn roadmap,
vision GUI, downloader/update hoặc checkpoint tự động.

## Những phần đã hoàn tất

- GUI bỏ nút duyệt chữ/giờ, ô lý do và cột cần duyệt. Bảng 3 cột, **Xuất
  phụ đề** / **Mở bảng phụ đề / dịch** dùng được sau scan đầy đủ hợp lệ.
  **Chi tiết bản đọc** thu gọn; chỉnh sửa ở bảng phụ đề hoặc Video Editor.
- CLI `ocr ... -o captions.srt|json` không cần file review.
  `--checkpoint` tùy chọn, `--review` là alias tương thích.
  `ocr-export saved.ocr.json --source VIDEO -o captions.srt` xuất tại máy
  không inference; `ocr-review` là alias, các tùy chọn sửa cũ vẫn dùng được.
- `export_issues` tách lỗi chặn xuất khỏi `pending_issues` chẩn đoán.
  Metadata subtitle/editor nhận observations chưa duyệt, giữ lineage qua
  JSON/dịch/editor. Schema `ocr-document-v1` / `editor-project-v1` giữ nguyên.
  Binary cũ có thể từ chối JSON chứa observations chưa duyệt.
- Full offline **1.853 pass / 5 skip / 51 deselected**, 193,18 s, exit0;
  Ruff/Pyright0/0, translations sync. 372 scoped pass trước full. Giữ log
  regression trước sửa4fail/1pass và lượt assertion test cũ81pass/1fail.
- Binary export checkpoint tổng hợp cũ3cue exit0; partial vẫn exit5.
  Video 1 đoạn13–15s:60frame/1cue/3request/3det/3rec, JSON và SRT exit0.
  Hai scan video tổng11request/11det/76rec/0cls/0API; video2 vẫn chưa xong.
- Native chính EXE tại dist395,156s exit0/0child/không traceback; mở3cue cũ,
  xuất/handoff thẳng, JSON khớp CLI. Watcher100ms không thấy remote connection.
  Backup AppData trước mở, khôi phục5cache từ backup thực,6file khớp SHA.
  Lỗi Computer Use element77 hai lần đã vượt qua bằng bàn phím/tọa độ mới.

## Artifact phải giữ

`dist/VideoCaptioner-OCR6-Medium-20260911/` đã được cập nhật riêng app;
models/AppData/work-dir giữ nguyên. Build một spec exit0/6warning/0error,
app590file/529.736.078byte, không copy models49GB.

EXE **31.429.660 byte**, **2026-09-13 02:00:19+07**, SHA-256:
`58548169a739abcfe467c7ccc2250f522964ca2f5dbec27081d4402c2877593c`.

App trước nằm trong `ocr-direct-export-32/rollback-app/`, EXE SHA
`34a1e970fcb643b3435ef09b09f73df9fc26ee8831c8b70e1101e643284338f1`.
Script `ocr-direct-export-32/Update-App.ps1 -Action Rollback` trả riêng
EXE/`_internal` khi app đã đóng; nhánh Rollback chưa chạy. Giữ mọi backup.

## Giới hạn còn hiệu lực

- **0 API mới**; cap vision14 đã hết. Không đọc Api.txt/.env/cookies, gọi
  vision/dịch/TTS, tải model, `uv sync`, cài/nâng dependency hoặc Python3.13.
- Host `../VideoCaptioner/.venv/Scripts/python.exe` 3.12.13; Pyright dùng
  `--venvpath ../VideoCaptioner`. Giữ worker `-I -B`, `child_environment()`,
  contextvars helpers, test cô lập settings/cache/logger và `QThread.wait()`.
- Không chạy lại full suite/build/native smoke/cache/resume đã pass chỉ
  lấy số mới. Nếu sửa code thì chạy kiểm tra tương ứng; source pass không
  thay binary gate. Build một spec, stage riêng, không đè toàn bộ gói hoặc
  chép lại models49GB; backup trước khi mở GUI dùng dữ liệu thật.
- Không chạy lại audit23crop,16fixture dấu câu, CTC hoặc width×2; dừng các
  hướng này. Kết quả chất lượng cũ và bất định Unicode giữ nguyên, không
  biến tham chiếu agent thành nhãn chuẩn hoặc suy bỏ review là chữ đúng hơn.
- Không xóa/stage `ffcachePuSHPB`, đụng media/raw/evidence/settings/model hoặc
  gỡ junction evidence25 từng bị auto-review chặn bằng công cụ khác.
- Hủy → **Lưu dữ liệu OCR** để resume; chưa tự lưu khi crash/kill.
  Bàn giao đúng file/gate/giới hạn, không gọi toàn bộ hai video hoặc roadmap
  hoàn tất khi chưa có bằng chứng.
