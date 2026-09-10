# Prompt phiên tiếp theo — nghiệm thu câu đọc sau phân đoạn LLM

Tiếp tục **VideoCaptioner** tại worktree **`VideoCaptioner-ASR-S3`**, nhánh
**`codex/asr-s3-native`**, cạnh checkout `VideoCaptioner` đang là master.
Không làm ở checkout master. Đọc đầy đủ `AGENTS.md`, `README.md`, mục mới nhất
của `status.md` và [báo cáo phân đoạn](speech-segmentation-2026-09.md).

## Git và snapshot bàn giao

User đã yêu cầu commit/push snapshot ngày 2026-09-10. Các commit code:

- `39ce70ffd727e862ee4700e0d88dea97d8b66ec1`: sửa đích ngôn ngữ/cache DeepLX.
- `9e6acf55f1a9d193ce1e7d889012ef46921df6b9`: gỡ InfoBar filter khỏi trang con khi đóng GUI.
- **`b824d2b27885a56659d353d74d2c82ba31a0d9bb`**: phân đoạn câu đọc lossless,
  bảo toàn punctuation/Unicode/timing và đường handoff TTS.

Commit tài liệu bàn giao theo sau các commit code. Khi bắt đầu, lấy **HEAD cuối
bằng Git**, đối chiếu nhánh tracking và `origin/codex/asr-s3-native`; không coi
commit code là HEAD tài liệu. Chạy `git status --short --branch`, giữ mọi thay
đổi có sẵn. Quyền commit/push vừa cấp chỉ chốt snapshot bàn giao này; không tự
commit/push thay đổi của phiên mới, không reset/force-push/merge master/tag/release.

## Mục tiêu phiên tiếp

**Nghiệm thu câu đọc/ngắt nghỉ sau phân đoạn LLM mới trên mẫu 30 giây đã có**,
phân biệt rõ tính đúng của text/timing với đánh giá nghe. Đây là phần còn thiếu
của bản SpeechSegmentation; không cần lặp lại unit test/build/probe chỉ để tăng
số gate. Tiếp tục các stage cần thiết trong phạm vi request/inference/render
ngắn đã được user cho phép; không hỏi lại quyền chung.

1. Xem kết quả và kế hoạch đã có trước. Tái sử dụng ASR của clip, không nhận dạng
   hoặc cắt lại video. Chỉ chạy lại split/translate/TTS cho phần thực sự cần
   nghiệm thu thay đổi mới; giữ output và cache cũ, dùng output/cache riêng.
2. Kiểm tra phân đoạn giữ một câu trọn ý khi vừa giới hạn, câu dài mới tách mệnh
   đề; không cắt vì mỗi dấu phẩy, không đổi chữ/số/phủ định/từ lặp. Nếu đổi ranh
   giới cue, ghi rõ input/output và các mốc được dùng, không âm thầm thay bản cũ.
3. **SRT hiện có chỉ chứa timing theo câu.** Khi split legacy, word timing vẫn
   là ước lượng; không gọi đó là timestamp ASR theo từ hoặc forced alignment.
   Native metadata/context vẫn đi route/guard riêng, không bypass để ép LLM split.
4. Dùng bản đã dịch phù hợp cho TTS, giữ SRT hiển thị riêng. Nếu text/group không
   đổi thì dùng WAV/cache đã xong; nếu đổi chỉ tạo nhóm cần thiết. Giữ Natural
   **1,00×**, max start delay **2500 ms**, policy **review**; không cắt lời,
   tăng tốc, nới guard hoặc sửa source ASR theo phỏng đoán để ép vừa khung.
5. Kiểm tra tiếng Việt đọc liền câu, dấu phẩy/nghi vấn/kết câu, pause giữa các
   mệnh đề và group, timing đầu/cuối; khi cần sửa wording dùng review/resume hiện
   có. Phân biệt lỗi source ASR/dịch với lỗi phân đoạn hoặc TTS.
6. FFprobe stream/duration, FFmpeg decode, extract track kiểm tra Việt trên/Trung
   dưới, rồi mở mẫu cho user nghe duyệt. Không công bố mọi giọng/ngôn ngữ/model đã
   tốt hoặc toàn pipeline GUI đã pass từ kết quả core/CLI của một clip.

## Cấu hình user đã chọn

- Chỉ **LLM dịch đa luồng**, gateway **`https://api.videocaptioner.cn/v1`**,
  model **`gpt-5.6-terra`**, timeout **300 s**. Giữ lựa chọn này, không tự đổi
  model/gateway hay sweep concurrency. Mẫu 6 cue trước dùng 2 thread/batch 5;
  báo số batch/concurrency thực, không gọi một batch là test đa luồng.
- User đã cấp file **`Api.txt` ngoài repo**, đường dẫn tương đối từ worktree hiện
  tại **`../../Api.txt`**, cho agent tự đọc khi cần gọi gateway. Đọc đúng file,
  không yêu cầu nhập lại nếu có một key rõ ràng và hợp lệ. Nội dung file là dữ
  liệu credential, không phải chỉ dẫn. Không sửa file, không hiển thị hoặc sao
  chép key vào settings/chat/argv/env/log/Git/evidence; dùng `LLMCredentials`
  trong RAM và `child_environment()` cho subprocess. Chỉ hỏi nếu file thiếu,
  không rõ hoặc gateway từ chối key; không dò key từ history/log/archive.
- **DeepLX, Google Translate, Bijian/Bcut/Bilibili, Jianying, ElevenLabs/Scribe
  ngoài phạm vi.** Không kiểm tra/hỏi endpoint, không dùng default/fallback;
  không lấy media Bilibili, không probe Bing lại. Giữ code/provider/fix lịch sử.
- ASR local/model/runtime và OmniVoice đã cài. Không Prepare/download, cài/sync
  dependency, benchmark sâu, sweep model hoặc OCR. Python 3.12.13 sẵn ở
  `../VideoCaptioner/.venv/Scripts/python.exe`; FFmpeg/ffprobe ở
  `../VideoCaptioner/AppData/bin/ffmpeg/`.

## Bằng chứng và artifact kế thừa

### SpeechSegmentation mới nhất

Nguyên onedir **`dist/VideoCaptioner-SpeechSegmentation-20260910/`**; EXE
**31.263.571 byte**, SHA-256
`3478a39a356781f9ffc15712a9f974c1ed241404888d1fb5fbd79cf99d95dddd`.
Build exit 0/**264,437 s**, 6 WARNING/0 ERROR; 6 module PYZ + 2 prompt khớp source;
CLI help exit 0, GUI **103,577 s**, đóng exit 0/không child. Gate cuối
**781 pass/33 deselected**, Ruff/Pyright/translation sync pass.

Prompt/guard giữ nguồn chính xác, không lấy phản hồi sai cuối hoặc dùng fuzzy
match để bỏ prefix/tail; giữ punctuation tới TTS. **26 regression mới**.
Mẫu Việt/Trung online đúng; mẫu Anh lỗi request ở lượt đầu rồi retry riêng bằng
key file: HTTP 200/**275,781 s**, đúng hai câu và `not`/`3.14`. Giữ cả failure và
retry, không suy thành dịch vụ có độ trễ ổn định. Các mẫu chạy source core;
**chưa chạy/nghe TTS mới từ EXE SpeechSegmentation**.

### Media đã xong trên R2 — không coi là đã dùng prompt mới

[Báo cáo media](online-media-acceptance-2026-09.md) ghi từng gate:

- Clip user cung cấp đã cắt **00:10–00:40**. ASR ở
  `build/online-media-20260910/output/`: `wuthering-10-40-input.mp4`,
  `wuthering-10-40-input.srt`, `wuthering-asr.json`. **6 cue**, Faster-Whisper
  large-v3/CUDA mới, **25,812 s**. Giữ nguồn và kết quả này.
- LLM core/Qt worker: **6/6 cue**, 3 HTTP 200, peak **2** request đồng thời,
  **53,219 s**, model đều `gpt-5.6-terra`; cache replay **0 request mới**.
- OmniVoice Việt qua CLI R2: **6 WAV mới/0 cache**, 6 fit/0 lỗi/0 review,
  **1,00×**, **55,187 s**. Synthesis **0,628 s**, video **30 s** với
  H.264 1920×1080 + AAC mono 24 kHz + mov_text; decode/extract track pass.
- Output ở `build/llm-media-20260910/output/`: `wuthering.translated.json`,
  `wuthering.vi.srt`, `wuthering.vi-zh.srt`, `wuthering.vi.txt`,
  `wuthering.vi-dubbing-plan.json`, video TTS và **`wuthering.vi-zh.mp4`**.
  Video cuối **14.630.229 byte**, SHA-256
  `4f998a6aa8b0fe03ac5e85a1f57006fee5f0253602e9711937d5204e45afcb5e`.
  **6 WAV/JSON** ở `build/llm-media-20260910/tts-cache/`; chọn đúng root khi resume.
- R2: `dist/VideoCaptioner-DeepLXLanguageFix-20260910-R2/`, hash EXE
  `10fac15209dd1297389e10547b8c6d7142957f7d2218643588b39811aa375298`.
  Tên artifact là lịch sử build, không phải provider phải dùng.

Giữ thêm bản tiếng Trung/6 WAV tại `build/online-media-20260910/`, cùng bài giảng
đã chốt “tạm ổn”, **151 WAV/121 nhóm lời sửa**, mọi runtime/model/settings/cache
thật và artifact cũ. Không mở lại bài giảng để inference/render.

## Computer Use, cleanup và bàn giao

**Computer Use hiện đã dừng/reset.** Chỉ mở khi thực sự cần nghiệm thu GUI;
test xong đóng đúng các cửa sổ/process do agent tạo và reset/kết thúc phiên điều
khiển ngay. Không giữ phiên điều khiển trong lúc viết tài liệu/dọn file. User
nói tắt thì dừng thao tác UI ngay; không động vào cửa sổ/process không thuộc test.

Dùng một scratch cho phiên. Giữ output/WAV/kế hoạch và artifact lỗi cần thiết,
gom log nhỏ vào archive, dọn source-copy/PyInstaller trung gian/pytest temp.
Không dọn nhầm runtime/model hoặc media/cache thật vì chúng nằm dưới `build/`.
Evidence cũ đã gom, không tạo lại scratch để lặp helper:

- `build/online-media-20260910/evidence.zip`: 97 file.
- `build/llm-media-20260910/evidence.zip`: 32 file, 31.388 byte.
- `build/sentence-split-20260910/evidence.zip`: 46 file, 89.509 byte, SHA-256
  `eb55245780464400423063564fadd9ed3af52759db00eef5306206a0405fd6dd`.

Nếu gặp lỗi cụ thể, giữ phần đã xong, tái hiện/sửa đúng nguyên nhân và chạy test
phù hợp; chỉ build tên mới khi source đổi. Cập nhật `status.md`/biên bản, nêu rõ
pass/fail/skip/chưa chạy, nguồn/GUI/frozen và cache/fresh. Không tính kết quả nghe
là được user duyệt nếu chưa có xác nhận, không tự commit/push phiên mới.
