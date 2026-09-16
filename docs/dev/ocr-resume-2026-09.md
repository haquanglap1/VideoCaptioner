# Tiếp tục quét OCR từ checkpoint — 2026-09-12

**Bổ sung sau khi user yêu cầu tiếp tục:** smoke tại vị trí cài đặt đã pass.
EXE SHA `34a1e970…4338f1` chạy trực tiếp từ gói OCR6, mở màn OCR và tự tìm
`ppocrv6-medium-det-rec-cpu-v1` với ô runtime để trống, xác nhận model/profile
khớp SHA. Control cache/resume hiển thị đúng; resume/export bị khóa khi chưa
có document. App sống **79,953s**, đóng bằng GUI **exit0**, không traceback,
không process con; watcher50ms không thấy kết nối. Không chạy OCR/inference.
Đã backup AppData trước smoke, khôi phục5diskcache từ backup thực; **15 đường
dẫn theo dõi khớp hash** (EXE, manifest/profile/bridge/weights, settings và dữ
liệu sẵn có). Không hash lại toàn models hoặc chạy lại build/full suite.
Evidence: `build/ocr-pilot-20260910/ocr-resume-installed-27/`. Gate cuối của
resume đã khép; ghi chú Escape bên dưới là lịch sử của lượt bị ngắt.

Tiếp tục trên ASR-S3, `codex/asr-s3-native`, HEAD `cb92305`, giữ các thay đổi
cache/binary chưa commit của lượt trước. Không mở rộng OCR quality corpus,
vision/API hoặc tải/cài model/dependency.

## Hành vi và điểm nối

- GUI: **Hủy tác vụ → Lưu review → mở cùng video và review → Tiếp tục quét**.
  Nút mới chỉ bật khi có nguồn và document chưa quét xong. Resume dùng vùng,
  đoạn chọn và profile trong checkpoint; hạn mức cache có thể đổi theo phiên.
- CLI thêm `ocr-resume`; `ocr-review` tiếp tục chỉ duyệt/xuất, không inference.
  Đầu ra checkpoint của CLI phải khác video và checkpoint đầu vào.
- Giữ `ocr-document-v1`, không thêm trường JSON hoặc đổi cách tạo ID. Các cue
  hoàn tất trong checkpoint được giữ nguyên, gồm raw/candidate/ID, giờ đã đo,
  lựa chọn text, sửa giờ và ghi chú review. Không tự duyệt cue mới.
- Đọc lại một cue hoàn tất cuối cùng làm điểm kiểm tra. So khớp PTS, biên và
  khoảng bất định, timing issues, thứ tự candidate và SHA crop. Cue này không
  được đưa vào recognizer lần nữa. Không khớp thì dừng, không nối phần mới.
- Tracker bắt đầu lại tại đầu cue đó, giữ cờ chia do giới hạn 30 giây nếu có.
  Nhờ vậy cue đang dở sau checkpoint được dựng lại đầy đủ; câu lặp và hai câu
  đổi chữ liên tiếp không bị gộp hoặc nhân đôi tại điểm nối.
- FFmpeg seek theo timestamp nguồn, giữ `-copyts`, giải mã phần đầu từ keyframe
  rồi `select` bằng PTS nguyên. Làm tròn thời điểm seek xuống và lùi 1µs để
  tránh bỏ frame cần kiểm. Theo [tài liệu FFmpeg](https://ffmpeg.org/ffmpeg.html),
  input seek có thể lùi về điểm seek trước đó; `-seek_timestamp` dùng timestamp
  thực, còn `-noaccurate_seek` giữ phần giải mã trước đích để ứng dụng lọc.
  Bản thử dùng accurate_seek trả rỗng ở fixture có origin khác 0; đã thay và
  kiểm lại bằng CFR/VFR, H.264 B-frame, PTS phân số và origin 0/5 giây.
- Nguồn vẫn phải snapshot/hash toàn file và probe để xác minh. Resume giảm
  phần decode/tracking/recognition trước điểm nối; không bỏ kiểm SHA nguồn.
  Nếu chưa có cue hoàn tất, bắt đầu lại từ đầu selection.

```powershell
videocaptioner ocr-resume partial.ocr.json --source video.mp4 `
  --review continued.ocr.json --cache-mib 64 --report attempt.json
```

Runtime phải khớp profile/bridge cũ; checkpoint v5 cần chọn runtime v5 nếu app
mặc định tìm v6. Cache disk có thể đã bị xóa hoặc đặt 0: các cue đã lưu vẫn
được giữ và kiểm điểm nối bằng ảnh nguồn. Hủy/lỗi khi tiếp tục giữ các cue cũ
và chỉ thêm cue mới đã hoàn tất. Chỉ đánh dấu complete khi đi hết selection;
review còn mở tiếp tục khóa export, CLI exit5.

Metrics thuộc **lần chạy hiện tại**, gồm frame đọc kiểm điểm nối; không cộng
lại inference của lần trước. Các candidate thuộc phần giữ lại còn nguyên
`cache_hit` của lần tạo chúng. Không diễn giải tổng cue trong document là số
track được nhận dạng mới trong lần resume.

Không có tự lưu sau mỗi frame hoặc khôi phục khi process bị kill/crash.
Trong GUI cần hủy và lưu review trước khi đóng app. Các thumbnail/trạng thái
tracker đang dở không được persist; checkpoint chứa dữ liệu cue đã hoàn tất.

## Gate source

- 356 test OCR/CLI/GUI pass trước ba ca bổ sung. Regression bao gồm mở lại
  file, giữ review dù các control scan đã đổi, sai profile/source/crop, hủy
  lần hai khi đang kiểm điểm nối, câu liên tiếp/lặp, giới hạn giữ track và EOF.
- H.264 B-frame với PTS phân số/origin 0 và 5 giây pass. Fixture fade đầu tiên
  vô tình tạo nhiều track do mức sáng; sửa fixture dùng dãy đã kiểm ở tracker,
  không nới guard hoặc thay thuật toán để làm test pass.
- Worker v6 thật, fixture cũ 1,9s, disk cache tắt: hủy sau hai cue có 2 request,
  2 det/4 rec, 9 frame. Mở checkpoint và tiếp tục: 1 request, 1 det/2 rec,
  8 frame; đủ 3/3 câu, cùng hai cue cũ, 6 issue vẫn mở, jobs rỗng.
  Đây là kiểm contract, không là benchmark tốc độ/chất lượng corpus.

## Full offline và binary/native

- Hai lượt pytest chuẩn đã chạy hết test rồi thoát với access violation
  `0xc0000005` khi teardown, chưa có summary thành công. Lượt có hook chẩn đoán
  pass 1.839/5 skip. Hai testcase GUI mới được bổ sung `deleteLater` và xử lý
  DeferredDelete, kiểm `sip.isdeleted` trước khi QApplication bị teardown.
  Full cuối bằng `python -X faulthandler -m pytest`: **1.839 pass, 5 skip,
  51 deselected**, **190,04s**, exit0. Không thay lifetime của app hoặc kết luận
  nguyên nhân native chỉ từ việc lần chạy có chẩn đoán pass.
- Skip gồm 4 TTS cần key/service và 1 QtMultimedia offscreen. Ruff pass,
  Pyright app0/0, translations sync. Phạm vi Qt riêng 316 pass/8 skip do thiếu
  FFmpeg trên PATH ở lượt đó; full cuối có FFmpeg và chỉ còn 5 skip nói trên.
- PyInstaller một spec, build riêng app: **exit0/6warning/0error**,270,407s.
  EXE **31.430.444byte**, local2026-09-12 11:52:25+07, SHA-256
  `34a1e970fcb643b3435ef09b09f73df9fc26ee8831c8b70e1101e643284338f1`.
  App590file/529.736.862byte;11module PYZ khớp source, OCR nặng không vào Qt.
- CLI trên fixture dài cũ: full **12.316frame/2.842cue**, resume checkpoint
  cũ giữ1.386cue và chỉ xử lý **6.314frame/1.456track mới**. Hai kết quả khớp
  toàn bộ ID/raw/timing; prefix giữ nguyên cả review. Disk cache tắt; mỗi job
  full/resume có2request/2det/4rec/0cls. Job lần lượt56,656s/29,828s, có tải
  kiểm thử khác cùng máy nên không coi là benchmark tốc độ sản phẩm.
- Native GUI staging: mở cùng video và checkpoint từ binary trước, bấm
  **Tiếp tục quét**, giữ1.386cue, đủ2.842cue/5.684issue, khớp bản full;6.314frame,
  2request/2det/4rec, job19,328s. Resume bị khóa khi complete, export vẫn khóa
  vì review còn mở; lưu kết quả thành công. GUI exit0 sau347,656s, không
  traceback,0child/jobs rỗng. Watcher thấy seek877,199999s và lọc PTS8982528.
- Staging chọn runtime gốc tường minh; **không tạo junction mới hoặc copy models**.
  Đã thay riêng EXE/`_internal` tại `dist/VideoCaptioner-OCR6-Medium-20260911/`.
  Bản cache trước đó (SHAcef53f77…c87ef2) nằm ở `rollback-app/` dưới evidence26;
  bản trước cache/evidence25 được giữ. Cả hai app khớp inventory sau chuyển.

**Dừng theo user:** Computer Use báo user nhấn Escape khi bắt đầu chọn cửa sổ
smoke ở vị trí dist. Không tiếp tục điều khiển UI. Đã terminate đúng process
smoke do agent tạo, giữ receipt là **interrupted, chưa nghiệm thu startup tại
vị trí cài đặt mới**; không ghi exit0 cho bước này. Năm diskcache được khôi
phục từ backup AppData thực đã tạo trước build, giữ bản phát sinh sau smoke;
**4.970hash được bảo vệ khớp**,0process app còn lại. Gate native staging ở trên
đã pass; không dùng nó để đổi bước smoke bị ngắt thành pass.

Quay lui sau khi đóng app: từ root worktree, chạy
`./build/ocr-pilot-20260910/ocr-resume-26/Update-App.ps1 -Action Rollback`.
Nhánh Install đã chạy, nhánh Rollback chưa thực thi; giữ backup nếu cần dùng.
Junction evidence25 từng bị chặn gỡ vẫn giữ nguyên, không thử xóa lại.

File sửa của lượt resume: `VideoCaptioner.spec`, `README.md`, `status.md`,
`docs/dev/ocr-next-session-prompt.md`, `docs/plans/video-subtitle-ocr-integration-plan.md`,
file này; `videocaptioner/cli/{main.py,commands/ocr.py}`, `core/entities.py`,
`core/ocr/{decoder,pipeline,service,tracking,resume}.py`,
`ui/{task_factory.py,thread/ocr_thread.py,components/ocr_dialog.py}`;
`tests/test_ocr/{conftest,test_decoder,test_resume}.py`, `tests/test_ui/test_ocr.py`.
`resume.py`, `test_resume.py` và biên bản này là file mới. Giữ các diff cache/B
từ lượt trước. Git còn file untracked `ffcachePuSHPB`, chưa xóa/đưa vào commit.

Evidence ngoài Git: `build/ocr-pilot-20260910/ocr-resume-26/`. Chưa commit/push;
0API dịch vụ ngoài, không tải/cài dependency/model. Auto-accept, vision GUI,
downloader/update, checkpoint tự động khi crash và corpus rộng vẫn còn mở.
