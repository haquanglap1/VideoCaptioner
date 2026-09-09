# Qwen timing, generation budget và GUI resume — 2026-09-09

ASR-S3 / `codex/asr-s3-native`, HEAD **d2dc518**, kế thừa 25 file chưa commit.
Không reset/commit/push. **Qwen SRT mẫu user 60 s vẫn chưa đạt; TXT chưa thay SRT.
OCR dừng.** OmniVoice Studio vẫn sau ASR, cần xác minh dự án/interface chính thức.

Evidence mới:
`build/asr-session-evidence/VC-ASR-Completion-20260908-140534/cue-slots-20260909/`.
`source-before/` giữ snapshot 25 file đầu phiên. Giữ raw/cache/runtime/EXE cũ.

## Timestamp: hai thử nghiệm chưa đủ điều kiện tích hợp

Raw SentencePrep: chunk cuối 22.350 ms có hai cue cuối bị chặn bởi token biên
đảo chiều/zero-duration. Không đổi recognition, checkpoint, BF16/SDPA hoặc guard.

- `probe/`: một forward với toàn lexical text, chỉ đặt cặp slot sau token đầu/cuối
  của mỗi cue. Cơ sở là dynamic slot insertion trong
  [báo cáo Qwen, mục 3.3–3.4](https://arxiv.org/html/2601.21337v1#S3.SS3).
  Không giả định slot sau cả câu trả start của câu. **Hai lỗi biên cũ vẫn còn.**
- `refine/`: một forward căn lại vùng hai cue lỗi, giới hạn audio bởi end cue hợp
  lệ trước đó và cuối recording. Crop chỉ chọn audio, không làm giờ xuất. Một cue
  qua geometry; cue cuối còn mốc nội bộ ngoài biên nên **toàn kết quả bị chặn**.

Hai contract/raw/result/validation được giữ riêng; preservation pass, process
đóng. **Tổng hai forward aligner, không có SRT mới hay acoustic acceptance.**
Không clamp/drop/swap/LIS/interpolate, không lấy giờ FWW, không sửa review hoặc
tích hợp các thử nghiệm chưa đạt. Không lặp sparse slots/crop này hoặc sweep tiếp
từ cùng bằng chứng. RMS không chứng minh câu được căn đúng.

## Chặn generation kéo dài, không công bố partial

Worker dùng budget `min(8192, 256 + ceil(audio_seconds × 32))` mỗi request.
Chỉ trả text khi có EOS. Exhaustion trả `incomplete/generation-limit`, không ghi
result chứa partial. Host nhận `LocalRuntimeGenerationLimit`, giữ model/GPU lease
cho retry trong job; pipeline chia đúng chunk chưa xong thành <=15 s một lần.
Nếu cửa sổ nhỏ vẫn lỗi thì giữ incomplete/review. Timeout/cancel vẫn đóng process.
Cache recognition complete và retry plan cũ giữ tương thích; không sửa text/EOS/
checkpoint/temperature. **Budget chưa sửa nguyên nhân acoustic/generation.**

Locator giữ verify recipe/model/hash, nhận thêm đúng SHA-256 bridge bàn giao
`d8de7fce52e46ff19d3398ca78312a654170c47505dd38a8f51f74e6bb7e82ff`.
App chạy bridge hiện tại trong bundle với interpreter/weights đã verify, không
ghi đè runtime cũ. Tìm cả managed path trước cập nhật để không tải lại weights.
Bridge ngoài allowlist vẫn bị từ chối.

`stall/`: đo đúng **bốn WAV request/hash từng timeout**, không chạy lại request
đã hoàn tất, một model load:

| Case / offset ms | Timeout cũ s | Budget mới s | Sinh token / limit | Kết quả |
| --- | ---: | ---: | ---: | --- |
| R8001_M8004-c02 / 59.700 | 180,969 | 62,859 | 1.192 / 1.192 | Incomplete |
| R8001_M8004-c02 / 88.950 | 181,406 | 63,860 | 1.176 / 1.176 | Incomplete |
| R8007_M8010-c02 / 51.100 | 181,328 | 83,671 | 1.188 / 1.188 | Incomplete |
| Stress / 640.700 | 181,032 | 51,672 | 1.170 / 1.170 | Incomplete |

Cả bốn giữ cùng PID; load 11,594 s, CUDA peak allocated lúc load 4.698.543.616
byte. Host exit 0 / 277,750 s; 20 file bảo vệ giữ hash/mtime, process/lease đóng.
Có workload GPU khác và kiểm tra CPU cùng lúc ở một phần phép đo; đây là số
quan sát, không phải benchmark máy rảnh. **Không suy RTF toàn file mới hoặc CER tốt hơn.**

`cache-resume/`: pipeline hiện tại dùng bản sao cache riêng, cấm model request/
download. Hai clip khó và stress xuất TXT **giống từng ký tự** với SentencePrep,
0 inference/download; cache gốc giữ hash/mtime. Không chấm lại CER/common-28 hoặc
lấy thời gian cached làm tốc độ inference. Chất lượng chữ được kế thừa, chưa cải thiện.

## GUI chuẩn bị/hủy/tiếp tục

Manager thêm **Prepare / resume selected model**; worker gọi `ensure_model`
chung core, cùng root/model. Install thủ công vẫn có. Bắt đầu/thành công cập nhật
status cả khi reuse, tránh giữ dòng cancelled cũ. Signal sau hủy không đổi saved
root; controls mở lại sau worker.finished/`wait()`.

`gui-prepare/`: **native Windows Qt/QTest button clicks**, private settings,
hash verification trên Qwen 1.7B đã cài thật:

- Hủy verify **0,031 s**, không phát installed, worker thu hồi.
- Tiếp tục cùng root/model **4,750 s**; reuse lần nữa **5,250 s**.
- Controls bật lại, root/manifest/lock/bridge giữ nguyên; có ảnh trước/sau.
  0 download/subprocess/inference; **chưa là hủy HTTP transfer hoặc cài mới qua mạng**.

Không tải trùng model đã có để tạo số pass. Network/disk/partial fixtures cũ
được kế thừa; gate runtime mới thật vẫn mở.

## Source và EXE

- **142 pass / 13,16 s**, 0 fail/skip trong chín file ASR/CLI/UI liên quan.
  Bao gồm EOS/budget, incomplete giữ process, scratch cleanup, retry/cache,
  legacy managed discovery, GUI cancel/resume, TXT/review và sentence guard.
- Ruff code/test chạm mới pass; pyright năm file app/worker **0 error/0 warning**;
  translations in sync. Ruff lượt đầu có năm lỗi import/unused, đã sửa/rerun.
  Hai pytest warning là pydub audioop deprecation và FFmpeg không trên PATH unit;
  helper media dùng FFmpeg đã có. Python 3.12.13/tools từ project chính.
- Không dependency sync/install, full suite, benchmark dịch/Community-1/OCR/corpus.
- EXE **ResumeGuard-20260909** build từ spec duy nhất/source snapshot so hash:
  **exit 0 / 214,516 s**. Sáu warning đáng chú ý (emscripten/js, optional curl_cffi,
  yt_dlp_ejs, tzdata, sip, AppKit khác platform), 0 ERROR.
  Giữ SentencePrep và TimingGuard; phân phối nguyên onedir.

Artifact `dist/VideoCaptioner-ASR-ResumeGuard-20260909/`:

- EXE **31.185.678 byte**, timestamp UTC **2026-09-08 20:42:51.075610**;
  onedir sau GUI smoke **237.861.845 byte**, AppData mutable có thể tăng sau chạy.
- SHA-256 **`6e8b68b9b67efab6eac9857e1f0577ea61c23e14c77e234c70eabb8e957bc4f3`**.
- GUI native sống **25 s**, tìm thấy cửa sổ chính, WM_CLOSE đúng PID,
  **exit 0**, không force close.
- Qwen TXT public 10 s từ chính EXE: **exit 0 / 27,812 s**, 23 ký tự giống bản
  trước; quan sát worker `python.exe` thực chạy, không child còn sống. Đây là
  normal recognition với bridge/budget mới, không dùng cache để báo inference.
- Chưa frozen GUI button download/cancel/resume, tải runtime mới qua mạng, Qwen
  SRT mẫu lỗi, media synthesis hoặc API online. Kế thừa FWW/gateway smoke cũ.

## File chạm trong phiên này

Working tree cuối có 29 file thay đổi, gồm cả 25 file kế thừa. Phiên này chạm
15 file sau; code/timing thí nghiệm chỉ nằm trong evidence, chưa vào app:

```text
README.md
VideoCaptioner.spec
status.md
docs/dev/asr-local-s5.md
docs/dev/asr-completion-next-session-prompt.md
docs/dev/asr-stall-resume-2026-09.md
docs/plans/asr-completion-2026-09.md
tests/test_asr/test_qwen_long_audio.py
tests/test_asr/test_local_prepare.py
tests/test_ui/test_local_asr.py
videocaptioner/core/asr/local/pipeline.py
videocaptioner/core/asr/local/runtime.py
videocaptioner/resources/local_asr/bridge.py
videocaptioner/ui/components/local_asr_cards.py
videocaptioner/ui/thread/local_asr_thread.py
```

Ưu tiên tiếp tục: biên câu Qwen dựa trên audio, chất lượng file khó/nguyên nhân
generation thiếu EOS, tải mới qua mạng khi cần. **ASR chưa hoàn tất.**
