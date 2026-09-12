# Prompt phiên tiếp theo — OCR sau khi loại giả thuyết width×2

Tiếp tục worktree **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**.
Tìm bằng `git worktree list`, không làm ở checkout master. User đã yêu cầu
submit/push snapshot tài liệu chất lượng và chuẩn bị prompt này. Lấy commit
thực tế bằng `git log -1`, `git status --short --branch` và đối chiếu tracking
`origin/codex/asr-s3-native`; không reset/merge hoặc bỏ thay đổi mới.

**8b6bb8cc8582c8a81708d0ae13bc7f620ea9a993** là baseline code cache/resume
trước snapshot tài liệu này, không phải HEAD cần quay về. Các biên bản cũ
nói “chưa commit/push”, “chưa chạy fixture” hoặc “chưa thử width×2” mô tả
thời điểm trước snapshot; đọc trạng thái mới nhất bên dưới. Quyền submit
của phiên bàn giao không tự cấp commit/push/tag/release hoặc API cho việc mới.

## Đọc trước khi tiếp tục

Đọc AGENTS.md, README.md, mục mới nhất status.md và các tài liệu sau theo
thứ tự; không cần nạp lại toàn bộ lịch sử OCR:

- docs/dev/ocr-width-experiment-2026-09.md
- docs/dev/ocr-ctc-audit-2026-09.md
- docs/dev/ocr-punctuation-fixtures-2026-09.md
- docs/dev/ocr-quality-audit-2026-09.md
- docs/plans/video-subtitle-ocr-integration-plan.md

`ocr-quality-v6-2026-09.md` là nguồn số đo medium trên video. Chỉ đọc thêm
`ocr-resume-2026-09.md`/`ocr-cache-binary-2026-09.md` khi cần contract hoặc
artifact; các gate cache/resume và smoke đã khép, không mở lại.

## Việc ưu tiên tiếp theo

Tiếp tục chất lượng OCR và giảm gánh nặng review theo evidence hiện có.
**Không chạy lại audit, 16 fixture, phép tính CTC hoặc width×2; không thử
hệ số khác.** Hai hướng CTC thuần và width×2 chưa cho căn cứ vá app.

1. Tập trung phần còn thiếu: nhãn độc lập cho các cue video đang có và phép
   đo đúng/sai quyết định, số thao tác, thời gian review. Gói phân xử bốn ca
   nằm ở `ocr-quality-audit-28/`, trường nhãn vẫn để trống. Muốn đánh giá trên
   23 cue phải xác nhận cả 23; không mặc định 19 ca khớp agent là ground truth.
2. Kiểm nguồn text xác thực/nhãn độc lập mà user cung cấp trong phạm vi task.
   Nếu chưa có, nêu chính xác dữ liệu cần bổ sung; không tự viết nhãn từ
   output OCR hoặc đoán Unicode từ raster. Không quét toàn máy, mở corpus,
   gửi dữ liệu cho người khác hoặc gọi vision để lấp phần thiếu.
3. Khi có nhãn, giữ raw/reference cũ; lưu nhãn phân xử riêng cùng căn cứ,
   mức chắc chắn và SHA/PTS nguồn. Hai ca Unicode chưa xác định phải giữ
   trạng thái đó nếu chỉ có ảnh. Người dùng không biết tiếng Trung không
   phải nguồn ground truth; phép đo thao tác review tách khỏi việc chấm chữ.
4. Chỉ triển khai thay đổi app khi có lỗi cục bộ hoặc hành vi cần sửa được
   chứng minh và tiêu chí kiểm cụ thể. Chạy regression gần phần sửa, bảo
   toàn source/IDs/raw/candidate/review và khóa export khi pending. Không
   coi giảm warning, tăng confidence hoặc giảm số cue review là chất lượng.

Nếu user giao hướng khác, làm theo hướng đó trong các giới hạn hiện hành.
Không tự triển khai toàn roadmap hoặc chỉ lặp thêm một vòng audit để lấy số mới.

## Kết quả chất lượng đã có

- **Video, evidence21:** medium 23/23 đủ chữ-số, 19/23 exact trên crop của
  một video, theo tham chiếu agent chưa native-confirmed. Hai ca thiếu số
  chấm nhìn thấy, hai ca khác biểu diễn Unicode chưa phân xử. Đây không phải
  corpus hiệu chuẩn score hoặc bằng chứng chất lượng sản phẩm.
- **Fixture, evidence29:** nhãn/codepoint/PNG/SHA đóng băng trước inference;
  cùng font/renderer đã đối chiếu sáu PNG cũ. Medium 11/16 exact, 16/16
  chữ-số gồm empty; hai ca mất một chấm, ba ca đổi biểu diễn. 16 det/16 rec/
  0 cls/0 API. Top-1/recognizer/raw bridge khớp 16 dòng; chưa chứng minh lỗi
  app. Giữ cả lỗi serializer trước inference và chẩn đoán pixel chạm nét chữ.
- **CTC, evidence30:** tính trên top-5 đã lưu, 0 inference/API mới. Cả năm
  fixture sai có cận dưới tổng điểm raw cao hơn cận trên nhãn, có tính score
  thiếu/dung sai theo giả định chuẩn hóa. Không có căn cứ thay decoder tối
  đa hóa tổng điểm CTC để chọn nhãn đúng ở các ca đó. Harness kiểm 1.092
  đường đi, 110 tổng điểm và 110 khoảng cận pass; không hiệu chuẩn xác suất đúng.
- **Width×2, evidence31:** đúng 16 tensor của 15 fixture có chữ, lặp pixel
  ngang ×2, giữ model/decoder/config. 16 rec/0 det/0 cls/0 API, mỗi tensor
  một lần; P16 không áp dụng. P02/P03 vẫn thiếu chấm; exact **10/15 → 5/15**,
  thêm lỗi P01/P04/P06/P08/P11. Chữ/số/newline giữ 15/15. **Dừng hướng này**,
  không tích hợp hoặc nối sweep. Không có cải thiện nhận dạng/giảm review.

Width×2 measure **exit1** ở assertion cuối do một `socket.bind` bị chặn,
sau khi đã lưu đủ 16 raw/full prediction arrays và 16 cặp begin/end thành
công. Import class riêng không dựng model session tái hiện probe IPv6 local
của urllib3; log gốc không có địa chỉ/stack nên không khẳng định truy ngược
chính xác event gốc. Giữ gate fail và raw; không inference lại để lấy exit0.
Prepare/score/verification/preservation pass. Toàn phiên width×2 ghi hai
bind bị chặn (measure + chẩn đoán), không phải “0 socket attempt”.

Evidence nằm dưới `build/ocr-pilot-20260910/`, ngoài Git:
`ocr-quality-21/`, `ocr-quality-audit-28/`, `ocr-punctuation-29/`,
`ocr-ctc-audit-30/`, `ocr-width-31/`. Lượt width×2 giữ SHA/trạng thái 240
đường dẫn; runtime 4.960 file giữ danh sách/size/mtime. Không phải hash mới
toàn payload49GB. Không đổi source/test/profile/auto-accept trong snapshot
chất lượng; các script thí nghiệm/raw/prediction chỉ ở evidence local.

## Artifact và các gate đã khép

Cache/resume đã có ở source/CLI/GUI/binary. Checkpoint v1 giữ ID/raw/review;
resume đọc kiểm cue cuối bằng PTS/crop SHA rồi nối phần thiếu. Fixture dài:
2.842 cue khớp bản full, 6.314 frame thay 12.316 frame, giữ 1.386 cue cũ.
Review còn mở khóa export; OCR pending CLI exit5. Full offline cuối:
1.839 pass/5 skip/51 deselected, Ruff/Pyright0/0, translations sync. Giữ log
hai lượt AV teardown và lượt full cuối exit0; không dùng làm pass online.

Smoke sau cài đã pass sau khi user yêu cầu tiếp tục từ Escape: EXE trực
tiếp trong dist tự tìm v6 medium khi ô runtime trống, kiểm SHA, mở OCR/
resume rồi đóng GUI exit0 sau79,953s, không traceback/child. Không inference/
API; AppData backup trước chạy, năm cache khôi phục từ backup thực, 15 hash
khớp. Evidence `ocr-resume-installed-27/`; không nghiệm thu lại.

Giữ `dist/VideoCaptioner-OCR6-Medium-20260911` và models/AppData/work-dir.
EXE 31.430.444 byte, 2026-09-12 11:52:25+07, SHA-256:
`34a1e970fcb643b3435ef09b09f73df9fc26ee8831c8b70e1101e643284338f1`.
Build trước exit0/6 warning/0 error; chỉ app được cập nhật, không copy49GB.
Bản cache trước SHAcef53f77…c87ef2 ở evidence26/rollback-app; app trước cache
ở evidence25. `ocr-resume-26/Update-App.ps1 -Action Rollback` trả riêng EXE/
_internal sau khi app đóng; nhánh Rollback chưa chạy. Giữ mọi backup.

## Giới hạn thao tác

- 0 API mới; cap vision14 đã hết. Không đọc Api.txt, gọi vision/dịch/TTS,
  tải model, `uv sync`, cài/nâng dependency/global hoặc dùng Python3.13.
- Host `../VideoCaptioner/.venv/Scripts/python.exe` 3.12.13;
  Pyright `--venvpath ../VideoCaptioner`. Runtime v6 hiện có, worker `-I -B`.
  Test cô lập settings/cache/credentials/logger; giữ `child_environment()`,
  contextvars helpers và `QThread.wait()` hiện có.
- Một VideoCaptioner.spec; không đè nguyên gói bằng `--noconfirm` hoặc chép
  thêm49GB. Giữ .env/cookies/Api.txt/media/raw/evidence/log/settings. Smoke
  trên dữ liệu thật phải backup trước, vì mở GUI cũng có thể đổi cache.
- Junction models evidence25 từng bị auto-review chặn gỡ vẫn giữ; không
  dùng công cụ/shell khác né chặn. Không xóa/stage `ffcachePuSHPB`.
- Resume vẫn snapshot/hash toàn nguồn và đọc lại một cue tại điểm nối;
  không tự lưu khi crash/kill. GUI phải Hủy → Lưu review trước khi đóng.
- Vision GUI, downloader/update, checkpoint tự động và corpus rộng còn
  mở, không tự triển khai trong phiên này. Không nới auto-accept hoặc dùng
  tham chiếu agent làm nhãn chuẩn. Không chạy lại full suite/build/crop
  sweep đã qua chỉ để có số mới. Bàn giao đúng file/gate/giới hạn thực tế.
