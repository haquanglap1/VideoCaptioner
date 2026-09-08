# Tiếp tục hoàn thiện ASR: timing câu/đoạn và tải model

Làm tại checkout **VideoCaptioner-ASR-S3**, nhánh **`codex/asr-s3-native`**.
Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất của `status.md`, rồi
[plan hoàn thiện và so sánh model](../plans/asr-completion-2026-09.md).
Chạy `git log -1` và `git status --short --branch` trước sửa; giữ thay đổi hiện có.

Commit bàn giao **chứa prompt này**, từ nền **669c0da**, chốt **17 file**: bảy
file code, ba test, README/status/prompt/plan và ba báo cáo audit đã có.
Không reset về 669c0da hoặc các nền đo 2f8e0a8/63941a8. Những ghi chú “chưa
commit/push” trong báo cáo cũ là trạng thái lúc đo. User đã cho phép submit/push
snapshot này; quyền đó không áp dụng cho thay đổi mới của phiên tiếp theo.

## Yêu cầu mới nhất — ưu tiên hơn các audit lịch sử

- Nhận dạng âm thanh **đúng, nhanh, ổn định**; người nói là tính năng bổ sung.
- **Vẫn cần timestamp câu/đoạn để làm phụ đề và chuyển cho LLM.** Không bắt mọi
  timestamp từng chữ phải pass khi tác vụ chỉ cần cue. Giữ mốc có nguồn từ audio;
  LLM không thể suy thời điểm lời nói chính xác từ text.
- TXT là đầu ra khi chọn chỉ lấy text và bản bảo toàn khi timing lỗi;
  **TXT recovery chưa thay thế SRT/ASS hoặc nghiệm thu Qwen sentence timing**.
- Dịch giữ `https://api.videocaptioner.cn/v1`, `gpt-5.6-terra`, timeout 300 s.
  Không benchmark dịch thêm hoặc tìm key cũ. Key job trước không còn; nếu thật
  sự cần API mới, nhập kín theo scope mới, không ghi vào chat/argv/env/file.
- User không biết tiếng Trung và đã phàn nàn quá nhiều audit nhưng ít tiến triển
  sản phẩm. Sửa luồng thật; mỗi lần đo phải trả lời lỗi/thay đổi cụ thể. Không
  tiếp tục preflight CTC hoặc sweep model/dtype/window theo quán tính.
- **OCR vẫn dừng.** Scribe/ElevenLabs đã loại khỏi scope; không xin key/tài khoản.

## Code đã sửa trong snapshot

- `QwenLocalASR.recognize()` và `recognize_text()` trả text độc lập. GUI TXT và
  CLI output `.txt` không tìm/verify/nạp/chạy aligner hoặc Community-1.
- Timed export nhận dạng trước khi kiểm tra aligner. Nếu aligner thiếu/lỗi,
  giữ full text/raw trong review và GUI/CLI lưu TXT cạnh output dự kiến, dùng
  exclusive-create/hậu tố số khi tên đã có. Không overwrite TXT của user.
- Standalone GUI trả TXT, báo timing chưa hợp lệ, không ép mở modal sửa giờ.
  Task chạy lại xóa trạng thái kết quả cũ. Pipeline cần SRT vẫn dừng; CLI TXT
  thành công exit 0, timed output chưa tạo được giữ exit 5 để `process` không
  dịch/render file cũ hoặc thiếu. Partial/hủy không được công bố complete.
- Không sửa raw/clamp/swap/interpolate/drop chữ hoặc lấy chunk boundaries làm
  giờ lời nói. Không đổi checkpoint/frontend/chunk/timeout/cache/default/LLM.
- **Chưa giải quyết Qwen xuất SRT trên input lỗi timing. Chưa có tự tải model
  khi bắt đầu. EXE TimingGuard cũ chưa chứa fix source này.**

Implementation chính dưới `videocaptioner/`: `core/asr/local/pipeline.py`,
`core/asr/alignment/contract.py`, `core/asr/local/review.py`,
`core/asr/api_transcription.py`, `core/asr/transcribe.py`,
`cli/commands/transcribe.py`, `ui/thread/transcript_thread.py`,
`ui/view/transcription_interface.py`. Tests mới: `test_qwen_text_result.py` ở
`tests/test_asr`, `tests/test_cli`, `tests/test_ui`. Installer hiện vẫn explicit
install vào thư mục mới; mở settings không tự tải model.

## Việc tiếp theo theo thứ tự

1. **Timing câu/đoạn Qwen.** Tách kiểm tra biên cue khỏi lỗi timing nội bộ từng
   chữ. Chốt quy tắc biên có cơ sở và đủ text, không lấy min/max giấu outlier hoặc
   để LLM bịa giờ. Kiểm tra quy tắc mới trên raw đã lưu trước; chỉ inference khi
   có thay đổi acoustic cần đo. Chưa đủ cơ sở thì giữ TXT/review và báo timed
   output chưa xong. Không tự đổi engine hoặc lấy giờ FWW gắn vào chữ Qwen chưa
   đối chiếu. Xem gate và giới hạn cụ thể trong plan.
2. **Tự chuẩn bị model đang chọn** khi bắt đầu: core dùng chung GUI/CLI, đúng
   revision/hash, tiến độ/hủy/tiếp tục tải dở, khóa cài đồng thời, dùng lại model
   có sẵn. TXT không tải aligner; giữ runtime cũ. Community-1 cần quyền/token khi
   user bật, không làm mất transcript hoặc chặn recognition thường.
3. **File dài/timeout/tốc độ.** Xử lý ba clip lỗi chia audio, một timeout và
   stress sau thay đổi liên quan; giữ chunk đã hoàn tất. Báo cold load,
   recognition, speaker, export riêng. Không lặp nguyên corpus y hệt.
4. **Người nói tùy chọn**: nhãn ẩn danh/overlap/độ không chắc chắn; không đoán
   danh tính/xưng hô hoặc gán từng chữ khi chưa có timing phù hợp.
5. **EXE mới** sau khi luồng ổn: spec duy nhất, onedir tên mới, giữ artifact cũ;
   báo riêng build/artifact/hash/GUI/workflow thật theo AGENTS.md.

## Baseline và validation đã có

- Cùng 28 clip meeting: Qwen 1.7B **21,04% CER**, 0.6B **22,00%**, FWW large-v3
  word **36,74%**, sentence **36,78%**. CER thấp hơn tốt hơn; giữ script/case/
  số/overlap, không phải cpCER. Recognition đủ 28/32 ở mỗi Qwen và 32/32 ở FWW.
  Trường FWW `completed_valid_stage_output=5` là timing, không phải recognition.
- Median hai Qwen khoảng **17 s/clip** sau load trên các clip 105–150 s; chưa
  đủ chứng minh model nào nhanh hơn. 0.6B ít VRAM hơn. 1.7B là ứng viên ưu tiên
  quality trên máy đã đo, chưa đổi default app.
- Stress 26,23 phút: Qwen chưa hoàn tất; FWW có text nhưng CER thô **64,94%**,
  đuôi chưa nhãn. Meeting không thay nghiệm thu mọi phim/phương ngữ.
- Source fix: **226 test local ASR/CLI/UI pass / 17,44 s**, gồm 13 case mới.
  Ruff/pyright app pass. UI bỏ modal: 5 pass/2,36 s; trạng thái cũ: 1 pass/1,42 s.
  Đây là offline/stub, **0 acoustic inference/API mới**; không full suite,
  tải model, build hoặc GUI EXE mới trong lượt sửa source.
- Lượt submit chỉ rà manifest/diff, nội dung nhạy cảm và liên kết; không rerun
  các gate trên. Sau thay đổi mới chỉ chạy kiểm tra liên quan.

## Evidence và tài sản cần giữ

Root evidence: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`.
Dataset dùng chung: `build/asr-session-evidence/datasets/AliMeeting-Eval/`.
32 clip/66,9079 phút đã kiểm tra integrity; không tải/copy toàn bộ lại.
Clip user ở `VC-UserClip-20260908-114035/` cạnh Completion; resolve nguồn qua
`reports/source-preflight.json`, chỉ 60 s đầu đã được cho phép, không quét ổ/hỏi lại.

Đọc [S6](asr-s6-results-2026-09.md) và [follow-up](asr-s6-followup-2026-09.md)
khi cần baseline. Audit [attention](asr-qwen-attention-audit-2026-09.md),
[Parakeet](asr-parakeet-eligibility-2026-09.md),
[head Qwen CTC](asr-qwen-ctc-eligibility-2026-09.md) và các audit cũ khác là lịch
sử; evidence/raw/helper không nằm trong Git. Mask wiring có lỗi thật nhưng probe
vẫn fail strict; không suy nó đã sửa timing hoặc lặp probe/dictionary cũ.

Artifact mới nhất: `dist/VideoCaptioner-ASR-S6-TimingGuard-20260908/`, EXE SHA-256
`cdfecfafe7009129e2446923ddbe515db8b121b06f2b72808031ee2ccb4a093a`.
Giữ onedir, runtime/model, AppData/cache, media/raw cũ. Không force-add build/dist
hoặc dọn chúng để commit. Junction `s6-final-build/smoke-app/_internal` tới
S6-Review từng bị automatic approval review chặn gỡ; không retry hoặc xóa qua
parent/link. Helper cũ thường tạo output độc quyền: đọc guard trước dùng.
Kiểm tra process/VRAM trước GPU; chỉ đóng process thuộc task.

Bàn giao đúng trạng thái code/timing/quality/download/EXE, file đã sửa và
`git status --short`. Không gọi ASR sản phẩm hoàn tất khi các bước còn mở.
