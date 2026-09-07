# Prompt phiên tiếp theo — hướng dẫn user test nghiệm thu S5.2

Tiếp tục tại checkout user chỉ định, worktree `VideoCaptioner-ASR-S3`, nhánh
`codex/asr-s3-native`. **Mục tiêu là hướng dẫn tôi trực tiếp test nghiệm thu**, chuẩn bị các file
và lệnh cần thiết, quan sát/đối chiếu kết quả cùng tôi. Không chỉ đưa một checklist dài rồi kết thúc;
không tự chạy hết test nền và gọi đó là user đã nghiệm thu. Chưa mở S6 hoặc làm tính năng mới.

## 1. Snapshot phải xác minh trước

- **Code S5.2:** `073510db54e5a24ab3deba3626d53279d478813f`, parent `27be883`, đúng **35 file**
  trong manifest. Code S5.1 `8599965` là ancestor. Code S5.2 đã commit/push theo yêu cầu user;
  HEAD còn có commit tài liệu bàn giao sau code. Kiểm tra `git status --short --branch`, `git log`
  và ancestry, không reset/clean/stash hoặc overwrite thay đổi user.
- Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`, `docs/dev/asr-s52.md`, phần
  bàn giao S5.2/roadmap trong `docs/dev/asr-implementation-2026-09.md`. Đọc architecture và domain
  tương ứng khi cần: `asr-local-s5.md`, `asr-alignment-s2.md`, `asr-s41.md`, `asr-native-s3.md`,
  `asr-context-s4.md`. Dùng `rg` để xác minh tên UI/flag/call site trước hướng dẫn.
- **Artifact đã test:** `dist/VideoCaptioner-ASR-S52-Review-20260907-Final/`, EXE cùng tên folder,
  **31.161.859 byte**, local **2026-09-07 19:11:44**, SHA-256
  **`457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649`**.
  Onedir trước GUI **580 file / 237.667.163 byte**; **218 module / 39 resource** khớp source,
  không bundle GPU. Build exit 0; 6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream.
- Runtime Qwen/aligner **`build/S5-Qwen-Runtime-20260907-R2/`**; Community-1 ready
  **`build/S51-Community1-Runtime-20260907/`**. Không chọn bản Qwen S5 đầu hoặc thư mục
  `S5-Pyannote-Dependencies-20260907` chỉ có dependency. Không move/copy venv rồi gọi portable.
  Community-1 revision **3533c8cf8e369892e6b79ff1bf80f7b0286a54ee**, manifest SHA-256
  **8af6543a4f173c8a3c19c84c802c57a4f4ded1ccf242ad23c2fee6b675068447**; không cần HF token để inference.
- Python **3.12.13**, interpreter/FFmpeg có sẵn; worktree không có `.venv` riêng. Tìm interpreter
  phù hợp, xác minh import đúng checkout. Không dùng Python 3.14 trên PATH, không uv sync/cài global,
  nâng pin/dependency, sửa generated version/QM hoặc đưa GPU libraries vào venv Qt.

## 2. Cách phối hợp với tôi

1. Mở đầu bằng trạng thái ngắn: đã có gì, còn gate nào, đang dùng binary nào. Mặc định hướng dẫn
   **GUI trên bản EXE test riêng**; CLI dùng khi tính năng chỉ có CLI hoặc cần thu exit code.
2. Agent tự chuẩn bị thư mục mới, mẫu kiểm thử và lệnh đầy đủ. Mỗi lần đưa **1–3 thao tác cụ thể**:
   bấm ở đâu, chọn file nào, chờ trạng thái nào, kết quả pass/fail nhìn thế nào. Không bắt user tự
   đoán đường dẫn hoặc sửa lệnh placeholder. Cho tôi phản hồi ở checkpoint cần quan sát/nghe thật.
3. Phân biệt **user xác nhận**, **agent đo tự động**, **kế thừa snapshot**, **chưa chạy**, **bị chặn**.
   Chưa nhận phản hồi của tôi thì chưa được đánh dấu user pass. Không coi thời gian chờ là đồng ý.
4. Khi lỗi: giữ output/review/log riêng, giải thích ngắn, khoanh vùng tái hiện. Không tự sửa source,
   đổi policy/threshold/model để ép pass; đề xuất hướng sửa và chờ tôi yêu cầu xử lý lỗi. Vẫn tiếp
   tục những gate độc lập. Không để thiếu một key chặn cả phiên.

## 3. Chuẩn bị an toàn, không cần hỏi lại cho việc đọc/copy kiểm thử

- Giữ media, `.env`, cookies, AppData, work-dir, logs, mọi runtime/artifact S4–S5.2 hiện có.
  Tạo thư mục scratch **mới chưa tồn tại**, tách nguồn, output, review, log và báo cáo.
- Copy **EXE + `_internal/`** vào bản onedir test mới; không copy AppData/media/log của artifact
  gốc. So SHA-256 trước chạy, dùng bản copy cho GUI/API. Giữ nguyên venv runtime tại chỗ.
- Ưu tiên [audio Trung public Qwen 4,204 s](https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_zh.wav)
  đã dùng ở S5.2; tìm file media này trong scratch bàn giao bằng tên/identity, không đọc credential
  hoặc log cũ để tìm key. Nếu thiếu, tải lại từ đúng nguồn public hoặc để user chỉ định media.
  Mẫu public [pyannote 30 s](https://github.com/pyannote/pyannote-audio/blob/main/tutorials/assets/sample.wav)
  chỉ dùng smoke speaker nhỏ; không mở corpus S6. Video riêng chỉ dùng khi tôi chọn/chấp thuận.
- Chuẩn bị hai audio **tổng hợp** khác nội dung nhưng cùng duration, một bản đổi tên/lossless,
  JSON/review có identity và bản legacy không có identity. Tạo qua API typed của app, không sửa raw
  checksum của file thật. Dữ liệu tổng hợp chỉ test contract/UI, không chấm chất lượng ASR/speaker.
- Key gateway của S5.2 đã bị bỏ khỏi RAM khi owner thoát. **Không tìm lại trong chat cũ, lịch sử,
  checkout khác, log/artifact hoặc environment chung.** Nếu cần, cho user nhập kín qua password/
  getpass, giữ RAM; không argv/env/file hay terminal history. Không yêu cầu dán key vào chat.
  HF, gateway và Scribe là ba loại credential khác nhau. Không tự chấp nhận điều kiện dịch vụ.
- Gate trả phí phải nêu rõ provider/endpoint/model/audio trước chạy. Chỉ chạy khi credential/quyền
  và lựa chọn của user phù hợp. Không gọi thêm model để dò, không đổi provider ngầm. API status
  probe, local health và inference là các gate khác nhau.

## 4. Thứ tự test cùng user và tiêu chí

### A. Khởi động, settings và đóng app

- Mở bản EXE test, để user xác nhận giao diện lên và phản hồi bình thường. Mở settings, chuyển
  engine rồi quay lại; riêng mở settings không được tự download/nạp model/probe API.
- Cho user thử nút quản lý mô hình, chọn đúng runtime đã cài. Nếu health cần thiết, bấm tường minh;
  báo đó là load/health, chưa chứng minh inference. Không cần tải Community-1/HF token lại.
- Quan sát ít nhất 25 s, thử đóng bằng nút X/WM_CLOSE. Đo đúng process do test tạo và cleanup,
  đọc log của bản test. Không kết luận pass chỉ từ exit 0.
- **Known issue:** `BottomInfoBarManager has been deleted` trong `qfluentwidgets` eventFilter
  line 432 khi đóng sau thông báo update, tái hiện ở cả S5.1 Final và S5.2 Final. Cả hai sống
  25,047 s, WM_CLOSE exit 0, không process sót nhưng log teardown chưa sạch. Không bấm cài update
  hoặc đổi generated version để tránh điều kiện lỗi.
- **Known flake riêng:** test Settings exit **3221225477**, faulthandler `<no Python frame>`;
  WER `sip.cp312-win_amd64.pyd`, **0xc0000005 / offset 0x13a26**, PyQt5 5.15.11, sip 12.18.0,
  QFluentWidgets 1.8.4. Đã xảy ra khi không có build/GPU nền. Chưa chứng minh quan hệ nhân quả
  giữa lỗi này với InfoBar; rerun pass không phải fix. Nếu tái hiện, thu thời điểm/exit/stack nhỏ,
  không dump dữ liệu riêng tư; không sửa framework hoặc tăng mock timeout để che lỗi.

### B. Mở review, chọn audio và giữ pending — không upload

Đây là gate ưu tiên để user thấy trực tiếp phần S5.2.

1. **Nhận dạng → Mở bản review ASR**, chọn review tổng hợp đã chuẩn bị. Trước khi chọn nguồn,
   thông báo chỉ nói giữ identity, chưa được tự báo audio khớp.
2. Bấm **Chọn âm thanh gốc…**, chọn audio sai cùng duration: phải báo mismatch, không nạp model/
   upload; export bị chặn. Chọn đúng nguồn hoặc bản đổi tên/lossless: báo khớp, UI vẫn phản hồi.
3. Chọn token có timing lỗi tổng hợp, nhập mốc đã quy định cho fixture, **Áp dụng → Hoàn tác →
   Làm lại**. Raw giữ nguyên, override riêng; xuất JSON giữ cue/token IDs và `edited`.
   Không dùng mốc fixture để sửa audio thật hoặc bỏ token 0 ms nhằm vượt parser.
4. Lưu review sang tên mới, đóng/mở lại, kiểm tra lại nguồn. Review có diarization pending chỉ
   xuất timing; JSON/editor vẫn giữ pending. Mở lại không được tự upload hoặc inference.
5. Mở review/JSON/SRT legacy: phải dùng được và báo **chưa xác minh**, không tự thêm identity sau
   diarization. Cancel/đóng dialog trong lúc kiểm tra nguồn phải dọn worker, không treo app.

Agent có thể dùng các lệnh dưới để đối chiếu; phải thay biến bằng đường dẫn đã kiểm tra và output
chưa tồn tại. `$exe` là binary trong bản copy test, `$diarizationRoot` là runtime cũ tại chỗ:

```powershell
& $exe asr-review $review --audio $originalAudio -o $reviewedJson
& $exe local-diarize $reviewedJson --audio $originalAudio --runtime $diarizationRoot -o $speakersJson
```

Wrong audio + identity phải exit 5 **trước runtime**, kể cả chỉ định runtime không tồn tại;
không output partial. `local-diarize` không nhận `--config`; đừng lẫn parser error exit 2 với gate
runtime/API. `transcribe`/`subtitle`/`asr-review` nhận `--config` sau subcommand khi cần.

### C. JSON → Video Editor → JSON/SRT — giữ association

- Mở kết quả có identity vào editor bằng handoff hoặc import; cho user xem timing/cue, sửa speaker
  tường minh, undo/redo rồi Save project tên mới. Không suy danh tính/giới/quan hệ/người nghe/voice.
- Mở lại project và so cue/token IDs, timing, raw/provenance, speaker override, context confirmed/
  locked và pending nếu có. Normal save vẫn **editor-project-v1 JSON + SRT**, ASS chỉ Save as ASS.
- SRT không giữ identity/metadata. Việc mở editor không tự chứng minh video được chọn đúng nguồn;
  dùng kiểm tra audio của review/local-diarize khi cần xác minh, không thêm nhãn verified giả.
- Với speaker: giữ unknown/ambiguous/overlap, không ép đủ người nói theo reference bằng cách đổi
  threshold. Policy union span + đúng một speaker phủ ≥80% không phải acoustic probability.

### D. Whisper API từ EXE — gate còn thiếu do HTTP 429

- User chọn đúng preset `videocaptioner`, endpoint **https://api.videocaptioner.cn/v1**,
  model **whisper-1**, Chinese `zh`, timing cấp câu, bật local diarization. Agent xác minh cấu hình
  thực, runtime và local health **trước upload**. Dùng audio public ngắn hoặc media user chấp thuận.
- Chỉ chạy **một command/job tường minh** khi user sẵn sàng với credential/quyền hiện tại. Policy
  app S1 có tối đa 3 attempt hữu hạn trong một command; không tự chạy vòng lặp command sau 429.
  Nếu tiếp tục 429, ghi blocked/service và dừng gate này; không suy key sai hoặc đổi provider/mini.
- Pass cần request ASR mới từ chính EXE → timed data → Community-1 → JSON/SRT đầy đủ, identity
  khớp nguồn, timing nằm trong duration, pending false, không process sót. Ghi HTTP/exit, counts,
  stage và cache hit/miss. Source pass hoặc local-diarize từ timed JSON cũ không thay gate này.
- Kết quả tham chiếu S5.2: source Whisper **exit 0, 1 cue 0–4000 ms, 43,390 s**; full EXE
  **429 / exit 5, 39,187 s**. EXE local-diarize trên timed source JSON pass 10,157 s, legacy SRT
  pass 9,609 s và vẫn unverified. Không đòi transcript/timing ngẫu nhiên của API phải giống hệt
  reference để ép pass; kiểm tra toàn bộ dữ liệu thực và ghi khác biệt cho user review.

### E. GPT hybrid và Qwen local — xác nhận lại theo lựa chọn user

- GPT **đã pass source/EXE thật**: `gpt-4o-transcribe` → strict Chinese alignment → Community-1
  → JSON/SRT, public 4,204 s, 1 cue **400–3680 ms / 13 token IDs / 1 speaker**, cùng identity
  **67.263 sample**, pending false. Source 70,859 s; EXE 58,312 s. Không cần trả phí lại chỉ để
  đọc kết quả đã có; có thể mở bản sao output cho user kiểm tra trước.
- Nếu user muốn đo job mới, dùng đúng GPT model, chọn runtime **S5 Qwen R2** qua `--qwen-runtime`
  / local_asr.runtime_root cho aligner. Không dùng Qwen recognition thay API. Local health phải
  pass trước upload. Text/timing lỗi giữ full review; không clamp/nội suy/bỏ token/cắt prefix.
- Qwen 0.6B/1.7B và Community-1 đã inference local thật ở S5.1, cả source/EXE. Nếu user muốn test
  local để tránh API, chọn model tường minh, không download/đổi pin. Phân biệt evidence thừa kế
  S5.1 với lần chạy trên binary S5.2 hiện tại; chưa chạy lại thì không ghi đã pass binary mới.
- User nghe/xem output và ghi thời điểm có lỗi text/timing/speaker; agent không tự chấm thay user
  chất lượng xưng hô. Đây là smoke có hướng dẫn, không CER/DER/corpus benchmark hay chọn mặc định S6.

### F. Scribe và phần ngôn ngữ — chỉ khi đủ đầu vào

- Scribe chưa có credential riêng: nếu user muốn test, nhập kín đúng ElevenLabs key. Probe quyền
  và inference **scribe_v2** là hai gate riêng. Giữ timing/speaker/events/native review/remote
  cleanup; không trộn nhãn Community-1 lên native. Thiếu key thì ghi chưa chạy, làm phần khác.
- Không resubmit Soniox chỉ để vượt parser zero-time. Review cũ dùng local/override tường minh.
- Phồn thể strict, speaker accuracy và xưng hô bằng người đọc vẫn chưa nghiệm thu. Chỉ cập nhật
  khi có media/đối chiếu/quan sát tương ứng; không đổi giản-phồn thể hoặc prompt để ép timing pass.
  Nếu test dịch bằng `gpt-5.6-terra`, chọn timeout **300 s** tường minh; app vẫn 1–600/default120.
  Cần đúng endpoint/quyền và lựa chọn LLM; không tự suy key STT có quyền dịch hoặc ngầm gọi thêm
  dịch vụ tính phí.

## 5. Ghi kết quả và dừng đúng phạm vi

- Tạo bảng cùng user, mỗi hàng gồm **gate, nguồn bằng chứng (user/agent/kế thừa), source hay EXE +
  hash/commit, pass/fail/blocked/chưa chạy, expected, observed, bước tái hiện, việc còn lại**.
  Báo cáo chỉ lưu metadata không nhạy cảm vào Git; transcript/media/raw response/log giữ local.
- Gate kế thừa: full offline **1.116 pass / 4 skip / 51 deselect, 131,78 s**; guard output/audio
  thêm sau full có **CLI 106 pass / 2,58 s**, identity fixture **24 pass / 3,44 s**. Tổng 30 test mới,
  ruff pass, pyright 0/0, translations/diff-check pass. Không gọi đây là full 1.118 đã chạy.
- Fixture API alignment phải dùng cache RAM: S2 vẫn retain values khi cache reads tắt. Phiên S5.2
  đã hoàn trả đúng 2 entry tổng hợp do test tạo, rerun xác nhận không tái tạo. Không ghi test vào
  cache/settings/media thật; QThread tests phải wait. Không chạy full cùng build/GPU jobs.
- Không rerun full/build chỉ để đổi tài liệu hoặc chốt Git. Nếu sau yêu cầu sửa code có thay đổi
  cần kiểm thử: chạy test gần lỗi và gate liên quan; metadata/runtime/lifecycle đổi thì full offline.
  Artifact mới phải dùng spec duy nhất và tên/output/cache/scratch mới, đo lại bốn gate build.
- Cập nhật status/implementation theo phép đo thật; giữ khoản chưa nghiệm thu riêng. Kết thúc bằng
  kết quả user đã xác nhận, blocker cụ thể và bước tiếp theo đề xuất. **Dừng review**, không tự mở
  S6, commit/push/PR/tag/release. Quyền commit/push của phiên bàn giao không tự cấp cho phiên này.

Lưu prompt này không khởi chạy phiên test mới. Chỉ thực hiện khi user dùng nó trong phiên tiếp theo.
