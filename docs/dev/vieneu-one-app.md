# VieNeu Local one-app

`VieNeu Local` là provider TTS được VideoCaptioner quản lý. Người dùng chỉ mở VideoCaptioner; ứng dụng
tự chọn loopback port, sinh bearer token theo session, khởi động sidecar ẩn khi cần và đóng đúng process
tree do nó sở hữu. Provider `Local AI` vẫn dành cho server OpenAI-compatible do người dùng tự quản lý.

## Hợp đồng runtime

- Protocol: `vieneu-runtime-protocol-v1`.
- Model state: `vieneu-model-state-v1`.
- Endpoint chỉ bind `127.0.0.1`; health phải khớp service ID, protocol, session và model revision.
- Model được pin theo Hugging Face commit SHA trong toàn bộ dubbing job. Tokenizer/codec cũng được pin
  theo revision trong `runtime/vieneu/runtime-manifest.json`.
- Runtime chỉ đọc snapshot local. Check/download model có thể chạy nền, nhưng activation chỉ xảy ra khi
  không có job đang giữ lease.
- Health, danh sách voice và WAV 48 kHz phải pass trước khi candidate được activate. Candidate lỗi được
  đánh dấu rejected; last-known-good vẫn chạy được offline và có thể rollback thủ công.
- Log/state/cache identity không chứa bearer token, API key hoặc transcript. Cache VieNeu được namespace
  theo model/runtime/protocol/backend/sample rate nên update không xóa WAV cũ.

Qt chỉ điều phối qua `videocaptioner/ui/thread/vieneu_runtime_thread.py`; VieNeu, CUDA, FastAPI và model
không được import vào Qt process.

## Cách dùng

Trong tab `Lồng tiếng`, chọn `VieNeu Local`. API Base, API Key, Model và Sample Rate do ứng dụng quản lý;
không cần mở batch/server riêng. Các nút `Start/Stop`, `Check for model update`, `Rollback` và
`Open model folder` chạy ngoài Qt main thread, tuần tự qua một hàng đợi của tab: action đến khi đang bận
được giữ lại (mới nhất thắng) và chạy khi thread hiện tại xong, nên bấm `Tải danh sách` ngay sau `Start`
không bị bỏ qua; `Start` thành công tự nạp danh sách giọng.

`Auto update` mặc định bật và chỉ **kiểm tra** revision trên Hugging Face khi tab được mở; có bản mới thì
một InfoBar đề nghị `Download and activate`, không tải gì nếu người dùng chưa bấm. Tắt `Auto update` thì
khởi động không kết nối mạng. Nút `Check for model update` cũng chỉ kiểm tra rồi đề nghị. Khi tải, tiến
độ (số file, MB đã ghi) hiện ở thanh tiến độ của tab; validate trên GPU khởi động lại sidecar với
candidate nếu không có job đang giữ lease, còn không thì candidate được giữ lại và hoãn kích hoạt. Khi
offline, active model hiện tại vẫn dùng được.

CLI source hoặc EXE đóng gói dùng cùng lifecycle:

```powershell
videocaptioner vieneu status
videocaptioner vieneu update
videocaptioner vieneu update --revision <40-character-sha>
videocaptioner vieneu rollback
videocaptioner dub input.mp4 --subtitle translated.srt `
  --tts-provider vieneu-local --voice "Minh Đức" --timing-mode natural -o dubbed.mp4
```

`vieneu-local` không yêu cầu `--tts-api-key`, `--tts-api-base`, model hoặc sample rate. CLI không tự check
network trước mỗi job; nó dùng active model và dừng sidecar của chính process ở `finally`.

## Layout portable/installed

```text
VideoCaptioner-VieNeu-OneApp-<label>/
  VideoCaptioner-VieNeu-OneApp-<label>.exe
  distribution-manifest.json
  runtime/vieneu/
    python.exe
    bridge/vieneu_bridge.py
    runtime-manifest.json
    Lib/site-packages/...
  AppData/models/vieneu/
    state.json
    hf/models--.../snapshots/<sha>/...
```

Model seed và mọi model update là dữ liệu mutable bên ngoài one-file EXE. Chỉ có một shortcut
`VideoCaptioner`; không có shortcut/server console cho sidecar.

## Build tái lập

Runtime dùng Python 3.12 do `uv` quản lý, source VieNeu ở commit ghi trong manifest, và lock có hash cho
từng package. Không copy developer `.venv` và không cài global:

```powershell
.venv\Scripts\python.exe scripts\build_vieneu_runtime.py `
  --source <thư-mục-clone-VieNeu-TTS> `
  --output build\vieneu-runtime-<label>

.venv\Scripts\python.exe scripts\build_vieneu_one_app.py `
  --name VideoCaptioner-VieNeu-OneApp-<label> `
  --runtime build\vieneu-runtime-<label> `
  --model-root AppData\models\vieneu
```

Builder ghi SHA-256 của requirements lock, VieNeu wheel và EXE vào manifest. File static development
`torch/lib/dnnl.lib` không cần cho inference và được bỏ khỏi runtime; DLL runtime vẫn giữ nguyên và GPU
import/synthesis phải được smoke-test lại sau bước này.

Builder runtime yêu cầu source ở đúng commit ghi trong manifest với working tree sạch, và cài dependency
bằng `uv pip install --no-config --require-hashes`: cấu hình `[tool.uv]` của workspace (ví dụ
`override-dependencies` PyQt5-Qt5 không có hash) không được lọt vào runtime. Chạy source mode với runtime
vừa build bằng `$env:VIDEOCAPTIONER_VIENEU_RUNTIME = '<repo>\build\vieneu-runtime-<label>'`; locator mặc
định chỉ tìm `<ROOT>/runtime/vieneu/`. Khi tải model trên Windows, `HuggingFaceVieNeuClient` ép
`HF_HUB_DISABLE_SYMLINKS=1` (huggingface_hub dò quyền symlink lười theo thư mục nên nhiều thread tải có thể
dính WinError 1314 trên máy không có quyền symlink) để cache luôn là file thường.

Installer Windows dùng duy nhất source `installer/VideoCaptioner-VieNeu-OneApp.wxs`. Vì payload runtime +
model vượt giới hạn thực tế của một cabinet/PE tự giải nén, output hỗ trợ là một MSI cùng các external CAB
trong một thư mục phân phối; user chỉ chạy MSI và nhận đúng một shortcut. Đây vẫn là one-app contract,
không phải một giant one-file EXE:

```powershell
wix build installer\VideoCaptioner-VieNeu-OneApp.wxs -arch x64 `
  -d SourceDir=<absolute-portable-directory> `
  -intermediatefolder build\wix-vieneu-oneapp `
  -o dist\installer\VideoCaptioner-VieNeu-OneApp-<label>.msi
```

### Thin web installer

Phương án mặc định cho người dùng có mạng tách thành:

- `VideoCaptioner-Base.wxs`: EXE + shortcut, được nhúng vào web setup;
- `VideoCaptioner-VieNeu-Runtime.wxs`: runtime GPU và model seed, xuất thành MSI + external CAB;
- `VideoCaptioner-Web-Bundle.wxs`: Burn bootstrapper khoảng 120 MB, tải remote payload trong lúc cài.

`PayloadBaseUrl` là biến build, không hardcode URL production trong source. Burn dùng size/hash lấy từ
payload build-time để verify từng file trước khi apply. CDN production phải là HTTPS, hỗ trợ range/resume
và giữ immutable file name/hash; build loopback chỉ dùng để nghiệm thu ngay trên máy phát triển:

```powershell
wix build installer\VideoCaptioner-Web-Bundle.wxs -arch x64 `
  -ext WixToolset.BootstrapperApplications.wixext.dll `
  -d BaseMsi=<absolute-base-msi> `
  -d RuntimeMsi=<absolute-runtime-msi> `
  -d PayloadDir=<absolute-payload-directory> `
  -d PayloadBaseUrl=https://downloads.example.com/videocaptioner/1.1.0 `
  -o dist\VideoCaptioner-Web-Setup.exe
```

Không dùng MSI custom action để tự tải network. Burn quản lý download, verify, package cache, rollback và
uninstall transaction. Build local-test trỏ `127.0.0.1` chỉ chạy khi payload server nội bộ đang hoạt động;
không gửi file đó cho máy khác trước khi rebuild bằng URL HTTPS thật.

## Acceptance boundary

Fake bridge/Hugging Face tests chứng minh ownership, auth, cancellation, retry, update và rollback logic;
chúng không chứng minh CUDA/TTS. Trước khi phát hành phải báo riêng: real GPU cold/warm start, voices/WAV,
concurrency/batching, controlled update + forced rollback, Natural Dubbing/FFmpeg từ exact packaged EXE,
GUI startup, installer, zero owned processes và nghe thủ công chất lượng tiếng Việt.
