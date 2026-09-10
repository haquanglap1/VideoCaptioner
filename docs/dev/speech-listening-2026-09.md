# Nghiệm thu câu đọc sau phân đoạn LLM — 2026-09-10

Tiếp tục tại worktree `VideoCaptioner-ASR-S3`, nhánh `codex/asr-s3-native`.
HEAD đầu phiên **`f03420c7e46c6e0f9f2c4da0f32c58a84254c722`** khớp upstream,
ref origin tại máy và `git ls-remote`. Worktree sạch; không làm ở master,
không commit/push. Kế thừa [bản phân đoạn](speech-segmentation-2026-09.md) và
[media đã hoàn tất](online-media-acceptance-2026-09.md).

## Kết quả và giới hạn

**Text/timing lossless, dùng lại WAV qua CLI frozen và media kiểm tra pass.
Chất lượng nghe vẫn chờ user duyệt.** Phân đoạn mới giữ đúng 6 cue của clip
30 giây; bản dịch, lời đọc và nhóm TTS không đổi. Vì vậy tái sử dụng 6 WAV,
không dịch lại hoặc sinh giọng mới. Video cuối giống từng byte với bản R2 cũ:
đây là bằng chứng giữ nguyên lời đọc/cache, không chứng minh nhịp đọc đã cải thiện.

## Phân đoạn và handoff

- Đọc SRT đã có của đoạn 00:10–00:40; không cắt video, nhận dạng lại, chạy
  forced alignment hoặc bỏ native/context guard. JSON nguồn kế thừa được nhập
  từ SRT câu, không chứa timestamp ASR theo từ.
- Source core `SubtitleSplitter`, gateway `https://api.videocaptioner.cn/v1`,
  model `gpt-5.6-terra`, timeout 300 s; giới hạn hiện có CJK 25 / ngôn ngữ cách
  từ 18. Cấu hình 2 thread nhưng clip chỉ có **1 batch, peak 1 request**.
- **2 request SDK thành công**, model trả về đúng tên đã chọn. Phản hồi đầu
  có nội dung ngoài định dạng nên validator từ chối (27,831 s); lượt feedback
  thứ hai hợp lệ (16,575 s). Tổng split **44,413 s**, giữ cả hai receipt.
  Không gọi phản hồi đầu là pass hoặc suy thành test dịch đa luồng mới.
- Đủ **6/6 cue** giữ nguyên chữ, thứ tự, dấu câu và start/end. Câu hỏi có dấu
  phẩy giữ thành một cue. Phần câu đầu kết thúc ở cue 2 có **29 đơn vị** theo
  `count_words`, vượt 25 nên được chia ở mệnh đề; bộ đếm hiện tại tính cả cụm
  punctuation. Các cue lần lượt 20/9/19/10/5/8 đơn vị. Không đổi bộ đếm hoặc
  giới hạn. Clip không có câu đúng sát ngưỡng, không tính thêm gate đó.
- Timing canonical: **2510–9110, 9250–13250, 13770–17710, 19550–21430,
  24090–25270, 27450–29990 ms**. Ranh giới input/output không đổi. Các đơn vị
  timing trung gian của split legacy vẫn là **ước lượng từ SRT**, được lưu
  riêng trong evidence; không gán nhãn timestamp ASR theo từ.
- Ghép lại đúng cue với bản dịch kế thừa, giữ cue ID của bản dịch. SRT TTS
  chỉ tiếng Việt; SRT hiển thị Việt trên/Trung dưới riêng. Hai SRT và TXT
  giống byte bản cũ. **0 request dịch mới**; bằng chứng dịch đa luồng trước
  đó vẫn giữ phạm vi riêng. Key từ đúng file user cấp chỉ vào `LLMCredentials`
  trong RAM, không vào settings/argv/env/evidence; scan key trên artifact pass.

## CLI frozen và media

Chạy chính EXE trong onedir `dist/VideoCaptioner-SpeechSegmentation-20260910/`,
SHA-256 giữ nguyên `3478a39a356781f9ffc15712a9f974c1ed241404888d1fb5fbd79cf99d95dddd`.
Cache phiên riêng chứa bản sao đã kiểm tra hash của 6 WAV/JSON cũ. Không build lại.

| Gate | Kết quả mới |
| --- | --- |
| Dubbing CLI frozen | Exit 0 / **18,626 s** gồm verify/load/cache/mix; **6 cache hit, 0 TTS attempt**, 6 fit, 0 failed/review/rewrite |
| Policy | Natural **1,00×**, max start delay **2500 ms**, `review`; thực tế 0 tăng tốc/0 dịch start, không cắt lời |
| Synthesis CLI frozen | Exit 0 / **0,530 s**, nhúng SRT song ngữ đã xong |
| Streams | Container/video **30,000 s**, H.264 1920×1080; AAC mono 24 kHz **29,994667 s**; mov_text **29,990 s** |
| Decode/extract | FFmpeg `-xerror` decode video/audio exit 0; extract subtitle exit 0, đúng cả 6 cặp Việt trên/Trung dưới và timing |
| Process | Dubbing quan sát 7 process con; kết thúc không còn child đã theo dõi. Inventory sau chạy không còn Python/app. Synthesis ngắn có giới hạn lấy mẫu process |

Không dùng thời gian cache replay làm thời gian sinh giọng. Harness dubbing dùng
TEMP riêng; không tính lượt này là nghiệm thu GPU lease giữa các app. Launcher
sau đó giữ TEMP mặc định. Pydub báo thiếu FFmpeg trên PATH của parent lúc import
helper; các bước media gọi binary đã cài bằng đường dẫn chỉ định và đều pass.

| Nhóm | Bắt đầu WAV | Kết thúc WAV | Kết thúc SRT | Khoảng trống tới nhóm sau |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2,510 s | 7,950 s | 9,110 s | 1,300 s |
| 2 | 9,250 s | 11,690 s | 13,250 s | 2,080 s |
| 3 | 13,770 s | 18,570 s | 17,710 s | 0,980 s |
| 4 | 19,550 s | 21,870 s | 21,430 s | 2,220 s |
| 5 | 24,090 s | 26,010 s | 25,270 s | 1,440 s |
| 6 | 27,450 s | 29,160 s | 29,990 s | 0,840 s tới hết video |

Các mốc là placement và duration WAV, không phải ranh giới âm vị. Nhóm 3/4/5
mượn khoảng lặng sau SRT **860/440/740 ms**, vẫn trước nhóm sau. Đầu video có
2,510 s trước WAV đầu. `silencedetect` −35 dB / tối thiểu 120 ms ghi khoảng
âm lượng thấp trong WAV: nhóm 1 khoảng 254/123/311 ms, nhóm 3 khoảng 279/252 ms,
nhóm 6 khoảng 204 ms. Đây không phải nghe xác nhận vị trí từng dấu phẩy hoặc
độ tự nhiên/ngữ điệu nghi vấn; không dùng ngưỡng âm lượng làm forced alignment.

## Duyệt nghe và nội dung còn mở

Đã cung cấp WAV phát trực tiếp trong cuộc trò chuyện và yêu cầu preview video
trong Codex (tool trả `queued`); không bật Computer Use hoặc mở player native.
Chưa có phản hồi nghe của user tại thời điểm ghi biên bản. Cần nghe nhóm 1/3/6
về dấu phẩy/nghi vấn, cùng các khoảng nghỉ giữa nhóm. Một số nội dung nhóm 2/3
cần đối chiếu ASR/tên riêng; sắc thái câu 6 cần duyệt bản dịch. Không tự sửa
nguồn hoặc wording để che vấn đề. Nếu user chỉ rõ câu cần sửa, dùng review/resume
và cache root của phiên, chỉ tạo lại nhóm đổi lời.

Không suy thành mọi giọng/ngôn ngữ/model hoặc toàn pipeline GUI đã pass. Không
lặp unit test/static/build/probe đã có vì không sửa source app. Không Prepare,
tải model, cài/sync dependency, inference bài giảng hoặc gọi provider ngoài phạm vi.

## Artifact và cleanup

Scratch duy nhất: `build/speech-listening-20260910/`.

- `output/`: split SRT/JSON, translated JSON, SRT TTS/hiển thị, TXT, kế hoạch
  `wuthering.vi-dubbing-plan.json`, video và `wuthering.vi-listen.wav`.
- Video `output/wuthering.vi-zh.mp4`: **14.630.229 byte**, SHA-256
  `4f998a6aa8b0fe03ac5e85a1f57006fee5f0253602e9711937d5204e45afcb5e`.
- `tts-cache/`: giữ 6 WAV/JSON để review/resume. **23 file được bảo vệ**
  (media/cache/settings kế thừa) giữ nguyên cả hash và mtime.
- `evidence.zip`: **59 entry / 41.692 byte**, kiểm CRC và SHA từng entry;
  SHA-256 `f3a884531476d2dc87533281a92255f31b44a5c853bcea4f040c714c87ce3c0f`.
- Kiểm duyệt tự động chặn xóa junction và xóa file scratch đã archive, chỉ trả
  `blocked by policy`. Đã **di chuyển có thể hoàn tác 5 junction** ra khỏi EXE
  vào `retired-junctions/`, giữ đích; EXE không còn link/cache/log thử. File phụ
  gốc khoảng **441 KB** còn giữ, `cleanup.json` ghi `cleanup_completed: false`.
  Không xóa qua liên kết hoặc đổi phương thức để vượt chặn. Không tạo source-copy,
  PyInstaller trung gian hay pytest temp trong phiên này.

File tracked sửa: biên bản này, `speech-segmentation-2026-09.md` và `status.md`.
Không sửa code/test, không commit/push. Gate cuối tài liệu dùng `git diff --check`.
