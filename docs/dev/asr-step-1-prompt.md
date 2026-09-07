# Prompt bàn giao — thực hiện ASR bước 1

User đã chấp nhận kế hoạch mở rộng ASR của VideoCaptioner và yêu cầu task mới thực hiện bước
đầu. Hãy triển khai S1 đến hết code, kiểm thử phù hợp và bàn giao; không chỉ đề xuất lại kế hoạch.

Mục tiêu toàn dự án: nghe video tiếng Trung (chủ yếu phổ thông), dịch phụ đề sang tiếng Việt,
timestamp đúng, nếu có thể phân biệt người nói và giữ ngôi/xưng hô theo nhân vật/cảnh.
Không cần nhận dạng tiếng Việt. Cần dùng model qua https://api.videocaptioner.cn/console.

Đọc đầy đủ AGENTS.md, README.md, status.md mới nhất và docs/dev/architecture.md. Đọc tiếp:
- docs/dev/asr-provider-plan-2026-09.md: kết quả nghiên cứu đã được chấp nhận.
- docs/dev/asr-implementation-2026-09.md: S1 chi tiết và các gói S2–S6.

Nếu worktree mới thiếu ba tài liệu ASR do chưa commit, dùng bản ở checkout nguồn được chỉ trong
tin nhắn tạo task: đọc rồi copy đúng ba file Markdown sang cùng đường dẫn trong worktree nếu
chưa tồn tại. Không copy AppData, .env, credentials, media hoặc artifact. Không sửa checkout nguồn.
Chạy git status trước sửa, giữ mọi thay đổi không thuộc task. Nếu thấy baseline code khác mô tả,
rà soát thực tế và điều chỉnh thay đổi nhỏ nhất, không reset/cherry-pick hàng loạt.

Thực hiện S1: nền OpenAI-compatible ASR, capability theo provider/model/request profile,
request/parser dùng chung giữa WhisperAPI và check_whisper_connection, preset VideoCaptioner
API/Groq/OpenAI/Custom, config GUI/CLI tương thích và cache/log an toàn. Model nhập tay còn dùng
được với request profile rõ ràng. Ưu tiên code hiện có và dependency đang khóa; không cài global,
không thêm framework hay runtime GPU trong gói này.

Dữ kiện đã đọc trong repo: WhisperAPI và check_whisper_connection đều luôn gửi verbose_json +
word/segment timestamps; parser cần words hoặc segments; cache thiếu endpoint và chứa prompt
dạng thô. ASRData dùng millisecond; EditorCue đã có speaker nhưng chưa cần nối ở S1. GUI/CLI
đã có whisper_api base/key/model/prompt. Tìm call site trước khi sửa và kiểm tra lại tài liệu API.

Gateway có API Base https://api.videocaptioner.cn/v1, POST /audio/transcriptions, Bearer key của
gateway. Catalog đã thấy whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe. Ví dụ GPT dùng
response_format=json. Chưa gọi thật hay đọc key trong task nghiên cứu. Groq base là
https://api.groq.com/openai/v1; Whisper large-v3/turbo hỗ trợ verbose_json/timestamps. Tham khảo
các nguồn chính thức được link trong kế hoạch, dùng OpenAI Docs khi làm phần OpenAI; không
suy model có trên catalog là tài khoản chắc chắn gọi được.

Tiêu chí S1 quan trọng:
1. Whisper/Groq có timing tiếp tục xuất phụ đề như cũ. GPT text-only request/probe nhận dạng
   đúng JSON, không gửi tham số timestamp unsupported.
2. Phân biệt nhận dạng thành công với đủ khả năng xuất subtitle. Text-only được probe nhưng
   subtitle preflight báo cần alignment của S2 trước upload; không fake timing, không KeyError,
   không tuyên bố đã hoàn thành GPT→SRT. Chưa cần mở flow TXT riêng nếu đòi rewrite lớn.
3. Giữ config/flag/exit codes cũ, custom base/model và language user đã lưu. Preset không gửi
   credential của provider trước sang host mới. Mở settings không network hoặc inference tự động.
4. Cache hash có version, endpoint/model/language/prompt/request/timing; không key/prompt/path
   nhạy cảm trong log. MIME đúng bytes thực; upload byte limit, timeout và retry hữu hạn.
5. Worker đúng Qt, submit_with_context và child_environment giữ quy tắc repo. Test cô lập
   settings/env; QThread test phải wait(). Không chỉnh AGENTS/CLAUDE trừ khi có lý do trong scope.

Đọc test matrix S1 trong kế hoạch, thêm test hồi quy có ý nghĩa cho request/response/probe,
cache, preset/config và thiếu timestamp. Chạy ruff toàn videocaptioner/ tests/, pyright,
test_cli, ASR/probe/UI gần thay đổi, sync translations; full offline khi thay shared core đáng kể.
Nếu dùng interpreter của checkout nguồn, xác nhận imports/tests đang chạy code trong worktree;
không vô tình test editable package cũ. Theo fallback ACL/basetemp của AGENTS nếu cần.

Hoàn thành code và offline gates ngay cả khi thiếu API key. Nếu có credential sẵn cho đúng
provider, có thể smoke ngắn theo kế hoạch với audio công khai/tổng hợp; không tự lấy media riêng,
không tạo token/mua credit, không in/copy credential. Giới hạn smoke nhỏ, ghi online pass/fail/
chưa chạy tách biệt; không coi mock hay model listing là E2E. Thiếu key chỉ để lại phần online
chưa nghiệm thu và nêu chính xác điều cần bổ sung. Không yêu cầu user xác nhận lại plan S1.

Chưa triển khai alignment/Qwen/pyannote, Soniox/Scribe native, speaker/xưng hô, đổi mặc định
engine hoặc phát hành EXE trong task này. Nếu đổi runtime resource/dynamic import, cập nhật
spec và làm gate artifact cần thiết theo AGENTS bằng tên riêng, bảo toàn artifact user.

Sau khi có thay đổi bền vững, cập nhật status.md và trạng thái S1 trong tài liệu. Bàn giao danh
sách file, hành vi thay đổi, kết quả gate, hạn chế còn lại, và đề xuất đầu vào cho S2. Không
commit/push/tag/release hoặc viết GitHub. Không tự làm tiếp S2; dừng ở S1 để user review.
