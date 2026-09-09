# Video bài giảng mới và phép đo onset — 2026-09-09

Tiếp tục ASR-S3 / `codex/asr-s3-native`, HEAD và tracking branch cùng
**b102ae9**. Giữ bốn file tài liệu chưa commit từ lượt native timestamp.
**Video mới nhận dạng xong toàn bộ, nhưng Qwen SRT vẫn chưa đạt.** Không đổi
code app, guard, model/runtime, cấu hình dịch hoặc EXE; không commit/push.

## Luồng thật trên video user vừa cung cấp

User bổ sung video bài giảng AI tiếng Trung trong phiên này. Video dài
**771,067 s**, H.264 2560×1440, AAC stereo 48 kHz. Chỉ đọc đúng file được cung
cấp; identity/hash và đường dẫn nguồn nằm trong evidence local, không vào Git.

Chạy **CLI source `transcribe`, Qwen 1.7B, Chinese, xuất SRT**, policy hiện tại
`qwen-sentence-anchors-v1`. Cấu hình CLI trống, AppData/cache riêng, mạng bị chặn;
dùng runtime/model đã cài. Instrumentation chỉ lưu request/receipt, không sửa
inference hoặc quyết định validation của app.

| Phạm vi | Wall host | Load hai model | Request recognition | Request alignment | Kết quả CLI |
| --- | ---: | ---: | ---: | ---: | --- |
| 60 s đầu | 35,031 s | 19,265 s | 7,500 s | 0,813 s | Exit 5; TXT 355 ký tự, không SRT |
| Toàn video | 118,016 s | 18,251 s | 90,750 s | 1,313 s | Exit 5; TXT 4.783 ký tự, không SRT |

- Đoạn 60 s: ba request recognition đều complete/EOS; ba request aligner.
  Cue cuối bị chặn vì end raw **60.030 ms** vượt đoạn cắt **60.000 ms**.
  Không clamp hoặc nới biên cho lưới 80 ms.
- Toàn video: **29 chunk** phủ audio đã decode dài **771.029 ms**; dùng lại hai
  chunk đầu cùng hash/config từ bản sao cache đã đóng SQLite. **27 request
  recognition mới đều complete**, không timeout/incomplete. Request mới đầu tiên
  bắt đầu ở 52.750 ms, có ngữ cảnh tiếp tục thật thay cho đoạn cắt ở giây 60.
  Không chạy lại request đã complete có cùng audio hash; không ghép text của
  chunk 7,25 s cũ vào cửa sổ mới dài 29,85 s.
- Timing dùng lại hai chunk đầu, gọi thêm **bảy request aligner**. Tám chunk đầu
  qua guard sản phẩm. Chunk thứ chín **220.850–248.900 ms** bị chặn: token biên
  `token-001149` có raw start=end **228.050 ms**. Đây là biên ở trong video,
  không phải lỗi duy nhất do cắt file ở giây 60. Hai mươi chunk sau chưa gọi
  aligner vì pipeline dừng ở lỗi đầu tiên.
- TXT khớp nguyên văn với review và chuỗi text của 29 chunk. Đã đối chiếu hai
  chunk cache và 27 raw receipt mới. Không cắt repetition, sửa chữ hoặc coi
  text complete là quality pass. **Chưa có reference audio độc lập/CER** cho
  video này. Các số thời gian toàn video có cache reuse, không thay benchmark
  common-28/stress hoặc chứng minh mọi file đạt RTF mục tiêu.
- Hai process CLI đã đóng, không còn child do task tạo. Mười file bảo vệ mỗi
  lượt giữ nguyên hash/mtime, gồm video, runtime và settings thật của hai checkout.
  Cache đoạn 60 s giữ nguyên sau khi chạy toàn video trên bản sao riêng.

## Phép đo onset riêng trên mẫu cũ

Đọc logits có sẵn trước, không chạy lại native timestamp/DTW. Thử thay đổi
acoustic cụ thể: tắt dần một vùng audio và đo xác suất token đầu cue với prefix
text Qwen cố định, **không có timestamp token trong prefix**. Ý tưởng tham khảo
[Stable-ts Refiner](https://github.com/jianfch/stable-ts/blob/main/stable_whisper/non_whisper/refinement.py);
đây là helper chẩn đoán riêng, không cài hoặc nghiệm thu thư viện Stable-ts.

Contract ghi trước inference: hai onset lỗi, probability floor 0,5, drop tối đa
0,05 tuyệt đối và 3% tương đối, precision 100 ms. Speech/gap dùng cùng bracket
vật lý, đối chứng chèn 16.000 sample zero tại local 5 s; delta kỳ vọng +1.000 ms,
tolerance 250 ms. Giữ speech/silence và toàn bộ vector logits tại vị trí được đo.

**Không đạt:** onset cue 2 chạm đáy bracket, vẫn chứa khoảng nghỉ; confidence
baseline trên audio chèn gap thấp hơn floor nên không đủ điều kiện đo. Cue 4
dịch 800 ms (residual −200 ms qua riêng shift control), nhưng onset speech
**47.250–47.350 ms** vẫn nằm quá sớm so với lời nói cần xác minh. Không coi một
shift pass hoặc xác suất thấp trên silence là nghiệm thu biên tuyệt đối.

Host exit 0 / **23,015 s**, **25 encoder forwards / 25 decoder requests**,
0 Qwen recognition, 0 DTW, 0 download/API; 139 file bảo vệ nguyên hash/mtime,
process/lease đóng. `accepted=false`, không xuất SRT/ghép mốc hoặc tích hợp.
Không chỉnh threshold để thử lại cùng input/config.

## Evidence và bàn giao

Dưới `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`:

- `acoustic-token-onset-20260909/`: contract, helper, 25 logits/receipt, result,
  preservation. Những giới hạn tìm kiếm là input thử nghiệm, không là giờ xuất.
- `ai-lecture-20260909/`: source preflight, WAV 60 s, CLI result, raw, TXT và
  private review/cache. Giữ receipt exit 5 và mốc vượt 30 ms.
- `ai-lecture-full-20260909/`: source preflight, cache seed manifest, full TXT,
  raw/traces, review/cache và `validation.json`. Validation dùng lại chính
  `sentence_cues` trên raw đã lưu; không inference. Tám chunk pass geometry
  không được gọi là acoustic acceptance. Đầu ra đủ chữ chưa được gửi cho LLM.

App không thay đổi nên kế thừa **142 test**, Ruff/pyright/sync và ResumeGuard;
không chạy lại unit suite/build. Các kiểm tra mới là workflow thật và validation
evidence ở trên. Chưa GUI/EXE trên bài giảng, tải model mới qua mạng, GUI HTTP
cancel/resume, sửa ba generation loop cũ hoặc nghiệm thu quality toàn bộ.

Ưu tiên timing còn mở. Kế thừa toàn bộ recognition/cache mới; không nhận dạng lại
video này từ đầu. Onset ablation đã bị loại; cần giải pháp biên có căn cứ audio,
không sửa raw/gộp lại cue theo lỗi để biến guard thành pass. OmniVoice Studio
đã có trong plan, vẫn sau ASR và giữ VieNeu Local; OCR tiếp tục dừng.
