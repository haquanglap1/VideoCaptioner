# Project Status

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
