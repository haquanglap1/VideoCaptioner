# Điều kiện head Qwen CTC sau probe attention

**ASR chưa đạt; OCR dừng.** Tiếp tục từ `669c0da`, giữ bốn thay đổi tài liệu
Parakeet/attention đầu phiên; không commit/push. Đây là khảo sát head CTC khác
ForcedAligner đã đo, không lặp probe mask, decoder hoặc benchmark cũ.

## Contract trước tải và kiểm tra

[Card của JazerJu](https://huggingface.co/JazerJu/qwen3-asr-ctc) mô tả head CTC
riêng trên encoder Qwen 1.7B, có compact vocabulary và code alignment. Đây là
đầu mối để kiểm tra khả năng dùng raw CTC; số đo của tác giả chưa là evidence S6.
Giới hạn không tải tokenizer của lượt attention cũ chỉ thuộc contract lượt đó;
lượt này có contract metadata riêng, chưa cho phép tải weight hoặc inference.

1. Evidence mới `s6-qwen-ctc-eligibility-20260909/` trong job Completion hiện có;
   output tạo độc quyền. Snapshot contract/helper/hash trước GET metadata, pin
   commit model trước tải file. Chỉ GET công khai, không credential hoặc upload
   text/audio/local path; tối đa 12 file, 4 MB/file, 12 MB tổng. Tải card/config/
   code/compact vocabulary nhỏ, không weight, package hoặc encoder/tokenizer mới.
2. Kiểm tra mapping compact ID ↔ original tokenizer bằng tokenizer Qwen đã có
   tại máy. Đọc code mới như dữ liệu, không import/thực thi downloader hoặc
   wrapper. Kiểm tra provenance encoder, blank/special IDs và timestamp mapping.
3. Dùng đúng 91 ID/hash/số ký tự preflight cũ, policy lexical cũ. Mỗi ký tự phải
   có một CTC class thường, decode nguyên ID ra đúng một ký tự Unicode; không
   unknown, đổi script/case, ghép byte token, chia timestamp subword hoặc ghép head.
   Giải mã byte encoding của một ID hoàn chỉnh không được biến nhiều ID hay
   một subword nhiều chữ thành timestamp từng chữ. Giữ mapping ambiguous riêng.
4. Dictionary đủ không chứng minh head đã học acoustic cho từng class. Báo riêng
   direct-character coverage và tokenization/đơn vị mà tác giả dùng. Không dùng
   tokenizer normalization hoặc claim zero-unknown để vượt contract từng chữ.
5. Nếu thiếu coverage/provenance hoặc native time mapping chưa xác lập, dừng trước
   weight. Nếu đủ vẫn cần contract acoustic riêng, raw emissions/path, negative
   controls và giới hạn dispatch trước mọi inference. Không lấy constant-bias
   correction, duration rescale, clamp/swap/drop/interpolate làm timing raw.
6. Snapshot inventory bảo vệ hiện tại, gồm evidence attention cũ, app/scorer/test,
   runtime/tokenizer và artifact; so hash/mtime sau kiểm tra. Không lặp acoustic,
   scoring, preflight cũ, full/static/build/GUI. Không sửa app/runtime/default.

Reference dịch vẫn cần key mới nhập kín; stress/phồn thể, nhãn đầy đủ, xưng hô,
phút sửa tay và genre/dialect còn mở. Contract này chưa phê chuẩn acoustic dispatch.

## Kết quả vocabulary và provenance

**Dừng trước weight: 89/91 mẫu đủ một class riêng cho mỗi ký tự.** Head pin
**`9c59b40add48e8ada2b9586f2d7763b8cdcb63e8`**, compact vocabulary SHA-256
**`8a612071ea9a4a0d71de8aa237ba295cb83f0f1a54540ced20619f1130572141`**.
Mapping được đối chiếu với tokenizer Qwen đã cài tại revision
**`7278e1e70fe206f11671096ffdd38061171dd6e5`**, không tải tokenizer khác.

| Phạm vi | Kết quả |
| --- | --- |
| Đúng 91 ID/hash/số ký tự cũ, 1.104 ký tự khác nhau | **89/91** đủ direct-character roundtrip |
| Target Qwen user, 94 ký tự | Đủ dictionary; chưa acoustic |
| Mẫu phồn thể, 13 ký tự | Thiếu **`滯`** |
| Ký tự thiếu khác trong corpus | **`诶`** |
| Mapping ambiguous trên tập mẫu | **0** |

Có 72.468 class: 72.466 ID thường, blank **72.466**, unknown **72.467**.
Mapping compact↔original là song ánh trên 72.466 ID giữ lại. Khi decode từng ID
bằng byte alphabet của tokenizer tại máy: **8.421** ID ra một ký tự Unicode,
**63.187** ra nhiều ký tự, **858** không tạo UTF-8 hoàn chỉnh. Không ghép các byte
token hoặc chia subword để tăng coverage. Alphabet 256 byte khớp hàm decoder
đang cài; mọi mẫu đủ có roundtrip nguyên chữ, không normalization.

Hai ký tự thiếu đều **không có ID đơn nguyên ký tự trong vocab gốc tại máy**,
không chỉ bị loại khi compact. Vì vậy nới riêng ngưỡng pruning không giải quyết
điều kiện này. Không suy rằng Qwen không thể biểu diễn chuỗi bằng nhiều BPE token;
kết quả chỉ nói head này chưa đủ contract một class cho từng chữ.

[Config head tại pin](https://huggingface.co/JazerJu/qwen3-asr-ctc/blob/9c59b40add48e8ada2b9586f2d7763b8cdcb63e8/config.json)
chỉ nêu tên encoder Qwen 1.7B. Những file đã đọc không cung cấp revision/hash
encoder và tokenizer dùng khi huấn luyện. Mapping trên được ghi **có điều kiện
theo tokenizer local**, chưa chứng minh provenance training giống runtime.
Metadata head cung cấp weight **193.385.776 byte**, SHA-256
**`8a70cc712fd9e0a4d9f6d6064031e20ac7b489700ce4ecd5fafe7e8713d71875`**;
không tải. Card công bố Apache-2.0 cho head; không gán license đó cho training data.

## Rà wrapper từ source

[Example tại pin](https://huggingface.co/JazerJu/qwen3-asr-ctc/blob/9c59b40add48e8ada2b9586f2d7763b8cdcb63e8/example.py)
lấy offset của tokenizer cho cả chuỗi rồi xuất `text[a:b]`; một span có thể gồm
nhiều chữ. Nó bỏ target ID ngoài compact mapping và bỏ state không có frame.
Không dùng example để gọi output là timestamp từng chữ hoặc vượt strict raw.

[Wrapper tại pin](https://huggingface.co/JazerJu/qwen3-asr-ctc/blob/9c59b40add48e8ada2b9586f2d7763b8cdcb63e8/modeling_ctc.py)
gọi frontend với `padding=False`, không chỉ định `truncation`/`max_length`.
Đối chiếu AST Transformers **4.57.6** tại máy: mặc định `truncation=True`, giới
hạn `self.n_samples`; config encoder local đặt **480.000 sample / 30 s**.
Đường `_truncate` cắt input dù không padding. **Suy ra từ source/config**, wrapper
này với runtime hiện có sẽ cắt input dài hơn 30 s; chưa chạy audio để đo hành vi.
Đây là wrapper head mới, không phải bằng chứng lỗi frontend của batch S6 cũ.

Ba lệnh `from_pretrained` của wrapper không truyền revision. Hàm thời gian dùng
hằng số **1/13 s**; công thức đếm frame chưa tự chứng minh vị trí biên acoustic.
Không chạy wrapper, sửa frame shift hoặc áp constant-bias correction của card.
Rà source này không lặp decoder/attention synthetic hoặc feature parity cũ.

## Evidence, validation và bàn giao

Evidence mới tại `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`
`s6-qwen-ctc-eligibility-20260909/`:

- `contract-before-fetch.md`, `dispatch.json`, `pin-before-files.json`,
  `source-receipts.json`: **6 file nhỏ / 1.717.789 byte**, GET 200, Git blob/size
  khớp pin; fetch exit **0**, không thực thi code tải về.
- `contract-before-coverage.json`, `coverage.json`, `validation.json`: đúng 91
  mẫu, partition class/mapping/roundtrip nhất quán. **744 file bảo vệ** và **110
  file nguồn** giữ hash/mtime; hai inventory có thể giao nhau, không cộng dồn.
- Coverage đã lưu report và validation pass, sau đó **exit 1 / 7,395 s** khi in
  ký tự Trung ra console CP1252. Giữ helper/report, **không chạy coverage lại**.
  Lỗi đọc JSON qua PowerShell do key `G`/`g` được xử lý bằng `-AsHashtable`, chỉ
  đọc report có sẵn. Các lỗi trình bày/path được giữ trong `process-receipts.json`.
- `source-review.json`, `source-review-validation.json`: kiểm tra AST/config
  **exit 0 / 0,293 s**, chín nguồn giữ hash/mtime; không tính feature/load model.
- **0 weight download / 0 model inference / 0 API ASR-dịch**. Chỉ thêm evidence
  và ba tài liệu trong lượt này: báo cáo này, status và prompt bàn giao. Giữ nội
  dung bốn thay đổi tài liệu cũ. Không đổi app/scorer/tests/dependency/runtime/
  media/AppData/artifact, không commit/push. Kế thừa 595 ASR/CLI + TimingGuard;
  không lặp full/static/build/GUI, scoring hay preflight cũ.

**ASR chưa đạt; OCR dừng.** Head này chưa tạo cơ sở acoustic dispatch. Không lặp
cùng compact vocabulary hoặc khôi phục byte/subword để vượt contract. Muốn xét
lại cần head/tokenizer có class riêng cho chữ còn thiếu và provenance phù hợp;
vẫn phải chốt native time mapping và acoustic contract trước weight/inference.
Reference dịch chưa key mới; phồn thể/stress, nhãn đầy đủ, xưng hô, phút sửa tay
và genre/dialect tiếp tục mở.
