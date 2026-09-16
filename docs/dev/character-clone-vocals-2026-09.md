# Clone nhân vật và sửa tùy chọn tách vocals — 2026-09-16

User phản hồi mẫu trước thiếu thoại phía sau và giọng chưa hay, yêu cầu
clone giọng nhân vật trong video. Mẫu cũ chỉ chọn ba câu dù ASR đã có cue
tiếp theo; không phải toàn bộ thiếu sót đều do nhận dạng. Lượt này đối chiếu
đoạn 107–126 s và tạo mẫu sáu lượt thoại, không chạy lại toàn video.

## Thay đổi app

`FasterWhisperASR._build_command` kiểm prefix `faster-whisper-xxl` trên toàn
đường dẫn sau resolve. Với đường dẫn cài đặt đầy đủ, bật tách vocals vẫn
không gửi `--ff_mdx_kim2`, đồng thời cache key không phân biệt hai chế độ.
Sửa kiểm tra bằng tên executable không phân biệt hoa/thường; giữ opt-in,
không thêm flag cho binary Faster-Whisper thường. `_get_key` vốn hash command
nên tự phân biệt audio processing sau sửa, không migrate hoặc xóa cache cũ.

Regression đi qua constructor/resolved path → command/cache: ba kiểu tên
XXL (thường, hoa, có hậu tố version), hai binary thường; kiểm bật/tắt và
không đổi các flag khác. Trước sửa **3 fail/2 pass**, sau sửa Faster-Whisper
và CLI **162 pass**. Ruff app/tests, Pyright 0/0, translation sync và diff
check pass. Không chạy full suite hoặc build EXE.

Source CLI chạy thêm trên 113,5–116,3 s với `voice_extraction=true`, đúng
executable đã cài: ghi nhận command thật có `--ff_mdx_kim2`, GPU provider
hoàn tất exit0 và xuất một cue. Lượt instrumentation đầu của harness lỗi
trước inference; đã sửa harness, giữ log lỗi và chạy lại ở thư mục mới.
Text của clip 2,8 s vẫn sai/lặp so với caption; chỉ pass đường xử lý option,
không pass chất lượng nhận dạng và không dùng text đó cho mẫu clone.

## Bằng chứng thực tế

Audit `.tools/bv1gf-clone-20260916-174613/` tạo snapshot từ `d342d5b`, chép
đúng source/test sửa rồi kiểm bytes; settings/cache/temp/log riêng. Bàn giao
trong `work-dir/BV1GFbk6LEVm-cloned-20260916-174613/`. Không stage dữ liệu,
transcript, model hoặc reference giọng vào Git.

- Đối chiếu 16 frame ngữ cảnh và 38 crop PP-OCRv6 medium mỗi 500 ms. Đây là
  sampled observations, không giả full scan/checkpoint được duyệt. Raw còn
  chữ nền; assistant đối chiếu ảnh để chọn sáu câu, không sửa raw.
- Cùng 19 s, native large-v3/CUDA/VAD bật: âm thanh gốc 5 cue; thêm
  Kim_Vocal_2 đã cài có 6 cue và lấy lại câu bị bỏ. Một vài chữ vẫn khác
  caption; không suy số cue thành text accuracy hoặc human ground truth.
- Reference clone từ vocals gốc: đệ tử 3,69 s nối hai lượt cùng người;
  sư phụ 6,10 s liên tục. Giữ transcript tiếng Trung/SHA/source spans riêng,
  clone sang Việt bằng OmniVoice ghim revision, seed0/32 steps. Đây là lần
  user cho phép clone nhân vật, thay reference tổng hợp của B–E.
- Sáu WAV GPU mới/0 cache hit; vai đệ tử 1/3/4, sư phụ 2/5/6 được gán thủ
  công theo cảnh/ngữ cảnh user. Tốc độ 1×, trễ tối đa 451 ms, không cắt lời.
  Video 19 s H.264/AAC/mov_text, sáu subtitle Việt sạch tag, decode exit0.
- Chờ user đánh giá giống giọng/tự nhiên. Clone cross-language có thể mang
  accent; tách vocals có thể làm méo âm. Nhạc/hiệu ứng gốc chưa được mix lại.
  Mốc thán từ đầu là ước lượng rõ trong report, không giả word timestamp.
- Không gọi gateway/upload audio/tải model/cài package. SHA nguồn/settings/
  checkpoint/reference cũ giữ nguyên. GUI native và EXE chưa kiểm mới.
