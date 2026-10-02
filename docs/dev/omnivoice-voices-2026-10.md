# OmniVoice: thư viện giọng cố định — 2026-10-02

## Nguyên nhân và đối chiếu

Worker cũ gửi `instruct="female"` hoặc `"male"` cho mỗi request mà không có
reference. Đây là mô tả thuộc tính, không phải ID của một người đọc. Cùng seed
không khóa danh tính giọng giữa các text khác nhau.

[OmniVoice tại revision đang ghim](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/README.md#voice-design)
nêu voice cloning là mode ổn định nhất; voice design được train bằng dữ liệu
Trung/Anh và có thể thiếu ổn định ở ngôn ngữ khác.

[BetterBox-TTS](https://github.com/nowtranminh1-TTS/BetterBox-TTS) có lựa chọn
reference WAV + TXT cùng tên và dùng chung reference khi sinh từng đoạn. Đây là
cách hữu ích cho vấn đề hiện tại. “Voice Profile Builder” trong README thuộc
Viterbox, không phải OmniVoice. Các phần pitch/VAD/Chunkformer/fine-tune là tính
năng hoặc model khác, chưa phải bằng chứng cải thiện độ đồng nhất giọng của app.
README BetterBox ghi CC BY-NC và các audio mẫu lấy từ TikTok; thay đổi này được
viết riêng trên API OmniVoice đã có, không sao chép code hoặc mẫu giọng của repo đó.

## Hành vi mới

- Bốn mẫu AI tiếng Việt: `vi-female-1`, `vi-female-2`, `vi-male-1`, `vi-male-2`.
  Các tên hiển thị là Nữ 01, Nữ 02, Nam 01, Nam 02. Không cam kết giọng vùng miền.
- `female` và `male` cũ lần lượt chọn Nữ 01 và Nam 01. `auto` vẫn tự sinh từng
  câu; UI ghi rõ có thể đổi giọng. Audio + lời mẫu tường minh của CLI vẫn ưu tiên.
- Job chụp một bản reference riêng và tạo một `voice_clone_prompt`, dùng lại cho
  mọi câu. Không cho đổi sang giọng khác giữa job đang giữ một reference.
- Cache chứa SHA của audio/lời mẫu và ID profile; cùng mẫu và cấu hình dùng lại
  được cache. Worker hash mới ngăn dùng nhầm WAV tạo theo cơ chế cũ. Không xóa cache cũ.
- GUI có danh sách giọng, Nghe mẫu/Dừng nghe, nhập audio và tên giọng riêng.
  File `.txt` UTF-8 cùng tên audio được đọc tự động nếu có; user có thể sửa lại.
- Lưu giọng chạy FFmpeg trong QThread: bản sao WAV PCM16 mono 24 kHz, dài 3–10 s,
  không crop, đổi tốc độ hoặc tự sửa lời mẫu. Audio toàn zero bị từ chối; chưa có
  nhận diện nhiều người nói hay đánh giá độ sạch tự động.
- Thư viện riêng ở `APPDATA_PATH/voices/omnivoice`, mỗi profile có ID riêng, WAV
  và metadata; file gốc được giữ. Mất/hỏng giọng đã chọn sẽ báo lỗi, không đổi giọng
  ngầm. Chọn giọng cố định không bị audio mẫu cũ trong settings ghi đè, kể cả CLI
  kế thừa settings GUI.
- Tốc độ/timing/mixer dùng cấu hình hiện có. Worker vẫn chạy ngoài Qt và được đóng
  sau job. Bốn reference nhỏ được bundle cùng app, không cài thêm dependency.

CLI dùng `--tts-provider omnivoice-local --voice vi-female-1` (hoặc một ID khác).
Giọng riêng đã lưu dùng `--voice saved-<id>` trong cùng app data; CLI với reference
tường minh tiếp tục dùng `--omnivoice-reference-audio` và
`--omnivoice-reference-text-file`.

## Evidence và giới hạn

Audit: `.tools/omnivoice-voices-20261002/`.

- Regression trước sửa: 1 fail vì `female` không có reference. Sau sửa, bộ
  OmniVoice/dubbing/CLI/editor voice regeneration: **357 pass**, 2 warnings.
- Ruff toàn app/tests pass; Pyright toàn app **0 errors / 0 warnings**;
  translations in sync. Kiểm import có FFmpeg thật, QThread được join, cache
  phân biệt audio/transcript, private library cô lập khỏi dữ liệu của user.
- Sau sửa lời hướng dẫn và tránh transcript cũ khi đổi audio: **43 tests
  OmniVoice pass**. Không cộng dồn với suite 357 vì có overlap. Test chạy worker
  bằng stub cũng cô lập `logging.disable` khỏi các test chạy sau.
- Bốn reference mới tạo từ model đã cài, dài 4,90–5,16 s, mono24k PCM16. Catalog
  giữ revision, seed, instruction, script gốc và SHA. Mỗi giọng tạo tiếp hai câu
  khác nhau ở 1,00× qua production runtime trên GPU thật: **8 WAV mới**, tất cả
  worker/GPU lease đóng sau job. `gpu-verification.json` giữ hashes và số đo.
- `listening/*-review.wav` ghép mẫu giọng và hai câu mới để user nghe so sánh.
  Chưa có nghiệm thu nghe về độ giống người đọc, giới tính, phát âm hoặc tự nhiên.
  Việc dùng chung prompt là bảo đảm của data path, không phải bảo đảm giọng hoàn
  toàn đồng nhất ở mọi câu.

## Đóng gói

Lượt frozen đầu đã phát hiện `copy_payload()` bỏ mọi file ẩn, trong khi recipe
OmniVoice kiểm cả `model/.gitattributes` và `model/audio_tokenizer/.gitattributes`.
Do đó một bộ weights đủ vẫn bị từ chối là chưa sẵn sàng. Regression trước sửa
**1 fail**; sau sửa **15 tests packaging pass**, bao gồm giữ `.libs`, bỏ secrets/
cache và các guard OCR. Builder cho phép đúng tên `.gitattributes`; không đổi
weights, runtime hoặc bỏ kiểm checksum. Stage cuối **99.315 files /
42.353.432.041 bytes**, recipe OmniVoice verify pass.

Lượt PyInstaller đầu gặp ACL ở `build/VideoCaptioner/Analysis-00.toc`; lượt sau
dùng work/cache riêng dưới audit. Lệnh frozen đầu đặt `--config` sai vị trí đã
được sửa trong helper; các log fail được giữ, không tính chúng là TTS inference.
Helper GUI đầu in Unicode ra console GBK lỗi sau khi đã ghi receipt: bản app
vẫn mở 20 s, đóng exit0 và không còn child. Helper đã sửa output encoding.

### Gate artifact cuối

- `dist/VideoCaptioner-20261002-omni-voices/`: PyInstaller exit0, 182,59 s,
  **6 WARNING / 0 ERROR** trong build log (các warning platform/import giống
  nhóm baseline; dependency còn có SyntaxWarning/UserWarning).
- EXE **31.555.520 bytes**, timestamp **2026-10-02 10:31:28 +07:00**, SHA-256
  `d7727ff563d71a85130cf5a506f7769cb111dd4e62c40a5ccc87c1454bf001cc`.
- Catalog/README/4 WAV bundle khớp SHA source. **99.315 model/runtime files**
  khớp size inventory sau copy; stage đã kiểm SHA. Recipe OmniVoice tiếp tục
  được kiểm checksum trong từng job thật. Không gọi size check của toàn EXE
  payload là rehash toàn bộ model lần nữa.
- Có Faster-Whisper runtime + large-v3/tiny, Qwen, OmniVoice, VieNeu runtime/model,
  OCR-v6-medium. Không có component diarization/Community-1 riêng trong bộ đang
  cài được sao chép; không tải thêm model.
- Frozen CLI trên video tổng hợp 18 s, không có audio gốc: **2 nhóm / 2 WAV mới /
  0 cache**, sau đó **2 cache hit / 0 TTS attempts**. Cả hai exit0, tạo video,
  0 lỗi/rewrite/tăng tốc/trễ; video cùng SHA
  `fdcae64e78eaca1dd564cf1c177505e756da46315a701024895a1c41d9f78773`.
  Runtime tự tìm model cạnh EXE sau khi chuyển từ vị trí cài trên ổ khác.
- GUI cuối mở 20 s có cửa sổ chính, đóng exit0; cả GUI và hai workflow frozen
  không còn owned child processes. Layout panel được render/kiểm ảnh riêng;
  chưa có nghiệm thu thao tác nghe mẫu bằng GUI native hoặc nghe chủ quan.
- Receipts: `artifact-verification.json`, `gui-smoke.json`, `build-result.json`,
  `stage-repair.json`; lỗi trước được giữ trong log riêng. Không test thêm
  ASR/translation/online hoặc một video thật dài trong phiên này.

## File triển khai

- `videocaptioner/core/tts/omnivoice/runtime.py`, `voices.py`;
  `videocaptioner/resources/omnivoice/worker.py`, `voices/` (catalog, README, 4 WAV).
- `videocaptioner/ui/components/omnivoice_panel.py`,
  `videocaptioner/ui/thread/omnivoice_voice_thread.py`,
  `videocaptioner/ui/common/config.py`, `videocaptioner/ui/task_factory.py`,
  `videocaptioner/ui/view/dubbing_interface.py`.
- `videocaptioner/cli/config.py`, `scripts/package_test_models.py`, `VideoCaptioner.spec`.
- `tests/conftest.py`, `tests/test_cli/test_config.py`,
  `tests/test_omnivoice/{test_provider,test_ui,test_voices,test_packaging}.py`.
- `README.md`, `status.md`, tài liệu này. Artifacts và scripts kiểm chứng nằm
  riêng trong `.tools/omnivoice-voices-20261002/`; không commit/push.

Bản cài người dùng đang dùng không được thay trong bước tạo artifact thử. Các
gate OCR/ASR cũ không thay đổi bởi công việc này.

## Khảo sát mở rộng BetterBox-TTS

Cập nhật sau khảo sát: P1 → P1b → P2–P4 đã được triển khai và kiểm riêng trong
[báo cáo nâng cấp](omnivoice-batching-2026-10.md). Nội dung dưới đây giữ ngữ cảnh
khảo sát của snapshot cũ; không thay các evidence/giới hạn của artifact cũ ở trên.

Ngày 2026-10-02, đọc code tại commit
[`1192005fdd150b6383fcf0c4bf1f6d121de83d0f`](https://github.com/nowtranminh1-TTS/BetterBox-TTS/tree/1192005fdd150b6383fcf0c4bf1f6d121de83d0f).
Đây là khảo sát source; chưa chạy BetterBox, benchmark, tải model hay triển khai
thêm các mục bên dưới. Snapshot code tham khảo và provenance ở
`.tools/betterbox-survey-20261002/`; không đưa code BetterBox vào app.

| Tính năng đã thấy trong BetterBox | Đối chiếu và hướng áp dụng |
| --- | --- |
| Danh sách WAV, TXT cùng tên, nghe mẫu, upload/thu bằng microphone | VideoCaptioner đã có danh sách/lưu/nghe mẫu; thu trực tiếp là phần có thể bổ sung sau. |
| Cache `voice_clone_prompt` cả RAM và JSON disk: tokens, transcript, RMS | App hiện tái dùng prompt trong một job. Nên khảo sát cache giữa các job, bind thêm revision model/tokenizer/worker và preprocessing; cache này khác WAV cache. |
| Thiếu transcript thì tự load Chunkformer để chép lời reference | Có thể làm nút chép lời mẫu bằng ASR đã cài, cho user sửa/duyệt trước khi lưu. Không cần tự thêm model ASR mới vào mọi job TTS. |
| Omni có cấu hình 64 steps, FP32, guidance/temperature và preprocessing riêng | Có thể đưa preset Cân bằng/Ưu tiên chất lượng lên UI. Cần A/B giọng, đủ chữ, thời gian và VRAM; cấu hình này chưa chứng minh tốt hơn bản 32-step/FP16 hiện tại. |
| Pitch bằng Pedalboard và speed từ model là hai điều khiển riêng | Đáng bổ sung pitch mặc định trung tính; đo lại duration và đưa tham số vào cache. Speed hiện tại tiếp tục theo lựa chọn của user. |
| Chuyển số sang chữ Việt, chia text và chèn nghỉ theo dấu câu | Nên có lớp lời đọc có thể xem/duyệt, bảo toàn subtitle gốc; mở rộng có kiểm soát cho số, đơn vị, viết tắt. Khoảng nghỉ phải đi qua scheduler/timing hiện có. |
| VAD và xử lý silence sau từng đoạn | Có thể học cách phát hiện đầu/đuôi nhiễu, nhưng chỉ bật trim khi có bằng chứng không mất âm đầu/cuối; giữ WAV gốc để đối chiếu. |
| Sinh audio kèm SRT từ duration từng đoạn sau xử lý | Hữu ích cho chế độ nhập văn bản → giọng đọc + SRT. Editor hiện đã có đường tạo `tts.srt` nội bộ; nên tái dùng thay vì tạo một hệ timing khác. |
| Chỉ giữ model được chọn; unload model kia khi chuyển provider | App hiện có GPU lease và đóng Omni worker sau job. Có thể học UI trạng thái model; không đồng nhất cache prompt với việc giữ model trong VRAM. |
| Gợi ý KhanhTTS-OmniVoice fine-tune Việt/Anh | Là ứng viên để so sánh riêng, không thay model hiện tại chỉ dựa vào mô tả. [Model card](https://huggingface.co/kjanh/KhanhTTS-OmniVoice) nêu mục tiêu phát âm và clone, chưa là phép đo trong VideoCaptioner. |

Các điểm phải đọc theo đường gọi thực tế:

- [Nhánh Omni trong `app.py`](https://github.com/nowtranminh1-TTS/BetterBox-TTS/blob/1192005fdd150b6383fcf0c4bf1f6d121de83d0f/app.py)
  nhận reference, text, language, speed và pitch. `emotional_profile` chỉ được
  truyền cho Viterbox, dù dropdown hiển thị ở phần Settings chung.
- `general/EQ_emotion_config/eq_emotional_profiles.py` hiện có preset sad/question
  chủ yếu đổi amplitude envelope, kèm high-pass/limiter. Không coi đó là khả năng
  điều khiển cảm xúc ngôn ngữ của OmniVoice.
- `viterbox/pretrain_voice_builder.py` tạo `conds.pt` từ speaker embeddings và
  context nhiều cửa sổ, tối đa 20×80s. Đây là công cụ riêng của kiến trúc Viterbox,
  không phải bộ tạo giọng OmniVoice có thể chép sang trực tiếp.
- [Cache prompt và cấu hình inference](https://github.com/nowtranminh1-TTS/BetterBox-TTS/blob/1192005fdd150b6383fcf0c4bf1f6d121de83d0f/OmniVoice/omnivoice_inference/omnivoice_support/ttsOmni_Config.py)
  có ý tưởng hữu ích, nhưng cache key hiện chưa bind model revision/preprocessing;
  khi áp dụng cần giữ contract SHA/revision của VideoCaptioner.
- `ttsOmni.py` gọi `clearText()` trước `segment_text()`. `clearText()` casefold và
  đổi nhiều dấu câu thành dấu phẩy, nên bảng pause theo loại dấu không còn nhận
  nguyên loại dấu gốc. Đây là nhận xét static, chưa đo tác động nghe.
- `noise_detect_VAD.py::vad_trim()` dùng `collect_chunks()` nối các speech spans;
  không chỉ trim khoảng lặng đầu/cuối. Sau đó còn rút silence bằng helper riêng.
  Không dùng nguyên chính sách đó cho phụ đề có timeline sẵn.

Thứ tự đề xuất: **preset chất lượng + cache prompt → lời đọc tiếng Việt có preview
→ pitch/ngắt nghỉ có đo duration → chép lời mẫu và tiện ích thu/xuất audio**.
Fine-tune khác hoặc profile/cảm xúc từ Viterbox là nhánh đánh giá riêng. Mọi mục
trong thứ tự này vẫn là đề xuất khảo sát, chưa được triển khai trong bản EXE đã build.
