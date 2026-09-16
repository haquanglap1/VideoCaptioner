# Preflight hai CTC head sau audit SenseVoice

**ASR chưa đạt; OCR vẫn dừng.** Không chạy lại SenseVoice hoặc scoring tên/số cũ.
Giữ HEAD `2f8e0a8` và mọi thay đổi chưa commit của các lượt audit trước.

## Contract trước kiểm tra vocabulary

Kiểm tra hai ứng viên bằng metadata và code công khai trước khi cân nhắc weight:

- OmniASR CTC v2: kiến trúc waveform → encoder → CTC projection, tokenizer ký tự
  dùng chung cho các kích thước v2. Nguồn code pin
  `81f51e224ce9e74b02cc2a3eaf21b2d91d743455` của `facebookresearch/omnilingual-asr`.
- FireRedASR2-AED: có CTC head phụ và đường căn thời gian; tác giả công bố hỗ trợ
  Mandarin/dialect/singing. Nguồn code pin
  `4e7d9aaf4482a47cec1724807026b9b151926eb5`, model metadata pin
  `2304afed56eacfee6256dee5937ed22ffa0b64ec` của `FireRedTeam/FireRedASR2-AED`.

Đây là căn cứ khảo sát head mới, chưa là bằng chứng acoustic trên dữ liệu của job.
Không dùng benchmark tác giả làm điểm chất lượng S6.

1. Chỉ tải metadata, vocabulary/tokenizer, license và code nhỏ từ nguồn tác giả;
   giới hạn 4 MB/file. Giữ URL, revision khi có, SHA-256, kích thước và receipt.
   URL tokenizer OmniASR trong asset card không có commit: chỉ snapshot/hash nội
   dung đã nhận, không gọi nó là immutable provenance của weight.
2. Dùng đúng 91 mẫu preflight cũ: ba mẫu đã có, 32 reference và 56 transcript Qwen
   hoàn tất. Khớp ID, số ký tự và hash với report cũ trước khi chấm coverage mới.
   Không gửi transcript/audio/path riêng tư ra mạng; caption cũ chỉ là mẫu vocab.
3. Mỗi ký tự lexical phải có token thường riêng và roundtrip giữ nguyên script,
   case, số. Báo missing theo mẫu; không unknown, romanization, đổi giản/phồn thể,
   đổi case, wildcard, hoặc ghép head. Không chạy tokenizer chuẩn hóa để ép pass.
4. Đọc riêng đường CTC raw và timestamp wrapper. Wrapper sửa blank, kéo biên,
   clamp hoặc điền timestamp không được dùng làm nghiệm thu `strict-raw-v1`.
5. Lượt preflight này **không tải/load weight, không inference GPU, không cài
   dependency, không đổi runtime/app/artifact, không API dịch hoặc ASR**. Nếu vocab
   thiếu, dừng ứng viên trước tải. Nếu đủ, vẫn cần contract acoustic riêng với
   frontend, grid, provenance weight và giới hạn phép đo trước mọi dispatch.
6. Output tạo độc quyền dưới job Completion cũ:
   `s6-ctc-second-preflight-20260908/`. Giữ report/helper cũ, so hash/mtime nguồn
   và inventory bảo vệ trước/sau. Không lặp full/test/build/GUI đã pass.

Contract ban đầu được snapshot/hash trước tải và coverage; kết quả bên dưới được
bổ sung sau phép kiểm tra.

## Kết quả và quyết định

**Cả hai ứng viên dừng ở coverage, không tải weight.** 91 ID, hash văn bản và số ký
tự khớp hoàn toàn với preflight SenseVoice cũ. Không đổi mẫu hoặc chính sách lexical.

| Head | Vocabulary | Mẫu có đủ từng ký tự | Target user 94 ký tự | Mẫu phồn thể 13 ký tự |
| --- | --- | --- | --- | --- |
| OmniASR CTC v2 | 10.288 entry; 10.284 ký tự thường đơn | **73/91** | Thiếu một ký tự | Đủ vocab, chưa acoustic |
| FireRedASR2-AED | 8.667 entry; 7.656 ký tự thường đơn | **84/91** | Đủ vocab, chưa acoustic | Thiếu bốn ký tự |

OmniASR có 11 ký tự khác nhau thiếu trong tập kiểm tra. FireRed có chín: bốn chữ
phồn thể và năm chữ Latin thường. Đây là kiểm tra biểu diễn nguyên văn, không phải
CER hay tỷ lệ nhận dạng đúng. Không ghép hai head, viết hoa Latin, chuyển script
hoặc dùng unknown để chữa coverage. Những mẫu đủ chỉ có roundtrip qua dictionary;
chưa xác minh ánh xạ ID runtime, acoustic hoặc timestamp.

[Asset card OmniASR đã pin](https://github.com/facebookresearch/omnilingual-asr/blob/81f51e224ce9e74b02cc2a3eaf21b2d91d743455/src/omnilingual_asr/cards/models/rc_models_v2.yaml)
chỉ rõ các CTC v2 dùng chung tokenizer. Vì vậy đổi riêng kích thước model trong
family này không chữa thiếu vocabulary của snapshot đã kiểm tra. Danh sách
[ngôn ngữ upstream](https://github.com/facebookresearch/omnilingual-asr/blob/81f51e224ce9e74b02cc2a3eaf21b2d91d743455/src/omnilingual_asr/models/wav2vec2_llama/lang_ids.py)
có Mandarin giản/phồn thể; tên ngôn ngữ không bảo đảm mọi chữ của job đều có token.
Tokenizer được lấy từ URL tác giả trong card, snapshot **91.481 byte**,
SHA-256 được giữ trong `source-receipts.json`. URL không có content revision;
chưa có provenance/checkpoint đủ để phê chuẩn tải hoặc load weight.

FireRed có [CTC projection raw](https://github.com/FireRedTeam/FireRedASR2S/blob/4e7d9aaf4482a47cec1724807026b9b151926eb5/fireredasr2s/fireredasr2/models/module/ctc.py),
nhưng đường timestamp công khai không dùng trực tiếp cho contract của job:
CTC helper kéo end qua blank tới start kế tiếp và sửa duration theo trung bình;
[`_get_and_fix_timestamp`](https://github.com/FireRedTeam/FireRedASR2S/blob/4e7d9aaf4482a47cec1724807026b9b151926eb5/fireredasr2s/fireredasr2/asr.py)
còn shift/clamp, kéo start về end trước, sửa biên cuối và chia đều thời gian nếu
không có timestamp. [Tokenizer](https://github.com/FireRedTeam/FireRedASR2S/blob/4e7d9aaf4482a47cec1724807026b9b151926eb5/fireredasr2s/fireredasr2/tokenizer/aed_tokenizer.py)
viết hoa input. Không mang các hành vi này vào app hoặc gọi chúng là acoustic pass.
Model metadata có weight **4.731.558.506 byte** và SHA-256; không tải vì coverage fail.

## Validation và bàn giao

- Evidence mới `s6-ctc-second-preflight-20260908/` dưới job Completion hiện có.
  `contract-before-fetch.md`, `dispatch.json`, `contract-before-coverage.json`
  khóa contract/helper/sources; `coverage.json` giữ từng mẫu và missing.
- Tải **17 file nhỏ / 532.893 byte**, receipts khớp. Model files FireRed được so
  size cùng Git blob hash hoặc LFS SHA-256 từ metadata model pin. Không thực thi
  code tải về. Bộ đọc protobuf khớp toàn bộ 25.055 entry SenseVoice đã lưu;
  đây là kiểm tra consistency của parser, không phải decoder độc lập.
- `validation.json` pass: **195 file bảo vệ** và **100 file nguồn mẫu** giữ
  SHA-256/mtime. Hai inventory có thể giao nhau; không cộng thành số file duy nhất.
  Có EXE TimingGuard trong inventory, nhưng không chạy GUI/build lại.
- **0 weight download, 0 model inference, 0 API ASR/dịch**; có HTTP GET công khai
  cho discovery/metadata/code. Một URL HF v2 đoán theo tên trả 401 ở discovery;
  đã lấy tokenizer theo asset card chính thức, không tìm credential hoặc gọi đó
  là xác nhận quyền tải weight. Không đổi app/scorer/tests/dependency/runtime.
- Kế thừa gate ASR/CLI 595 và EXE TimingGuard; không lặp test/static app/full,
  scoring nhãn cũ, build/GUI hoặc benchmark. Chỉ kiểm tra preflight/evidence mới.

Hai checkpoint/family trên không là phương án alignment đủ contract hiện tại.
Không lặp download/preflight cùng vocabulary để tăng số lần kiểm tra. Cần head
khác có nguyên chữ của cả tập và bằng chứng acoustic trước dispatch; chưa có
ứng viên mới được duyệt tải. Reference dịch vẫn cần key job mới nhập kín, giữ
scope/endpoint/model cũ; không tìm key cũ. Stress, chất lượng phồn thể, quan hệ
xưng hô, phút sửa tay và genre/dialect vẫn mở. **ASR chưa đạt; OCR tiếp tục dừng.**
