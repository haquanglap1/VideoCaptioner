# Audit decoder timestamp Qwen sau S6

**ASR chưa đạt; OCR vẫn dừng.** Tiếp tục tại HEAD `2f8e0a8`, giữ tám file thay đổi
cũ. Không lặp benchmark, preflight CTC, scoring tên/số hoặc acoustic inference.

## Contract trước kiểm tra

Giả thuyết cần loại trừ: zero-duration hoặc overlap của Qwen xuất hiện do adapter
decode/đổi đơn vị thời gian, hoặc upstream đã có thay đổi thực thi liên quan mà
runtime pin `qwen-asr==0.0.6` chưa có. Báo cáo của người dùng ở
[Qwen issue #197](https://github.com/QwenLM/Qwen3-ASR/issues/197) chỉ là đầu mối,
không phải xác nhận nguyên nhân hoặc số đo của S6.

- Snapshot/hash contract trước tải code hoặc chạy audit. Evidence riêng tại
  `VC-ASR-Completion-20260908-140534/s6-qwen-decoder-audit-20260908/` trong root
  `build/asr-session-evidence/`; file mới tạo độc quyền, giữ report/helper cũ.
- Chỉ HTTP GET công khai metadata/code/license; tối đa 2 MB/file, 20 file.
  Pin commit GitHub trước lấy source; metadata model chỉ đọc, không tải weight.
  Không gửi text/audio/local path, không đọc credential hoặc gọi API ASR/dịch.
- So nguồn decoder/config/model/processor/audio utils đã cài với commit upstream
  bằng bytes và AST; ghi rõ từng khác biệt. Không import downloader/model hay
  thực thi nguyên module tải về; chỉ chạy đoạn decode đã đọc với input synthetic.
- Kiểm tra CPU đủ mọi timestamp class theo config checkpoint đang cài, gồm mask
  vị trí timestamp, parse raw, seconds rounding và integer-ms serialization của
  hai bridge. Dùng zero/reversed/overlap/out-of-bounds synthetic để kiểm tra việc
  giữ nguyên lỗi; không sửa raw hoặc bật `fix_timestamp`.
- Phân loại raw alignment đã lưu của S6 và user theo lưới native cùng các lỗi
  hình học; giữ denominator item/chunk/clip và offset riêng. Không chạy lại
  validator như gate nghiệm thu, không chấm lại CER/tên/số hoặc dùng TextGrid để
  sinh timestamp từng chữ. Không lưu transcript riêng tư vào tài liệu Git.
- So hash/mtime nguồn, raw, runtime và inventory bảo vệ của lượt preflight cũ.
  Không sửa app/scorer/tests/dependency/runtime/artifact, không build/GUI/full
  test lại. Audit CPU pass không đồng nghĩa acoustic hoặc ASR pass.

Chỉ cân nhắc dispatch mới nếu tìm được thay đổi hoặc lỗi thực thi có liên quan;
không dùng issue bên ngoài, phép đếm lỗi hoặc parity để tự phê chuẩn chạy lại model.

## Kết quả source và decoder

Không tìm thấy bản sửa upstream chưa áp dụng trong năm file đã đối chiếu.
Commit snapshot **`7c6daf77a2421100f5fb066495372c00129d39ff`**: decoder, audio utils,
model, processor và config đều **khớp từng byte và AST** với package đang cài.
Lịch sử file decoder trả về một commit ban đầu; metadata model hiện tại vẫn là
**`c7cbfc2048c462b0d63a45797104fc9db3ad62b7`**, trùng pin runtime. Đây là phạm vi
snapshot đã kiểm tra, không phải tuyên bố mọi fork/package đều không có thay đổi.

[Decoder tại commit đã pin](https://github.com/QwenLM/Qwen3-ASR/blob/7c6daf77a2421100f5fb066495372c00129d39ff/qwen_asr/inference/qwen3_forced_aligner.py)
chọn `argmax` theo từng vị trí timestamp, nhân class ID với 80 ms, rồi chuyển sang
seconds. Bridge đổi lại integer ms; callback `raw_timestamp` thay thế LIS repair.
Config checkpoint có **5.000 class**. Hai endpoint được chọn riêng; đường raw
không tự bảo đảm end lớn hơn start hoặc không overlap. Vì vậy không bật lại
`fix_timestamp`, đặt min duration hay đổi rounding để làm kết quả hợp lệ.

CPU chạy **12 case pass**: đủ 5.000 class và một vector lỗi cho từng tổ hợp của
FP32/BF16 synthetic logits với bridge S2, bridge S5 source và bridge S5 đã cài.
Tổng 30.096 boundary qua đường decode; sai số lớn nhất **0 ms**. Kiểm tra đi qua
`align()` đã đọc, mask timestamp, parse, structured items và đúng biểu thức đổi ms
của bridge; các vị trí không phải timestamp được bỏ đúng. Phép nhân int64 class ID
với grid dùng **float32**, không làm tròn timestamp bằng BF16.

Đây là **logits synthetic và processor/model stub trên CPU**, không chạy frontend,
encoder hoặc load checkpoint. BF16 ở đây chỉ kiểm tra truyền/decode timestamp,
không chứng minh logits acoustic BF16 bằng FP32 hoặc sai số acoustic bằng 0.
Zero-duration, reversed, overlap và mốc vượt giới hạn 240 s của fixture đều được
giữ nguyên. Nhãn âm không thuộc miền class ID, nên không tạo class âm giả.

## Phân loại raw đã lưu

Đọc đúng 64 report alignment S6 theo manifest, 282 file raw chunk và một review
user; giữ cả manifest trong **348 file nguồn**. Mỗi nhánh có raw ở **28/32 clip,
141 chunk**; bốn clip thiếu recognition vẫn ngoài alignment, không inference lại.
Chấm hình học ở thời gian local của từng chunk; không cộng offset rồi kiểm tra
lưới sai. Chỉ số overlap so start với end của item ngay trước; các cờ có thể giao
nhau, không cộng các cột thành tổng item lỗi.

| Target recognition | Raw item | Zero-duration | Reversed | Overlap với end trước | Ngoài audio | Item có ít nhất một cờ |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen 0.6B | 14.665 | 533 | 77 | 588 | 1 | 1.186 |
| Qwen 1.7B | 14.691 | 519 | 89 | 628 | 0 | 1.217 |
| User Qwen 1.7B, 60 s | 94 | 2 | 2 | 3 | 0 | 6 |

Hai nhánh corpus đều có **139/141 chunk** chứa ít nhất một cờ hình học trên.
Tất cả endpoint trong các raw này là bội của **80 ms**; không phải lỗi do cộng
offset hoặc làm tròn milliseconds. Đây là phân loại lỗi, **không phải chấm lại
gate strict/RMS hoặc timing accuracy**. Hai chunk còn lại không tự thành acoustic
pass; các kết quả guard cũ vẫn giữ nguyên.

Kết hợp code và roundtrip loại được giả thuyết bridge làm gộp hai timestamp class
khác nhau. Tuy nhiên raw cũ chỉ có timestamp sau decode, không có logits gốc của
Qwen: không đo được margin/tie hoặc ảnh hưởng precision của acoustic model, không
chỉ định một nguyên nhân acoustic duy nhất từ histogram. Lưới 80 ms cũng không
tự chứng minh nó là nguyên nhân duy nhất của mọi zero-duration.

[Issue #197](https://github.com/QwenLM/Qwen3-ASR/issues/197) đang mở, snapshot API
có 0 comment; [issue #55](https://github.com/QwenLM/Qwen3-ASR/issues/55) đóng với
`not_planned`. Đây là báo cáo người dùng tại repo upstream, không phải xác nhận
của maintainer hay benchmark độc lập cho S6; không nhập tỷ lệ của issue vào số đo.

## Validation và quyết định tiếp tục

- Tải **12 file công khai / 155.551 byte**, receipts/hash khớp. Không tải weight,
  cài gói, sửa runtime hoặc gửi dữ liệu riêng ra mạng.
- Lượt CPU đầu **exit 1 / 24,859 s** do selector AST lấy cả dictionary diarization;
  lỗi trước decoder case, 0 inference. Giữ helper/report/log gốc. Bản sửa chỉ chọn
  dictionary có `text`; helper mới và output **`run02/`** riêng, kế thừa source
  comparison đã xong. Không xóa report để chạy lại.
- Lượt đúng **exit 0 / 9,656 s**, stderr rỗng; `run02/validation.json` pass.
  **231 file bảo vệ** và **348 file nguồn raw** giữ hash/mtime. Hai inventory có
  thể giao nhau; không cộng chúng thành số file duy nhất.
- **0 model inference / 0 API ASR-dịch / 0 weight download.** Không đổi app,
  scorer/tests, dependency, runtime hoặc artifact. Kế thừa 595 ASR/CLI và EXE
  TimingGuard; không lặp full/static app/build/GUI hoặc scoring tên/số.

**ASR vẫn chưa đạt; OCR dừng.** Không có lỗi đổi đơn vị hoặc bản cập nhật upstream
liên quan để sửa và dispatch lại Qwen. Không thử precision/window/prompt tùy tiện
chỉ từ các số lỗi này. Phương án acoustic mới vẫn cần cơ sở, contract và coverage
phù hợp trước tải/inference. Reference dịch còn thiếu key mới nhập kín; phồn thể,
stress quality, quan hệ xưng hô, phút sửa tay và genre/dialect chưa được khép lại.

Evidence: `source-comparison.json`, `source-receipts.json`, `setup-correction.json`,
`run02/decoder-roundtrip.json`, `run02/raw-contract-before-analysis.json`,
`run02/raw-geometry.json`, `run02/validation.json`, `run02/cpu-process.json`.
