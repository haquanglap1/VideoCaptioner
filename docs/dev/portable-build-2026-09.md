# Portable Windows để chạy ở ổ khác — 2026-09-10

User yêu cầu build EXE để tự đưa sang ổ khác. Tiếp tục worktree ASR-S3,
HEAD `f03420c`; giữ nguyên ba tài liệu nghiệm thu đang sửa, không commit/push.
Bản giao là onedir trong ZIP: giải nén cả thư mục rồi chạy EXE. Không cần
cài Python; ZIP kèm FFmpeg/ffprobe đã có trên máy, không chứa model/runtime AI,
key, cookie, media riêng hay cấu hình cá nhân. Runtime/model dùng lại nơi đã cài
trong cùng tài khoản hoặc chọn đường dẫn trong Cài đặt; không tự chuyển model
sang ổ mới. VieNeu cần runtime riêng.

## Lỗi phát hiện trước bàn giao

- Candidate đầu build exit 0 / **199,028 s**, 6 warning / 0 error. Khởi động
  bản giải nén ở ổ C có GUI, sống 45 s và đóng exit 0, nhưng log ghi request
  GitHub và lượt tải bản cũ đã hủy dù `CheckUpdateAtStartUp=false`.
  **Không giao candidate này.** Giữ ở
  `build/package-20260910/not-for-delivery-r1/`, cùng log/receipt đầu.
- `_start_background_services()` luôn tạo VersionChecker, chưa đọc công tắc
  đã có. Nay chỉ tạo worker khi công tắc bật; kiểm tra FFmpeg vẫn chạy khi tắt.
  Regression mới fail trước sửa, pass sau sửa; fixture bật/tắt config trong
  RAM và giữ cơ chế cô lập file settings, `thread.wait()` khi teardown.
- Build trực tiếp từ worktree bằng interpreter cạnh checkout không chạy hook
  tạo `_version.py`, khiến app dùng fallback `0.0.0-dev`. R2 dùng cùng generator
  `dump_version` của Hatch VCS hook với version lấy từ Git:
  **`1.5.1.dev90+gf03420c7e.d20260910`**. Chỉ sinh file trong snapshot build,
  không sửa tay file generated hoặc thay version source. Dùng toolchain Hatch/
  setuptools-scm đã có trong cache local, không tải/cài/sync dependency.

## Kiểm tra source

- **160 pass / 1 warning**, gồm toàn CLI và lifecycle VersionChecker;
  regression công tắc là 1 test mới. Lượt trước sửa: 1 fail / 10 deselected.
- Ruff app/tests pass; Pyright app 0 errors / 0 warnings; translations in sync.
  Cảnh báo harness Pyright không thấy `.venv` trong worktree đã được bù bằng
  `--pythonpath` trỏ interpreter 3.12.13 có sẵn. Không nâng version công cụ.
- Settings/cache/log/test temp riêng. Không chạy ASR/LLM/TTS inference hoặc
  lặp media đã có. Đây là sửa startup/config, không đổi thuật toán phân đoạn.

## Bản giao R2

**`dist/VideoCaptioner-20260910-R2-Portable.zip`** — giải nén nguyên thư mục,
chạy `VideoCaptioner-20260910-R2.exe`. Trong gói có `HUONG-DAN.txt`, license,
`SHA256SUMS.txt` cho từng file và cấu hình đã chọn với key trống.

| Gate | Bằng chứng R2 |
| --- | --- |
| PyInstaller | **Exit 0 / 205,342 s**, 6 WARNING / 0 ERROR; cùng spec và interpreter 3.12.13, snapshot 291 file gồm version do toolchain sinh |
| Warning | js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit; dependency warning như candidate đầu |
| EXE | **31.264.100 byte**, timestamp local **2026-09-10 12:28:53**; SHA-256 `a897118666718784b69ebf234028a22ebd2583c2e4d8c2e2ae63c505fc12778d` |
| ZIP | **232.660.344 byte**, 590 file, giải nén **529.567.498 byte**; SHA-256 `4049aae64d9c5cae9e1f2d53b943561871815cf793e1125313329f91f041e6ed` |
| Nội dung gói | 10 module PYZ khớp source cuối; 2 prompt split khớp byte; module version mang đúng snapshot Git. CRC và SHA từng entry ZIP pass |
| Chuyển ổ | Giải nén chính ZIP từ ổ D sang thư mục test riêng ở ổ C, đối chiếu lại toàn bộ hash; không dùng junction tới checkout |
| CLI/tools ở ổ C | CLI `--help` exit 0, UTF-8 đọc được; ffprobe đi kèm chạy exit 0 |
| GUI ở ổ C | Cửa sổ chính sau **1,049 s**, sống đủ 45 s; tổng **45,591 s**, đóng đúng process exit 0, không child còn lại / traceback / hoạt động update trong log |

Smoke dùng lifecycle của đúng process tạo ra; không bật phiên Computer Use.
Các bản thử ở TEMP riêng đã đóng; không động vào app đang mở của user. Candidate
đầu có warning hành vi được giữ cùng bằng chứng, không tính chung thành pass.

Cấu hình portable giữ gateway `api.videocaptioner.cn/v1`, `gpt-5.6-terra`,
timeout 300 s, 2 thread/batch 5, bật split/dịch; OmniVoice Việt, Natural 1,00×,
delay cap 2500 ms/review. Tắt tự kiểm tra cập nhật khi mở và tự cập nhật model
VieNeu trong gói. Key không sao chép; cache/media/user settings không đưa vào ZIP.

Không chạy lại workflow media/API trên R2 này. Bằng chứng clip ở
[biên bản câu đọc](speech-listening-2026-09.md) vẫn giữ phạm vi source split /
CLI frozen SpeechSegmentation; code media đã đối chiếu trong gói mới.
Không suy build/startup thành nghiệm thu máy sạch, chuyển toàn bộ model,
ASR/TTS mọi ngôn ngữ hoặc installer Setup.exe. **Duyệt nghe vẫn còn mở.**

## Thay đổi và evidence

- Source sửa: `videocaptioner/ui/view/main_window.py`.
- Test sửa: `tests/test_ui/test_version_checker_lifecycle.py`.
- Tài liệu sửa trong lượt build: biên bản này và `status.md`; hai báo cáo
  speech-segmentation/speech-listening đang sửa từ lượt trước được giữ nguyên.
- Evidence ở `build/package-20260910/`: build log/result của cả hai candidate,
  manifest, helper, receipt ZIP và smoke ổ C. Giữ source snapshot, PyInstaller
  intermediate và candidate lỗi; việc xóa scratch đã bị policy chặn ở lượt
  trước, không thử phương thức khác để vượt chặn. Artifact người dùng ở `dist/`.
- `git diff --check` pass. Không commit/push/tag/release hoặc cài dependency.
