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

## CDN dự phòng cho các vùng byte bị kẹt — 2026-10-03

User còn9 mục chưa hoàn tất:4,5,6,11,15,18,21,22,26. Bộ file hiện có22
receipt hoàn tất; thư mục lồng của lượt trước đã được user xử lý. Bản E đúng
SHA của bản network đã phát hành, không phải đang chạy EXE cũ.

Audit `.tools/playlist-stuck-20261003/`: đọc64 KiB tại đúng offset của mỗi
file dở. Cả9 request tới `upos-hz-mirrorakam.akamaized.net` trả HTTP206 nhưng
body bị cắt; URL backup `upos-sz-mirrorcosov.bilivideo.com` do Bilibili cung
cấp trả đủ cùng vùng byte và Content-Range. Hai control ở đầu file4/26 qua
CDN chính vẫn thành công. Mục26 tái hiện đúng497 bytes read; đây là bằng chứng
lỗi theo vùng byte trên đường CDN chính, không chỉ là thiếu retry tổng quát.

Extractor yt-dlp đang cài chỉ giữ `baseUrl`, bỏ `backupUrl` của DASH. Core
playlist nay thu URL dự phòng từ cùng media record trong lúc extract, rồi
khôi phục method của extractor. Khi tải báo short read sau retry hữu hạn,
thử đúng một URL backup đã nhận từ server. Không tự thay hostname, đổi
format ID/chất lượng, hạ HTTPS xuống HTTP, bỏ kiểm certificate hoặc đổi
cookies. HTTP403 và lỗi khác không được coi là short read. Backup thất bại
thì giữ lỗi/file dở; không xoay vòng CDN hoặc retry vô hạn.

Mỗi lần process dùng bản sao format metadata vì yt-dlp sửa dict khi tải.
Giữ filename/format ID để tiếp tục `.part` cũ. Kiểm receipt/SHA, selection,
thứ tự và handoff Batch giữ contract trước. Direct media ngoài Bilibili vẫn
đi đường cũ; không đổi dependency hoặc file cấu hình user.

Regression38 pass và CLI160 pass (overlap); Ruff pass, Pyright0 errors/0
warnings, translations in sync. HTTP loopback thật kiểm primary short read
→ backup tiếp đúng byte, full SHA, reuse không mạng, backup cũng lỗi thì
dừng, HTTP403 không fallback, cancel và URL không hợp lệ/TLS downgrade.
Lượt đầu4 test lộ việc thêm `formats=[]` vào direct media; đã sửa để giữ
nguyên trường vắng mặt, giữ log PRE và chạy lại. Không chạy full suite.

Source mục4 tự chuyển CDN và đi từ310.272 lên66.148.638bytes; chạm budget
480s nên hủy ở483,063s và giữ partial, không gọi lượt đó hoàn tất. EXE mới
tiếp tục một bản sao partial này, tải/merge xong42,125s/exit0; lặp lại1,500s
SHA-hit. VideoAV1/3456×2160/210,033312s + audioAAC/210,048118s; full decode
exit0/stderr trống,75.501.149bytes, receipt SHA khớp. File user không đổi.

Artifact `dist/VideoCaptioner-20261003-playlist-backup/`: build exit0/266,547s,
6 WARNING/0 ERROR,31.688.036bytes,SHA256
`6aa8f578367fd0739fc19f9f2870565f6a4e0f96adb9fe192bf29967096b9a93`.
Core bytecode khớp source;99.315 model/runtime files khớp size manifest,
inventory như bản trước. GUI20s/exit0, không còn owned children. Không tải/cài
dependency/model. Đã kiểm9 vùng byte và hoàn tất mục4 trong audit, chưa tải
trọn cả9 video hoặc nâng gate ASR/dịch/TTS/nghe.

Đã deploy sau khi app E đóng:602 file app khớp SHA, chỉ EXE/base_library.zip
thay; backup tại audit `rollback-payload/`.1601 file dữ liệu/settings/cookies/
voices/manifest không đổi SHA, không chép lại models, giữ shortcut/tên EXE cũ.
Live CLI help exit0; GUI/media gates từ artifact cùng SHA. Không commit/push.
Khi tải tiếp, chọn thư mục cha chứa thư mục playlist để nhận lại các receipt
hiện có; app vẫn tự thêm một cấp tên playlist. CDN backup có thể chậm hơn.

## Nhớ link tải và trạng thái Batch tiếng Việt — 2026-10-03

`Download.LastUrl` lưu một URL HTTP(S) gần nhất khi nhập hoặc bắt đầu thao
tác tải/đọc danh sách. Tạo tác vụ và dialog playlist dùng chung lịch sử này;
mở lại điền link nhưng không tự discovery/download/ASR. Đường dẫn media local,
URL không hợp lệ hoặc URL chứa username/password không thay link đã lưu.
URL Bilibili được canonical hóa, bỏ query theo dõi và giữ phần P.

Batch hiển thị các trạng thái qua translator, còn logic chờ/chạy dùng enum
trong item data để không phụ thuộc tiếng Việt/Trung. Việt hóa menu, cảnh báo
và thông báo số tác vụ; hàng lỗi có màu đỏ, tooltip và nhấp đúp/menu **Chi
tiết lỗi**. Lỗi Faster-Whisper timing có giải thích Việt và nguyên văn chi
tiết kỹ thuật. Progress tới muộn không thay thế trạng thái lỗi/hoàn tất.

Ảnh user là lỗi ASR trong Batch. Log bản E ghi `MissingTimingError` với
`need_word_time_stamp=True`; TaskFactory hiện lấy cờ này từ `NeedSplit` khi
chạy tiếp pipeline Faster-Whisper. Đọc cache bằng SQLite read-only:17 kết
quả có190 cue chứa chữ, start=end (0 cue đảo chiều;181 cue tại biên cue trước).
Replay cả17 qua parser hiện tại tái hiện lỗi,0 inference/0 gọi dịch vụ mới.
Không đưa transcript/cookies vào Git. Đây là chẩn đoán timing; lượt thay đổi
UI không nới guard, sửa timestamp, bỏ chữ hoặc thay cấu hình ASR của user.

Audit `.tools/download-history-batch-20261003/`. UI/CLI/timing guards351 pass;
focused11 pass sau sửa Qt enum notation, Ruff pass, Pyright0 errors/0 warnings,
translations in sync. Giữ log lỗi type-check ban đầu13 errors đã sửa. Không
chạy lại full suite hoặc benchmark ASR; gate EXE/reopen có receipts riêng.

EXE `dist/VideoCaptioner-20261003-history/`: build exit0/209,203s,6 WARNING/
0 ERROR,31.690.540bytes,SHA256
`a56be0ef901916985a468ef02832a9ada71cf94e34897ed5a01a3c2b2bf2dea6`.
Năm module runtime khớp bytecode source, JSON Việt bundle khớp source,
99.315 model/runtime files khớp size manifest. Native EXE hai process riêng
cùng qua startup20s/exit0, không còn owned children. Gõ URL ở lượt1, đóng
app, lượt2 phục hồi đúng URL ở Tạo tác vụ/playlist, không bấm tải. Fixture
media không hợp lệ kiểm `Đang chờ` → `Thất bại` → nhấp đúp `Chi tiết lỗi`
với lý do Việt; lỗi xảy ra trước ASR, không gọi model/dịch vụ.

Đã backup delta và deploy E khi app đã đóng:602 file app khớp SHA, thay4
file (EXE/base_library.zip/hai JSON dịch),1606 file dữ liệu được bảo vệ không
đổi; không chép lại models. Live help exit0, shortcut giữ tên EXE cũ. Gate
GUI dùng artifact cùng SHA, không mở profile user để seed lịch sử. User
nhập link lần đầu sau cập nhật thì app lưu. Không commit/push.
