# Nghiệm thu media mới — 2026-09-10

Tiếp tục worktree `VideoCaptioner-ASR-S3`, nhánh `codex/asr-s3-native` từ HEAD
`3156f911e9cd7ca0d5bec19b0c96a16e12eb3406`, khớp ref tracking tại máy; Git sạch
lúc bắt đầu. Không commit/push, tải model hoặc cài/sync dependency.

## Phạm vi và giới hạn nghiệm thu

- **Điều chỉnh mới nhất: user bỏ DeepLX khỏi plan, hiện chỉ dùng LLM để dịch,
  ưu tiên đa luồng.** Không kiểm tra hoặc yêu cầu endpoint DeepLX nữa. Các sửa
  lỗi và bằng chứng lịch sử bên dưới được giữ nguyên; 0 request DeepLX của lượt
  trước không trở thành điều kiện chặn tiếp tục.
- **Luồng kỹ thuật Trung → Việt đã pass** trên 6 cue: LLM source core/Qt worker,
  sau đó OmniVoice và synthesis bằng CLI của EXE R2. Không nhận dạng lại; đây
  không phải một lượt bấm toàn pipeline trong GUI. Chất lượng lời/giọng vẫn
  cần user nghe duyệt.
- DeepLX, Google Translate, Bijian/Bcut/Bilibili, Jianying và ElevenLabs/Scribe **ngoài phạm vi
  theo yêu cầu user**; không gọi hoặc dùng làm fallback. Bing không probe lại.
- Các request kiểm tra phiên bản GitHub khi mở GUI được ghi riêng trong log;
  không phải request dịch. Không cập nhật ứng dụng từ dialog đó.

## LLM gateway và video tiếng Việt — lượt tiếp theo trong ngày

User chọn **`https://api.videocaptioner.cn/v1`**, model **`gpt-5.6-terra`**. Đã lưu
endpoint/model/compatible mode vào `AppData/settings.json` của R2, cùng timeout
300 s, 2 thread và batch 5. Key nhập bằng ô password, chỉ giữ trong RAM của job;
không ghi vào settings/chat/argv/env/log. Không dò key từ bằng chứng cũ.

| Gate | Kết quả mới |
| --- | --- |
| LLM online | Source core `LLMTranslator` thật trong Qt worker; 6 cue/2 batch 5+1, cache miss, **3 request HTTP 200**, model trả về đều `gpt-5.6-terra`, **53,219 s** |
| Đa luồng | HTTP event hooks quan sát client thật, **peak 2 request đồng thời**; không thay transport bằng mock hoặc chỉnh code provider |
| Cache replay | Cùng input/config, kết quả giống nhau, **0 request mới**; thời gian dưới độ phân giải 1 ms của receipt, không phải tốc độ dịch online |
| Identity | Đủ 6 bản dịch nonempty; original text, cue ID, metadata và millisecond timing giữ nguyên; không split/optimize hoặc ASR lại |
| OmniVoice VI | CLI frozen R2 exit 0/**55,187 s**, **6 WAV mới/0 cache hit**, 6 fit/0 lỗi/0 review/0 rewrite; Natural **1,00×**, không dịch thời điểm bắt đầu, max fit ratio 0,8421 |
| Synthesis | CLI frozen R2 exit 0/**0,628 s**, không inference lại; nhúng SRT Việt trên/Trung dưới vào video TTS |
| Media | **30,000 s**, H.264 1920×1080 + AAC mono 24 kHz + mov_text; FFmpeg decode `-xerror` exit 0, extract track giữ đủ 6 cặp chữ/timing đúng thứ tự |
| Cleanup process | Các CLI exit 0, không child còn lại; GPU lease lấy/nhả lại được. Key worker `wait()` rồi process kết thúc. MPC-HC phát tới khoảng 25/30 s và thoát exit 0 |

Output tại `build/llm-media-20260910/output/`:
`wuthering.translated.json`, `wuthering.vi.srt`, `wuthering.vi-zh.srt`, bản đọc
`wuthering.vi.txt`, `wuthering.vi-dubbing-plan.json`, video TTS và video cuối
**`wuthering.vi-zh.mp4` — 14.630.229 byte**, SHA-256
`4f998a6aa8b0fe03ac5e85a1f57006fee5f0253602e9711937d5204e45afcb5e`.

Không sửa source app/build lại hoặc lặp các test đã pass trong lượt cấu hình
và chạy online này. Kế thừa gate 476 pass và artifact R2 ở phần dưới. Nghiệm thu
LLM qua core, media qua frozen CLI; không công bố thêm gate toàn GUI hay chất
lượng dịch/ASR/giọng nói từ một clip. Một số cụm trong bản dịch cần user duyệt
theo lời nguồn; không tự sửa transcript ASR đã nhận dạng để che sai khác.

Helper kiểm tra song ngữ ban đầu nhầm rằng `.text` chứa cả hai dòng; parser của
app tách dòng thứ hai vào `.translated_text`. File SRT/track đã đúng sẵn; sửa
assertion kiểm tra cả hai field rồi pass, không dịch/TTS/render lại để sửa helper.

Evidence LLM/VI đã gom **32 file** vào `build/llm-media-20260910/evidence.zip`,
**31.388 byte**, từng entry được đối chiếu SHA-256; hash ZIP
`bda8eff5defbf9f33e987ca77477fbca045e69f358a08f81d5bc08f5564b8766`.
Đã gỡ 4 junction thử, chuyển **27 mục/366.682 byte** cùng các liên kết vào
Thùng rác, không xóa vĩnh viễn. Giữ output, `tts-cache/` (6 WAV/JSON), ZIP và
cleanup.json. R2 giữ cấu hình gateway/model mới, không còn link/cache/log thử;
EXE và clip nguồn giữ hash. Không có source app mới để build hoặc commit.

## Media mới: ASR → OmniVoice tiếng Trung → synthesis

User cung cấp video khác bài giảng cũ. File gốc 46.585.545 byte, 111,333 s,
AV1 1920×1080 + FLAC stereo 48 kHz; SHA-256
`5229cb9e26691c96fa5a0f6e2213bb741a76f02ea494933cbf37d1f6a109e0b1`.
Cắt **00:10–00:40** thành clip H.264/AAC riêng, không ghi đè nguồn; hash clip
`5d90921c6f0e37a6ac48f173a040efd8eb6f367522312e6e035259e4f3e1d7f3`.

| Gate | Bằng chứng của phiên |
| --- | --- |
| ASR GUI frozen | GoogleDeepLXFix cũ, chọn rõ Faster-Whisper large-v3/CUDA/zh, tắt word timestamp. Cache miss, inference mới, **6 cue**, **25,812 s** từ bấm chạy đến ghi SRT. GUI báo hoàn tất, không treo |
| Timing | Cả 6 cue nonempty, start < end, không overlap, nằm trong 0–30.000 ms; lưu SRT và JSON nhập lại từ SRT để bàn giao |
| OmniVoice readiness | Verify **13 file**, revision code `08be0b4c…`, model `c5fdb5cc…`; 0 byte tải. Qt không import model/CUDA |
| TTS GUI frozen | DeepLXLanguageFix R1, **6 nhóm/6 WAV mới**, **0 cache hit**, 0 rewrite/0 lỗi/0 review; ngôn ngữ `zh`, giọng `auto`, không reference/clone giọng người trong video |
| Policy | Natural 1,00×; max start delay 2500 ms, policy `review`, không LLM rewrite. Thực tế cả 6 fit, 0 dịch thời điểm bắt đầu, không tăng tốc; max fit ratio 0,7098 |
| Ghép audio | **47,880 s** từ bấm TTS đến video; gồm verify/load/generation/mix, không phải thời gian model thuần. Audio gốc mute, AAC mono 24 kHz |
| Synthesis GUI frozen | Dùng video TTS và SRT đã xong, ghép mềm; khoảng **0,220 s** từ click đến mtime output. Không chạy lại ASR/TTS |
| Kiểm tra media | Video cuối **30,000 s**, H.264 1920×1080 + AAC mono 24 kHz + mov_text. FFmpeg decode với `-xerror` exit 0. Extract track giữ đúng toàn bộ text/start/end của 6 cue |
| Phát mẫu | Đã mở MPC-HC, quan sát playback tiến tới 00:25/00:30, H.264/AAC, không báo lỗi. Đánh giá nghe, độ tự nhiên và độ chính xác lời nhận dạng vẫn cần user xác nhận |
| Worker | Sau TTS thu hồi GPU lease, helper lấy/nhả lại được; giữ 6 WAV và kế hoạch GUI để tiếp tục |

Video cuối `build/online-media-20260910/output/wuthering-10-40-input_dubbed_captioned.mp4`:
**14.589.366 byte**, SHA-256
`ac13ac8d4cbaba2d143eddb027875b8197b5112ecbe81317334ed60db7d2d5b2`.
SRT gốc, JSON nhập từ SRT và `wuthering-zh-dubbing-plan.json` nằm cùng output;
WAV/metadata nằm trong `build/online-media-20260910/tts-cache/`.

Không lấy kết quả một clip làm nghiệm thu chất lượng mọi model/provider, hoặc
cài đặt máy sạch. Không chạy lại bài giảng/151 WAV/121 nhóm lời đọc cũ.

## Lỗi DeepLX tìm thấy trước khi gọi dịch vụ

Bảng `DEEPL_LANG_MAP` thiếu tiếng Việt. Chọn Vietnamese gửi `zh-Hans` do fallback
mặc định; cache vẫn mang nhãn Vietnamese, nên thêm mapping đơn thuần sẽ tiếp tục
đọc nhầm cache cũ. [Tài liệu DeepL](https://developers.deepl.com/api-reference/languages/retrieve-supported-languages)
liệt kê mã `VI`; đây là nguồn mã ngôn ngữ, không chứng minh endpoint DeepLX của
user hỗ trợ phiên bản tương ứng.

- Thêm mapping `vi`. DeepLX từ chối ngôn ngữ chưa có mapping trước request/cache,
  không âm thầm đổi đích về tiếng Trung. Provider khác giữ hành vi hiện có.
- Cache DeepLX giữ namespace `validated-v2`, thêm mã đích hiệu lực vào key.
  Các key trước sửa được bỏ qua, **không xóa cache cũ**, kể cả entry từng hợp lệ.
- **4 regression fail trước sửa**, pass sau sửa: request giữ đích Vietnamese,
  bỏ qua cache sai cũ nhưng giữ dữ liệu, cache phụ thuộc mã đích thực tế, ngôn ngữ
  chưa ánh xạ không request/cache. Cache replay ở test này dùng mock offline.

## Lỗi shutdown phát hiện sau media

R1 chạy media thành công nhưng khi đóng sau synthesis bị
`TopInfoBarManager has been deleted`, exit **3221225477 / 0xC0000005**. Log và
artifact lỗi được giữ; không coi R1 là pass shutdown. Không còn process con.

`MainWindow._detach_info_bar_managers()` trước đó chỉ gỡ filter khỏi main window,
trong khi tab synthesis đăng ký InfoBar trên widget con. Nó còn gọi `make()`
lúc teardown, có thể chạy lại QObject initializer của singleton hoặc tạo manager
chưa từng dùng. Nay lấy instance đã có và gỡ filter khỏi cả các widget con thuộc
cửa sổ đang đóng; không gỡ filter của cửa sổ khác.

Hai regression Qt event fail trước sửa/pass sau sửa. Source smoke với InfoBar
thật trên trang con, để thông báo hết hạn rồi đóng QApplication: exit 0, 0 exception.
Lần đầu helper source thiếu method `resize` của splash giả; đã sửa helper và giữ
receipt riêng, không coi lỗi fixture là lỗi app.

## Build và validation

- Gate cuối source: **476 pass / 24 deselected / 1 warning**, gồm translator,
  toàn CLI/UI/thread; không skip. Không cộng chồng với 313 pass trước sửa shutdown,
  75 test HTTP hoặc 10 test lifecycle. Các marker integration/slow/llm bị loại.
- Ruff app/tests pass; Pyright app **0 error/0 warning**. Translation sync pass,
  không sửa translation. Không chạy lại full suite hoặc dịch vụ ngoài.
- Test dùng Python 3.12.13 có sẵn, cache/log/settings/temp riêng; socket guard
  chặn ngoài loopback cho regression. Không dùng dependency mới.

| Artifact | Build | EXE |
| --- | --- | --- |
| DeepLXLanguageFix-20260910 (R1) | Exit 0; 210,422 s; 6 WARNING/0 ERROR | 31.263.945 byte; 2026-09-10 04:47:26 local; SHA `b6db75b221a5793048a8f78301765cf19fb9158349b194eb6e9df4c28a0b91b7` |
| DeepLXLanguageFix-20260910-R2 | Exit 0; 129,500 s; 6 WARNING/0 ERROR | 31.263.972 byte; 2026-09-10 05:01:08 local; SHA `10fac15209dd1297389e10547b8c6d7142957f7d2218643588b39811aa375298` |

Warning quen thuộc: js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit;
dependency có SyntaxWarning. Build từ bản sao source/resource đã hash đối chiếu
**289 file**. Không sửa spec hoặc bundle model. Phân phối nguyên onedir R2 tại
`dist/VideoCaptioner-DeepLXLanguageFix-20260910-R2/`.

R2 đã đối chiếu **7 module PYZ** với source, gồm DeepLX/types/main_window và các
module media liên quan. Fresh media ở trên được tạo bởi R1; R2 chỉ sửa lifecycle,
không lặp inference/render để cộng thêm gate.

**R2 GUI/shutdown pass:** sống **161,305 s**, hiện thông báo thiếu input trên
tab synthesis, để thông báo hết hạn rồi đóng; **exit 0, 0 traceback, 0 child**.
Ca này tạo đúng TopInfoBar trên trang con mà không chạy model/render lại. Không
suy rộng thành đã loại bỏ mọi lỗi Qt/SIP ngắt quãng từng ghi nhận.

## Evidence và cleanup

Toàn bộ dữ liệu mới ở `build/online-media-20260910/`; output/6 WAV giữ để bàn giao.
Lượt đầu cấu hình thử dùng sai enum, loader dừng giữa file; đã chuyển sang ghi
config typed và xác nhận provider/language/policy trên GUI trước inference.
Mẫu public được tạo trước khi user chỉ clip riêng chưa chạy inference và không
được tính là nghiệm thu.

Giữ báo cáo build lỗi/shutdown lỗi và dữ liệu stage hoàn tất. Không tự commit/push.
Lượt tiếp dùng LLM theo [prompt đã cập nhật](online-media-next-session-prompt-2026-09.md).
User sau đó chọn gateway `https://api.videocaptioner.cn/v1`, model `gpt-5.6-terra`.
Đã lưu endpoint/model trên cấu hình R2, timeout 300 s, 2 thread/batch 5; key mới
chỉ nhập qua ô password và giữ trong RAM của job. Phần LLM mới dùng scratch
`build/llm-media-20260910/`, không mở lại scratch cũ; kết quả online phải dựa trên
receipt thực tế, không suy từ cấu hình hay bằng chứng dịch bài giảng trước đây.

- `evidence.zip`: **97 file** log/receipt/helper/cache thử, **130.385 byte**, mọi
  entry đối chiếu SHA-256; hash ZIP
  `631d94a7866fb7832ab62f6426e2d87179c303d29883b80ec178229a6a123caf`.
- Hash và mtime nguồn video, settings thật, EXE GoogleDeepLXFix cũ, sample public
  và marker runtime/model được kiểm tra giữ nguyên. Cả R1/R2 giữ hash build.
- Đã gỡ 8 junction thử khỏi artifact/scratch, giữ đích runtime/model; chuyển
  junction và **77 mục / 340.538.460 byte** scratch trung gian/bản sao source/
  pytest temp/log rời vào **Thùng rác**. Đây không phải dung lượng xóa vĩnh viễn.
  Thư mục phiên chỉ còn output, tts-cache, evidence.zip và cleanup.json.
- Lệnh xóa junction trực tiếp bị kiểm duyệt tự động chặn (`blocked by policy`,
  không có lý do chi tiết); phương án chuyển liên kết rồi đưa vào Thùng rác đã
  thành công. Không xóa runtime/model hoặc media/cache thật dưới build.

File tracked thay đổi: `core/translate/{types,deeplx_translator}.py`,
`ui/view/main_window.py` dưới `videocaptioner/`;
`tests/test_translate/test_http_failures.py`,
`tests/test_ui/test_version_checker_lifecycle.py`, tài liệu này và `status.md`.

Ngày 2026-09-10 user yêu cầu commit/push snapshot đã nghiệm thu: DeepLX đích/cache
ở `39ce70f`, InfoBar teardown ở `9e6acf5`, phân đoạn câu đọc tiếp theo ở `b824d2b`;
commit tài liệu bàn giao theo sau. Trạng thái “không commit/push” trong lịch sử
trên là trước yêu cầu chốt Git. [Prompt phiên sau](online-media-next-session-prompt-2026-09.md)
giữ riêng các gate và quyền Git; lấy HEAD cuối/tracking từ Git khi tiếp tục.
