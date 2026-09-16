# ASR — nghiệm thu GUI và tải model, 2026-09-09

User yêu cầu tiếp tục và chọn **nghiệm thu GUI và tải model**. Phạm vi này mở
lại các gate chuẩn bị model; bản lồng tiếng toàn bài đã chốt vẫn giữ nguyên.
Không chạy lại ASR, dịch, TTS hoặc benchmark corpus. Không commit/push; OCR dừng.

Evidence riêng: `build/gui-download-acceptance-20260909/`.

## Thay đổi từ lỗi đã tái hiện

- Sau hủy, result signals của worker được chủ động bỏ qua để tránh cập nhật
  muộn. Tuy nhiên `LocalASRDialog.done_work()` trước đây vẫn để dòng “Cancelling;
  waiting...” và đặt progress 100% sau khi worker đã dừng. Nay completion của
  worker bị hủy ghi trạng thái cancelled vào đúng stage và đặt progress về 0;
  giữ guard signal và chỉ mở lại controls sau `wait()`.
- Tên file Hub `.incomplete` làm đường dẫn vượt MAX_PATH trên Windows. Download
  vẫn chạy nhưng code đọc dung lượng ném WinError 3, khiến tiến độ MiB đứng yên.
  `_partial_download_bytes()` dùng extended Windows path (gồm UNC) và bỏ qua
  file vừa được downloader finalize. Không đổi revision, payload hoặc HTTP policy.

## Source GUI và HTTP thật

- Mở chính `LocalASRDialog` của source bằng host có AppData/settings/cache riêng;
  thao tác qua Windows Computer Use, không mock worker/installer/model.
  Observer HTTP chỉ ghi method, Range, status, Content-Range/length; không ghi
  URL có chữ ký, headers credential hay response body.
- Qwen 0.6B được chuẩn bị vào runtime mới; tải thật theo pin `5eb144179a02`,
  inventory/hash verified, GUI báo ready. Model cũ của user không bị thay đổi.
- ForcedAligner pin `c7cbfc2048c4` tải riêng cho stage timing. Observer giới hạn
  tốc độ đọc response để có thời gian hủy bằng GUI; HTTP/data vẫn từ Hub thật.
- Sau lần hủy đầu, giữ **293.601.280 byte (280 MiB)**. Lần tiếp tục trả HTTP
  **206** với `Range: bytes=293601280-` và
  `Content-Range: bytes 293601280-1835544543/1835544544`.
- Bấm hủy tiếp trên source đã sửa trạng thái: giữ **660.602.880 byte (630 MiB)**;
  GUI báo `Local operation cancelled.`, progress 0%, controls mở lại, không còn
  child. Host đóng exit 0; settings thật, media cuối, pyproject/uv.lock giữ hash
  và mtime. `session-r2/host-result.json`, `session-r3/host-result.json` ghi riêng.
- Host ghi bằng chứng đầu tiên kết thúc sớm trong bước dependency, trước tải
  model; giữ output lỗi. Bản r2 chịu được Windows sharing conflict khi reader
  đang mở live-state; dùng lại staging/dependency, không xóa để cài lại.

## Validation

- Test hồi quy trạng thái hủy fail trên code cũ, pass sau sửa.
- **150 passed**, gồm UI Local ASR, installer/download và toàn CLI; 2 warning
  môi trường/fixture. Test mới tạo file partial có đường dẫn >260 ký tự thật.
- Ruff app/tests pass; pyright với interpreter project đã có: **0 error/0 warning**;
  translations in sync. Lần pyright không chỉ interpreter tìm `.venv` ở worktree
  không tồn tại, báo thiếu import; không tính lượt đó là gate code hợp lệ.

## EXE

Artifact: nguyên thư mục `dist/VideoCaptioner-ASR-GUIResume-20260909/`.
Không chép riêng EXE; runtime/model nghiệm thu nằm riêng trong evidence.

1. PyInstaller **exit 0 / 184,906 s**, **6 WARNING / 0 ERROR**. Warning quen
   thuộc: js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit. Có thêm
   SyntaxWarning từ dependency được scan; không phải exception startup.
2. EXE **31.224.100 byte**, timestamp local **2026-09-09 17:32:44**;
   SHA-256 `6187f8789f577c1def90cd596eda3dc2a817b03883337397046e70cda91a3b90`.
   `build-result.json` giữ kết quả và log riêng. UI hiển thị version fallback
   `0.0.0-dev` của checkout; đây là artifact nghiệm thu, chưa là release.
3. Mở **chính EXE**, vào Cài đặt → Qwen → Quản lý mô hình → chọn thư mục
   nghiệm thu và ForcedAligner. GUI sống **412,938 s**, đóng bằng nút X,
   **exit 0**, không còn child. Settings thật, media cuối, pyproject/uv.lock
   giữ hash/mtime theo `exe-result.json`.
4. Frozen GUI tiếp tục file 630 MiB; progress hiển thị **862 → 902 MiB** và
   tăng đúng theo bytes thật. Bấm hủy lúc HTTP đang tải giữ **1.405.091.840 byte
   (1340 MiB)**, báo cancelled/0%, controls mở lại, không child sót. Bấm
   Prepare/resume lần nữa hoàn tất cùng file, verify/hash pass; **9 file /
   1.840.070.940 byte** của ForcedAligner. Probe health nạp model thành công
   rồi giải phóng worker; **không inference**. Bấm Prepare/resume sau ready
   chỉ verify/reuse, không sinh process download hoặc model mới.

EXE chạy recipe/helper bundle nguyên trạng, không observer hay throttle HTTP.
`exe-events.jsonl` theo dõi dung lượng partial tăng từ đúng offset đang giữ
đến finalize, marker ready và toàn bộ child do EXE sở hữu. Range/206 được ghi
trực tiếp ở source; không giả có trace HTTP headers riêng cho frozen.

Qwen 0.6B tải source: **9 file / 1.880.618.159 byte**, inventory/hash pass;
không nạp thử lại model nhận dạng trong lượt này. Health mới của lượt này là
ForcedAligner. Runtime là venv tại máy, chưa là gói portable/cài máy khác.

Full workflow video → dịch → lồng tiếng qua GUI vẫn là phạm vi nghiệm thu
riêng; GUI downloader OmniVoice, model gated/người nói, disk-full và mất mạng
thật chưa được suy thành pass từ các test offline. Không build hoặc inference
thêm để mở các phạm vi đó trong lượt này.

## File thay đổi trong lượt này

- `videocaptioner/core/asr/local/prepare.py`
- `videocaptioner/ui/components/local_asr_cards.py`
- `tests/test_asr/test_local_prepare.py`
- `tests/test_ui/test_local_asr.py`
- `docs/dev/asr-gui-download-2026-09.md`
- `docs/dev/asr-completion-next-session-prompt.md`
- `docs/plans/asr-completion-2026-09.md`
- `status.md`

Giữ mọi thay đổi chưa commit có sẵn trên `b102ae9`. Không sửa spec, dependency,
bridge, bản dịch hoặc media trong lượt này. Evidence/build không đưa vào Git.
