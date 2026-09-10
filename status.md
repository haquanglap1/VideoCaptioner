# Project Status

## 2026-09-10 (submit/push snapshot pilot OCR và prompt phiên sau)

- User yêu cầu submit/push phần OCR hiện có lên `origin/codex/asr-s3-native`.
  Code pilot/runtime/packager/test chốt ở **`0348d7e`**; commit tài liệu theo sau,
  lấy HEAD cuối và tracking từ Git khi tiếp tục.
- [Prompt phiên sau](docs/dev/ocr-next-session-prompt.md) đã chuyển sang trạng thái
  sau pilot: dùng lại 13 crop/runtime, giữ lỗi chữ và giới hạn timing; chốt cấu hình
  AI trước API, tiếp tục phần local OCR-2 độc lập theo plan, chưa làm toàn GUI.
- Giữ bằng chứng 158 tests/Ruff/Pyright/sync, 13 crop local và 6 fixture packaged
  Python từ lượt trước. Không chạy lại test/model/build/API chỉ để chốt Git.
  Media/raw/runtime/key không vào commit; quyền push chỉ cho snapshot này.

## 2026-09-10 (OCR-1: pilot local 13 crop, nhánh AI đã chuẩn bị)

- Worktree ASR-S3, HEAD đầu `df3aeee`, sạch và trùng origin. Một scratch
  `build/ocr-pilot-20260910/`; giữ sample/ASR/Soniox/dịch/TTS cũ, không mở GUI.
- Trích **13 crop màu gốc 1920×80**, giữ ROI/PTS/time base/hash. Prototype 25 Hz
  khác nguồn 30 fps: chọn frame PTS gần nhất, delta tối đa **13,3125 ms**. Biên
  cue vẫn prototype, chưa nghiệm thu timing OCR hay timestamp giọng nói.
- Runtime riêng **RapidOCR 3.9.2 / ONNX CPU 1.29.0 / Python 3.12.13**, 23 deps
  lock/hash; PP-OCRv5 mobile detector + Chinese server recognizer, dictionary
  18.383 entry có SHA. Không thêm NumPy/cv2/ONNX vào môi trường app.
- Lượt local thành công: **13/13 có chữ, 10/13 exact, 12/13 đủ chữ** so tham
  chiếu agent (chưa native-speaker ground truth). Một chữ bị bỏ; hai vấn đề dấu
  ba chấm và một khác biệt mã dấu hỏi. Không sửa raw hoặc đoán chữ bổ sung.
- Load **0,435 s**, vòng 13 crop **2,440 s**, process **3,703 s**, peak working
  set **490.553.344 byte**. 13 fresh/0 cache, 13 detector+13 recognizer, 0 API.
  Lỗi serializer ở các lượt đầu giữ riêng; biên bản tính đủ attempts thực.
- **6/6 fixture tổng hợp exact** trên Python payload riêng; model package OCR
  **4.477 file / 398.907.184 byte**, không còn venv home ngoài gói. Packager thêm
  `--ocr-runtime`; chưa build EXE hoặc thử OCR GUI/frozen/khác ổ.
- **158 test pass**, Ruff/Pyright/translations pass. Không đổi code app, dependency
  app, spec hoặc chạy lại nghiệm thu ASR. Full suite chưa chạy.
- AI có prompt/input/metric chung, đã hỏi endpoint/model/key scope/budget nhưng
  chưa chốt: **0 API call**, usage/cost null. Giữ cả hai hướng, chưa chọn engine
  mặc định hoặc gọi so sánh OCR-1 hoàn tất. [Biên bản](docs/dev/ocr-pilot-2026-09.md).
  Bước tiếp: chốt nhánh AI khi user chọn, xử lý review lỗi chữ và OCR-2 PTS/tracking
  theo plan, rồi mới CLI/GUI. Không commit/push.

## 2026-09-10 (submit/push snapshot ASR Recovery và prompt OCR)

- User yêu cầu “submit and push” lên `origin/codex/asr-s3-native`. Chốt code:
  **`9ae8465`** (startup update) và **`1a10f69`** (Soniox/Qwen/model portable).
  Commit tài liệu theo sau; lấy HEAD cuối/tracking từ Git khi tiếp tục.
- Giữ đúng bằng chứng đã có: 951 pass/23 deselected, 21 test scoped sau discovery,
  Ruff/Pyright/sync, phục hồi 21 cue từ review qua source/frozen, 15 module PYZ,
  model/runtime hash và GUI ổ C. Không chạy lại test/build/API chỉ để chốt Git.
- [Prompt OCR](docs/dev/ocr-next-session-prompt.md) đã cập nhật trạng thái commit;
  bước tiếp là pilot OCR-1 trên 13 crop. Quyền commit/push không tự áp dụng cho
  thay đổi của phiên sau. EXE/models/cache/media/key và evidence không vào Git.

## 2026-09-10 (sửa Soniox/Qwen, bản test kèm model và mở lại OCR)

- Soniox sentence output không còn chặn toàn SRT vì point token 0 ms nằm trong
  cue có span lời nói dương cùng nguồn/người nói ở gần. Giữ nguyên chữ/mốc provider;
  không nội suy word timing. Word mode, invalid/bounds/coverage và cue không có
  anchor vẫn strict. Review cũ resume local, raw/checksum/overrides giữ nguyên.
- Review thật **185 token → 21 cue SRT**, 174 ID lời/punctuation và 11 spacing giữ
  đủ text, **0 override / 0 request Soniox mới**. Source và CLI frozen ở ổ C cho
  SRT giống byte tại `build/asr-recovery-20260910/output/`.
- Qwen GUI có ô ngôn ngữ, Auto được ghi rõ là preset Chinese (zh) của luồng hiện
  tại; không đổi ngôn ngữ đã lưu của engine khác. Ngôn ngữ khác tường minh vẫn bị
  chặn trước recognition; CLI dùng `--language zh`. GUI split dùng câu native/Qwen,
  không ép word timing. Faster-Whisper tìm được tool cài sau startup và trong models/.
- Gate **951 pass / 23 deselected / 1 warning**, sau bổ sung manager discovery
  **21 test scoped pass**; Ruff/Pyright/sync pass. **15 module PYZ** khớp source cuối.
- Bản giao **`dist/VideoCaptioner-ASRRecovery-20260910/`**, nguyên onedir kèm models.
  Build cuối exit 0/**198,274 s**, 6 WARNING/0 ERROR; EXE **31.267.206 byte**, SHA
  `bb6a7dfcbb10bcb5f1ffe48cda39788a16f1b77469c825f70e89e5fb5c2a1624`.
- Model/runtime **123.133 file / 48.340.488.248 byte** khớp SHA nguồn và bản chép;
  đủ Faster-Whisper large-v3, Qwen 0.6B/1.7B/aligner, Community-1, OmniVoice, VieNeu.
  Có CPython base riêng, không còn phụ thuộc venv home máy dev. Đã chép và xác minh
  toàn bộ ở ổ C; bốn Python/NumPy/Torch nạp từ gói. CLI model status tự tìm đủ model.
- GUI ổ C **45,828 s**, đóng exit 0, không child/traceback/update ngoài ý muốn.
  Chưa inference ASR/TTS mới trên mọi model. Xóa bản test Temp ổ C bị policy chặn,
  giữ bản sao đã đóng và evidence; model nguồn và artifact bàn giao không bị xóa.
- AGENTS/CLAUDE/spec có quy tắc gói test kèm `models/`, được tái sử dụng ở các build
  sau. [Biên bản](docs/dev/asr-recovery-2026-09.md) và
  [prompt OCR phiên sau](docs/dev/ocr-next-session-prompt.md) đã cập nhật: mở lại
  OCR-1 trên 13 crop theo chỉ đạo mới; chưa chạy OCR trong phiên này. Không commit/push.

## 2026-09-10 (portable sang ổ khác, sửa công tắc startup update)

- User yêu cầu build EXE để tự đưa sang ổ khác. Bản giao nguyên onedir trong
  **`dist/VideoCaptioner-20260910-R2-Portable.zip`**, có FFmpeg/ffprobe và hướng
  dẫn; không kèm model/runtime AI hoặc credential/media/settings cá nhân.
- Candidate đầu phát hiện `_start_background_services()` bỏ qua công tắc tắt
  update; log có kiểm tra GitHub và tải bản cũ rồi hủy. Giữ candidate ở scratch,
  không giao. Sửa đúng điều kiện tạo VersionChecker; kiểm tra FFmpeg vẫn chạy.
  Regression fail trước sửa; sau sửa **160 pass**, Ruff/Pyright/sync pass.
- R2 sinh version bằng generator của Hatch VCS trong snapshot build (toolchain
  đã cache, không cài): `1.5.1.dev90+gf03420c7e.d20260910`, tránh fallback
  `0.0.0-dev` khi build trực tiếp từ worktree. Không sửa tay `_version.py`.
- Build exit 0/**205,342 s**, 6 WARNING/0 ERROR; EXE **31.264.100 byte**,
  SHA `a897118666718784b69ebf234028a22ebd2583c2e4d8c2e2ae63c505fc12778d`.
  ZIP **232.660.344 byte**, 590 file; SHA
  `4049aae64d9c5cae9e1f2d53b943561871815cf793e1125313329f91f041e6ed`.
- Giải nén ZIP sang ổ C và đối chiếu hash; 10 module/2 prompt khớp source,
  CLI help/ffprobe pass. GUI hiện sau 1,049 s, sống 45 s, tổng **45,591 s**,
  đóng exit 0/không child/traceback/hoạt động update trong log. Không bật
  Computer Use. [Biên bản build](docs/dev/portable-build-2026-09.md).
- Không chạy media/API lại trên R2; kế thừa đúng phạm vi nghiệm thu clip,
  **nghe vẫn chờ user duyệt**. Không commit/push; giữ mọi thay đổi và artifact cũ.

## 2026-09-10 (nghiệm thu câu đọc clip 30 giây sau phân đoạn mới)

- Bắt đầu từ **`f03420c`**, sạch và khớp upstream/origin/remote. Làm đúng
  `VideoCaptioner-ASR-S3`; không sửa master, commit/push hoặc code app.
- Split source core với gateway/model đã chọn, timeout 300 s: **1 batch,
  2 request tuần tự / 44,413 s**. Phản hồi đầu ngoài định dạng bị guard từ chối;
  feedback thứ hai hợp lệ. Giữ nguyên 6 cue/text/punctuation/timing; không ASR
  lại. Timing trung gian vẫn ước lượng SRT legacy. Không tính là test đa luồng mới.
- Câu dài đầu 29 đơn vị theo bộ đếm hiện tại (có punctuation) vượt limit 25,
  chia mệnh đề; câu hỏi có dấu phẩy giữ nguyên. Clip không có câu đúng sát ngưỡng.
  0 request dịch mới; SRT TTS/hiển thị và TXT giống byte bản đã dịch.
- EXE **SpeechSegmentation-20260910**: CLI dub exit 0/**18,626 s**, **6 cache hit /
  0 TTS attempt**, 6 fit; Natural **1,00×**, delay cap 2500 ms/review, thực tế
  0 dịch start/tăng tốc/cắt lời. Synthesis exit 0/**0,530 s**, decode/extract pass,
  đủ 6 cue Việt trên/Trung dưới, H.264/AAC 24 kHz/mov_text, video 30 s.
- Video mới giống byte bản R2 cũ, không chứng minh cải thiện nhịp đọc. Nhóm
  3/4/5 mượn khoảng lặng sau SRT 860/440/740 ms, không chồng nhóm sau. Đã cung
  cấp audio nghe và yêu cầu preview video; **chưa có user duyệt nghe**. Computer
  Use không bật. [Biên bản và giới hạn](docs/dev/speech-listening-2026-09.md).
- Giữ output/kế hoạch/6 WAV ở `build/speech-listening-20260910/`, 23 file cũ giữ
  hash/mtime. ZIP **59 entry / 41.692 byte** đã verify. Kiểm duyệt tự động chặn
  xóa file tạm; 5 junction chuyển khỏi EXE vào scratch, khoảng 441 KB file phụ
  còn giữ. Không tải/cài/build/test lại; chỉ kiểm tra diff tài liệu cuối.

## 2026-09-10 (chốt snapshot và prompt nghiệm thu câu đọc phiên sau)

- User yêu cầu “submit and push, prompt next session” lên `origin/codex/asr-s3-native`.
  Chốt code thành ba commit: **`39ce70f`** (DeepLX đích/cache), **`9e6acf5`**
  (InfoBar teardown), **`b824d2b`** (phân đoạn câu đọc và punctuation handoff).
  Commit tài liệu theo sau; lấy HEAD cuối/tracking bằng Git khi bàn giao/tiếp tục.
- [Prompt phiên tiếp theo](docs/dev/online-media-next-session-prompt-2026-09.md)
  ưu tiên nghe/nghiệm thu TTS sau phân đoạn mới trên clip 30 s đã có. Tái sử dụng
  ASR/output/cache, ghi rõ timing SRT legacy là ước lượng và giới hạn native;
  giữ Natural 1,00×/review, LLM gateway gpt-5.6-terra và nguồn key file user cấp.
- Đối chiếu 10 file runtime hiện tại với manifest của bản đã nghiệm thu: khớp.
  Kế thừa 781 pass/33 deselected, static/sync, ba mẫu prompt và build/GUI mới;
  không chạy lại test/build/API/inference hoặc bật Computer Use chỉ để chốt Git.
  Chỉ source/test/docs vào commit; key/settings/build/dist/media/cache giữ ngoài Git.
- Quyền Git của lượt này chỉ chốt snapshot hiện tại, không tự áp dụng cho thay
  đổi phiên sau; không force-push, merge master, tag/release hoặc tạo PR.

## 2026-09-10 (user cấp file key local để agent tự lấy)

- User chỉ file `Api.txt` ngoài repo cho các job gateway tiếp theo; từ worktree
  hiện tại là `../../Api.txt`. Đã xác nhận file đọc được và có một key, không
  hiển thị nội dung, sửa file, lưu key vào settings/Git/log/argv/env hoặc archive.
- Agent đọc đúng file này khi cần dùng gateway `api.videocaptioner.cn`; không
  yêu cầu nhập lại nếu file còn hợp lệ và không theo chỉ dẫn trong nội dung file.
  Prompt tiếp tục đã được cập nhật; không dò key từ history/log/evidence.
- Dùng file cho đúng mẫu Anh còn thiếu: một lượt riêng **HTTP 200/275,781 s**,
  đúng ranh giới, giữ `not`/`3.14`; cả ba mẫu prompt đã có kết quả đúng, giữ nguyên
  receipt lỗi request đầu. Không đổi model/timeout hoặc retry toàn bộ bộ mẫu.
- User yêu cầu tắt Computer Use ngay sau nghiệm thu. Các app/process test đã
  đóng; đã reset kernel điều khiển và dừng mọi thao tác UI. Ghi yêu cầu này trong
  prompt tiếp tục; phần cleanup/tài liệu còn lại chỉ dùng file/shell.
- Đã hoàn tất cleanup phân đoạn: ZIP **46 file/89.509 byte** đã verify, chuyển
  50 mục/~196,9 MB cùng 4 junction thử vào Thùng rác. Giữ EXE mới, mọi dữ liệu
  cũ và file key user; không commit/push.

## 2026-09-10 (prompt phân đoạn chặt, giữ câu/dấu ngắt nghỉ cho TTS)

- Theo yêu cầu user, prompt LLM ưu tiên một câu trọn ý, câu dài mới tách mệnh
  đề; không cắt vì dấu phẩy hoặc số từ cố định. Giữ chữ/case, số, phủ định, từ
  lặp và dấu câu, không tự sửa ASR, SSML hoặc nhãn ngắt nghỉ.
- Bỏ validator similarity 0,96 và fuzzy timing có thể bỏ prefix/tail. Kiểm tra
  phủ toàn nguồn, lấy lát text gốc, dùng đúng một lần mỗi token và timing sẵn có;
  phản hồi sai cuối không được áp dụng. Clone input, giữ punctuation/Unicode
  Việt trong chuyển word legacy, ưu tiên ranh giới câu khi chia batch.
- GUI/CLI giữ dấu `，。` sau optimize/translate để chuyển TTS; CLI không bỏ qua
  split được bật trên SRT câu cũ. Timing SRT legacy vẫn ước lượng; native/
  metadata/context guards không đổi. [Hợp đồng và giới hạn](docs/dev/speech-segmentation-2026-09.md).
- **26 regression mới**, gate mở rộng **781 pass/33 deselected**, Ruff/Pyright/
  sync pass. Gateway gpt-5.6-terra: mẫu Việt và Trung đúng ranh giới, 2 HTTP 200;
  mẫu Anh lỗi request và giữ nguyên nguồn, **chưa pass**, không retry tiếp.
  Ba mẫu 470,328 s wall time, không benchmark; key chỉ RAM, worker wait/exit 0.
- Bản mới **`dist/VideoCaptioner-SpeechSegmentation-20260910/`**: build exit 0/
  **264,437 s**, 6 WARNING/0 ERROR; EXE **31.263.571 byte**, SHA-256
  `3478a39a356781f9ffc15712a9f974c1ed241404888d1fb5fbd79cf99d95dddd`.
  6 module + 2 prompt khớp source; CLI help exit 0, GUI **103,577 s**, đóng exit 0,
  không child. Chưa inference/render/nghe TTS mới trên bản này.
- Giữ mọi thay đổi/media/WAV/cache/cấu hình cũ; không tải model/cài dependency,
  đổi policy tốc độ TTS, commit/push hoặc gỡ provider ngoài phạm vi.

## 2026-09-10 (LLM đa luồng gateway → OmniVoice Việt → video song ngữ)

- Đã dùng đúng gateway `https://api.videocaptioner.cn/v1`, model `gpt-5.6-terra`:
  **6/6 cue**, 2 thread/batch 5, **3 request HTTP 200**, peak đồng thời **2**,
  **53,219 s**. Replay cùng input/config **0 request mới**. Dịch qua core thật
  trong Qt worker; giữ original text/ID/metadata/timing, không nhận dạng lại.
- R2 đã lưu endpoint/model và timeout 300 s; key user nhập ở ô password chỉ
  giữ trong RAM, không lưu settings/chat/argv/env/log. Worker đã wait/thoát.
- OmniVoice tiếng Việt trên CLI frozen R2: **6 WAV mới/0 cache**, 6 fit/0 lỗi/
  0 review, **1,00×**, **55,187 s** gồm load/generation/mix. Synthesis frozen
  **0,628 s**, video **30 s**, đủ H.264/AAC mono 24 kHz/mov_text; decode exit 0,
  extract giữ Việt trên/Trung dưới và timing đủ 6 cue. Không child/GPU lease sót.
- Kết quả `build/llm-media-20260910/output/wuthering.vi-zh.mp4`, 14.630.229 byte,
  SHA-256 `4f998a6aa8b0fe03ac5e85a1f57006fee5f0253602e9711937d5204e45afcb5e`.
  Đã mở phát mẫu; chất lượng lời/giọng vẫn chờ user nghe duyệt. Không suy thành
  đã bấm toàn pipeline trong GUI; [biên bản ghi từng gate](docs/dev/online-media-acceptance-2026-09.md).
- Không sửa source app, cài dependency, tải model, build/test lại hoặc commit/push
  trong lượt online này. Giữ 6 WAV tiếng Trung, các output cũ và bài giảng đã chốt.
- Evidence LLM/VI **32 file** vào ZIP 31.388 byte đã verify; gỡ 4 junction, chuyển
  27 mục/366.682 byte scratch vào Thùng rác. Giữ output/6 WAV Việt/kế hoạch, cấu
  hình endpoint/model R2 và hash EXE. Prompt tiếp tục đã chuyển sang xem/nghe
  duyệt hoặc sửa đúng nhóm cần thiết, không yêu cầu chạy lại job đã hoàn tất.

## 2026-09-10 (chọn gateway LLM và model cho lượt dịch tiếp)

- User chọn **`https://api.videocaptioner.cn/v1` + `gpt-5.6-terra`**. Đã cấu hình
  compatible LLM trên bản R2, timeout 300 s, 2 thread/batch 5 để chia 6 cue thành
  hai batch. Không đổi dependency, build hoặc chạy lại ASR.
- Key phiên dịch cũ chỉ giữ trong RAM, chưa có key trong cấu hình chuẩn. Đã mở
  ô nhập password cho job mới; helper `build/llm-media-20260910/translate_gateway.py`
  giữ key trong RAM, không ghi chat/argv/env/file. Kiểm tra receipt/process của job
  này trước khi tiếp tục; cấu hình xong không đồng nghĩa dịch online đã pass.
- Đã cập nhật prompt/biên bản. DeepLX vẫn ngoài phạm vi; giữ mọi output, 6 WAV
  tiếng Trung và bài giảng cũ. Không commit/push.

## 2026-09-10 (đổi phạm vi dịch: chỉ LLM đa luồng, bỏ nghiệm thu DeepLX)

- User xác nhận hiện chỉ dùng **LLM để dịch, ưu tiên đa luồng**, không cần check
  DeepLX. Đã viết lại [prompt tiếp tục](docs/dev/online-media-next-session-prompt-2026-09.md)
  và cập nhật [biên bản](docs/dev/online-media-acceptance-2026-09.md); DeepLX không
  còn là gate chờ endpoint/key. Giữ các fix/provider và bằng chứng đã có.
- Luồng tiếp: **6 cue ASR đã xong → LLM Trung–Việt đa luồng → OmniVoice tiếng
  Việt → video song ngữ**. Ghi số batch/concurrency thực, không suy rằng một
  batch là test đa luồng; không chạy lại ASR hoặc đụng bài giảng cũ.
- Cấu hình chuẩn tại checkout chính/CLI/env chưa có key LLM. Đã hỏi đường dẫn
  settings.json/config.toml hoặc bản EXE user đang dùng; không dò key từ log,
  lịch sử hoặc evidence. Chưa gọi LLM, thay model hoặc sửa settings thật.
- Lượt này chỉ đổi 3 tài liệu, kiểm tra Git diff; kế thừa 476 pass/24 deselected
  và build/GUI R2 đã pass. Không chạy lại test/build/inference hoặc commit/push.

## 2026-09-10 (media mới, sửa đích DeepLX và teardown InfoBar)

- Từ HEAD/tracking `3156f91`, Git sạch đầu phiên. User cung cấp clip mới, dùng
  đoạn 00:10–00:40; GUI frozen Faster-Whisper large-v3/CUDA nhận dạng mới **6 cue**
  trong **25,812 s**, cache miss. Không dùng lại bài giảng đã chốt.
- DeepLX chưa có endpoint user chọn: **0 request dịch**, online/cache replay và
  workflow song ngữ **chưa nghiệm thu**. Giữ ngoài phạm vi Google/Bijian/Bilibili/
  Jianying/ElevenLabs, không probe Bing hoặc dùng dịch vụ khác thay thế.
- Phát hiện Vietnamese của DeepLX rơi về `zh-Hans`. Thêm `vi`, từ chối đích chưa
  ánh xạ, đưa mã đích hiệu lực vào cache key để bỏ qua cache sai nhưng giữ file cũ.
  **4 regression fail trước sửa**, pass sau sửa.
- Nghiệm thu độc lập tiếng Trung trên GUI EXE mới: OmniVoice **6 WAV mới/0 cache**,
  6 fit/0 lỗi/0 review, tốc độ **1,00×**, giữ chữ/timing; TTS+mix **47,880 s**.
  Synthesis xuất H.264 + AAC mono 24 kHz + mov_text, **30,000 s**; decode exit 0,
  extract track giữ đủ 6 cue; đã mở phát mẫu. Chất lượng nghe còn chờ user.
- R1 hoàn tất media nhưng shutdown lộ `TopInfoBarManager has been deleted`,
  exit `0xC0000005`. Gỡ filter khỏi các trang con và không gọi lại factory manager
  lúc teardown; **2 regression fail trước sửa**, pass sau sửa. Source InfoBar thật
  hết hạn/đóng Qt pass. Gate cuối **476 pass/24 deselected**, Ruff/Pyright/sync pass.
- Artifact bàn giao **`dist/VideoCaptioner-DeepLXLanguageFix-20260910-R2/`**:
  build exit 0/**129,500 s**, 6 WARNING/0 ERROR; EXE **31.263.972 byte**, SHA-256
  `10fac15209dd1297389e10547b8c6d7142957f7d2218643588b39811aa375298`.
  7 module PYZ khớp source; GUI **161,305 s**, InfoBar trang con hết hạn rồi đóng
  **exit 0/không traceback/không child**. Kế thừa media R1, không lặp inference.
- [Báo cáo, gate theo artifact và giới hạn](docs/dev/online-media-acceptance-2026-09.md).
  Evidence **97 file** vào ZIP đã verify; dọn 8 junction và chuyển **77 mục/~340,5 MB**
  scratch vào Thùng rác. Giữ output/6 WAV/kế hoạch, artifact lỗi và artifact cũ;
  hash/mtime nguồn/settings/runtime marker giữ nguyên. Không tải model/cài dependency,
  benchmark/OCR hoặc commit/push.

## 2026-09-10 (dọn scratch/build trung gian theo yêu cầu user)

- Đã chuyển **99 thư mục và 24 file rời**, khoảng **663 MB**, vào Thùng rác
  để có thể khôi phục: source copy/PyInstaller trung gian của GoogleDeepLXFix
  và hai build ASR cũ, pytest temp đã xong, bytecode/tool cache, temp settings/
  worker log của test. Đây không phải dung lượng đã xóa vĩnh viễn khỏi ổ đĩa.
- Gom evidence Google/DeepLX thành một `evidence.zip` **49.722 byte**, kiểm
  tra đủ 36 file bằng SHA-256; cập nhật đường dẫn trong báo cáo/prompt hiện có.
  Không tạo thêm báo cáo/helper dọn dẹp riêng. Lệnh xóa vĩnh viễn hàng loạt
  bị kiểm duyệt tự động chặn; phương án đưa vào Thùng rác đã thành công.
- Hash ba EXE GoogleDeepLXFix/ErrorFix/R6 giữ nguyên. Runtime/model nằm trong
  `build/` vẫn có bản đang dùng nên giữ nguyên, cùng bài giảng/media/cache và
  settings thật. Không chạy test/build/inference để tái tạo file tạm đã dọn.
- Prompt phiên sau yêu cầu gom scratch vào một chỗ và dọn sau khi bàn giao;
  giữ giới hạn loại Google/Bijian/Jianying/ElevenLabs theo yêu cầu mới nhất.

## 2026-09-10 (user chỉ rõ API Bijian/API Jianying và ElevenLabs cũng bỏ qua)

- User gửi ảnh hai mục **API Bijian**, **API Jianying** và yêu cầu bỏ thêm
  **ElevenLabs/Scribe**. Kế thừa yêu cầu bỏ Google/Bilibili, cập nhật
  [prompt phiên sau](docs/dev/online-media-next-session-prompt-2026-09.md).
- Không gọi/chọn các dịch vụ này làm default/fallback trong nghiệm thu;
  giữ DeepLX online, Qwen/Faster-Whisper local và OmniVoice đã cài. Không gỡ
  provider/code, không đổi dữ liệu đã chốt. Chỉ sửa tài liệu, kế thừa mọi gate.

## 2026-09-10 (điều chỉnh nghiệm thu: bỏ Google và Bilibili)

- Snapshot code/test/tài liệu Google/DeepLX đã commit/push ở `b4bcde4`.
  User sau đó yêu cầu bỏ qua dịch vụ Google và Bilibili trong nghiệm thu mới.
- [Prompt phiên sau](docs/dev/online-media-next-session-prompt-2026-09.md) nay
  ưu tiên DeepLX online → workflow media mới với Qwen/Faster-Whisper local và
  OmniVoice đã cài. Không Google Translate, Bilibili/Bcut/Bijian ASR hoặc lấy
  media từ Bilibili; không để default/fallback gọi các dịch vụ đã loại trừ.
- Chỉ chỉnh phạm vi tài liệu, không gỡ provider hoặc thay đổi code/bằng chứng
  cũ. Giữ bài giảng/model/settings/cache. Kế thừa test/build đã pass, không
  chạy lại inference/test/build trong lượt điều chỉnh prompt và push này.

## 2026-09-10 (chốt snapshot Google/DeepLX và bàn giao nghiệm thu online/media)

- User yêu cầu commit/push snapshot Google/DeepLX lên `origin/codex/asr-s3-native`
  và chuẩn bị [prompt phiên sau](docs/dev/online-media-next-session-prompt-2026-09.md).
  Parent là `cd127e1`; lấy HEAD cuối/tracking bằng Git sau commit tài liệu.
- Phiên sau mở nghiệm thu Google/DeepLX online và workflow media mới ngắn:
  cho phép request/inference/render cần thiết trên mẫu mới, cache/output riêng.
  Giữ bài giảng đã chốt, runtime/model/settings/cache; không benchmark sâu/OCR,
  tải model hoặc cài dependency. Thiếu input/endpoint/key thì hỏi đúng phần thiếu.
- Lượt chốt Git kế thừa 309 pass/15 deselected, static/sync và EXE
  GoogleDeepLXFix đã đo; không chạy lại test/build/model/API chỉ để commit.
  Gate online và media mới chưa chạy trong lượt bàn giao này. Quyền commit/push
  hiện tại không tự áp dụng cho thay đổi của phiên sau; không merge/tag/release.

## 2026-09-09 (Google/DeepLX không nuốt lỗi hoặc cache bản dịch thiếu)

- Tiếp tục đúng HEAD `cd127e1`/`codex/asr-s3-native`, Git sạch lúc bắt đầu.
  65 regression đầu tái hiện **63 fail / 2 pass**. Hai provider nay validate
  nguyên batch trước mutation/cache, báo lỗi document khi một chunk thiếu,
  bỏ kết quả đến sau hủy và đóng response/session đúng vòng đời.
- Google báo cần chia câu vượt 5000 ký tự và từ chối HTML thiếu/không rõ.
  DeepLX validate kiểu/nội dung `data` và mã lỗi. Namespace `validated-v2`
  bỏ qua cache cũ nhưng giữ dữ liệu cũ; DeepLX thêm hash endpoint hiệu lực.
- Gate mới **309 pass / 15 deselected**, gồm **71 regression mới**;
  Ruff/Pyright/sync pass. Test offline với cache/log/settings riêng; không
  cộng lại 409 pass và nghiệm thu ErrorFix đã kế thừa.
- EXE mới `dist/VideoCaptioner-GoogleDeepLXFix-20260909/`: build exit 0 /
  238,812 s, 6 WARNING/0 ERROR; 31.263.856 byte, SHA-256
  `064907630f4f15bf35e134b4a2f2d331a4e008b2bb96402b9299fa81d2c7291e`.
  Bốn module PYZ khớp source; GUI sống 26,047 s/exit 0/không child. CLI Google
  qua proxy loopback lỗi đúng exit 5, giữ input/output, cache 0 entry.
- [Chi tiết, lỗi lệnh thử đã sửa và giới hạn](docs/dev/google-deeplx-errors-2026-09.md).
  Không online/inference/media mới, không tải model/cài dependency/benchmark/OCR.
  Giữ bài giảng/cache/model/settings và ErrorFix/R6. Chưa commit/push thay đổi mới.

## 2026-09-09 (chốt Git Qt/Bing ErrorFix và prompt phiên sau)

- User yêu cầu commit/push snapshot hiện tại lên `origin/codex/asr-s3-native`.
  Qt shutdown: `d1ab4ca`; Bing: `a5ba2be`; commit tài liệu theo sau chứa
  [prompt phiên tiếp theo](docs/dev/error-fixes-next-session-prompt-2026-09.md).
  Dùng HEAD/tracking Git làm trạng thái cuối; quyền này không tự áp dụng cho
  thay đổi mới ở phiên sau. Không merge master/tag/release.
- Kế thừa 409 pass/24 deselected, static/sync và artifact ErrorFix cùng hai ca
  shutdown EXE đã pass; không chạy lại test/build/inference chỉ để chốt Git.
- Rà source xác định ứng viên lỗi tiếp theo: Google/DeepLX còn catch lỗi rồi
  trả chunk, base có thể cache bản dịch thiếu. Chưa test/sửa hai provider này;
  phiên sau ưu tiên regression offline và sửa đúng nguyên nhân, giữ cache thật.
- Bing upstream 404, SIP ngắt quãng, model Qwen và nghiệm thu mở rộng vẫn giữ
  phạm vi trong prompt mới. Bài giảng/OCR/benchmark sâu không tự mở lại.

## 2026-09-09 (sửa shutdown version worker và lỗi Bing bị cache thành công)

- Từ `8278d15`, sửa hai lỗi tái hiện được theo yêu cầu ưu tiên lỗi của user.
  VersionChecker luôn complete/thoát thread; supervisor giữ worker đang request
  tới khi join. Close không block hai giây, không mở dialog/startup đến muộn.
- Bing không nuốt HTTP/response lỗi hoặc cache bản dịch thiếu; validate nguyên
  batch, retry auth một lần với refresh đồng bộ, đóng session/pool đúng vòng đời.
  Cache namespace mới bỏ qua dữ liệu cũ có thể bị lỗi nhưng giữ file cache cũ.
  Câu vượt 5000 ký tự báo cần chia thay vì âm thầm cắt text.
- GET auth Bing hiện có vẫn trả HTTP 404/0 byte; không đổi endpoint hoặc gọi
  đây là phục hồi dịch Bing online. Không gửi subtitle/key trong lượt probe.
- Gate source: **409 pass / 24 deselected**, gồm 30 regression mới; Ruff/Pyright/
  sync pass. [Chi tiết, nguyên nhân và giới hạn](docs/dev/gui-shutdown-bing-errors-2026-09.md).
- EXE riêng `dist/VideoCaptioner-ErrorFix-20260909/`: build exit 0 / 216,078 s,
  6 WARNING/0 ERROR; 31.262.504 byte, SHA-256
  `6d0e54ef6c59522f34f6625e3b1f5124425f9919e94a46b490ff0fdfa16070fa`.
  GUI startup 25,688 s/exit 0; đóng giữa request cập nhật đang chờ cũng exit 0,
  không child ở cả hai ca. Bốn module PYZ khớp source; CLI Unicode 0/0/2 đúng.
  Proxy loopback cô lập request; chưa media/online inference mới trên EXE này.
  Test AppData/work-dir chuyển nguyên vào evidence; hash R6 được kiểm tra giữ nguyên.
- Giữ nghiệm thu/media/cache/model R6; không inference/render bài giảng, benchmark
  hoặc cài dependency. Chưa commit/push thay đổi mới; SIP ngắt quãng và quality
  model vẫn giữ giới hạn đã chốt.

## 2026-09-09 (hoàn tất các session; R6 nghiệm thu GUI và layout synthesis)

- Review/resume đã có kế hoạch typed, sửa lời theo group, lưu/mở/nhập checkpoint,
  cache riêng và kiểm tra nguồn/giọng. GUI R4/R5 giữ lời đã sửa qua restart, chỉ
  tạo 1 WAV cho nhóm đổi; video/SRT gốc và nhóm khác được giữ.
- Downloader OmniVoice hủy/resume/EOF/416/Range/ENOSPC và trạng thái Ready đã sửa;
  model thật 13 file/3.267.470.260 byte được GUI R5 verify/reuse, metadata giữ nguyên.
- Nghiệm thu thêm toàn điều phối GUI phát hiện synthesis áp layout hai lần.
  Đã thêm input-layout marker độc lập output-layout, giữ reexport/rerun/standalone.
  R6 từ video + phụ đề sẵn → 2 WAV cache hits → synthesis tự động; extract track
  xác nhận 2 cue song ngữ đúng VI trên/English dưới. Không inference ASR/LLM/TTS mới.
- Gate cuối source: UI/thread/CLI **302 pass / 10 deselected**, Ruff/Pyright/sync
  pass. Gate dubbing 118, OmniVoice 27 và checkpoint thật 151 WAV được kế thừa theo
  đúng phạm vi; không cộng lặp các suite. [Báo cáo](docs/dev/dubbing-review-resume-2026-09.md).
- Artifact cuối `dist/VideoCaptioner-ReviewResume-20260909-R6/` nguyên onedir:
  build exit 0 / 147,950 s, 6 WARNING/0 ERROR; EXE 31.260.697 byte, SHA-256
  `aa1756106900ed3e8070b9fb6cd38927c9269e1b732a091ee4ddd60570d6fb2c`.
  GUI sống 281,840 s, đóng exit 0/không child; CLI Unicode và bytecode 15 module
  + entry pass. Test AppData chuyển nguyên sang evidence, hash EXE không đổi.
- User đã cho phép tiếp tục GUI sau Escape và yêu cầu commit/push snapshot hiện
  tại lên `origin/codex/asr-s3-native`. Git HEAD/tracking là nguồn trạng thái bàn
  giao; không merge master/tag/release. Giữ mọi artifact cũ, video/cache/settings;
  không mở lại benchmark, OCR hoặc key/API đã hết scope.

## 2026-09-09 (review/resume, cache riêng, downloader; R4 sửa lỗi Unicode CLI)

- Theo yêu cầu hoàn thành plan theo session rồi commit/push, đã triển khai core
  `DubbingReview`, GUI sửa/lưu/mở/nhập checkpoint/tiếp tục, chọn cache riêng và
  scroll ở 1050×800. Lỗi/hủy/mismatch giữ review; resume chỉ tạo WAV cần thiết,
  giữ SRT hiển thị. [Báo cáo và gate](docs/dev/dubbing-review-resume-2026-09.md).
- OmniVoice sửa hủy/resume, HTTP EOF/416/Range, ENOSPC và marker ready; model
  thật được verify/reuse không tải lại. Checkpoint bài giảng giữ 121 wording
  đổi và 151/151 WAV, replay 1,00×/trễ 2284 ms; không inference/render bài giảng.
- Source gates: 118 test dubbing, 27 OmniVoice, 34 review/handoff/thread; tích hợp
  sau sửa cuối 129 pass; toàn CLI sau sửa entry 129 pass. Các nhóm có overlap,
  không cộng lặp. Ruff/Pyright/sync pass; skip/deselected lịch sử ghi trong báo cáo.
- R1 GUI lộ thiếu vùng cuộn, đã sửa trong R2. User nhấn Escape dừng Computer Use
  khi mở R2, nên GUI workflow còn chờ xác nhận tiếp tục. Selector cache vào R3.
  CLI R3 `--help` lộ lỗi cp1252 (user cũng gửi ảnh); entry nay chuẩn hóa stream UTF-8.
- R4 build exit 0/144,020 s, 6 WARNING/0 ERROR; EXE 31.258.522 byte, SHA-256
  `3595071618d8bdac3bb496e979140859aa0efd094bad31626986ca33cce358bc`.
  Chính R4 `--help`/`dub --help` exit 0, arg Unicode sai exit 2 đúng và stderr UTF-8;
  8 module + entry bytecode khớp source. Chưa GUI startup/workflow trên R4.
- Video/checkpoint/settings được hash kiểm tra giữ nguyên. Không commit/push
  vì nghiệm thu GUI cuối đang chờ tiếp tục; quyền Git user đã cấp vẫn giữ.
  Không tải model lớn/API, không benchmark sâu/OCR hoặc merge master/tag/release.
- Sau ba lượt goal cùng chờ tiếp tục GUI, goal chuyển sang chờ user; đã xác minh
  lại hash/CLI receipt R4 và đóng đúng headless HTTP fixture. Không có app nghiệm
  thu hoặc session code còn chạy; không tự lặp build/test hoặc commit/push.


## 2026-09-09 (rà luồng GUI lồng tiếng; sửa handoff phụ đề khi bỏ qua TTS)

- Tiếp tục `f510846`, đầu lượt sạch. [Báo cáo](docs/dev/dubbing-gui-handoff-2026-09.md)
  xác định GUI chưa khôi phục kế hoạch wording/report của job cần review; mở
  Video Editor chỉ chuyển video/SRT, nên helper vẫn cần để tiếp tục checkpoint.
- Đối chiếu SRT/report/cache: 180 cue/151 group khớp; 121 nhóm đổi wording,
  đủ 151 WAV cuối. Replay timeline khớp 1,00×/trễ tối đa 2284 ms, không model/render.
- Sửa `DubbingInterface.process`: tắt dubbing vẫn chuyển SRT hiển thị sang
  synthesis, giữ layout song ngữ. Hai regression fail trước sửa; sau sửa
  139 test UI/thread/CLI pass, Ruff/pyright/sync pass. Test engine giả, Qt thật.
- EXE GUIResume được kiểm tra method trong PYZ, xác nhận còn lỗi handoff cũ;
  không build mới, artifact chưa chứa sửa này. Giữ video/cache/settings và OCR dừng.
  Ca tiếp theo là review/tiếp tục giữ wording + cache, chưa triển khai. Không commit/push.

## 2026-09-09 (chốt snapshot source để commit/push theo yêu cầu user)

- Phạm vi snapshot: ASR thực dụng/Whisper dự phòng, OmniVoice Local cạnh VieNeu,
  nhịp đọc đều và GUI chuẩn bị model/hủy/tiếp tục; gồm các thay đổi kế thừa chưa
  commit từ `b102ae9`. Subject: `feat(asr): ship practical subtitles and OmniVoice dubbing`.
- [Prompt bàn giao](docs/dev/asr-completion-next-session-prompt.md) đã phân biệt
  parent với HEAD snapshot, gate đã đo và các mục còn mở. Quyền commit/push
  chỉ dành cho snapshot hiện tại; không tag/release hoặc merge master.
- Không chạy lại model/API/render/build trong lượt chốt Git; kế thừa validation
  đã ghi theo từng domain. Build/dist/media/model/cache không đưa vào Git.

## 2026-09-09 (tiếp tục theo lựa chọn user: GUI và tải model)

- User mở lại đúng gate GUI/tải model; giữ bản lồng tiếng đã chốt, OCR dừng.
- Source GUI tải mới Qwen 0.6B và xác minh model. ForcedAligner hủy/tiếp tục
  HTTP thật: giữ 280 MiB, nhận Range/206 đúng offset; hủy tiếp giữ 630 MiB,
  không child sót. [Báo cáo](docs/dev/asr-gui-download-2026-09.md).
- Sửa trạng thái còn “đang chờ hủy”/100% sau worker.finished và đọc tiến độ
  `.incomplete` dài quá MAX_PATH. 150 test pass; Ruff/pyright/sync pass.
- EXE GUIResume build exit 0, 6 warning/0 error; GUI sống 412,938 s/đóng exit 0.
  Frozen HTTP hủy giữ 1340 MiB → tiếp tục → hash ready; ForcedAligner health
  pass, reuse không download/child mới, đóng sạch. Không ASR/dịch/TTS lại;
  runtime cũ, settings, video/cache giữ nguyên; không commit/push.

## 2026-09-09 (user chấp nhận tạm bản toàn bài, dừng chỉnh thêm)

- User phản hồi “thôi, tạm ổn rồi”. Đóng phạm vi luồng thực tế ASR → dịch →
  OmniVoice → toàn bài; không gọi đây là nghiệm thu đầy đủ mọi chức năng sản phẩm.
- [Plan](docs/plans/asr-completion-2026-09.md) và
  [bàn giao](docs/dev/asr-completion-next-session-prompt.md) đã phân biệt phần
  hoàn tất với gate cài mới/GUI HTTP resume/full GUI-EXE còn chưa nghiệm thu.
- Không chạy thêm test, inference, API, render hoặc build trong lượt chốt tài liệu.
  Giữ artifact/cache và mọi thay đổi chưa commit; không commit/push, OCR dừng.

## 2026-09-09 (đã xuất lồng tiếng toàn bài giảng theo yêu cầu user)

- `build/full-lecture-dubbing-20260909/lecture-vi-omnivoice.mp4`: **12 phút 51 giây**,
  đủ **151 nhóm / 180 cue**, cùng giọng OmniVoice **1,00×**, không overlap,
  không cắt lời, độ trễ lớn nhất **2284 ms**, 0 group cần review.
- LLM xử lý 131 outlier qua 180 response thành công. Hai câu gây dồn lời được
  Codex rút riêng ở bước cuối: 149 WAV dùng cache, 2 WAV mới, không gọi API thêm.
  Wording thay đổi ở tổng 121 nhóm; source video/SRT giữ nguyên. Không ASR/dịch lại.
- Render exit 0; FFprobe đúng stream/duration, decode toàn audio FFmpeg exit 0;
  worker/GPU lease đóng. User sau đó chấp nhận bản hiện tại ở mức “tạm ổn”.
- Trạng thái cuối `render-r2-state.json`, report `report-final-r2.json`; không
  chạy lại helper cũ. [Artifact, hash và cách tiếp tục](docs/dev/full-lecture-dubbing-2026-09.md).
  Không sửa code app/test/build/commit/push trong lượt xử lý media này.

## 2026-09-09 (giữ nhịp đọc đều theo phản hồi user, rút lời dài bằng LLM)

- User phản hồi bản tăng tốc riêng từng nhóm nghe không tự nhiên. Policy
  `sequential` nay giữ một hệ số tốc độ chung, ưu tiên 1,00×; gợi ý chỉ tăng nhẹ
  1,05× khi cần. LLM chỉ rewrite group vượt khung sau đo WAV, không pre-rewrite
  theo prediction; source/subtitle display giữ nguyên, context lân cận bất biến.
- Lượt thật scope g-0002/g-0003: 3 request terra, một rewrite hợp lệ (g-0003,
  WAV mới 6,6 s); g-0002 có hai response JSON không hợp lệ, giữ lời gốc. Key
  nhập kín chỉ trong RAM. Không gọi lại LLM/TTS đã xong.
- Preview `build/steady-dubbing-20260909/lecture-steady-preview.mp4`: **1,00×
  toàn đoạn, 0 speed adjustments, không overlap**, trễ lớn nhất **2120 ms**,
  giới hạn được chọn 2500 ms. Các đoạn khác giữ audio gốc; subtitle/hash giữ nguyên.
- 205 test liên quan pass; 24 test tập trung cuối pass, Ruff/pyright/sync pass.
  EXE Natural-Steady build exit 0, 6 warning/0 error; GUI 25 s/đóng exit 0.
  Frozen cached workflow exit 0, 1,00×/không overlap, không child sót; không
  inference lại khi tiếp tục sau lần ngắt.
  [Chi tiết và gate EXE](docs/dev/sequential-dubbing-2026-09.md). User chưa xác nhận
  chất lượng nghe bản nhịp đều; chưa chạy toàn bộ 180 cue. Không commit/push.

## 2026-09-09 (OmniVoice Local tích hợp cạnh VieNeu, có mẫu giọng và preview video)

- User cung cấp `k2-fsa/OmniVoice`. Provider GUI/CLI mới dùng API Python qua
  worker riêng; code pin `08be0b4c`, model pin `c5fdb5cc`. Có Prepare / resume,
  ngôn ngữ, auto/design voice hoặc reference audio + transcript; không cần key,
  không import GPU vào Qt, không tự tải Whisper. VieNeu giữ nguyên.
- Runtime Python 3.12/CUDA riêng đã cài và model tải/verify thật. Một câu tiếng
  Việt tạo WAV 4,75 s, synthesis 1,953 s sau load/verify 43,484 s. Preview video
  30 s từ bản dịch: 5 nhóm TTS thành công, dùng giọng tham chiếu tự sinh;
  Natural/allow-overlap, có hai nhóm vượt khung cần user nghe kiểm tra.
- 204 test liên quan pass; OmniVoice cuối 10 pass, Ruff/pyright/sync pass.
  EXE `VideoCaptioner-OmniVoice-20260909-R2` build exit 0, 6 warning/0 error;
  frozen cached workflow exit 0, 5 cache hits/0 generation mới, không child sót.
- [Cách dùng, giấy phép thành phần, hash và gate](docs/dev/omnivoice-local.md).
  Chưa lồng tiếng toàn bài giảng hoặc nghiệm thu giọng/timeline bằng người nghe.
  Giữ mọi thay đổi ASR/dịch và artifact cũ; không commit/push, OCR vẫn dừng.

## 2026-09-09 (dịch 180 câu bài giảng sang tiếng Việt theo yêu cầu user)

- Core LLMTranslator dùng gateway đã chốt + `gpt-5.6-terra`, timeout 300 s:
  **180/180 cue**, **7 request thành công / 155,844 s**. Chỉ gửi text, không
  nhận dạng/căn thời gian lại hoặc upload audio. Key nhập kín và chỉ giữ RAM.
- Có SRT tiếng Việt, SRT song ngữ Việt–Trung, TXT và JSON giữ metadata dưới
  evidence `practical-sentences-20260909/translation-vi/`. Validation đủ cue,
  timestamp giống nguyên bản, text gốc/ID/provenance/hash giữ nguyên; worker
  joined, process exit 0. [Chi tiết](docs/dev/asr-practical-sentences-2026-09.md).
- User kiểm tra bản dịch; chưa nghe đối chiếu tên riêng hoặc chấm chất lượng.
  Chưa dịch bằng nút GUI/EXE, synthesis/TTS. Không test/build/commit/push thêm.

## 2026-09-09 (phụ đề Qwen thực dụng + Whisper dự phòng đã xuất được bài giảng)

- User đồng ý triển khai hướng thực dụng. Policy câu mới bỏ yêu cầu duration
  từng token biên; legacy review/word strict giữ nguyên. Vùng lỗi được thay cả
  chữ/time bằng Whisper đã cài; có deadline/hủy/cache, metadata và thông báo.
- Bài giảng xuất **180 cue: 164 Qwen + 16 Whisper**; giữ Qwen 26 chunk đầu,
  Whisper vùng 713.100–771.029 ms gồm chunk 26–28 (thêm 27 làm ngữ cảnh cho đuôi).
  0 Qwen/aligner inference mới; một Whisper inference thành công 26,234 s.
- Source CLI exit 0; SRT/JSON roundtrip và editor adapter nhập đủ 180 cue.
  EXE Practical R2 build exit 0, 6 warning/0 error; frozen CLI dùng cache exit 0,
  SRT giống source, giữ GPU lease cấm inference, không child sót.
- 254 test khác nhau pass / 2 skip; Ruff pass, pyright 0/0, translations in sync.
  Chưa có % chính xác hoặc nghe thủ công bài giảng; không benchmark lại corpus,
  dịch, TTS hoặc tải model. [Báo cáo và các gate](docs/dev/asr-practical-sentences-2026-09.md).
- Giữ mọi tài liệu cũ, runtime/model/cache/media; không commit/push. OmniVoice
  Studio sau ASR, VieNeu giữ lại, OCR dừng.

## 2026-09-09 (user chốt tiêu chí thực dụng, dừng kiểm thử Qwen quá sâu)

- User chấp nhận nhận dạng tương đối **80–90%**, không yêu cầu 100%; ưu tiên luồng
  dùng được như Whisper. Cập nhật [kế hoạch](docs/plans/asr-completion-2026-09.md)
  và [bàn giao](docs/dev/asr-completion-next-session-prompt.md) để chỉ đạo mới thay
  thế các điều kiện acoustic quá nghiêm trước đây, không mở tiếp vòng benchmark.
- Tiêu chí tiếp tục: phụ đề câu/đoạn tương đối bám lời nói, có thể review; xử lý
  treo, mất chunk, timeline/output hỏng. Dùng raw/cache đã có, chỉ kiểm tra phần
  sửa và luồng thật. 80–90% là kỳ vọng, không phải kết quả đo đã được xác nhận.
- Lượt này chỉ đổi tài liệu/tiêu chí validation; code và EXE chưa đổi, Qwen SRT
  bài giảng vẫn chưa được tạo. Không inference/test/build lại, không commit/push.
  OmniVoice Studio sau ASR, bên cạnh VieNeu Local; OCR vẫn dừng.

## 2026-09-09 (bài giảng: đủ raw 29 chunk, năm chunk timing còn bị chặn)

- Tiếp tục **b102ae9**, giữ năm tài liệu đầu phiên; [báo cáo mới](docs/dev/asr-lecture-complete-alignment-2026-09.md).
- Căn nốt **20 chunk chưa từng alignment**, dùng lại chín raw đầu; **0 recognition**.
  Full TXT 4.783 ký tự giữ nguyên. Host exit 0 / 14,844 s, load 8,609 s,
  request alignment 3,002 s; không coi đây là benchmark ASR toàn video.
- Policy sản phẩm có **24/29 chunk** qua geometry/energy, còn lỗi tại index
  **8, 12, 26, 27, 28** (zero-duration/overlap). Chưa acoustic acceptance/SRT/LLM.
- Thử quy tắc text ưu tiên dấu phẩy trước cap 40: giải phóng hai chunk nhưng
  làm hai chunk khác fail, tổng vẫn 24/29. **Loại phương án**, khôi phục source
  đúng snapshot; không nới guard, chọn policy theo lỗi hoặc xuất SRT candidate.
- Evidence `cue-clauses-20260909/` giữ toàn raw/receipt/failure. Không nhận dạng
  hoặc alignment lại các chunk đã có. 72 file preservation pass, worker/lease đóng.
  App/cache/runtime/EXE không đổi, kế thừa 142 test/ResumeGuard; không test/build lại.
  OmniVoice sau ASR, VieNeu giữ nguyên; OCR dừng. Không commit/push.

## 2026-09-09 (video bài giảng mới: full TXT, SRT vẫn bị chặn)

- Tiếp tục **b102ae9**, giữ bốn tài liệu thay đổi từ lượt trước. User cung cấp
  video bài giảng tiếng Trung dài 12 phút 51 giây; [báo cáo mới](docs/dev/asr-lecture-onset-2026-09.md).
- CLI source Qwen 1.7B: đoạn 60 s exit 5 / 35,031 s, giữ TXT; end cuối vượt
  đoạn cắt 30 ms. Toàn video exit 5 / **118,016 s**, TXT **4.783 ký tự** nguyên
  review; 29 chunk, hai cache reuse + 27 request mới đều EOS, không stall.
  Recognition request 90,750 s, load hai model 18,251 s; không coi thời gian
  có cache reuse là benchmark mới. Chưa reference/CER cho video này.
- Timing toàn video dừng ở chunk **220.850–248.900 ms**, token biên
  `token-001149` có start=end **228.050 ms**; 20 chunk sau chưa gọi aligner.
  Không clamp/nới guard; chưa SRT/LLM. Cache/raw/text đã có để tiếp tục.
- Phép đo lexical audio ablation trên mẫu cũ không đủ điều kiện tích hợp;
  25 encoder/decoder requests, không lặp native/DTW hoặc Qwen recognition.
  Process đóng, preservation pass. App/runtime/EXE/dịch không đổi, kế thừa
  142 test/ResumeGuard, không test/build lại. OmniVoice sau ASR; OCR dừng.

## 2026-09-09 (native timestamp head: onset tiến triển, audio-shift control fail)

- Tiếp tục đúng **b102ae9**, working tree đầu phiên sạch; không reset/commit/push.
  [Báo cáo mới](docs/dev/asr-native-timestamp-control-2026-09.md): timestamp-token
  head của Whisper được condition bằng chính text Qwen cached; không direct DTW
  hoặc nhận dạng lại. Hai onset chuyển tới 44.150 / 49.150 ms, nhưng **6/8 biên
  fail** đối chứng chèn gap +1 s, lệch 500 ms so với mức dịch chuyển dự kiến.
- Giữ logits/prefix/receipt và hai lỗi serialization helper; không sửa raw,
  tăng tolerance, xuất thêm SRT hoặc tích hợp. Validation `accepted=false`;
  mỗi lượt 41 file bảo vệ nguyên hash/mtime, process/lease đóng. **Qwen SRT và
  chuyển timing cho LLM vẫn chưa nghiệm thu.**
- 0 Qwen recognition/DTW/API/download; parent 88.950 ms và ba trace loop giữ
  nguyên. App/cache/runtime/translation config/EXE không đổi, kế thừa 142 test
  và ResumeGuard, không test/build lại. Quality/stall, tải mạng mới và GUI HTTP
  cancel/resume tiếp tục sau timing; OmniVoice sau ASR, OCR dừng.

## 2026-09-09 (chốt snapshot ResumeGuard và prompt tiếp tục theo yêu cầu user)

- User yêu cầu **submit/push và prompt next session**. Snapshot gom **30 file**
  code/test/tài liệu trên nền d2dc518, gồm sentence policy, tự chuẩn bị model,
  retry/cache, generation budget, GUI prepare/resume và ba báo cáo nghiệm thu.
  Commit subject: `feat(asr): add resumable model preparation and bounded recognition`.
- [Prompt bàn giao](docs/dev/asr-completion-next-session-prompt.md) dùng snapshot
  chứa chính nó làm mốc, không nhầm d2dc518 là HEAD sau commit. Giữ ưu tiên biên
  câu/đoạn có căn cứ audio; SRT candidate 9 cue chưa acoustic acceptance; ba
  request generation còn loop và một parent mask đã EOS không chạy lại.
- Lượt chốt chỉ rà diff/manifest, phạm vi dữ liệu và liên kết tài liệu; kế thừa
  142 test, Ruff/pyright/sync và EXE ResumeGuard. Không inference, test hoặc build
  mới. Build/dist, raw/candidate, cache, media, runtime và dữ liệu user giữ local.
- Quyền commit/push chỉ cho snapshot được yêu cầu, không tự áp dụng phiên sau.
  **ASR sản phẩm, tải model mới qua mạng và GUI HTTP cancel/resume vẫn chưa nghiệm
  thu**; OmniVoice Studio sau ASR và cần xác minh interface, OCR tiếp tục dừng.

## 2026-09-09 (direct Qwen-text alignment và generation trace; chưa nghiệm thu SRT)

- Tiếp tục d2dc518, giữ nguyên 29 file đầu phiên; không reset/commit/push.
  [Báo cáo và artifact review](docs/dev/asr-direct-alignment-stall-2026-09.md).
  **SRT thử nghiệm 9 cue đủ chữ đã có, nhưng chưa đạt acoustic acceptance**:
  direct Whisper DTW trên chính text Qwen đưa khoảng nghỉ vào hai đầu cue.
  Không tích hợp candidate, sửa raw/nới guard hoặc lặp sparse slots/crop cũ.
- Một forward speech + một silence control; dùng weights large-v3 đã có, tải
  riêng wheel CT2 19.470.040 byte vào evidence, không cài vào project/runtime.
  Geometry/energy và SRT roundtrip pass, **không phải gate CLI/GUI/LLM**.
- Mask recognition trên đúng bốn request stall: một request EOS **5,687 s**;
  ba request vẫn incomplete, trace lặp terminal pair 582/546/570 lần. Giữ output
  mới riêng và cache cũ; không cắt repetition để trả partial. Candidate ghép một
  parent vào TXT cached giảm CER một clip **61,44% → 60,21%**, cùng 975 ký tự
  reference; không chấm lại common-28 hoặc gọi quality/stall đã sửa.
- Process/lease đóng, preservation pass. Không đổi app source, runtime, cache,
  cấu hình dịch hoặc EXE. Kế thừa 142 test và ResumeGuard, không test/build lại.
  Tải model mới qua mạng, GUI HTTP cancel/resume và workflow đầy đủ vẫn mở;
  wheel thử nghiệm không là tải model. OmniVoice sau ASR; OCR dừng.

## 2026-09-09 (tiếp tục d2dc518: generation budget, GUI resume; timing vẫn mở)

- Kế thừa 25 file chưa commit, không reset/commit/push; [báo cáo mới](docs/dev/asr-stall-resume-2026-09.md).
  **Qwen SRT 60 s vẫn chưa đạt, OCR dừng.** Hai probe audio có contract riêng
  vẫn fail; giữ raw và không tích hợp/nới guard.
- Worker giới hạn token theo audio, bắt buộc EOS; exhaustion trả incomplete,
  giữ model cho retry <=15 s. Bốn request timeout ~181 s nay dừng ở
  **51,672–83,671 s**, cùng PID; 20 file bảo vệ nguyên hash/mtime. Chưa sửa
  quality/nguyên nhân generation; không suy RTF toàn file mới.
- Cache cũ cho cùng TXT trên hai clip khó/stress, 0 inference/download. Bridge
  bundle mới dùng interpreter/weights đã verify; giữ runtime/managed cũ.
- GUI thêm **Prepare / resume selected model**. Native Qt/QTest với model thật:
  hủy verify **31 ms**, tiếp tục **4,750 s**, reuse **5,250 s**; root giữ nguyên,
  không download. HTTP cancel/tải runtime mới vẫn chưa nghiệm thu.
- **142 test pass / 13,16 s**, Ruff pass, pyright 0/0, translations in sync;
  không full/corpus/API. EXE ResumeGuard build exit 0 / 214,516 s, 6 warning/
  0 ERROR; GUI sống 25 s, đóng đúng PID exit 0. Frozen Qwen TXT thực chạy 10 s
  audio, exit 0 / 27,812 s, 23 ký tự giữ nguyên, không child còn sống.
  Artifact/hash/gate chưa chạy ghi trong báo cáo; chưa Qwen SRT hoặc tải mạng mới.
  OmniVoice Studio vẫn sau ASR, phải xác minh dự án/interface chính thức.

## 2026-09-09 (sentence policy, chuẩn bị model và hoàn tất TXT file dài)

- Tiếp tục ASR-S3 / `codex/asr-s3-native` từ đúng **d2dc518**, đầu phiên sạch;
  không commit/push. [Báo cáo source/evidence/EXE](docs/dev/asr-sentence-preparation-2026-09.md).
  **Qwen SRT trên mẫu user vẫn chưa đạt; ASR sản phẩm chưa nghiệm thu. OCR dừng.**
- Thêm policy cue riêng với word strict: group theo text, giữ start/end token biên,
  kiểm tra audio biên và containment của mọi mốc raw; không min/max, sửa raw hoặc
  bỏ chữ. Review giữ policy/ID; cache raw tách khỏi output đã validate. Replay cũ
  **11/32 chunk** qua guard nhưng **0/8 cặp model/clip** có timing hoàn chỉnh.
- GUI/CLI Qwen tự chuẩn bị đúng model khi bắt đầu, TXT không cần aligner; có verify
  hash, staging riêng, OS lock, progress, hủy/resume, dùng lại model cũ. Cài qua mạng
  chưa đo vì runtime phù hợp đã có. Optional speaker lỗi giữ timed subtitle và
  pending, không chặn recognition hoặc gán giả từng chữ.
- Request nhận dạng tối đa 30 s, fallback cắt audio theo năng lượng giữ đủ sample;
  timeout retry một lần <=15 s, cache giữ chunk xong, partial không thành complete.
  **4/4 clip lỗi cũ nay xuất TXT**, CER thô **33,91–61,44%**. Stress **26,23 phút**
  hoàn tất TXT trong **432,422 s**, gồm 1 timeout; CER **44,27%**, RTF sau load có
  điều phối **0,261**, chưa đạt mục tiêu 0,25. Mẫu user mới vẫn TXT/review; không
  chấm lại common-28 hoặc đổi engine/LLM/model/lock. Không API/model download mới.
- Gate cuối liên quan **110 pass / 14,52 s**; lượt rộng 648 pass/5 fail đã có rerun
  45 pass sau sửa fixture cũ, gồm 1 Scribe timeout race không sửa app. Ruff pass,
  pyright 0/0, translations in sync. Chi tiết fail/deselected/giới hạn trong report.
- EXE **SentencePrep-20260909**: PyInstaller exit 0, 6 warning đáng chú ý/0 ERROR,
  EXE **31.184.350 byte**, SHA-256
  `22495164beef9977300c5bf5b83b6c31086f836fe4eb7a2d79eab58604a89f80`.
  GUI native sống 25 s, đóng đúng PID exit 0. Frozen TXT được xác nhận qua cache
  (helper lần đầu race sau khi đã tạo text); FWW sentence 10 s thực chạy, SRT hợp lệ,
  không còn child. Chưa GUI button workflow/cài mới qua mạng/Qwen SRT/media online.
  Giữ artifact TimingGuard, runtime/model, AppData và toàn bộ evidence cũ.

## 2026-09-09 (chốt snapshot speech-to-text và prompt tiếp tục)

- User yêu cầu **prompt next session, submit và push**. Snapshot từ nền
  **669c0da** gồm **17 file**: bảy code, ba test, README/status/prompt/plan và
  ba tài liệu audit Parakeet/attention/Qwen CTC đã có từ các lượt trước.
- [Prompt bàn giao](docs/dev/asr-completion-next-session-prompt.md) được rút gọn
  theo yêu cầu mới nhất: phụ đề vẫn cần timing câu/đoạn; TXT recovery bảo toàn
  recognition, chưa thay thế SRT. Ưu tiên tiếp theo là timing cue rồi tải model,
  file dài/tốc độ, người nói và EXE. Các audit cũ giữ trong báo cáo/evidence riêng.
- Kế thừa 226 test + kiểm tra UI cuối, ruff/pyright đã pass; lượt chốt chỉ rà
  manifest/diff, nội dung Git và liên kết. Không model/API/test/build mới.
  **Qwen timed output, tự tải model và EXE mới vẫn chưa hoàn tất; OCR dừng.**
- Quyền submit áp dụng cho snapshot này, không tự cho phép commit/push công việc
  của phiên tiếp theo. Build/dist/media/runtime/AppData giữ tại máy, không đưa lên Git.

## 2026-09-09 (speech-to-text độc lập với aligner, đổi ưu tiên nghiệm thu)

- User chốt ưu tiên **chữ đúng, nhanh, ổn định; người nói tùy chọn**, dịch giữ
  gpt-5.6-terra. Timestamp từng chữ không còn chặn acceptance của recognition.
  **User bổ sung: workflow phụ đề vẫn cần timestamp câu/đoạn.** TXT là bản giữ
  kết quả chữ; chưa coi TXT recovery là hoàn tất SRT/ASS hoặc đầu vào timed cho LLM.
  [So sánh model và plan hoàn thiện](docs/plans/asr-completion-2026-09.md).
- Qwen TXT trong GUI/CLI chỉ chạy nhận dạng, không cần aligner/Community-1. Timed
  export nhận dạng trước; aligner thiếu/lỗi vẫn giữ full text và xuất TXT riêng,
  không ghi đè file cũ. Standalone GUI trả TXT, không ép mở modal timing; pipeline
  cần SRT dừng riêng. CLI TXT exit 0, timed output chưa tạo được vẫn exit 5.
- Giữ raw/timestamp, nhận dạng partial/hủy không thành complete. Không đổi model/
  frontend/chunk/timeout/cache/default hoặc LLM; lỗi file dài cũ vẫn còn. Kế hoạch
  tiếp theo: timing câu/đoạn → tự tải model đang chọn → file dài/tốc độ → người
  nói → EXE mới. Fix này chưa làm Qwen xuất được SRT trên mọi input lỗi timing.
- **226 test offline local ASR/CLI/UI pass / 17,44 s**, gồm 13 case mới; ruff và
  pyright app pass (sửa import ordering). Chỉnh UI cuối bỏ modal được kiểm tra riêng.
  Không model inference/API mới, download weight, full suite, build/GUI EXE.
  EXE TimingGuard cũ chưa chứa fix; chỉ source được sửa, không commit/push.
- Kế thừa benchmark chữ: cùng 28 clip Qwen 1.7B **21,04% CER**, 0.6B **22,00%**,
  FWW large-v3 **36,74%**. Recognition 28/32, 28/32, 32/32; không nhầm timing
  fail với recognition fail. Chỉ tổng hợp evidence đã có, không chấm/chạy lại.
- **Fix trả transcript đã có ở source; ASR sản phẩm còn bước hoàn thiện. OCR dừng.**
  Giữ các tài liệu/audit cũ làm lịch sử, không tiếp tục chuỗi preflight aligner theo
  ưu tiên cũ. Những file thay đổi từ trước được giữ nguyên nội dung.

## 2026-09-09 (điều kiện head Qwen CTC sau probe attention)

- ASR-S3/`codex/asr-s3-native`, HEAD/tracking tại máy **669c0da**; giữ bốn thay
  đổi tài liệu cũ, không commit/push. [Báo cáo](docs/dev/asr-qwen-ctc-eligibility-2026-09.md),
  evidence riêng `VC-ASR-Completion-20260908-140534/s6-qwen-ctc-eligibility-20260909/`.
- Head JazerJu Qwen CTC pin **9c59b40add48e8ada2b9586f2d7763b8cdcb63e8** đủ
  class riêng cho **89/91** mẫu cũ; user 94 ký tự đủ, thiếu `滯` và `诶` ở tập
  đầy đủ. Hai chữ không có ID đơn trong tokenizer Qwen local, không chỉ bị compact
  pruning. Không ghép byte/chia subword/đổi script; **dừng trước weight**.
- Mapping conditional theo tokenizer local; training encoder revision/hash chưa
  xác minh. Example xuất span BPE và có bỏ ID/state; source frontend mặc định
  cắt input 30 s trong runtime hiện có. Chỉ rà AST/config, không acoustic probe,
  không suy thành lỗi S6 cũ hoặc sửa timestamp theo hằng số 1/13 s của wrapper.
- Contract/hash trước GET và coverage: **6 file nhỏ / 1.717.789 byte**; fetch
  exit 0, validation pass, **744 file bảo vệ / 110 nguồn** giữ hash/mtime. Coverage
  exit 1 ở bước in console Unicode sau khi lưu validation; giữ lỗi, không chấm lại.
  Source review exit 0. **0 weight / 0 inference / 0 API ASR-dịch**; app/runtime/
  artifact giữ nguyên, kế thừa 595 ASR/CLI + TimingGuard, không lặp gate cũ.
- **ASR chưa đạt; OCR dừng.** Không dispatch head này từ evidence hiện tại;
  reference dịch còn cần key mới nhập kín và các tiêu chí chất lượng vẫn mở.

## 2026-09-09 (audit mask encoder Qwen và probe acoustic giới hạn)

- Tiếp tục ASR-S3/`codex/asr-s3-native`, HEAD/tracking ref tại máy **669c0da**;
  giữ ba thay đổi tài liệu Parakeet đầu phiên, không commit/push.
  [Báo cáo](docs/dev/asr-qwen-attention-audit-2026-09.md), evidence riêng
  `VC-ASR-Completion-20260908-140534/s6-qwen-attention-audit-20260909/`.
- Xác nhận encoder Qwen có mask helper nhưng không nối vào layer; SDPA/eager
  bỏ qua `cu_seqlens`. CPU **12 attention + 24 encoder synthetic**: mask khớp
  oracle từng block, sai số tối đa **7,45e-9**, perturb block khác không còn ảnh
  hưởng block đầu. Không gọi synthetic là acoustic pass. Giữ hai lỗi setup/
  assertion; `run03` exit 0/11,078 s, **301 file bảo vệ** giữ hash/mtime.
- Chốt contract trước đúng **ba forward ForcedAligner** (user, một chunk meeting,
  silence), cùng checkpoint/BF16/SDPA/text/audio, chỉ nối mask trong RAM. User còn
  **5 item có cờ**, meeting **12**: cả hai **strict fail**, RMS chưa chạy; silence
  bị strict chặn. Giữ raw và logits 5.000 class; không sửa timestamp/giải tie.
- Host exit 0/16,953 s, validation pass, **340 file bảo vệ** giữ hash/mtime, process/
  lease đóng. **0 weight download / 0 API ASR-dịch**. Candidate chưa vào app/runtime;
  không lặp benchmark/scoring/full/static/build/GUI, kế thừa 595 ASR/CLI + TimingGuard.
- **ASR chưa đạt; OCR dừng.** Mask wiring chưa đủ giải quyết timing, không lặp probe
  hoặc sweep precision/window từ cùng bằng chứng. Dịch reference vẫn thiếu key mới
  nhập kín; các tiêu chí phồn thể/stress/xưng hô/sửa tay/genre vẫn mở.

## 2026-09-09 (khảo sát điều kiện Parakeet CTC, sau bàn giao 669c0da)

- Xác minh ASR-S3/`codex/asr-s3-native`: HEAD, tracking ref tại máy và remote
  branch đều **669c0da**, working tree ban đầu sạch. Không commit/push phiên mới.
  [Báo cáo](docs/dev/asr-parakeet-eligibility-2026-09.md), evidence mới
  `VC-ASR-Completion-20260908-140534/s6-parakeet-eligibility-20260908/`.
- Parakeet CTC Mandarin là head khác các ứng viên đã đo. Model gốc NGC yêu cầu
  đăng nhập; chưa xác minh tokenizer/checkpoint gốc. Chỉ chấm dictionary của bản
  chuyển đổi FluidInference pin **ad0da3a453ce93ae53263f9a757ad365ce90bd58**:
  **90/91** mẫu đủ nguyên chữ, target user đủ; thiếu bốn chữ phồn thể. Không gán
  kết quả/license/benchmark conversion cho NVIDIA gốc; **dừng trước weight**.
- Contract snapshot trước tải/coverage, đúng 91 ID/hash/số ký tự cũ. Tải **8 file
  metadata/card/vocabulary / 515.668 byte**; fetch/coverage exit 0, validation pass.
  **275 file bảo vệ** và **101 nguồn mẫu** giữ hash/mtime, inventory có thể giao.
  **0 weight / 0 inference / 0 API ASR-dịch**, không lặp preflight/scoring/decoder/
  parity/benchmark cũ hoặc full/static app/build/GUI. App/scorer/tests/dependency/
  runtime/media/AppData/artifact nguyên vẹn; kế thừa 595 ASR/CLI và TimingGuard.
- **ASR chưa đạt; OCR dừng.** Chưa có cơ sở acoustic dispatch mới; không đổi
  script/head để chữa coverage hoặc lặp dictionary conversion này. Reference dịch
  cần key mới nhập kín; các tiêu chí chất lượng còn mở như prompt bàn giao.

## 2026-09-08 (chốt các audit sau S6 và prompt phiên tiếp theo)

- User yêu cầu **commit/push và prompt next session**. Snapshot **chín file** từ
  nền `2f8e0a8` gồm dev scorer/test định vị entity, bốn báo cáo segmentation/parity/
  CTC preflight/decoder Qwen, cập nhật contract CTC, status và prompt bàn giao.
- [Prompt tiếp tục](docs/dev/asr-completion-next-session-prompt.md) phân biệt nền
  đo với HEAD bàn giao, ghi thứ tự đọc các audit mới và trạng thái evidence chỉ
  ở máy. **ASR chưa đạt; OCR dừng**; quyền submit này không áp dụng cho phiên sau.
- Lượt chốt chỉ rà manifest/diff, nội dung Git và liên kết tài liệu; kế thừa 12 test
  scorer, ruff/pyright scorer, audit validation và gate 595 ASR/CLI + TimingGuard.
  Không lặp model/API, scoring, full/static/build/GUI. Giữ evidence/media/runtime/
  AppData/artifact tại máy, không đưa vào commit hoặc đổi code ứng dụng.

## 2026-09-08 (audit decoder Qwen và phân loại raw S6)

- Tiếp tục ASR-S3/`codex/asr-s3-native`, HEAD **2f8e0a8**, giữ tám file thay đổi
  cũ; không commit/push. [Báo cáo](docs/dev/asr-qwen-decoder-audit-2026-09.md),
  evidence `VC-ASR-Completion-20260908-140534/s6-qwen-decoder-audit-20260908/`.
- Năm file Qwen decoder/utils/model/processor/config **khớp từng byte** với source
  upstream pin; revision model vẫn như runtime. CPU **12 case pass**: đủ 5.000
  class timestamp qua FP32/BF16 synthetic logits và ba bridge, sai số **0 ms**.
  Không lỗi làm tròn ms hoặc bản sửa upstream liên quan làm cơ sở inference mới;
  không suy synthetic decoder pass thành acoustic parity/ASR pass.
- Raw S6: mỗi nhánh **28/32 clip, 141 chunk**; Qwen 0.6B **533 zero / 77 reversed /
  588 overlap**, Qwen 1.7B **519 / 89 / 628**. Cờ có thể giao nhau; mọi endpoint
  nằm trên lưới 80 ms. User giữ sáu item có cờ, không sửa raw. Chỉ phân loại, không
  chấm lại CER/entity/strict/RMS hoặc giải thích mọi lỗi bằng một nguyên nhân.
- Tải **12 file nhỏ / 155.551 byte**. Lỗi setup selector AST ban đầu giữ riêng;
  `run02/validation.json` pass, CPU **exit 0 / 9,656 s**. **231 file bảo vệ** và
  **348 file nguồn raw** giữ hash/mtime (có thể giao nhau). **0 weight / 0 model
  inference / 0 API ASR-dịch**; không đổi app/scorer/tests/runtime/artifact hoặc
  lặp full/static/build/GUI. Gate 595 ASR/CLI và TimingGuard được kế thừa.
- **ASR chưa đạt; OCR dừng.** Chưa có cơ sở acoustic dispatch mới; dịch reference
  cần key mới nhập kín, không tìm credential cũ. Các tiêu chí chất lượng vẫn mở.

## 2026-09-08 (preflight OmniASR CTC v2 và FireRedASR2-AED)

- Tiếp tục đúng ASR-S3/`codex/asr-s3-native`, HEAD **2f8e0a8**, giữ bảy file thay
  đổi cũ; không commit/push. [Báo cáo](docs/dev/asr-ctc-second-preflight-2026-09.md),
  evidence `VC-ASR-Completion-20260908-140534/s6-ctc-second-preflight-20260908/`.
- Trên đúng 91 ID/hash/số ký tự preflight cũ: OmniASR CTC v2 đủ vocabulary **73/91**,
  FireRedASR2-AED **84/91**. Omni thiếu một ký tự target user; FireRed thiếu bốn chữ
  phồn thể và năm Latin thường. **Dừng cả hai trước tải weight**; không ghép head,
  đổi script/case hoặc unknown. Đủ dictionary không là acoustic/timing pass.
- Source pin cho thấy Omni CTC v2 dùng chung tokenizer giữa các size; FireRed có
  raw CTC nhưng wrapper sửa/kéo/chia đều timestamp, không phù hợp strict raw của
  job. Không mang wrapper vào app, không lặp SenseVoice/window/benchmark/scoring cũ.
- Contract snapshot trước tải/coverage; **17 file nhỏ / 532.893 byte**, receipts
  khớp. Validation pass: **195 file bảo vệ** và **100 file nguồn mẫu** giữ hash/mtime
  (có thể giao nhau). **0 weight download / 0 model inference / 0 API ASR-dịch**;
  chỉ HTTP GET công khai metadata/code. App/scorer/tests/dependency/runtime/artifact
  giữ nguyên, kế thừa 595 ASR/CLI + TimingGuard, không lặp full/static/build/GUI.
- **ASR chưa đạt; OCR dừng.** Chưa có ứng viên acoustic đủ cơ sở dispatch. Dịch
  reference chưa key mới; phồn thể, stress quality, xưng hô, sửa tay và genre còn mở.

## 2026-09-08 (audit parity acoustic và mở rộng rubric số/đơn vị)

- Tiếp tục ASR-S3, HEAD **2f8e0a8**, nhánh tracking đúng; giữ sáu file thay đổi của
  lượt trước. [Báo cáo mới](docs/dev/asr-acoustic-parity-2026-09.md), evidence
  `VC-ASR-Completion-20260908-140534/s6-acoustic-parity-20260908/`. **ASR chưa đạt;
  OCR vẫn dừng**, không commit/push hoặc đổi default.
- Audit CPU **54/54** feature khớp từng bit với frontend upstream pin và phép LFR
  độc lập, max error **0**. AST encoder khác cách đặt maxlen của mask, không ảnh
  hưởng single input không padding của pilot. Chưa có căn cứ lỗi frontend/encoder
  để dispatch acoustic khác; không lặp SenseVoice/window sweep. Process **exit 0 /
  10,844 s**, không load weight; 0 acoustic inference mới.
- Rà reference 32 clip, 125 ứng viên số kèm đơn vị; đóng băng **79 nhãn / 11 clip**,
  65 vị trí mới và 14 trùng bộ cũ; giữ 46 mục ngoài phạm vi/chưa chấm cùng lý do.
  Cùng 54 ID có recognition đầy đủ: Qwen 0.6B **40 khớp / 4 ambiguous**, Qwen 1.7B
  **48 / 1**, FWW word/sentence cùng **40 / 10**. 25 nhãn khác thiếu Qwen output;
  không dùng denominators khác nhau để chọn engine. Đây là textual correspondence,
  chưa là full entity/value/speaker accuracy; giữ giới hạn ký hiệu phần trăm.
- Evidence validation pass; 67 file nguồn và 51 file bảo vệ cũ giữ hash/mtime
  (hai inventory có thể giao nhau). Chỉ thêm report/harness riêng và cập nhật tài
  liệu; không sửa app/scorer/tests/runtime/artifact. Kế thừa 595 ASR/CLI và EXE
  TimingGuard, không rerun full/static app/build/GUI/API. Reference dịch 0 request,
  chưa key mới; acoustic/phồn thể, stress, xưng hô, sửa tay và genre/dialect còn mở.

## 2026-09-08 (kiểm tra segmentation CTC và định vị nhãn tên/số)

- Tiếp tục checkout ASR-S3, `codex/asr-s3-native`, HEAD **2f8e0a8**, trạng thái đầu
  sạch. [Báo cáo mới](docs/dev/asr-ctc-segmentation-audit-2026-09.md); evidence riêng
  `VC-ASR-Completion-20260908-140534/s6-alignment-audit-20260908/`. **ASR chưa đạt;
  OCR vẫn dừng**, không commit/push hoặc đổi engine mặc định.
- Chốt contract trước một thử nghiệm mới: cùng 60 s/960.000 sample và nguyên target
  94 ký tự; chỉ chia acoustic thành 4 × 15 s rồi ghép emissions, không chia/đổi text.
  Frame hỗ trợ tăng **2/94 → 37/94**, blank **99,8% → 96,2%**; cửa sổ cuối toàn blank.
  Strict/RMS pass không đủ acoustic acceptance: **57 target chưa có frame hỗ trợ**.
  Không tích hợp backend, sửa raw hoặc thử thêm window tùy tiện. Host **exit 0 /
  8,437 s**, worker **4,203 s**, peak CUDA allocated **1.011.769.344 byte**; process
  và lease đóng, model/runtime/raw/input giữ hash/mtime. Chỉ bốn acoustic inference.
- Thêm dev scorer `scripts/asr_entity_acceptance.py`: định vị nhãn bằng mọi đường
  Levenshtein tối thiểu, giữ ambiguity và rubric số tường minh; không dùng dò literal
  nơi khác trong clip làm pass. 21 nhãn cũ: mỗi Qwen **15/18** nhãn có output đầy đủ
  khớp tại vị trí, 3 chưa chấm; FWW word/sentence cùng **17/21**, gồm sáu dạng digits
  tương đương. Chưa là speaker/entity accuracy toàn corpus; không đổi CER/ASR text.
- 12 test mới pass / 0,35 s (đối chiếu 225 cặp chuỗi với mọi edit path), ruff hai file
  mới pass, pyright scorer 0/0 bằng Python project đã có; không lặp full,
  ASR/CLI, build, EXE smoke hoặc gateway đã đo. Không đổi code app/dependency/resource.
  Reference dịch chưa có key mới, 0 API request; còn acoustic/phồn thể, stress quality,
  nhãn đầy đủ, xưng hô, phút sửa tay và genre/dialect.

## 2026-09-08 (chốt ASR/S6 và prompt tiếp tục theo yêu cầu user)

- User yêu cầu **commit/push và prompt sang session sau**. Snapshot 28 file từ nền
  `63941a8` gồm code ASR/CLI/translation guards, regression, công cụ chấm reference,
  báo cáo S6/CTC và tài liệu bàn giao; thay đổi OCR chỉ giữ trạng thái dừng.
- [Prompt tiếp tục](docs/dev/asr-completion-next-session-prompt.md) phân biệt commit
  bàn giao với ghi chú chưa commit trong lịch sử; giữ **ASR chưa đạt nghiệm thu**,
  endpoint/model/scope, raw evidence và các giới hạn acoustic/quality còn mở.
- Chỉ kiểm tra manifest, diff, nội dung đưa lên Git và liên kết tài liệu cho lượt chốt;
  kế thừa 595 ASR/CLI pass, ruff/pyright và frozen TimingGuard đã đo. Không chạy lại
  full/static/build/model/API hoặc đưa build/dist/media/runtime/AppData vào Git.
- Quyền submit này chốt snapshot hiện tại; không tự cho phép commit/push công việc
  của phiên sau, tạo tag/release hoặc chuyển sang OCR.

## 2026-09-08 (sau S6: đo sentence/stress, CTC chưa đạt; guard interval và EXE mới)

- Tiếp tục đúng `codex/asr-s3-native`, nền `63941a8`; giữ thay đổi cũ, không commit/push.
  [Báo cáo tiếp nối](docs/dev/asr-s6-followup-2026-09.md), evidence mới trong
  `VC-ASR-Completion-20260908-140534/s6-followup-20260908-204000/`. OCR vẫn dừng.
- User giải phóng GPU; đo 31 clip sentence mới và stress, tái dùng một frozen output
  cũ. Corpus 1.093 cue: **31/32** clip có mọi interval hợp lệ; CER cùng 28 **36,78%**,
  đủ 32 **40,53%**. Biên 35/1.673 utterance khớp: median **185 ms**, p95 **530 ms**;
  không so như cùng tập 30 word-mode utterance cũ. Stress 26,2308 phút có 617 cue
  dương/trong bounds nhưng CER thô **64,94%**, đuôi 22.897 ms chưa gán nhãn: chưa
  đạt chất lượng. Batch **exit 0 / 1.949,984 s**; không gọi đây là full app pipeline.
- [Contract CTC](docs/dev/asr-ctc-candidate-2026-09.md) pin trước tải/inference.
  SenseVoiceSmall có đủ ký tự 91 mẫu, tải một weight đã so SHA vào evidence riêng;
  không cài gói hoặc đổi runtime. Pilot giữ raw logits/path: phồn thể/user qua strict
  và RMS nhưng chỉ **9/13 / 2/94** target có frame argmax hỗ trợ; user 99,8% blank.
  Meeting chỉ một trong năm chunk qua cả guard; negative silence bị chặn. **Chưa
  đạt acoustic acceptance, không đưa backend vào app hoặc sửa script/timestamp.**
- Sentence `R8008_M8013-c04` có cue **10.870→10.870 ms**. Sửa FWW chặn `start >= end`
  trước lọc marker, ở cả hai mode; không publish prefix hoặc bỏ cue để pass. Regression
  **6 red → green**, tổng **8 pass**; ASR/CLI **595 pass / 13 deselect / 43,80 s**.
  Ruff pass, pyright **0/0** với Python project được chỉ rõ; lượt thiếu `.venv` ban đầu
  là setup failure. Không lặp full/sync/API; không đổi dependency hoặc resource.
- EXE **VideoCaptioner-ASR-S6-TimingGuard-20260908**: build **exit 0 / 215,141 s**,
  sáu optional/platform warning, 0 error, sáu SyntaxWarning; **218 module/PYZ khớp**.
  EXE **31.164.833 byte**, SHA-256
  **cdfecfafe7009129e2446923ddbe515db8b121b06f2b72808031ee2ccb4a093a**.
  GUI **25,594 s / exit 0**; frozen raw replay lỗi sentence/word đều **exit 5, không
  output**, hợp lệ **exit 0 / 22 cue** giữ text/timing. Ba fixture replay, **0 model/API
  request**; artifact gốc giữ nguyên, bản smoke riêng, không chạm junction cũ bị chặn.
- Có 21 nhãn tên/số chẩn đoán và rubric Việt cho 12 câu reference; chưa là điểm chất
  lượng độc lập. Sáu cờ số của FWW là khác dạng chữ số, không tự tính thành sai giá trị.
  Dịch reference vẫn **0 request/no key**; còn acoustic timing, tên nhân vật/xưng hô,
  phút sửa tay và genre/dialect. **ASR chưa hoàn tất nghiệm thu.**
- Theo câu hỏi user, đã xác nhận model FWW hiện tại là **large-v3 FP16, model.bin
  3.087.284.237 byte (2,88 GiB)**; không cần tải thêm chỉ vì tên “Whisper 3 GB”.

## 2026-09-08 (đã đo S6 local; sửa CLI/sentence/model window; chưa nghiệm thu)

- User chọn public corpus + clip hiện có. AliMeeting Eval đã tải/CRC64/gzip pass;
  chuẩn bị **32 clip / 66,9079 phút** từ tám recording, không bung toàn archive.
  [Báo cáo S6](docs/dev/asr-s6-results-2026-09.md) là kết quả hiện tại;
  [prompt ASR](docs/dev/asr-completion-next-session-prompt.md) đã cập nhật. OCR vẫn dừng.
- Qwen 0.6B và 1.7B đều có transcript đủ ở **28/32**; CER cùng 28 clip **22,00% /
  21,04%**. Một timeout và ba preflight không có khoảng ngắt; strict alignment
  **0/28 đạt** cho cả hai. Faster-Whisper có text 32/32, CER cùng tập **36,74%**;
  word timing chỉ **5/32** có mọi interval hợp lệ. Không suy default mới từ các số này.
- Community-1 có 11 response kéo sang phần đệm cuối. Đã sửa giới hạn theo window
  10 s/hop 1 s của model pin và số sample thực; giữ nguyên raw span, cue/word timing,
  threshold 80% và runtime. Replay **32/32** pass adapter. DER raw trong UEM toàn bộ:
  **20,66%** không collar, **14,90%** collar tổng 250 ms, có overlap. Không xác nhận danh tính.
- CLI hỗ trợ chọn Faster-Whisper với executable/model directory tường minh; không
  lệ thuộc PATH hoặc tự thay executable đã chọn. `process --no-split` dùng sentence
  timing khi chỉ dịch/optimize; native FWW boundaries không bị display timing cũ đổi.
- Full sau model-window fix **1.187 pass / 5 skip / 51 deselect / 114,72 s**; sau sửa
  cuối giữ native boundaries, regression red→green và ASR/CLI **587 pass / 13 deselect /
  38,88 s**. Ruff/pyright/sync pass. Không đổi dependency hoặc chính sách strict word.
- EXE **VideoCaptioner-ASR-S6-Review-20260908**: build exit 0 / 208,719 s, 6 optional
  warnings, 0 error, 6 SyntaxWarning; 218 module/PYZ khớp. EXE 31.164.611 byte,
  SHA-256 **c9604ea57d8e34bfb267f5191ec6b719e5cb72eec206d4d4d2a483d51e730426**.
  GUI 25,844 s/exit 0. Process user WAV → native sentence → replay bản dịch đã đo →
  SRT Việt: **exit 0 / 29,25 s / 9 cue**, child one_word=0, sentence=true, không API mới.
  SRT trùng hash bản đã render nên không lặp synthesis. Corpus sentence smoke:
  **58 cue hợp lệ / 69,938 s**; EXE local-diarize **31,219 s**, giữ text/timing/IDs/identity.
- Film text chấm trên bản chép caption cũ: CER 0.6B **12,77%**, 1.7B **6,38%**,
  FWW **7,45%**; không dùng caption visibility làm acoustic timing. Bản Việt vẫn
  truyền lỗi ASR về tước hiệu/thuật ngữ/câu hỏi. Không có nghiệm thu ngôn ngữ toàn tuyến.
- Phép đo dịch mới trên 12 câu reference đã chuẩn bị, ô key kết thúc chưa có key,
  **0 request**. Gate gateway cũ 9 cue/11.190 token giữ nguyên, không gọi lại hoặc xin Scribe.
- Stress 26 phút chưa pass; speech-gap trên user clip không chữa được strict timing.
  Còn alignment thay thế, quality/genre/pronoun/reference và phút sửa tay. **ASR chưa
  hoàn tất nghiệm thu; không chuyển OCR, không tự commit/push.**
- Đã dọn tiếp 10 mục build/test tạm (1.824 file / 356.069.728 byte) vào Thùng rác,
  giữ source snapshot/diagnostics đã nén và so hash. Bộ duyệt tự động chặn gỡ junction
  của `s6-final-build/smoke-app`; giữ nguyên host/link đó và mọi artifact, không đổi
  sang lệnh xóa khác để vượt chặn. Media/AppData thật/runtime giữ nguyên.

## 2026-09-08 (S6 được chọn nguồn; sửa gom cue trước gán speaker)

- User đã chọn **corpus công khai + clip hiện có** để hoàn tất ASR trước OCR. Đang
  tải AliMeeting Eval từ nguồn OpenSLR119, dùng một bản dưới root evidence. File
  `.partial` có kích thước cấp sẵn, **không chứng minh tải xong**; trạng thái/receipt
  nằm ở `datasets/AliMeeting-Eval/range-state.json`. Không đổi scope thành Scribe
  hoặc gửi corpus sang LLM trả phí khi chưa có job/credential tương ứng.
- Sửa ngắt câu local diarization: gom word theo punctuation/gap/provenance và chỉ
  nối khi toàn khoảng cue không có quá một speaker, rồi đo coverage ở cấp cue.
  Ngưỡng 80% giữ nguyên; không nối qua turn/overlap/người chen trong khoảng trống.
  Word mode, cue có context hoặc bản dịch giữ ranh giới. Không đổi text/token IDs,
  timing gốc, manual override, audio identity hoặc engine/model pin.
- Replay từ 88 word + 13 span đã lưu: **30 → 9 cue; 15 → 0 cue một chữ**. Kết quả
  mới **3 assigned / 6 unknown ở cấp câu**; không nhầm với 71/17 ở cấp word hoặc
  suy speaker accuracy tăng. Không inference/API lại. Evidence `cue-assembly-replay.json`,
  output `faster-hybrid-readable.json` trong job ASR Completion hiện có.
- Test gần **184 pass / 14,31 s**, sau đó thêm case mixed timing. Full sau thay đổi
  **1.156 pass / 5 skip / 51 deselect / 110,49 s**; ruff, pyright 0/0 và translation
  sync pass. Artifact TranslationGuard trước đó chưa chứa sửa gom cue này.
- Artifact mới **VideoCaptioner-ASR-CueAssembly-20260908**: build **exit 0 / 190,921 s**,
  6 optional/platform warning, 0 error, 6 upstream SyntaxWarning; 218 module/PYZ khớp.
  EXE **31.162.855 byte**, SHA-256
  **87d357843622dfb187e69080a04f5b6015527d81af155995d3d1eb9cbd9c69b4**.
  EXE replay word đã lưu qua loopback + Community-1 thật **exit 0 / 30,25 s**, đúng 9 cue,
  text/timing/identity/pending đúng. Không ASR/API trả phí lại. GUI **25,453 s**, đóng
  đúng PID exit 0. Sáu mục temp/build/test (1.478 file / 408.518.136 byte) đã vào Thùng
  rác; giữ diagnostics đã so hash, artifact/media/runtime. Code chưa commit/push.
- Thêm `scripts/asr_acceptance.py`: đọc TextGrid dài với quote/multiline đúng,
  CER giữ script/case/numbers và DER có overlap/global speaker mapping. **18 test**;
  đối chiếu DER trên raw tutorial tiếng Anh cũ khớp pyannote.metrics: 5,2033% không
  collar; 1,31685% collar tổng 250 ms quanh biên. Đây không phải nghiệm thu Trung S6.
  Bộ chọn clip giữ ranh giới utterance, chuẩn bị kênh đầu far-field theo recipe công
  khai; chưa có kết quả corpus nên chưa chọn mặc định hoặc gọi ASR hoàn tất.
- Bổ sung timing score chỉ trên full utterance khớp duy nhất và đúng ranh giới word,
  báo coverage cùng median/p95; không nội suy timing chữ từ nhãn câu. Metrics hiện
  **24 test pass / 1,14 s** (full 1.156 phía trên có trước sáu test timing bổ sung).
- Stress public **26,2308 phút**, Qwen 1.7B/chunk 120 s mặc định: **exit 5 / 443,969 s**,
  lỗi inference, chưa output/review. Cache job xác nhận bốn chunk đầu đã nhận dạng,
  lỗi ở vùng **464,2–581,65 s**. Thử riêng vùng đó với chunk tối đa 30 s: **5/5 đoạn
  nhận dạng xong / 31,813 s** gồm load, chưa alignment. Dùng 30 s làm cấu hình ứng viên
  cho corpus; chưa đổi mặc định hoặc coi toàn stress đã pass. Giữ cache/raw/lỗi cũ.
- Nhãn AliMeeting đã đọc đủ tám bản ghi. TextGrid xmax là cuối vùng gán nhãn, có thể
  ngắn hơn audio (bản đầu có đuôi 22,897 s ngoài nhãn); không đổi offset/scale để ép
  hai duration bằng nhau. Chọn clip trong vùng nhãn, stress giữ audio đầy đủ và đánh
  dấu đuôi ngoài vùng chấm. Setup guard chuẩn bị dữ liệu đã sửa theo khác biệt này.

## 2026-09-08 (ASR trước OCR; bỏ Scribe; sửa guard dịch thiếu và build riêng)

- User yêu cầu **làm hết ASR rồi mới sang OCR**; OCR pilot tạm dừng. User bỏ nghiệm
  thu ElevenLabs/Scribe và chọn gateway **api.videocaptioner.cn / gpt-5.6-terra** cho
  dịch. [Prompt mới](docs/dev/asr-completion-next-session-prompt.md) thay thứ tự cũ;
  không tự commit/push code mới. ASR/S6 vẫn chưa hoàn tất, không lấy source/test pass
  hoặc hạng mục user bỏ qua làm nghiệm thu toàn sản phẩm.
- Qwen 1.7B đã cài, cùng mẫu 60 s/pin aligner/strict policy: source CLI **exit 5 /
  54,422 s**, 94 token, vẫn sáu vị trí timing lỗi như 0.6B. Chữ có cải thiện nhưng
  chưa chữa alignment; giữ raw/identity/pending, không clamp hoặc OCR thay ASR.
- Baseline Faster-Whisper large-v3 đã có: VAD off thêm chữ đầu clip/bốn cue 0 ms;
  VAD `silero_v4_fw` **exit 0 / 16,922 s**, 88 word / 94 ký tự, bounds/timing hợp lệ
  nhưng còn sai từ/tên. Core Community-1 **21,047 s**, 13 span / 3 nhãn, 71 assigned /
  17 unknown; giữ identity và xóa pending sau diarization. Gom sau đó có 30 cue, còn
  mảnh quá ngắn; chưa nghiệm thu speaker accuracy. Đây là các stage tường minh, không
  một lệnh full pipeline mới hoặc benchmark so tốc độ model.
- Dịch 9 cue gom trước diarization từ ASR thật bằng model user chọn: **exit 0 /
  159,11 s / 1 request**, timeout 300 s; giữ source/IDs/timing/metadata/identity/pending.
  Gateway báo **11.190 token** (10.879 prompt gồm 8.891 cached, 311 completion), chưa
  có giá thực. Key chỉ password/RAM, owner/worker đã thoát. Tên sai từ ASR còn trong
  bản Việt; directed pronoun rules chưa được chấm. Không xin/gọi lại key cho gate này.
- Sửa `llm_translator.py`: response còn thiếu/sai sau ba lần validate phải fail batch,
  không điền source text rồi cache như bản dịch thành công; namespace cache mới tránh
  đọc fallback cũ, không xóa cache user. Regression mới **4 red → green**, 1 repair/cache
  pass; gần + CLI **166 pass / 5,07 s**. Full **1.124 pass / 5 skip / 51 deselect /
  97,09 s**, ruff pass, pyright 0/0, translations sync. Không đổi ASR/alignment policy.
- Artifact **VideoCaptioner-ASR-TranslationGuard-20260908**: build **exit 0 / 186,313 s**,
  6 optional/platform warnings, 0 error, 6 upstream SyntaxWarning; **218 module/PYZ khớp**.
  EXE **31.161.608 byte**, local **14:57:10**, SHA-256
  **90c1abd9bd12aabe187243ee7b13468aeccf728bc9512b439672fb787a3d55a0**;
  onedir **575 file / 237.662.680 byte**, chỉ thiếu 5 generated resource pyc so với Lifetime.
- EXE loopback: malformed **3 request → exit 5 / không output**; response đủ **1 request
  → exit 0 / 2 cue**, không cache hỏng. GUI startup **25,546 s**, WM_CLOSE đúng PID,
  **exit 0**. Render bản ASR→Terra bằng EXE mới **exit 0 / 8,282 s**, ffprobe/frame pass;
  đây là bản giữ nguyên lỗi nguồn, không bản Việt biên tập từ hình. API job khởi động
  trước code fix; nhánh lỗi mới nghiệm thu bằng regression/EXE loopback, không paid rerun.
- Evidence giữ trong **VC-ASR-Completion-20260908-140534** dưới root evidence đã gom;
  media/runtime/model/binary gốc giữ nguyên. Ba lỗi setup baseline helper được ghi riêng,
  không tính exit 0 thiếu output là pass. Còn alignment/phồn thể, ngắt câu, chất lượng
  speaker/xưng hô và bộ nhãn S6; **không chuyển OCR hoặc tự commit/push**.
- Preflight CTC chỉ đọc metadata/vocab public của model Chinese dùng trong danh sách
  WhisperX: 3.503 mục, thiếu ký tự ở cả text Qwen 1.7B/reference/phồn thể. Không tải
  weight **1.276.296.151 byte**, không inference/đổi script để ép coverage. Đã khoanh
  AliMeeting/AISHELL-4 làm nguồn nhãn S6 và hỏi user chọn nguồn; chưa tải corpus.
  Sáu mục build/test tạm đã vào Thùng rác, metadata/log cần giữ được nén và so hash.

## 2026-09-08 (chốt tài liệu và prompt so sánh OCR local / AI đọc ảnh)

- User yêu cầu **prompt next session và submit/push**. Manifest từ baseline **fb2bfad**
  gồm status, implementation, prompt ASR Việt cũ, kế hoạch OCR và
  [prompt OCR mới](docs/dev/ocr-next-session-prompt.md); code Lifetime **e6c0074** không đổi.
- User thấy agent đọc ảnh tốt; giữ OCR local và AI đọc ảnh như hai lựa chọn, pilot
  cùng nội dung **13 crop** trước khi chọn mặc định. Hiện chỉ có contact sheet và
  video mẫu, chưa lưu 13 crop độc lập; prompt yêu cầu chuẩn bị đúng input chung, tách
  đọc chữ khỏi dịch, giữ số token/RSS chưa đo và quyền model/endpoint cho job có phí.
- Làm rõ theo câu hỏi của user: **plan ASR đã có, triển khai/nghiệm thu chưa hoàn tất**.
  S1–S5/S5.2 có code; 60 s clip thực tế còn fail, OCR-0 mới là kế hoạch; S6 chưa giao.
- Quyền commit/push lần này chỉ chốt manifest hiện tại, không tự khởi chạy phiên,
  pilot, tải model hoặc cho phép submit thay đổi mới. Chỉ kiểm tra Git/diff/link/scan
  tài liệu; không lặp full/static/build/API/media hoặc thay runtime/artifact/data.

## 2026-09-08 (thống kê prototype và lập kế hoạch OCR phụ đề video)

- Theo yêu cầu user, hoàn thành **OCR-0: thống kê và thiết kế**, lưu tại
  [kế hoạch tích hợp OCR](docs/plans/video-subtitle-ocr-integration-plan.md).
  Prototype chỉ tự động quét/gom thời gian; **agent đọc chữ, chưa chạy engine OCR**.
- Tổng hợp evidence có sẵn: 60 s, khoảng **1.500 mẫu danh nghĩa** ở 25 mẫu/s, 13 cue /
  94 ký tự; ROI đúng loại dải hình chuyển động gây 33 nhóm ở lượt đầu. Lệnh quét cuối
  **2,664 s** chưa gồm engine đọc chữ; token agent/RSS đỉnh chưa có phép đo riêng.
  Không diễn giải 40 ms lưới mẫu thành sai số timing hoặc 99,13% giảm ảnh thành giảm token.
- Đề xuất RapidOCR + ONNX CPU trong runtime riêng, PTS-aware streaming, typed visual
  identity/metadata, review và nối bảng phụ đề/editor. Năm gói OCR-0→OCR-4; **OCR-1 trở
  đi chưa làm**. Không dùng AudioIdentity cho OCR, không đổi strict ASR hoặc mặc định engine.
- Report thống kê mới giữ trong job evidence hiện có; không quét media/inference lại,
  cài dependency/model, build, tạo thư mục cạnh checkout, S6 hoặc commit/push.
  Chỉ thêm plan và cập nhật ba tài liệu bàn giao; diff/scan/link kiểm tra khi bàn giao.

## 2026-09-08 (clip user chọn: ASR chưa đạt; có bản Việt đối chiếu 60 giây)

- User cung cấp một video cụ thể dài **111,333 s**; thử **60 s đầu**, không quét media
  hoặc mở corpus S6. Input **960.000 sample**, giữ hash/mtime file gốc. Evidence nằm tại
  **`build/asr-session-evidence/VC-UserClip-20260908-114035/`**, không transcript/media vào Git.
- Một job **EXE Lifetime / Qwen 0.6B**, **exit 5 / 46,375 s**: nhận dạng **94 token**,
  raw lexical khớp text ASR nhưng strict alignment chặn **6 token** (32, 35, 49, 73, 76,
  94): hai zero-duration, hai interval đảo, ba overlap có một token thuộc hai loại.
  Giữ review/identity, **0 override**, pending true; **chưa chạy tới Community-1**.
  Đối chiếu chữ Trung trong hình còn thấy ASR nghe sai. Không nhận dạng lại/đổi model/policy.
- Tạo **bản đối chiếu riêng 13 cue** từ phụ đề Trung có sẵn trong hình, agent đọc và dịch;
  thời điểm hiển thị đo **25 mẫu/s, độ phân giải 40 ms**, không là acoustic word timing
  hoặc kết quả ASR đã pass. Google trên EXE **exit 0 / 15,047 s** nhưng sai vài thuật ngữ;
  giữ bản Google riêng. Export target-only **exit 0 / 0,312 s** giữ text/timing từ JSON.
  Export đầu mặc định song ngữ làm assertion helper sai; không dịch lại để sửa layout.
- Ghép **bản Việt biên tập** bằng app ASS renderer **exit 0 / 8,141 s**; ffprobe và
  frame trước/trong/sau cue pass, chữ Việt đủ dấu và tách dòng Trung gốc. Audio vẫn là
  nguồn gốc, không TTS. Bản Việt mới chưa có phản hồi user; 51,333 s còn lại chưa thử.
- Final verify giữ file nguồn/sample/review, identity, **580 hash bundle**, lease đã
  acquire/release lại, không process job/request temp/ASS persist. Đã dọn EXE + `_internal`
  bản test vào Thùng rác ngay sau lượt; artifact/runtime gốc giữ nguyên. Helper phân tích
  đầu thiếu NumPy, chuyển sang Pillow đã có; không cài dependency. Không sửa code sản phẩm,
  full/static/build hoặc gate cũ; giữ ba file tài liệu đã sửa, **chưa S6/commit/push**.

## 2026-09-08 (dọn dữ liệu thử và gom evidence theo yêu cầu user)

- Chuyển **390 mục / 20.441 file / 3,247 GiB** dữ liệu build/test và chín bản sao
  binary vào Thùng rác; xác minh đủ 390 mục, không gọi đây là dung lượng đã giải phóng.
  Giữ 10 artifact gốc, runtime/model, media, AppData thật và output/report nghiệm thu.
  Metadata của mười build work giữ trong ZIP **70 file**, đã đối chiếu hash từng entry.
- Gom bảy thư mục **VC-*** từ cạnh checkout vào **`build/asr-session-evidence/`**;
  **2.710 file** giữ SHA-256/size/mtime, không còn thư mục VC-* tại vị trí cũ. Mapping
  nằm trong `relocation-20260908.json`; prompt tiếp tục đã cập nhật nơi tìm evidence.
  Script/report cũ giữ nguyên nội dung và có thể còn đường dẫn lịch sử.
- Không đổi code, runtime/artifact hoặc chạy lại gate; chưa S6/commit/push.

## 2026-09-08 (chốt tài liệu và prompt sau nghiệm thu phụ đề Việt)

- User yêu cầu **commit/push và prompt next session**. Manifest chốt từ baseline **d820ca0**
  gồm **status.md**, **docs/dev/asr-implementation-2026-09.md** và
  **docs/dev/asr-vietnamese-next-session-prompt.md**; code Lifetime **e6c0074** giữ nguyên.
  Các dòng chưa commit/push dưới đây ghi thời điểm review trước yêu cầu này; quyền chốt tài
  liệu không tự áp dụng cho thay đổi phiên sau.
- [Prompt mới](docs/dev/asr-vietnamese-next-session-prompt.md) giữ mục tiêu Trung→Việt, user
  không biết tiếng Trung và đã chấp nhận bản Việt mẫu. Kế thừa dịch/export/synthesis trên
  Lifetime đã pass; giữ phồn thể token 7 đảo **2080→2000 ms** là chưa đạt, không đo lại cùng case
  hoặc phục hồi nợ raw chưa có. Scribe/nhiều speaker/xưng hô/SIP và S6 giữ đúng giới hạn.
- Fetch xác nhận local/remote cùng baseline; hai EXE giữ hash bàn giao. Chỉ kiểm tra manifest,
  diff/scan/link tài liệu trước chốt; không full/static/build/API/media lại. Không đổi dữ liệu,
  runtime/artifact hoặc tạo task/automation mới; chưa mở S6/tag/release.

## 2026-09-08 (tiếp tục: phụ đề Việt trên Lifetime EXE và chẩn đoán phồn thể)

- Giữ HEAD **d820ca0**, code Lifetime **e6c0074**, nhánh và hai thay đổi tài liệu trước đó.
  Scratch mới **VC-Lifetime-VI-Review-20260908-092244** chỉ copy EXE + `_internal`, **580 file /
  237.667.204 byte**, so hash từng file; AppData/config/cache/profile/temp/source-host riêng.
- **Google → JSON Việt trên EXE Lifetime pass**, **exit 0 / 2,219 s / 1 cue**, cache mới;
  giữ nguyên source text/cue ID/timing/speaker/provenance/identity/context/pending. **Cùng EXE
  xuất SRT Việt pass**, **exit 0 / 0,438 s**, text/timing khớp JSON **400–3680 ms**, không dịch
  hoặc ASR lại. Không upload audio hoặc gọi paid API.
- **Ghép phụ đề cứng bằng EXE pass**, app ASS renderer, **exit 0 / 1,063 s**. Input video mới
  là nền tổng hợp **960×540** + audio public gốc **4,204 s**; ffprobe audio/video/duration pass.
  Frame **0,16 / 1,5 / 3,92 s** lần lượt không chữ / chữ Việt đầy đủ dấu / hết chữ. Đây là app
  synthesis thật trên clip tổng hợp, khác viewing aid trước; không suy full video/corpus/S6.
  Chuỗi bằng chứng trên cùng Lifetime đã có ASR kế thừa → dịch/export/synthesis mới theo từng
  command, không chạy lại ASR hoặc gọi đây là một lệnh `process` mới xuyên suốt.
- **Phồn thể đã khoanh lỗi cụ thể bằng một request aligner local**: reference do agent chuẩn
  bị, audio cũ **67.263 sample**, pin **c7cbfc20…2b7**, `strict-raw-v1`, timeout **180 s**.
  Giữ raw trước validate: **13 token, lexical toàn câu đúng**, chỉ **token 7** có interval đảo
  **2080→2000 ms (−80 ms)**; không mất chữ/script. Validator chặn đúng `start < end` trong
  thông báo gộp, **phồn thể vẫn chưa đạt**, không swap/clamp/override hoặc xuất SRT ép pass.
  Diagnostic **48,297 s**, load **43,953 s**, inference **1,360 s**, exit 0 của helper thu bằng
  chứng không phải alignment accepted. Không benchmark hoặc nhận dạng lại.
- Runtime/reader đã đóng, lease acquire/release lại được, manifest/lock/bridge và audio nguyên
  vẹn. Final verify: **580 hash gốc/copy**, Final cũ và hash/mtime năm file evidence giữ nguyên;
  không process test/request temp hoặc ASS persist. Helper monitor ban đầu đếm nhầm Python
  launcher của chính nó; snapshot độc lập rỗng, sửa filter ancestor và verify pass, không rerun job.
- Chỉ sửa **status.md** và **docs/dev/asr-implementation-2026-09.md**; evidence/transcript/output
  mới giữ local. Diff-check/scan pass; không full/static/build/GUI/playback/cancel lại, không
  đổi code/dependency/model/policy hoặc media/AppData/runtime/artifact gốc. Giữ Scribe, chất
  lượng nhiều speaker/xưng hô và giới hạn SIP; **dừng review, chưa S6/commit/push**.

## 2026-09-08 (user làm rõ đầu ra tiếng Việt; dịch Google từ output Lifetime)

- Sau khi xem kết quả, user xác nhận **không có vấn đề với bản dịch mẫu**. Checkpoint bản Việt
  của clip **4,204 s / 1 cue** được chấp nhận; không mở rộng thành nghiệm thu video dài,
  nhiều người nói/xưng hô, đối chiếu chữ Trung hoặc cho phép bắt đầu S6/paid job/commit/push.
- User xác nhận **giọng đọc ổn**, đồng thời nói không biết tiếng Trung và muốn phụ đề **tiếng
  Việt dịch từ tiếng Trung**. Không coi đây là xác nhận text Trung/timing/speaker accuracy.
  Checkpoint tiếp theo phải đưa phụ đề Việt; agent tự đối chiếu phần nguồn Trung và kỹ thuật,
  không yêu cầu user chấm chữ Trung. Clip vẫn dùng audio Trung gốc, không phải TTS mới.
- Tạo SRT Việt biên tập trong phiên và preview riêng từ audio/output đã có; ghi rõ không phải
  kết quả translator của app. Sau đó agent dùng Google không cần key cho một lượt dịch public
  bằng **CLI command handler của source app**, config/AppData/cache/temp riêng; không dùng
  credential/paid job, không ASR/upload audio lại hoặc chạy EXE.
- **Google → JSON/SRT Việt pass**, command handler **exit 0 / 1,953 s / 1 cue**; kiểm tra
  translation không rỗng, giữ source text/IDs/timing/speaker/provenance/identity/context/pending.
  SRT target-only giữ **400–3680 ms**. Google dùng một từ diễn đạt chưa sát bằng phương án agent
  đề xuất; giữ nguyên output để review, không gọi exit 0 là chứng minh chất lượng ngôn ngữ chung.
- Render preview từ SRT Google thật + audio gốc bằng FFmpeg, ffprobe audio/video/duration pass;
  đã xem frame có dấu Việt, không cắt chữ. Đây là viewing aid ngoài app synthesis, không phải
  gate EXE/S6. Warning pydub thiếu FFmpeg trên PATH ở lượt dịch text-only không ảnh hưởng kết quả;
  render sau đó dùng FFmpeg hiện có bằng path tường minh, không cài dependency.
- Output/report mới giữ tại **VC-Vietnamese-Preview-20260908-091203**, không ghi đè output cũ.
  Chỉ sửa hai tài liệu status/implementation, giữ thay đổi review trước; diff-check/scan pass.
  Không lặp full/static/build/runtime, không đổi media/AppData/runtime/artifact gốc, không
  S6/commit/push. Job LLM có phí vẫn cần user chọn model/endpoint và nhập credential kín.

## 2026-09-08 (sau Lifetime: checkpoint chất lượng và rà phồn thể — dừng review)

- Tiếp tục đúng nhánh **codex/asr-s3-native**, HEAD bàn giao **d820ca0**, checkout sạch;
  **e6c0074** và **073510d** là ancestor. Không có diff code/tests/spec/dependency từ Lifetime
  đến HEAD. Đọc prompt post-Lifetime và evidence mới nhất, không phục hồi nợ Whisper 429,
  playback hoặc hủy decode binary đã pass.
- Đã đưa clip/audio public và JSON/SRT có sẵn cho một checkpoint text/timing/giọng nhất quán.
  **Chưa nhận phản hồi chất lượng của user**; một giọng không đủ nghiệm thu nhiều speaker/xưng hô.
  Audit chỉ đọc bằng Python **3.12.13**, **exit 0**: PCM identity **67.263 sample**, JSON/SRT
  khớp **1 cue / 13 token IDs / 400–3680 ms**. Hash và mtime của năm file evidence đã đọc giữ
  nguyên; EXE Lifetime **b2dfe869…b38a75f78**, Final **45761316…f91649** khớp bàn giao.
  Đây là đối chiếu output lưu sẵn, không phải lượt ASR/media acceptance mới.
- Rà phồn thể: report **S5-validation/strict-negative-smoke.json** ghi lỗi timing tổng hợp
  **zero-length/overlap/out-of-audio**, cùng revision aligner **c7cbfc20…2b7**. Report không
  lưu input chính xác, identity theo case hoặc raw spans; request debug còn lại có text rỗng,
  không thể dùng làm input phồn thể. Validator kiểm tra lexical từng token trước timing rồi
  dừng ở lỗi đầu, nên chưa xác định token/time lỗi hoặc coverage lexical toàn câu. Resume
  vẫn kiểm tra toàn text; sửa timing không khắc phục thiếu/đổi chữ. Không sửa policy/code.
- Chuẩn bị đặc tả một phép đo aligner riêng trên WAV public đã có, reference phồn thể tường
  minh, giữ raw trước validate để phân loại lexical/timing; **chưa chạy inference mới**.
  Scribe đã khoanh provider ElevenLabs / **scribe_v2** / route **speech-to-text** và cùng clip
  **4,204 s**, nhưng chưa được chọn hoặc nhập key đúng provider. SIP không có triệu chứng hoặc
  giả thuyết kiểm chứng mới; không mở stress/GUI loop.
- Evidence audit và đặc tả phép đo giữ local tại **VC-PostLifetime-Review-20260908-085948**.
  Chỉ cập nhật **status.md** và **docs/dev/asr-implementation-2026-09.md**; giữ full/static/build/
  runtime/playback/cancel là evidence kế thừa, không rerun. Diff-check/scan tài liệu mới pass;
  không đổi media/AppData/runtime/artifact, không S6/commit/push.

## 2026-09-08 (prompt bàn giao sau Lifetime; user yêu cầu chốt tài liệu)

- User yêu cầu prompt phiên tiếp theo, rồi yêu cầu submit/push tài liệu. Manifest chốt gồm
  **status.md**, **docs/dev/asr-implementation-2026-09.md** và
  **docs/dev/asr-post-lifetime-next-session-prompt.md**, từ baseline **16e410d**; code Lifetime
  **e6c0074** giữ nguyên. Các dòng “không commit/push” bên dưới mô tả thời điểm review trước
  yêu cầu chốt này; quyền submit hiện tại không tự áp dụng cho thay đổi ở phiên sau.
- [Prompt mới](docs/dev/asr-post-lifetime-next-session-prompt.md) cập nhật local hybrid,
  native playback và hủy decode trực tiếp trên Lifetime đều đã pass. Ưu tiên checkpoint chất
  lượng từ output/audio đã có và khoanh vùng gate còn mở; không lặp gate pass hoặc retry Whisper
  vì 429 cũ. Giữ Scribe/phồn thể/chất lượng/SIP ngắt quãng riêng, không mở S6.
- Lưu prompt không tạo phiên/task/automation. Không thay media/AppData/runtime/artifact hoặc
  dependency; không full/build/API mới chỉ để chốt tài liệu. Git/diff/scan kiểm tra trước submit.

## 2026-09-08 (Lifetime: hủy decode trực tiếp trên binary đã pass — dừng review)

- Theo yêu cầu tiếp tục, giữ HEAD **16e410d**, nhánh **codex/asr-s3-native** và hai thay đổi tài
  liệu của lượt trước. Scratch mới **VC-Lifetime-Cancel-20260908-0714**, chỉ copy EXE + `_internal/`,
  AppData/cache/temp/lease riêng; **580 file / 237.667.204 byte** khớp hash gốc trước/sau.
  Lifetime vẫn **b2dfe869…b38a75f78**, Final cũ **45761316…f91649**; không đổi runtime/media user.
- **Đã bổ sung gate còn thiếu: hủy kiểm tra nguồn giữa decode ngay trên EXE Lifetime.**
  Nguồn FFmpeg concat hữu hạn từ PCM tổng hợp, không network/model hoặc mock/delay decoder.
  FFmpeg PID **31208** đã chạy **13,618 s** trước click đóng review, sample process gần nhất
  **66 ms trước click** vẫn chạy. App gọi taskkill cho cây process của job; monitor 50 ms ghi
  toàn bộ child của lượt hủy biến mất sau **0,875 s** tính từ yêu cầu đóng qua UI tool.
  Lệnh click+capture trả về **0,483 s** (không phải đo riêng handler Qt); thư mục decode tạm đã dọn.
- GUI vẫn phản hồi; mở lại review, chạy worker mới xác minh FLAC khớp, lưu bằng native picker.
  Typed reload giữ nguyên raw/2 token/1 override/identity/pending. Không tự xuất kết quả từ lượt
  hủy hoặc đổi liên kết nguồn. Không signal lỗi muộn quan sát được trên GUI/log sau hủy.
- **PID 59068**, sống **374,719 s**, RSS trước đóng **202.395.648 byte**, đóng X **exit 0**.
  Sau hơn 25 s: không process test hoặc decode temp còn lại, không Application Error/WER mới
  khớp binary; log chỉ update-check, không traceback/InfoBar. Không tái hiện crash SIP.
- Chỉ cập nhật **status.md** và **docs/dev/asr-implementation-2026-09.md**; không sửa code,
  build/full/static/GPU/ASR/API mới hoặc dependency. Helper đọc evidence ban đầu lỗi encoding
  Windows, đã sửa UTF-8 và verify pass; không chạy lại workflow để che lỗi. Diff-check/scan mới
  pass trước bàn giao. Giữ Scribe/phồn thể strict/chất lượng người đọc và SIP ngắt quãng còn mở.
  **Dừng review, không S6/commit/push.**

## 2026-09-07 (agent nghiệm thu local/media trên Lifetime — dừng review)

- Tiếp tục đúng **codex/asr-s3-native**, HEAD **16e410d**, code Lifetime **e6c0074** và S5.2
  **073510d** là ancestor; checkout sạch đầu lượt. Chỉ cập nhật hai tài liệu trạng thái, không
  sửa code/dependency/model/policy, không build/full/API mới, S6 hoặc commit/push.
- Scratch mới chỉ copy EXE + `_internal/`: **580 file / 237.667.204 byte**. So SHA-256 toàn bộ
  file copy/gốc trước và sau GUI pass; Lifetime giữ **b2dfe869…b38a75f78**, Final cũ giữ
  **45761316…f91649**. Không copy AppData/media/log của artifact; runtime Qwen R2/Community-1
  dùng nguyên tại chỗ. Python **3.12.13**, import đúng checkout, FFmpeg/config/cache/temp/lease cô lập.
- **Lifetime Qwen 0.6B → strict alignment → Community-1 thật pass**, audio Trung public
  **4,204 s / 67.263 sample**. Status Qwen/aligner/Community-1 exit 0; health Qwen+aligner
  **55,171 s**, Community-1 **23,438 s**, đều exit 0, khác gate inference.
  Job **exit 0 / 40,844 s**, cache **MISS** (cache mới trống; sau job có đủ ba namespace),
  **1 cue / 13 token IDs / 400–3680 ms / 1 speaker assigned**, identity khớp và pending false.
  EXE xuất SRT **exit 0 / 0,281 s**, text/timing khớp JSON; không review/retry/clamp/token drop.
  Lease acquire/release lại pass, không bridge còn lại. Không dùng thời gian smoke so tốc độ.
- **Native source editor: 7 passed / 1 warning / 6,04 s / exit 0**, không skip; gồm H.264
  Play/seek, poster, selection/playhead/inspector, layout và timeline. **GUI Lifetime thật** phát
  video tổng hợp 12 s, frame/playhead tiến và inspector chuyển cue; seek **2.010 ms** rồi Play
  tiếp đúng frame. Sau hết video, seek cập nhật vị trí; frame mới xuất hiện khi Play tiếp.
  Lưu/mở lại project JSON+SRT giữ hai cue/IDs/text/timing và playhead **1.000 ms**, không ASS.
- Review GUI: mở fixture tổng hợp, FFmpeg xác minh FLAC khớp, save qua native picker rồi reopen;
  typed reload giữ raw/2 token/1 override/identity/pending. Reopen yêu cầu xác minh nguồn lại.
  Lượt tone dài trên binary đã decode xong **trước** khi đóng review, nên không tính là hủy
  giữa decode. Test bổ sung **source Qt native + FFmpeg thật** đóng dialog khi process decode
  đang chạy: close **0,016 s**, join/cleanup **0,578 s**, không late signal/worker/process sót,
  review không đổi. File chooser do harness cấp; decoder/worker/lifecycle không mock.
- **GUI Lifetime PID 69912** sống **696,797 s**, RSS snapshot **319.356.928 byte**, đóng X
  **exit 0**; sau đóng hơn 25 s không process/bridge còn lại, không Application Error/WER mới
  khớp artifact. Log chỉ update-check, không traceback/InfoBar. Đây là smoke mới, không chứng
  minh mọi crash SIP đã hết; hủy giữa decode trực tiếp trên binary vẫn chưa được quan sát.
- Đã chuẩn bị audio public, JSON/SRT thật và clip có phụ đề để user nghe/đọc chung tại checkpoint.
  **Chất lượng text/timing/speaker chưa có xác nhận của user**; clip một giọng không nghiệm thu
  speaker accuracy/xưng hô. Whisper pass vẫn thuộc Final cũ; không xin key/gọi lại API.
  Scribe/phồn thể strict và SIP ngắt quãng còn mở. Evidence chi tiết giữ local trong scratch
  **VC-Lifetime-Media-20260907-2334**; không đưa transcript/media/path riêng tư/credential vào Git.

## 2026-09-07 (chốt code GUI Lifetime và prompt phiên agent tự nghiệm thu)

- Theo yêu cầu user commit/push, code và kết quả nghiệm thu đã chốt thành
  **`e6c0074250df41b5da4b7eaa71b2e9f21e4adcab`**, parent **7e28895**, đúng 4 file trong manifest
  GUI Lifetime. Các dòng “không commit/push” ở phần đo bên dưới mô tả thời điểm trước yêu cầu submit.
- Trước commit: fetch xác nhận local/remote cùng baseline; ruff pass, pyright 0/0, translations/
  diff-check và scan credential/path pass. Hash EXE Lifetime **b2dfe869…b38a75f78** không đổi;
  giữ gate full **1.119 pass / 5 skip / 51 deselect**, không rerun full/API/build chỉ để chốt Git.
- [Prompt phiên tiếp theo](docs/dev/asr-lifetime-next-session-prompt.md) chuyển rõ sang agent tự
  kiểm thử kỹ thuật, chỉ gom checkpoint chất lượng/credential/quyết định có phí. Ưu tiên local
  media trên Lifetime và native playback/shutdown; giữ giới hạn SIP chưa tái hiện tất định,
  Scribe/phồn thể/speaker/xưng hô chưa nghiệm thu. Whisper Final đã pass, không tự gọi lại vì 429 cũ.
- Prompt chưa khởi chạy phiên mới; quyền submit lần này không tự áp dụng cho thay đổi ở phiên sau.
  Giữ nguyên media/AppData/runtime/artifact, không S6/tag/release hoặc dependency mới.

## 2026-09-07 (S5.2 GUI lifetime: sửa vòng đời Qt, build riêng, dừng review)

- User yêu cầu tiếp tục xử lý crash SIP sau phiên nghiệm thu. Giữ nhánh/HEAD **7e28895** và các
  thay đổi tài liệu trước đó; không commit/push/S6, không đổi dependency/model/runtime/artifact cũ.
- Đọc local crash dump đúng PID 52400, unwind bằng PE function tables: main thread đi qua
  QApplication destruction → SIP wrapper visitor → `sip_api_get_address` tại **0xe58e** trong
  lúc Python/SystemExit cleanup. Không còn coi thao tác Lưu là nguyên nhân đã chứng minh.
  **24 subprocess chẩn đoán trước sửa đều exit 0**; chưa tái hiện access violation tất định.
- Probe riêng đo được `FluentTranslator` tạm bị hủy ngay trong event loop và QApplication bị thu
  gom khi function entry point thoát. `ui/main.py` giữ application ở module scope, parent translator
  vào application; không tắt GC/SIP destructor, không thay exit code hoặc cleanup worker. Hai case
  regression VI/EN **fail trên code cũ, pass sau sửa**; hướng lifetime phù hợp tài liệu PyQt/SIP.
- Test gần **29 passed / 6,89 s**; **full offline 1.119 passed / 5 skipped / 51 deselected /
  145,95 s / exit 0**. Skip thêm QtMultimedia vì offscreen, cùng bốn TTS/service; không suy online.
  Ruff pass, pyright **0/0**, translations sync, diff-check pass. Full chạy với AppData/cache/config
  cô lập trước build; không sync/cài dependency. Không gọi rerun pass là chứng minh hết mọi lỗi SIP.
- Artifact riêng **`dist/VideoCaptioner-ASR-S52-Lifetime-20260907/`**, spec duy nhất, output/work/
  temp/cache mới: build **exit 0 / 234,437 s**, **6 WARNING optional/platform, 0 ERROR,
  6 SyntaxWarning upstream**. **218 module** trong PYZ khớp source; không thêm GPU vào base build.
  EXE **31.161.900 byte**, local **22:39:32**, SHA-256
  **`b2dfe8692266fd08dc2471f54838385b975c6ebfe0839d8aa1d5436b38a75f78`**;
  onedir **580 file / 237.667.204 byte**. Hash artifact S5.2 Final cũ vẫn đúng bàn giao.
- **GUI native trên bản copy cùng hash:** review lưu bằng native picker, xác minh FLAC/FFmpeg,
  xuất JSON và mở lại pass; editor đổi speaker Apply/undo/redo, lưu project JSON+SRT rồi mở lại pass.
  Reload typed giữ raw/IDs/timing/provenance/context confirmed/locked/pending, không tạo ASS.
  GUI sống **966,328 s**, RSS snapshot **255.377.408 byte**, đóng X **exit 0**, không process con;
  log chỉ update-check, không traceback/InfoBar error. Không rebuild sau gate.
- Bản mới chưa chạy ASR/API/TTS/synthesis hoặc chấm chất lượng playback. Whisper full API pass
  trước đó thuộc hash Final cũ; không dùng thêm key/job trả phí. Scribe/phồn thể/speaker/xưng hô/S6
  vẫn chưa nghiệm thu. Giới hạn còn giữ: chưa có reproducer tất định của access violation cũ,
  nên đây là sửa lifetime có regression và smoke pass, chưa khẳng định loại bỏ mọi crash SIP.

## 2026-09-07 (nghiệm thu: Whisper EXE pass; GUI review crash SIP; dừng review)

- Tiếp tục từ HEAD **7e28895**, code S5.2 **073510d**, đúng nhánh và checkout sạch ban đầu.
  User xác nhận riêng **A1–A6 và B1** rồi yêu cầu agent tự kiểm thử để giảm thao tác xác nhận.
  A gồm GUI/settings, chọn đúng Qwen R2/Community-1, nạp thử Community-1/ForcedAligner và đóng app.
- Agent dùng bản sao EXE + `_internal/` mới, **580 file / 237.667.163 byte**, AppData riêng.
  EXE gốc và bản sao giữ SHA-256 **457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649**.
  PID test thoát **0** sau **2.965,891 s**; snapshot không còn PID/con trực tiếp. Stderr và app log
  chỉ có thông báo kiểm tra update, không traceback. **Không tái hiện InfoBar trong lượt này**;
  không coi đây là fix lỗi teardown cũ hoặc crash SIP ngắt quãng. Bản CLI riêng cùng hash cũng dùng
  AppData mới, không copy settings/media/log; cuối phiên không còn EXE/bridge của lượt kiểm tra.
- Chuẩn bị review/JSON/legacy và hai tone tổng hợp **4 s / 64.000 sample** bằng API typed trong
  scratch cô lập. Đổi tên/FLAC khớp PCM; audio khác cùng duration mismatch. Agent đối chiếu EXE:
  timing lỗi **exit 5**, sai audio + missing runtime **exit 5**, đều không output; reference đã sửa
  **exit 0 / 2 cue**, giữ identity/IDs/edited/pending. GUI agent đã thấy mismatch/chặn xuất, FLAC
  khớp và Apply/undo/redo giữ raw; **chưa hoàn thành lưu/mở lại GUI**.
- **GUI lượt B crash thực:** PID 52400, exit **3221225477 / 0xc0000005**, sau **1.032,578 s**.
  Windows Application Error lúc **21:54:10**, WER **21:54:15**: `sip.cp312-win_amd64.pyd`, offset
  **0xe58e**, khác offset **0x13a26** từng ghi ở test Settings. Stderr chỉ update-check, không Python
  traceback. Xảy ra sau chuỗi review khi công cụ Windows timeout ở lưu/activate; chưa có reproducer
  tách khỏi automation hoặc quan hệ nhân quả với thao tác Lưu/InfoBar. Không sửa framework/source.
- B/C kỹ thuật tiếp tục độc lập: EXE CLI lưu/reopen/JSON/SRT/legacy/guard audio pass; source
  CommandStack + EditorProjectStore rồi **EXE đọc project→JSON/SRT** giữ raw/provenance/IDs/timing,
  speaker override, context confirmed/locked và pending. Fixture union span giữ unknown/ambiguous/
  overlap/assigned, không suy acoustic probability hoặc speaker accuracy. GUI editor vẫn chưa đo.
- **Community-1 từ EXE thật** trên tone tổng hợp: pending→diarization **exit 0 / 21,000 s**,
  legacy SRT **exit 0 / 7,453 s**; pending chỉ xóa sau stage, legacy không tự có identity.
  **32 test gần identity/review/QThread pass / 1 warning / 2,58 s**; Qt offscreen không phải gate layout.
- **Whisper API từ EXE mới pass** theo lựa chọn user: đúng `videocaptioner`, endpoint
  `https://api.videocaptioner.cn/v1`, `whisper-1`, audio Trung public **4,204 s / 67.263 sample**.
  Health trước upload **exit 0 / 40,109 s**; **một command**, cache **MISS**, ASR→Community-1→JSON
  **exit 0 / 22,141 s**, **1 cue 0–4000 ms / 1 speaker**, identity khớp, pending false; EXE xuất SRT
  **exit 0**. Không 429 lượt này; log không có mã HTTP cụ thể. Key chỉ password/RAM/named pipe ACL
  current-user; **0 reader còn sống**, owner thoát; không key vào argv/env/file hoặc gọi thêm model.
- Giữ GPT/Qwen audio inference là evidence kế thừa; không chạy lại. Scribe, phồn thể strict,
  speaker accuracy/xưng hô do người đọc và GUI/SIP vẫn chưa nghiệm thu. Chỉ sửa hai tài liệu trạng
  thái; giữ dữ liệu/runtime/artifact gốc, không dependency/full/build/S6/commit/push. `git diff --check`
  pass; báo cáo, fixture, output và WER metadata giữ local. Đề xuất tiếp theo: khoanh vùng crash SIP.

## 2026-09-07 (chốt commit S5.2 và bàn giao phiên hướng dẫn nghiệm thu)

- Theo yêu cầu user sau review, code S5.2 đã commit thành
  **`073510db54e5a24ab3deba3626d53279d478813f`**, parent `27be883`, và push lên
  `origin/codex/asr-s3-native`. Đúng **35 file** trong manifest, không media/AppData/runtime/
  build/dist/credential. Các dòng “không/chưa commit” bên dưới mô tả thời điểm review trước submit.
- Trước commit: fetch xác nhận local/remote cùng baseline; ruff pass, pyright **0/0**, translations,
  diff-check và scan credential/path pass. **218 module / 39 resource** vẫn khớp EXE S5.2 Final,
  SHA-256 **457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649** không đổi.
  Không đổi code từ gate bàn giao; không rerun full/API hoặc rebuild chỉ để commit/push.
- [Prompt phiên tiếp theo — hướng dẫn test nghiệm thu](docs/dev/asr-acceptance-next-session-prompt.md)
  yêu cầu agent chuẩn bị bản test riêng và hướng dẫn user từng 1–3 thao tác, ghi riêng user xác nhận,
  agent đo và evidence thừa kế. Ưu tiên audio identity/review/pending, Whisper EXE còn 429, Qt teardown;
  Scribe chỉ khi có đúng credential. Giữ phồn thể/speaker/xưng hô chưa nghiệm thu, chưa mở S6.
- Chỉ chuẩn bị prompt; chưa khởi chạy phiên test mới. Không đổi runtime, media/AppData, artifact hoặc
  dependency. Quyền commit/push lần bàn giao này không tự áp dụng cho thay đổi ở phiên kế tiếp.

## 2026-09-07 (S5.2: identity recording và gateway hybrid; dừng review)

- Đúng worktree/nhánh user chỉ định, baseline **27be883** sạch; code S5.1 **8599965** là ancestor.
  Không commit/push/S6, không đổi dependency Qt/pin/model/runtime. Giữ artifact cũ; SHA-256 S4,
  S4.1 Final, S5 Final và S5.1 Final khớp bàn giao. Checkout vẫn không có settings.json mới.
- Thêm identity typed của toàn PCM16 mono 16 kHz (SHA-256 + số sample, không path/transcript/key),
  giữ tail và optional schema cũ. Qwen/API/native qua pipeline, JSON/review/editor/table giữ
  identity/IDs/override/pending. Sai audio cùng duration dừng trước cache/runtime/inference;
  file lossless/đổi tên vẫn khớp. Legacy mở được, báo unverified và không tự được xác minh.
- Review có chọn audio chạy QThread, cancel/retain/signal guard; CLI `asr-review --audio`, bảo vệ
  audio khỏi output/save-review. Pending chỉ được xóa sau diarization; export timing không thành
  full hybrid success. Aligner S5 được chọn tường minh cho API text-only, giữ strict S2. Gateway
  recognition đầy đủ trước alignment/review, text thiếu trên audio có năng lượng không resume pass.
- **API source thật**, đúng gateway/model đã chọn, public Chinese 4,204 s, cache reads off:
  Whisper → Community-1 → JSON/SRT **exit 0 / 1 cue 0–4000 ms / 43,390 s**;
  GPT → strict alignment → Community-1 → JSON/SRT **exit 0 / 1 cue 400–3680 ms / 13 token IDs /
  70,859 s**. Cùng identity **67.263 sample**, 1 speaker, pending false. Catalog HTTP 200 là gate riêng.
- **GPT từ EXE mới thật pass**: 58,312 s, 1 cue 400–3680 ms / 13 token IDs; JSON/SRT và identity
  khớp source. **Whisper API từ EXE HTTP 429 / exit 5**, không output; không chạy thêm command retry.
  Frozen `local-diarize` từ timed Whisper JSON của source **exit 0 / 10,157 s**, SRT legacy
  **exit 0 / 9,609 s** (giữ unverified). Đây không thay thế full Whisper API từ EXE còn thiếu.
- Frozen wrong-audio trước missing runtime **exit 5**, không inference/output. Review tổng hợp
  reject/override/reopen giữ raw/IDs/edited/pending và source identity; mismatch exit 5; không upload.
  Key gateway chỉ RAM/password + named pipe current-user ACL, không argv/env/file; owner/readers
  đã thoát, không runtime bridge còn lại. Không cấp/tìm key Scribe hoặc gọi lại Soniox/mini.
- **Full offline: 1.116 passed / 4 skipped / 51 deselected, 131,78 s, exit 0**; sau đó thêm guard
  output trùng audio và chạy **CLI cuối 106 passed / 2,58 s**. **30 test S5.2 mới** (24 core,
  4 UI, 2 CLI); test identity sau cô lập cache **24 pass / 3,44 s**. Ruff pass, pyright **0/0**
  với interpreter 3.12.13 có sẵn, translations sync. 4 skip TTS/service; native Qt playback pass.
- Full đầu **2 fail / 1.114 pass**: regression thứ tự preflight (đã sửa), Settings subprocess
  access violation **3221225477**, faulthandler `<no Python frame>`. Windows ghi fault trong
  **PyQt5-sip 12.18.0**, offset **0x13a26**. Không build/GPU song song ở lượt fail; chưa biết nguyên
  nhân. 4 case chẩn đoán (preflight/Settings/Scribe cancel-timeout) pass; 3 subprocess Settings
  có stage/atexit marker (2 original, 1 teardown tường minh) pass. Không coi rerun là fix Qt/Scribe.
- Rà fixture mới phát hiện S2 vẫn retain cache values khi tắt cache reads: đã thay bằng cache RAM
  trong test, xóa đúng **2 entry tổng hợp do test tạo** sau đối chiếu key/value/store-time; rerun
  xác nhận không tái tạo entry. Không xóa cache khác. Runtime/API output và log nghiệm thu ở scratch
  riêng; không dùng helper ignored làm bằng chứng duy nhất, không đưa media/credential vào Git.
- Artifact mới **`dist/VideoCaptioner-ASR-S52-Review-20260907-Final/`**, duy nhất spec: build exit 0,
  **6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream**; **218 module / 39 resource**
  khớp source, không bundle GPU. EXE **31.161.859 byte**, local **19:11:44**, SHA-256
  **`457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649`**.
  Onedir trước GUI **580 file / 237.667.163 byte**. Không rebuild sau nghiệm thu.
- GUI **25,047 s**, 1 Qt window, RSS **101.412.864 byte**, WM_CLOSE exit 0, 0 process sót.
  **Log teardown chưa sạch**: `BottomInfoBarManager has been deleted` sau thông báo update;
  bản sao S5.1 Final tái hiện cùng lỗi (25,047 s/exit 0). Không phải lỗi mới chỉ có ở S5.2;
  chưa chứng minh liên quan crash SIP. Không sửa framework để che fail. Review VI native render
  và QThread/FFmpeg xác minh audio thật pass; offscreen không vẽ chữ, không dùng làm gate layout.
- Còn mở: **Whisper API từ EXE sau HTTP 429, Scribe online, Qt/SIP/InfoBar teardown, phồn thể strict,
  speaker accuracy và xưng hô do người đọc chấm**. Chưa chuyển S6. Hướng dẫn và giới hạn:
  [S5.2](docs/dev/asr-s52.md); manifest/gate: [bàn giao](docs/dev/asr-implementation-2026-09.md#bàn-giao-s52--2026-09-07).

## 2026-09-07 (chốt commit S5.1 và bàn giao prompt S5.2)

- Theo yêu cầu user sau review, đã chốt **code S5.1** thành
  **`8599965b7931d8c555a55cfa379b4a2e2cee9238`**, parent `80f6e36`, và push lên
  `origin/codex/asr-s3-native`. Commit đúng **12 file** theo manifest, không chứa media/AppData/
  runtime/build/dist/credential. Các mục “không commit/push” bên dưới mô tả thời điểm nghiệm thu
  trước yêu cầu submit này, không phải trạng thái Git hiện tại.
- Trước commit: fetch xác nhận local/remote cùng baseline; ruff pass, pyright **0/0**, translations
  sync, diff-check và quét mẫu credential/path pass. **216 module / 33 resource** vẫn khớp artifact
  S5.1 Final, SHA-256 không đổi. Không đổi code từ gate **1.088 pass / 4 skip / 51 deselect**, CLI104
  và các lượt local-hybrid source/EXE thật; không rerun full hoặc rebuild chỉ để commit.
- [Prompt phiên tiếp theo — S5.2](docs/dev/asr-step-5-2-prompt.md) ưu tiên nợ API thật, liên kết
  audio khi mở lại JSON/review và chẩn đoán có bằng chứng trước S6. Community-1 đã cài/đã inference
  thật, không cần xin lại HF token để chạy offline. Giữ các khoản chất lượng/API chưa đo riêng.
  **Chưa khởi chạy S5.2/S6**; quyền commit/push lần này không tự áp dụng cho phiên tiếp theo.
  Giữ nguyên runtime, artifact, media/AppData và mọi dữ liệu user.

## 2026-09-07 (S5.1: Community-1 và local-hybrid đã chạy thật; dừng review)

- User cung cấp quyền tải và nhập token qua ô password trên máy; installer truyền token trong
  RAM/stdin, không lưu vào settings/argv/env/log/source. Cài bằng installer hiện có vào đích mới
  **`build/S51-Community1-Runtime-20260907/`**, không đổi runtime/artifact hoặc dependency Qt cũ.
  Revision **3533c8cf8e369892e6b79ff1bf80f7b0286a54ee**, **8 file / 32.832.557 byte** model,
  manifest/hash/recipe/health pass. Giữ pyannote 4.0.7, Torch 2.9.1+cu128, lock đã pin.
- **Community-1 inference thật pass** qua waveform PCM trong RAM, HF offline/telemetry off/socket
  guard bật, không cần token sau download. Mẫu pyannote public **30 s → 13 span / 2 nhãn speaker**;
  clip Trung Qwen public **4,204 s → 1 span / 1 speaker**; silence **3 s → 0 span**.
  Cold/warm inference mẫu 30 s **1,688/0,485 s**, Torch peak allocation **1.708.632.064 byte**;
  RSS tree warm **1.944.559.616 byte**. Không suy tổng VRAM/NVML hoặc benchmark tốc độ từ số này.
- Health load đầu **75,094 s**, restart load **25,968/9,421 s**, shutdown **0,907–0,922 s**.
  Cancel startup/inference Community-1 thật **1,531/1,563 s**, process/reader/lease đã giải phóng.
- Cancel inference Qwen/aligner thật **1,187/1,344 s**, cleanup pass. Process thứ hai nhận GPU
  busy trong khi Community-1 owner còn sống; không unload/kill owner. Speaker override qua
  CommandStack undo/redo và JSON/editor roundtrip giữ nguyên diarization provenance.
- **Qwen 0.6B → strict alignment → Community-1 thật từ source pass**, cache tắt: **13 cue/token**
  đều assigned, toàn lượt **86,110 s**. JSON/SRT nhập riêng từ timing reference tổng hợp của mẫu
  public giữ **11 cue: 1 unknown, 3 ambiguous, 7 overlap**; không ép gán nhãn. Text/timing/IDs,
  JSON/editor roundtrip và scope riêng giữa hai job pass. Đây không phải nhận dạng transcript mẫu.
- Spot-check các cửa sổ nội bộ theo RTTM upstream giữ hai speaker quay lại, overlap và silence
  unknown. **Lượt thoại ngắn đầu clip khác reference và bị giữ ambiguous**; chưa nghiệm thu
  speaker accuracy nói chung, chưa mở corpus/benchmark S6.
- **EXE local-hybrid thật pass** từ bản sao riêng của S5.1 Final, giữ nguyên binary SHA-256
  **5c2cc4ad873d7acbc0ccb9a94ce942e87a41c3bc8ba0c68c6e36af8df25f73c8** và artifact/AppData gốc.
  Qwen → alignment → Community-1 → JSON/SRT **exit 0**, **1 cue 400–3680 ms / 13 token IDs**,
  **51,719 s**. `local-diarize` dùng Qwen timed JSON/SRT đã có đều **exit 0 / 13 assigned cue**,
  **11,328/11,204 s**, không nhận dạng/upload lại. Không rebuild chỉ để nghiệm thu runtime mới.
- Lượt này chỉ cập nhật **README.md, status.md, implementation và hướng dẫn S5**; source/test snapshot giữ
  nguyên gate **1.088 pass / 4 skip / 51 deselect**, CLI104, ruff/pyright/sync đã pass trước đó.
  Giữ riêng **hybrid API cloud, Scribe online, GPT gateway→alignment→SRT, phồn thể strict,
  speaker accuracy và xưng hô do người đọc chấm** là chưa nghiệm thu. Không commit/push/S6.

## 2026-09-07 (S5.1: củng cố local/hybrid; Community-1 chờ quyền tải; dừng review)

- Đúng worktree/nhánh user chỉ định, baseline **80f6e36** sạch, code S5 **3a7c231** là ancestor.
  Không commit/push/S6. Giữ media/AppData, runtime, dependency Qt và artifact S4–S5; SHA-256
  ba EXE S4/S4.1 Final/S5 Final vẫn đúng bàn giao. Không tìm credential ở checkout/artifact/log.
- Sửa lỗi hybrid nhận audio khác khi file gốc đổi giữa stage: chụp config và source riêng cho
  toàn job, có cancel/deadline/copy validation/cleanup. Giữ text/timing/review/policy và IDs.
  Guard Windows dùng baseline stat riêng cho handle/path; khác biệt `ctime` đã tái hiện bằng
  file tổng hợp, tránh false rejection. Không lưu fingerprint audio mới vào schema JSON/SRT.
- Từ chối cue ngoài duration/nhãn native hoặc local đã có trước khi nạp diarization. Kiểm tra
  protocol/model/revision mỗi response runtime, thêm điểm hủy khi hash model. GUI chỉ áp cờ
  local diarization cho Qwen/Whisper; chuyển engine khác không mang cờ ẩn vào job, giữ preference.
- **Full offline mã cuối: 1.088 passed, 4 skipped, 51 deselected, 118,40 s, exit 0**; **22 test mới**.
  Toàn CLI **104 pass, 2,09 s**; test gần phần cuối **26 pass, 4,55 s**. Ruff pass, pyright
  **0 errors/0 warnings**, sync translations/diff-check pass. Python **3.12.13**, đúng checkout,
  FFmpeg/venv có sẵn, không sync dependency. 4 skip TTS/service; native QtMultimedia pass.
- Có gate trung gian fail: guard `ctime` mới (đã sửa/test); rồi crash Settings subprocess
  **3221225477** cùng test Scribe mock deadline **10 ms** chưa vào transport (`closed=False`).
  Ba case chẩn đoán riêng pass; full cuối chạy không có build/runtime song song pass.
  **Chưa xác định nguyên nhân crash Settings hay khẳng định đã sửa flake timeout**; giữ bằng
  chứng local ignored. Không coi mock Scribe là online acceptance.
- **Qwen source thật**: 0.6B/1.7B, audio Trung public **4,204 s**, cache tắt → strict alignment
  → JSON/SRT **13 cue/token, 400–3680 ms** mỗi bản, toàn lượt **59,266/42,609 s**. Có build nền,
  không dùng làm benchmark tốc độ. Không còn bridge Qwen, host không import GPU libraries.
- **Community-1 chưa inference**: chưa được cung cấp quyền/token trong phiên; không cài model,
  không tự chấp nhận điều kiện. Giữ pin/recipe và thư mục pyannote dependency S5. Community-1/
  hybrid API, speaker accuracy, Scribe online, GPT gateway→alignment→SRT, phồn thể strict và
  xưng hô do người đọc chấm vẫn thiếu. **Chưa đủ điều kiện nghiệm thu để chuyển S6**.
- Artifact mới **`dist/VideoCaptioner-ASR-S51-Review-20260907-Final/`**: PyInstaller exit 0,
  **6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream**; **216 module / 33 resource**
  khớp source, không bundle GPU. EXE **31.150.810 byte**, local **2026-09-07 17:55:01**, SHA-256
  **`5c2cc4ad873d7acbc0ccb9a94ce942e87a41c3bc8ba0c68c6e36af8df25f73c8`**.
  Onedir trước smoke **580 file / 237.650.489 byte**; giữ riêng bản S5.1 đầu.
- **Workflow Qwen từ EXE Final pass**: 0.6B/1.7B nhận dạng → strict alignment → JSON → SRT,
  các command exit 0, mỗi bản **1 cue 400–3680 ms**, giữ **13 token IDs**. Toàn transcribe
  **37,562/27,500 s**, export SRT **0,360/0,390 s**. Frozen `local-diarize` từ chối JSON native
  **exit 5 trước runtime**, không output partial; không process EXE sót sau workflow.
  Đây là media/local Qwen, không phải Community-1, hybrid cloud hay portable-runtime acceptance.
- **GUI Final pass**: hidden launch **25 s**, 1 cửa sổ Qt đúng process; WM_CLOSE **exit 0**,
  RSS **100.052.992 byte**, **0 process sót / 0 startup error marker**. Không rebuild sau smoke.
- Hướng dẫn: [S5.1](docs/dev/asr-local-s5.md#củng-cố-s51). Manifest đúng **11 file** và gate
  chi tiết: [bàn giao S5.1](docs/dev/asr-implementation-2026-09.md#bàn-giao-s51--2026-09-07).

## 2026-09-07 (chốt commit S5 và bàn giao phiên S5.1)

- Theo yêu cầu user sau review, đã chốt **code S5** thành
  `3a7c231a53069fefc58b34e95d7cc9ba10dac846` trên `codex/asr-s3-native`, parent `1bf4dd0`.
  Commit gồm đúng 53 file trong manifest; không media/AppData/build/dist/credential hoặc dependency Qt.
  Các mục “không/chưa commit” bên dưới mô tả thời điểm triển khai trước yêu cầu submit/push mới này.
- Trước commit: fetch xác nhận local/remote cùng baseline; ruff, pyright 0/0, sync translations,
  diff-check và quét mẫu credential/path mới pass. **215 module / 34 resource** tiếp tục khớp
  artifact Final; EXE giữ SHA-256 bàn giao. Không đổi code từ full **1.066 pass / 4 skip / 51 deselect**
  và CLI **104 pass**, nên không rerun full hoặc rebuild chỉ để commit.
- [Prompt phiên tiếp theo — S5.1](docs/dev/asr-step-5-followup-prompt.md) ưu tiên nghiệm thu
  Community-1/local-hybrid và củng cố lỗi tái hiện trước S6, giữ riêng các khoản runtime/API còn thiếu.
  Lưu prompt không khởi chạy công việc mới; quyền commit/push ở lượt bàn giao này không tự áp dụng
  cho thay đổi mới của phiên kế tiếp. Giữ nguyên media/AppData và mọi artifact S4–S5.

## 2026-09-07 (S5: Qwen local và hybrid diarization; dừng review)

- Tiếp tục đúng worktree user chỉ định, nhánh `codex/asr-s3-native`, HEAD sạch ban đầu
  **1bf4dd0**; xác minh code S4.1 **db23299** là ancestor. Không commit/push/tag/release/S6.
  Giữ nguyên dependency Qt (`pyproject.toml`/`uv.lock`), AGENTS/CLAUDE và dữ liệu/artifact S4–S4.1.
- Thêm Qwen 1.7B/0.6B được chọn tường minh, recognition → strict alignment S2 tuần tự;
  runtime/model pin SHA, lock hash, download chủ động vào đích mới, verify inventory/revision.
  Qwen dùng recipe S2 trong runtime mới; pyannote có runtime riêng. Mở settings không tải/nạp/API.
- Diarization Community-1 toàn recording, policy overlap/coverage versioned, unknown/ambiguous
  không bị gán đại. Provenance recognition/alignment/diarization tách bạch, giữ cue/token IDs,
  override và context S4 qua pipeline/JSON/editor. `local-diarize` dùng output có timing sẵn;
  không nhận dạng/upload lại. Native Soniox/Scribe không bị trộn label ngầm.
- `local-asr-review-v1` giữ raw/chunk/coverage/pending stage; dùng lại GUI/CLI S4.1 và CommandStack.
  GPU lease dùng chung S2/S5/VieNeu, báo busy thay vì unload job đang chạy; process ẩn, env lọc,
  deadline/cancel/join hữu hạn. Không import GPU libraries vào Qt. Runtime là venv cài tại máy,
  chưa phải bản portable phân phối độc lập.
- **Full offline mã cuối: 1.066 passed, 4 skipped, 51 deselected, 144,10 s, exit 0**.
  **Toàn CLI: 104 passed, 2,96 s, exit 0**; ruff pass, pyright **0 errors/0 warnings**, sync
  translations và diff-check pass. 79 test S5 mới; QtMultimedia trước đây skip đã chạy pass trong
  lượt này. 4 skip là TTS/service; 51 deselect integration/slow/llm. Python **3.12.13**, FFmpeg/venv
  có sẵn, import đúng checkout; không sync/cài dependency Qt. Tests cô lập settings/cache/review/GPU
  lease và wait QThread. Đã xem render settings/manager tiếng Việt; JSON sync, TS cập nhật,
  không sửa QM vì thiếu lrelease.
- Lượt full trước có một subprocess test Settings crash Windows `3221225477`; test riêng pass,
  hai full tiếp theo **1.064** rồi **1.066** pass. Chưa xác định nguyên nhân crash ngắt quãng,
  không claim đã sửa lỗi Qt. Test đầu cũng phát hiện dùng chung GPU lease với runtime thật;
  fixture đã tách lease theo từng test trước gate cuối.
- **Qwen runtime thật**: cả 0.6B/1.7B trên audio Trung public 4,204 s → strict alignment → JSON/SRT
  **13 cue pass**. Inference cold/warm lần lượt **2,813/0,672 s** và **0,984/0,360 s**;
  peak Torch allocation **1.876.073.984 / 4.698.543.616 byte**. Các lượt có cache/tải nền khác nhau,
  không suy benchmark tốc độ/chất lượng. Restart/stop sạch, shutdown **0,890–0,938 s**, cancel
  startup thật **1,250 s**. Phồn thể và silence có text vẫn bị strict guard từ chối.
- **Pyannote mới nghiệm thu dependency import/CUDA**, chưa model inference: không có token/quyền
  Community-1 được cung cấp trong phiên, không tự chấp nhận điều kiện hoặc tìm credential.
  TorchCodec báo thiếu decoder DLL; adapter dùng waveform memory theo upstream. **Community-1/
  hybrid API, speaker accuracy, Scribe online, GPT gateway→alignment→SRT, phồn thể strict và
  chất lượng xưng hô bằng người đọc vẫn thiếu nghiệm thu**. Các gate EXE được ghi riêng bên dưới.
- **Artifact Final** `dist/VideoCaptioner-ASR-S5-Review-20260907-Final/`: PyInstaller exit 0,
  6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream; **31.148.265 byte**, local
  **2026-09-07 17:23:00**, SHA-256 **`1717175295241e722a3e5a516d903b85668a3372417260bf0e776e3f303fe9f3`**.
  **215 module / 34 resource** khớp source, không bundle GPU libraries. Onedir trước smoke
  **580 file / 237.647.944 byte**. GUI hidden **25 s**, WM_CLOSE **exit 0**, không process sót/
  startup error marker. Giữ bản S5 đầu; không rebuild Final sau smoke.
- **Workflow local từ EXE pass** cho cả Qwen 0.6B/1.7B: audio public → nhận dạng → strict alignment
  → JSON → SRT, mỗi bản **1 cue 400–3680 ms**, giữ **13 token IDs** trong JSON. Transcribe lần lượt
  **70,766 / 22,421 s** (gồm load/verify/alignment). Frozen review tổng hợp reject/resume cũng pass.
  Đây là media/local-ASR từ EXE, **không phải API cloud hoặc nghiệm thu portable runtime**.
- Hướng dẫn và giới hạn: [S5 local/hybrid](docs/dev/asr-local-s5.md). Manifest và gate artifact:
  [bàn giao S5](docs/dev/asr-implementation-2026-09.md#bàn-giao-s5--2026-09-07).

## 2026-09-07 (chốt commit S4.1 và bàn giao prompt S5)

- Theo yêu cầu user sau review, đã chốt **code S4.1** thành
  `db23299370f311395fae39069f0983739d259250` trên `codex/asr-s3-native`, parent `47d1cec`.
  Commit gồm đúng 56 file trong manifest, không có media/AppData/build/dist/credential.
  Các mục “không/chưa commit” bên dưới mô tả thời điểm triển khai trước yêu cầu submit này.
- Trước commit: fetch xác nhận local/remote cùng baseline; ruff, pyright 0/0, sync translations,
  diff-check và quét mẫu credential pass. **202 module source** tiếp tục khớp bytecode artifact
  Final đã smoke. Không đổi code từ full **986 pass / 5 skip / 51 deselect**; không rerun full suite
  hoặc rebuild EXE chỉ để commit. Giữ nguyên mọi artifact/media/AppData hiện có.
- [Prompt phiên tiếp theo — S5 local/hybrid](docs/dev/asr-step-5-prompt.md) đã ghi baseline,
  runtime Qwen/diarization, compatibility S4.1, validation và các khoản online còn thiếu.
  **Phiên này chưa triển khai S5/S6**. Prompt chỉ được thực thi khi user dùng nó để bắt đầu S5;
  phiên mới dừng review sau S5, không tự commit/push hoặc làm S6.

## 2026-09-07 (S4.1: deadline dịch, local ASR review/resume và lifecycle; dừng review)

- Đúng checkout user chỉ định, nhánh `codex/asr-s3-native`, baseline **47d1cec** sạch;
  S4 **8558082** là ancestor. Hoàn thành phạm vi A–C của followup, **không commit/push/tag/release**,
  không làm S5–S6. Giữ media/AppData/work-dir và artifact S4 hiện có; EXE S4 vẫn khớp SHA-256 bàn giao.
- Timeout chung có validation **1–600 s**, default cũ **120**; GUI/CLI/SubtitleConfig/factory đã nối,
  dùng `--llm-timeout 300` cho `gpt-5.6-terra` mà không cần harness. Model/endpoint không đổi ngầm.
  Worker snapshot config/credential/source; LLM request sở hữu socket, deadline/cancel/join hữu hạn,
  không retry HTTP POST tự động. Thất bại batch LLM không publish một kết quả thiếu thành success.
- Request context policy **conversation-request-v2**, schema persistence vẫn v1. Bỏ fields/review
  unknown lặp, giữ glossary, source window và evidence theo selection/rules/lock. Nguồn tổng hợp
  30 cue: **11.595 → 2.044 byte UTF-8, giảm 82,37%** cho khối context; không claim token/chi phí.
- Native ASR giữ `asr-review-v1` riêng trước khi báo lỗi timing/coverage. GUI mở lại, hiển thị token/
  ngữ cảnh/lý do, chỉnh ms tường minh, undo/redo qua CommandStack; CLI `asr-review` validate/resume
  local, không upload. Giữ raw và overrides/provenance; group có override mang `edited`, token IDs
  xuyên JSON/editor. Guard zero-time/coverage/speaker/scope/overlap và remote cleanup/409 vẫn giữ.
- Stale guard editor theo project/source/cue/timing/speaker/context/selected target; playback/zoom
  không làm mất bản dịch. Selection chỉ đổi display_text. QThread không terminate; UI cancel/close
  giữ worker qua supervisor, app quit tiếp tục xử lý Qt events khi join. Signal cũ không reset job
  mới. Subtitle output được staging trước commit; hủy trong request/staging không ghi output một phần.
- **Full offline mã cuối: 986 passed, 5 skipped, 51 deselected, 92,17 s** (baseline 910 + 76 test).
  Gồm toàn CLI, ASR, translate, subtitle, editor, UI/thread. Gate gần code cuối **427 passed**;
  ruff toàn source/tests pass, pyright **0 errors/0 warnings**, sync translations và diff-check pass.
  Python **3.12.13**, import đúng checkout, dùng venv/FFmpeg có sẵn; không cài/sync dependency.
  Cô lập settings/config/cache/review; QThread tests wait. Skip: native QtMultimedia playback và
  4 TTS/service; deselect integration/slow/llm. 1 warning offline là audioop deprecation.
- Full đầu tìm khác biệt `stop().executor`; đã giữ API cũ và thêm private owner để join. Regression
  cancel còn phát hiện wait treo trên future bị hủy, đã sửa collection/join. Final suite trên đã pass.
  Rà cuối thêm regression signal xếp hàng sau khi Qt xóa interruption flag: dùng dấu hủy riêng,
  **30 tests UI/lifecycle pass** trước full cuối. Bản Final dùng output mới, không rebuild bản đã smoke.
  Đã render dialog review và card timeout tiếng Việt, sửa mô tả bị cắt; JSON vi sync, TS en/zh cập nhật.
  Thiếu lrelease nên QM giữ nguyên, zh mới fallback English.
- **Artifact cuối** `dist/VideoCaptioner-ASR-S41-Review-20260907-Final/`, scratch riêng, duy nhất spec.
  PyInstaller **exit 0, 6 WARNING optional/platform, 0 ERROR**; thêm 6 SyntaxWarning upstream
  (4 pydub, 2 modelscope). **202 module bytecode** từ EXE khớp source, prompt và 2 JSON vi khớp bytes;
  không bundle Torch/Qwen/Torchaudio. EXE **31.093.132 byte**, timestamp local **2026-09-07 15:35:00**,
  SHA-256 **2ab4c85035ba64fd59fe96d5686b75ac00139644936bd960a206a419803e4284**.
  Onedir trước smoke **573 file / 237.245.477 byte**; phân phối nguyên thư mục.
- **Frozen local review smoke pass**: JSON tổng hợp lỗi trả **exit 5**, không tạo SRT partial;
  explicit override + export JSON **exit 0**, mở lại và export SRT **exit 0**, giữ edited/token/scope.
  `subtitle --help` từ EXE pass. **GUI startup pass 25 s**, đúng cửa sổ Qt, WM_CLOSE → **exit 0**,
  **0 process sót / 0 Traceback-ERROR-CRITICAL**. Không rebuild sau khi artifact có AppData.
- **Không chạy API/media thật trong phiên S4.1**: worktree không có settings LLM, env key LLM/native
  trống; không tìm/copy key từ S4/checkout khác/log. Scribe online, GPT→alignment→SRT, phồn thể
  Qwen strict, speaker accuracy và chất lượng xưng hô/người đọc vẫn còn thiếu nghiệm thu.
  Frozen local JSON và startup không thay thế workflow media/API từ EXE.
- Hướng dẫn: [S4.1](docs/dev/asr-s41.md). Manifest file và gate:
  [bàn giao S4.1](docs/dev/asr-implementation-2026-09.md#bàn-giao-s41--2026-09-07).

## 2026-09-07 (chốt commit S4 và chuẩn bị session S4.1)

- Theo yêu cầu user sau khi xuất SRT xem thử, đã chốt **code S4** thành
  `8558082945575d551a4c38cdc4943c395254a583` trên `codex/asr-s3-native`, parent S3 `327c214`.
  Commit gồm 37 file, kể cả prompt S4 có sẵn được giữ nguyên nội dung. Các mục “chưa commit”
  bên dưới là trạng thái tại thời điểm bàn giao/đo test trước yêu cầu submit mới này.
- Trước commit: ruff toàn source/tests pass; pyright 0 errors/0 warnings; sync translations và
  diff-check pass; quét mẫu credential 37 file pass. 21 module source khớp bytecode của EXE đã
  kiểm thử. Code không đổi kể từ full offline **910 pass / 5 skip / 51 deselect**, nên không
  rerun toàn suite hoặc rebuild artifact chỉ để commit. Media, outputs, keys, AppData không vào Git.
- Session tiếp theo ưu tiên **S4.1**: timeout/chi phí context trong app, bảo toàn và review/resume
  ASR timing lỗi, stale guard theo dữ liệu liên quan và lifecycle UI. Chưa sang S5/S6.
  Prompt đầy đủ: [củng cố S4.1](docs/dev/asr-step-4-followup-prompt.md).
- User có thể xem SRT Việt đã xuất và ghi lại lỗi kèm thời điểm để bổ sung vào session kế tiếp.
  Yêu cầu submit/push ở phiên này không phải quyền tự commit/push trong session S4.1.

## 2026-09-07 (xuất full SRT Việt để user xem video thử)

- Theo yêu cầu user, dịch đủ 30 cue Whisper cấp câu của clip Trung 111.333 s bằng đúng
  `gpt-5.6-terra`. Một request trả đúng response model trong 131.56 s; toàn lượt xuất 131.69 s.
  Dùng timeout 300 s riêng cho lượt xuất, không sửa timeout/source/dependency/EXE của app.
- Xuất SRT Việt, SRT song ngữ Việt/Trung, JSON và editor project vào thư mục riêng; đặt thêm
  sidecar `.vi.srt` cùng tên cạnh đúng bản video Trung, không ghi đè file có sẵn. Parse lại đủ
  **30 cue**, mốc **12.560–104.180 s** giữ nguyên từng cue so với Whisper, nằm trong audio.
  Không dùng word timestamps 0 ms, không tạo speaker/character mapping giả.
- Sửa riêng hai tên/thuật ngữ nguồn đã có bằng chứng chữ trên video, giữ nguyên cue ID/timing;
  nhật ký sửa và transcript chỉ lưu local ignored. Bản xem thử vẫn cần user review ASR/ngôi/tên.
  Các giới hạn Soniox zero spans, GPT text alignment, Scribe, phồn thể và EXE workflow giữ nguyên.
- Key dùng trong RAM/getpass, không argv/env/settings/output. Chỉ cập nhật `status.md` và
  implementation; diff-check pass, không commit/push. Gate code gần nhất vẫn 910 offline pass.

## 2026-09-07 (STT gateway: Whisper sentence SRT, GPT text, mini HTTP 429)

- Theo yêu cầu user, thử ba model STT chuyên dụng có trong catalog gateway hiện tại trên cùng
  audio Trung 111.333 s: `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`. Dùng builder/
  parser S1 và SDK thật, filename multipart trung tính, zh/default prompt, không cache; key qua
  getpass/in-memory, không settings/env/argv/report. Không thử các model audio-chat/TTS khác.
- **Whisper pass nhận dạng + SRT cấp câu**, **9.00 s**: 189 ký tự text, 142 word spans và 30
  sentence spans. **11 word spans có duration 0** nên không nghiệm thu word timing. Cả 30 câu
  có start<end và nằm trong audio; ghép segment khớp text response khi bỏ whitespace.
  Xuất JSON/SRT toàn bản nhận dạng bằng **timing segment độc lập do API cung cấp**, không nội suy
  hoặc sửa word timestamps. JSON/editor project roundtrip pass. Response không có speaker.
- **gpt-4o-transcribe pass text**, **4.11 s**, 178 ký tự; JSON không có words/segments/speaker.
  Chưa chạy alignment, do đó **GPT gateway→alignment→SRT vẫn chưa nghiệm thu**. Usage được trả
  là 1,287 token; không suy ra hóa đơn hoặc chi phí từ con số này.
- **gpt-4o-mini-transcribe chưa pass inference**: HTTP 429 sau 4.23 s, một retry chủ động sau
  khoảng nghỉ vẫn 429 sau 8.27 s. Chưa xác định chính xác nguyên nhân 429; không gọi đó là key
  sai hoặc model chắc chắn không được hỗ trợ chỉ từ status. Không retry tiếp hoặc đổi model ngầm.
- Spot-check hai tên/thuật ngữ có chữ trên video: cả Whisper/GPT text đều chưa khớp hai checkpoint;
  output cần review nguồn. Chưa benchmark CER/timing/diarization/xưng hô; không đổi ASR mặc định.
  Các phép đo là source builder/parser/SDK, **không phải workflow media/API trong process EXE**.
- Output transcript/report/SRT/project nằm trong thư mục test local ignored cạnh video; không
  đưa media, transcript, key hoặc path riêng vào Git. Chỉ sửa `status.md` và implementation;
  diff-check pass, code/dependency/EXE giữ nguyên; gate offline gần nhất vẫn 910 pass, không
  rerun suite cho lượt ghi nhận validation này. Không commit/push hoặc làm S5/S6.

## 2026-09-07 (clip Trung user chỉ định + gateway gpt-5.6-terra)

- Chọn đúng bản lồng tiếng Trung trong thư mục có bốn ngôn ngữ, audio 111.333 s. User yêu cầu
  “gpt 5 terrain”; catalog hiện có `gpt-5.6-terra`, đã nêu ID này và xác minh request/response cùng
  model đó. Key giữ riêng theo dịch vụ, chỉ nhận qua getpass và truyền trong RAM; không lưu settings.
- Soniox `stt-async-v5`, zh/diarization/cache tắt: upload→poll→result thật trong **7.05 s**, trả
  **185 token / 4 nhãn speaker**. Full parser vẫn dừng vì **2 lexical token start=end** tại
  **83.010, 104.010 s**. Remote job/file cleanup thành công, không warning, không resubmit audio.
- Để hoàn thành yêu cầu dịch, dùng SourceCue/SubtitleProcessData và snapshot S4 **không timing**
  cho toàn bộ transcript nhận dạng: **17 đơn vị text**, không bỏ token, không tạo timestamp.
  Context chỉ có unknown proposals, không bịa nhân vật/người nghe/rules đã xác nhận.
- `gpt-5.6-terra`: lượt đầu batch 12/17 đơn vị timeout theo policy 120 s; batch 5 đơn vị thành công
  được cache. Một lần retry chẩn đoán riêng đúng batch thiếu, deadline 300 s, **pass sau 76.31 s**;
  5 đơn vị còn lại lấy từ cache, không dịch lặp. Request/response model trùng nhau. Retry trả usage
  8,079 token (không phải tổng usage/chi phí toàn lượt thử). Không sửa timeout hoặc transport của app.
- Đã xuất toàn văn Việt, bản đối chiếu Trung–Việt và JSON text-only review vào output local ignored.
  **Không có SRT full clip được nghiệm thu**. Mẫu native hợp lệ trước lỗi kết thúc **80.970 s**,
  **17 cue / 4 speaker**, có JSON/SRT/project riêng để user xem; không gọi đó là output đầy đủ.
- Spot-check phụ đề hiển thị trong hai frame tìm thấy lỗi tên/thuật ngữ của ASR truyền sang bản dịch;
  ghi chi tiết trong báo cáo local, không đưa transcript/frame hoặc path riêng vào Git. Chưa chấm
  toàn bộ ASR, diarization hoặc chất lượng ngôi/xưng hô bằng người đọc. Các khoản Scribe/GPT-ASR
  alignment/phồn thể/EXE media workflow vẫn thiếu acceptance như trước.
- Chỉ cập nhật `status.md`, implementation; không đổi source/dependency/artifact, không commit/push.
  Gate offline code gần nhất vẫn 910 pass; không rerun suite cho thay đổi chỉ ghi bằng chứng online.

## 2026-09-07 (Soniox/gateway online spot-check bằng media user chỉ định)

- User cung cấp riêng key Soniox và gateway, cho phép test video được chỉ định. Key nhận qua
  stdin/getpass không echo, truyền tường minh; không ghi vào argv, environment, settings, source
  hoặc report. Không commit/push. Không thay source/runtime policy; chỉ bổ sung bằng chứng validation.
- Video 260.551 s, audio gắn nhãn English và transcript quan sát được là tiếng Anh. FFmpeg tách
  PCM mono 16 kHz toàn file; Soniox `stt-async-v5`, diarization bật, language auto, không dùng cache.
  Service probe pass; upload/submit/poll/result thật hoàn tất trong 13.59 s tính cả probe.
  Provider trả **471 token / 4 nhãn speaker**; transcript/token coverage khớp. Không có timestamp
  âm/đảo/vượt audio, nhưng **3 lexical token có start=end** tại **34.890, 102.510, 157.350 s**.
- **Full ASR→subtitle chưa pass**: parser S3 dừng đúng guard `Zero-duration speech token`.
  Không nội suy/clamp/bỏ chữ để ép pass. Cleanup chỉ tài nguyên thuộc job: remote deleted,
  không warning cleanup. Response tối thiểu được giữ trong thư mục test local ignored để review;
  không upload/resubmit lại video khi phân tích lỗi.
- Tạo riêng **mẫu prefix hoàn chỉnh trước lỗi**, kết thúc **33.150 s**, **6 cue / 3 nhãn speaker**,
  dùng nguyên timestamp hợp lệ. Đây không phải output đầy đủ hoặc fallback thành công của job lỗi.
  JSON ASR + SRT và project editor mẫu được lưu trong thư mục test cạnh video; JSON/editor roundtrip
  pass, cue ID/speaker/timing giữ nguyên. Không gán tên, quan hệ hoặc người nghe giả cho đủ schema.
- Gateway đúng API base `https://api.videocaptioner.cn/v1`: GET models HTTP 200, **366 model ID**.
  Chỉ thử inference **`gpt-4o-mini`**, không suy toàn bộ catalog có quyền inference. Qua LLMTranslator
  S4 thật, dịch **6 cue Anh→Việt trong 3.81 s**; metadata giữ nguyên, JSON/project lưu được. Context
  chỉ có proposal unknown, **0 quan hệ xác nhận**; chưa test hiệu lực rule xưng hô có xác nhận trên phim.
- Giới hạn: mới đo từ **source**, chưa workflow media/API trong process EXE; không chạy dịch toàn clip,
  không benchmark chất lượng speaker/xưng hô hoặc Trung→Việt. Mẫu dịch cần người đọc sửa diễn đạt/ngôi.
  **Scribe online, GPT transcription gateway→alignment→SRT và phồn thể Qwen strict vẫn chưa nghiệm thu**.
  Bộ offline 910 pass ở mốc S4 vẫn là gate code gần nhất; lượt này không đổi code nên không chạy lại suite.
- File đổi trong lượt test: `status.md`, `docs/dev/asr-implementation-2026-09.md`. Transcript/media/
  catalog/report riêng tư chỉ ở thư mục test ignored; kiểm tra output và script tạm không chứa key.

## 2026-09-07 (ASR S4: ngữ cảnh xưng hô có bằng chứng; dừng để review)

- Tiếp tục trực tiếp working tree/nhánh `codex/asr-s3-native` user chỉ định. Đầu phiên HEAD S2
  `d21251a` + 50 file S3 dirty và prompt S4 untracked. Theo yêu cầu riêng, commit/push **S3**
  thành `327c214bcc749f49f160e89594d3c95902698403` trước khi sửa S4. Giữ toàn bộ nội dung S3,
  prompt S4 vẫn nguyên vẹn untracked. **S4 chưa commit/push/tag/release**, không làm S5/S6.
- Core typed/frozen cho nhân vật, scoped speaker mapping, người nghe nhóm/unknown, người được
  nhắc đến, loại lời, cảnh/cue scope, quy tắc có hướng và evidence/status. User/lock ưu tiên;
  proposal text phải có cue evidence, không tự gán danh tính/người nghe hoặc nối request mới.
  Conflict/missing có review, không lấy diarization làm bằng chứng quan hệ.
- Snapshot toàn tài liệu trước dịch song song, dùng cả khi dịch lại 1–9 cue. LLM nhận rule đã
  resolve + source window/evidence, chỉ trả text; không sửa timing, ID hay speaker. Cache có
  policy/source/IDs/config/rules/override tất định, không dùng brief LLM ngẫu nhiên; stale state
  bị từ chối. Context S4 dùng credential job, request deadline/cancel/cleanup hữu hạn, không echo
  raw error/context. Google/Bing/DeepLX giữ dữ liệu nhưng không áp quy tắc; UI giải thích giới hạn.
- Sửa nền S3 liên quan: giữ cue ID qua ASR/clone/JSON/editor; native ID gồm scope để không bám
  nhầm context vào request mới; speaker override giữ ASR provenance và không lặp prefix;
  manual load/export/handoff bảng giữ events/context; CLI subtitle đọc được JSON ASR/project.
- GUI More → Ngữ cảnh xưng hô có bảng sửa/khóa/review; mutation atomic qua CommandStack,
  editor dịch selection undo/redo và không tự đổi voice/TTS text. Worker được chờ khi app quit.
  Normal save vẫn editor-project-v1 JSON + SRT, ASS chỉ khi chọn. SRT mất metadata/context và
  không tự thêm nhãn speaker. Context đã gắn thì phải tắt split; association mới cần review.
- Gate: ruff toàn source/tests pass; pyright **0 errors/0 warnings**; sync translations và
  diff-check pass. Full offline cuối **910 passed, 5 skipped, 51 deselected**, **105.38 s**
  (baseline 862 + 48 mới), gồm toàn CLI và các domain liên quan. Gate gần trước regression
  shutdown cuối **60 passed**. QThread tests wait; settings/config/env cô lập, Python 3.12.13
  import đúng working tree, dùng toolchain/FFmpeg có sẵn, không sync/cài dependency.
- 5 skip vẫn là QtMultimedia native playback và bốn test TTS cần dịch vụ; 51 deselect theo
  integration/slow/llm. Đã render dialog tiếng Việt với font Noto Sans SC; JSON vi sync, TS en/zh
  cập nhật, QM giữ baseline vì thiếu lrelease (chuỗi zh mới fallback English).
- Artifact **`dist/VideoCaptioner-ASR-S4-Review-20260907/`**: build sạch từ duy nhất spec,
  **exit 0; 6 warnings optional/platform, 0 ERROR**. Đối chiếu **21 module bytecode từ chính EXE**
  khớp source cuối và prompt/JSON vi khớp bytes; không bundle Torch/Qwen/Torchaudio.
  EXE **31.057.002 byte**, timestamp máy **2026-09-07 11:31:30**, SHA-256
  `08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`.
  Onedir trước smoke **573 file / 237.192.253 byte**. Build dùng scratch riêng; chỉ rebuild
  output S4 do phiên này tạo trước khi có AppData. EXE S3 vẫn nguyên SHA-256 baseline.
- Smoke từ artifact: hidden GUI đúng cửa sổ Qt, sống **25 s**, `WM_CLOSE` → **exit 0**, không
  process artifact sót, log **0 Traceback/ERROR/CRITICAL**. Stderr 103 byte là thông tin version
  check, không lỗi import/resource. Harness lượt đầu lỗi encoding khi in tên cửa sổ; đã chạy
  lại UTF-8, lưu report đầy đủ và kiểm tra stderr riêng. Không rebuild sau khi smoke tạo AppData.
- **Chưa nghiệm thu bản dịch LLM thật/chất lượng xưng hô bằng người đọc**: worktree/env không có
  key LLM. **Soniox/Scribe online, GPT gateway→SRT, workflow media/API từ EXE chưa nghiệm thu**;
  **phồn thể Qwen strict chưa đạt acceptance**. S2 local alignment/S3 startup là bằng chứng riêng.
  Không dùng mock làm ground truth, không lấy credential/media/runtime từ checkout khác.
- Hướng dẫn và giới hạn: [ASR context S4](docs/dev/asr-context-s4.md). Bàn giao/manifest:
  [implementation S4](docs/dev/asr-implementation-2026-09.md#bàn-giao-s4--2026-09-07).

## 2026-09-07 (ASR S3: native Soniox/Scribe và speaker metadata; dừng để review)

- Baseline đúng `origin/codex/asr-s2-alignment` tại `d21251a5d1be3d4baceec5a3e8d6869ceb4877c5`,
  đã xác minh code S2 `96470bf7` là ancestor. Worktree riêng, nhánh `codex/asr-s3-native`;
  giữ nguyên checkout master và các tài liệu untracked của user. Chưa commit/push.
- Native Soniox `stt-async-v5` upload/submit/poll/result, Scribe `scribe_v2` multipart/words/events;
  không ép qua Whisper route, không đổi mặc định, không dùng key gateway. Toàn file có preflight
  byte/duration; GET retry/deadline hữu hạn, POST không tự resubmit khi acceptance không chắc chắn.
  Hủy in-flight local và cleanup tài nguyên đúng job; giới hạn remote cancellation/chi phí hiển thị rõ.
- `ASRMetadata` optional với speaker anonymous scope riêng mỗi request; canonical ms có validation,
  giữ overlapping speech và events riêng. Không tạo timestamp/speaker giả, không suy danh tính/xưng hô.
  Cache có version, hash audio/provider/endpoint/model/language/options/speaker policy, giữ scope;
  không lưu remote IDs/credential/raw error body. Cache S1/S2 không bị trộn.
- Speaker/events giữ qua copy, split theo span đo, optimize một cue mỗi request, translate input,
  GUI/CLI in-memory handoff, JSON/editor. Merge khác speaker/source bị chặn; legacy fuzzy chunk merger
  từ chối native metadata. Editor giữ `editor-project-v1`, cue IDs, CommandStack và JSON+SRT normal save.
  Cue native chưa có explicit text boundary nên nút split editor dừng review; không dùng chia chữ/timing
  ước lượng. SRT không tự chèn speaker; JSON giữ metadata. Preview overlay còn hiển thị một active cue.
- CLI/GUI thêm engine/config/probe tường minh, key riêng theo provider/endpoint, không network khi mở
  settings; worker giữ contextvars, cancel và wait. Đã render kiểm tra settings tiếng Việt và sửa mô tả
  bị cắt dòng. TS có chuỗi en/zh mới, JSON vi đồng bộ; chưa compile QM mới do thiếu lrelease trong
  toolchain hiện có, nên chuỗi mới ở locale zh dùng fallback English trong artifact hiện tại.
- Gate core đầy đủ cuối: **862 passed, 5 skipped, 51 deselected**, 96,71 s (baseline 768 + 94 test mới).
  Skip: native playback/TTS cần dịch vụ; deselect: integration/slow/llm. Ruff toàn source/tests pass;
  pyright 0 errors/0 warnings; toàn CLI + native ASR/pipeline/UI 171 pass; sau sửa chiều cao label,
  17 tests settings/UI pass. Sync translations và diff-check pass. Không đổi/cài dependency.
- **Chưa nghiệm thu Soniox/Scribe online**: không có key native trong worktree/env, không lấy key/media
  từ checkout khác. Giữ nguyên khoản thiếu S2: GPT gateway→SRT chưa nghiệm thu và phồn thể Qwen strict
  chưa đạt acceptance. S2 local alignment/EXE startup đã đo ở baseline, không suy thêm từ mock S3.
- EXE review cuối: PyInstaller exit 0, 6 warnings optional/platform, 0 errors; 36 module bytecode
  khớp source. EXE 31.023.698 byte, SHA-256 `0e3be9f4…3761ebec`, timestamp máy 10:13:24.
  Onedir 572 file / 237.121.067 byte trước smoke. GUI hidden có đúng cửa sổ Qt, sống qua 25 s,
  WM_CLOSE → exit 0, 0 process sót/0 startup error markers. Workflow media/API từ EXE chưa đo.
- Hợp đồng, limits/retry/cancel, lựa chọn kỹ thuật và giới hạn:
  [ASR native S3](docs/dev/asr-native-s3.md). Artifact và danh sách file:
  [bàn giao S3](docs/dev/asr-implementation-2026-09.md#bàn-giao-s3--2026-09-07).
- Dừng ở S3 để review; không triển khai S4–S6, bảng nhân vật/addressee/xưng hô, gán giọng hoặc pyannote.

## 2026-09-07 (ASR S2: JSON → alignment tiếng Trung, dừng để review)

- Baseline đúng `origin/codex/asr-s1-api-profiles`, commit
  `43bb76f45d8dc12cd107fbcbd92c7e21ab811cc3`. Làm trong worktree/nhánh
  `codex/asr-s2-alignment`; giữ nguyên master và ba tài liệu untracked của checkout nguồn.
- `AlignedAPI` nối JSON S1 qua runtime Qwen riêng vào ASRData/SRT cho CLI/GUI; preflight
  Chinese + runtime/model/CUDA trước upload. Chunk lossless <=240 s, cắt ở silence, không overlap,
  không bỏ tail. Model limit 300 s; không dùng chunk ASR 10 phút.
- Contract ms strict giữ nguyên text/dấu câu, kiểm tra coverage/bounds/overlap/silence; tắt
  nội suy `fix_timestamp` của upstream Qwen. Thiếu/trùng chữ, zero-length, lệch timing hoặc
  không có ranh cắt an toàn dừng review cả job, không tạo SRT một phần/timestamp giả.
- Runtime Windows Python 3.12 CUDA riêng, lock có hash (Qwen 0.0.6, Torch 2.8.0+cu128), model pin
  `c7cbfc2048c462b0d63a45797104fc9db3ad62b7`; tải chỉ qua builder tường minh. Job/probe offline,
  process ẩn, lọc credential env, timeout/cancel/đóng cả Windows venv process tree. Qt không import
  Torch/Qwen; worker probe giữ contextvars và `wait()`. S2 HTTP async hủy socket được, giữ retry S1.
- Cache nhận dạng và alignment tách riêng; key hash theo audio/text/config/model/revision/policy.
  Preset, key theo endpoint, model/base/prompt/language và engine mặc định S1 được giữ.
- Alignment thật: clip Qwen Trung công khai 4.204 s → 13 span 400–3680 ms và SRT; warm ~0.10 s,
  peak Torch allocation ~1.76 GiB. Câu lệch audio và silence bị chặn; bản phồn thể cũng bị strict
  validator chặn, **chưa đạt acceptance phồn thể**. Không suy chất lượng cả corpus từ clip này.
- Gateway thật/GPT→SRT chưa nghiệm thu: worktree không có settings ASR hay env ASR key, không lấy
  credential/media từ checkout khác. Không triển khai S3–S6.
- Sau bàn giao, user yêu cầu commit/push S2 và prompt session tiếp theo: code S2 commit
  `96470bf7c60eb7598f61eb7d450327011f9f19c8` trên `codex/asr-s2-alignment`.
  [Prompt S3](docs/dev/asr-step-3-prompt.md) giữ baseline, guard S1/S2 và các phần chưa nghiệm thu;
  quyền commit/push của lượt bàn giao này không tự áp dụng cho thay đổi S3 ở session mới.
- Gate cuối: ruff/sync translations/diff-check pass; pyright 0 errors/0 warnings; full offline
  **768 passed, 5 skipped, 51 deselected** (83.74 s). EXE review PyInstaller exit 0, 6 warnings
  optional/platform (chi tiết trong bàn giao); EXE 30,985,630 byte, SHA-256 `133d04bb…55d5cb6`.
  Cửa sổ chính từ artifact sống qua 25 s, đóng sạch. Bytecode/recipe S2 đã đối chiếu source;
  workflow media/API từ EXE chưa nghiệm thu, base artifact không chứa GPU runtime/model.
- Chi tiết contract, cài runtime, giới hạn và số đo: [ASR alignment S2](docs/dev/asr-alignment-s2.md).
  Gate cuối và danh sách file: [bàn giao S2](docs/dev/asr-implementation-2026-09.md#bàn-giao-s2--2026-09-07).

## 2026-09-07 (ASR S1: request profile, preset gateway/Groq và gate offline)

- Hoàn tất S1 offline: registry provider/model/profile nhẹ; request/parser chung WhisperAPI/probe;
  Whisper/Groq giữ timing, GPT JSON probe được và subtitle preflight báo cần alignment S2 trước upload.
- Cache v2 SHA-256 cách ly endpoint/request/timing, prompt được hash; MIME theo bytes, cap upload,
  timeout/retry hữu hạn, lỗi/log không echo key/prompt/raw provider response. Không giả timestamp.
- Settings hai mặt có preset VideoCaptioner API/Groq/OpenAI/Custom và model nhập tay; giữ cấu hình
  preset, key theo endpoint và ngôn ngữ user. CLI thêm provider/profile theo precedence cũ; đổi endpoint
  không tự thừa kế key. Probe chạy worker chung giữ contextvars; không network khi mở settings.
- Validation: ruff toàn source/tests pass; pyright 0 error/0 warning; CLI và tests gần thay đổi pass;
  full offline **720 passed, 5 skipped, 51 deselected** (76,48 s); sync translations pass. Đã sửa
  startup guard bị kéo theo SDK OpenAI trong lượt test đầu. Dùng Python 3.12.13/môi trường project có
  sẵn, xác nhận import worktree; FFmpeg có sẵn, Qt offscreen, settings/cache/basetemp test cô lập.
- Online/EXE chưa nghiệm thu; không có key ASR trong worktree/env, không đọc/copy key checkout nguồn.
  Docs OpenAI/Groq đã đọc lại; trang docs gateway không tải được bằng web tool ở lượt này, giữ hợp đồng
  đã chấp nhận trong nghiên cứu. Không cài dependency, không build/phát hành, không triển khai S2–S6.
- Chi tiết hành vi, giới hạn, từng gate, manifest file và đầu vào S2:
  [bàn giao S1](docs/dev/asr-implementation-2026-09.md#bàn-giao-s1--2026-09-07).

## 2026-09-05 (Nghiệm thu VieNeu qua GUI one-app, sửa treo EXE, cập nhật model theo đề nghị, tài liệu, CI Node 24)

### Lỗi phát hiện từ log one-app trước khi nghiệm thu (mục 1)
- Log `dist/VideoCaptioner-VieNeu-OneApp-20260905/AppData/logs/app-2026-09-05.log` của hai lần user chạy (10:51 và
  11:12): `VieNeu auto-update failed: 'NoneType' object has no attribute 'write'` ngay khi mở tab Lồng tiếng, và hai
  process one-app còn sống không cửa sổ (PID 27060/28060, working set 3.8/6.7 MB). py-spy: main thread kẹt ở
  `tqdm._monitor.TMonitor.exit` → `join()`, thread monitor của tqdm kẹt chờ lock. Nguyên nhân: EXE windowed khởi động
  với `sys.stderr = None`; `tqdm.refresh()` (tqdm 4.67.1) giữ lock rồi `display()` ném AttributeError, lock không được
  nhả, atexit của tqdm join monitor vô hạn → mọi update model fail và app treo khi thoát. Sửa `5fc914a`:
  `ProgressTqdm` không tạo monitor thread và dùng sink ghi khi thiếu stderr; `scripts/pyinstaller_gui.py` thay
  stdout/stderr None bằng devnull cho cả đường GUI; test `test_hub_client_progress_bar_works_without_stderr` dò lock
  của đúng lớp bar (`tqdm.auto` và `tqdm.std` có lock riêng nên dò `tqdm.std` là vô nghĩa).
- Cùng log: `Dubbing thất bại: cannot schedule new futures after interpreter shutdown` lúc 11:56 khi user đóng app
  giữa job. Sửa `4111c6b`: `DubbingThread._progress_callback` ném `DubbingCancelled` khi thread bị
  `requestInterruption()` (callback chạy cả trong worker TTS nên job unwind mà core không cần cancel token);
  `MainWindow.closeEvent` yêu cầu dừng sớm, tắt sidecar/child process như cũ rồi `wait_for_dubbing_job(10 s)`; job bị
  hủy không hiện popup/report. Test mới `tests/test_thread/test_dubbing_thread.py`.
- Hai process treo được dừng thủ công sau khi lấy stack.

### Auto-update VieNeu: chỉ kiểm tra rồi đề nghị (mục 3, `6055687`)
- Trước: mở tab Lồng tiếng là tải ~1.7 GB và validate GPU âm thầm, tiến độ ghi vào widget đang ẩn, action của user
  xếp hàng sau. Nay `Auto update` bật → khởi động chỉ `check`; có bản mới → InfoBar "Có bản cập nhật mô hình VieNeu"
  với nút "Tải và kích hoạt"; nút "Kiểm tra cập nhật mô hình" cũng check rồi đề nghị; tắt `Auto update` → không kết
  nối mạng lúc khởi động. Khi tải: progress bar + status label của tab hiện "Downloading VieNeu model: Downloading
  bytes 799/1678 MB" (`describe_download_progress` gom ba bar của huggingface_hub: số file, bytes tải, bytes ghi; giữ
  phần trăm đơn điệu), rồi "Validating VieNeu candidate on the GPU..."; kết quả tách bạch: đã kích hoạt / đã tải nhưng
  hoãn vì có job giữ lease / đã mới nhất / offline. Action `auto-update` của thread bị bỏ; label trạng thái thêm
  "có bản <sha12>". Test GUI với hub giả: launch check không tải gì, bấm nút mới tải + kích hoạt qua fake bridge
  (+2 test trong `test_ui_thread.py`), test `describe_download_progress`; 11 chuỗi dịch vi_VN mới.

### Nghiệm thu VieNeu qua chính GUI one-app (mục 1)
- One-app build lại từ `6055687` (dời `AppData`/`work-dir` của bản cũ ra ngoài rồi trả lại, vì PyInstaller
  `--noconfirm` xóa cả `dist/<name>`), rồi điều khiển bằng UI Automation: pywinauto backend uia qua
  `uv run --frozen --with pywinauto` (không đổi dependency), nút tìm theo text tiếng Việt, `invoke()` cho InfoBar nằm
  ngoài màn hình (tab cao hơn 1440 px ở 125 %), `set_edit_text` cho LineEdit đường dẫn.
- Kết quả (104.7 s tổng): mở tab → 1.1 s sau có InfoBar đề nghị `8b7e9cff` (HF main đã qua `19dd1cc`); Start → Ready
  sau 32 s (cold), tự nạp 20 giọng, combo giữ "Ngọc Huyền"; lồng tiếng thủ công clip 14.32 s (3 câu, `allow-overlap`)
  xong sau 8.7 s → `smoke_dubbed.mp4` h264 + aac 12.99 s, report 3 group (2 fit, 1 speed_adjust 1.15x + allow_overlap);
  bấm "Tải và kích hoạt": tải 1678 MB trong ~20 s, validate GPU (Stopping → Starting → Ready `8b7e9cff`) ~11 s, InfoBar
  "Đã cập nhật mô hình VieNeu / Bản 8b7e9cffb4b4 đang hoạt động."; `state.json` active `8b7e9cff…14a6`, previous
  `2da0efab…ef5b`, `rejected_revisions` rỗng (không cần rollback); "Tải danh sách" lại 20 giọng từ model mới; lồng
  tiếng lần 2 OK (8.8 s); Stop → Stopped, python runtime tắt; đóng cửa sổ exit 0, 0 process sót.
- Log app sau đó chỉ còn 2 traceback cosmetic lúc teardown (`wrapped C/C++ object of type BottomInfoBarManager has
  been deleted` từ event filter của qfluentwidgets). Sửa `8b47447`: `closeEvent` gỡ các InfoBarManager khỏi event
  filter của cửa sổ; smoke lại trên bản build cuối (mở tab, kiểm tra cập nhật → InfoBar "Mô hình VieNeu đã mới nhất",
  đóng): exit 0, log không traceback.
- Chưa làm: installer WiX, nghe thủ công chất lượng giọng, workflow LLM thật và TTS OpenAI/MiniMax thật.

### Tài liệu (mục 2, `1e0a98c`)
- `docs/dev/architecture.md` + `docs/en/dev/architecture.md`: style_presenter, core/llm/services, core/editor/presenter,
  `entities.enum_from_display`, env `VIDEOCAPTIONER_VIENEU_RUNTIME`, guard stderr trong entry EXE, quy tắc
  `thread.wait()`, builder `--no-config`; `docs/dev/vieneu-one-app.md`: hàng đợi action, luồng check → đề nghị, flag
  builder, guard symlink, ví dụ `--source` không còn đường dẫn tuyệt đối; `docs/dev/view-structure.md` viết lại theo
  view hiện tại; AGENTS.md/CLAUDE.md thêm quy tắc `thread.wait()` cho test QThread qua QEventLoop và gate
  `ruff check videocaptioner/ tests/`.

### CI (mục 5, `e6b81ad`)
- actions/checkout v7, setup-python v7, astral-sh/setup-uv v10.0.1 (ghim tag đầy đủ: từ v8 setup-uv không còn tag
  major floating nên `@v10` làm CI fail ở Set up job; `enable-cache: true` vẫn tường minh nên đổi mặc định của v10 không
  ảnh hưởng), setup-node v7 (+ cache npm theo `docs/package-lock.json`), upload-artifact v7,
  download-artifact v8, upload-pages-artifact v5, deploy-pages v5; các input đang dùng không đổi ở các major này.
  Job quality thêm `ruff check tests/` (sửa 1 lỗi I001 ở `tests/test_editor/test_architecture_contract.py`). Chưa
  push nên CI chưa chạy với các workflow mới.

### Comment CJK đợt 3 (mục 4, `66d29f0`)
- 429 mục trong `ui/view/setting_interface.py` (101), `ui/components/FasterWhisperSettingWidget.py` (101),
  `core/split/split.py` (85), `core/entities.py` (76), `ui/components/WhisperCppSettingWidget.py` (66); thay đúng token
  (file, dòng), giữ CRLF. Còn **838 mục / 55 file**; nhiều nhất: `ui/view/batch_process_interface.py` 49,
  `ui/view/transcription_interface.py` 46, `ui/view/subtitle_style_interface.py` 44, `ui/thread/batch_process_thread.py`
  43, `ui/view/llm_logs_interface.py` 35. Bốn view ~1000 dòng vẫn chủ yếu là layout, không tách thêm.

### Build lại từ HEAD `8b47447` (mục 6)
- Base (`python -m PyInstaller VideoCaptioner.spec --clean --noconfirm` bằng `.venv`): exit 0, 0 error, 6 warning quen
  thuộc (js/emscripten, curl_cffi, yt_dlp_ejs, AppKit, tzdata, sip). `dist/VideoCaptioner/VideoCaptioner.exe`
  30,946,521 byte, 2026-09-05 13:23, SHA-256 `953f5f9f195ce826a3e52f098f19bbe66f859e9cfddfa26ceb5bdd5da22cf77a`;
  524 file / 234.5 MB, đủ prompts/resources/assets/fonts/translations/subtitle_style. Smoke: cửa sổ sau 5.8 s, đóng
  exit 0, không process sót, log chỉ có dòng version check.
- One-app (`scripts/build_vieneu_one_app.py --overwrite`, giữ AppData): exit 0, 6 warning như trên. EXE 30,946,521
  byte, SHA-256 `A8EFD5F85763D977563900F189609C5AD26E6070406AA3F3C50F534F7B6F2FDC`, runtime 29,256 file / 5.91 GB,
  seed 42 file / 1.77 GB (`2da0efab` từ repo AppData); AppData thật của bản one-app (settings, tool 4.9 GB, cache,
  model state active `8b7e9cff`) đã trả lại. Smoke `dubtab`: exit 0, không process sót, log không traceback.
- Nghiệm thu GUI ở mục 1 chạy trên bản build từ `6055687`; các commit sau chỉ đổi comment, docs, CI và
  `_detach_info_bar_managers`, đã smoke lại trên bản cuối.

### Gate
- ruff `videocaptioner/ tests/` pass; pyright `videocaptioner/` 0 errors / 0 warnings sau mỗi commit code;
  `sync_translations --check` in sync; test theo commit: test_vieneu + test_thread + test_ui (54 passed),
  test_cli + test_ui + test_split (190 passed); full suite offline (`-m "not integration and not slow and not llm"`,
  basetemp ngắn): **645 passed, 4 skipped (TTS cần API key), 51 deselected** trong 1:19, 1 warning.
- Phát hiện thêm khi so mtime: `tests/test_editor/test_startup_responsiveness.py` chạy GUI trong process con nên
  fixture cô lập `cfg.file` của root conftest không áp dụng; child ghi lại `AppData/settings.json` thật (hôm nay nội
  dung y nguyên, hash không đổi, nhưng `cfg.transcribe_model.value = BIJIAN` trong script có thể lọt vào file thật).
  Sửa: helper `_run_script` chèn preamble trỏ `cfg.file` sang thư mục tạm; chạy lại file test, mtime không đổi.
- Sự cố phiên: một script debug chạy ngoài pytest lúc 12:57 dựng `DubbingInterface` với `cfg` thật và đổi provider
  combo, nên có thể đã ghi `Dubbing/TTSProvider = vieneu-local` vào `AppData/settings.json` của repo (khóa khác không
  đổi; không có backup để so). Nếu trước đó dùng OpenAI thì đổi lại trong tab Lồng tiếng.
- 9 commit local `5fc914a..HEAD`, chưa push theo yêu cầu.

## 2026-09-04 (Sau roadmap: build EXE nghiệm thu, tách view đợt 2, dịch comment, pyright sạch, layout test)

### Build EXE onedir, smoke và workflow thật (mục 1)
- `uv run --frozen pyinstaller VideoCaptioner.spec --clean --noconfirm` tại HEAD `176ca84` (trước các thay đổi
  mục 2–5): exit code 0, 0 error, 6 warning không đáng chú ý (`urllib3.contrib.emscripten` thiếu module `js`,
  `curl_cffi`/`yt_dlp_ejs` không phải package nên bỏ qua data, `darkdetect` import AppKit chỉ có trên macOS).
- Artifact `dist/VideoCaptioner/VideoCaptioner.exe`: 30,934,673 byte, 2026-09-04 22:53, SHA-256
  `f4a00cc16f6830a2363d75a77ed9d386d9df13a0178df3f3606aa376135c86c6`; thư mục onedir 225 MB / 524 file, đã có
  `videocaptioner/core/prompts`, `videocaptioner/resources`, `resource/{assets,fonts,translations,subtitle_style}`.
- Smoke: khởi động EXE từ `dist/VideoCaptioner`, sau 20 s process vẫn sống (working set 139 MB), cửa sổ chính
  "Trợ lý phụ đề Kaka -- VideoCaptioner" hiện, EXE tự tạo `AppData/` riêng dưới `dist/` (cache DB + log ngày),
  dừng đúng PID do test tạo. Không đụng `AppData/settings.json` của repo (hash không đổi).
- Theo yêu cầu, tải công cụ bằng chính cơ chế của app để test dễ hơn: FFmpeg (BtbN qua
  `installer.ensure_ffmpeg()` → `AppData/bin/ffmpeg`), Faster-Whisper-XXL r245.2 bản GPU (ModelScope, giải nén
  bằng 7-Zip vào `AppData/bin/Faster-Whisper-XXL`), model `faster-whisper-large-v3` (3.09 GB, ModelScope vào
  `AppData/models`). Máy có RTX 5070 12 GB, driver 616.56. `config.py` tự prepend các thư mục này vào PATH của
  process nên test pydub/`silent_video` nay chạy thật; shell ngoài vẫn không có `ffmpeg` trên PATH.
- Workflow thật chạy từ source (EXE chỉ có GUI): clip 14 s giọng SAPI ghép FFmpeg → `video2audio` → `transcribe()`
  FasterWhisper large-v3 trên CUDA: 28 segment word-level đúng nội dung trong 49.6 s (gồm nạp model), 5 sự kiện
  progress; CLI `synthesize` hard (CRF 32) và soft: exit 0, output h264+aac 14.32 s, bản soft có stream
  `mov_text`. Các subprocess ffmpeg/ffprobe/faster-whisper-xxl đều chạy qua `env=child_environment()`.
- Chưa nghiệm thu: LLM thật (không có API key hay local server), dubbing/TTS thật, auto-update, và workflow
  chạy trực tiếp qua EXE. EXE này build từ `176ca84` nên chưa chứa các thay đổi mục 2–5.

### Tách logic khỏi view đợt 2: style, settings, editor (mục 2)
- `core/subtitle/style_presenter.py` (không import Qt): `PREVIEW_TEXTS`/`PREVIEW_ORIENTATIONS`,
  `preview_text_pair`, `default_background`/`preview_background`, `parse_rgba_hex`/`format_rgba_hex`,
  `font_choices` + `pil_can_load_font`, `style_file_path`/`resolve_style_path`/`list_style_ids`/`choose_style_id`/
  `save_style`, `rounded_bg_style`, `render_style_preview` (chọn renderer theo `StyleMode`), `first_image_path`.
  `SubtitleStyleInterface` (1281 → 967 dòng) chỉ còn snapshot widget ↔ `SubtitleStyle` (`_ass_style`,
  `_rounded_style`, `_apply_style`); hai QThread preview gộp thành `StylePreviewThread`; `generateAssStyles`
  thay bằng `SubtitleStyle.to_ass_string()` (cùng chuỗi ASS, bold=-1); load/save rounded đi qua
  `SubtitleStyle.from_file`/`to_json_dict` thay vì dict thủ công.
- `core/llm/services.py`: `LLM_SERVICE_PRESETS` (prefix trong settings.json, attr trên `cfg`, base mặc định, model
  gợi ý, base có sửa được hay không, key mặc định cho Ollama/LM Studio, placeholder), `settings_prefix_for`,
  `fill_default_api_key`, `missing_whisper_api_fields`; `core/entities.enum_from_display` thay
  `_enum_from_display`. `SettingInterface` (1120 → 1006) dựng card theo bảng; CLI `GUI_LLM_SERVICE_PREFIX` suy
  ra từ cùng bảng nên không còn hai bản map provider.
- `core/editor/presenter.py`: `new_cue_span`/`new_cue` (`CuePlacementError.reason` = `inside_cue`/`no_space`),
  `split_position`, `inspector_commands`, `track_state_command`/`track_locked`, `layer_range`,
  `unique_layer_name`, `layer_properties`, `new_layer`, `layer_index`, `layer_pending_changes`,
  `layer_list_label`, đường dẫn gợi ý và `preview_output_path`. `VideoEditorInterface` (1117 → 1043) giữ dialog
  trong `_ask_layer_value`; `CommandStack` và các command hiện có không đổi.
- Test mới: `tests/test_subtitle/test_style_presenter.py` (26), `tests/test_ui/test_subtitle_style_interface.py`
  (5, offscreen, `SUBTITLE_STYLE_PATH` trỏ tmp, preview stub, cfg.file đã cô lập), `tests/test_llm/test_services.py`
  (6, gồm đối chiếu với CLI), `tests/test_ui/test_setting_interface.py` (5), `tests/test_editor/test_presenter.py`
  (15).
- Validation: ruff `videocaptioner/` pass; pyright 0 errors; test_ui/test_subtitle/test_llm/test_cli/test_editor/
  test_thread/test_dubbing/test_translate/test_utils offline: **393 passed, 26 deselected**.

### Dịch comment/docstring tiếng Trung đợt 2 (mục 3)
- 163 mục trong 6 file: `core/asr/faster_whisper.py` (34), `core/subtitle/rounded_renderer.py` (43),
  `core/subtitle/ass_renderer.py` (36), `ui/thread/video_download_thread.py` (33),
  `ui/thread/file_download_thread.py` (13), `core/asr/whisper_cpp.py` (4). Chỉ token COMMENT và docstring
  theo `tokenize`, thay đúng (file, dòng); chuỗi `tr()` và message log giữ nguyên. ruff pass, import được.
- Còn lại theo cùng thống kê: **1267 mục / 60 file**. Nhiều nhất: `ui/view/setting_interface.py` 101,
  `ui/components/FasterWhisperSettingWidget.py` 101, `core/split/split.py` 85, `core/entities.py` 76,
  `ui/components/WhisperCppSettingWidget.py` 66, `ui/view/batch_process_interface.py` 49,
  `ui/view/transcription_interface.py` 46, `ui/view/subtitle_style_interface.py` 44,
  `ui/thread/batch_process_thread.py` 43, `ui/view/llm_logs_interface.py` 35, `core/asr/chunk_merger.py` 34,
  `core/optimize/optimize.py` 33, `core/asr/chunked_asr.py` 32; 47 file còn lại mỗi file ≤ 31.

### Dọn 9 warning pyright còn lại (mục 4)
- `ui/thread/video_download_thread.py`: typeshed gõ `YoutubeDL(params)` bằng TypedDict riêng `_Params` (không có
  trong package yt-dlp 2026.7.4) còn dict option được dựng động, nên `cast(Any, ...)` ở hai điểm gọi kèm comment.
- `ui/thread/subtitle_pipeline_thread.py`: `file_path`/`output_path` của `FullProcessTask` là Optional; thu hẹp
  trước khi dựng đường dẫn video lồng tiếng, thiếu thì báo qua `handle_error` (TaskFactory luôn đặt hai giá trị).
- `ui/view/batch_process_interface.py`: `_current_task_type()` thu hẹp `currentData()` (chỉ None trước init) về
  `FULL_PROCESS` mặc định, dùng ở 5 chỗ đọc task type.
- Validation: pyright `videocaptioner/` **0 errors, 0 warnings**; ruff pass.

### Test layout editor ổn định dưới offscreen trên Windows (mục 5)
- Nguyên nhân: offscreen Qt trên máy Windows dùng font Helvetica 12pt (native là MS Shell Dlg 2 7pt) nên hàng bốn
  nút Blur/Logo/Mask/Text trong `QHBoxLayout` đẩy `minimumSizeHint` của tab Layers lên 356 px; `QSplitter` tôn
  trọng min đó nên preview chỉ còn 306 px. Sửa: hàng nút dùng `FlowLayout` của qfluentwidgets (min bằng một nút,
  tự xuống dòng khi hẹp hoặc font lớn); test giữ nguyên ngưỡng 320/290/300. Đo lại offscreen: preview 372,
  tabs 294.
- Validation: `test_ui_sync_performance.py` offscreen 6 passed 1 skipped (QtMultimedia); native
  `test_ui_sync_performance` + `test_visual_layers` 26 passed. Full suite offline cuối cùng
  (`-m "not integration and not slow and not llm"`, basetemp ngắn) với FFmpeg/Whisper thật: **636 passed,
  4 skipped (TTS cần API key), 51 deselected** trong 1:15; hash `AppData/settings.json` không đổi.

### VieNeu Local: dựng runtime, kích hoạt model và one-app (2026-09-05)
- Yêu cầu: máy chưa có model lồng tiếng VieNeu. Clone `pnnbao97/VieNeu-TTS` vào `D:\AI-Work\VieNeu-TTS` đúng commit
  pin `36c4b501`, build runtime bằng `scripts/build_vieneu_runtime.py` → `build/vieneu-runtime-20260904` (5.6 GB,
  Python 3.12 + torch 2.8.0+cu128, smoke `ok 2.8.0+cu128 True`).
- Lỗi 1: `uv pip install --require-hashes` trong builder (uv 0.11.6) kéo `[tool.uv] override-dependencies`
  PyQt5-Qt5 của workspace vào và fail vì thiếu hash. Builder nay truyền `--no-config` cho cả hai lần `uv pip install`.
- Lỗi 2: huggingface_hub 1.28 dò symlink theo thư mục cache một cách lười và không khóa; với nhiều thread tải,
  thread thứ hai qua mặt probe và `os.symlink` ném WinError 1314 trên máy không có quyền symlink (Developer
  Mode tắt). `HuggingFaceVieNeuClient.snapshot_download` nay ép `HF_HUB_DISABLE_SYMLINKS` (env + `constants`)
  trên win32 để cache luôn là file thường; 2 test mới trong `tests/test_vieneu/test_model_updater.py`.
- Model: tokenizer/codec MOSS `6aa02b01` và `pnnbao-ump/VieNeu-TTS-v3-Turbo` revision pin `2da0efab` (HF main đã
  là `19dd1cc`) tải vào `AppData/models/vieneu/hf` (1.7 GB); `videocaptioner vieneu update --revision 2da0efab…`
  với `VIDEOCAPTIONER_VIENEU_RUNTIME` trỏ runtime vừa build: sidecar khởi động trên RTX 5070, health/voices/WAV
  pass, active revision `2da0efab`, sidecar tắt sạch (0 process sót).
- Lồng tiếng thật từ source: `dub smoke.mp4 --subtitle smoke_vi.srt --tts-provider vieneu-local --voice "Minh Đức"
  --timing-mode natural --mix-mode mute`: 3 nhóm TTS thành công (0 failed). Lần 1 dừng đúng policy `review`
  (exit 6: câu 1 audio 4.75 s / khung 3.22 s, tỷ lệ 1.48); lần 2 `--unresolved allow-overlap` ra
  `smoke_dubbed.mp4` h264 + AAC 48 kHz 14.32 s, report `output_created: true`.
- One-app: `scripts/build_vieneu_one_app.py --name VideoCaptioner-VieNeu-OneApp-20260905` từ HEAD `ed2c3a4` + hai
  fix trên: EXE 30,941,586 byte SHA-256 `3822ED7E…B600FC`, runtime 29,256 file / 5.91 GB, model seed 42 file /
  1.77 GB (tổng 7.7 GB), `distribution-manifest.json` ghi đủ revision. Locator/store của app đọc được runtime và
  ba snapshot trong gói. Smoke EXE one-app 30 s: cửa sổ chính hiện, không spawn process con, không lỗi log.
- Chưa nghiệm thu: bấm Start/Update/lồng tiếng từ chính GUI one-app, auto-update nền lên `19dd1cc` (chưa chạy
  vì smoke chỉ 30 s), installer WiX, nghe thủ công chất lượng giọng.

### VieNeu GUI: không tải được danh sách giọng (2026-09-05)
- Báo cáo từ bản one-app: bấm "Tải danh sách" với VieNeu Local không ra giọng. Log one-app cho thấy sidecar đã
  khởi động và báo `voices=20`, nên lỗi nằm ở tầng GUI. Nguyên nhân: `main_window` chạy action `auto-update`
  (mặc định) bằng một `VieNeuRuntimeThread` riêng không nằm trong `_vieneu_threads` của tab Lồng tiếng, còn
  `_start_vieneu_action` bỏ qua im lặng mọi action khi đã có thread đang chạy; `_fetch_voices` lại đổi nút thành
  "Đang tải..." và disable trước khi gọi, nên nút kẹt vĩnh viễn khi bấm trong lúc check/update hoặc ngay sau Start.
  Hai luồng dùng chung một sidecar còn có thể chạy song song (launch update + Start của user).
- Sửa `dubbing_interface.py`: action đến khi bận được xếp vào `_vieneu_pending_action` (mới nhất thắng) và chạy
  khi thread hiện tại `finished`; status label báo "VieNeu: busy, {action} queued"; sau `start` thành công tự
  gọi `_fetch_voices` để combo có ngay giọng VieNeu (không còn để "alloy" của OpenAI); kết quả `voices` cũng
  refresh nút Start/Stop; `_on_vieneu_error` ghi `logger.warning` để log app có dấu vết; `shutdown_vieneu_threads()`
  dùng chung cho `closeEvent` và lúc thoát app. `main_window.py` gọi launch action qua cùng hàng đợi của tab và
  chờ bằng `shutdown_vieneu_threads(11_000)` khi đóng.
- Test: `tests/test_vieneu/test_ui_thread.py` +2 (fake bridge): bấm tải giọng khi Start đang chạy → được xếp hàng,
  nút bật lại, combo nhận `fake-voice`; Start một mình cũng điền danh sách. Tái hiện với runtime thật qua
  offscreen: `check` → Start → tải giọng liên tiếp: 20 giọng trong 8.1 s, chọn "Minh Đức", trạng thái Ready.
- Validation: ruff pass, pyright 0/0, `tests/test_vieneu` + `test_startup_responsiveness` + `test_dubbing`
  **106 passed**; `test_ui` + `test_ui_thread` 23 passed. One-app build lại cùng tên với `--overwrite`.
- CI của `2d1f2c2`: job offline abort (exit 134, `Fatal Python error: Aborted`) tại
  `test_subtitle_thread.py::TestSubtitleThreadError::test_missing_file`, không liên quan thay đổi: helper
  `run_thread_with_timeout` thoát event loop ngay khi nhận signal `error` rồi thả `SubtitleThread` còn đang chạy,
  Qt `qFatal` "Destroyed while thread is still running" tùy thời điểm (local 6/6 pass, CI dính). Helper nay
  `thread.wait()` sau event loop.

## 2026-09-04 (Nhóm trung hạn: hợp nhất config GUI/CLI, credentials không qua os.environ)

### Nguyên nhân và thay đổi
- CLI và GUI giữ hai bộ cấu hình riêng (`config.toml` trong `user_config_dir` và `AppData/settings.json`)
  nên LLM key phải nhập hai lần. `build_config()` thêm lớp `load_gui_settings()` nằm dưới `config.toml`:
  chỉ mirror credentials/endpoint (key/base/model của dịch vụ LLM đang chọn trong GUI, Whisper API, DeepLX
  endpoint, TTS lồng tiếng; `local_ai` chuẩn hóa thành `local-ai`), bỏ qua giá trị rỗng, không đổi tên key.
  Thứ tự ưu tiên vẫn CLI > env > file > GUI > default; `config path` in thêm file GUI đang làm fallback.
  Test CLI nay cô lập `CONFIG_FILE`, `settings.json` và biến `OPENAI_*`/`VIDEOCAPTIONER_*` của máy dev.
- 10 điểm ghi `OPENAI_API_KEY`/`OPENAI_BASE_URL` (và `DEEPLX_ENDPOINT`) vào `os.environ` làm key rò sang
  mọi child process. `get_llm_client()` nay nhận `LLMCredentials` (dataclass frozen, key ẩn khỏi repr,
  base URL chuẩn hóa) hoặc dùng bộ đã đăng ký qua `configure_llm_client()`; env `OPENAI_*` chỉ còn là
  fallback đọc. CLI subtitle, dubbing orchestrator, `SubtitleThread`/`RetranslateThread` đăng ký object;
  CLI transcribe bỏ hẳn vì Whisper API đã nhận key qua `TranscribeConfig`; DeepLX endpoint đi qua
  `TranslatorFactory.create_translator(deeplx_endpoint=...)`.
- Thêm `child_environment()` trong `subprocess_helper`: copy `os.environ` bỏ prefix `OPENAI_`/
  `VIDEOCAPTIONER_` (không phân biệt hoa thường), giữ PATH đã prepend ffmpeg/whisper/deno. Áp cho 44 call
  site `subprocess.run/Popen` trong `videocaptioner/` (ffmpeg/ffprobe, faster-whisper, whisper.cpp, yt-dlp,
  editor render, 7z/tar, updater, explorer/open), default của `run_process_with_stream_reader` và
  `_environment()` của sidecar VieNeu (token session đặt sau khi lọc).

### Validation
- Test CLI **70 passed** (10 test GUI fallback, regression key không vào env). Mới: `test_llm/test_client.py`
  (8), `test_utils/test_subprocess_helper.py` (5, gồm child process Python thật qua `env=` và qua
  `run_process_with_stream_reader`), test VieNeu `_environment`. Bộ offline test_llm/test_utils/test_cli/
  test_translate/test_subtitle/test_dubbing/test_thread/test_editor/test_ui: **227 passed, 12 skipped,
  9 errors**; 9 error là fixture `silent_video` của `test_natural_dubbing_integration` gọi ffmpeg không có
  trên PATH máy này. Ruff `videocaptioner/`: pass. Pyright `cli/` + 10 module đã sửa: **0 errors**.
- Chưa nghiệm thu: ffmpeg/whisper/yt-dlp thật với `env=child_environment()` (máy không có FFmpeg), sidecar
  VieNeu thật, và gọi LLM thật qua `LLMCredentials`.

### Test cho core/utils (mục 3)
- `tests/test_utils/` trước chỉ có 5 test layout PyInstaller. Thêm `conftest.py` với fixture `ffmpeg`
  (skip khi `shutil.which` không thấy hoặc binary không chạy được `-version`, ví dụ file ngoại lai trên
  PATH gây WinError 216) và `silent_video` sinh clip 1 giây bằng lavfi.
- `test_video_utils.py`: `plan_video_chunks`, `temporary_subtitle_file`, parser banner `ffmpeg -i` (video
  + nhiều audio stream có tag ngôn ngữ, audio-only, không stream, lỗi subprocess), `video2audio`,
  `check_cuda_available`, `add_subtitles` soft/hard (progress từ `time=` giả, lỗi return code) qua module
  `subprocess` giả ghi lại lệnh và kiểm `env=` đã lọc key; 4 test chạy FFmpeg thật (skip ở máy này).
- `test_installer.py`: tra cứu managed dir > PATH, `_prepend_to_path` idempotent, `_validate_archive`,
  giải nén ffmpeg zip chỉ lấy file trong `bin/`, `ensure_ffmpeg`/`ensure_deno` với `_download` giả và
  không network. Fixture khôi phục PATH vì `ensure_*` prepend thư mục tmp, nếu không `ffmpeg.exe` giả rò
  sang test sau.
- `test_platform_utils.py` mở rộng: predicate hệ điều hành, `get_subprocess_kwargs`, lọc FasterWhisper
  trên macOS, `open_folder/open_file/reveal_in_explorer` với Popen giả (đúng launcher, env đã lọc,
  `os.startfile` ưu tiên trên Windows). `test_subprocess_helper.py` thêm `StreamReader` và
  `run_process_with_stream_reader` với child Python thật (hai stream, override `env`).
- Validation: `tests/test_utils` **71 passed, 4 skipped** (4 skip là nhóm FFmpeg thật). Ruff pass.

### Pyright toàn package và gate CI (mục 4)
- Khảo sát bằng `pyright --outputjson` trên 170 file: chỉ còn **10 lỗi** ngoài `cli/` (8 ở
  `ui/view/dubbing_interface.py` do `Qt.Horizontal`/`Qt.AlignCenter` không có trong stub PyQt5, 2
  `reportReturnType` ở `core/translate/base.py` và `llm_translator.py`) cùng 21 warning.
- Sửa: dùng enum có scope `Qt.Orientation.Horizontal`/`Qt.AlignmentFlag.AlignCenter` (bằng nhau ở
  runtime PyQt5 5.15, không cần `type: ignore`); `_safe_translate_chunk` cast kết quả cache về
  `Optional[List[SubtitleProcessData]]`, `_agent_loop` cast dict đã validate; `_parallel_translate` raise
  rõ khi executor đã shutdown thay vì đưa `None` vào `submit_with_context`. Dọn 12 warning biến không dùng
  và `title` có thể `None` trong `video_download_thread`; 9 warning còn lại là stub yt-dlp `_Params`,
  `output_path`/`task_type` Optional trong pipeline/batch UI, để lại vì cần đổi logic.
- Gate CI `.github/workflows/ci.yml` đổi từ `pyright videocaptioner/cli/` sang `pyright videocaptioner/`;
  AGENTS.md, CLAUDE.md và README cập nhật lệnh gate.
- Validation: pyright `videocaptioner/` **0 errors, 9 warnings**. Ruff pass. Test translate/subtitle/
  thread/ui/dubbing engine: pass; 20 fail trong `tests/test_asr/test_chunk*` là pydub gọi ffmpeg không có
  trên máy (đã ghi từ đợt trước), không liên quan thay đổi này.

### Tách logic khỏi view lớn: subtitle_interface và dubbing_interface (mục 5, đợt 1)
- `core/subtitle/editing.py` (không import Qt) nhận toàn bộ thao tác trên dict phụ đề dạng
  `ASRData.to_json()`: `merge_rows`, `delete_rows`, `select_rows`, `replace_text`, `playback_range`,
  `find_supported_subtitle`, `export_subtitle`, `pipeline_reexport_targets`/`reexport_pipeline_outputs`,
  `task_folder`, `write_editor_handoff`. `SubtitleInterface` giữ nguyên `SubtitleTableModel`, chỉ gọi vào
  các hàm này; thêm `_selected_rows()` dùng chung cho menu chuột phải và phím tắt.
- Hành vi đổi có chủ đích: gộp hàng khi chọn cách quãng (Ctrl+click) nay gộp cả các hàng nằm giữa; code cũ
  âm thầm xóa những hàng không được chọn trong khoảng đó.
- `core/dubbing/presets.py` gom bảng provider (thứ tự combo, voice gợi ý, API base/model mặc định), key
  mix mode/text source/timing/unresolved, sample rate, `provider_from_key` (nhận cả `local_ai`/`local-ai`),
  `mix_mode_from_key`, `fill_provider_defaults` (chỉ điền ô trống), `merged_output_path`.
  `DubbingInterface` và CLI `dub.py` dùng chung, bỏ hai bản map trùng.
- Test: `tests/test_subtitle/test_editing.py` (20), `tests/test_dubbing/test_presets.py` (6),
  `tests/test_ui/test_subtitle_interface.py` (4, view offscreen: load, merge, delete, click hàng phát
  trước cue end 50 ms). Dubbing view kiểm offscreen: đổi provider điền preset, giữ voice đã gõ, ẩn/hiện
  khối VieNeu, `_save_settings` lưu đúng key.
- Fixture autouse mới ở root conftest trỏ `cfg.file` sang tmp: trước đó dựng `DubbingInterface` trong test
  (`test_vieneu/test_ui_thread.py`) và smoke thủ công ghi thẳng vào `AppData/settings.json` của máy dev;
  trong phiên này smoke đã ghi đè TTSApiBase/TTSModel/Voice và được trả về mặc định (`alloy`,
  `https://api.openai.com/v1`, `tts-1`), TTSProvider hiện là `vieneu-local` do test cũ đặt.
- Còn lại của mục 5: `subtitle_style_interface.py` (1281 dòng), `setting_interface.py` (1120),
  `video_editor_interface.py` (1117) chưa tách; `subtitle_interface.py` còn ~1000 dòng chủ yếu là dựng
  layout.
- Validation: ruff pass; pyright `videocaptioner/` 0 errors; test_ui + test_vieneu UI thread + test_cli +
  editing + presets: **pass**, hash `settings.json` không đổi sau khi chạy.

### Comment/docstring tiếng Trung sang English trong file đã chạm (mục 6, đợt 1)
- 198 comment và docstring CJK trong 10 file đã sửa logic ở đợt này được dịch sang English:
  `core/utils/subprocess_helper.py`, `platform_utils.py`, `video_utils.py`, `ui/thread/subtitle_thread.py`,
  `core/translate/base.py`, `llm_translator.py`, `deeplx_translator.py`, `factory.py`,
  `core/llm/client.py`, `ui/view/subtitle_interface.py`. Chuỗi `self.tr(...)` và message log giữ nguyên
  vì là key bản dịch/UI. Cách làm: tokenize để liệt kê đúng COMMENT/docstring có CJK, thay theo
  (file, dòng, nội dung) nên không đụng string literal.
- Còn lại theo thống kê `tokenize`: ~160 mục trong `faster_whisper.py`, `rounded_renderer.py`,
  `ass_renderer.py`, `video_download_thread.py`, `file_download_thread.py`, `whisper_cpp.py`; các file
  chưa chạm khác chưa đếm.
- Validation: ruff pass, pyright 0 errors, test translate/subtitle/utils/ui/llm/cli **210 passed**.

### CI: job offline fail từ run đầu tiên vì thiếu libpulse cho QtMultimedia
- Sau khi push 7 commit lên `origin/master`, job "Lint, type check, CLI tests" pass (gate
  `pyright videocaptioner/` xanh trên Linux) nhưng "Offline test suite" fail với pytest exit code 2, giống
  run của `a893800` trước đó. Log job cần đăng nhập nên không đọc được từ máy dev; soi wheel
  `PyQt5_Qt5-5.15.2 manylinux2014` cho thấy `libQt5Multimedia.so.5` cần `libpulse.so.0` và
  `libpulse-mainloop-glib.so.0`, trong khi job chỉ cài libGL/xkb/dbus. Hai file `tests/test_editor/`
  import `PyQt5.QtMultimedia` nên collection fail.
- Sửa `.github/workflows/ci.yml`: cài thêm `libpulse0 libpulse-mainloop-glib0` và gstreamer
  (base/good/libav) cho backend playback; giữ log pytest qua `tee` và thêm bước `Annotate failures` phát
  dòng `FAILED/ERROR` thành annotation `::error` để API public đọc được nguyên nhân mà không cần token.
- Run `0051b2b` sau khi cài libpulse chạy hết bộ test trên Ubuntu: **576 passed, 3 failed** — annotation
  chỉ đúng ba test đặc thù Linux: `validate_relative_reference` không chặn `C:/...` trên POSIX (nay kiểm
  cả `PurePosixPath`/`PureWindowsPath`), test locator so sánh `sys.executable` chưa resolve (trên Linux
  `.venv/bin/python` là symlink), và test `get_subprocess_kwargs` mới thêm giả định có `CREATE_NO_WINDOW`.
  Sửa ở `9fca48a`.
- Run `9fca48a` abort SIGABRT (exit 134) không có tóm tắt pytest: test playback QtMultimedia dùng backend
  gstreamer trên runner không có sink. `555e406` skip test đó khi `QT_QPA_PLATFORM=offscreen` và bước
  annotate in thêm 10 dòng cuối log + dòng faulthandler. Run `555e406`: **cả hai job pass**, CI trên
  `master` xanh lần đầu kể từ khi thêm workflow.
- Test layout editor (`test_editor_layout_remains_usable_at_700_pixel_page_width`) pass trên Ubuntu
  offscreen; chỉ fail khi chạy offscreen trên máy Windows dev (preview 306 px < 320), pass ở platform
  native. Chưa sửa.

### Tài liệu kiến trúc, gộp snapshot cũ, đồng bộ AGENTS/CLAUDE (mục 7)
- `docs/dev/architecture.md` viết lại theo hiện trạng (tiếng Việt như các dev doc mới): sơ đồ CLI/core/GUI,
  cấu trúc thư mục, chế độ đường dẫn, lớp cấu hình, pipeline phụ đề, LLM client, dubbing, VieNeu Local,
  Video Editor, subprocess env, đóng gói và gate. `docs/en/dev/architecture.md` (trước đây rỗng) có bản
  tiếng Anh tương đương; sidebar VitePress đã trỏ sẵn tới hai đường dẫn này.
- `docs/TRANG_THAI_DU_AN.md` (snapshot 2026-05-01) được rút gọn thành mục "Lịch sử cũ" ở cuối
  `status.md` rồi xóa; `docs/README.md` trỏ sang architecture thay cho link cũ.
- `AGENTS.md` và `CLAUDE.md` hợp nhất: cùng nội dung, chỉ khác mục "Đặc thù Claude Code". Sửa claim sai
  rằng `CLAUDE.md` bị gitignore (file được track, chỉ `.claude/` bị ignore), bỏ tham chiếu tới snapshot
  đã xóa, guard Bing ghi đúng là "từng hỏng, chưa đo lại", bổ sung cấu trúc `core/editor`, `core/tts/vieneu`,
  `core/llm`, `installer/`, quy tắc test không ghi vào `AppData/settings.json`, ghi chú môi trường
  (basetemp ngắn, FFmpeg thiếu) và bài học mojibake khi patch file qua stdin trên Windows.

## 2026-09-04 (Nhóm sửa ngắn hạn: CI, test hermetic, timeout, auto-update onedir, LLM log race)

### Nguyên nhân và thay đổi
- Trước đây chỉ `publish-pypi.yml` chạy gate khi push tag. Thêm `.github/workflows/ci.yml` chạy trên
  push `master/main/dev` và mọi PR: ruff, pyright `cli/`, translation sync, test CLI, và job riêng cho
  bộ offline `-m "not integration and not slow and not llm"` trên Ubuntu có FFmpeg + Qt offscreen.
- `tests/test_cli/test_dub.py` fail trên máy không có FFmpeg vì `dub.run` gọi `validate_ffmpeg()` trước
  mọi mock. Thêm `tests/test_cli/conftest.py` autouse patch validator này.
- `test_daily_logs::test_log_interface_loads_only_selected_day` chỉ đúng vào ngày 2026-08-21 vì
  `available_llm_log_days` luôn chèn hôm nay; nay pin `local_day`. Cùng test giữ `QApplication` trong
  biến cục bộ nên bị GC sau khi pass và kéo `qconfig` của qfluentwidgets chết theo, làm mọi test Qt chạy
  sau báo `wrapped C/C++ object ... has been deleted`; nay giữ tham chiếu ở module.
- 14 lời gọi `requests` ở Bcut, JianYing và tải phụ đề YouTube không có timeout nên worker có thể treo
  vô hạn. Thêm `REQUEST_TIMEOUT = (10, 120)` cho hai ASR và `timeout=30` cho phụ đề; kiểm bằng AST:
  không còn `requests.*` nào thiếu timeout trong `videocaptioner/`.
- `UpdateDialog.__onYesButtonClicked` bị name-mangling theo lớp cha nên nút "Cập nhật ngay" thực tế
  chỉ đóng dialog; nay override `validate()` và giữ dialog mở. `_apply_update` copy exe đè
  `sys.executable` sẽ làm hỏng bản onedir; thêm `is_onedir_frozen_build()` trong `platform_utils`,
  với onedir chỉ giữ file đã tải, hướng dẫn chạy thủ công và nút mở thư mục. Bỏ `shell=True`, chạy
  `cmd /c` với list args.
- `request_logger` dùng dict toàn cục không lock và ghép response với entry "completed đầu tiên", nên
  log request/response lẫn giữa các thread translator; entry lỗi không bao giờ bị xóa. Nay ghép qua
  `ContextVar` một slot theo thread/context; thêm test 4 thread song song và retry.

### Validation
- Targeted `test_cli` + `test_llm` + `test_utils` + `test_ui`: **85 passed**. Ruff `videocaptioner/`
  và test mới: pass. Pyright `cli/` và 5 module đã sửa: **0 errors, 0 warnings** (6 warning sẵn có của
  `video_download_thread.py` không đổi). Translation sync: pass.
- Full offline cùng filter CI: **416 passed, 17 skipped, 21 failed, 9 errors**. Toàn bộ fail/error là
  môi trường máy này: FFmpeg không có trên PATH (pydub trong `test_asr/test_chunk*`, fixture của
  `test_natural_dubbing_integration`) và `test_one_app_builder` vượt MAX_PATH khi basetemp dài; chạy
  lại với basetemp ngắn: pass.
- Chưa nghiệm thu: workflow CI chưa chạy thật trên GitHub (job `offline-tests` trên Linux chưa được
  kiểm chứng), UpdateDialog chưa click-through trên EXE thật, Bcut/JianYing chưa gọi thật sau khi thêm
  timeout.

## 2026-08-22 (Nghiệm thu Video Editor trên EXE và sửa lỗi phát hiện khi chạy thật)

### Nguyên nhân và thay đổi
- `Thoát xem trước` làm hỏng playback: `setMedia` rồi `setPosition` ngay lập tức nên backend Windows
  báo `QtMultimedia playback failed` và `QVideoWidget` rơi về surface trắng. Nay seek được hoãn tới
  `LoadedMedia`, position tạm thời trong lúc chờ bị bỏ qua, và poster được hiện lại thay cho surface rỗng.
- Danh sách layer rỗng render trắng vì app stylesheet của QFluentWidgets thắng selector cũ. Dùng ID
  selector `QListWidget#EditorLayerList` cộng palette `Base`; không dùng viewport translucent vì nó để
  lộ nội dung tab bên cạnh.
- Status bar kẹt ở `Loading editor media...` sau khi worker xong; nay khôi phục thành số cue đã tải khi
  không còn media request nào đang chạy.
- Bổ sung 22 chuỗi dịch Việt còn thiếu của editor (`TTS text`, placeholder preview, các thông báo
  render/lưu/xuất và tiêu đề hộp thoại).

### Validation và artifact
- Editor suite: **54 passed** (thêm regression cho exit-preview deferred seek và status label). Ruff
  `videocaptioner/`: pass. Pyright module editor: **0 errors, 0 warnings**. Translation sync: pass.
- PyInstaller 6.22.2 exit 0 với `--workpath` riêng: `build/VideoCaptioner/` cũ thuộc account sandbox
  `CodexSandboxOffline` nên `--clean` không xóa được (WinError 5); đây là ACL của máy, không phải lỗi spec.
- Artifact cuối `dist/VideoCaptioner-EditorLayers-20260822c/`: 585 file / 236.713.006 bytes; EXE
  **30.921.908 bytes**, SHA-256
  `BA400A39D2C82DF3D9410669D4EFBF1687DEA5CAFC1EA96F570AF67DE27537B6`, `NotSigned`. Warning file 614
  dòng, 0 match module editor. `resource/fonts` có trong bundle nên `drawtext` dùng đúng font đã ghim.
  Ba lần build vì hai lỗi chỉ lộ ra khi chạy thật; bản `-20260822` và `-20260822b` là bước trung gian.
- Chạy thật trên EXE (click-through + screenshot từng bước): mở video 12 giây + SRT tiếng Việt qua hộp
  thoại thật, V1 có thumbnail, A1 có waveform, TS1 có 3 cue, thêm layer Văn bản và Mặt nạ, `Xem trước
  nhanh` render và phát với playhead giữ đúng `00:05.023 / 00:12.000` theo timeline dự án, `Thoát xem
  trước` trả về video gốc đúng vị trí và không còn báo lỗi.
- Chưa nghiệm thu: export video đầy đủ, dubbing với provider thật, và các codec ngoài H.264/AAC.

## 2026-08-22 (Video Editor: sửa lỗi visual layer, preview và render)

### Nguyên nhân và thay đổi
- Fast Preview trước đây `setMedia` clip đã render vào chính player, nên vị trí local của clip bị ghi
  thẳng vào `playhead_ms`: playhead nhảy về đầu range, inspector tự chọn nhầm cue và không có đường về
  video gốc. Preview nay chạy ở mode riêng có offset, cộng lại về timeline project, kèm action
  `Exit preview`.
- Mở `.vceditor.json` không gán `project_path` nên Ctrl+S luôn hỏi lại chỗ lưu; nay giữ đúng file đã mở.
- `_refresh_layer_list()` clear list ở mỗi command nên selection về -1 và nút Chỉnh sửa/Xóa im lặng
  không làm gì. Selection nay theo layer id và list được rebuild có block signal.
- Thumbnail đến muộn gọi `set_poster` vô điều kiện, ẩn `QVideoWidget` giữa lúc đang phát. Poster nay chỉ
  áp khi playback chưa bắt đầu.
- Không có cảnh báo mất dữ liệu: `is_dirty` có trong model nhưng UI không đọc. Mở project khác nay hỏi
  trước khi bỏ thay đổi.
- Render không hủy được và `closeEvent` không chạy cho navigation page. `_run` đổi sang `Popen` + poll
  cancel, kill FFmpeg child; có action `Cancel render`, và page dừng worker qua `aboutToQuit`.
- `AppData/cache/editor_preview/` không bao giờ được dọn; nay xóa bản render cũ trước mỗi lần preview.
- Asset khác ổ đĩa (logo, WAV cache) làm hỏng toàn bộ `save()`; path vệ tinh nay fallback absolute, còn
  video/subtitle vẫn bắt buộc relative.
- Visual layer chỉ chỉnh được một thuộc tính qua `QInputDialog` và không đổi được vị trí/kích thước.
  Thêm `LayerInspector` (geometry, timing, opacity, visible/lock, property theo kind) trong cùng tab
  `Layers` với nút add và danh sách; layer chọn/kéo/resize được trên track FX1; track header có nút V
  cho TS1 và FX1.
- Parity preview/export: `drawtext` ghim `fontfile` từ `resource/fonts/` và canh giữa trong box layer,
  logo scale theo frame width thật lấy từ probe, opacity áp cho blur/mask qua `colorchannelmixer`, box
  clamp trong khung, overlay preview dùng rect video đã letterbox và scale font theo tỉ lệ video/widget.
- `boxblur` radius clamp theo `min(w,h)/4 - 1`: giới hạn thật đến từ plane chroma 4:2:0, và render thật
  đã bắt được lỗi `Invalid chroma_param radius value 35` mà assert chuỗi không thấy.

### Validation và artifact
- Editor suite: **52 passed** (thêm `tests/test_editor/test_visual_layers.py`, 17 test). Dubbing +
  thread suite: **69 passed, 2 skipped**. Ruff `videocaptioner/`: pass. Pyright bốn module editor:
  **0 errors, 0 warnings**. Translation sync: pass.
- Có render FFmpeg thật cho blur translucent + text tiếng Việt, và test hủy `_run` bằng FFmpeg đang chạy.
- Kiểm tra layout bằng ảnh render offscreen của page: hai tab vừa khung 1050 px, không còn ô nhập bị cắt.
- Chưa build EXE, chưa click-through GUI thủ công và chưa nghiệm thu video/provider thật cho các thay đổi
  này.

## 2026-08-22 (VieNeu base-build guard và khôi phục one-app onedir)

### Nguyên nhân và thay đổi
- Ảnh lỗi `runtime manifest is unavailable` đến từ việc chạy base onedir ~236 MB; build này không có
  `runtime/vieneu/python.exe`, bridge, runtime manifest hoặc model seed. Lỗi `no active model` là hệ quả.
- Base build nay không tự chạy VieNeu auto-update, không cho lặp action/thread khi runtime vắng, disable
  Start/Update/Fetch và hiển thị hướng dẫn dùng VieNeu One-App thay vì spam InfoBar có đường dẫn lỗi.
- `build_vieneu_one_app.py` trước đó vẫn giả định PyInstaller onefile rồi xóa nhầm output onedir mới tạo.
  Builder nay chạy PyInstaller bằng Python environment hiện tại, giữ toàn bộ `_internal`, ghép runtime +
  model seed vào đúng thư mục onedir và chỉ replace managed VieNeu data khi có `--overwrite`.
- Thêm regression cho base build thiếu runtime và builder augment onedir; đồng bộ bản dịch Việt.

### Validation và artifact
- VieNeu suite: **26 passed**. Startup/UI regression: **10 passed**. Ruff phạm vi source/scripts/tests:
  pass. Pyright service/main-window/builder: **0 errors, 0 warnings**. Translation sync: pass.
- Sáu MSI/CAB input đều khớp SHA-256 ledger. Admin-extract đích dài fail/rollback do MAX_PATH; đích ngắn
  `build/v22` hoàn tất với MSI status 0: runtime **29.245 file / 5.906.443.598 bytes**, model seed
  **42 file / 1.765.957.812 bytes** và active revision `2da0efab622a1722125991736524f080b751ef5b`.
- Exact EXE `vieneu status` exit 0; `vieneu update` exit 0 và báo `current`. Exact packaged Natural Dubbing
  cold-start PyTorch/CUDA, load 20 voices, tạo video 4 giây H.264/AAC mono 48 kHz và exit 0; zero process.
- Computer Use lần đầu phát hiện thêm ACL sandbox làm GUI auto-update gặp WinError 5. Chỉ `AppData` của
  artifact được cấp Modify cho user `Lap-4090`; atomic state replace nay có đúng quyền. Không dùng lại
  Computer Use sau khi binding nhầm sang Codex; hậu-ACL được kiểm bằng ACE/state và test, không gọi là
  visual acceptance lần hai.
- Artifact sạch: `dist/VideoCaptioner-VieNeu-Fixed-20260822/`, **29.853 file / 7.908.872.539 bytes**;
  EXE **30.899.994 bytes**, SHA-256
  `06FC34FA34931E65986EA5B21DBB1D916F120501167788C44276A90E3247DC44`, `NotSigned`. Runtime/model khớp
  distribution manifest; không còn cache/log/work-dir test. Artifact chưa deploy, commit hoặc push.

## 2026-08-21 (Cài đặt và màn tải model không còn nền trắng)

### Đã sửa
- `SettingInterface` nay áp transparent-background contract cho cả `ScrollArea`, native viewport và
  content widget. Dark theme không còn render viewport Windows màu `#efefef` che gần hết chữ/card.
- Hai trang cấu hình FasterWhisper/WhisperCpp cũng đánh dấu native viewport và container là translucent,
  tránh model settings/download flow rơi về palette sáng trên Windows.
- Khi chọn FasterWhisper trong Cài đặt, một card `Quản lý mô hình` hiện ngay bên dưới và mở trực tiếp
  `FasterWhisperDownloadDialog`; dialog vẫn được import lazy. Chọn lại provider đang active không còn là
  ngõ cụt UX vì user có action riêng để tải chương trình/model.
- Thêm regression offscreen cho pixel nền Cài đặt, thuộc tính transparent của cả hai model page, click
  Qt thật từ card mới tới callback mở manager và cả hai nút tải chương trình/model trong dialog.

### Validation và artifact
- Startup/UI targeted: **10 passed**. Ruff các file sửa: pass. Pyright ba module UI: **0 errors, 0
  warnings**. Pixel probe Cài đặt đổi từ `#efefef` sang `#202020` tại toàn bộ điểm nền đã đo.
- PyInstaller 6.22.2 exit 0: `dist/VideoCaptioner-FasterWhisperClickFix-20260821/`, 565 file /
  236,468,546 bytes; EXE **30,898,675 bytes**, SHA-256
  `C89176C89693BA69221EA64FA788644A1F90FE8281445F35A9268FEB70DA4D5D`, `NotSigned`. Warning file
  614 dòng optional/transitive và 0 match ba module sửa.
- Computer Use mở đúng EXE mới và click xuyên suốt Cài đặt → FasterWhisper → Quản lý mô hình → dialog
  tải; toàn bộ flow nhận click và giữ dark surface. Không bắt đầu download thật; đã đóng đúng bản test và
  xác nhận zero process. Artifact chưa được deploy đè lên bản user.

## 2026-08-21 (Video Editor dark UI và visual acceptance)

### Đã sửa
- Sửa nguyên nhân page trắng: `QVideoWidget`, `QTabWidget`, `QScrollArea` và spinbox Qt chuẩn trước đó
  fallback về Windows light palette dù navigation QFluent đang dark. Editor giờ có local dark surfaces
  cho command bar, preview, inspector, splitter, timeline shell, layer list, status/progress và scrollbar.
- Empty state ẩn native video surface trắng và hiện dark placeholder. Loaded state dùng thumbnail đầu làm
  poster trước khi Play; khi bắt đầu playback mới đưa `QVideoWidget` lên để giữ QtMultimedia behavior.
- Thay command bar bọc trong `QScrollArea` (làm width không co và action chồng chữ) bằng responsive shell.
  Chỉ giữ Open/Save/Undo/Redo/Fast Preview/Export trên hàng chính; Save as ASS và visual layers vào More.
- Page đặt window title `Video Editor`; dark hierarchy giữ nguyên tại page width 700 px, không thay engine,
  project schema, timeline model hoặc worker boundary.

### Validation đã đo
- Computer Use chụp ba trạng thái thật: packaged-before có preview/inspector trắng; source empty-state sau
  patch; source loaded-state với video poster, V1 thumbnails, A1 waveform, 5 TS1 cues và inspector; exact
  packaged-after không còn white surface hay toolbar overlap.
- Editor suite: **25 passed, 0 failed**. Ruff toàn `videocaptioner/`: pass. Targeted Pyright editor:
  **0 errors, 0 warnings**. Translation sync: pass.
- PyInstaller 6.22.2 exit 0: EXE **119,560,723 bytes**, SHA-256
  `7F9FBC771E8D41E9E71D31B64D27F6CA49EA40A538491B7155664B4D7399DD08`, 614 warning lines và
  0 editor-warning match, `NotSigned`.
- Web bundle/base bump `1.2.0`; setup SHA-256
  `FFA45AE9072BF692C71786ECB934D4702D2DD6C08D91008426C748D5C53D8F04`. Upgrade apply `0x0`;
  VieNeu runtime detect `Present / execute None`, không tải lại payload. Installed EXE hash khớp build và
  settings hash trước/sau upgrade byte-identical.

## 2026-08-21 (Thin web installer VieNeu)

### Đã triển khai
- Tách distribution thành base MSI chỉ chứa EXE và remote VieNeu MSI chứa runtime GPU + model seed.
  WiX Burn `VideoCaptioner Web Setup` nhúng base nhưng lấy runtime MSI + 5 CAB qua `DownloadUrl`; Burn tự
  tính/kiểm SHA-256 cho từng payload trước khi apply.
- Web setup `1.1.0` dùng cùng base UpgradeCode với offline MSI `1.0.0`, nên đường migration là Windows
  Installer major upgrade thay vì xóa/ghi đè file thô. Runtime là package riêng để bundle uninstall theo
  thứ tự ngược và không trùng component ownership với base.
- Source mới: `installer/VideoCaptioner-Base.wxs`, `VideoCaptioner-VieNeu-Runtime.wxs` và
  `VideoCaptioner-Web-Bundle.wxs`. `PayloadBaseUrl` là build variable; build test hiện trỏ loopback
  `http://127.0.0.1:8765`, cần đổi thành HTTPS CDN/object storage trước khi phát hành cho máy khác.

### Validation đã đo
- Setup EXE **119,974,725 bytes** (114.42 MiB), nhỏ hơn bộ offline nén khoảng 3.8 GiB. Base MSI nhúng
  **118,919,168 bytes**; remote payload gồm runtime MSI + 5 CAB.
- Đã xóa các payload copy cạnh setup để buộc remote path. Burn log xác nhận HTTP `HEAD/GET`,
  `download from http://127.0.0.1:8765/...` và `Verified acquired payload` cho runtime MSI + đủ 5 CAB.
- Quiet install pass: base apply `0x0`, runtime apply `0x0`, bundle apply/cleanup `0x0`. Installed EXE
  SHA-256 `2CEC54842FD78FE34407C97E5E235DC632EAC5318B735140ACD29263D9CCBCCD`; runtime
  `vieneu-3.3.0-bridge-1.0.0`, active model
  `2da0efab622a1722125991736524f080b751ef5b`, `torch_cuda.dll` tồn tại và đúng một shortcut.
- Runtime Burn cache dùng `Cache=remove` và đã được dọn sau install. Bản offline `1.0.0` user cài trước
  đó được gỡ qua registered ProductCode với removal status 0 trước khi nghiệm thu web setup.

## 2026-08-21 (VieNeu Local one-app V0-V5)

### Đã triển khai
- Thêm provider `VieNeu Local` riêng, giữ nguyên generic `Local AI`. GUI/manual/full/batch/editor và CLI
  cùng dùng một managed service; app tự điền loopback endpoint, session token, model và sample rate.
- Thêm domain Qt-independent `core/tts/vieneu`: protocol/state schema có version, locator không hardcode
  checkout developer, hidden sidecar ownership, health identity/auth, timeout/retry/cancel, job lease pin
  revision, graceful/forced owned-tree shutdown và cache/report identity đã sanitize.
- Ship bridge FastAPI/OpenAI-compatible riêng trong runtime, bind `127.0.0.1`, không import CUDA/VieNeu vào
  Qt, không log transcript/token; health báo runtime/backend/revision/48 kHz và scheduler batch an toàn.
- Thêm updater theo Hugging Face commit SHA: resumable full snapshot, atomic state, pinned tokenizer/codec,
  health + voices + WAV validation, deferred activation khi busy, rejected record, offline reuse và rollback.
- GUI có status/start-stop/check-update/rollback/model folder/auto-update qua QThread. CLI có
  `vieneu status|update|rollback` và `--tts-provider vieneu-local`; EXE windowed attach stdout/stderr vào
  console/redirected pipe khi chạy CLI nhưng không mở console ở GUI mode.
- Runtime build dùng uv-managed Python 3.12, pinned VieNeu source commit
  `36c4b501b0634a8f59805e6b529a058fbd30190b`, hash-locked dependencies và notices/license. Builder bỏ
  đúng static development `torch/lib/dnnl.lib`; `torch_cuda.dll` và inference runtime vẫn được giữ.

### Validation đã đo
- Full offline suite: **447 passed, 19 skipped, 0 failed** / 466 collected, 127.06 giây. VieNeu + CLI +
  dubbing regression cuối: **142 passed, 0 failed**. Ruff toàn `videocaptioner/` và các script VieNeu:
  pass; targeted Pyright: **0 errors, 0 warnings**; translation sync/parse và `git diff --check`: pass.
- Real RTX/CUDA: cold **7.7161 s**, warm **0.001295 s**, 20 voices, 4 concurrent WAV mono 48 kHz,
  dynamic batch observed, zero owned process sau shutdown. Clean pruned runtime chạy lại cold
  **13.8077 s**, warm **0.001596 s**, 2 concurrent và dynamic batch pass.
- Real update/rollback: activate `d0c7ea3951eaaca27bdcf53ff9fa9eaf8ed5893a`, update/activate
  `2da0efab622a1722125991736524f080b751ef5b`, offline rollback chạy TTS thật, rồi trả lại latest. Forced
  candidate `760c29661f7ae65c6a6e55abd9691d05613f82ec` bị reject; previous restart, snapshot giữ lại, lỗi
  được sanitize và zero process.
- Exact packaged EXE CLI `vieneu status`: stdout JSON 1.310 byte, stderr rỗng, exit 0. Real packaged
  Natural Dubbing: exit 0, sidecar observed, video H.264/AAC **6.000 s**, mono **48 kHz**, zero EXE/sidecar.
  GUI smoke có parent + child sống sau 15 giây, không eager-start sidecar, log không có startup exception;
  sau đóng còn zero process.

### Runtime, portable và installer
- Clean runtime: **5,906,443,598 bytes / 29,245 files**; lock SHA-256
  `079E23501EF943E355F411F18094992D1E9A25E7FEFD7022F37DA5DFAEF171AE`, VieNeu wheel SHA-256
  `8D4CE3EEB6B645EC1AD03CDCA4AA5BE81906896DE16D531E50AF7387234C8424`.
- Portable `dist/VideoCaptioner-VieNeu-OneApp-20260821/`: EXE **119,559,584 bytes**, SHA-256
  `2CEC54842FD78FE34407C97E5E235DC632EAC5318B735140ACD29263D9CCBCCD`; model seed
  **1,765,957,812 bytes / 42 files**, active latest + pinned MOSS dependency. Release tree được tái tạo
  sau acceptance và xác nhận không chứa cache/log/work-dir/acceptance data.
- WiX MSI entry point `dist/installer-wix6-release-final/VideoCaptioner-VieNeu-OneApp-20260821.msi`:
  **5,345,404 bytes**, SHA-256 `0E64C755A1345F139817163EA8AB47310B4A52CD59215D02239EF3B81E5515DD`,
  đi cùng 5 external CAB dưới giới hạn media và tạo đúng một Start Menu shortcut. MSI install status 0;
  installed EXE hash/model/runtime khớp, installed `vieneu status` exit 0; uninstall status 0, shortcut,
  registry, install dir và owned process đều về zero. EXE/MSI hiện `NotSigned`.

### Acceptance boundary
- Machine audio/container/content gates đã pass nhưng cảm nhận giọng tiếng Việt vẫn cần người nghe ký
  duyệt; artifact là `AppData/vieneu-final-packaged-output.mp4` (không nằm trong release package).
- Giant physically single self-extracting EXE không được hỗ trợ; distribution contract là một MSI entry
  point + external CAB payload, một shortcut/app, với sidecar nội bộ. Publication đi qua feature branch
  để không ghi trực tiếp thêm một payload lớn lên `master`.
## 2026-08-21 (Lazy tabs và Subtitle Style packaged closeout)

### Đã sửa
- `SegmentedWidget.clicked(bool)` trước đó đẩy `bool` vào tham số mặc định của lazy callback, làm mọi
  Home tab sau tab đầu ném `TypeError` và giữ nguyên nội dung Task Creation. Callback nay nhận riêng
  `_checked` và giữ đúng `route_key`.
- Subtitle Style gọi transparent-background contract của QFluentWidgets cho ScrollArea/viewport/widget,
  nên text dark-theme không còn trắng trên panel trắng.
- ASS preview đặt temp `.ass` dưới `AppData/cache` của app và quote/escape đúng đường dẫn FFmpeg filter
  có drive letter, khoảng trắng và dấu nháy; preview không còn fail `original_size` trên Windows.

### Validation
- Regression mới dùng click Qt thật, pixel render dark thật và FFmpeg thật: **8 passed**. Post-merge full
  suite với VieNeu + Video Editor + startup/UI: **453 passed, 23 skipped, 0 failed** / 476 collected,
  113.49 giây. Ruff pass; Pyright CLI + các module tích hợp: **0 errors, 0 warnings**; translation sync pass.
- Computer Use click trực tiếp trên EXE ở `E:\Game\Translate video`: Transcription, Optimize/Translate,
  Dubbing và Synthesis đều hiện đúng page riêng. Subtitle Style có panel dark và preview ASS hiển thị sau
  4 giây; app đóng sạch, zero window/process. Settings giữ nguyên SHA-256
  `DD880B4DFC002DAD90BB91B01E00E7B0E6D7FC868BE45B1ED29E78B320F97384`; log không có error mới sau
  các marker cũ lúc 16:25, preview mới 3,801,434 bytes lúc 16:42:45.

### Artifact cuối
- Onedir EXE **30,883,355 bytes**, 565 file / 236,449,303 bytes; SHA-256
  `23963B0B24D8E6FA8B578B62DD8204B22651DDD59BFB2C997D7118EAB28BEEEE`, `NotSigned`.
- MSI **95,940,948 bytes**, SHA-256
  `CFD055858C02BF99EB488A77A66B1B3CBC45ADD6E48ED0866D9BBF9D8DF4EC10`, `NotSigned`; filtered ICE
  validation exit 0 với ba warning ICE60 TTF app-private như trước.
- Deploy E dùng staged swap; backup runtime/EXE/settings timestamp `20260821-163844` được giữ nguyên.

## 2026-08-21 (Startup responsiveness và Transcription UI không còn khóa)

### Đã sửa
- Đổi PyInstaller mặc định từ `onefile` sang `onedir`; EXE được gắn `logo.png`, installer source nhận
  cả thư mục app và vẫn tạo một shortcut. Mỗi lần mở không còn giải nén hơn 100 MB vào `_MEI...`.
- `MainWindow` và các page Home/Batch/Subtitle Style/Video Editor/Logs/Settings được tạo lazy. Trong
  Home chỉ Task Creation được tạo ban đầu; Transcription/Subtitle/Dubbing/Synthesis chỉ load khi mở.
- `core.asr`, `core.translate` và `core.llm` giữ nguyên public API nhưng chuyển sang lazy exports.
  `yt_dlp` và ModelScope chỉ import trong worker khi thật sự tải video/model.
- Transcription không còn dựng cả ba provider setting widget lúc mở. Kiểm tra FasterWhisper chạy trong
  `QThread`; scan model/bin có giới hạn depth/entry, chịu lỗi permission và không còn tự xóa executable
  nhỏ/hỏng trong một phép kiểm tra trạng thái.

### Validation và số đo
- Fresh-process import `MainWindow`: khoảng **3.300 ms -> 422 ms**. Constructor: **1.618 ms -> 106 ms**.
  First frame + Home: **1.042 ms -> 217 ms**. Mở Transcription lần đầu: **920 ms -> 106 ms**.
- Startup/ASR/thread/CLI/translate targeted: **186 passed, 14 skipped**. Offline suite trong phạm vi sạch:
  **421 passed, 26 skipped, 1 deselected** / 448 collected, 90.94 giây. Ruff toàn source: pass; Pyright
  startup/Transcription: **0 errors, 0 warnings**; translation sync: pass.
- Sau khi merge `origin/master`, targeted VieNeu UI/CLI + lazy tabs + ASS preview đạt **12 passed**;
  full merged suite đạt **453 passed, 23 skipped, 0 failed** trước publication.

### Packaged artifact
- PyInstaller 6.22.2 exit 0:
  `dist/startup-fix/VideoCaptioner-StartupFix-20260821/VideoCaptioner-StartupFix-20260821.exe`,
  **30,883,014 bytes**; toàn onedir **565 file / 236,448,962 bytes (225.50 MiB)**; SHA-256
  `FE0235C18ED9A1BF33D30CE41280D4DD160025D9F5242C3999012F29B749BBEE`; `NotSigned`.
- Warning file 614 dòng optional/transitive, 0 match startup/Transcription/VieNeu. Cold start đầu sau build
  và Windows scan: **11.042 ms**; ba warm start: **863 / 828 / 905 ms**. Mỗi run đúng 1 process,
  `CloseMainWindow` exit 0, zero process còn lại và app log không có exception/error.
- WiX CLI **5.0.2** được cài project-local tại `.tools/wix`; Dotnet home, NuGet cache, temp và
  intermediate đều nằm dưới repo trên ổ F (`.tools` được gitignore, 19.48 MiB). WiX 7 không được dùng
  vì yêu cầu chấp nhận OSMF EULA; không có tool/app project nào được cài global hoặc vào ổ C.
- MSI onedir: `dist/startup-fix/VideoCaptioner-StartupFix-20260821.msi`, **95,936,852 bytes**, SHA-256
  `15B1F1DAD90154E896B4CCE939BEE851F3555509F8F13AACB2F73CE10EE59E19`, `NotSigned`. Decompile xác nhận
  565 File rows và một Start Menu shortcut trỏ đúng EXE. ICE validation còn lại pass sau khi suppress
  `ICE38/64/91` là ba rule WiX không tương thích với wildcard harvesting trong package per-user; chỉ còn
  3 warning ICE60 đã map tới ba TTF app-private. MSI không được chạy cài và registry product vẫn bằng 0.
- Portable onedir được deploy trực tiếp tới `E:\Game\Translate video` mà không chạy MSI; EXE cũ,
  `AppData` và `work-dir` được giữ nguyên. Settings đích giữ đúng SHA-256
  `DD880B4DFC002DAD90BB91B01E00E7B0E6D7FC868BE45B1ED29E78B320F97384` và có backup timestamp trước
  test. Smoke từ E: cold Windows scan **13.096 ms**, warm **1.008 ms**, đúng 1 process, exit 0, zero
  leftover, app log append 55 bytes và 0 error match.

## 2026-08-21 (Video Editor E0-E7)

### Đã triển khai
- Thêm tab `Video Editor` native PyQt5/QFluentWidgets ngay dưới `Kiểu phụ đề` và trên `Nhật ký yêu
  cầu`; page co được tới 700 px, command bar overflow vào More thay vì overlap.
- Thêm domain `editor-project-v1` với stable cue/layer IDs, milliseconds canonical, relative paths,
  atomic project + SRT save và ba trường riêng `source_text` / `display_text` / `tts_text`. Normal save
  không persist ASS; chỉ explicit `Save as ASS` tạo ASS.
- Preview QtMultimedia, inspector và timeline V1/A1/TS1 đồng bộ playhead/selection/overlay. Timeline có
  zoom/scroll/range, add/split/delete, drag/resize, track mute/lock và undo/redo; waveform/thumbnails chạy
  QThread, cache theo media fingerprint và bỏ kết quả stale.
- `Regenerate voice` dùng `DubbingEngine`, force-refresh đúng cache key của selected group, đo WAV và
  giữ nguyên cache/audio group khác. Fast Preview dùng WAV live đã regenerate; final export dùng cùng
  editor snapshot và Natural/Legacy config hiện có, không tạo report JSON mặc định.
- Blur/Logo/Mask/Text có core model, layer panel, timeline clip, preview, FFmpeg export, command undo,
  serialization và round-trip. Không thêm PySide6, MPV hay dependency mới.
- Thêm `Open in Video Editor` từ Subtitle và Dubbing workflow; cập nhật translation sources/fallback,
  README, tài liệu dev và plan. `VideoCaptioner.spec` không cần đổi vì đã collect toàn bộ submodule.

### Validation đã đo
- Editor targeted: **23 passed, 0 failed**. Dubbing/thread/CLI/subtitle/translate regression:
  **151 passed, 10 skipped, 0 failed**. Full offline suite cuối với AppData/cache cô lập:
  **419 passed, 23 skipped, 0 failed** / 442 collected, 107.01 giây.
- Real FFmpeg H.264/AAC + SRT/WAV fixtures pass Fast Preview 1.5 giây, live display/TTS routing,
  regenerated voice mix, Blur/Logo/Mask/Text render và final export giữ duration trong ±120 ms. Không
  có ASS ngoài explicit export.
- QtMultimedia H.264/AAC playback tiến được và seek 1.7 giây trong tolerance. Layout 700 px, stale-result
  discard, preview/inspector/timeline sync và worker isolation đều pass.
- Timeline 60 phút/1.000 cue tại viewport giữa chỉ paint **3 cue**; 100 paint = **21.958 ms**
  (**0.220 ms/frame**), 5.000 query = **1.801 ms** (**0.360 µs/query**).
- Ruff toàn `videocaptioner/`: pass. Pyright CLI + toàn bộ editor module: **0 errors, 0 warnings**.
  Translation JSON/TS parse và sync `--check`: pass.

### Packaged artifact
- PyInstaller 6.22.2 exit 0: `dist/VideoCaptioner-VideoEditor-20260821.exe`, **113,104,947 bytes**,
  timestamp `2026-08-21 04:08:23 +07:00`, SHA-256
  `23836F039A3C4E7CC2C2257352E2AC1A150901BFE8B8D707176A4BA486F119E7`, `NotSigned`.
- Warning file có 569 dòng optional/transitive; 0 match editor/QtMultimedia. Archive chứa QtMultimedia,
  toàn bộ `core.editor`, UI components, media/voice thread, interface và Vietnamese translation.
- Exact packaged smoke: parent PID 52244 + child PID 79816 sống sau 15 giây; daily log append 55 bytes,
  0 startup exception match; đã đóng đúng owned tree và xác nhận 0 process còn lại.

### Còn chờ user/provider thật
- Chưa nghiệm thu cảm nhận UX, codec/video thực tế đa dạng, chất lượng nghe tiếng Việt, provider TTS thật,
  rate-limit hoặc video thật dài. Machine acceptance không dùng API key/live provider.

## 2026-08-21 (Dubbing report in-memory và lỗi có nguyên nhân)

### Đã sửa
- GUI và full pipeline không còn tự ghi `<output>-dubbing-report.json`. `dubbing-report-v1` được giữ trong
  RAM để dialog hiển thị; CLI chỉ persist JSON khi user chủ động truyền `--report PATH`.
- Provider failure nêu số group, group ID và lỗi provider đã sanitize; API key/Bearer token bị redaction.
- Natural review nêu số group, group tệ nhất, audio duration, available duration và fit ratio, kèm hướng
  xử lý. GUI giữ lỗi trên status label và InfoBar sticky thay vì biến mất sau 5 giây.
- CLI exit 6/7 in nguyên nhân ra stderr; chỉ in report path khi report thực sự được yêu cầu.

### Validation và package
- Dubbing + TTS + CLI targeted: **139 passed**. Ruff: pass. CLI Pyright: **0 errors, 0 warnings**.
- PyInstaller exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`, SHA-256
  `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`, `NotSigned`.
- Packaged smoke: parent PID 21468 + child PID 34896 sống sau 15 giây; daily app log append 55 bytes,
  0 startup exception match; đã đóng đúng hai PID và xác nhận 0 process test còn lại.
- Không chạy lại full suite; full gate gần nhất vẫn **379 passed, 26 skipped, 0 failed**.

## 2026-08-21 (Chia log theo ngày)

### Đã sửa
- Application log ghi vào `AppData/logs/app-YYYY-MM-DD.log`; mỗi ngày vẫn size-rotate 10 MiB với tối đa
  5 backup trong ngày. Tất cả named logger dùng chung một handler để không tranh chấp rollover.
- LLM request log ghi vào `llm_requests-YYYY-MM-DD.jsonl`; quá 10 MiB sẽ giữ tối đa 2 backup trong ngày.
- Màn `Nhật ký yêu cầu` có bộ chọn ngày, chỉ nạp file của ngày đang xem và nút xóa chỉ xóa ngày đã chọn.
  `llm_requests.jsonl` / `.old` cũ vẫn xuất hiện dưới mục `Cũ`, nhưng writer không ghi thêm vào đó.
- `LogWindow` theo dõi file app-log của ngày hiện tại, tự chuyển ngày/rotation và chỉ đọc tail 20 KiB thay
  vì nạp toàn bộ file. Không tự xóa hoặc migrate log cũ của user.

### Validation và package
- Daily-log + context/UI tests: **15 passed**; riêng daily contract: **6 passed**.
- Ruff: pass. CLI Pyright: **0 errors, 0 warnings**. Translation sync/source validation: pass.
- PyInstaller exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`, SHA-256
  `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`, `NotSigned`.
- Packaged smoke tạo đúng `app-2026-08-21.log`; parent PID 21468 + child PID 34896 sống sau 15 giây,
  0 startup exception match; đã đóng đúng hai PID và xác nhận 0 process test còn lại.
- Không chạy lại full suite; full gate gần nhất vẫn **379 passed, 26 skipped, 0 failed**.

## 2026-08-21 (SRT-only pipeline, TTS boundary dedup và kế hoạch Video Editor)

### Đã sửa
- Full subtitle pipeline nay dùng output `【字幕】*.srt` và chỉ persist SRT cạnh video; không còn tự tạo
  `【样式字幕】*.ass` hoặc `<video>.ass`. Menu Save trong `SubtitleInterface` vẫn giữ lựa chọn ASS khi user
  chủ động cần export.
- Layout re-export chỉ cập nhật các SRT pipeline đã tạo, không tự ghi lại ASS cũ.
- Natural planner nay loại overlap 1-4 spoken token ở biên giữa các cue được merge, ví dụ
  `"... bạn" + "bạn khỏe ..."`. Chỉ `tts_text` thay đổi; `subtitle_text`/cue display giữ nguyên. Report
  ghi warning `Removed repeated TTS boundary overlap`. Một cue lặp hoàn toàn vẫn được giữ để không xóa
  lời lặp có chủ ý.
- Thêm kế hoạch tích hợp tab `Video Editor` dựa trên khảo sát read-only `F:\CppClone\CapCap`, port theo
  kiến trúc PyQt5/QFluentWidgets thay vì import trực tiếp PySide6.

### Validation
- Dubbing: **58 passed**. Thread: **10 passed, 2 skipped**. CLI: **58 passed**.
- Regression riêng output/dedup: **18 passed**. Ruff: pass. CLI Pyright: **0 errors, 0 warnings**.
- Không chạy lại full suite vì thay đổi hẹp; full gate gần nhất vẫn là **379 passed, 26 skipped, 0 failed**.
- PyInstaller exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`, SHA-256
  `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`, `NotSigned`.
- Packaged smoke: parent PID 21468 + child PID 34896 sống sau 15 giây; 0 startup exception match;
  đã đóng đúng hai PID và xác nhận 0 process test còn lại.

## 2026-08-21 (Natural Dubbing P-1 đến P8)

### Đã triển khai
- Tách `source_text`, `subtitle_text`, `tts_text`; `AUTO` ưu tiên bản dịch và full pipeline dùng artifact
  target-only riêng, không tái sử dụng SRT display song ngữ cho TTS.
- Thêm domain schema `dubbing-plan-v1` / `dubbing-report-v1`, deterministic grouping planner, dự đoán
  duration chỉ để routing và sức chứa timeline có borrowable silence + guard.
- Thêm persistent WAV cache `AppData/cache/dubbing_tts/v1` với key SHA-256 theo text đã normalize,
  provider host, model, voice, speed và sample rate; metadata không chứa credential/raw response.
- Thêm timing rewrite qua `call_llm` hiện có với strict JSON validator giữ số, phần trăm, tiền tệ, unit,
  product token và negation. Không có LLM config thì bỏ rewrite và đi thẳng fit/review policy.
- Natural mode đo WAV thật, chỉ re-synthesize outlier, giới hạn speed mặc định 1.08x và không truncate.
  Outlier chưa giải quyết sẽ `review` (dừng trước mix) hoặc `allow-overlap` có warning. Legacy vẫn có
  max-speed/truncate và ghi action `legacy_truncate`.
- GUI có Auto/Translation/Original, Natural/Legacy, rewrite/cache/unresolved controls và report dialog
  read-only. Provider failure/review không còn bị báo thành công bằng video gốc.
- CLI có `dub` và `process --dub`; exit code 6 = review, 7 = provider failure. Quiet `dub` chỉ in output
  path khi thành công.

### Validation đã đo
- Targeted: dubbing **55 passed**; subtitle pipeline **1 passed**; CLI **58 passed**; translate
  **14 passed, 7 skipped**; ASRData **46 passed**.
- Full suite với `LOCALAPPDATA=AppData/CodexTest`: **379 passed, 26 skipped, 0 failed** / 405 collected,
  76.62 giây. Skip thuộc live credential/service markers, Bcut HTTP 412, JianYing rate-limit và Bing 404.
- Ruff `videocaptioner/`: pass. Pyright `videocaptioner/cli/`: **0 errors, 0 warnings**. Translation sync:
  pass.
- FFmpeg integration tạo video fixture thật và WAV FakeTTS deterministic: cache miss→hit, target routing,
  measured rewrite, Natural review không truncate, allow-overlap, Legacy truncate, voice-track/mix và
  video không audio stream đều pass.

### Packaged artifact
- PyInstaller 6.22.2 exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`.
- SHA-256: `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`; Authenticode:
  `NotSigned`.
- Archive có `dubbing/initial.md`, `dubbing/rescue.md` và `DubbingReportDialog`. Warning file có 555
  missing-module lines, chủ yếu optional/transitive từ ModelScope, yt-dlp, urllib3; không có match Natural
  Dubbing. Noteworthy: `tzdata`, `sip`, `js`, `curl_cffi`, `yt_dlp_ejs` không được bundle.
- Smoke exact EXE: parent PID 21468 + child PID 34896 cùng sống sau 15 giây; log append 55 bytes, 0 startup
  exception match; đã đóng đúng hai PID và xác nhận 0 process test còn lại.

### Còn chờ user/provider thật
- Chưa nghiệm thu chất lượng nghe tiếng Việt, OpenAI/MiniMax/local provider thật, rate-limit hay video dài.
- Không có live API/key nào được dùng trong machine acceptance. EXE GUI đã startup pass nhưng workflow
  media/TTS thật trong packaged app vẫn chờ user thử.

## 2026-08-18 (Sửa lỗi theo review code)

### Sửa lỗi chặn tính năng
- **Dubbing hỏng hoàn toàn với ffmpeg 8.x**: `-filter_complex_script` đã bị ffmpeg 8.0 loại bỏ →
  bước ghép voice track fail 100%. Nay probe một lần rồi chọn `-filter_complex_script` (ffmpeg cũ)
  hoặc `-/filter_complex` (ffmpeg mới). Đã verify end-to-end với ffmpeg N-126188 (2026-08-17).
- **Không lồng tiếng được sang Trung/Nhật/Quảng**: `_strip_cjk` lọc ký tự CJK vô điều kiện làm mọi
  câu rỗng. Nay có `DubbingConfig.strip_cjk`, `task_factory` tự tắt khi ngôn ngữ đích là CJK; nếu
  toàn bộ câu bị lọc thì báo lỗi nêu rõ nguyên nhân thay vì "TTS thất bại cho tất cả segments".
- **Mix audio fail trên video không tiếng**: filter `[0:a]` không có stream. Nay probe bằng ffprobe
  và tự rơi về chế độ "tắt audio gốc".
- **Search & Replace chưa được nối vào UI**: dialog chỉ được import, không có nút nào gọi. Nay có
  action trong command bar của `SubtitleInterface`, thay thế hàng loạt trên cả cột gốc và cột dịch.
- **`uv.lock` lệch `pyproject.toml`** (`yt-dlp>=2026.6.9` vs lock `2025.12.8`) làm `uv sync --frozen`
  của CI fail. Đã `uv lock` (yt-dlp 2026.7.4) và verify `remote_components: ["ejs:github"]` là option
  thật của yt-dlp → bản fix YouTube HD mới thực sự có hiệu lực.
- **ASR chunking sinh chunk rác**: mp3 padding làm audio dài hơn vài chục ms so với yêu cầu, khiến
  `_split_audio` cắt thêm một chunk ~48ms và gửi thêm một request ASR cho mỗi file. Nay bỏ qua phần
  đuôi ngắn hơn 1s.
- **`logger` chưa định nghĩa** trong `FasterWhisperSettingWidget._extract_7z` → NameError khi giải
  nén bằng tar thất bại.

### Sửa chất lượng dịch / cache
- Cache key của translator dùng chỉ số nội dung tất định (`source_signature`) thay cho ngữ cảnh toàn
  cục do LLM sinh ở temperature=1 — trước đó cache 7 ngày mất hiệu lực sau 1 giờ.
- Không build ngữ cảnh toàn cục khi số dòng < 10 (dịch lại vài dòng đã chọn không còn tốn thêm một
  lần gọi LLM cho một bản brief vô nghĩa).
- Reflect mode không còn ghi raw dict (`{'initial_translation': ...}`) vào phụ đề khi LLM trả sai
  schema — điều kiện nào không hợp lệ thì giữ nguyên bản gốc.
- Progress bar không còn đứng khi hit cache (`update_callback` được gọi cả trên nhánh cache).
- Chỉ gửi **tên file** thay vì đường dẫn tuyệt đối vào prompt LLM.
- `core/llm/context.py` chuyển sang `contextvars` + `submit_with_context` ở mọi ThreadPool → batch
  chạy song song không còn lẫn nhãn `task_id`/`stage` trong `llm_requests.jsonl`.

### Dọn dẹp
- Lint: `ruff check videocaptioner/` từ 58 lỗi → **0**. Gỡ dead config `speed_range[0]`, `gap_ms`,
  `output_format` (`speed_range` → `max_speed`), bỏ tham số không dùng của `_align_timeline`.
- Test suite: **21 failed + 16 errors → 0** (325 passed, 23 skipped). Nguyên nhân đã sửa: module
  `tests/test_tts` không collect được (`SiliconFlowTTS` đã bị gỡ trong refactor), thiếu fixture
  `mock_llm_client`, fixture cache rò trạng thái sang test khác, `MockTTS` ghi file không encoding.
  Test phụ thuộc service miễn phí bên thứ ba nay **skip** khi outage/rate-limit thay vì fail.
- Gộp 4 file `.spec` trùng nhau thành `VideoCaptioner.spec` (đặt tên exe qua `VC_BUILD_NAME`).
- Thêm `scripts/sync_translations.py` (có `--check`) thay cho bước copy tay 2 bản translations.
- `pyproject.toml`: `[tool.uv] dev-dependencies` → `[dependency-groups] dev` (bỏ deprecation warning).
- Docs: sửa đường dẫn `app/core/...` → `videocaptioner/...`, bỏ link chết `docs/CI_SETUP.md` và
  `docs/TESTING.md`.

### Còn tồn (chưa sửa)
- **Bing translator hỏng phía Microsoft**: `https://edge.microsoft.com/translate/auth` trả 404 (đã
  verify độc lập bằng curl, có và không có User-Agent). Cần tìm endpoint mới của Edge translate —
  không đoán. Trong lúc đó `--translator google` vẫn chạy tốt.
- CLI vẫn chưa có lệnh `dub`.

## 2026-06-30 (Nâng cấp dịch thuật)
- Thêm pha "ngữ cảnh toàn cục": đọc toàn bộ phụ đề một lần để sinh brief (chủ đề/tông giọng/glossary), nhồi vào mọi khối dịch giúp nhất quán thuật ngữ và mạch văn (áp dụng cho cả chế độ thường và phản tư).
- Sửa lỗi cache key: nay phân biệt theo chế độ phản tư, custom prompt và ngữ cảnh — tránh nhận nhầm kết quả cache cũ khi đổi thiết lập.
- Dịch phản tư có chọn lọc: chỉ phân tích sâu các dòng "có mùi dịch máy" để tiết kiệm token/thời gian.
- Ghi log phần phản tư (initial/reflection) thay vì bỏ đi; thêm nhãn tiến trình riêng cho chế độ phản tư.

## 2026-06-30
- Hoàn thiện engine lồng tiếng (Dubbing): tích hợp MiniMax TTS và mở rộng nhiều nhà cung cấp TTS khác nhau.
- Cải thiện chất lượng, tốc độ xử lý âm thanh và bổ sung chức năng trộn/ghép (merge) audio.
- Giữ giọng lồng tiếng ở âm lượng đầy đủ khi trộn với audio gốc.
- Thêm tùy chọn lồng tiếng hàng loạt (batch dubbing) và cho phép nhập thủ công số luồng TTS (thread count).
- Tăng tốc bước trộn âm thanh.

## 2026-05-01
- Thêm tính năng "Tìm kiếm & Thay thế" (Search & Replace) trong giao diện `SubtitleInterface` (Tab Tối ưu và Dịch phụ đề).
- Tính năng này hiển thị một popup nhập liệu, cho phép người dùng thay thế hàng loạt những từ bị dịch sai trong dữ liệu phụ đề hiện tại.
- Cập nhật tài liệu `README.md` tương ứng.


## Lịch sử cũ (gộp từ `docs/TRANG_THAI_DU_AN.md`, snapshot ngày 2026-05-01)

File snapshot đã bị xóa; nội dung dưới đây là bản rút gọn để giữ lịch sử. Mọi mục mới hơn ở trên
mới là trạng thái hiện tại.

- Build lúc đó: `dist/VideoCaptioner-PhaseD-20260501.exe` (~107 MB, onefile), Python 3.12.13,
  PyInstaller 6.20.0, tên EXE đặt qua `VC_BUILD_NAME`. Từ 2026-08 spec đã chuyển sang onedir.
- Phase D lồng tiếng bằng TTS API: thêm `core/dubbing/` (config, audio_mixer, engine), `DubbingThread`,
  tab "Lồng tiếng" (pipeline + thủ công), `DubbingTask` trong entities, 9 config item dubbing, dubbing
  step tùy chọn trong `subtitle_pipeline_thread`. Tái dùng `core/tts` (OpenAI TTS, SiliconFlow, voice
  clone + cache); ba chế độ audio gốc (giữ/giảm 40%/tắt); căn timeline bằng atempo 0.75x–1.5x, truncate
  khi vượt. Sau này Natural timing, planner, rewrite và VieNeu Local thay thế phần lớn logic này.
- Dọn UI: xóa card "Trợ giúp", "Gửi phản hồi" ở Cài đặt và icon GitHub trên sidebar.
- Tự cập nhật phiên bản: `auto_update_thread.py` tải EXE mới, `UpdateDialog` với progress + batch script
  thay thế và restart; `main_window.onNewVersion()` và `setting_interface.checkUpdate()` dùng dialog này.
  (2026-09-04: dialog từ chối thay EXE trên bản onedir và chỉ giữ file đã tải.)
- Bản dịch Việt: `resource/translations/VideoCaptioner_vi_VN.json` 698 entry, đồng bộ sang
  `videocaptioner/resources/translations/`.
- Kế hoạch còn dang dở khi đó: dubbing trong batch FULL_PROCESS, CLI `videocaptioner dub` (đã có),
  test end-to-end với TTS key thật, tối ưu build (UPX/exclude module).
