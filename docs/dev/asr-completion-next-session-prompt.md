# Tiếp tục ASR và ghi nhớ hạng mục OmniVoice Studio

## Bắt đầu đúng workspace

Làm tại checkout **VideoCaptioner-ASR-S3**, nhánh **`codex/asr-s3-native`**.
Snapshot chứa prompt này gom **30 file code/test/tài liệu** trên nền **`d2dc518`**,
với commit subject **`feat(asr): add resumable model preparation and bounded recognition`**.
`d2dc518` là parent của snapshot, **không còn là HEAD bàn giao**. Lấy SHA chính xác
bằng `git log -1`; đối chiếu SHA trong tin nhắn bàn giao và tracking branch.
Sau lượt submit/push, working tree được kỳ vọng sạch. Chạy
`git status --short --branch`, đọc diff nếu có thay đổi mới và giữ tất cả chúng.
Không reset về d2dc518, 669c0da, 2f8e0a8 hoặc nền benchmark cũ.

Đọc `AGENTS.md`, `README.md`, mục mới nhất `status.md`, rồi:

- [Báo cáo mới nhất: direct Qwen-text alignment và generation trace](asr-direct-alignment-stall-2026-09.md).
- [Timing probes, stall và GUI resume được kế thừa](asr-stall-resume-2026-09.md).
- [Báo cáo SentencePrep được kế thừa](asr-sentence-preparation-2026-09.md).
- [Plan ASR và hạng mục OmniVoice Studio](../plans/asr-completion-2026-09.md).

Báo cáo cũ là lịch sử; số file chưa commit trong từng báo cáo mô tả thời điểm đo.
User đã yêu cầu submit/push snapshot này. Quyền đó **không áp dụng cho thay đổi
của phiên tiếp theo**: không tự commit/push, tạo tag/release. **OCR vẫn dừng.**

## Ưu tiên của user

- Nhận dạng đúng, nhanh, ổn định; **cần timestamp câu/đoạn** để làm phụ đề và chuyển
  cho LLM. Không bắt mọi word timestamp phải pass khi chỉ cần cue.
- TXT là đầu ra text và bản bảo toàn khi timing lỗi; **chưa thay SRT/ASS**.
  LLM không thể suy giờ nói chính xác chỉ từ text.
- User không biết tiếng Trung; cần tiến triển trên luồng thật. Mỗi phép đo phải
  trả lời lỗi/thay đổi cụ thể, không tiếp tục chuỗi audit/CTC hoặc sweep model,
  dtype, cửa sổ theo quán tính. Không tính RMS pass là nghiệm thu acoustic.
- Dịch giữ `https://api.videocaptioner.cn/v1`, `gpt-5.6-terra`, timeout 300 s.
  Không benchmark dịch thêm hoặc tìm key cũ. Nếu cần API mới, dùng credential nhập
  kín theo scope cần thiết, không đưa vào chat/argv/env/file.
- Scribe/ElevenLabs đã ngoài scope. Không xin key/tài khoản cho các engine đó.
- **Hạng mục sau ASR:** thêm lồng tiếng bằng **OmniVoice Studio**, bên cạnh
  **VieNeu Local** hiện có. Chưa yêu cầu triển khai OmniVoice Studio ngay.

## Source hiện có và giới hạn

1. **Recognition độc lập:** Qwen TXT không tìm/verify/nạp aligner hoặc Community-1.
   Timed export nhận dạng trước; lỗi timing giữ TXT/review, không overwrite TXT
   của user. CLI timed output chưa tạo được giữ exit 5; pipeline cần SRT dừng.
   Partial/hủy không được công bố complete.
2. **Cue policy:** `qwen-sentence-anchors-v1` chia theo text, lấy start token đầu
   và end token cuối, kiểm tra hai token biên với audio; mọi mốc raw phải nằm trong
   cue. Word strict giữ riêng. Không min/max, clamp, swap, interpolate, bỏ chữ
   hoặc lấy ranh giới chunk làm giờ nói. Review giữ raw/policy/ID/audio identity;
   cache raw alignment tách khỏi output đã validate.
3. **Tự chuẩn bị model:** core GUI/CLI dùng lại model đã verify; thiếu thì tải đúng
   model vào runtime managed riêng, có ownership/OS lock/hash/progress/hủy/resume.
   TXT không tải aligner; giữ runtime cũ. Mở manager không download.
   Cài mới thật qua mạng chưa đo vì runtime phù hợp đã có.
4. **File dài:** request nhận dạng tối đa 30 s; thiếu silence thì cắt theo năng
   lượng gần cuối, giữ đủ sample. Timeout retry một lần <=15 s; cache giữ chunk
   hoàn tất và retry plan. Worker mới dùng budget token theo audio, bắt buộc EOS;
   hết budget trả incomplete và giữ model cho retry nhỏ. Bốn stall cũ được chặn
   ở 51,672–83,671 s thay vì ~181 s, nhưng nguyên nhân generation chưa được sửa.
5. **Người nói tùy chọn:** lỗi giữ subtitle đã có timing và `pending_diarization`.
   Chỉ gán nguyên cue khi có sentence timing; không đoán danh tính/xưng hô hoặc
   giả gán từng chữ. Community-1 vẫn cần quyền/token khi cài model gated.

Implementation chính dưới `videocaptioner/`: `core/asr/local/{pipeline,audio,
sentence_timing,prepare,runtime,review}.py`, `core/asr/transcribe.py`,
`resources/local_asr/download.py`, `cli/commands/transcribe.py`,
`ui/thread/transcript_thread.py`, `ui/components/local_asr_cards.py`.
Bridge `resources/local_asr/bridge.py` và `ui/thread/local_asr_thread.py` cũng đã
sửa. Locator chạy bridge bundle với runtime đã verify, nhận đúng hash bridge cũ,
tìm cả managed path cũ để không tải trùng. GUI manager thêm Prepare / resume;
native Qt/QTest đã hủy verify rồi tiếp tục model thật, chưa hủy HTTP transfer.
Danh sách file và gate chi tiết nằm trong các báo cáo trên. Direct DTW và mask
recognition thử nghiệm chỉ nằm trong evidence, không có trong bridge app/EXE.

## Việc tiếp theo theo thứ tự

**Evidence bổ sung mới nhất:** `direct-qwen-align-20260909/` trong Completion.
Một forward Whisper.align trên nguyên text Qwen của chunk cuối (không generation
Whisper) và một silence control. SRT trong `candidate-not-accepted/` đủ **9 cue**,
giữ nguyên chữ/ID/provenance, nhưng **chưa nghiệm thu acoustic** vì đầu cue 2/4
trong chunk còn chứa khoảng nghỉ. Không dùng nó làm đầu vào LLM/sản phẩm, không
gán giờ của transcript khác, clamp hoặc sửa raw. Không chạy lại direct DTW cùng
input/config; Community-1 cache cũng bỏ sót phần cue ngắn, không dùng để cắt lời.
Wheel CT2 19.470.040 byte chỉ giải nén riêng trong evidence; không tải weights,
không sửa dependency project/runtime. Tool audio không hỗ trợ nghe ở phiên này.

`mask-stall/` kiểm tra recognition mask đúng bốn WAV/hash từng stall: parent
R8001_M8004-c02 tại **88.950 ms** đã EOS **5,687 s / 111 token**, giữ output riêng
và **không chạy lại parent đã xong**. Ba request còn lại vẫn incomplete; có raw
token trace với cặp lặp **582/546/570 lần**. Không lặp phép đo mask để quan sát
cùng loop, không cắt repetition để giả EOS. Candidate ghép parent mới với cache
cũ có CER **60,21%** thay baseline **61,44%**, cùng 975 ký tự reference; đây là
output trộn policy ở một clip, không thay common-28 hoặc chứng minh quality tốt.
Mask chưa tích hợp app. `source-before/` ở lượt mới giữ snapshot đủ 29 file cũ.
Nếu cache hết TTL, chỉ phục hồi raw/receipt đã complete vào cache thử nghiệm
riêng sau khi khớp audio hash, sample interval, model revision và policy. Giữ
cache gốc; không gắn output mask candidate vào namespace recognition production.

1. **Qwen timing câu/đoạn còn chưa đạt.** Replay raw cũ chỉ cho 11/32 chunk được
   chọn qua guard, 0/8 cặp model/clip có timing hoàn chỉnh. Mẫu user 60 s chạy với
   cửa sổ mới vẫn TXT/review. Dùng raw đã lưu để định vị lỗi biên trước; chỉ
   inference khi có thay đổi acoustic cần kiểm chứng. Chốt biên có nguồn từ audio
   và đủ text, không nới guard chỉ để có SRT hoặc lấy giờ FWW gán cho chữ Qwen
   chưa đối chiếu. Gate thật: SRT đầy đủ, biên hợp lệ và chuyển nguyên timing cho LLM.
   Hai probe mới (sparse first/last slots, crop vùng cue lỗi theo cue trước) đều
   chưa qua guard; giữ raw trong `cue-slots-20260909/`, **không chạy lại chúng**.
2. **Quality và stall:** bốn clip lỗi cũ đã có TXT, CER thô 33,91–61,44%; stress
   26,23 phút hoàn tất trong 432,422 s, CER 44,27%. RTF sau load có điều phối
   0,261, chưa đạt mục tiêu 0,25. Text mẫu ngắn đã đổi; chưa chứng minh cap 30 s
   cải thiện quality clip ngắn. Kế thừa output/cache/retry plan; không chạy lại từ
   đầu các chunk đã xong. Báo load, request, timeout, speaker/export riêng.
   Ba job cache-resume mới cho TXT nguyên chữ, 0 inference; không lấy số cached
   làm tốc độ model hoặc coi token budget đã cải thiện CER/RTF toàn stress.
3. **Nghiệm thu luồng chuẩn bị model:** cài mới qua mạng khi thực sự cần, GUI
   cancel/resume, disk/network failure, lần hai dùng lại model. Fixture offline
   không thay thế end-to-end tải runtime thật. Người nói là bước bổ sung.
4. **EXE:** đã có bản mới bên dưới. Chỉ build tiếp khi code/resource thay đổi cần
   đóng gói; dùng spec duy nhất, tên mới và báo đủ các gate theo AGENTS.md.

## Hạng mục tương lai: OmniVoice Studio

Ghi nhớ mong muốn của user: thêm lựa chọn lồng tiếng OmniVoice Studio và tiếp tục
giữ VieNeu Local. Khi đến hạng mục này:

- Xác định đúng sản phẩm/repository, phiên bản, license và interface từ nguồn
  chính thức hoặc link user cung cấp. Hiện **chưa xác minh** các thông tin đó;
  không đoán endpoint, hỗ trợ tiếng Việt/Windows/GPU hay tương thích OpenAI.
- Sau khi có contract thực, thêm adapter/provider phù hợp với pipeline dubbing
  hiện có; dùng lại chọn giọng, cache, duration/timeline và hủy job ở nơi phù hợp.
  Nếu cần runtime GPU, tách khỏi Qt process; giữ runtime/model/config của VieNeu.
- Có gate riêng cho tổng hợp tiếng Việt, chất lượng lời đọc, đo duration, ghép
  timeline, lỗi/hủy và source/EXE. Không lấy gate VieNeu/ASR làm pass cho OmniVoice.

## Benchmark và validation được kế thừa

- Common-28: Qwen 1.7B 21,04% CER; 0.6B 22,00%; FWW large-v3 word 36,74%,
  sentence 36,78%. Không thay denominator hoặc ghép quality bốn clip khó vào bảng
  này để tự xếp hạng lại. 1.7B là ứng viên quality, chưa đổi default app.
- Gate cuối source liên quan: **142 pass / 13,16 s**, Ruff pass, pyright 0/0,
  translations in sync. Lượt rộng trước đó 648 pass/5 fail; có 45 pass kiểm tra
  lại sau sửa fixture cũ và rerun timeout race. Xem report để phân biệt fail/skip.
- Checkout không có `.venv`; lượt trước dùng Python 3.12.13 và tools đã có ở
  môi trường project chính bên cạnh. Không tự đồng bộ dependency/cài global.
- Chỉ kiểm tra lại phần thay đổi. Không full suite/build/GPU/API chỉ để lặp gate cũ.

## Evidence và artifact cần giữ

Root: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`.
Evidence mới: `sentence-20260909/`, đặc biệt `replay.json`, `measure/summary.json`,
`measure/traces.json`, raw/review/TXT và cache trong `measure/host/AppData/`.
Lượt ResumeGuard: `cue-slots-20260909/` chứa `probe/`, `refine/`, `stall/`,
`cache-resume/`, `gui-prepare/`, `frozen-txt/` và build/smoke receipts. `source-before/`
giữ snapshot 25 file đầu phiên. Chỉ hai forward aligner và bốn request recognition
đúng WAV/hash từng timeout; một normal TXT smoke riêng từ EXE mới.
Lượt mới nhất: `direct-qwen-align-20260909/` chứa `probe/` (speech/silence DTW),
`candidate-not-accepted/` (SRT/JSON 9 cue và validation accepted=false),
`mask-stall/` (bốn request, raw generation IDs; `1.complete.json` là parent đã
EOS), `quality/summary.json` và `handoff-validation.json`. Snapshot `source-before/`
giữ đủ 29 file đầu lượt đó. Các helper có exclusive-create; không chạy lại helper
để tạo lại output đã có. Evidence/library/media không nằm trong Git; checkout ở
máy khác không tự có các artifact này. Không tải lại corpus/model chỉ để lấp thiếu.
Dataset: `build/asr-session-evidence/datasets/AliMeeting-Eval/`; không tải/copy lại.
Clip user nằm ở `VC-UserClip-20260908-114035/` cạnh Completion; resolve nguồn qua
`reports/source-preflight.json`. Chỉ 60 s đầu đã được cho phép, không quét ổ.

EXE mới nhất: `dist/VideoCaptioner-ASR-ResumeGuard-20260909/`, nguyên onedir.
SHA-256 `6e8b68b9b67efab6eac9857e1f0577ea61c23e14c77e234c70eabb8e957bc4f3`.
Build exit 0 / 214,516 s, 6 warning đáng chú ý/0 ERROR; GUI sống 25 s, đóng đúng
PID exit 0. Frozen Qwen TXT public 10 s **thực gọi worker**, exit 0 / 27,812 s,
23 ký tự giống bản cũ, không child còn sống. Không chạy lại FWW/translation/synthesis;
chưa frozen GUI button download/cancel hoặc Qwen SRT trên mẫu lỗi.

EXE SentencePrep giữ lại: `dist/VideoCaptioner-ASR-SentencePrep-20260909/`.
SHA-256 `22495164beef9977300c5bf5b83b6c31086f836fe4eb7a2d79eab58604a89f80`.
Build exit 0, 6 warning đáng chú ý/0 ERROR; GUI sống 25 s, đóng đúng PID exit 0.
FWW sentence smoke thật 10 s xuất SRT hợp lệ. Qwen TXT tạo được text; helper lần
đầu race sau khi file đã tạo, lượt xác nhận exit 0 dùng cache. Không coi thời gian
cached là inference. Chưa GUI button workflow/cài mới qua mạng/Qwen SRT trên mẫu lỗi.

Giữ TimingGuard cũ, mọi runtime/model, AppData/cache, media/raw. Junction
`s6-final-build/smoke-app/_internal` từng bị automatic approval review chặn gỡ;
không retry/xóa qua parent. Helper thường dùng exclusive-create; đọc trước chạy.
Kiểm tra process/VRAM trước GPU, chỉ đóng process thuộc task. Không force-add
build/dist hoặc dọn artifact để commit. Bàn giao đúng trạng thái, file sửa và
`git status --short`; không gọi ASR hoặc OmniVoice Studio hoàn tất vượt bằng chứng.
