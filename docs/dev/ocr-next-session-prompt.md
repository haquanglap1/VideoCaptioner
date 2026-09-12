# Prompt phiên tiếp theo — cache và resume OCR đã qua các gate đã giao

Tiếp tục worktree VideoCaptioner-ASR-S3, nhánh codex/asr-s3-native. Tìm bằng
`git worktree list`; đọc HEAD/tracking/Git status thật. User đã yêu cầu submit
snapshot cache/resume; tài liệu này nằm trong cùng commit snapshot đó.
`cb92305` là baseline trước snapshot, không phải HEAD cần quay về. Giữ mọi
diff mới nếu có; không reset/merge. Quyền commit/push của lượt submit không
tự cấp commit/push/tag/release hoặc thêm API cho công việc phiên sau.

Đọc AGENTS.md, README.md, mục mới nhất status.md và:
- docs/dev/ocr-resume-2026-09.md
- docs/dev/ocr-cache-binary-2026-09.md
- docs/plans/video-subtitle-ocr-integration-plan.md

Cache và resume đã có ở source/CLI/GUI/binary. Resume giữ checkpoint v1,
ID/raw/review; đọc kiểm cue cuối bằng PTS/crop SHA, rồi nối phần thiếu.
Fixture dài:2.842cue khớp bản full;6.314frame thay12.316frame, giữ1.386cue cũ.
Review còn mở vẫn khóa export, OCR pending CLI exit5. Full offline cuối
1.839pass/5skip/51deselected; Ruff/Pyright0/0, translations sync. Hai lượt
chuẩn trước AV ở teardown; cleanup widget trong test mới đã thêm, full cuối
exit0, giữ log chẩn đoán; không dùng kết quả đó làm pass dịch vụ online.

User từng nhấn Escape ở smoke sau cài, rồi yêu cầu TIẾP TỤC. Gate đó nay
**đã pass**: EXE trực tiếp trong dist, ô runtime trống tự tìm v6 medium/khớp
SHA; mở màn OCR/resume rồi đóng GUI exit0 sau79,953s, không traceback/child.
Không inference/API; AppData được backup trước chạy,5cache khôi phục từ
backup thực,15hash theo dõi khớp. Evidence mới:
`build/ocr-pilot-20260910/ocr-resume-installed-27/`.
Không coi các dòng “smoke còn thiếu” trong mục lịch sử là trạng thái hiện tại.

Giữ nguyên gói dist/VideoCaptioner-OCR6-Medium-20260911 và models/AppData/work-dir.
EXE31.430.444byte,2026-09-12 11:52:25+07, SHA-256:
34a1e970fcb643b3435ef09b09f73df9fc26ee8831c8b70e1101e643284338f1.
Build trước exit0/6warning/0error; chỉ app được cập nhật, không copy49GB.
Bản cache trước SHAcef53f77…c87ef2 ở evidence26/rollback-app; app trước cache
vẫn ở evidence25. `ocr-resume-26/Update-App.ps1 -Action Rollback` trả riêng
EXE/_internal khi app đã đóng; nhánh Rollback chưa chạy. Giữ các backup.

Junction models evidence25 từng bị auto-review chặn gỡ vẫn giữ; không thử
công cụ/shell khác để né chặn. Evidence26/27 không tạo junction mới. Git còn
untracked ffcachePuSHPB, chưa xóa hoặc đưa vào commit.

0API mới; cap vision14 đã hết. Không đọc Api.txt, gọi vision/dịch/TTS, tải model,
uv sync/cài/nâng dependency/global/Python3.13. Host ../VideoCaptioner/.venv/Scripts/python.exe
3.12.13; Pyright --venvpath ../VideoCaptioner. Dùng runtime v6 hiện có, worker
Python -I -B. Một VideoCaptioner.spec; không đè nguyên gói bằng --noconfirm
hoặc chép thêm49GB. Giữ .env/cookies/Api.txt/media/raw/evidence/log/settings.
Mọi smoke trên dữ liệu thật phải backup trước, vì mở GUI cũng có thể đổi cache.
Test cô lập settings/cache/credentials/logger, QThread.wait(), child_environment
và contextvars helpers hiện có.

Resume vẫn snapshot/hash toàn nguồn và đọc lại một cue tại điểm nối; không
tự lưu khi process crash/kill. GUI phải Hủy → Lưu review trước khi đóng.
Bước tiếp cần theo phần user giao: hiệu chuẩn/giảm review, vision GUI,
downloader/update, checkpoint tự động và corpus rộng còn mở. Không tự cấp
thêm API hoặc dùng tham chiếu agent làm nhãn chuẩn/auto-accept. Không chạy lại
full suite/build/crop sweep đã qua chỉ để có số mới. Không gọi toàn roadmap
OCR hoàn tất; bàn giao đúng file sửa, gate và giới hạn thực tế.
