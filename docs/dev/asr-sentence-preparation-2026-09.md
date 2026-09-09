# Qwen sentence timing, model preparation và file dài — 2026-09-09

Checkout ASR-S3, nhánh `codex/asr-s3-native`, nền bàn giao `d2dc518`. Thay đổi
chưa commit/push. **Qwen SRT chưa đạt trên mẫu user; ASR sản phẩm chưa nghiệm thu.
OCR vẫn dừng.** Không đổi engine mặc định, checkpoint, dtype, bridge, dependency
Qt/lock hoặc dịch gateway/gpt-5.6-terra. Không gọi API ASR/dịch hoặc tải model mới.

Evidence mới: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/sentence-20260909/`.
Giữ benchmark common-28 và artifact TimingGuard cũ; không chạy lại nguyên corpus.

## Hành vi sản phẩm

**Timing câu:** `qwen-sentence-anchors-v1` áp dụng khi không yêu cầu word timestamp.
Chia text theo dấu câu và giới hạn 40 ký tự tại ranh giới token, trước khi xét giờ.
Start/end cue lấy nguyên start token đầu/end token cuối; hai token biên phải có
interval dương, nằm trong media, có năng lượng âm thanh. Cue không overlap và không
dài quá 15 s. Mọi giá trị nội bộ phải là ms canonical và nằm trong biên cue. Lỗi
zero/overlap/reversed của word nội bộ không được xuất thành word timing và không
tự chặn cue. Không chọn min/max, clamp, sửa raw, bỏ chữ hay tự gộp lại câu lỗi.

Review giữ raw, text, token ID, audio identity và policy; save/load/resume không
đổi text hoặc ID. Word mode giữ policy strict cũ. Cache raw alignment được tách
khỏi cache kết quả đã validate và luôn phải qua kiểm tra lại trước xuất phụ đề.
Biên lỗi vẫn trả TXT/review; pipeline cần SRT không được tiếp tục bằng TXT.
Kiểm tra RMS chỉ loại span rơi vào im lặng, **không chứng minh alignment đúng từ
hoặc đúng câu**. Chưa có nghiệm thu biên câu độc lập trên audio cho policy mới.

**Chuẩn bị model:** core dùng chung GUI/CLI tìm bản đã cài, verify hash rồi dùng lại.
Thiếu model thì chuẩn bị đúng model đang chọn trong thư mục managed riêng bên cạnh
root đã chọn; không ghi đè runtime cũ. TXT không chuẩn bị aligner/Community-1.
Runtime Python 3.12 dùng recipe lock cũ, có OS lock theo candidate, ownership marker,
progress MiB, hủy subprocess và giữ tải dở. Chỉ bỏ marker incomplete sau khi verify
toàn bộ manifest/file. File hoàn chỉnh đúng hash được dùng lại; file hỏng trong
staging được tải lại. Việc resume HTTP của `.incomplete` dùng thư viện Hub đã pin
trong recipe; fixture kiểm tra quyết định resume/force-download và hash tại máy,
chưa là phép đo mạng đứt thật. [Hugging Face download guide](https://huggingface.co/docs/huggingface_hub/guides/download).

Máy cần Windows, `uv`, Python 3.12 và CUDA phù hợp. Base EXE không kèm GPU runtime;
cài mới trên máy chưa có model chưa được đo trong lượt này vì runtime phù hợp đã có.
Manager mở lên không download. Cài thủ công vẫn giữ contract đích mới.

**File dài:** tách splitter nhận dạng khỏi splitter strict của API alignment S2.
Giới hạn request Qwen 30 s, ưu tiên silence cũ; khi không có silence thì chọn vùng
năng lượng thấp trong hai giây cuối cửa sổ. Giữ tất cả sample, kể cả phần cuối chưa
đủ một ms; mốc chia cửa sổ không phải giờ phụ đề. Không fuzzy dedup/bỏ lời.
Timeout request được chia lại một lần thành cửa sổ <=15 s. Cache giữ chunk hoàn tất
và kế hoạch retry; recognition lỗi sau đó giữ review có `recognition_complete=false`.
Partial/hủy không được công bố complete. Deadline cấu hình vẫn 180 s mặc định nên
lượt gặp stall đầu tiên còn chậm; chưa có fix nguyên nhân generation bị treo.

**Người nói:** optional failure không chặn nhận dạng hoặc làm mất subtitle đã có
timing. JSON giữ `pending_diarization`; CLI/GUI báo rõ. Cue có policy sentence được
gán speaker nguyên cue, không tách/gán từng chữ; overlap/ambiguous giữ nhãn unknown.
Community-1 thiếu quyền vẫn cần token nhập kín trong manager; không xin key mới,
không tải hoặc chạy lại model người nói trong lượt này. Gate DER cũ được kế thừa.

## Kiểm tra raw trước inference

`replay.json`: hai model trên user 60 s và ba clip meeting có raw đầy đủ
(`R8001_M8004-c01`, `R8003_M8001-c01/c02`), tổng **32 chunk**. **11 chunk** qua
sentence geometry và RMS biên dù word geometry fail; 12 lỗi token biên, 4 outlier
nội bộ ngoài cue, 5 overlap giữa câu. **0/8 cặp model/clip đủ toàn bộ timing**.
0 inference cho replay, 43 file nguồn/raw/audio giữ hash và mtime. Đây là kiểm tra
contract trên tập chọn, không phải benchmark quality mới hoặc SRT đã nghiệm thu.

## Đo lại đúng các lỗi liên quan

`measure/summary.json`, `traces.json`: Qwen 1.7B, runtime/model cũ, request mặc định
180 s, âm thanh đã có. Có cold load riêng từng job; metric load bên dưới gồm các
lần restart sau timeout, không phải cache đĩa lạnh toàn máy. PyInstaller chạy CPU
đồng thời với một phần lượt đo; wall/load là số quan sát, không phải benchmark
trên máy hoàn toàn rảnh. Hai chunk đã hoàn tất ở clip timeout được seed từ receipt
cũ khi sample interval khớp. Kiểm tra tái dùng stress không thấy WAV request trùng
hash nên không ghép text cũ vào cửa sổ mới. Không đổi denominator common-28.

| Input | Trước | Kết quả mới | Wall s | Load s | Request nhận dạng s | CER thô |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| R8001_M8004-c02 | Timeout, 2 chunk xong | TXT, 2 timeout được retry | 449,891 | 70,421 | 373,907 | 61,44% |
| R8007_M8010-c02 | Không có silence cut | TXT, 1 timeout được retry | 235,031 | 26,469 | 203,125 | 44,27% |
| R8007_M8010-c03 | Không có silence cut | TXT | 37,203 | 11,265 | 21,031 | 52,16% |
| R8007_M8010-c04 | Không có silence cut | TXT | 38,844 | 11,734 | 22,375 | 33,91% |
| User 60 s | TXT/review, SRT fail | TXT/review, SRT vẫn fail | 35,375 | 22,468 | 4,938 | Không chấm lại |
| Stress 26,2308 phút | Recognition chưa xong | TXT, 1 timeout được retry | 432,422 | 22,343 | 391,673 | 44,27% |

User: alignment request 0,891 s, vẫn có lỗi token biên. Cửa sổ nhận dạng mới làm
text khác baseline 60 s; chưa chứng minh quality tốt hơn, không lấy việc hoàn tất
TXT làm pass SRT. Stress: 59 request hoàn tất và một request timeout; RTF request
0,249, bỏ load nhưng giữ điều phối 0,261, toàn wall 0,275. Mục tiêu toàn bước sau
load <=0,25 chưa đạt. CER giữ script/case/số/overlap như scorer cũ, không phải cpCER;
đuôi stress 22.897 ms chưa có nhãn vẫn giữ giới hạn cũ. Không suy 44,27% là tỷ lệ
audio sai hoặc bằng chứng mọi phim/phương ngữ.

Batch host exit 0; từng kết quả được lưu riêng, không dùng exit host làm pass SRT.
14 file bảo vệ (input/reference và runtime manifest/lock/bridge) giữ hash/mtime.
Không đổi weight hoặc runtime; locator verify model đã có trước các lần chạy.
Không chạy lại common-28, FWW corpus, Community-1 hoặc benchmark dịch.

## Source gates

Dùng Python 3.12.13 và công cụ đã có trong môi trường project chính; checkout này
không có `.venv`. Không `uv sync`, đổi dependency hoặc cài package global.

- Lượt rộng ASR/CLI/UI: **648 pass, 5 fail, 13 deselected / 54,93 s**. Bốn fail do
  fixture còn patch preflight người nói đã bỏ; cập nhật fixture theo hành vi mới.
  Một test timeout Scribe 10 ms gặp race khi máy đang chạy model; không sửa Scribe.
- Rerun các fixture liên quan và timeout nói trên: **45 pass / 6,08 s**.
- Gate cuối cho source đã sửa: **110 pass / 14,52 s**, gồm sentence pipeline/SRT/
  JSON/review, install/hash/resume/lock, file dài/timeout/cache, CLI/UI recovery.
  Download helper có thêm **5 pass / 0,61 s** trước gate cuối, dùng file nhỏ/mocked
  Hub; không tính là tải runtime thật. Test timeout synthetic từng có sai kỳ vọng
  số chunk; đã sửa kỳ vọng theo sample coverage, không đổi thuật toán để khớp test.
- Ruff app/tests pass; pyright app **0 error, 0 warning**; translations in sync.
  Pyright có notice checkout thiếu `.venv`, dùng `--pythonpath` môi trường đã có.
- Không full suite ngoài ASR/CLI/UI, không online/API test. Deselected/fixture giả
  không chứng minh model tải mới, speaker quality hoặc GUI button workflow đã pass.

## EXE và workflow

Artifact: `dist/VideoCaptioner-ASR-SentencePrep-20260909/` (**phân phối nguyên onedir**).
Dùng bản copy đã so hash của spec duy nhất và source snapshot, không đưa AppData thật
vào build. PyInstaller **exit 0 / 243,157 s**, 6 warning đáng chú ý, 0 dòng ERROR.
Warnings: `urllib3.contrib.emscripten/js`, optional `curl_cffi`, `yt_dlp_ejs`, hidden
imports `tzdata`, `sip`, và framework AppKit khác platform. Warn-file có 595 dòng
missing-module (gồm dependency tùy chọn/khác platform), không coi là 595 lỗi startup.

- EXE **31.184.350 byte**; onedir sau smoke GUI **237.859.242 byte** (AppData mutable
  có thể tăng khi sử dụng). Timestamp UTC **2026-09-08 19:33:55.103818**, tương ứng
  giờ Việt Nam 2026-09-09 02:33:55.
- SHA-256: `22495164beef9977300c5bf5b83b6c31086f836fe4eb7a2d79eab58604a89f80`.
- GUI native sống **25 s**, tìm thấy cửa sổ chính; đóng bằng WM_CLOSE đúng PID test,
  **exit 0**, không force kill.
- EXE Qwen TXT trên 10 s audio public tạo 23 ký tự. Helper lần đầu gặp race psutil
  sau khi file đã được tạo nên không có receipt exit CLI lần đó. Lượt xác nhận dùng
  cache, **exit 0 / 4,359 s**, cùng hash output; chỉ thấy FFmpeg/conhost, không gọi
  lại model. Không gọi 4,359 s là tốc độ inference.
- EXE Faster-Whisper large-v3 sentence cùng 10 s: **exit 0 / 20,25 s**, 1 cue SRT có
  interval dương/trong audio; đã quan sát executable và FFmpeg thực chạy. Không còn
  child thuộc hai workflow. Đây là smoke ngắn, không chấm lại benchmark FWW cũ.
- Chưa test luồng bấm nút GUI file→download→cancel→resume, cài model mới qua mạng
  trong EXE, Qwen SRT thành công trên mẫu lỗi, FFmpeg synthesis hoặc API online.

TimingGuard cũ vẫn có SHA-256
`cdfecfafe7009129e2446923ddbe515db8b121b06f2b72808031ee2ccb4a093a`.
Không xóa/junction cleanup, không thay artifact cũ, không commit build/dist/media.

## Việc còn lại

1. Giải quyết biên Qwen lỗi và nghiệm thu cue với audio; không nới guard để hợp thức
   hóa SRT hoặc lấy giờ FWW gán cho chữ Qwen chưa đối chiếu.
2. Giảm generation stall và đo quality của chính các file khó; giữ cache/receipt mới,
   không lặp các request đã xong chỉ để có lại số pass.
3. Xác minh cài mới qua mạng, GUI cancel/resume và speaker association ở phạm vi cần
   dùng. Giữ source/EXE hiện tại là cải tiến có giới hạn, chưa là ASR sản phẩm hoàn tất.

## File đã thay đổi so với d2dc518

25 file trong working tree; không staged/commit/push. Evidence/build/helper mới nằm
dưới build/dist bị Git ignore, không thuộc danh sách source bàn giao:

```text
README.md
VideoCaptioner.spec
status.md
docs/dev/asr-completion-next-session-prompt.md
docs/dev/asr-local-s5.md
docs/dev/asr-sentence-preparation-2026-09.md
docs/plans/asr-completion-2026-09.md
tests/test_asr/test_local_download.py
tests/test_asr/test_local_prepare.py
tests/test_asr/test_local_s5.py
tests/test_asr/test_local_s51.py
tests/test_asr/test_qwen_long_audio.py
tests/test_asr/test_qwen_sentence_timing.py
tests/test_asr/test_qwen_text_result.py
videocaptioner/cli/commands/transcribe.py
videocaptioner/core/asr/local/audio.py
videocaptioner/core/asr/local/pipeline.py
videocaptioner/core/asr/local/prepare.py
videocaptioner/core/asr/local/review.py
videocaptioner/core/asr/local/runtime.py
videocaptioner/core/asr/local/sentence_timing.py
videocaptioner/core/asr/transcribe.py
videocaptioner/resources/local_asr/download.py
videocaptioner/ui/components/local_asr_cards.py
videocaptioner/ui/thread/transcript_thread.py
```
