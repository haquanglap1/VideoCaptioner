# Tiếp tục ASR sau benchmark S6

Làm tại checkout VideoCaptioner-ASR-S3 user chỉ định, nhánh `codex/asr-s3-native`.
Commit bàn giao chứa prompt này chốt code ASR/CLI, guard dịch thiếu, tests và tài liệu
S6 từ nền lịch sử **63941a8**. Xác minh HEAD và tracking branch bằng `git log -1`
và `git status --short --branch`; các ghi chú “chưa commit” ở báo cáo cũ là trạng thái
tại thời điểm đo. Quyền commit/push lượt bàn giao đã dùng, không tự áp dụng cho thay đổi mới.
Đọc đầy đủ AGENTS.md, README.md, phần mới nhất của status.md, rồi
`docs/dev/asr-s6-results-2026-09.md`, `docs/dev/asr-s6-followup-2026-09.md` và
`docs/dev/asr-ctc-candidate-2026-09.md`. Đọc thêm implementation theo đúng phần cần xử lý.
Chạy `git status --short --branch` trước sửa; không reset/stash hoặc bỏ thay đổi hiện có.

## Kết quả lượt tiếp nối — ưu tiên hơn snapshot S6 bên dưới

Evidence mới: `s6-followup-20260908-204000/` trong job ASR Completion cũ. Đọc
`sentence-score/summary.json`, `ctc-pilot/validation.json`, `ctc-acoustic-diagnostic.json`
và `timing-guard-build/reports/frozen-timing-guard.json`. Không ghi đè report/helper output.

- Đã đo 31 clip sentence mới, dùng lại frozen c03, thêm stress. 32 clip: 1.093 cue,
  **31/32** clip có mọi interval hợp lệ; CER đủ 32 **40,53%**, cùng 28 **36,78%**.
  Timing 35/1.673 utterance: median 185 ms/p95 530 ms, coverage 2,09%; không đổi tập
  rồi so như một phép head-to-head. Stress có 617 cue hợp lệ nhưng CER thô 64,94%,
  đuôi chưa nhãn 22.897 ms: chưa đạt quality. Không lặp batch y hệt.
- SenseVoiceSmall đã tải một weight sau contract/vocab/provenance; lưu riêng trong
  `sensevoice-model/`, SHA đúng, runtime cũ nguyên vẹn. Vocab đủ 91 mẫu không là
  acoustic pass: user 60 s chỉ hai ký tự greedy/99,8% blank, phồn thể bốn target yếu;
  meeting có span âm và RMS failures. **Không tích hợp backend, không clamp hoặc đổi
  script/confidence threshold để pass.** Raw emissions giữ để chẩn đoán không inference lại.
  `ctc-short-preflight.json` chỉ là giả thuyết: hai transcript gap cũ khác lexical với
  bản nguyên 60 s; chưa chạy probe ngắn mới và không có phép so chỉ thay chunking.
- Đã sửa FWW chặn interval không dương trước lọc marker, ở cả sentence/word mode.
  Lỗi corpus thật là cue 10.870→10.870 ms; raw còn nguyên. Test mới
  `test_faster_whisper_timing.py`: 6 red→green, 8 pass; ASR/CLI 595 pass/13 deselect,
  ruff/pyright pass. Không cần chạy lại các gate đó nếu không có thay đổi/rủi ro mới.
- Artifact mới nhất **dist/VideoCaptioner-ASR-S6-TimingGuard-20260908/**, EXE
  31.164.833 byte, SHA-256 **cdfecfafe7009129e2446923ddbe515db8b121b06f2b72808031ee2ccb4a093a**.
  Build exit 0/215,141 s; GUI 25,594 s/exit 0. Frozen raw replay: malformed cả hai mode
  exit 5/không output, hợp lệ exit 0/22 cue giữ text/timing. Đây là fixture replay,
  **0 model inference/API mới**. Nguyên onedir/artifact cũ giữ nguyên.
- Đã có 21 nhãn tên/số chẩn đoán; dò literal cùng clip không là entity accuracy.
  Sáu cờ FWW là số cùng giá trị nhưng viết bằng digits. Rubric Việt 12 cue là agent
  soạn, chưa kiểm định độc lập; không gateway output/cache. Reference API vẫn 0 request.
- User hỏi Whisper 3 GB: đã xác nhận đang dùng **large-v3 FP16**, model.bin
  **3.087.284.237 byte / 2,88 GiB**. Không tải thêm model chỉ dựa vào dung lượng file.

## Chỉ đạo còn hiệu lực

- Hoàn tất ASR trước OCR. OCR vẫn dừng; không cài engine/crop mới hoặc dùng hình ảnh
  để biến ASR thất bại thành thành công. User không biết tiếng Trung; agent tự đối
  chiếu và kiểm thử kỹ thuật, không hỏi xác nhận từng nút.
- User đã chọn corpus công khai + clip hiện có. AliMeeting Eval đã tải, kiểm tra
  CRC64 từ OSS và gzip thành công; không tải lại hoặc tạo thêm bản sao toàn bộ.
- Scribe/ElevenLabs loại khỏi scope theo user; không xin tài khoản/key và không ghi pass.
- Dịch dùng `https://api.videocaptioner.cn/v1`, `gpt-5.6-terra`, timeout 300 s/request.
  Key của job cũ chỉ ở RAM, owner đã thoát; không tìm lại key trong logs/cache/settings.
  Một phép đo reference mới đã chờ key rồi kết thúc với 0 request. Không coi đó là API pass.
- Giữ media, AppData thật, runtime và các artifact bàn giao gốc. Chỉ dọn temp/copy do
  task tạo sau kiểm tra ownership; không xóa vĩnh viễn hoặc làm rơi dữ liệu để dọn máy.
- Không tự commit/push/tag/release cho công việc mới. User đã yêu cầu chốt/push
  snapshot ASR/S6 chứa prompt này; không suy quyền đó thành quyền submit phiên sau.
- Không lặp gate đã pass hoặc retry cùng một model/input/config chỉ để tích số lần chạy.
  Giữ raw, không clamp/swap/interpolate/drop token hoặc đổi script để vượt gate alignment.

## Trạng thái cần kế thừa

**Chưa đạt nghiệm thu sản phẩm.** Benchmark local đã chạy; lỗi ứng dụng tìm được đã
sửa và EXE mới đã kiểm tra. Không đổi engine mặc định, không chuyển OCR.

Evidence chính: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`.
Dataset: `build/asr-session-evidence/datasets/AliMeeting-Eval/`.
Có 32 clip / 66,9079 phút, tám recording, reference Trung + speaker; một stress 26,2308
phút. Archive SHA-256 **dc47343b2474b5ebcf458927e878155f6ddeb59c85e685b3645c32a1f9578d92**.
`prepared/manifest.json` ghi trạng thái lúc chuẩn bị sớm; attestation hiện tại là
`integrity-verified.json`. TextGrid xmax có thể sớm hơn audio; không shift/scale nhãn.

Trên cùng 28 clip có transcript đầy đủ: CER Qwen 0.6B 22,00%, Qwen 1.7B 21,04%,
Faster-Whisper 36,74%. Đây là lexical time-ordered CER có overlap, không phải cpCER.
Hai Qwen đều có một timeout, ba preflight không tìm được khoảng lặng khi chia 30 s.
Strict aligner **0/28** đạt cho mỗi Qwen. Faster-Whisper có text ở 32/32, nhưng word
SRT chỉ 5/32 có mọi interval hợp lệ; chưa nghiệm thu word timing.

Community-1: 11 response có phần đệm cuối vượt media 9–379 ms. Đã sửa tiếp nhận theo
cửa sổ model pin (10 s, hop 1 s, tính cả phần dư sample), **không đổi raw span hoặc
mốc từ/cue**. Source cue vẫn bị giới hạn bởi duration media. Replay 32/32 pass adapter;
policy `overlap-conservative-model-window-v2`, coverage 80% giữ nguyên. DER toàn bộ
raw trong audio UEM: 20,66% không collar, 14,90% collar tổng 250 ms; giữ overlap.
Không nhầm với nghiệm thu speaker/xưng hô. Xem báo cáo S6 để hiểu các tập được chấm.

Clip user nằm trong `VC-UserClip-20260908-114035/` cạnh job chính. Resolve video gốc
qua `reports/source-preflight.json`, không hỏi lại đường dẫn và không quét ổ tìm media.
Chỉ thử 60 s đầu/960.000 sample của video 111,333 s. 0.6B/1.7B nguyên mẫu còn sáu lỗi
alignment. Thử hai phần tại speech gap 29.013 ms từ Community-1 vẫn fail strict cả hai;
không triển khai fallback đó. RMS chunk 30 s cũng không có boundary thích hợp trên clip
có nhạc. Public stress 120 s/chunk fail inference sau 443,969 s; cache giữ bốn chunk
xong, không output/review. Thử riêng vùng lỗi ở 30 s nhận dạng xong, chưa chứng minh
whole stress hoặc alignment đã đạt. Không lặp những thử nghiệm này y hệt.

## Code và artifact hiện tại

- Guard LLM thiếu response: fail batch, không điền source rồi cache; namespace
  `complete-llm-response-v1`. Không xóa cache user.
- Gom cue trước local association, giữ turn/overlap/source/context/overrides. Clip
  user 30 → 9 cue, hết 15 mảnh một chữ; word mode vẫn giữ bằng chứng từng word.
- Adapter cửa sổ Community-1 như trên; không đổi pin/runtime hoặc strict word policy.
- CLI có `--asr faster-whisper`, `--fw-program`, `--fw-model-dir`, `--fw-model`,
  `--fw-device`; executable được chọn không phụ thuộc thư mục đó có trên PATH.
- `process --no-split` không ép word timestamp chỉ để dịch. Native Faster-Whisper
  sentence boundaries không bị logic display timing cũ thay đổi.

Full offline sau model-window fix: **1.187 pass / 5 skip / 51 deselect / 114,72 s**.
Sau sửa cuối giữ native sentence boundaries: regression red → green, ASR/CLI
**587 pass / 13 deselect / 38,88 s**. Ruff/pyright/sync pass. Không rerun full nếu
không có thay đổi hay rủi ro mới; không tính offline/skip thành online acceptance.

Artifact S6 trước guard **dist/VideoCaptioner-ASR-S6-Review-20260908/** (nguyên onedir).
EXE **31.164.611 byte**, SHA-256
**c9604ea57d8e34bfb267f5191ec6b719e5cb72eec206d4d4d2a483d51e730426**.
Build exit 0 / 208,719 s, 6 optional/platform warnings, 0 error, 6 SyntaxWarning;
218 module/PYZ khớp. GUI 25,844 s, đóng đúng PID, exit 0.

EXE process trên WAV user: Faster-Whisper sentence → replay bản dịch thật đã lưu →
SRT Việt, exit 0 / 29,25 s / 9 cue. Quan sát child one_word=0, sentence=true, đúng
model directory. **Replay không phải inference LLM/gateway mới.** SRT Việt trùng hash
với bản đã render trước, nên không render lại. Giới hạn lỗi chữ ASR còn nguyên.
EXE sentence smoke clip R8007_M8011-c03: 58 cue dương/trong bounds, exit 0 / 69,938 s;
không suy cả corpus sentence mode đã đạt. Gắn identity từ đúng input trong fixture rồi
EXE local-diarize: exit 0 / 31,219 s, giữ thời gian/text/IDs/identity, 17 assigned,
40 overlap, một ambiguous. Không gọi fixture binding là tính năng auto-bind của FWW.

## Công việc tiếp theo

1. Đọc report lượt tiếp nối bên trên, rồi `reports/s6-measurements.json`,
   `reports/model-window-replay.json`, `reports/community-uem-diagnostic.json`,
   `s6/*/results.json` khi cần so snapshot cũ.
   Giữ kết quả trước/sau riêng. Không đánh dấu transcript complete là timing/quality pass.
2. Cần một phương án alignment mới có bằng chứng acoustic thực, không sửa timestamp
   lỗi sau suy luận. Jonatas CTC preflight cũ thiếu vocab, không tải weight đó. SenseVoice
   pilot mới có đủ vocab nhưng chưa đạt acoustic acceptance như phần mới bên trên.
   Không dùng unknown/homophone/đổi script để lách coverage. Chốt contract/vocab/provenance
   và giới hạn acoustic trước mọi phương án mới; giữ runtime/model hiện có.
3. Sentence đã có benchmark corpus; chất lượng chưa đủ chọn mặc định. Không chạy
   lại chỉ để tăng số lần pass. Cần giả thuyết mới hoặc thay đổi thực tế trước phép đo tiếp.
4. Phép đo dịch reference đã chuẩn bị ở `s6-translation-reference/`: 12 câu Trung,
   384 ký tự, không upload audio, tối đa 3 request. Trạng thái cancelled-no-key,
   không request nào. Nếu user cung cấp key kín cho job, giữ endpoint/model/scope này;
   không ghi key vào chat/argv/env/file. Giữ report cũ khi tạo một lần thử mới có scope rõ.
5. Còn nhãn/chấm tên-số đủ phạm vi, xưng hô theo quan hệ được xác nhận, phút sửa tay,
   chất lượng stress và độ phủ thể loại/phương ngữ. Không tự biến meeting corpus thành đầy đủ
   cho phim hay nhãn utterance thành ground truth từng chữ.
6. Scribe đã loại; giữ review Soniox cũ, không resubmit upload hoặc gọi lại Whisper/GPT
   đã pass vì lỗi 429 lịch sử. SIP chỉ điều tra khi có triệu chứng/giả thuyết mới.

Các helpers trong build là evidence/dev harness, không phải giao diện sản phẩm.
Build/test temp của các lượt trước đã dọn vào Thùng rác sau khi nén/so hash diagnostics;
artifact giữ nguyên. Lượt `s6-followup-20260908-204000/` còn source snapshot/build work,
validation temp và `timing-guard-build/smoke-copy/` do task tạo; chưa dọn những mục mới này.
Model SenseVoice, emissions/raw và report là evidence cần giữ, không coi là temp build.
`s6-final-build/smoke-app/_internal` cũ còn là junction tới artifact **S6-Review**:
gỡ link đã bị automatic approval review chặn (`blocked by policy`). Không retry lệnh
xóa tương đương hoặc recycle parent qua link; không đụng nội dung artifact đích.
Trước khi chạy lại helper, đọc guard/output của nó: nhiều helper tạo file độc quyền,
không được ghi đè hoặc xóa report chỉ để chạy lại. Kiểm tra process đang sống trước
khi dispatch GPU. Kết thúc bằng trạng thái đạt/chưa đạt/skip đúng bằng chứng, file đã
sửa, và `git status --short`; không gọi ASR đã xong nếu các tiêu chí còn mở.
