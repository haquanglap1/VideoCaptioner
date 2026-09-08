# Kiểm tra điều kiện khảo sát Parakeet CTC Mandarin

**ASR chưa đạt; OCR vẫn dừng.** Phiên tiếp từ HEAD `669c0da` trên nhánh
`codex/asr-s3-native`; HEAD, tracking ref tại máy và remote branch đều khớp,
working tree ban đầu sạch. Không chạy lại các phép đo của snapshot bàn giao.
Contract và metadata được khóa cuối ngày 2026-09-08; bàn giao sang ngày 2026-09-09,
giữ tên thư mục evidence theo ngày bắt đầu.

## Contract trước tải metadata và kiểm tra vocabulary

Cơ sở khảo sát mới: [model card NVIDIA](https://build.nvidia.com/nvidia/parakeet-ctc-0_6b-zh-cn/modelcard)
mô tả một head FastConformer CTC Mandarin/English khác các head đã đo.
[NFA](https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/tools/nemo_forced_aligner.html)
có thể dùng log-probability CTC để align text cung cấp. Đây chỉ là cơ sở khảo sát,
chưa phải bằng chứng acoustic trên S6 hoặc bảo đảm đủ vocabulary nguyên script.

1. Chỉ HTTP GET công khai, không credential, upload text/audio/path hoặc API ASR/dịch.
   Tối đa 20 file, 2 MB/file và 8 MB tổng, chỉ metadata/card/code/vocabulary;
   không weight, container, package, model load, feature extraction hoặc inference.
   Snapshot/hash contract trước lượt tải có receipt; discovery web trước đó chỉ
   đọc trang công khai, chưa tải tokenizer hoặc chấm corpus.
2. Phân biệt model gốc NVIDIA với bản chuyển đổi của FluidInference. Pin revision
   repo chuyển đổi trước lấy file nhỏ; kiểm tra Git blob hoặc LFS hash từ metadata.
   Vocabulary của bản chuyển đổi chưa tự chứng minh ID/tokenizer/checkpoint NVIDIA
   tương đương. Không lấy license hoặc benchmark của bản chuyển đổi gán cho model gốc.
3. Đường NGC hiện hiển thị yêu cầu đăng nhập; không vượt hạn chế bằng endpoint khác,
   tìm key, tải bản sao weight hoặc cài NIM/WSL. Ghi provenance gốc chưa xác minh nếu
   không có nguồn metadata/tokenizer công khai phù hợp. Không suy cần xin tài khoản
   trước khi biết ứng viên đủ contract.
4. Nếu có vocabulary nhỏ công khai từ tác giả bản chuyển đổi, chỉ chấm khả năng
   biểu diễn của đúng snapshot đó trên 91 ID/hash/số ký tự preflight đã khóa.
   Dùng policy lexical cũ, mỗi ký tự lexical có token thường riêng, roundtrip nguyên
   script/case/số. Không unknown, bỏ chữ, đổi case/script, romanization, wildcard,
   ghép head hoặc chia timestamp của subword để ép đủ từng chữ.
5. Dừng trước weight nếu thiếu coverage hoặc provenance. Đủ vocabulary vẫn cần
   contract acoustic riêng: checkpoint/ID mapping, frontend/grid, raw logits/path,
   negative controls và phạm vi phép đo. Không gọi kết quả dictionary là acoustic pass.
6. Evidence riêng `s6-parakeet-eligibility-20260908/` trong job Completion hiện có;
   tạo output độc quyền, giữ helper/report cũ. Snapshot hiện trạng các file bảo vệ
   trước/sau; tài liệu đã đổi khi chốt `669c0da` không bị so với hash tài liệu lúc đo
   `2f8e0a8` rồi coi là corruption. Không rerun scoring tên/số, decoder, parity,
   benchmark, full/static app/build/GUI. Runtime/media/artifact/AppData giữ nguyên.

Contract này không cho phép acoustic dispatch hoặc thay backend/default/strict policy.

## Kết quả và quyết định

**Dừng bản chuyển đổi trước weight; chưa xác minh coverage model NVIDIA gốc.**
Vocabulary [FluidInference tại revision đã pin](https://huggingface.co/FluidInference/parakeet-ctc-0.6b-zh-cn-coreml/blob/ad0da3a453ce93ae53263f9a757ad365ce90bd58/vocab.json)
có 7.000 entry, 5.226 entry một ký tự; metadata ghi blank ID 7.000 bên ngoài list.
Không strip marker SentencePiece hoặc lấy phần chữ trong subword làm token mới.

| Phạm vi dictionary của bản chuyển đổi | Kết quả |
| --- | --- |
| Cùng 91 mẫu, ID/hash/số ký tự khớp baseline | **90/91** có đủ token riêng từng ký tự |
| Target Qwen user 94 ký tự | Đủ dictionary; chưa acoustic hoặc kiểm định CTC ID |
| Mẫu phồn thể 13 ký tự | Thiếu **4** ký tự khác nhau, mỗi ký tự xuất hiện một lần |
| NVIDIA original tokenizer/checkpoint | **Chưa xác minh**, không gán kết quả conversion cho original |

Bốn ký tự thiếu là `幾`, `況`, `滯`, `現`; không đổi sang giản thể hoặc bỏ mẫu để
gọi 90/91 là đủ contract. Đây là lexical representability, không phải CER/timing.
Model NGC gốc được card gọi là `trainable_v3.0`; tên nguồn trong metadata conversion
khớp tên phiên bản, nhưng không có hash checkpoint gốc hoặc đối chiếu tokenizer gốc
trong những file đã đọc. Tên giống nhau không đủ chứng minh equivalence.

[NGC catalog](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/riva/models/parakeet-ctc-riva-0-6b-unified-zh-cn)
yêu cầu đăng nhập để truy cập toàn bộ nội dung/download. Chỉ đọc card công khai,
không thử đường tải thay thế để vượt đăng nhập. NGC và card NVIDIA chỉ tới NVIDIA
Community Model License; nhãn CC-BY-4.0 của repo conversion không được dùng làm
license weight gốc. Không tải weight.

Không cài CoreML/NIM/WSL, không ghép head zh-CN/zh-TW. Chưa đọc/đo vocabulary zh-TW;
không suy model đó pass hoặc fail từ kết quả zh-CN. NFA là công cụ alignment, không
tự bổ sung ký tự thiếu vào CTC head hoặc tạo provenance cho model này.

## Evidence và validation

Evidence tại `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`
`s6-parakeet-eligibility-20260908/`, output tạo độc quyền; helper mới chỉ phục vụ
development, không thêm giao diện/backend vào app.

- `contract-before-fetch.md`, `dispatch.json`, `conversion-pin-before-files.json`:
  contract và revision khóa trước tải vocabulary. Repo pin
  **`ad0da3a453ce93ae53263f9a757ad365ce90bd58`**; vocabulary 67.395 byte, SHA-256
  **`dc724cffa4af0101576c451ea9dbbced7d18070eb8eb13aa49b20afc8c80569c`**.
- `source-receipts.json`: **8 file / 515.668 byte**, HTTP 200; ba file của repo pin
  khớp size và Git blob/LFS metadata. HTML NVIDIA là snapshot URL mutable có hash,
  không gọi nó là pin checkpoint. Metadata-only fetch **exit 0**.
- `contract-before-coverage.json`, `coverage.json`, `validation.json`: **91 mẫu**
  khớp baseline; dictionary coverage **exit 0**. **275 file bảo vệ** và **101 file
  nguồn mẫu** giữ hash/mtime trước/sau; inventory có thể giao nhau, không cộng dồn.
  Đây là validation evidence mới, không chạy lại acceptance/scoring/model cũ.
- **0 weight download / 0 model inference / 0 API ASR-dịch**. Không đổi app,
  scorer/tests, dependency, runtime, media, AppData hoặc artifact. Kế thừa 595
  ASR/CLI và EXE TimingGuard; không lặp full/static app/build/GUI/translation sync.

**ASR chưa đạt; OCR dừng.** Lần kiểm tra này không tạo cơ sở acoustic dispatch.
Không lặp cùng dictionary conversion. Hướng NVIDIA gốc chỉ được xét tiếp khi có
tokenizer/CTC ID và provenance checkpoint phù hợp để kiểm tra riêng; không tự xin
tài khoản hoặc tải weight chỉ từ tên model. Head khác vẫn cần đủ nguyên 91 mẫu và
contract acoustic trước dispatch. Reference dịch tiếp tục thiếu key mới nhập kín;
stress quality, phồn thể, xưng hô, phút sửa tay và genre/dialect còn mở.
