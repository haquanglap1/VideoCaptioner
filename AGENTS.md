# AGENTS.md — VideoCaptioner

Đọc file này đầy đủ trước khi làm việc trong repository. Đây là hướng dẫn bền vững cho agent; trạng
thái công việc hiện tại nằm trong `status.md`, còn cấu hình chạy/build thực tế nằm trong
`pyproject.toml`, `uv.lock`, và `VideoCaptioner.spec`.

## Bắt đầu mỗi task

1. Đọc `README.md` để nắm tính năng, lệnh CLI, yêu cầu môi trường và cách build được hỗ trợ.
2. Đọc phần mới nhất của `status.md`; chỉ đọc các mục cũ khi task liên quan. Nếu trạng thái ở
   `docs/TRANG_THAI_DU_AN.md` khác `status.md`, ưu tiên `status.md` vì file kia là snapshot cũ.
3. Đọc đúng tài liệu domain cần sửa dưới `docs/dev/`, `docs/config/`, hoặc `docs/guide/`; không nạp cả
   thư mục nếu không cần.
4. Trước khi sửa, chạy `git status --short --branch` và giữ nguyên mọi thay đổi không thuộc task.
5. Dùng `rg`/`rg --files` để tìm symbol và call site trước khi đọc hoặc thay đổi code.

`CLAUDE.md` là bản song song cho Claude Code, hiện nằm trong `.gitignore` nên chỉ tồn tại cục bộ. Khi
máy có file đó, cập nhật nó cùng lúc với thay đổi quy tắc ở đây; `AGENTS.md` là bản chuẩn khi hai file
mâu thuẫn. Không sao chép quy tắc đặc thù Unreal Engine/Perforce từ project khác vào đây.

## Project snapshot

- Ứng dụng xử lý phụ đề video bằng Python: ASR → split/optimize → translate → subtitle → synthesis;
  có cả CLI và GUI Windows.
- Python được hỗ trợ: **3.10–3.12**. Không dùng Python 3.13 để tạo môi trường project.
- Quản lý môi trường và lockfile bằng **uv**. `pyproject.toml` và `uv.lock` là nguồn sự thật cho dependency.
- GUI dùng **PyQt5** + **QFluentWidgets**. Công việc dài chạy qua các class trong
  `videocaptioner/ui/thread/`; không block Qt main thread và không cập nhật widget trực tiếp từ worker.
- Xử lý media dựa vào **FFmpeg/ffprobe**. Một số ASR/translator/TTS/LLM phụ thuộc dịch vụ hoặc API key
  bên ngoài; không coi unit test offline là bằng chứng end-to-end cho các dịch vụ đó.
- Đóng gói Windows dùng **PyInstaller** với duy nhất `VideoCaptioner.spec`; entry point GUI là
  `scripts/pyinstaller_gui.py`.
- Version control là Git. Không commit, push, tạo tag/release, hoặc viết GitHub nếu user chưa yêu cầu.

## Cấu trúc chính

```text
videocaptioner/cli/             CLI parser, commands, config, output và exit codes
videocaptioner/core/asr/        Speech recognition và chunking
videocaptioner/core/split/      Tách/căn chỉnh câu phụ đề
videocaptioner/core/optimize/   Tối ưu phụ đề bằng LLM
videocaptioner/core/translate/  LLM, Google, Bing và DeepLX translators
videocaptioner/core/subtitle/   SRT/ASS/style/rendering
videocaptioner/core/dubbing/    TTS orchestration và audio mixing
videocaptioner/core/utils/      FFmpeg, subprocess, logging, cache, installer
videocaptioner/ui/              PyQt views, widgets, threads và task factory
videocaptioner/core/prompts/    Prompt `.md` cần có cả trong source package và EXE
resource/                       Runtime assets, fonts, translations và subtitle styles
videocaptioner/resources/       Fallback resources cho package cài bằng pip
tests/                          Unit/integration tests theo domain
scripts/                        Launcher, translation sync và PyInstaller entry point
```

Luồng dữ liệu chuẩn dùng các entity trong `videocaptioner/core/entities.py` và các type theo domain;
không truyền dict tùy ý qua nhiều tầng nếu đã có model tương ứng. UI là tầng điều phối/trình bày,
không đặt business logic mới vào view khi logic có thể nằm trong `core/`.

## Quy tắc sửa code

- Ưu tiên thay đổi nhỏ nhất giải quyết đúng nguyên nhân; giữ API, config key, CLI flag và exit code ổn
  định trừ khi task yêu cầu migration.
- Tách network/subprocess/FFmpeg khỏi UI. Luôn truyền argument dưới dạng list cho subprocess khi có
  thể; không ghép command từ input người dùng bằng `shell=True`.
- Với code đa luồng, giữ `contextvars` khi chuyển việc sang executor bằng helper hiện có; không làm
  lẫn `task_id` hoặc stage giữa các job song song.
- Không ghi API key, cookie, absolute local path, transcript riêng tư, hoặc raw response nhạy cảm vào
  source, test fixture, log mẫu hay artifact được version control.
- Mọi đường dẫn runtime phải đúng ở cả source mode, pip-installed mode và PyInstaller frozen mode.
  Kiểm tra logic trong `videocaptioner/config.py` trước khi đổi resource/data path.
- `resource/translations/` là bản phát triển/bundle; `videocaptioner/resources/translations/` là bản
  fallback trong package. Sau khi đổi translation, chạy
  `uv run python scripts/sync_translations.py --check`; nếu có drift thì chạy script không có
  `--check`, rồi kiểm tra lại.
- Khi thêm runtime resource hoặc dynamic import, cập nhật `VideoCaptioner.spec` và kiểm tra trên EXE;
  chạy từ source không chứng minh resource đã được bundle.
- Giữ comment ngắn và giải thích lý do/bẫy, không kể lại code. Code, identifier, CLI flag và tên file
  dùng English; nội dung UI/documentation theo ngôn ngữ hiện có của file.
- Không sửa trực tiếp file sinh tự động như `videocaptioner/_version.py`, `*.qm`, `build/`, `dist/`,
  cache hoặc log. Với `*.qm`, sửa nguồn `*.ts` rồi dùng toolchain tương ứng.

## Known guards

- `status.md` ghi Bing translator đang hỏng do endpoint Microsoft trả 404. Không đoán endpoint mới và
  không gọi việc đổi User-Agent là fix nếu chưa có phép đo end-to-end.
- FFmpeg 8.x đã bỏ `-filter_complex_script`; giữ cơ chế probe/chọn cú pháp tương thích cho cả FFmpeg
  cũ và mới trong dubbing.
- Video không có audio stream phải tiếp tục dùng đường fallback không trộn audio gốc.
- Với ngôn ngữ CJK, không bật lọc CJK theo cách làm rỗng toàn bộ câu TTS.
- Cache translator phải phụ thuộc nội dung/config tất định; không đưa output LLM ngẫu nhiên vào cache key.
- Không gửi absolute local path vào prompt LLM; chỉ gửi metadata tối thiểu cần thiết.
- Không ghi API key vào `os.environ`: LLM dùng `LLMCredentials` + `configure_llm_client()` trong
  `core/llm/client.py`; mọi `subprocess.run/Popen` truyền `env=child_environment()` từ
  `core/utils/subprocess_helper.py` để child process không kế thừa `OPENAI_*`/`VIDEOCAPTIONER_*`.

## Cài đặt và lệnh chuẩn (PowerShell 7)

Không tự đổi dependency hoặc cài package global. Khi user cho phép đồng bộ dependency project:

```powershell
uv sync --frozen
```

Chạy app từ source:

```powershell
uv run --frozen videocaptioner --help
uv run --frozen videocaptioner
```

Quality gates cơ bản:

```powershell
uv run --frozen ruff check videocaptioner/
uv run --frozen pyright videocaptioner/
uv run --frozen pytest tests/test_cli/ -q
uv run --frozen python scripts/sync_translations.py --check
```

Chạy thêm test gần code đã sửa trước; chỉ chạy full suite khi phạm vi/rủi ro đáng kể:

```powershell
uv run --frozen pytest tests/ -q
```

Phân biệt rõ test offline với test `integration`, `slow`, `llm`, hoặc translator dùng service ngoài.
Thiếu API key/service hoặc test được skip không phải là bằng chứng tính năng online đã pass.

## Build EXE Windows

Build mặc định:

```powershell
uv run --frozen pyinstaller VideoCaptioner.spec --clean --noconfirm
```

Artifact mặc định: `dist/VideoCaptioner.exe`. Nếu cần tên riêng, không tạo thêm file spec:

```powershell
$env:VC_BUILD_NAME = 'VideoCaptioner-<label>'
uv run --frozen pyinstaller VideoCaptioner.spec --clean --noconfirm
Remove-Item Env:VC_BUILD_NAME
```

`--clean` có thể thay thế output cùng tên trong `build/` và `dist/`; kiểm tra target trước nếu đã có
artifact cần giữ. Không commit `build/` hoặc `dist/`.

Sau build phải báo riêng từng gate:

1. PyInstaller exit code và số warning/error đáng chú ý.
2. File EXE tồn tại, size, timestamp và SHA-256.
3. Smoke test khởi động GUI từ chính EXE, quan sát process sống đủ lâu để loại lỗi import/resource lúc
   startup, rồi đóng đúng process do test tạo.
4. Nếu chưa chạy workflow thật với video/FFmpeg/API, ghi rõ runtime media/online chưa được nghiệm thu.

Build thành công không đồng nghĩa ASR, translation, TTS, FFmpeg synthesis hoặc auto-update đã pass
end-to-end. Không gọi task hoàn tất vượt quá bằng chứng thực tế.

## Quản lý artifact và trạng thái

- Giữ nguyên `.env`, cookies, `AppData/`, `work-dir/`, media đầu vào/đầu ra và log của user.
- Không xóa hoặc ghi đè artifact khác tên chỉ để dọn build.
- Chỉ cập nhật `status.md` khi có thay đổi bền vững về code/behavior/validation; một lần build lại không
  tự động trở thành lịch sử tính năng.
- Trước khi bàn giao, chạy `git status --short`, liệt kê đúng file đã sửa và nêu các gate đã chạy,
  chưa chạy, fail hoặc skip.
