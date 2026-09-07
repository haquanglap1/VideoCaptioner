# Prompt bàn giao — thực hiện ASR bước 2

Triển khai S2 của kế hoạch ASR VideoCaptioner đến hết code, kiểm thử phù hợp và bàn giao;
không chỉ đề xuất lại kế hoạch. User đã chấp nhận hướng triển khai S1–S6 và S1 đã hoàn tất
code/offline. Phạm vi session này chỉ là S2; không tự triển khai S3–S6.

## Baseline và tài liệu cần đọc

- Bắt đầu từ nhánh `codex/asr-s1-api-profiles` trên `origin` của repo
  `https://github.com/haquanglap1/VideoCaptioner.git`. Xác nhận commit có S1 trước khi sửa;
  không mặc định `master` đã chứa S1. Nếu tạo worktree mới, lấy đúng nhánh này làm baseline.
- Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-provider-plan-2026-09.md` và `docs/dev/asr-implementation-2026-09.md`.
  Các tài liệu này đã được đưa vào commit S1; không cần copy từ checkout khác.
- Chạy `git status --short --branch`; giữ mọi thay đổi ngoài task. Tìm call site bằng `rg`
  trước khi sửa. Không reset/cherry-pick hàng loạt hoặc sửa checkout khác để xử lý baseline.

## Mục tiêu S2

Nhận dạng video/audio tiếng Trung, chủ yếu phổ thông, bằng model text-only qua gateway
VideoCaptioner API; căn text với audio thật để tạo ASRData/SRT có timing hợp lệ. Đầu ra này
phục vụ pipeline dịch sang tiếng Việt hiện có. Không cần alignment/ASR tiếng Việt.

Gateway: `https://api.videocaptioner.cn/v1`, POST `/audio/transcriptions`, Bearer key của
gateway. Model đã khai báo: `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `whisper-1`.
GPT dùng JSON, không gửi timestamp kiểu Whisper. Đọc lại tài liệu chính thức trước khi
triển khai; dùng OpenAI Docs cho phần OpenAI. Catalog không chứng minh quyền inference.

## S1 đã có và phải giữ

- `core/asr/api_profiles.py`: registry SDK-free, preset/provider/model/request profile,
  normalize endpoint, fingerprint cache v2 và guard `require_subtitle_timing`.
- `core/asr/api_transcription.py`: builder/parser/transport chung, `TranscriptionResult`
  có text và words/segments tùy chọn, MIME theo bytes, byte cap, timeout và retry hữu hạn.
- `WhisperAPI` và factory trong `transcribe.py` hiện chặn text-only trước đọc/chia audio/upload
  cho subtitle; probe không bị guard này chặn và báo riêng timing quan sát được.
- GUI/CLI giữ custom model/base/prompt/language, key theo endpoint, preset và request profile.
  `auto` nhận biết đúng ID đã khai báo, ID khác giữ Whisper legacy; alias riêng có override.
- Cache không dùng key/prompt/path nhạy cảm trong tên/log, không đọc cache legacy lẫn endpoint.
- Worker probe chung ở `ui/thread/whisper_connection_thread.py`, có contextvars; không network
  khi mở settings. Config startup không được import OpenAI/modelscope/yt_dlp sớm.

Baseline validation: ruff toàn source/tests pass; pyright 0 error/0 warning;
full offline 720 passed, 5 skipped, 51 deselected. Skip gồm QtMultimedia native playback và
TTS ngoài; chưa chạy API ASR thật, chưa nghiệm thu EXE hoặc GPT→SRT. Không biến kết quả mock
thành tuyên bố E2E. Chi tiết nằm ở mục bàn giao S1 trong tài liệu implementation.

## Công việc S2 và tiêu chí nghiệm thu

1. Thiết kế contract alignment audio + text + language → word/character spans canonical ms,
   có offset chunk và trạng thái không align được. Tách domain/core khỏi Qt.
2. Thử Qwen ForcedAligner tiếng Trung trong runtime/sidecar riêng, pin revision và dependency
   tường minh. Xác minh giới hạn input theo tài liệu hiện hành (kế hoạch ghi 5 phút);
   không lấy chunk ASR 10 phút làm chunk alignment mặc định. Tận dụng cách quản lý runtime
   VieNeu nhưng không trộn dependency/model vào runtime VieNeu nếu chưa chứng minh tương thích.
3. Không import Torch/CUDA/model vào Qt process; không cài package global. Runtime mới cần
   manifest/lock có thể tái tạo, đường dẫn đúng source/pip/frozen. Theo AGENTS cho subprocess,
   `child_environment()`, worker và `submit_with_context`.
4. Nối kết quả JSON của S1 qua aligner vào ASRData/SRT và pipeline CLI/GUI hiện có. Chỉ cho
   phép upload model text-only sau preflight xác nhận aligner/ngôn ngữ sẵn sàng. Nếu thiếu,
   giữ lỗi rõ ràng trước upload; không bỏ guard vô điều kiện và không fake timing.
5. Kiểm tra finite/nonnegative/start≤end, giới hạn audio, offset/chunk boundary, overlap,
   không mất/trùng text. Xử lý silence, tên/số, giản/phồn thể, punctuation và text lệch audio.
   Từ không căn được phải có policy review/fallback tường minh; không chia đều thời lượng.
6. Cache alignment tách theo fingerprint audio/text/language, model revision, config và policy.
   Không gửi local path vào prompt/metadata; không log transcript, key hoặc raw response nhạy cảm.
7. Worker/probe local health, cancel/shutdown, timeout/failure rõ ràng, không process sót;
   phân biệt runtime thiếu, đang tải, lỗi và sẵn sàng. Không tự inference/download khi mở settings.
8. Thêm test hồi quy có ý nghĩa cho contract, parser→aligner→SRT, chunk offset/overlap,
   mismatch/silence/unmatched spans, cache invalidation, preflight, config/preset/key isolation,
   worker/lifecycle. QThread qua QEventLoop phải `wait()` trước khi object ra khỏi scope.

## Validation, quyền truy cập và bàn giao

- Chạy ruff toàn `videocaptioner/ tests/`, pyright, test_cli, test ASR/alignment/runtime/UI gần
  thay đổi, sync translations; full offline vì thay shared core. Test phải cô lập config/env/cache.
- Python project 3.10–3.12, dùng môi trường có sẵn hoặc chuẩn bị đúng môi trường project theo
  AGENTS. Nếu mượn interpreter từ checkout khác, kiểm tra `videocaptioner.__file__`/PYTHONPATH
  đang trỏ đúng worktree. Dùng basetemp ngắn nếu gặp ACL/MAX_PATH.
- S1 không có ASR key trong worktree/env. Không tự lấy/copy credential hoặc media riêng từ
  checkout khác. Nếu có key được cấu hình đúng provider, smoke ngắn bằng clip Trung công khai/
  tổng hợp, ghi model/routing, timing và usage không nhạy cảm; không tạo token/mua credit.
- Thiếu key không ngăn hoàn tất code và offline gates. Đo alignment thật trên audio tổng hợp/
  công khai khi runtime khả dụng; ghi riêng phần chưa đo được, cold/warm, peak VRAM, offline
  sau tải và hạn chế môi trường. Không gọi mock là runtime acceptance.
- Nếu thêm runtime resource/dynamic import, cập nhật `VideoCaptioner.spec` và thực hiện gate
  artifact tên riêng theo AGENTS; bảo toàn artifact user. Phân biệt build/startup với workflow thật.
- Cập nhật `status.md` và trạng thái S2 trong tài liệu implementation theo bằng chứng thực tế.
  Bàn giao file đổi, gates pass/fail/skip/chưa chạy, GPT→SRT đã/chưa nghiệm thu, hạn chế và đầu vào S3.
- Không đổi engine mặc định, không thêm Soniox/Scribe, diarization/pyannote, speaker/xưng hô,
  hoặc ASR Qwen đầy đủ (S5). Không commit/push/tag/release/viết GitHub trong session S2 trừ khi
  user yêu cầu thêm. Dừng ở S2 để review.
