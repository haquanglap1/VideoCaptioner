# Thử tensor OCR rộng gấp đôi — 2026-09-13

ASR-S3, `codex/asr-s3-native`, HEAD/tracking **8b6bb8c**. User yêu cầu tiếp
tục phép thử đã chốt trong [biên bản CTC](ocr-ctc-audit-2026-09.md). Giữ các
diff trước; không đổi model/decoder, mở corpus hoặc gọi dịch vụ ngoài.

## Kết quả: loại thay đổi này

**Tăng chiều rộng tensor bằng lặp pixel ×2 không đạt tiêu chí.** Hai ca
P02/P03 vẫn thiếu một chấm; năm ca vốn exact trở thành sai. Không tích hợp
vào app, không thử tiếp hệ số khác hoặc chọn riêng output tốt để thay raw.

So trên cùng **15 fixture có chữ**: baseline **10/15 exact**, width×2
**5/15 exact**; chữ/số và newline giữ đúng **15/15**. P15 có hai dòng nên
đã chạy 16 tensor. **P16 không áp dụng** vì không có tensor recognizer;
không cộng empty baseline để ghi thành một empty pass mới.

| ID | Nhãn tác giả | Baseline | Width×2 |
| --- | --- | --- | --- |
| P01 | `学生....` | `学生....` | `学生...` |
| P02 | `学生.....` | `学生....` | `学生....` |
| P03 | `学生......` | `学生.....` | `学生.....` |
| P04 | `学生……` | `学生……` | `学生…` |
| P05 | `......学生` | `……学生` | `.学生` |
| P06 | `……学生` | `……学生` | `学生` |
| P07 | `学......生` | `学……生` | `学.....生` |
| P08 | `学……生` | `学……生` | `学生` |
| P09 | `学生!` | `学生！` | `学生！` |
| P10 | `学生！` | Exact | Exact |
| P11 | `学生?` | `学生?` | `学生？` |
| P12 | `学生？` | Exact | Exact |
| P13 | `学生3.14` | Exact | Exact |
| P14 | `学生314` | Exact | Exact |
| P15 | `学生三人。` + newline + `学生五人。` | Exact | Exact |

Các ca mất exact: **P01/P04/P06/P08/P11**. P06/P08 mất toàn bộ dấu dù score
0,99954/0,99944; không coi confidence cao là căn cứ tự duyệt. Đây là kết quả
trên một font/cách render có nhãn tác giả, không phải chất lượng video hoặc
bằng chứng giảm review. Không đổi tham chiếu agent của 23 crop video.

## Phép thử đã thực hiện

- Dùng đúng 16 tensor của evidence29, kiểm SHA khớp trace cũ. Biến đổi duy
  nhất: `np.repeat(tensor, 2, axis=3)`, từ `[1,3,48,320]` thành
  `[1,3,48,640]`. Lặp cả phần padding; giữ giá trị/dtype float32, BGR,
  height và normalization. So cả cột chẵn/lẻ với nguồn, 16/16 khớp tuyệt đối.
- Manifest tensor dẫn xuất và protocol/SHA script được ghi trước inference;
  nhãn/SHA cũ giữ nguyên. Manifest SHA
  `cf7dbfd56fc9a105fb7eace5db9302338c77a9faedf17f59b960789b8ba50514`.
  Worker có hook chặn đọc nhãn và raw baseline; 0 lần chạm hai file đó.
- Dùng `CpuEngine` hiện hành để kiểm package/model/profile và tạo các
  session CPU; chỉ gọi recognizer session với tensor dẫn xuất. Detector/
  classifier được nạp theo constructor cũ nhưng bị chặn gọi inference.
  Giữ decoder `postprocess_op` đã cài, không thay CTC hoặc hậu xử lý chữ.
- Effective config và dictionary **khớp byte baseline**; profile vẫn SHA
  `ef54a9b0de3b6625bc3a6c0589f46a190103e2a37112c935f9630dd7d160abb9`.
  Python3.12.13 `-I -B`, RapidOCR3.9.2/ORT1.29.0, CPU threads4/1.
- Đúng **16 rec /0 det /0 cls**, mỗi tensor một lần, không retry/warmup.
  Đủ **16 cặp begin/end thành công**, 16 raw dòng và 16 full prediction
  arrays `[1,80,18710]`, tổng 95.797.248 byte gồm header NPY.
  Greedy dựng lại từ toàn bộ score khớp raw **16/16 dòng**.
- Raw mới SHA
  `4f99d0de7e010ccee34a12c0cc54c6dfa9b85d908ab244de78a1a6bedfb80ddd`.
  Không ghi đè raw/tensor/PNG/nhãn cũ. Thời gian process 2,359s gồm startup,
  inference và ghi score; không dùng làm benchmark tốc độ sản phẩm.

## Lỗi gate của harness và chẩn đoán

Lượt measure **exit1**, sau khi đã lưu đủ 16 kết quả: assertion cuối yêu
cầu không có sự kiện socket nào, nhưng audit ghi **một `socket.bind` đã bị
chặn**. Không có connect/getaddrinfo/sendto được ghi bởi audit; bộ chặn
network/download của `CpuEngine` ghi 0 attempt. Không gọi API/download.
Không coi measure là exit0 hoặc ghi “0 socket attempt”. Trường `failure:null`
trong metrics chỉ phủ vòng inference; lỗi assertion nằm sau khi ghi metrics.

Chẩn đoán riêng, **không inference hoặc dựng model session**:

1. Chỉ `import rapidocr` không tái hiện bind vì package dùng lazy import;
   giữ receipt của lượt này, không coi nó là giải thích sự kiện gốc.
2. Import class `RapidOCR` tái hiện một bind bị chặn tại `('::1',0)`, stack
   vào `urllib3.util.connection._has_ipv6()`: probe khả năng bind IPv6 local
   khi import dependency. Đã khóa constructor `onnxruntime.InferenceSession`,
   0 lần gọi constructor. Không có request dịch vụ hoặc model inference.

Phép tái hiện phù hợp với nguyên nhân bind khi import; log measure gốc
chỉ có tên event, không lưu địa chỉ/stack, nên không khẳng định đã truy
ngược chính xác event đó. Giữ nguyên gate fail, script/log và mọi raw. Có
tổng hai bind bị chặn trong phiên (measure và chẩn đoán import class).
Không chạy lại tensor nào để làm sạch exit code. Score/đối chiếu receipt
chạy trên output đã lưu, exit0; kết luận chất lượng là **không đạt**.

## Bảo toàn và bàn giao

- Prepare, score, chẩn đoán import và verification/preservation exit0;
  measure exit1 như trên. SHA script/manifest/raw, effective config,
  dictionary, toàn bộ score và ledger đã đối chiếu.
- **240 đường dẫn** giữ SHA/trạng thái; **4.960 file runtime** giữ danh sách,
  size và mtime. Không hash lại toàn payload49GB. Launcher dùng
  `child_environment()`, scratch riêng, logger stub; không import config
  app, mở GUI/cache, chạy FFmpeg hoặc ghi AppData của user.
- Không sửa source/test/resource/profile hoặc auto-accept. Không chạy
  pytest/Ruff/Pyright/translations/build/smoke/cache/resume; không có bản
  vá app cần regression fail-trước/pass-sau ở lượt này. Giữ artifact,
  settings/models/media/evidence cũ, `ffcachePuSHPB` và junction.
- Evidence mới: `build/ocr-pilot-20260910/ocr-width-31/`, ngoài Git. Có
  manifest/tensor đóng băng, script/plan, prediction/raw/ledger/score,
  receipt lỗi và chẩn đoán, preservation và bản sao tài liệu trước phiên.
  Cập nhật biên bản này, status, plan, prompt; chưa commit/push.

Hướng width×2 đã dừng theo tiêu chí đặt trước. Chưa có căn cứ tích hợp
thay đổi nhận dạng hoặc giảm review. Phần thiếu vẫn là nhãn độc lập cho
các cue video đang có và phép đo quyết định/thao tác review đã mô tả trong
biên bản CTC; không tự mở corpus, đổi engine, gọi vision hoặc nối sweep mới.
