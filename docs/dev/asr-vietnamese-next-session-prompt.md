# Prompt phiên tiếp theo — sau phụ đề Việt trên Lifetime EXE

**Bàn giao mới nhất: [hoàn tất ASR trước OCR](asr-completion-next-session-prompt.md).**
User đã yêu cầu tạm dừng OCR, bỏ nghiệm thu Scribe và chọn gateway/gpt-5.6-terra cho
dịch. Tài liệu dưới đây giữ snapshot ASR trước đó; không dùng baseline/quyền hoặc các
dòng "chưa S6" lịch sử thay mục tiêu/điều kiện nghiệm thu trong prompt mới.

Tiếp tục tại checkout **VideoCaptioner-ASR-S3** user chỉ định, nhánh **codex/asr-s3-native**.
Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md` và phần bàn giao S5.2 trong
`docs/dev/asr-implementation-2026-09.md`. Đọc tài liệu domain/source liên quan khi cần;
không dùng prompt cũ để phục hồi gate đã pass hoặc checkpoint user đã trả lời.

## 1. Mục tiêu user và quyền hiện tại

- **Yêu cầu mới nhất sau clip thực tế:** thống kê cách đọc phụ đề trong hình và lập
  kế hoạch tích hợp OCR vào app. Đã hoàn thành OCR-0 tại
  [`docs/plans/video-subtitle-ocr-integration-plan.md`](../plans/video-subtitle-ocr-integration-plan.md).
  OCR-1→OCR-4 chưa được triển khai; phiên vừa rồi chỉ làm kế hoạch, không cài model/dependency.
  Khi user giao triển khai, bắt đầu engine local trên crop đã có rồi PTS streaming /
  contract / GUI theo plan; không gọi bản đọc ảnh bằng agent là engine OCR đã pass.
- Mục tiêu là **audio/video tiếng Trung → phụ đề tiếng Việt**. User không biết tiếng Trung.
  Agent tự đối chiếu phần Trung và tự kiểm thử kỹ thuật; chỉ đưa bản Việt để user đánh giá
  cách diễn đạt/dễ đọc khi cần. Không giao user chấm chữ Trung hoặc xác nhận từng nút.
- User đã nói **giọng đọc ổn** và **không có vấn đề với bản dịch mẫu** của clip public
  **4,204 s / 1 cue**. Không xin lại checkpoint đó. Giọng trong clip là audio Trung gốc,
  không phải TTS mới. Chấp nhận mẫu không chứng minh chữ Trung đúng, nhiều speaker/xưng hô,
  video dài hoặc chất lượng mọi provider. User chưa chọn Google làm mặc định sản phẩm.
- Đang **review cuối S5.2 + Lifetime**. S1–S5 đã triển khai code, còn nợ nghiệm thu bên dưới.
  **S6 chưa được giao**: không tự chạy corpus/benchmark, chọn engine mặc định hoặc làm release.
  Nếu user giao S6 rõ ràng ở phiên mới, phạm vi đó mới thay giới hạn tương ứng.
- User yêu cầu commit/push tài liệu và prompt trong phiên bàn giao. Quyền đó chốt manifest
  hiện tại, không tự áp dụng cho thay đổi mới. Không tự commit/push/tag/release ở phiên sau.
  Lưu prompt không tạo task, phiên, automation hoặc job mới.

## 2. Snapshot và dữ liệu phải giữ

- Baseline trước commit tài liệu lần này: **d820ca0401b6b37c6349af49d1e84320103874b4**.
  Commit kế tiếp chỉ gồm **status.md**, **docs/dev/asr-implementation-2026-09.md** và
  **prompt này**. Lấy HEAD thật từ Git, đối chiếu log/ancestry và HEAD user bàn giao;
  không ép checkout về baseline cũ. Chạy `git status --short --branch` trước sửa.
- Code Lifetime **e6c0074250df41b5da4b7eaa71b2e9f21e4adcab**, parent **7e28895**;
  S5.2 **073510db54e5a24ab3deba3626d53279d478813f** là ancestor. Các lượt review/Việt mới
  không sửa code, tests, spec, dependency, pin hoặc policy.
- Giữ artifact **dist/VideoCaptioner-ASR-S52-Lifetime-20260907/** và EXE cùng basename:
  **31.161.900 byte**, local **2026-09-07 22:39:32**, SHA-256
  **b2dfe8692266fd08dc2471f54838385b975c6ebfe0839d8aa1d5436b38a75f78**.
  Onedir **580 file / 237.667.204 byte**; **218 module** source/PYZ khớp tại build.
- Giữ Final cũ **dist/VideoCaptioner-ASR-S52-Review-20260907-Final/**, SHA-256
  **457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649**.
- Không đổi media, `.env`, cookies, AppData, work-dir, logs, runtime hoặc artifact cũ;
  không reset/clean/stash. Nếu cần GUI/CLI mới: scratch chưa tồn tại, chỉ copy **EXE +
  `_internal/`**, so hash, tạo config/AppData/cache/temp/lease riêng. Không dùng AppData cũ
  làm fixture hoặc rerun helper create-only vào scratch/output đã nghiệm thu.
- Python **3.12.13** có sẵn trong venv checkout VideoCaptioner bên cạnh; ASR-S3 không có
  `.venv` riêng. Xác minh import đúng checkout; cô lập config trước import app. FFmpeg có sẵn.
  Không dùng Python 3.14 trên PATH, uv sync/cài global, nâng Qt hoặc đưa GPU vào venv Qt.

## 3. Gate đã có — kế thừa đúng snapshot, không chạy lại để tăng số pass

| Gate | Bằng chứng và giới hạn |
| --- | --- |
| Lifetime ASR local thật | Qwen **0.6B → strict alignment → Community-1 → JSON/SRT**, public Chinese **67.263 sample / 4,204 s**, exit 0 / **40,844 s**, **1 cue / 13 token IDs / 400–3680 ms / 1 speaker**, identity khớp, pending false, cache MISS |
| Runtime/cache | Qwen/aligner/Community-1 readiness/health và cache ba stage đã pass; bridge/reader đóng, lease acquire/release lại được |
| Việt trong source app | Google → JSON/SRT Việt từ output Lifetime, exit 0 / **1,953 s**; user đã chấp nhận bản dịch mẫu. Bản agent biên tập được giữ riêng |
| Việt trên Lifetime EXE | Google → JSON Việt **exit 0 / 2,219 s**; source text/IDs/timing/speaker/provenance/identity/context/pending giữ nguyên; cache mới. Không ASR/upload audio lại |
| SRT Việt trên cùng EXE | Export từ JSON đã dịch, tắt translate/split/optimize, **exit 0 / 0,438 s**; target-only, text/timing bằng JSON **400–3680 ms** |
| Synthesis trên cùng EXE | App ASS renderer ghép phụ đề cứng, **exit 0 / 1,063 s**. Input mới là nền tổng hợp **960×540** + audio public gốc. ffprobe audio/video/duration và frame trước/trong/sau cue pass; không persist ASS |
| Giới hạn chuỗi Việt | ASR kế thừa, dịch/export/synthesis mới trên cùng hash theo từng command. Không phải một lượt `process` mới xuyên suốt, video tự nhiên dài, corpus hoặc TTS |
| Native playback/editor/review | H.264 Play/seek, moving frames/playhead/inspector, save/reopen JSON+SRT và review identity/IDs/override/pending đã pass; source native **7 pass**, zero skip, và GUI Lifetime thật |
| Hủy decode trên binary | Đã pass ngày 2026-09-08: FFmpeg chạy **13,618 s**, sample còn sống **66 ms trước click**; child biến mất sau **0,875 s**, temp dọn, GUI phục hồi. Click+capture **0,483 s** có overhead công cụ |
| Shutdown/SIP | Ba lượt Lifetime **966,328 / 696,797 / 374,719 s**, X→exit 0, cleanup/log/WER checks pass. Không suy mọi crash SIP đã hết |
| Full/static/build kế thừa | **1.119 passed / 5 skipped / 51 deselected / 145,95 s**, gồm CLI106; ruff pass, pyright 0/0, translations sync. Build exit 0, **6 optional/platform WARNING, 0 ERROR, 6 upstream SyntaxWarning**. Không full/build/API lại chỉ vì sửa tài liệu |
| Whisper/GPT | Whisper source/Final cũ đã pass, kể cả một job EXE mới sau 429 cũ; GPT source/Final cũ đã pass. Không tự retry Whisper hoặc chuyển dấu pass API đó sang Lifetime |

Năm skip full gồm QtMultimedia do offscreen và bốn TTS/service; native playback sau đó được
đo riêng. Không đổi số skip lịch sử hoặc suy TTS online pass. Google không áp quy tắc xưng hô
có hướng như LLM; một câu dịch ổn chưa nghiệm thu phần đó.

## 4. Phồn thể: đã có raw và nguyên nhân gần, không đo lại cùng case

Một request ForcedAligner local trên runtime S5 R2, revision
**c7cbfc2048c462b0d63a45797104fc9db3ad62b7**, `strict-raw-v1`, deadline **180 s**,
cùng audio public **67.263 sample** và reference phồn thể tường minh do agent chuẩn bị.
Reference không phải request lịch sử được khôi phục; text/raw chỉ giữ local, không trong Git.

- **13 token; lexical toàn câu khớp thứ tự và script.** Chỉ **token 7** trả start **2080 ms**,
  end **2000 ms**: interval đảo **−80 ms**. Không mất chữ; các token còn lại không có lỗi
  zero-length/overlap/bounds trong phép đo này. Toàn span đầu/cuối **400–3680 ms**.
- `validate_alignment()` chặn đúng điều kiện `start < end`; thông báo hiện tại gộp với
  zero-length/overlap/out-of-audio. **Phồn thể chưa đạt acceptance.** Không gọi helper exit 0
  là alignment pass; helper chỉ thu bằng chứng thành công.
- Diagnostic **48,297 s**; load **43,953 s**, inference **1,360 s**. Raw lưu trước validate.
  Runtime/reader đóng; lease reacquire/release và manifest/lock/bridge/audio unchanged pass.
- Không swap/clamp/interpolate timestamp, bỏ token, xuất prefix, đổi script thành giản thể
  hoặc copy timing giản thể để ép pass. Không đổi pin/model/policy. Đường review chỉ được
  dùng với timing có bằng chứng đo; không gán việc agent tự đoán thành user override.

Nếu điều tra tiếp, đọc raw và code trước; chỉ chạy phép đo mới có giả thuyết, dữ liệu và mục
đích phân biệt rõ. Lỗi raw model đã biết không tự chứng minh app sai. Không hỏi user không
biết tiếng Trung chấm reference, hoặc lặp request y hệt để thử vận may. Chỉ sửa app khi có lỗi
tái hiện thuộc app; giữ nghiêm coverage/script/timing và báo giới hạn thực.

## 5. Công việc còn lại và cách tiếp tục

**Cập nhật sau khi user chọn media, 2026-09-08:** đã thử 60 s đầu của video 111,333 s;
không hỏi lại đường dẫn. Resolve file gốc từ `reports/source-preflight.json` trong
`build/asr-session-evidence/VC-UserClip-20260908-114035/`, không chép path/tên media vào Git.
Một job Lifetime/Qwen 0.6B exit 5 / 46,375 s, 94 token, sáu token lỗi timing; raw review
giữ nguyên/0 override/pending true, Community-1 chưa chạy. Chữ ASR còn khác phụ đề Trung
trong hình. Đọc `reports/asr-diagnosis.json` trước; không chạy lại cùng job để thử vận may.
`outputs/reference-vi-preview.mp4` và `reference-vi-edited.srt` là **bản biên tập đối chiếu
13 cue từ phụ đề có sẵn trong hình**, timing hiển thị đo ở 25 mẫu/s; không phải ASR đã pass.
Bản Google từ cùng reference giữ riêng vì sai thuật ngữ. User chưa phản hồi bản Việt này;
51,333 s còn lại chưa thử. EXE test đã dọn; artifact/runtime gốc giữ nguyên. Quyền chọn clip
không tự mở S6, đổi pin/model/policy, job có phí hoặc commit/push.

1. Ưu tiên mục tiêu phụ đề Việt. Dịch/xuất/ghép trên EXE cho clip mẫu đã pass; không thêm lượt
   giống vậy. Nếu user muốn tiến sang video thực tế nhiều câu/người nói, cần xác định một
   media cụ thể và phạm vi thử nhỏ; không quét media riêng hoặc tự mở corpus S6. Agent chuẩn
   bị/runs kỹ thuật, chỉ gom câu hỏi về chọn media, dịch vụ có phí hoặc chất lượng bản Việt.
2. Scribe chỉ khi user chọn **ElevenLabs / scribe_v2**, endpoint code hiện tại
   **https://api.elevenlabs.io/v1/speech-to-text**, audio ngắn cụ thể và có key đúng provider.
   Chưa có lựa chọn thì giữ chưa nghiệm thu. Không xin key vô cớ hoặc dùng key gateway thay.
   Soniox vẫn có khoản timing zero-duration từ lượt cũ; không tự resubmit upload.
3. Nếu user chọn **gpt-5.6-terra** cho dịch, timeout tường minh **300 s**, xác định endpoint
   và quyền LLM riêng. Mỗi job có phí cần user chọn model/media rõ; quyền job cũ đã dùng.
   Không lấy STT key làm LLM key hoặc tìm key trong chat cũ/checkout/AppData/log/env/artifact.
   Nhập key bằng password/getpass, giữ RAM; không chat/argv/env/file.
4. SIP chỉ điều tra khi có triệu chứng mới hoặc giả thuyết kiểm chứng cụ thể. Không loop GUI/
   stress/full để tích pass, không đổi Qt, tắt GC/SIP destructor hoặc nới timeout để che lỗi.
   Nếu crash, giữ PID/hash/time/exit/WER/dump local; không suy lỗi automation focus là lỗi app.
5. S6 còn nguyên phạm vi chưa giao: tập video có nhãn, video dài, CER/timing/speaker/xưng hô,
   thời gian chỉnh tay, chi phí/RAM/VRAM, so baseline và lựa chọn mặc định theo bằng chứng.
   Khi hết việc độc lập trong scope review, báo rõ điều kiện còn thiếu và dừng review; không
   thay phần cần lựa chọn bằng gate đã pass hoặc tự gọi job có phí.

## 6. Vị trí evidence và runtime

Sau yêu cầu dọn thư mục ngày 2026-09-08, resolve các scratch dưới
**`build/asr-session-evidence/` trong checkout ASR-S3**, giữ basename bên dưới;
không còn nằm cạnh checkout. Bảy thư mục đã được di chuyển cùng volume, kiểm tra
**2.710 file** khớp SHA-256/size/mtime. `relocation-20260908.json` ở root evidence
giữ mapping đường dẫn cũ/mới. Script/report lịch sử có thể còn đường dẫn cũ;
không chạy lại helper create-only trực tiếp. Các bản sao EXE/`_internal` dùng test,
cache và build intermediates đã dọn vào Thùng rác; artifact gốc/runtime vẫn giữ
nguyên. Metadata build đã nén và kiểm tra từng file trong report cleanup của
`VC-Lifetime-VI-Review-20260908-092244`. Không tìm credential:

- **VC-Lifetime-VI-Review-20260908-092244**: `README.md`; `outputs/lifetime-vi.json`,
  `outputs/lifetime-vi.srt`, `outputs/lifetime-vi-captioned.mp4`; `reports/frozen-google.json`,
  `reports/frozen-srt.json`, `reports/frozen-synthesis.json`, `reports/frozen-verification.json`,
  `reports/synthesis-verification.json`, `reports/final-verification.json`; phồn thể ở
  `reports/traditional-request.json`, `outputs/traditional-raw-spans.json`,
  `reports/traditional-diagnosis.json`. Scripts có command đã resolve, không rerun vào output cũ.
- **VC-Vietnamese-Preview-20260908-091203**: Google source report/JSON/SRT/preview và bản agent
  biên tập riêng. **VC-PostLifetime-Review-20260908-085948**: audit cũ và đặc tả phồn thể;
  các dòng chưa chạy/chưa user trả lời ở đó đã được kết quả mới thay thế.
- **VC-Lifetime-Media-20260907-2334**: `sources/public-zh.wav`, `outputs/qwen-hybrid.json`,
  native playback/review/ASR evidence. **VC-Lifetime-Cancel-20260908-0714**: hủy decode binary.
- **VC-S52-SIP-Diag-20260907-221507**: dùng **native-stack-unwind.txt**, không dùng các bản
  unwind thử sai. Crash cũ ở Final PID **52400**, **0xc0000005 / offset 0xe58e**; Settings
  **0x13a26**. Chỉ hai vấn đề lifetime có regression red→green; chưa có crash reproducer tất định.
- Runtime giữ tại **build/S5-Qwen-Runtime-20260907-R2/** và
  **build/S51-Community1-Runtime-20260907/**. Qwen 0.6B revision
  **5eb144179a02acc5e5ba31e748d22b0cf3e303b0**; Community-1 revision
  **3533c8cf8e369892e6b79ff1bf80f7b0286a54ee**, manifest SHA-256
  **8af6543a4f173c8a3c19c84c802c57a4f4ded1ccf242ad23c2fee6b675068447**.
  Không xin lại HF token/tải lại model hoặc copy/move venv rồi gọi portable.

Final verify của lượt mới giữ **580 hash gốc/copy**, Final cũ và hash/mtime năm file evidence;
không process test/request temp/ASS persist. Monitor ban đầu đếm nhầm Python launcher của
chính nó; snapshot độc lập rỗng, đã loại/report ancestor và verify pass. Không có job rerun.

## 7. Contract và bàn giao

Identity là toàn PCM16 mono 16 kHz + sample count, gồm tail; legacy không tự verified.
JSON/project giữ metadata, SRT không giữ identity/context. Pending chỉ xóa sau diarization;
union coverage ≥80% không phải acoustic probability. Không trộn Community-1 lên native labels.
Cache fixture dùng RAM; S2 có thể ghi cache values dù tắt reads. QThread luôn wait trước khi
ra scope, subprocess luôn `child_environment()`, không GPU imports vào Qt process.

Nếu sửa code do lỗi có bằng chứng: test gần và gate liên quan; đổi lifetime/metadata/runtime
thì full offline. Build chỉ khi cần, dùng spec duy nhất với tên/output/work/cache/temp mới,
báo đủ bốn gate artifact và source/bundle match; không dùng source pass thay EXE. Chỉ metadata
không nhạy cảm vào Git. Cập nhật status/implementation bằng evidence thực; báo file đã sửa,
gate mới/kế thừa/fail/skip/chưa chạy. **Dừng review; không tự S6/commit/push.**
