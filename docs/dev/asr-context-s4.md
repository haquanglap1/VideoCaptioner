# S4 — ngữ cảnh xưng hô Trung → Việt

S4 bổ sung dữ liệu có bằng chứng và lựa chọn chủ động của user cho LLM translator. Đây là
contract/code đã kiểm thử offline, **chưa phải nghiệm thu chất lượng xưng hô bằng người đọc**.
Diarization chỉ cho nhãn speaker; không suy danh tính, tuổi, giới, quan hệ hoặc người nghe.

## Dùng GUI

1. Mở phụ đề JSON/SRT trong tab phụ đề hoặc Video Editor. Chọn **More → Ngữ cảnh xưng hô**.
   SRT thiếu metadata vẫn mở được với người nói/người nghe chưa rõ. Mở hộp thoại không gọi LLM.
2. Thêm **Nhân vật**, sửa tên hiển thị. ID nội bộ tự tạo, có thể copy để tham chiếu và không đổi
   khi rename. Tab **Câu nguồn** hiển thị ID câu, nhãn ASR scoped và văn bản làm bằng chứng.
3. **Liên kết người nói** chọn đúng nhãn ASR và nhân vật. Dropdown hiển thị tên cùng ID. Không
   ghép cùng số speaker của hai request. Nếu không có ASR metadata, chỉ định nhân vật theo cue
   trong **Người nói và người nghe**, hoặc giữ unknown.
4. **Người nói và người nghe**: nhập các ID câu trong phạm vi (phân cách bằng dấu phẩy), chọn
   nhân vật nói, nhập ID người nghe. Nhiều ID là nhóm; ô rỗng là unknown. Người được nhắc đến là
   trường riêng. Chọn loại lời `Hội thoại`, `Lời kể`, `Trích dẫn` hoặc `Chưa rõ`.
5. **Quy tắc xưng hô** theo hướng: A→B `anh/em`, B→A `em/anh`; A→C có thể `tôi/bạn`.
   Phạm vi có thể là các ID câu, một cảnh được khai báo bằng tập ID câu, hoặc toàn tài liệu.
   Phạm vi câu và cảnh cùng có giá trị nghĩa là giao của hai phạm vi.
6. Nguồn `Văn bản` cần ID câu bằng chứng. Đề xuất/chưa rõ không được áp dụng. Xác nhận/khóa
   mới có hiệu lực; nguồn user ưu tiên nguồn text, khóa ưu tiên xác nhận, rồi phạm vi cue/cảnh.
   Hai mục cùng ưu tiên bị báo xung đột, không chọn ngẫu nhiên. **Áp dụng** là một lệnh atomic;
   sửa hoặc mở khóa ở đây là thao tác user rõ ràng. Có undo/redo (editor dùng stack hiện có;
   tab phụ đề có More → Hoàn tác/Làm lại ngữ cảnh).
7. Bấm **Kiểm tra ngữ cảnh** để xem chỗ cần review. Chọn dịch LLM; Google/Bing/DeepLX giữ dữ
   liệu nhưng không áp quy tắc. Tab phụ đề dùng Ctrl+T cho selection; editor dùng
   **More → Dịch các câu đã chọn** (range timeline, hoặc cue trong inspector).

Editor chỉ sửa `display_text` khi dịch selection; không tự đổi TTS text, voice hoặc timing.
Một kết quả selection là một composite command có undo/redo. Nếu nội dung/ngữ cảnh thay đổi
trong lúc dịch, kết quả cũ bị bỏ; user chạy lại sau khi review. Từ **S4.1**, guard chỉ so sánh
project identity và dữ liệu phụ đề/ngữ cảnh cần bảo vệ; playhead/zoom/track display không làm
mất bản dịch. More → Hủy dịch dừng worker hợp tác. Xem [S4.1](asr-s41.md).

Lưu **JSON** ở tab phụ đề hoặc **Save project** ở editor để giữ mọi liên kết. Editor vẫn dùng
`editor-project-v1`, normal save ghi JSON + SRT; ASS chỉ qua Save as ASS. SRT không giữ ID/speaker/
ngữ cảnh, và không tự chèn tên vào chữ. JSON cũ thiếu trường S4 mở với defaults. Reader editor
cũ có thể bỏ qua trường mới nhưng khi save lại bằng bản cũ sẽ không bảo toàn dữ liệu S4.

## Dùng CLI

`subtitle` đọc được JSON ASR và `*.vceditor.json`, giữ nguyên cue ID của project:

```powershell
uv run --frozen videocaptioner subtitle review.vceditor.json --no-split --no-optimize `
  --translator llm --target-language vi -o translated.json
uv run --frozen videocaptioner subtitle subtitles.json --no-split --no-optimize `
  --translator llm --target-language vi --conversation-context review.vceditor.json -o translated.json
```

`--conversation-context JSON` dùng chung với `transcribe`, `process`, `subtitle`, ánh xạ vào
`translate.conversation_context`. File có thể là context standalone (policy
`conversation-context-v1`), JSON ASR hoặc project JSON. Không thêm key/API/engine mặc định mới.
Khi nhận dạng lại, scope request và cue ID native mới khác: dữ liệu cũ chưa khớp phải review,
không tự chuyển mapping sang speaker cùng số. Context gắn ở transcribe chỉ được lưu, không
khởi chạy dịch ngoài lệnh đã yêu cầu. Dùng `-o ...json` để không mất dữ liệu khi mở lại.

Đã có context thì **tắt split**; re-segmentation hiện dừng để review association. Đây là giới
hạn chủ động: S4 không tự phân phối lại bằng chứng/người nghe qua các cue mới. Merge/delete làm
mất cue tham chiếu sẽ hiện missing khi review, không suy ID thay thế. Optimize giữ ID, còn text
nguồn thay đổi khiến translation cache đổi fingerprint.

## Contract, snapshot và cache

Core `translate/conversation.py` chứa các dataclass bất biến: Character, Scene, SpeakerMapping,
CueAssignment, AddressRule, Scope, Evidence và ConversationSnapshot. JSON là biên serialization;
không dùng dict làm dữ liệu liên tầng. Machine chỉ được thêm proposal có bằng chứng, không
ghi đè hoặc xóa lựa chọn user/confirmed/locked. Chưa có bộ tự suy đề xuất quan hệ; S4 cho nhập,
review và xác nhận chúng bằng cùng schema mà không tự gọi thêm LLM.

Cue ID được tạo một lần và giữ qua clone/optimize/translate/JSON/editor. Native ID còn phụ thuộc
scope request; unknown vẫn unknown. Speaker override editor có trường riêng, giữ provider/scope/
speaker ASR gốc, tránh thêm prefix lần nữa sau nhiều vòng JSON. Audio events và overlapping speech
được giữ, không biến thành lời thoại hoặc tạo timestamp mới.

Một snapshot được tạo trước chunking cho toàn tài liệu. Selection 1–9 cue cũng dùng snapshot đó;
request nhận mapping đã resolve, nhân vật xác nhận, cửa sổ ±4 cue quanh selection và mọi cue được
dẫn làm bằng chứng, không chỉ tập câu cần dịch. Không gửi path/media/credential. Nguồn hội thoại và
label được khai báo là dữ liệu, không phải chỉ dẫn điều khiển. Response chỉ có text theo khóa output;
không được cập nhật speaker, người nghe, ID hay timing. Context có bật dùng policy malformed strict;
response sai schema sau tối đa ba lượt sửa bị từ chối, không ghi vào cue.

Quy tắc chỉ cấp cho direct dialogue; narration/quotation/unknown không nhận quy tắc hai ngôi.
Prompt yêu cầu phân biệt 他/她/它, lược chủ ngữ, danh xưng thân tộc/chức vị và người được nhắc đến;
thiếu bằng chứng giữ cách diễn đạt trung tính/ambiguity. Đây là hướng dẫn cho model, không phải
bộ kiểm chứng ngữ nghĩa hoặc cam kết dịch đúng mọi câu.

Translation cache hash nguồn/cue ID/metadata, policy, snapshot mapping/listener/rule/scope/evidence/
override, target/model/custom prompt và endpoint. Thứ tự tương đương không đổi key; brief LLM ngẫu
nhiên không tham gia key. Đổi context chỉ tạo key mới, không xóa toàn cache. Kết quả cũ vẫn thuộc
snapshot cũ nhưng không được ghi đè state mới. Dữ liệu cache local theo chính sách hiện có của app.

Đường LLM có context S4 giữ credential của job, dùng socket async sở hữu bởi worker, deadline
120 s/request mặc định (**S4.1 cho cấu hình 1–600 s**, ví dụ 300 s với `gpt-5.6-terra`), không tự
retry HTTP/network hoặc follow redirect. Validation response tối đa ba
lượt là các request có chủ đích. Hủy kiểm tra khoảng 100 ms, cancel/join task và đóng client trước
ra khỏi request. HTTP lỗi chỉ báo status, không echo body/key. Hủy local không bảo đảm hủy phí/xử
lý phía provider. S4.1 áp dụng socket/deadline này cho mọi request LLM translation/brief, kể cả
context trống. Google/Bing/DeepLX giữ transport riêng.

## Giới hạn nghiệm thu

Unit/contract tests dùng câu tổng hợp; output mock không phải ground truth tiếng Việt. Chưa có
benchmark người nghe, tên nhân vật, đại từ hoặc video dài bằng người đọc. Các lượt online sau
bàn giao: Soniox nhận dạng được nhưng full parser dừng token 0 ms; Whisper gateway xuất được
SRT cấp câu; GPT transcription trả text, chưa chạy alignment. Có bản Việt đủ 30 cue từ output
Whisper + `gpt-5.6-terra`, dùng timeout riêng 300 s trong harness vì request mất 131.56 s;
timeout app ở snapshot S4 lúc đó vẫn 120 s. S4.1 đã đưa lựa chọn 300 s vào app; chưa chạy lại API
thật với code mới. Bản xem thử còn cần review ASR/ngôi/tên, không chứng minh chất lượng toàn bộ.

Scribe online, GPT transcription→alignment→SRT và workflow media/API từ process EXE vẫn **chưa
nghiệm thu**. Phồn thể Qwen strict vẫn **chưa đạt acceptance**. Chi tiết từng lượt đo trong status
và implementation; phép đo Qwen local/S3 startup không thay thế các khoản này.

Không thêm S5/S6, Qwen ASR/pyannote, auto voice, corpus benchmark hay đổi engine mặc định.
Gate chạy và artifact S4 được ghi riêng trong `status.md` và implementation.
Code S4 đã chốt tại `8558082` theo yêu cầu user. [Prompt S4.1](asr-step-4-followup-prompt.md)
ưu tiên củng cố các luồng trên trước khi mở rộng S5.
