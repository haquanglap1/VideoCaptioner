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

## Kiểm native GUI sau bàn giao

Audit `.tools/playlist-native-queue-20261002/`, baseline `8ed4187`. Kiểm SHA
và shortcut bản E trước probe. Dùng EXE cùng SHA nêu trên với AppData test
riêng và runtime/model hiện có; không sửa code hoặc build/deploy lại.

Thao tác trực tiếp qua native Windows UI đã kiểm đường từ **Tạo tác vụ** đến
dialog: đọc đúng31 mục Bilibili, bỏ chọn toàn bộ, chặn tải khi selection rỗng,
chọn riêng mục1 và trả `Đã có (SHA khớp)`. **Đưa video đã tải sang Xử lý hàng
loạt** đưa đúng file vào Batch ở trạng thái chờ. Không tải thêm video Bilibili
hoặc bắt đầu ASR/dịch/TTS.

Nút **Dừng tải** được kiểm riêng bằng HTTP loopback có giới hạn tốc độ, phục
vụ lại video audit đã có qua hai URL. Dừng giữ `.part`8.856.702bytes, mục2
chưa được tải và handoff bị khóa. Đóng/mở dialog rồi **Tiếp tục** gửi
`Range: bytes=8856702-`; cả hai file hoàn tất, size/SHA khớp nguồn. Tắt server
rồi bấm tải lại vẫn nhận2 SHA-hit. Handoff nối hai file theo đúng thứ tự sau
file Bilibili đã có trong Batch; cả3 hàng chờ, chưa xử lý.

`validation.json` ghi gate và giới hạn; accessibility snapshots và
`batch-final.png` giữ evidence native.1605 file được bảo vệ giữ nguyên SHA,
bao gồm1601 file dữ liệu bản E trong inventory trước, EXE, settings source và
media/receipt gốc. GUI test/server đã đóng, không còn owned process. Windows
observer không trả exit code GUI trong lượt này; không gọi teardown exit0.

Native EXE discovery/selection/reuse/handoff và loopback cancel/resume PASS
trong phạm vi đã đo. Online vẫn **PARTIAL**: chưa kiểm nút Dừng giữa tải
Bilibili qua Internet hoặc tải cả31, playlist riêng tư/quyền khác. Loopback
không thay gate đó. Không chạy lại full suite/build hay thay trạng thái
ASR/LLM/TTS/nghe/CI vì runtime code không đổi.

## Khắc phục lỗi kết nối khi tải nhiều video

User báo1 video hoàn tất/30 lỗi. Kiểm bản E đúng SHA đã phát hành và thư mục
tải có1 media hoàn tất cùng30 `.part`. Lỗi thực tế gồm short read, server đóng
kết nối và SSL EOF; không đủ bằng chứng để quy tất cả thành lỗi cookies/quyền.

Tải media Bilibili dùng HTTP Range tối đa1 MiB/request và ngân sách10 retries
hữu hạn của yt-dlp cho mỗi stream. Discovery vẫn giữ2 retries; các dịch vụ
khác giữ policy cũ. Không giảm chất lượng, thay cookies/gateway, tắt kiểm tra
certificate hoặc bỏ qua đoạn lỗi. File dở tiếp tục được giữ để resume; chỉ
ghi `completed.json` sau khi media hoàn tất và SHA đã tính xong. Dừng vẫn
được kiểm ở progress/network boundaries, không phải chờ dùng hết retries.

Sửa riêng phân loại lỗi: chỉ nhận `HTTP Error 403/412/429` hoặc `HTTP 403/412/429`
thật trong thông báo, không tìm các chữ số đó trong số byte tải dở. Trước sửa,
hai regression short-read bị báo nhầm hạn chế truy cập; sau sửa giữ đúng lỗi.

Audit `.tools/playlist-network-20261002/`: chỉ chia Range1 MiB với2 retries
vẫn lỗi ở mục2; CDN dự phòng chưa hoàn tất khi chạm budget240s và đã hủy.
Không đưa lựa chọn CDN dự phòng vào bản sửa. Policy cuối tải/merge mục2 từ
bản sao `.part` thành công85,797s: AV1/3456×2160/210,200s và AAC/210,210658s,
full decode exit0/stderr trống. Không sửa media/receipt/cookies/settings thật.

Regression HTTP loopback thực sự ngắt kết nối bốn lần: phục hồi đủ byte/SHA,
resume không mất prefix, lặp lại không mạng. Server lỗi liên tục dừng sau
11 attempts; hủy dừng ở request đầu; dịch vụ khác vẫn dừng sau3 attempts.
Focused32 pass, CLI160 pass (có overlap); Ruff pass với warning cache ACL,
Pyright0 errors/0 warnings, translations in sync. Không chạy lại full suite
vì thay đổi chỉ ở policy tải và phân loại lỗi; EXE/deploy có receipts riêng.

EXE `dist/VideoCaptioner-20261002-playlist-network/`: build exit0/208,344s,
6 WARNING/0 ERROR,31.686.057bytes,SHA256
`34119fa4b767d3af57cbdfd883a95edd8f398cbcb409b4220c5c29a3a89ec590`.
Core bytecode khớp source;99.315 file model/runtime khớp size manifest,
inventory giữ nguyên, không tải/cài thêm. GUI startup20s/exit0, không còn
owned children. Mục3 từ bản sao `.part` tải/merge bằng EXE exit0/177,312s;
AV1/3456×2160/206,966625s + AAC/206,983084s, full decode exit0/stderr trống.
Lặp lại exit0/1,484s, SHA-hit; cookies giữ nguyên. Không tự chạy toàn31.

Sau khi bản E đã đóng và các gate trên đạt, đã backup delta rồi cập nhật
602 file app khớp SHA; chỉ EXE và `base_library.zip` thay. Giữ tên EXE cũ
cho shortcut;1601 file dữ liệu/settings/cookies/voices/manifest giữ nguyên,
không chép lại model. CLI help trực tiếp tại E exit0; GUI/media gates kế thừa
artifact cùng SHA. Backup ở audit `rollback-payload/`. Không commit/push.

Mở lại app, đọc cùng danh sách và chọn cùng thư mục đích, rồi bấm **Tải /
Tiếp tục các tập đã chọn**. Video hoàn tất được kiểm SHA, các `.part` dùng
lại theo hỗ trợ Range của server. Hai lượt media mới chỉ ghi vào audit;
file tải của user được giữ nguyên. Đây là cải thiện khả năng phục hồi kết
nối, không bảo đảm server luôn sẵn sàng hoặc toàn31 đã được nghiệm thu.
