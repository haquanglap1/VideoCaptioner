# Prompt tiếp tục triển khai OCR/ASR quality-first

Tiếp tục làm việc tại root repository **VideoCaptioner**, nhánh
`codex/ocr-asr-quality-pilot`. Trả lời tiếng Việt, giữ code/identifier/file name
bằng English. Đây là phiên **tiếp tục triển khai**, không chỉ lập lại plan.

## 1. Mục tiêu và quyền đã có

Ưu tiên **OCR và speech-to-text đủ, đúng trước → phụ đề nguồn → dịch → lồng tiếng**.
Chưa thử thêm giọng, clone nhân vật, tích hợp giọng B hoặc lồng tiếng toàn video.
Không dịch/rewrite sáu câu Việt đã được user chấp nhận.

Được sửa code, chạy test/inference local cần thiết; đã được phép cài/tải phần thiếu
trong project sau inventory, không cài global hoặc đổi cấu hình ngoài repository.
Được commit/push thay đổi liên quan sau review/validation, stage allowlist cụ thể.
Không tự merge pilot vào `master` khi chưa được yêu cầu. Không apply/pop/drop stash,
reset hard, clean, xóa/ghi đè dữ liệu hoặc thay đổi ngoài task. Không đưa media,
model, credential, raw transcript riêng hoặc absolute local path vào Git.

Giữ `.env`, cookies, `AppData/`, `work-dir/`, settings và artifact cũ. Mọi file mới
nằm trong project, ưu tiên một audit root riêng dưới `.tools/`. Không hỏi lại quyền
sửa/test thông thường. Nếu thiếu dữ liệu thực, báo bằng chứng và tiếp tục phần độc lập.

## 2. Đọc và xác minh trước khi sửa

Đọc đầy đủ `AGENTS.md`, `README.md`, mục mới nhất của `status.md`, rồi:

- `docs/plans/ocr-asr-quality-first-2026-09.md`
- `docs/dev/ocr-asr-quality-first-results-2026-09.md`
- Tài liệu domain cần cho phần đang sửa, không nạp cả thư mục.

Nhãn `PLAN ONLY` trong plan là lịch sử phiên lập kế hoạch, không chặn triển khai.
Các ghi chú “OCR dừng” của task bài giảng cũ không áp vào video này.

Baseline implementation: `5ba151ab9819c66dc7b49c005dea9b5e21f018ee`, đã push lên
`origin/codex/ocr-asr-quality-pilot`. Commit chứa prompt này chỉ bổ sung tài liệu;
kiểm live HEAD/remote trước khi suy ra trạng thái hiện tại. `master` và
`origin/master` ở lần kiểm trước cùng `62abacae421d2011948f467d3386d81de9f8879b`.

Giữ hai stash:

- `6a1e12d531cfb0e7408ab5737d02c544902001e2`
- `e61dd7e2cea5eeffd2d64a30b84af1477d504558`

Kiểm status/index/diffs/refs/stashes và remote. Không checkout đè dirty state.

## 3. Nguồn, runtime và evidence cần reuse

Video Bilibili `BV1GFbk6LEVm`, P1 dài **266.566625 s**, **1920×886**.
Media path nằm trong `.tools/bv1gf-20260916-145613/source.json`.
Source SHA-256:
`3e56b8d3349bb2013723617ce856cd44a72f1f5140d81ef1c126a65747d13d90`.
Không tải lại nếu file còn đúng hash.

Audit triển khai chính: **`.tools/ocr-asr-quality-20260916-201453/`**.
Đọc trước khi chạy lại:

- `runtime-manifest-final.json`, `cases.json`, `budget.json`
- `coverage-ledger.json`, `run-ledger.jsonl`, `phase-results.json`
- `quality-report.md`, `preservation-check.json`, `publication.json`
- `ocr-final/results.json`, các checkpoint/report D1/D2
- `ocr-geometry-replay.json`, `negative-feature-probe.json`, `feature-transition-probe.json`
- `exact-frames/manifest.json`, `visual-audit/manifest.json`, `cache-parity.json`
- `qwen-txt/inputs-locked.json`, `runtime-verified.json`, `results.json`, TXT/raw/request WAV
- `p3-roundtrip/results.json`, các project JSON/SRT đã save/reopen.

Evidence cũ giữ nguyên:

- `.tools/bv1gf-20260916-145613/`: source, baseline toàn video, OCR raw/checkpoints/tools.
- `.tools/ocr-compare-20260916-155842/`: crop/gateway reference, VAD on/off, line-selection replay.
- `.tools/bv1gf-prosody-20260916-171148/`: gap frame 30 s, ROI trial, WAV/ASR D1/D2.
- `.tools/bv1gf-clone-20260916-174613/`: original/vocals D3, 38 OCR observations, failed short-ASR.

Runtime thực đã có; verify thay vì tải lại:

- OCR: `.tools/bv1gf-20260916-145613/runtimes/ocr-v6-medium/`.
  Python nằm ở `env/Scripts/python.exe`, không phải `env/python.exe`.
- Faster-Whisper-XXL, FFmpeg/ffprobe và Kim_Vocal_2: audit cũ `tools/`; large-v3 ở `models/`.
- Qwen 1.7B: `.tools/ocr-asr-quality-20260916-201453/qwen-runtime2/`.
  Pin `7278e1e70fe206f11671096ffdd38061171dd6e5`; đã verify và inference CUDA thật.
  Đây là runtime machine-local, chưa được nghiệm thu portable. `qwen-runtime/`
  là lượt cài lỗi trước đó, giữ nguyên, không chọn nhầm hoặc xóa nó.
- Chưa cài ForcedAligner vào Qwen runtime mới vì text gate chưa đạt. Manifest
  alignment ở repo không chứng minh có đầy đủ runtime/weights hoạt động.

Với ASR, **`qwen-txt/inputs-locked.json` là bản chốt WAV thực sự**, ưu tiên nó so
với mục D3 ban đầu trong `cases.json`: D3 dùng `source-107-126-stereo.wav_dump.wav`
sau Kim_Vocal_2, không dùng file trung gian `*_mdx.wav`. Log XXL xác nhận dump
là waveform gửi vào recognition. Không tách vocals lần hai.

## 4. OCR đã làm và lỗi cần sửa tiếp

Đã có worker/resource `ocr_tracking_worker_v2.py`, policy `character-features-v2`.
CLI mới chọn thử bằng **`--tracking characters-v2`**. `characters` và checkbox
quét mới của GUI vẫn là v1; chưa promote mặc định.

V2 sửa floor `0.4 × ROI height` loại dòng 32 px trong ROI 90 px. Khi bbox thay
đổi, so hai frame liên tiếp trên cùng support; giữ candidate quality độc lập
frame trước để phục vụ resume. Không post-merge theo text hoặc xóa cue ngắn.

Kết quả lượt CLI đã đo:

| Ca | Kết quả | Recognition mới / cache hit | Tracking / feature batches |
|---|---|---:|---:|
| D1 OCR 28,8–32,3 s | 2 cue, export hợp lệ; caption 29,4–32,3 s liên tục | 6 / 0 | 105 / 231 |
| D2 OCR 57–63 s | Scan complete, 7 cue, 1 `empty_engine_read`, export exit5 | 16 / 0 | 180 / 288 |

D2 còn các vấn đề riêng:

1. Chữ nền tại khoảng **57.033 s**. Probe thấy detector có box nhưng character
   features có thể toàn blank; chỉ geometry chưa chứng minh có subtitle.
2. Khoảng **62.833 s** tạo cue rỗng từ box nền/transition; raw giữ nguyên.
3. Câu đáp ngắn bị tách khoảng **62.600 s** dù chữ nhìn thấy chưa đổi rõ.
4. Detector/recognizer bỏ interjection hoặc dấu ở mép dòng, đặc biệt khoảng
   **62.900 s**; đây là lỗi recognition riêng, không sửa chỉ bằng tracking.

Hai hướng đã bị loại:

- Mở rộng support hai bên làm background lọt lại, hồi quy fragmentation D1.
- Bắt buộc confidence để khởi tạo track làm mất dòng chỉ có dấu chấm.
  Không thử lại cùng thay đổi threshold mà thiếu giả thuyết/regression mới.

Đọc `exact-frames/` để đánh giá biên theo PTS chính xác. Ảnh trích bằng `-ss` trong
`visual-audit/` chỉ hỗ trợ đọc ngữ cảnh, không dùng thay decoder PTS để chốt frame biên.
Không gọi assistant/gateway reference là human ground truth.

**Bẫy hash checkpoint cần giữ:** lượt CLI đo dùng worker trước cleanup một binding
`cv2` không dùng:

- `candidate-workers/final-measured.py`: SHA
  `14606a29932fc83a68b66658a32d9e670b9b3931540c80eb76c16c2fb7554b60`.
- Worker source được commit: SHA
  `7f0890b8e9efd02291311206a8923f7c083283ee9718cbb13a1f14d33db8f94d`.
- Audit giữ cả hai và companion `candidate-workers/ocr_stream_worker.py`.
  `ocr-final/*.checkpoint.json` là complete scan; D2 fail **quality**, không
  phải partial cần `ocr-resume`. Muốn tái hiện bytes cũ phải chọn explicit bridge
  đã lưu; không sửa hash/checkpoint để làm current worker trông tương thích.
- Nếu tiếp tục đổi semantics sau commit `5ba151a`, tạo policy/worker version mới,
  giữ đường resume v1/v2. Không âm thầm thay semantic v2 đã được commit.

## 5. ASR đã đo; bước tiếp theo có giới hạn

Đã dùng đúng ba recognition mới của Qwen candidate đầu: D1 **27–34 s**, D2
**57–63 s**, D3 **107–126 s**; TXT trước, 0 cache hit, không alignment/diarization,
không prompt đáp án/OCR và không upload audio. Qwen còn khác chữ/lặp/đuôi đáng ngờ.
Chưa có reference nghe đủ chắc để chấm CER/WER hay coi mọi khác biệt với caption là lỗi lời nói.

- Reuse Whisper VAD-on. VAD-off đã thất bại, không mặc định tắt VAD.
- D3 original/vocals baseline 5/6 cue không chứng minh text đúng. Clip 2,8 s cũng
  từng sai/lặp; không lấy cắt càng ngắn càng tốt làm policy.
- Trước lượt mới, kiểm biên audio D1/D3 có cắt lời hay không và chuẩn bị reference
  từ audio có ngữ cảnh; giữ unknown nếu chưa nghe xác định được. Chọn đúng một
  giả thuyết mới, khóa input/config/budget trước inference, không rerun chọn kết quả đẹp.
- Chỉ alignment khi text dùng được; reuse recognition cache. Nếu fallback,
  giữ nguyên cặp text+timing của provider dự phòng và provenance. Không ghép text
  Qwen với giờ Whisper khác lời; có TXT không có timing thì không báo SRT success.
- Gateway `api.videocaptioner.cn` chỉ từng được phép đối chiếu crop OCR bằng
  `gpt-5.6-terra`; không suy thành quyền gửi audio hoặc retry batch timeout cũ.

## 6. Validation có rồi và gate chưa chạy

- OCR/GUI offline: **312 passed, 3 deselected**.
- ASR/CLI offline: **243 passed**.
- **3 integration test** feature model CPU thật trên synthetic glyphs pass:
  blank/repeat, fade, đổi glyph/dấu một frame, standalone punctuation, bbox jitter,
  background text sát cạnh. Đây không phải phép chấm accuracy toàn video.
- Frame 30 s trên bytes worker cuối: cache/no-cache quyết định bằng nhau,
  `present=true`, 4 tracking request/0 recognition mới.
- Ruff pass, Pyright **working tree** 0 errors/0 warnings, translation sync/diff pass.
  Pyright trên snapshot không có `.venv` từng báo warning không phản ánh environment
  project; không cài package hoặc sửa code chỉ để che warning đó.
- P3 domain/CLI thật: OCR D1 2 cue và Whisper baseline 33 cue giữ text/ms/IDs qua
  table/handoff/undo và hai vòng editor save/reopen. OCR còn giữ visual/raw metadata;
  SRT chỉ giữ text/time. D2 export bị từ chối đúng; không fake approve để xuất.
- Native GUI chỉ startup, màn nhận dạng, form OCR/source chooser và đóng exit0.
  Chưa hoàn tất chọn file/export/cancel/playback native. Computer Use gặp vấn đề
  targeting element trong modal; field source của OCR là read-only, phải dùng
  `Chọn video…`. Dùng skill `computer-use:computer-use`, không tự thay bằng thao tác
  UI qua PowerShell. Smoke không thay thế workflow acceptance.
- Holdout đã khóa **74–94 s/140–162 s** nhưng annotation còn pending, inference
  chưa chạy. Whole-video/full offline/build/EXE/TTS **NOT RUN** vì P1/P2 chưa đạt.

## 7. Cách thực thi phiên này

1. Xác minh baseline/evidence, tạo audit mới. Reuse runtime/model và source cũ.
2. Tạo harness cô lập dựa trên `run.py`/`setup.py`/`sync.py` trong audit đã có.
   Không chạy nhầm `app/` snapshot cũ. Sync đúng allowlist, so bytes trước mỗi gate.
   Cô lập settings/cache/log/temp/HF/UV/Torch/CUDA paths; không ghi ra dữ liệu user.
3. Bắt đầu bằng regression và replay các ca D2 nêu trên. Phân biệt presence,
   fragmentation, background và recognition; giữ nguyên guard, raw, cue ngắn và
   valid direct export, không đưa lại mandatory review từng cue.
4. Mỗi candidate OCR có **một lượt/window**, tối đa **40 recognition request**
   và **360 s/window**. Chỉ thêm candidate khi có nguyên nhân/regression mới.
   Chạm cap/hủy giữ partial, không tăng cap. Ghi recognition/tracking/features/cache
   riêng. Lượt trước có 103 recognition đã được đếm ở các window hoàn tất và một
   lượt D2 bị dừng không có số cuối: không gọi tổng 103 là toàn bộ attempts.
5. P1/P2 có thể làm xen kẽ, **một GPU job tại một thời điểm**. ASR mới cần budget
   riêng sau giả thuyết mới; ba lượt candidate cũ đã dùng hết, không tự lặp lại.
6. Làm tiếp P3 native với output hợp lệ, kiểm partial/cancel/source mismatch và
   save/reopen. Giữ hai nguồn OCR/ASR riêng; không điền OCR vào ASR rồi đổi provenance.
7. Chỉ mở P4 khi P1/P2/P3 đạt: annotation holdout trước output, một lượt mỗi
   holdout, rồi mới một lượt toàn video với budget cố định trước chạy. Build sau
   source gates, dùng một `VideoCaptioner.spec` và inventory portable đã verify.
8. Báo cáo hypothesis, allowlist, hashes, commands, số inference/cache, timing,
   pass/fail/not-run và stop reason mỗi phase. Review rồi commit/push đúng scope.

Giữ giọng B cho giai đoạn sau: recipe
`work-dir/BV1GFbk6LEVm-voiceB-20260916-192625/voice-b-recipe.json`, mẫu B của phép thử
OmniVoice instruction ngày 2026-09-16 19:13, không phải mẫu 11 s cũ. Reference Việt
5,16 s, `instruct="female"`, `language="vi"`, seed0 mỗi cue, 32 steps, speed1×;
SHA reference `509ff70aee71483ec547a0d86d354e153cb61f07ca28e76b3da4078384b14c2d`.
User đã chấp nhận giọng; mix nền chưa nghiệm thu riêng, recipe chưa import trực tiếp
vào app. Giữ tất cả WAV/reference/report, chưa làm TTS khi nhận dạng còn lỗi chính.

**Bắt đầu ngay bằng kiểm Git/evidence và regression D2. Không kết thúc ở việc
đọc lại plan hoặc đề xuất một kế hoạch chung.**
