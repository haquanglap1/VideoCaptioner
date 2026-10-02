# Tải playlist /合集 / nhiều phần P

## Dùng trong app

Ở **Tạo tác vụ**, bấm **Tải playlist /合集 / nhiều phần P**. Dán URL rồi
**Đọc danh sách**. Mở cửa sổ chưa gọi mạng. Có hai phạm vi:

- **Tự nhận diện合集 / playlist**: link một video thuộc合集 Bilibili được mở
  thành danh sách video của合集; cũng nhận link danh sách trực tiếp.
- **Các phần P của video Bilibili**: đọc các phần của riêng BV hiện tại,
  kể cả link nhập có `?p=2`. Không chuyển sang合集 chứa video đó.

Bấm **Chọn tất cả** hoặc chọn từng hàng; chọn thư mục đích rồi **Tải / Tiếp tục
các tập đã chọn**. Queue tải lần lượt theo thứ tự danh sách. Mỗi video có thư
mục và trạng thái riêng, không ghi đè video khác trùng tên. Tập lỗi không làm
mất các tập đã xong; danh sách lồng nhau/thiếu URL được báo để mở riêng.

**Dừng tải** hoặc đóng cửa sổ yêu cầu hủy; chờ thao tác mạng/FFmpeg hiện tại
trả về, giữ media hoàn tất và `.part`. Mở lại cùng danh sách/thư mục và chọn
tải tiếp: file đã hoàn tất phải khớp URL, size, SHA256 mới được dùng lại mà
không gọi mạng. File/receipt bị sửa hoặc bị xóa sẽ báo lỗi bảo toàn; chọn
thư mục mới để tải lại. File dở dùng cơ chế resume của yt-dlp, tùy server hỗ
trợ Range; không coi `.part` là media hoàn chỉnh.

Sau tải, **Đưa video đã tải sang Xử lý hàng loạt** đưa từng file thành hàng
riêng, giữ thứ tự playlist. Chọn loại xử lý phù hợp với video ở tab Batch rồi
bấm bắt đầu khi muốn. Thao tác tải/handoff không tự chạy ASR, dịch hoặc TTS.
Chế độ URL đơn cũ vẫn dùng `noplaylist=True` và đi qua pipeline một file.

Cookies lấy từ `AppData/cookies.txt`; worker tạo bản sao tạm rồi hủy sau request,
vì yt-dlp có thể ghi lại cookie jar khi đóng. Không thay cookies/settings thật.
Lỗi HTTP403/412/429 được báo rõ; không thử lách quyền truy cập hoặc đổi gateway.

## CLI

```powershell
videocaptioner download "BILIBILI_URL" --list-playlist
videocaptioner download "BILIBILI_URL" --playlist -o "downloads"
videocaptioner download "BILIBILI_URL" --playlist --playlist-items "1,3-5" -o "downloads"
videocaptioner download "BILIBILI_URL" --playlist --playlist-scope parts --cookies "cookies.txt"
```

`--list-playlist` xuất JSON metadata, không tải media. `--playlist-items` dùng
STT1-based, không đảo thứ tự hoặc bỏ qua index sai. Mặc định download cũ vẫn
là một video. Playlist dùng yt-dlp Python đã bundle, không yêu cầu executable
`yt-dlp` trên PATH và không tự cài Deno/dependency trong luồng playlist.
Thành công toàn selection trảexit0; còn mục lỗi trảexit5, kết quả từng mục
được xuất JSON. Playlist flags riêng không âm thầm bật playlist mode.

## Implementation và giới hạn

- Core typed `PlaylistInfo`/`PlaylistEntry`/`PlaylistResult` ở
  `videocaptioner/core/playlist.py`; worker QThread giữ context/cancel.
- Bilibili BV dùng `window.__INITIAL_STATE__.videoData.ugc_season` để nhận ra
  collection, vì extractor video của phiên bản yt-dlp đang cài không trả合集.
  Chỉ dùng danh sách nhúng khi số entries khớp `ep_count`; nếu chỉ có một phần,
  gọi extractor collection có pagination của yt-dlp. Không báo partial là đủ.
- URL query theo dõi của BV được bỏ, giữ `p`; canonical URL dùng cho folder
  identity. Hỗ trợ tối đa2000 entries/lượt, vượt giới hạn báo lỗi trước tải.
- Mỗi selected entry phải trả một video. Không tự tải danh sách con ngoài
  selection. Folder chứa STT/tên/hash URL, filename yt-dlp có ID. `completed.json`
  bind file cuối sau postprocessing; đường dẫn trong receipt bị giới hạn trong
  thư mục entry. Không ghi key/cookies vào receipt.
- `post_hooks` nhận path sau merge; SHA tính sau tải. Cookies snapshot tự dọn;
  queue có socket timeout15s, retries2 và extractor retry1. Cancel không dùng
  QThread.terminate; supervisor giữ worker tới native finished.
- yt-dlp giữ các giới hạn truy cập/format của dịch vụ. Không bảo đảm mọi loại
  URL/playlist riêng tư/phân cấp đều tải được; bộ test không thay thế gate online.
- Tham khảo [yt-dlp video selection và playlist options](https://github.com/yt-dlp/yt-dlp#video-selection).

## Evidence

Audit `.tools/bilibili-playlist-20261002/`, baseline `feee402`. User cung cấp
BV1addWBtEem: nhận diện合集 **UE5干货分享**,31 entries đầy đủ, chưa tải toàn bộ31.
APIView ẩn danh trảHTTP412; đọc trang qua cookies hiện có thành công. Cookies
gốc được hash trước/sau và giữ nguyên; raw page nằm trong audit, không vào Git.

Tải thật entry1 gặp ngắt mạng sau retry hữu hạn, báo failed và giữ `.part`.
Lượt resume riêng tiếp tục từ file dở46.884.991bytes, hoàn tất trong20,657s.
FFprobe xác nhận AV1/3840×2160/video244,200s và AAC/audio244,204717s. Chạy lại
trả `existing` bằng SHA và không tải lại. Không ASR/dịch/TTS.

Regression gồm collection/parts/pagination fail, missing/private entry, caps,
selection membership, order, trùng tên, failed item/retry, cancel giữ file,
receipt path/corruption, cookies snapshot, real yt-dlp loopback byte parity và
resume không mạng, QThread/UI chọn tập/handoff/close. Focused45 pass; sau sửa
theme dialog, focused22 pass. Các lượt overlap không cộng dồn.
Native Qt worker đã đọc31 mục và kiểm file đã có; screenshot dark theme được
đọc lại. Full offline **2333 pass/5 skip/58 deselected**,exit0/203,35s;
Ruff toàn app/tests pass, Pyright0 errors/0 warnings, translations in sync.
Lượt focused đầu có1 lỗi assertion tên file giả định dư dấu gạch dưới; sửa
assertion theo phép sanitize và giữ log lỗi. Không coi lỗi đó là lỗi downloader.

Không đổi dependency/lockfile hoặc bản cài chính; không commit/push trong
lượt thêm tính năng này. Những nghiệm thu Auto timing trước vẫn độc lập.

## EXE thử nghiệm

`dist/VideoCaptioner-20261002-playlist/`, build bằng spec duy nhất của repo,
exit0/175,015s,6 WARNING cấp build/0 ERROR. EXE31.685.941bytes, timestamp
2026-10-02 19:27:24 +07:00,SHA256
`571d41b80f50ad650db45ac57c01ffef809e8936f2a5895409cfd1930ec30df4`.
Mở EXE tại thư mục đó, không chép riêng file executable.

Frozen CLI help/list/reuse đều exit0, không còn owned children; đọc31 mục thật
và1 SHA-hit,0 media downloads mới. Cookies E giữ nguyên.9 module runtime sửa
khớp bytecode source;99.315 file model/runtime khớp size manifest. Có FW +
large-v3/tiny, Qwen, OmniVoice, VieNeu/runtime, OCR-v6-medium; không có
Community-1 riêng, không download/install. GUI từ chính artifact sống20s,
đóngexit0 và không còn owned children.

Online gate **PARTIAL**: đã đọc31/tải-resume1 video thật, chưa tải toàn bộ31
hoặc kiểm các playlist cần quyền truy cập khác. GUI source có real worker/
native visual; GUI EXE mới kiểm startup, chưa thao tác trọn queue bằng người dùng.

## File thay đổi

- `videocaptioner/core/playlist.py` — core discovery, selection, queue và receipts.
- `videocaptioner/ui/thread/playlist_thread.py` — QThread/context/cancel.
- `videocaptioner/ui/components/playlist_dialog.py` — chọn tập/tải/tiếp tục/handoff.
- `videocaptioner/ui/view/task_creation_interface.py`, `home_interface.py`,
  `main_window.py`, `batch_process_interface.py` — điểm vào và hàng đợi Batch.
- `videocaptioner/cli/main.py`, `videocaptioner/cli/commands/download.py` — CLI opt-in.
- `VideoCaptioner.spec` — bundle modules mới.
- `tests/test_thread/test_playlist.py`, `tests/test_ui/test_playlist.py`,
  `tests/test_cli/test_playlist.py` — regression.
- `README.md`, `status.md`, tài liệu này — cách dùng, scope và evidence.

16 file trong allowlist; `closeout.json` ghi SHA và trạng thái Git/stash/bản E.

## Cập nhật bản chạy thật và bàn giao

Theo yêu cầu tiếp theo, đã cập nhật bản E bằng đúng artifact playlist:
602 file app khớp SHA, chỉ EXE và `base_library.zip` cần thay. Giữ tên EXE cũ
để shortcut tiếp tục hoạt động.1601 file dữ liệu/settings/cookies/voices/
manifest giữ nguyên; model không bị chép lại. CLI help trực tiếp tại E exit0.
Backup delta nằm ở `.tools/bilibili-playlist-publish-20261002/rollback-payload/`.

User yêu cầu mặc định deploy E cho các cập nhật app tiếp theo sau validation;
quy tắc được ghi đồng bộ trong AGENTS.md/CLAUDE.md. Lượt công bố này gồm18 file
(16 file tính năng và2 hướng dẫn); runtime code không thay đổi so với artifact
đã kiểm. Commit/remote/stashes và prompt next session nằm trong audit publish.
Không nâng gate tải cả31 hoặc native GUI queue chỉ vì đã deploy.
