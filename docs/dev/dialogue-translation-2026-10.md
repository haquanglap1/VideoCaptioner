# Dịch lời thoại bằng cấu hình LLM của app — 2026-10-02

## Sử dụng

Trong Cài đặt → Dịch bật **Dịch cho lời thoại (LLM)**, dùng dịch vụ LLM hiện
có. Model, API Base, API key, timeout, custom prompt và ngôn ngữ đích đi qua
`SubtitleConfig`/`TranslatorFactory` như chế độ dịch thường. Không có endpoint,
key hay model dịch được hard-code trong tính năng này. Reflect tùy chọn kiểm
tra cách diễn đạt trong cùng response schema, không thêm một dịch vụ khác.

Đầu ra gồm SRT hiển thị và companion `.dialogue.json`; nếu tên JSON đã tồn tại,
chọn hậu tố mới để giữ bản đã duyệt. Chọn chế độ này cũng là chọn lưu companion
được mô tả ngay trên control. CLI hỗ trợ `subtitle` và `process --dialogue`:

```powershell
uv run --frozen videocaptioner subtitle input.srt --dialogue --target-language vi --no-optimize --no-split -o display.srt
uv run --frozen videocaptioner dub video.mp4 --subtitle display.dialogue.json --tts-provider omnivoice-local --voice vi-female-1 --prepare-review wording.json
uv run --frozen videocaptioner dub video.mp4 --subtitle display.dialogue.json --tts-provider omnivoice-local --voice vi-female-1 --review wording.json -o dubbed.mp4
```

Đây là hai bước tường minh: chuẩn bị/duyệt lời rồi yêu cầu đọc lời đó. Lượt
`dub` trực tiếp với kịch bản chưa duyệt dừng trước TTS và trả review. GUI nhận
review để sửa/tiếp tục. Pipeline tự động cũng dừng ở điểm này; không coi một
kịch bản vừa sinh bởi LLM là lời đã được user chấp nhận.

Chọn `.dialogue.json` trong Lồng tiếng áp dụng **preset riêng cho job**:
Natural/sequential, native1.00×, cap1.00×, delay2000ms, gap80ms, rewrite tắt.
Settings toàn app không bị đổi. Giá trị speed1.00 là nhịp của model/reference,
không phải cam kết thời lượng bằng thoại gốc. Wording resume không gọi lại LLM.

## Dữ liệu và bảo toàn

- `dialogue-translation-v1` chứa cue nguồn/timing/ID/speaker/scene, bản dịch
  hiển thị và các `SpeechBlock` typed. Mỗi cue thuộc đúng một parent block,
  đúng thứ tự; context lân cận chỉ được đọc tham khảo.
- LLM dịch hoặc biên tập ngôn ngữ đã có thành lời nói tự nhiên, không tóm tắt,
  không bỏ phủ định/số/tên hay từ lặp có ý nghĩa. Validation cơ học kiểm schema,
  coverage và biên nhóm; không tự chứng minh nội dung đúng nghĩa hoặc audio đủ từ.
- Chia request ở biên câu/lượt thoại với budget hữu hạn; không chỉ cắt cứng N
  cue. Phản hồi thiếu/sai có tối đa2 lượt sửa rồi giữ lỗi, không cache thành công.
- Block không vượt biên speaker/scene đã biết, overlap hay khoảng lặng từ1s.
  Span8s là mục tiêu. Có ngoại lệ tối đa12s để hoàn thành nguồn tiếp câu chưa
  có dấu kết câu; không tăng giới hạn chung cho mọi nhóm. Ngoại lệ này xuất
  phát từ một cặp cue thật dài9,664s bị tách chủ ngữ/vị ngữ ở lượt thử đầu.
- File nguồn/hiển thị giữ nguyên timing; fingerprint phát hiện nguồn trong
  JSON bị thay đổi. Cache dùng nguồn/context/model/endpoint/prompt/policy và
  owned IDs tất định; không dùng output LLM ngẫu nhiên làm cache key.
- Chuẩn hóa số/đơn vị/viết tắt tiếp tục qua nút gợi ý tiếng Việt trong review;
  nội dung mơ hồ cần duyệt. Không thêm pause định lượng bên trong câu hoặc
  tự đổi tốc độ xuống0.95 trong phase này.
- Lời đọc sử dụng `dubbing-plan-dialogue-v1`; report vẫn dùng envelope v1.
  Reader hỗ trợ plan cũ và mới, giữ kiểm membership/fingerprint khi resume.
  File kịch bản khác với report review, không dùng thay thế lẫn nhau.

## Video Editor

Mở `.dialogue.json` giữ cue hiển thị/timing nguồn. Lời đọc cả nhóm nằm ở
`tts_text` của cue đầu, những cue tiếp theo có `tts_text` trống và thông báo
membership. Sửa lời qua CommandStack tại cue đầu, không sao chép toàn câu
vào mọi cue. Đổi giọng cần cùng giọng trong nhóm.

Project JSON `editor-project-v1` giữ một trường dialogue typed bổ sung; SRT
hiển thị vẫn xuất như trước. Sửa text/timing hợp lệ được kiểm lại khi dựng
document từ trạng thái hiện tại. Thêm/xóa/tách/đảo cue làm mapping cũ không
còn hợp lệ thì phải chuẩn bị lại, không âm thầm dùng kịch bản cũ.

Regenerate giữ một WAV cho mỗi parent; preview không phát lặp theo số cue.
Thời lượng lấy từ WAV thật, preview giữa câu dùng audio offset đúng vị trí.
Export là yêu cầu đọc lời đang sửa trong Editor, vẫn kiểm preset/timing và
giữ review nếu không vừa. Hiển thị phụ đề không được tự gán timing từng từ
từ tỷ lệ ký tự của bản tiếng Việt.

## Phép thử có giới hạn

Audit: `.tools/dialogue-implementation-20261002/`.

User chỉ định video/SRT và file credential, chọn gateway VideoCaptioner cho
lượt A/B. Key chỉ đọc trong tiến trình thử, không vào source, môi trường child,
artifact bundle hoặc settings của user. Tính năng bình thường dùng cấu hình
LLM của app. Corpus giữ raw/hash; lấy0–150s,66/140 cue từ SRT tiếng Việt đã có.
Không dùng lượt thử này để nghiệm thu bản dịch so với thoại tiếng Trung gốc.

- LLM `gpt-5.6-terra` qua gateway được user chỉ định:6 responses,158,203s,
  66 cue →45 block, coverage/order/source preservation pass. Đây là lần thử
  prompt ban đầu; raw output giữ nguyên. Có kiểm riêng cho ngoại lệ tiếp câu
  sau khi nhận diện giới hạn8s, không dịch/TTS lại cả corpus để thay số đo A/B.
- A (cách gom cũ):22 WAV mới,198,91s lời đọc,21 nhóm cần review,
  max start delay47,919s. B (lời thoại mới):45 WAV mới,207,68s lời đọc,
  44 nhóm cần review, max start delay60,779s. Cùng Nữ01/batch1/32-step/1×,
  no rewrite, delay2s, gap80ms. Zero provider failures; không tăng tốc/cắt lời.
- **Cả A và B không đạt timing2s**. B không chứng minh cải thiện thời lượng.
  Audio đầy đủ để nghe nằm ở `tts-A/A-full-speech.wav` và
  `tts-B/B-full-speech.wav`; đây là audio tuần tự để so sánh, không phải bản
  video đã đạt sync. Không xuất video thành công khi vượt giới hạn.
- Sau sửa ngoại lệ tiếp câu, một request riêng16,125s ghép đúng hai cue dài
  9,664s thành một block. Ghép bản sửa vào candidate mà không đổi source
  fingerprint; bản cuối66 cue/44 block dùng43 WAV cache và chỉ sinh1 WAV mới.
  Tổng lời207,83s, max delay60,849s: vẫn cần review, không đổi kết luận timing.
  Audio cuối ở `tts-B-final/B-final-full-speech.wav`; kịch bản cuối ở
  `live-translation/candidate-final.dialogue.json`.
- Helper A ban đầu hiểu nhầm relative audio paths trong review là absolute;
  đã lấy lại đúng WAV qua cache key, không chạy inference A lần nữa. Giữ log
  lỗi helper, không gọi đó là lỗi TTS. Helper corpus/sai argument test được
  giữ trong log riêng; không cộng chúng vào các gate pass.
- Bộ657 tests liên quan pass,1 skipped,15 deselected (các suite overlap không
  cộng dồn). Full suite lần đầu có lỗi fixture CLI mới dùng lại cache từ lần
  trước, đã tái hiện riêng và cô lập cache; không hạ assertion số request.
  Full suite cuối: **2278 passed /5 skipped /58 deselected**, exit0. Các ca skip
  gồm QtMultimedia H.264 native và bốn ca TTS cần API; không tính là đã nghiệm thu.
- Frozen lần đầu phát hiện CLI `dub` còn chặn `.json` trước engine. Đã sửa
  validator và thêm regression gọi qua CLI; **183 tests** CLI/dialogue pass
  sau sửa. Giữ artifact/log thất bại, build final dưới tên mới.
- Ruff toàn app/tests pass, Pyright0 errors/0 warnings; translations in sync.
- Artifact cuối `dist/VideoCaptioner-20261002-dialogue-final/`: build exit0,
  169,562s,6 WARNING/0 ERROR; EXE31.623.841 bytes, SHA256
  `df4a013f04124c721efc00a37e7580c493dee5c57fc889da883d219e40997e70`.
  Dùng lại portable payload đã verify; không tải model/cài dependency.
  Gate chạy trên artifact ghi riêng tại `frozen-final.json` và `gui.json`.
- Frozen CLI: dịch fixture qua loopback →2 cue/1 block →preview review exit0;
  prompt bundle khớp SHA source;99.315 model/runtime files khớp size inventory.
  Có Faster-Whisper +large-v3/tiny, Qwen, OmniVoice, VieNeu runtime/model và
  OCR-v6-medium; không có Community-1 riêng trong payload kế thừa.
- GPU từ chính EXE trên video tổng hợp10s:1 WAV mới/0 hit, rồi1 hit/0 TTS,
  cả hai exit0, không rewrite/tăng tốc/review; video đầu ra cùng SHA256
  `2f122b67ee34e460e2a3ad28598c737c8484bb52b0034743fcd4c2b7e7ad2110`.
  Không còn owned children. GUI thật mở20s, đóng exit0, không còn child.
  Đây chưa phải nghiệm thu thao tác native với mọi control hoặc nghe chủ quan.

Nghe chủ quan, độ đủ từ của tiếng phát ra, video dài và pause nội bộ vẫn có
gate riêng. Kết quả này không nâng các gate OCR/ASR cũ. Không đổi bản cài hiện
tại, model/runtime hoặc private voices; không commit/push.

## Bàn giao tiếp theo cùng ngày

Sau khi user yêu cầu publish và cập nhật trực tiếp bản chạy thật, đã chép
payload mới vào thư mục chính, giữ nguyên settings/API key/cookies và tái
sử dụng toàn bộ model/runtime đã kiểm SHA. EXE giữ tên cũ để lối mở cũ tiếp
tục hoạt động, nội dung khớp SHA của dialogue-final ở trên. Shortcut hiện tại
là `VideoCaptioner.lnk`; catalog có10 giọng sau chuyển6 profile riêng từ bản phụ.

Bản trùng được xóa sau khi giữ dữ liệu mutable và kiểm payload mới. Thu hồi
42.884.572.839 bytes trong thư mục chạy thật. CLI help pass tại bản chính;
GPU relocation và GUI được kiểm với AppData cô lập nhằm giữ byte cấu hình
user. Receipts, scope publish và prompt tiếp tục nằm trong audit
`.tools/dialogue-release-20261002/`. Nghiệm thu nghe/timing của video thật vẫn
giữ kết luận còn mở; lượt sau phải ASR lại MP4, không biên tập tiếp SRT Việt cũ.
