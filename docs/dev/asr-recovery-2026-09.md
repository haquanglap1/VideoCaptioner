# Soniox SRT, ngôn ngữ Qwen và gói model portable — 2026-09-10

User yêu cầu sửa review Soniox và lỗi Qwen trong ảnh, kèm các model/runtime đã cài
vào thư mục model khi build EXE test, rồi bàn giao prompt cho phiên OCR. Làm tại
`VideoCaptioner-ASR-S3`, `codex/asr-s3-native`, từ HEAD `f03420c` và các thay đổi chưa
commit của những lượt trước. Không commit/push hoặc thay dependency app.

## Soniox

Kết quả user đã có trên R2: clip **111,333 s**, **185 token** gồm 11 token khoảng
trắng; text/token coverage khớp. Hai token lời nói có start=end tại **83.010 ms**
và **104.010 ms**, `word_timing=false`. Parser trước đây chặn lexical token 0 ms
trước khi gom câu nên không xuất SRT dù có mốc câu dùng được.

- `parse_native(..., word_timing=False)` gom cue cùng nguồn/người nói theo đường
  native hiện có. Token 0 ms chỉ được giữ nếu cue có duration dương và có span lời
  nói dương trong cùng cue cách point timestamp không quá 800 ms. Đầu/đuôi cue
  có thể dùng point timestamp do provider trả; không tự dựng duration cho token.
- Các kiểm tra coverage, thiếu/NaN/âm/đảo/vượt audio, speaker/source và cue không
  có anchor giữ nguyên. Cue toàn 0 ms vẫn review. Word output và Scribe raw zero
  vẫn strict. Không gọi fuzzy match, nội suy, chia đều, ép nhãn speaker hoặc sửa chữ.
- Review câu cũ dùng cùng validator khi resume, giữ checksum/raw/overrides/schema.
  Cache vẫn giữ raw response, được parse lại theo kiểu output; cache dùng cho câu
  không trở thành bằng chứng word timing hợp lệ, không upload lại khi word bị từ chối.
- GUI pipeline bật split dùng sentence spans của native/Qwen; không ngầm yêu cầu
  strict word output chỉ để phân đoạn. CLI word request tường minh giữ nguyên.

**Phục hồi dữ liệu thật:** source core rồi CLI frozen ở ổ C đều xuất **21 cue**
từ review có sẵn. Giữ đầy đủ text và 174 ID lời nói/punctuation; 11 token khoảng
trắng giữ trong text theo parser hiện có. **0 override, 0 request provider mới**,
review gốc giữ SHA-256. SRT source/frozen giống byte, SHA-256
`08ba491e8db5218f399ac5ac231abd7c39190d5dd01247f6dae15228dfe59595`.

Output tại `build/asr-recovery-20260910/output/`:
`soniox-recovered.zh.srt`, `soniox-recovered.zh.json`,
`soniox-recovered-frozen.zh.srt`. Đây là timing ghép câu từ số đo native, không
phải per-word alignment đã được sửa hoặc nghiệm thu độ chính xác lời nhận dạng.

## Qwen và Faster-Whisper

Lỗi Qwen trong ảnh xảy ra trước recognition: GUI truyền Auto vào luồng chỉ hỗ
trợ Chinese, nhưng trang Qwen không có ô ngôn ngữ riêng để user sửa.

- Thêm ô ngôn ngữ ngay trong cài đặt Qwen, ghi rõ Auto của GUI dùng preset Chinese
  (zh), không phải language detection. TaskFactory chỉ áp preset cho Qwen khi
  nguồn đang Auto; không thay giá trị đã lưu của engine khác. Ngôn ngữ khác chọn
  tường minh vẫn được giữ và dừng trước recognition/prepare với chỉ dẫn rõ.
- CLI vẫn dùng `--language zh`; guard alignment S2 không thay đổi và không tự
  suy ngôn ngữ từ transcript để ép align. Qwen worker/model/policy không đổi.
- Faster-Whisper có thể tìm executable trong thư mục managed tại thời điểm gọi,
  kể cả cài sau khi GUI đã mở. Đường dẫn file riêng sai vẫn lỗi, không rơi sang
  một engine khác. Manager và nút mở thư mục nhận cả `models/tools/` của gói portable.

## Model/runtime đi kèm bản test

`models/portable-models.json` đánh dấu bộ model cạnh EXE. `MODEL_PATH` dùng bộ này
nếu có; mặc định của Qwen/Community-1, OmniVoice và VieNeu tìm runtime tương ứng
bên trong. Các đường dẫn ngoài được user chọn tường minh vẫn ưu tiên. App giữ
cache/settings riêng ở AppData. Không nhét weights vào `_internal` hoặc Qt process.

`scripts/package_test_models.py` chỉ sao chép cài đặt đã có, kiểm tra SHA sau copy,
không tải/cài dependency. Khi nguồn là venv, bỏ `pyvenv.cfg` mang đường dẫn cũ và
chép CPython base 3.12 hiện có cạnh Lib/site-packages. Runtime dùng interpreter
trong chính gói; không dựa vào Python của máy dev. Giữ recipe, model revision,
license, manifest và Python/runtime riêng từng engine; loại cache tải, log và
file cá nhân. Source installation giữ nguyên.

Các thành phần được chọn: Faster-Whisper XXL + large-v3; Qwen 0.6B/1.7B và
ForcedAligner; Community-1; OmniVoice + audio tokenizer; VieNeu runtime/model store.
Model cloud Soniox/LLM không có weights local để chép. Gói không thay thế cài đặt
driver GPU hoặc chứng minh mọi model đều inference tốt ở máy khác.

Spec hỗ trợ `VC_TEST_MODELS_DIR` để chép bộ đã stage vào onedir; AGENTS.md và
CLAUDE.md ghi đây là mặc định cho bản test user, trừ khi user yêu cầu bản nhẹ.
Không đưa credential, settings/media hay cache job vào payload model.

## Gate source

- 16 ca Soniox sentence/strict/bounds/anchor/coverage/review; thêm ca cache sentence
  → word không upload lại, 6 ca GUI language/native/discovery và 4 ca portable path/copy.
- Bộ mở rộng **951 pass / 23 deselected / 1 warning**: ASR, UI, CLI, OmniVoice,
  VieNeu, thread và portable helper. Sau bổ sung discovery manager, **21 test scoped
  pass**. Không cộng chồng hai lượt thành một số test chạy duy nhất.
- Ruff app/tests/packager pass; Pyright app 0/0; translations in sync. Test dùng
  settings/cache/temp riêng, giữ `thread.wait()`. Không chạy fresh Soniox hoặc TTS.
- Qwen Python đã materialize được kiểm tra trong process riêng với `-I`: Python,
  stdlib, NumPy và Torch đều nằm trong gói; Python 3.12.13 / Torch 2.8.0+cu128 /
  qwen-asr 0.0.6. Không import GPU library vào Qt.

## Bản EXE và bàn giao

Onedir `dist/VideoCaptioner-ASRRecovery-20260910/`. Build cuối sau cập nhật manager
**exit 0 / 198,274 s**, 6 WARNING / 0 ERROR (js/emscripten, curl_cffi, yt_dlp_ejs,
tzdata, sip, AppKit). First build 193,948 s được giữ trong evidence, không cộng gate.
EXE **31.267.206 byte**, local **2026-09-10 15:40:37**, SHA-256
`bb6a7dfcbb10bcb5f1ffe48cda39788a16f1b77469c825f70e89e5fb5c2a1624`.

CLI frozen phục hồi Soniox ở ổ C đã pass. **15 module PYZ** khớp source cuối,
gồm native parser/review, Qwen, model paths, TaskFactory, manager và startup guard.

**Payload model: 123.133 file nguồn kỳ vọng / 48.340.488.248 byte**, không download.
Sau khi copy đủ, vòng checksum tuần tự chậm được dừng có kiểm soát; một verifier
12 thread đối chiếu lại đầy đủ SHA-256 của từng file nguồn với bản chép. Không bỏ
gate checksum hoặc coi exit bị dừng của helper cũ là thành công. Manifest mới ghi
đúng các file đã xác minh. Bytecode Python phát sinh khi kiểm tra là cache phụ.

| Thư mục trong models | File đã verify | Dung lượng GiB |
| --- | ---: | ---: |
| tools/Faster-Whisper-XXL | 5.116 | 4,36 |
| faster-whisper-large-v3 | 7 | 2,88 |
| qwen (0.6B, 1.7B, aligner và runtime) | 31.783 | 15,47 |
| diarization (Community-1 và runtime) | 28.367 | 4,65 |
| omnivoice | 31.664 | 10,59 |
| vieneu-runtime | 26.146 | 5,43 |
| vieneu (model store) | 50 | 1,64 |

Đã chép toàn bộ model/runtime sang bản test ở ổ C và đối chiếu lại toàn bộ hash.
Bốn interpreter đều **Python 3.12.13**, stdlib/NumPy/Torch nằm trong gói; Torch
Qwen/OmniVoice/VieNeu **2.8.0+cu128**, Community-1 **2.9.1+cu128** đúng môi trường
riêng đã cài. Không import CUDA/model vào Qt. CLI frozen `local-asr status` không
truyền root tìm đủ Qwen 0.6B/1.7B, aligner, Community-1, exit 0.

**GUI frozen ổ C:** cửa sổ sau 1,569 s, sống đủ 45 s; tổng **45,828 s**, đóng
đúng process **exit 0**, không child sót, traceback hoặc hoạt động update ngoài
ý muốn. Không bật Computer Use. Chưa chạy inference ASR/TTS mới cho mọi model;
chỉ nhập thư viện, xác minh file/đường dẫn, khởi động GUI và phục hồi review đã có.

Evidence duy nhất của phiên nằm trong `build/asr-recovery-20260910/`, giữ
output/review/gate lỗi và source snapshot. Bản test tại `Temp/vcm910/` đã đóng;
kiểm duyệt tự động chặn xóa nó (`blocked by policy`), nên vẫn còn trên ổ C.
Không thử cách khác để vượt chặn; gói bàn giao và nguồn model đều giữ nguyên.

[Prompt phiên OCR](ocr-next-session-prompt.md) đã mở lại OCR-1 theo yêu cầu mới:
pilot local và AI đọc cùng 13 crop, không lặp ASR/dịch/TTS đã xong. OCR chưa chạy
trong phiên sửa này; model vision/endpoint/budget chưa được chọn. Các giới hạn
ASR/TTS/chất lượng nghe còn lại không bị đổi thành pass hoặc chặn OCR vô thời hạn.

## File sửa trong lượt này

- `videocaptioner/config.py`; `core/asr/{native_result,native_api,review,faster_whisper}.py`;
  `core/asr/local/{pipeline,runtime}.py`; `core/tts/omnivoice/{config,runtime}.py`;
  `core/tts/vieneu/{runtime_locator,service}.py`; `ui/task_factory.py`;
  `ui/components/{local_asr_cards,FasterWhisperSettingWidget}.py` dưới `videocaptioner/`.
- `tests/test_asr/{test_native_asr,test_soniox_sentence_timing}.py`,
  `tests/test_ui/test_local_asr.py`, `tests/test_utils/test_portable_models.py`.
- `scripts/package_test_models.py`, `VideoCaptioner.spec`, `AGENTS.md`, `CLAUDE.md`,
  `README.md`, `status.md`, tài liệu này, `docs/dev/asr-s41.md`,
  `docs/dev/ocr-next-session-prompt.md`, `docs/plans/video-subtitle-ocr-integration-plan.md`.
- Giữ thay đổi từ trước ở main_window/version-checker test và các báo cáo portable/
  speech-segmentation/speech-listening. Không commit/push.

Sau nghiệm thu, user yêu cầu “submit and push”: startup update chốt ở `9ae8465`,
Soniox/Qwen và model portable ở `1a10f69`; tài liệu theo sau. Các ghi chú không
commit/push phía trên là lịch sử trước yêu cầu này. Lấy HEAD cuối/tracking từ Git;
không suy quyền push cho phiên OCR. Chỉ source/test/docs được đưa vào Git.
