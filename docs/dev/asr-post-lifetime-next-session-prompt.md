# Prompt phiên tiếp theo — sau nghiệm thu Lifetime local/media và hủy decode

Tiếp tục tại checkout **VideoCaptioner-ASR-S3** user chỉ định, nhánh **codex/asr-s3-native**.
Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất của `status.md` và phần S5.2 trong
`docs/dev/asr-implementation-2026-09.md`. Đọc `asr-s52.md`, `asr-local-s5.md`, `asr-s41.md`,
`asr-alignment-s2.md` hoặc `architecture.md` khi cần đúng domain.

**Agent tự kiểm thử kỹ thuật, không yêu cầu user xác nhận từng nút.** Chỉ gom checkpoint cho
chất lượng cần người nghe/đọc, chọn media riêng, chọn job tính phí hoặc nhập credential kín.
Không giao lệnh placeholder cho user. Phân biệt agent đo, user xác nhận, evidence kế thừa,
chưa chạy và bị chặn. Lời yêu cầu “tiếp tục” trước đó không phải xác nhận chất lượng audio.

**Mục tiêu phiên này:** đưa checkpoint chất lượng đã chuẩn bị cho user, khoanh vùng các gate còn
mở và chỉ thực hiện phần có dữ liệu/quyền phù hợp. Local/media/playback/hủy decode trên Lifetime
đã pass; không lặp lại để có thêm số pass. **Chưa S6**, không benchmark corpus, đổi engine mặc
định, tự commit/push/tag/release. Quyền submit/push cuối phiên bàn giao chỉ chốt ba tài liệu bên
dưới, không tự áp dụng cho thay đổi mới. Lưu prompt không tạo task hoặc automation mới.

## 1. Snapshot và dữ liệu phải giữ

- Baseline trước chốt tài liệu: **16e410de6b1c6b336f79cc506a042d3d9e0927c8**. Commit bàn giao
  sau đó chỉ có **status.md**, **docs/dev/asr-implementation-2026-09.md** và **prompt này**.
  Lấy HEAD thật từ Git, đối chiếu log/ancestry và HEAD user bàn giao; không ép HEAD về 16e410d.
- Code Lifetime: **e6c0074250df41b5da4b7eaa71b2e9f21e4adcab**, parent **7e28895**; S5.2
  **073510d** là ancestor. Không có code fix mới trong các lượt nghiệm thu 2026-09-07/08.
  Chạy `git status --short --branch` trước sửa và giữ thay đổi có sẵn; không reset/clean/stash.
- Artifact **dist/VideoCaptioner-ASR-S52-Lifetime-20260907/**, EXE cùng basename:
  **31.161.900 byte**, local **2026-09-07 22:39:32**, SHA-256
  **b2dfe8692266fd08dc2471f54838385b975c6ebfe0839d8aa1d5436b38a75f78**.
  Onedir **580 file / 237.667.204 byte**; **218 module** source/PYZ đã so khớp lúc build.
- Giữ Final cũ **dist/VideoCaptioner-ASR-S52-Review-20260907-Final/**, SHA-256
  **457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649**.
  Không đổi media, `.env`, cookies, AppData, work-dir, logs, runtime hoặc artifact cũ.
- Nếu có lý do chạy GUI/CLI mới: tạo scratch chưa tồn tại, chỉ copy **EXE + `_internal/`**,
  so hash; tạo AppData/cache/config/temp/lease mới. Không lấy settings/media/log từ artifact.
  Không rerun helper create-only của scratch cũ hoặc ghi đè output đã nghiệm thu.
- Python đã dùng **3.12.13**, có sẵn ở venv của checkout VideoCaptioner bên cạnh; worktree
  ASR-S3 không có `.venv` riêng. Xác minh import đúng checkout trước khi chạy. FFmpeg đã có sẵn.
  Không dùng Python 3.14 trên PATH, uv sync/cài global, nâng Qt hoặc thêm GPU vào venv Qt.

## 2. Gate đã pass — đọc bảng mới nhất, không phục hồi nợ cũ

| Gate | Snapshot và giới hạn |
| --- | --- |
| Lifetime local hybrid thật | Qwen **0.6B → strict alignment → Community-1 → JSON/SRT** trên cùng EXE Lifetime, public Chinese **4,204 s / 67.263 sample**; exit 0 / **40,844 s**, **1 cue / 13 token IDs / 400–3680 ms / 1 speaker assigned**, identity khớp, pending false |
| Cache và runtime | Cache mới trống trước job → MISS; sau có recognition/alignment/diarization riêng. Status/probe pass; health Qwen+aligner **55,171 s**, Community-1 **23,438 s**. Không bridge còn lại, lease acquire/release lại pass |
| SRT Lifetime | EXE xuất từ JSON, `--no-optimize --no-split --no-translate`, exit 0 / **0,281 s**; text/timing khớp, không nhận dạng/upload lại |
| Native playback | Source Windows **7 pass / 1 warning / 6,04 s**, zero skip, gồm H.264 Play/seek. GUI Lifetime có moving frames/playhead/inspector, seek **2.010 ms** rồi Play đúng vị trí; sau EOS, frame đổi khi Play tiếp |
| Editor/review | Lifetime GUI save/reopen JSON+SRT; typed reload giữ IDs/text/timing. Review raw/2 token/1 override/identity/pending giữ nguyên; mở lại yêu cầu xác minh audio. Không ASS |
| Hủy decode trực tiếp trên binary | **Đã pass ngày 2026-09-08**: FFmpeg PID 31208 đã chạy **13,618 s**, sample còn sống **66 ms trước click**; app hủy cây process, monitor 50 ms ghi child biến mất sau **0,875 s**. Decode temp được dọn, GUI phục hồi và xác minh FLAC mới pass |
| Hủy: giới hạn phép đo | Click+capture **0,483 s** gồm overhead công cụ, không phải latency riêng Qt. Nguồn concat hữu hạn từ PCM tổng hợp, không chèn delay/mock decoder. Đây là EXE thật; khác test source 0,578 s trước đó |
| Shutdown Lifetime | Các lượt **966,328 / 696,797 / 374,719 s** đều X→exit 0; các snapshot sau đóng không child/runtime, log chỉ update-check, không traceback/InfoBar. Lượt cuối không WER mới sau hơn 25 s. Không chứng minh mọi crash SIP đã hết |
| Full/static/build kế thừa | Full **1.119 passed / 5 skipped / 51 deselected / 145,95 s**, gồm CLI106; ruff pass, pyright 0/0, translations sync. Build exit 0, 6 optional/platform WARNING, 0 ERROR, 6 upstream SyntaxWarning. Không rerun full/build cho tài liệu |
| Skip full | QtMultimedia do offscreen và 4 TTS/service; gate native playback sau đó đã đo riêng. Không đổi số skip lịch sử hoặc suy TTS online pass |
| Whisper API | **Final cũ đã pass một job mới sau 429 cũ**: videocaptioner / whisper-1 / public Chinese → Community-1 → JSON/SRT, exit 0. Không còn nợ “Whisper EXE fail 429” cần tự retry |
| GPT hybrid | Source/Final EXE đã smoke thật ở snapshot trước. Không tự chuyển dấu pass sang Lifetime hoặc gọi lại API chỉ do GUI đổi lifetime |

**Local ASR trên Lifetime, native playback và hủy giữa decode trên binary đều không còn là gate
chưa đo.** Prompt `asr-lifetime-next-session-prompt.md` là kế hoạch cũ đã thực hiện; các dòng
“chưa đo” trong lịch sử ngày 2026-09-07 không ghi đè kết quả mới ngày 2026-09-08.

## 3. Việc cần làm tiếp và checkpoint

1. **Đưa output đã có để user nghe/đọc, không chạy ASR lại.** Resolve scratch
   **VC-Lifetime-Media-20260907-2334** cạnh checkout. Dùng `sources/public-zh.wav`,
   `outputs/qwen-hybrid.json`, `outputs/qwen-hybrid.srt`, `outputs/quality-preview.mp4`.
   Clip dài **4,204 s**, audio public + SRT thật trên hình nền tổng hợp; không coi là nghiệm thu
   synthesis pipeline của app. Gom một checkpoint: chữ có khớp lời nói, cue **0,400–3,680 s**
   có hợp lý, một giọng có nhất quán. Không suy danh tính/giới/quan hệ. Một giọng không đủ chấm
   accuracy nhiều speaker hoặc xưng hô Trung→Việt. Không ghi user đã xác nhận khi chưa có trả lời.
2. **Khoanh vùng phồn thể strict bằng evidence có sẵn.** Đọc đúng ghi nhận S2/S5/review liên quan,
   xác định input, lỗi lexical/timing và điều kiện còn thiếu trước khi đề xuất phép đo nhỏ tiếp.
   Không tự đổi script/normalize chữ/clamp timestamp/bỏ token/cắt prefix để ép pass; không đổi
   pin/model/policy. Nếu cần audio khác hoặc inference mới ngoài scope đã chọn, gom lựa chọn với
   checkpoint; agent vẫn tự chuẩn bị command/output và tự chạy phần kỹ thuật được giao.
3. **Scribe chỉ khi user chọn dịch vụ và có credential đúng provider.** Chuẩn bị trước provider,
   endpoint, model và audio ngắn cụ thể; nhập key qua password/getpass, không chat/argv/env/file.
   Chưa có lựa chọn thì giữ chưa nghiệm thu, không xin key vô cớ hoặc dùng gateway key thay.
4. **SIP chỉ điều tra tiếp khi có triệu chứng hoặc giả thuyết kiểm chứng cụ thể.** Không loop stress
   vô hạn/rerun full/GUI để tích số pass. Nếu crash thật, giữ đúng PID/hash/time/exit và WER/dump
   local, rồi khoanh vùng nguyên nhân. Không đổi Qt/framework, tắt GC/SIP destructor hoặc nới
   timeout để che lỗi. Không sửa app chỉ vì UI automation mất focus hoặc bị cửa sổ khác che.

Trong lúc chờ checkpoint, agent có thể đối chiếu metadata/output, rà gate/phồn thể từ source và
chuẩn bị test nhỏ phù hợp. Không thay việc còn cần lựa chọn bằng lặp lại gate đã pass. Khi hết
việc độc lập có ích, báo blocker cụ thể và dừng review; không tự chuyển S6 hoặc job có phí.

## 4. Runtime, evidence và giới hạn điều tra

Runtime dùng nguyên tại chỗ, **không copy/move venv rồi gọi portable**:

- Qwen/ForcedAligner: **build/S5-Qwen-Runtime-20260907-R2/**, không chọn bản S5 đầu.
- Community-1: **build/S51-Community1-Runtime-20260907/**, đã có model và inference thật;
  revision **3533c8cf8e369892e6b79ff1bf80f7b0286a54ee**, manifest SHA-256
  **8af6543a4f173c8a3c19c84c802c57a4f4ded1ccf242ad23c2fee6b675068447**.
  Không xin lại HF token/chấp nhận điều kiện/tải model chỉ để dùng runtime đã cài.
- Qwen 0.6B revision **5eb144179a02acc5e5ba31e748d22b0cf3e303b0**; aligner revision
  **c7cbfc2048c462b0d63a45797104fc9db3ad62b7**, policy **strict-raw-v1**.

Scratch cạnh checkout; chỉ tìm theo basename/evidence, không tìm credential:

- **VC-Lifetime-Media-20260907-2334**: `README.md`, `reports/media-verification.json`,
  `reports/final-verification.json`, native test/log, GUI actions và clip/output nêu trên.
- **VC-Lifetime-Cancel-20260908-0714**: `README.md`, `reports/verification.json`,
  `reports/gui-children.json`, `reports/gui-actions.json`, `reports/post-close.json`,
  inventory và `outputs/post-cancel-review.json`. Owner/monitor/GUI đã thoát.
- **VC-S52-SIP-Diag-20260907-221507**: `README.md`, **native-stack-unwind.txt** và lifetime
  regression/build logs. `native-stack.txt`/`native-stack-with-images.txt` là unwind thử sai,
  không dùng làm bằng chứng. Không upload dump hoặc quét heap tìm dữ liệu/credential riêng tư.
- **VC-S52-Accept-20260907-204008**: fixture/Whisper evidence. Owner có key đã thoát; không
  chạy lại owner/job trả phí hoặc tìm key cũ trong scratch này.

Crash SIP cũ: Final PID **52400**, exit **3221225477 / 0xc0000005**, offset **0xe58e**; Settings
trước đó **0x13a26**. Unwind qua QApplication destruction/SIP wrapper trong cleanup. **24 process
baseline/stress trước sửa đều exit 0**. Chỉ hai điều kiện lifetime có reproducer red→green;
không khẳng định Save/InfoBar/automation là cùng nguyên nhân hoặc mọi access violation đã hết.

## 5. Contract và cách bàn giao tiếp

- Không tìm API key trong chat cũ, checkout khác, AppData, log/artifact hoặc environment chung.
  Quyền job Whisper cũ đã dùng. Không gọi lặp command sau 429, đổi provider/model để vượt parser,
  resubmit Soniox hoặc trộn Community-1 lên native speaker labels.
- Nếu user chọn dịch bằng `gpt-5.6-terra`, timeout tường minh **300 s**, đúng endpoint/quyền LLM;
  không suy key STT dùng được cho dịch. Mỗi job tính phí phải được user chọn với model/audio rõ.
- Identity: toàn PCM16 mono 16 kHz + sample count, gồm tail; legacy không tự có identity.
  JSON/project giữ metadata, SRT không giữ identity/context. Pending chỉ xóa sau diarization;
  assigned/unknown/ambiguous/overlap và union coverage ≥80% không phải xác suất acoustic.
- Cô lập AppData/cache/config/lease; S2 có thể ghi cache values dù tắt cache reads, fixture dùng
  cache RAM. QThread luôn wait trước khi object ra scope. Không full đồng thời build/GPU jobs.
- Nếu sửa code có nguyên nhân rõ: test gần lỗi và gate liên quan; đổi lifetime/metadata/runtime
  thì full offline. Khi cần build, dùng spec duy nhất với tên/output/work/cache/temp mới, báo đủ
  bốn gate build, source/bundle match và giới hạn media/online. Không ghi đè artifact cũ.
- Chỉ metadata không nhạy cảm vào Git; không transcript/media/absolute local path/credential.
  Cập nhật status/implementation bằng bằng chứng thực, báo đúng file/gate mới và kế thừa.
  Kết thúc **dừng review**, không tự S6/commit/push dù phiên bàn giao trước đã được phép submit.
