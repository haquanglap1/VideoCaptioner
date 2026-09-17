# Prompt tiếp tục triển khai OCR/ASR quality-first

## Chỉ đạo ưu tiên mới nhất của user — OCR khoảng 80–90%, ASR là chính

User chấp nhận OCR khoảng **80–90%**, chủ yếu cần **speech-to-text tốt**.
Mục này thay yêu cầu phải sửa hết lỗi OCR/đạt exact-match D2 trước khi tiến hành
ASR ở các phần dưới. Mức 80–90% là mục tiêu chấp nhận, **chưa phải accuracy đã
đo trên toàn nguồn**; không sửa báo cáo lịch sử thành OCR đã pass một phép đo mới.

Giữ OCR hiện có làm nguồn đối chiếu phụ. Ghi nhận các lỗi glyph/dấu còn lại nhưng
không dành tiếp các lượt inference để đuổi từng lỗi nhỏ. OCR không được âm thầm
làm mất cả câu/đoạn, làm hỏng timing hoặc raw/provenance; các guard này vẫn giữ.

**Bước tiếp tập trung ASR:** ưu tiên cụm lặp/nhận sai và token đuôi D3, rồi lời
thiếu ở đầu/cuối D1/D2. Đọc `asr-visual-comparison-final.json`, các WAV/raw/config
đã khóa trước khi đề xuất đúng một hypothesis mới có input/budget rõ ràng.
Không chạy lại sáu lượt Qwen đã tiêu thụ hoặc chọn output đẹp nhất. Mục tiêu là
giữ đủ lời, đúng nội dung và timing dùng được; không áp tiêu chí OCR exact-match
để trì hoãn nhánh này. AI visual reference được user chấp nhận, không chờ human
transcript; giữ bất định lời thực nói và không đưa caption vào ASR prompt.

Việc giảm ưu tiên OCR không tự cho phép gọi ASR đạt, đổi OCR default hoặc mở
whole-video/full offline/EXE/TTS khi các gate liên quan còn thiếu. Các số đo/fail
cũ bên dưới vẫn là lịch sử, không phải lý do tiếp tục tập trung vào OCR.

## Trạng thái mới nhất: app candidate đã triển khai và đo từ `0403e02`

**Mục này thay các chỉ đạo “bắt đầu tích hợp”, “chưa scan D1/D2”, “implementation
vẫn cb437cb” ở phần bàn giao cũ bên dưới.** Phiên mới nhất có code app; đọc
`publication.json` và Git live để biết commit, không suy commit từ ghi chú cũ.

- Audit **`.tools/ocr-asr-quality-20260917-171207/`**. Verify 6.791 hash cũ,
  bảo vệ 6.858 file; snapshot ban đầu 763 tracked file, gate cuối 770 file gồm
  source/test mới và `_version.py` sẵn có. Không tải/cài model/package mới.
- Candidate **`paddleocr-vl-1.5-anchor-v1`** đã vào CLI/GUI opt-in, không default.
  `--recognizer-runtime` chọn thư mục có `paddle-vl-runtime.json`; manifest của
  lượt đo ở `171207/vl-runtime/`, dùng Qwen Python + model/deps cũ như bên dưới.
  [Contract](../dev/ocr-vl-candidate-2026-09.md) mô tả schema/path/identity.
- CPU giữ PP-OCRv6 geometry/tracking. VL đọc original RGB union dòng có margin
  nửa chiều cao theo ngang, một phần tư theo dọc; prompt chỉ `OCR:`. Giữ token
  IDs/raw decode/EOS/crop bounds/hash và CTC geometry. Score VL=0 chưa hiệu chuẩn.
  Recipe SHA `4911e12502304a5c06a9b705a88dab4028ca8030d8c56b92cbf1b89196a5d3fe`;
  worker SHA `5b49d0e678500e08a9731f9c9a9677d1751c1152f22effa6bbf8a051c8142283`.
- Một lượt/window đã dùng xong: D1 2 cue, 6 CPU + 6 VL requests, 127,906 s;
  D2 4 cue, 11 CPU + 11 VL, 171,329 s. Cả hai complete/export exit0, không retry,
  cache hoặc failed inference. CPU recognizer batches 12/14; VL batches 6/11;
  tracking 105/180, feature batches 231/287. Cap tổng CPU+VL 40/360 s/window.
- **D1 text PASS trên frame đã đọc; D2 text FAIL.** Raw được chọn cue cuối sai
  thán từ và thiếu một phần dấu ba chấm. Raw frame sau đọc đúng vẫn được giữ;
  hai score bằng 0, unchanged whole-read policy chọn raw sớm. Không lấy riêng
  output đúng hoặc sửa câu theo đáp án rồi gọi model pass. **P1/P2 unresolved**.
- Tổng VL hiện **21 attempts, 20 complete/1 failed**: 4 diagnostic cũ + 17 app
  requests mới. Không lặp hai crop/blank diagnostic hoặc D1/D2 bằng đúng candidate
  này. Không tự cấp một lượt mới chỉ vì đã sang phiên; cần hypothesis mới có
  version/input/config/budget khóa, không sweep hoặc chọn kết quả đẹp.
- 17 token decode replays khớp, 0 inference kiểm tra. Diagnostic crop0 tại PTS
  1006400 nằm nguyên pixels trong app crop có padding; processor tensors khác.
  Candidate app sau là PTS1007467, **khác** diagnostic crop1 PTS1006933. Harness
  đầu giả định nhầm đã fail và được giữ; final ghi unmatched, không self-compare.
  Chưa chứng minh padding là nguyên nhân duy nhất; không tự retry crop0 để thử.
- **509 passed, 7 deselected, 1 warning**, gồm 23 VL synthetic contracts;
  Ruff/Pyright/translation sync pass. Bốn checkpoint cũ v1/v3 giữ exact JSON.
  D1/D2 table/handoff/undo/hai vòng editor save-reopen giữ text/ms/IDs/raw; SRT giữ
  text/time. Đây là domain/source checks, không phải native GUI mới.
- Review cuối thêm guard CLI bảo vệ payload model/deps/Python ở ngoài thư mục
  manifest; ba tests nằm trong 509. Worker/recipe giữ nguyên, không inference lại.
  `measured-code/` giữ CLI lúc đo; `post-review-amendment.json` ghi thay đổi sau đo.
- **12 AI visual annotations**, đối chiếu đủ 6 raw Qwen cũ; 0 ASR mới/Qwen tổng6.
  D1 từ, D2 tên/thán từ, D3 cụm lặp/token đuôi còn khác caption. Speech ground
  truth unknown; không CER/WER/alignment hoặc sửa sáu câu Việt. Không chờ human
  transcript. Có thể tiếp tục phần độc lập, chỉ inference ASR khi có hypothesis mới.
- Native mới/real GPU cancel/holdout/whole-video/full offline/EXE/TTS **NOT RUN**.
  Tests hủy GPU dùng process thật với worker synthetic, không model inference.
  H1 contamination 539 ms giữ nguyên. Model/raw/checkpoint/receipts/snapshot được
  giữ; cache/temp riêng phiên được dọn theo receipts, không đụng artifact cũ.

Đọc trước: `publication.json`, `review.json`, `commit-allowlist.json`,
`preservation-check-final.json`, `phase-results.json`, `coverage-ledger.json`,
`run-ledger.jsonl`, `quality-report.md`, `runtime-manifest-final.json`,
`candidate-plan-locked.json`, `candidate-code-amendment.json`,
`candidate-quality-assessment.json`, `candidate-D1/`, `candidate-D2/`,
`candidate-verification*.json`, `old-checkpoint-verification.json`,
`p3-candidate-roundtrip/results.json`, `ai-visual-reference.json`,
`asr-visual-comparison-final.json`, `asr-visual-comparison.md`, cleanup receipts.

**Bước tiếp:** review boundary/selection đang fail bằng input/raw đã lưu; giữ
identity và không hardcode glyph hoặc tự chọn candidate theo AI đáp án. Chỉ đổi
semantics khi có version mới và regression trước sửa. Không rerun cùng candidate,
không dùng default/promote/holdout/TTS để né D2 hoặc ASR còn lỗi. Scope quyền
commit/push và các dữ liệu phải bảo vệ ở phần dưới vẫn áp dụng.

## Bàn giao lịch sử trước khi tích hợp — dùng để tra evidence, không lặp work

Cập nhật 2026-09-17 sau phiên tiếp từ `56bbbdf`. App implementation vẫn là
`cb437cb`. User đã cấp riêng 1 attempt crop0/90 s; lượt đó hoàn tất, EOS và giữ
glyph/body theo AI visual reading. Reuse nguyên crop1/blank cũ: diagnostic nhỏ
**PASS**, chưa tích hợp hoặc scan D1/D2; **P1/P2 vẫn unresolved**. Tổng lịch sử
PaddleOCR-VL 4 attempts, 3 complete/1 failed cũ; quyền bổ sung đã dùng hết.
Chi tiết candidate thất bại trước vẫn giữ trong báo cáo/audit. Commit chứa prompt
chỉ đổi tài liệu; kiểm live HEAD/remote và `publication.json` trước khi làm.

**Chỉ đạo mới nhất của user:** dùng chính assistant đọc chữ trực tiếp từ frame
làm reference đối chiếu. Gắn nhãn `AI visual reference`; không bắt buộc human
transcript và không dừng triển khai chỉ vì thiếu nó. Phân biệt chữ trên hình với
lời thực nói; không nâng AI reference thành human ground truth.

Tiếp tục tại root repository **VideoCaptioner**, nhánh `codex/ocr-asr-quality-pilot`.
Trả lời tiếng Việt, giữ code/identifier/file name bằng English. Đây là phiên
**triển khai tiếp**, không chỉ đọc lại plan. Ưu tiên OCR/ASR đủ và đúng trước.

## 1. Phạm vi và quyền đã có

- Được sửa code, test/inference local, chuẩn bị runtime/model còn thiếu trong
  project sau inventory; không cài global hoặc đổi cấu hình ngoài repository.
- Được commit/push phần liên quan sau review/validation, stage allowlist cụ thể.
  Không merge `master`, không reset/clean/apply/pop/drop stash hoặc checkout đè dirty state.
- Bảo vệ `.env`, cookies, `AppData/`, `work-dir/`, settings, media/model/raw và
  artifact cũ. Không đưa chúng, credential, private transcript hoặc absolute local
  path vào Git. Mọi output mới nằm trong một audit root riêng dưới `.tools/`.
- Chưa whole-video/full offline/build/EXE/TTS khi P1/P2/P3 chưa đạt. Giữ sáu câu
  Việt và recipe giọng B đã chấp nhận, không dịch/rewrite/thử giọng lại.
- Được dùng AI visual reference do assistant trực tiếp đọc ảnh để đối chiếu
  OCR/ASR theo chỉ đạo mới. Đây là working reference được user chấp nhận;
  không yêu cầu user chép/duyệt tiếng Trung hoặc chờ human reference mới làm tiếp.

## 2. Đọc và kiểm trước khi sửa

Đọc đầy đủ `AGENTS.md`, `README.md`, mục mới nhất của `status.md`, prompt này,
section **2026-09-17** đầu `docs/dev/ocr-asr-quality-first-results-2026-09.md` và
`docs/plans/ocr-asr-quality-first-2026-09.md`. `PLAN ONLY` và v1/v2/v3 trong các
section cũ là lịch sử; không dùng chúng thay trạng thái bàn giao dưới đây.

Phiên mới nhất bắt đầu với `56bbbdf` trùng remote, working tree sạch; app implementation
`cb437cb` giữ nguyên. Commit report/handoff tiếp theo xem `publication.json` trong
audit mới, rồi kiểm live Git. `master`/`origin/master` lúc kiểm đều ở
`62abacae421d2011948f467d3386d81de9f8879b`, chưa merge pilot.
Giữ nguyên hai stash:

- `6a1e12d531cfb0e7408ab5737d02c544902001e2`
- `e61dd7e2cea5eeffd2d64a30b84af1477d504558`

Kiểm live status/index/diff/refs/stashes/remote. Không suy working tree vẫn sạch
chỉ từ prompt hoặc publication cũ. Thiếu evidence thực thì báo đúng path thiếu;
không đoán dựng lại hoặc chạy lại inference chỉ để tạo evidence tương tự.

## 3. Evidence và runtime phải reuse

Audit mới nhất: **`.tools/ocr-asr-quality-20260917-164027/`**. Đọc:

- `publication.json`, `review.json`, `commit-allowlist.json`, `preservation-check-final.json`
- `phase-results.json`, `coverage-ledger.json`, `run-ledger.jsonl`, `quality-report.md`
- `baseline.json`, `snapshot-allowlist.json`, `snapshot-initial.json`, snapshot gates,
  `runtime-manifest-final.json`, `cleanup-final-plan.json`, `cleanup-final-receipt.json`
- `preflight.json`, `vl-supplement-plan-locked.json`, **`authorization.json`**,
  `vl-supplement-results.json`, `vl-supplement-receipt.json`,
  `vl-supplement-verification.json`, `vl-outputs/0.json`
- `asr-reference-plan-locked.json`, `asr-reference-results.json`,
  `asr-reference-assessment.json`, **`reference-policy-amendment.json`**,
  `coverage-final-amendment.json`

Phiên này verify 6.303 hash cũ, bảo vệ 6.791 file, copy 763 tracked file đúng
bytes. `*-prepared` và `quality-report-prepared.md` là trạng thái trước khi user
cấp quyền, không dùng thay final. Plan giữ chữ PENDING tại thời điểm khóa;
`authorization.json` là quyền cấp sau đó, gắn đúng SHA plan. Field kế thừa
`original_attempts_consumed=1` chỉ nói về first forward cũ; `previous_attempts=3`
là tổng cap cũ đã tiêu thụ. Không sửa plan khóa để xóa lịch sử này.

Audit PaddleOCR-VL đầu tiên: **`.tools/ocr-asr-quality-20260917-160948/`**. Đọc:

- `publication.json`, `review.json`, `commit-allowlist.json`, `preservation-check.json`
- `phase-results.json`, `coverage-ledger.json`, `run-ledger.jsonl`, `quality-report.md`
- `baseline.json`, `snapshot-allowlist.json`, `snapshot-initial.json`, các snapshot gates,
  `runtime-manifest-final.json`, `cleanup-plan.json`, `cleanup-receipt.json`
- `vl-upstream.json`, `vl-inventory.json`, `vl-inputs.json`, `vl-plan-locked.json`,
  `vl-results.json`, `vl-plan-remaining-locked.json`, `vl-remaining-results.json`,
  `vl-verification.json`, `vl-compat-verification.json`, runtime amendments/receipts
- `asr-reference-plan-locked.json`, `asr-reference-results.json`, `p0-amendment-final.json`

Phiên này verify 705 hash cũ/bảo vệ 6.303 file và copy 763 file tracked đúng bytes.
Giữ evidence/model/snapshot; cache/temp/profile/tools tạm đã dọn theo yêu cầu user.
Runner có thể tạo lại thư mục tạm; không dùng cache bị dọn như evidence bắt buộc.

Audit SVTRv2/PCM/native trước: **`.tools/ocr-asr-quality-20260917-151112/`**. Đọc:

- `publication.json`, `review.json`, `commit-allowlist.json`, `preservation-check.json`
- `phase-results.json`, `coverage-ledger.json`, `run-ledger.jsonl`, `quality-report.md`
- `runtime-manifest-final.json`, `baseline.json`, `snapshot-allowlist.json`,
  `snapshot-initial.json` và các `*-snapshot.json`
- `svtr-upstream.json`, `svtr-inventory.json`, `svtr-plan-locked.json`,
  `svtr-results.json`, `svtr-verification.json`, runtime amendment và receipts
- `asr-audio-plan-locked.json`, `asr-audio-results.json`, `asr-pcm-amendment.json`,
  **`asr-audio-final.json`**; bản initial có self-comparison D3 được ghi rõ/sửa ở final
- `native-text-partial/{plan-locked,results}.json`,
  `native-text-save/{plan-locked,results}.json`, `native-text-save/ui-saved.ocr.json`,
  `native-verification.json`, hai native process receipts

Phiên này verify 626 hash cũ, bảo vệ 705 file, copy 763 tracked file từ checkout.
Không sửa app, không chạy lại targeted/full suite; 6 đối chiếu tensor/decode
upstream là kiểm harness, không phải app test hoặc 6 inference mới.

Audit native cancel/listening trước: **`.tools/ocr-asr-quality-20260917-145000/`**. Đọc:

- `publication.json`, `review.json`, `commit-allowlist.json`, `preservation-check.json`
- `phase-results.json`, `coverage-ledger.json`, `run-ledger.jsonl`, `quality-report.md`
- `runtime-manifest-final.json`, `baseline.json`, `snapshot-allowlist.json`,
  `snapshot-initial.json` và các `*-snapshot.json`
- `got-tiled-inventory.json`, `got-tiled-plan-locked.json`, `got-tiled-results.json`,
  `got-tiled-inference-receipt.json`
- `native-harness-amendment.json`, `native-cancel-v2/{plan-locked,results,verification}.json`,
  `native-cancel-v2/ui-saved.ocr.json`, `native-reopen-result.json` và process receipts
- `listening/reference-template.json`, `listening/README.md`, ba WAV D1/D2/D3
- `targeted-contracts-receipt.json`: **92 passed, 1 warning**, không cộng 72 cũ.

Audit diagnostic/context trước: **`.tools/ocr-asr-quality-20260917-135038/`**. Đọc:

- `publication.json`, `review.json`, `commit-allowlist.json`, `preservation-check.json`
- `phase-results.json`, `coverage-ledger.json`, `run-ledger.jsonl`, `quality-report.md`
- `runtime-manifest-final.json`, `got-upstream.json`, `got-inventory.json`
- `got-plan-locked.json`, `got-plan-eager-locked.json`, `got-results.json`
- `asr-d2-context/plan-locked.json`, `results.json`, request WAV/raw/TXT
- `snapshot-initial.json`, `snapshot-mismatches.json`, `snapshot-sync-receipt.json`,
  `snapshot-gate-verification.json`, `p0-correction.json`, `targeted-contracts-final-receipt.json`

Audit app candidate vẫn ở **`.tools/ocr-asr-quality-20260917-112253/`**. Đọc:

- `publication.json`, `review.json`, `commit-allowlist.json`, `preservation-check.json`
- `phase-results.json`, `coverage-ledger.json`, `run-ledger.jsonl`, `quality-report.md`
- `runtime-manifest-final.json`, `dictionary-inventory.json`
- `recognizer-v4-plan.json`, `recognizer-v4-coverage.json`, `recognizer-v4-results.json`
- `consensus-replay.json`, `consensus-bright-replay.json`
- `ocr-consensus-v2/plan.json`, `results.json`, D1/D2 checkpoint/report/JSON
- `asr-original/plan-locked.json`, `results.json`, `D3-request.wav`, `D3-raw.json`
- `p3-roundtrip-consensus/results.json`, `native/results.json`, `guard-checks/results.json`

Audit trước vẫn giữ nguyên:

- `.tools/ocr-asr-quality-20260916-213401/`: v3b, dictionary/probes đã thất bại,
  Qwen D1 context, native v3a partial và các companion trong `candidate-workers/`.
- `.tools/ocr-asr-quality-20260916-201453/`: đặc biệt `qwen-txt/inputs-locked.json`,
  raw/TXT/request WAV ba ca đầu, runtime Qwen và exact decoder frames.

Nguồn BV1GFbk6LEVm P1: 266,566625 s, 1920×886. Path thật nằm trong
`.tools/bv1gf-20260916-145613/source.json`; SHA-256
`3e56b8d3349bb2013723617ce856cd44a72f1f5140d81ef1c126a65747d13d90`.

Runtime đã có, verify rồi reuse:

- OCR: `.tools/bv1gf-20260916-145613/runtimes/ocr-v6-medium/`;
  Python ở `env/Scripts/python.exe`.
- FFmpeg/ffprobe/Faster-Whisper-XXL/Kim_Vocal_2: audit nguồn `tools/`;
  large-v3 trong `models/` của audit đó, không phải giả định repo có `models/` root.
- Qwen: `.tools/ocr-asr-quality-20260916-201453/qwen-runtime2/`, pin
  `7278e1e70fe206f11671096ffdd38061171dd6e5`. Runtime CUDA đã chạy thật,
  chưa portable acceptance; không chọn nhầm `qwen-runtime/` bị cài lỗi trước đó.
- Diagnostic V4: audit `112253` có `ch_PP-OCRv4_rec_server.onnx`, SHA
  `6a2676219be9907c7fc9cf61ebaa843bf2898777def567925b78886fcd90c07a`.
  Candidate bị loại, chưa được tích hợp thành profile app.
- Diagnostic GOT: audit `135038/got-model/`, revision
  `d3017ef2c2c1395888c8d635c5e0508bcb0ac78d`, weights SHA
  `6175ac7868a4e75735f5d59f78c465081ad3427eb4f312d072a0f1d16b333ba4`.
  Reuse Qwen Python, không cài package; candidate bị loại, không phải runtime app.

Đọc/điều chỉnh `setup.py`, `run.py` và harness liên quan trước dùng; tạo audit
mới từ đúng checkout, không chạy nhầm `app/` snapshot cũ. Cô lập settings/cache/
log/temp/HF/Torch/UV; sync allowlist và so bytes trước mỗi gate. Giữ Python app
và runtime model riêng. Một GPU job tại một thời điểm.
`git archive` có thể khác checkout ở CRLF dù status sạch: so bytes trước chạy,
không đợi final review. Audit `135038` giữ 74 bản trước sync; không sửa chúng
hoặc gọi mọi file snapshot ban đầu là byte-identical với checkout.
Audit `145000` copy 763 file tracked trực tiếp từ checkout và so bytes trước mọi
gate; verify 538 hash cũ và bảo vệ 626 file. Reuse cơ chế này thay Git archive.

## 4. OCR — trạng thái cuối và việc cần làm

Tracking v3 đã sửa nền giả ở 57,033/62,833 s, split giả 62,600 s và biên đổi
standalone punctuation khi tiled CTC yếu. Không mở lại các sửa đó nếu không có
regression mới. Bytes v1/v2/v3 giữ nguyên để resume checkpoint cũ.

Cấu hình candidate cuối:
`--line-anchors 0.5 --tracking characters-v3 --consensus punctuation-v2`,
ROI `0.05,0.88,0.90,0.10`. Chưa promote mặc định.

| Window | Cue | Recognition mới/cache | Tracking/features | Wall | Complete/export |
|---|---:|---:|---:|---:|---|
| D1 28,8–32,3 s | 2 | 6/0 | 105/231 | 86,516 s | true/exit0 |
| D2 57–63 s | 4 | 11/0 | 180/287 | 123,391 s | true/exit0 |

Consensus `witnessed-punctuation-v2` lấy lại dấu cuối D2 bằng chọn **nguyên raw
candidate**, chỉ khi hai ảnh cùng chứng minh cụm dấu sáng/gọn bên ngoài bbox bị
cắt. Disagreement/uncalibrated/raw và cue ngắn vẫn còn. Đây là heuristic hẹp,
không sửa glyph ngoài dictionary hoặc chứng minh mọi font/nền đều đúng.
GUI resume giữ consensus policy đã lưu, vẫn kiểm runtime/profile/worker.

- Worker v3 SHA: `9bef0946f8456c9f7e4a36f49feba0555f61540dfc8f45eea4f6f94375931447`.
- Consensus source SHA trên bytes đã đo/commit:
  `7464cfa5950da83df0f1f88666c4fb59a03b5e6688b71174fdf29bea954961d1`.
- Đổi semantics tracking hoặc consensus sau commit này phải có version mới,
  giữ resume cũ; không sửa hash checkpoint. Worker v3a/v2 cũ khác hash cần dùng
  đúng companion đã lưu, không gọi checkpoint complete là partial để chạy lại.

**Lỗi chính còn mở:** thán từ khoảng 62,900 s. PP-OCRv6 medium dictionary
18.708 entry không có `诶` mà assistant đọc trên frame. Reference ảnh là AI,
không được gọi human ground truth. V5 cũng thiếu glyph. V4 có coverage nhưng
2 raw-crop batches trên đúng input cũ vẫn đọc sai glyph và kém phần cuối; đã loại.
Contrast/grayscale/padding/inversion/isolated-glyph probes trước đó cũng thất bại.

GOT-OCR2 đã thử **3 request/3 batches, 0 cache** trên hai raw crop cùng hash với
V4 và một blank synthetic. Tokenizer/output 151.860 class biểu diễn được glyph;
crop đầu lấy lại glyph, crop sau vẫn thiếu, blank hallucinate chữ/số. **Loại
candidate theo gate khóa trước**, không dùng riêng crop thành công hay ghép raw.
Lượt load `sdpa` lỗi trước inference; amendment `eager` giữ cùng cap/input,
18,047 s generation/25,750 s worker. Không lặp GOT raw hoặc sweep model.

GOT **dynamic patches cũng đã bị loại** trong audit `145000`: hypothesis giảm
biến dạng crop khoảng 7:1 khi resize vuông, giữ model/crop/greedy; chỉ bật
`crop_to_patches=True`, min1/max12 mặc định. Inventory model/tokenizer/151.860
output classes, hash crop/tensors/input IDs trước chạy. Đúng 3 request/3 batches,
0 cache, 38,109 s generation/46,765 s process; hai crop mất phần lớn câu, blank
lặp đến 96 token khi chưa EOS. Peak allocated VRAM 23.528.787.456 byte.
Không retry/tăng token/chọn patch hoặc tích hợp. Tổng GOT 6 request qua hai phiên;
không lặp raw **hoặc tiled**, không xem tiling thất bại là lý do sweep cấu hình.

**SVTRv2 cũng đã bị loại** trong audit `151112`: hypothesis encoder CTC khác
có dictionary coverage. Official `PaddlePaddle/ch_SVTRv2_rec`, pin
`67349283ac400fb34f73a5c32f1c0c00df5ee26a`, weights SHA
`2f9e8ea8852560f908e1a0fb497818477e5a3610f660ddb339b3dddb0c207116`.
Inventory 6.623 dictionary entries/6.625 classes, target class 3872 trước inference.
Paddle 3.0.0/NumPy 1.26.4 runtime riêng tại `151112/paddle-runtime/`; lỗi import
setuptools xảy ra trước inference, amendment bổ sung 80.9.0 giữ plan/input/budget.
Đúng 3 request/3 batches trên hai crop cùng hash và blank, CPU 4 threads,
official preprocessing/greedy CTC, 0 cache/tracking/features, 0 retry. Hai crop
vẫn sai glyph, blank rỗng; 0,875 s inference/4,125 s process. Sáu đối chiếu
preprocessing/decode official đều khớp, không inference lại. Không tích hợp,
không scan window, không lặp SVTRv2 hoặc đổi preprocessing để chọn output.

**PaddleOCR-VL-1.5 đã qua diagnostic nhỏ sau attempt bổ sung:** audit `160948` và `164027`,
pin `2a4195faa5e7914c12f2fc601d72c81caf8d2da5`, weights SHA
`d557c9d8997ae57ed3b1b33bdf347be878cc335687f32ca105341c16973f8958`.
103.424 output classes/101.316 tokenizer entries; target token 97757. Reuse Qwen
Python, dependency overlay `160948/vl-deps/`; official custom code pinned local,
BF16/SDPA, prompt `OCR:`, greedy96, use_cache=false, processor defaults.

Cap 3 attempts/180 s đã hết: crop0 first forward lỗi `inputs_embeds` vs
`input_embeds` của `create_causal_mask`, 0 token nhưng **tính 1 failed request**.
Adapter `vl_compat.py` chỉ đổi keyword, 4 mask cases pass. Amendment chỉ dùng
2 input còn lại, **không retry crop0**: crop1 giữ glyph/body/dấu theo AI reference,
blank rỗng, cả hai EOS. 14,874 s generation hoàn tất, 46,984 s tổng process kể cả
lượt lỗi, 0 cache/tracking/features. 12 input tensors/2 token decode replays khớp;
đây là kiểm harness, 0 app tests mới. Không sửa app/profile hoặc scan window.

Trong audit `164027`, user đã cấp **1 attempt bổ sung riêng cho crop0**, hard
process cap 90 s/worker 75 s, không retry tiếp. Giữ nguyên weights/input tensors/
adapter/BF16/SDPA/prompt/greedy96. Output crop0 giữ glyph đầu và body nhìn thấy,
EOS; **1 request/1 batch, 0 failed/cache/tracking/features**, generation 14,828 s,
process 23,782 s, exit0; peak allocated VRAM 1.978.958.848 byte. Crop1/blank reuse
nguyên bytes. Tổng hai audit **4 attempts, 3 complete/1 failed**, process 70,766 s;
không sửa failure trước hoặc gọi bốn attempts là lượt mới.

Diagnostic hai raw crops/blank **PASS theo AI visual reference**. Bốn tensor
comparisons crop0 và ba token decode replays đều khớp, 0 inference verification,
0 app tests mới. Không phải human ground truth hoặc quality acceptance toàn app.
Attempt bổ sung đã dùng hết; **không lặp crop0/crop1/blank**, không tải model khác
để sweep. Reuse Qwen Python, model và dependency overlay tại audit `160948`.

**Bước triển khai tiếp theo:** kiểm boundary recognizer/profile/runtime trong
app, chuẩn bị candidate PaddleOCR-VL opt-in với identity/provenance riêng. Giữ
tracking/consensus cũ và old resume; nếu đổi semantics phải version mới. Tách
runtime GPU khỏi Qt/app Python, một GPU job, deadline/cancel thật. Không thêm
glyph bằng dictionary giả hoặc chỉ thay đúng câu đang biết đáp án. Dùng regression
synthetic để kiểm routing/raw/identity/cache/resume và failure guards trước khi
khóa một lượt app candidate trên D1/D2. Không đổi default từ diagnostic nhỏ.

Inventory profile/weights/output classes/tokenizer trước inference;
coverage chỉ là điều kiện cần. Không rerun V4/raw, tải V5, lặp các probes cũ hoặc
sweep nhiều model. Không tự thêm dictionary entry khi weights/classes không đổi.
Không hardcode transcript, nối raw để che lỗi, xóa cue ngắn hoặc nới export guard.

Mỗi candidate đúng một lượt/window, tối đa **40 recognition request và 360 s/window**.
Diagnostic có hypothesis/input hashes/config/cap riêng khóa trước chạy, không tự
nới cap/retry chọn output đẹp. Ghi riêng recognition requests, recognizer batches,
tracking, feature batches, cache và failed attempts. Regression fail trước sửa;
giữ blank/fade/standalone punctuation/one-frame change/cache/resume guards.

## 5. ASR — nhánh độc lập, không lặp những lượt đã dùng

Phiên `164027`: một metadata extraction từ bản YouTube official
`https://www.youtube.com/watch?v=mT86JXY6oEw` trả 261 s, language en-US,
không có manual track trong response, chỉ automatic captions (có Chinese).
Không tải transcript/media, không playback. Khác edition/timebase với nguồn
266,566625 s; chưa có reference tiếng Trung. `asr-reference-{results,assessment}.json`
giữ evidence. Không gọi automatic Chinese track là người nghe độc lập.

**Working reference đã được user chấp nhận:** assistant trực tiếp đọc chữ từ
frame gốc D1/D2/D3, reuse ảnh/annotation đã có; ghi source/frame PTS/hash, text
nhìn thấy và chỗ không chắc. Đặt `reference_kind=AI visual reference`; không lấy
output recognizer đang đo làm đáp án, không tự gán human-reviewed. Khi annotation
mới, đọc ảnh trước output candidate nếu có thể; ghi prior exposure nếu đã thấy.

Đối chiếu ASR bằng bảng audio window/visual text/raw ASR/phần khớp-phần khác/
vùng chưa xác định. Đây là phép đối chiếu với caption, không mặc định mọi khác
biệt là lỗi lời nói. Không cần human transcript mới triển khai tiếp; đừng dành
cả phiên chỉ tìm reference hoặc hỏi user chép tiếng Trung. Có thể bổ sung người
nghe/kịch bản nếu có, nhưng việc thiếu nguồn đó không tự chặn P2.

Ground truth lời nói vẫn chưa xác minh; không báo CER/WER như độ chính xác lời
nói từ caption. Không đưa visual reference vào prompt ASR để làm đẹp kết quả.
Nếu về sau chỉnh phụ đề theo chữ trên hình, ghi visual-assisted correction và
giữ raw ASR. Các quality gate còn lại vẫn phải kiểm; quyền dùng AI reference
không tự có nghĩa ASR hiện đã đạt.

Phiên `160948`: tìm nguồn chính thức theo title chỉ thấy mô tả/credits; metadata
Bilibili anonymous trả HTTP 412, không có transcript nghe độc lập mới. Không
suy 412 là không có subtitles. `asr-reference-results.json` giữ giới hạn này;
0 ASR/upload/alignment/CER/WER, reference vẫn unknown.

Qwen đã thực hiện tổng cộng **6 request** cho các giả thuyết đã khóa:

1. D1 27–34 s original, D2 57–63 s original, D3 107–126 s filtered dump (3 request).
2. D1 original context 24–36 s (1 request): lấy lại đầu câu, còn từ đáng ngờ.
3. D3 original 107–126 s (1 request/0 cache, 33,812 s): lời lặp đổi nội dung,
   đuôi đáng ngờ còn; chưa có căn cứ gọi original hoặc filtered tốt hơn.
4. D2 original context 54–67 s (1 request/0 cache, 28,375 s): có thêm mệnh đề
   cuối trong input mở rộng, tên riêng vẫn khác caption; thán từ chưa xác nhận
   bằng nghe. Không gọi thêm input là thắng accuracy trên cùng audio.

Phiên `151112` không có ASR inference mới; Qwen vẫn tổng 6 request. Năm cặp
input/request mono khớp PCM/sample counts; D3 original từ source stereo 44,1 kHz
qua `decode_audio`/`wav_bytes` tái tạo đúng bytes request 304.000 sample. Lượt audit
ban đầu dùng chính request làm input D3 nên chỉ là pack identity; amendment/final
đã kiểm từ stereo thật, không tính self-comparison thành bằng chứng độc lập.
Ba listening WAV giữ nguyên hashes; số đo clipping/channel chỉ là signal check,
không xác nhận lời nói. Không có listener/transcript mới, reference vẫn unknown.

Phiên `145000` cũng không có ASR inference mới. Bộ
`listening/` có ba original WAV D1 24–36, D2 54–67, D3 107–126 s, copy đúng
bytes/PCM input cũ, không kèm caption/model output. Chưa có transcript độc lập;
template vẫn unknown. Nếu nhận reference, ghi người nghe, mốc bất định và
prior exposure trước khi gọi independent; không tự gán nhãn human-reviewed.
**User không biết tiếng Trung**, đã xác nhận trong phiên `145000`. Không yêu cầu
user chép lời hoặc nghiệm thu chữ tiếng Trung. Tình trạng này là lịch sử trước
khi user chấp nhận AI visual reference; áp working reference mới ở đầu mục này,
không coi thiếu human reference là điều kiện dừng triển khai.

D2 context WAV SHA `a29238016dca8f756dac8343ce6dfca99bd646a2fa11bcb659f810a1d6161f52`;
request SHA `8dbdd5555010d993f6a31220c433eec676c36c8a056c9fba839cf5b709256668`.
95.360 PCM sample nội vùng 57–63 s bằng tuyệt đối; mép resampling có khác nhỏ.
Không chạy lại context này để chọn output đẹp. Audio D3 gốc đã được đưa cho user
nghe; chưa nhận transcript độc lập, reference vẫn unknown.

D3 filtered recognition dùng `source-107-126-stereo.wav_dump.wav` sau Kim_Vocal_2,
**không phải `*_mdx.wav`**. Locked dump SHA
`a01e225b224330e77f1a35652eba293761c06946148f56adc1eed9403332be50`.
D3 original request WAV mới có SHA
`4e02d2ccfa4452bf28e1cdeeb6eadb3e62ccacd20174e3dd1d115049b96dd36c`.
Giữ hai preprocessing riêng; không tách vocals lần hai hoặc padding filtered dump
107–126 bằng original context 104–129 rồi gọi là cùng input/config.

Tiếp tục kiểm audio/reference và chỉ inference khi có giả thuyết mới, khóa WAV/
hash/config/budget trước chạy. Reuse Whisper large-v3 **VAD-on**; VAD-off đã fail.
Không đưa OCR/đáp án vào ASR prompt, không upload audio, không chọn output đẹp nhất.
Reference lời nói hiện **unknown**, working reference là **AI visual** được user
chấp nhận. Tiếp tục đối chiếu/triển khai với nhãn nguồn và bất định rõ ràng;
không chấm CER/WER lời nói hoặc gọi mọi khác biệt với caption là lỗi lời nói.
Chỉ alignment sau text gate; không ghép text Qwen với giờ Whisper khác lời.

## 6. Validation và native — phân biệt đúng bằng chứng

- Phiên `164027`: 1 supplemental OCR request đã được user cho phép, không
  request crop1/blank mới. 4 tensor comparisons/3 decode replays là kiểm harness,
  **0 app tests mới**. Diagnostic nhỏ pass không thay D1/D2 hoặc native workflow.
  ASR 0 mới/Qwen tổng 6; native/holdout/whole-video/full offline/EXE/TTS NOT RUN.
- Phiên `160948`: 4 synthetic mask checks, 12 tensor comparisons, 2 decode
  replays; 0 app tests, không cộng 92 lịch sử. Native mới NOT RUN; các kết quả
  native bên dưới là lịch sử. Không mở holdout/whole-video/EXE/TTS.

- Phiên `151112`: native open/save/reopen **partial lịch sử thật 69 cue, v1**
  giữ exact document và bytes, incomplete; UI Export khóa, CLI exit5 không SRT.
  Lượt đầu open pass nhưng timer 170 s đóng trước save; lượt sau preload cùng
  partial rồi save/reopen qua modal native, quan sát nạp xong và bấm Đóng, exit0.
  Không recognition/tracking/playback. Không biến complete thành partial;
  không gọi đây là fresh v3 cancel/resume có chữ hoặc full source/ROI-to-result.
  0 app tests mới; 6 đối chiếu upstream preprocessing/CTC pass riêng bằng dữ liệu
  đã lưu. Không cộng với 92 tests cũ và không mở holdout/whole-video/EXE/TTS.
- Phiên `145000`: **92 passed, 1 warning**, thêm OCR UI vào targeted contracts
  cũ; 763 file tracked khớp bytes trước gate. Không đổi app, không có regression
  app mới; không chạy lại toàn bộ suite/lint/type hoặc build để thay quality.
- Native partial resume/cancel/save/reopen mới: click hủy 17,766 s, stop 18,078 s,
  latency 312 ms, watchdog không dùng; 9 tracking/detector mới, 0 recognition/
  cache/feature batches. UI save và file-open riêng giữ exact document, incomplete,
  v3/punctuation-v2; export vẫn exit5. Không playback/holdout mới. Fixture preloads
  partial **0 cue**, chưa full native source/ROI-to-result hoặc giữ cue có text.
- Lượt harness đầu sửa frozen `OcrTask` trực tiếp gây exit3221226505 trước
  worker.start/0 inference; giữ evidence, sửa bằng `dataclasses.replace` trong
  script mới, cùng budget. Native reopen lần đầu chưa quan sát final trước timer
  đóng; lượt chỉ đọc riêng đã verify UI/readback và đóng exit0, 0 inference mới.
- Phiên `135038`: **72 passed, 1 warning** cho targeted consensus/resume/Qwen
  TXT/long audio/audio identity/GUI TXT, chạy trên 536 file source/test/scripts
  khớp bytes checkout. Không cộng với lượt 72 pass trước sync EOL. Một lệnh test
  sai path collect 0/exit4 được giữ, không tính thành pass. Không sửa app nên
  không có regression fail-before-fix mới; hai inference hypotheses chưa đủ gate.
- OCR/GUI scope cuối: **337 passed, 7 deselected**; ASR/CLI: **243 passed**.
  16 test consensus mới đã nằm trong 337, không cộng trùng. Ruff/Pyright (0 errors,
  0 warnings)/translation sync pass. Đây là kết quả trước phiên mới, không thay
  validation cho code sắp đổi. Bảy real-model tests của audit trước được reuse
  theo worker hash, không gọi là bảy lượt inference mới ngày 17.
- Domain D1 2 cue/D2 4 cue/Whisper baseline 33 cue giữ text/ms/IDs/metadata qua
  table/handoff/undo và hai vòng editor save/reopen; SRT giữ text/time.
- Native Editor đã mở project D2 từ CLI candidate, phát video, save JSON+SRT và
  reopen đủ 4 cue; bytes/domain giữ metadata. Full native OCR source-to-result,
  EXE và manual listening acceptance vẫn chưa đạt; native partial cancel mới
  được ghi riêng ở đầu mục này.
- Service cancellation phiên `112253`: 8 tracking, 0 recognition, 0 feature batches,
  18,047 s dưới cap 30 s; partial được giữ, export exit5 không tạo SRT. Không gọi
  service cancellation là bấm nút hủy native.
- Native cancel cũ bấm ở 33,740 s, vượt budget 30 s: giữ fail đó. Lượt native sau
  vẫn cần cutoff/deadline thực trong harness đã khóa trước, thao tác hủy sớm và ghi
  thời điểm click/dừng riêng; automatic watchdog không thay bằng chứng nút hủy.
- Dùng skill `computer-use:computer-use`. Với modal, UIA `focused_element` từng
  báo sai dù caret đã ở File name: quan sát screenshot đúng modal trước nhập;
  không gửi text vào field chỉ vì index cũ. Không thay bằng PowerShell UI automation.

**H1 74–94 s đã bị contamination:** native playback bấm pause khoảng 73,940 s,
dừng thực ở 74,539 s, làm lộ 539 ms đầu H1. Không được gọi H1 hoàn toàn unseen.
H2 140–162 s chưa inference. Chỉ sau P1/P2/P3 đạt mới xử lý holdout: ghi rõ
contamination hoặc khóa đoạn thay thế chưa xem, annotation trước candidate output.
Không chọn đoạn theo kết quả. Chưa mở holdout/whole-video/full offline/EXE/TTS
trong lúc lỗi recognition/reference còn mở; playback cũng phải có cutoff trước holdout.

## 7. Điều kiện dừng và bàn giao

User yêu cầu dọn rác sau khi xong. Chỉ dọn cache/temp và trung gian do phiên
hiện tại tạo, kiểm absolute path nằm dưới audit riêng; ghi inventory/receipt.
Giữ model/raw/checkpoint/receipts cần bàn giao và không dọn artifact cũ.

Giữ các giới hạn chất lượng trung thực: complete/export exit0/cue count ít hơn
không tự chứng minh text/coverage đúng. Khi thiếu reference hoặc giả thuyết bị
loại, ghi unresolved và tiếp tục phần độc lập; không né sang TTS hoặc rerun y hệt.

Sau thay đổi có căn cứ: chạy test gần code/checks phù hợp, kiểm đúng bytes đã đo,
review diff và allowlist, cập nhật `status.md`/báo cáo khi có kết quả bền vững,
commit/push đúng scope rồi verify remote/stash/worktree. Ghi hashes, commands,
counts/timing và pass/fail/not-run trong audit mới; không đưa raw/private data vào Git.

Giữ recipe giọng B tại
`work-dir/BV1GFbk6LEVm-voiceB-20260916-192625/voice-b-recipe.json` và mọi media
liên quan. Reference Việt 5,16 s SHA
`509ff70aee71483ec547a0d86d354e153cb61f07ca28e76b3da4078384b14c2d`,
`instruct=female`, `language=vi`, seed0, 32 steps, speed1×. Chưa tích hợp/TTS.

**Bắt đầu ngay bằng Git/evidence, rồi triển khai candidate PaddleOCR-VL opt-in
và khóa gate D1/D2 theo budget. Diagnostic nhỏ đã xong, không lặp lại. Đối chiếu
ASR bằng AI visual reference đã được user chấp nhận, không chờ human transcript.
Giữ bất định lời nói đúng phạm vi. Không kết thúc chỉ bằng nhắc
lại kế hoạch, sweep model hoặc chạy lại candidate đã thất bại.**
