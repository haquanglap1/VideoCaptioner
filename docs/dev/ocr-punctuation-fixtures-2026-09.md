# Kiểm 16 fixture dấu câu có nhãn tác giả — 2026-09-13

Tiếp tục ASR-S3, `codex/asr-s3-native`, HEAD/tracking **8b6bb8c**. Thực hiện
đúng P01–P16 trong [kế hoạch audit](ocr-quality-audit-2026-09.md), theo yêu cầu
tiếp tục chất lượng sau cache/resume. Không mở rộng tập video, đổi engine hoặc
sweep cấu hình. Giữ mọi diff tài liệu có trước; chưa commit/push.

## Kết quả và quyết định

**11/16 fixture exact từng codepoint**, **16/16 khớp chữ-số** (gồm fixture
rỗng). Năm ca sai đều ở dấu câu: hai ca mất một chấm, ba ca thay biểu diễn.
Nhãn được tác giả định nghĩa trước render/inference, không lấy từ output.
Đây là bộ kiểm lỗi cụ thể ở một font/cách render; không cộng với 23 crop video
để tính chất lượng sản phẩm, không thay tham chiếu video chưa xác nhận.

| ID | Nhãn tác giả | Raw medium | Kết quả |
| --- | --- | --- | --- |
| P01 | `学生....` | `学生....` | Exact |
| P02 | `学生.....` | `学生....` | Mất 1 chấm, 5→4 |
| P03 | `学生......` | `学生.....` | Mất 1 chấm, 6→5 |
| P04 | `学生……` | `学生……` | Exact |
| P05 | `......学生` | `……学生` | U+002E ×6 → U+2026 ×2 |
| P06 | `……学生` | `……学生` | Exact |
| P07 | `学......生` | `学……生` | U+002E ×6 → U+2026 ×2 |
| P08 | `学……生` | `学……生` | Exact |
| P09 | `学生!` | `学生！` | U+0021 → U+FF01 |
| P10 | `学生！` | `学生！` | Exact |
| P11 | `学生?` | `学生?` | Exact |
| P12 | `学生？` | `学生？` | Exact |
| P13 | `学生3.14` | `学生3.14` | Exact, giữ dấu thập phân |
| P14 | `学生314` | `学生314` | Exact, không tự thêm dấu |
| P15 | `学生三人。` + newline + `学生五人。` | Giữ đúng hai dòng | Exact |
| P16 | Chuỗi rỗng | Không có dòng nhận dạng | Exact |

Ở bộ tổng hợp này, biết chính xác Unicode được đưa vào renderer; không còn
phải đoán nhãn từ raster. Tuy vậy, nhãn được biết không có nghĩa mọi cách mã
hóa đều nhận biết duy nhất qua ảnh. Hai ca Unicode của video cũ vẫn chưa
phân xử; không dùng fixture để sửa tham chiếu cũ.

**Chưa sửa source/test/resource/profile của ứng dụng.** P02/P03 là lỗi tái
hiện có nhãn xác định, nhưng chưa chứng minh lỗi implementation trong app.
Giữ nguyên raw, ID, candidate, source, review và khóa export khi pending.
Không bù chuỗi chấm thành sáu, chuẩn hóa NFKC hoặc nới auto-accept. Chưa đo
được cải thiện nhận dạng hoặc giảm thời gian/thao tác review.

## Khoanh vùng bằng cùng lượt nhận dạng

- Dùng nguyên `CpuEngine` và `recognize()` từ bridge ứng dụng hiện hành;
  profile được kiểm SHA khớp source. Không dựng một decoder khác thay app.
- Bbox P02/P03 bao toàn bộ ink của input. Ảnh dòng lần lượt giữ năm/sáu
  chấm; tensor đã lưu vẫn nhìn thấy chúng. Greedy collapse top-1 từ trace
  trả bốn/năm chấm, khớp output recognizer trước bridge và raw sau bridge.
- Cả **16 dòng** (15 ảnh có chữ, P15 có hai dòng) đều có top-1 collapse,
  text trực tiếp từ recognizer và text bridge khớp nguyên văn. Không có
  bằng chứng tầng app đã xóa dấu trong bộ này. Chưa đối chiếu Paddle native
  hoặc chứng minh lỗi weights/thuật toán huấn luyện/implementation CTC.
- Đếm pixel chẩn đoán dùng cùng ngưỡng `min(R,G,B)>185`, 8 hướng, không thử
  nhiều ngưỡng. Vùng x≥70 trên line P02/P03 cho 5/6 thành phần. Tensor P02
  cho 5; tensor P03 cho 7 vì cửa sổ cắt vào hai pixel cuối nét chữ `生` tại
  x=70, y=37..38, ngoài sáu cụm dấu ở x=76..120, y=33..36. Giữ cả receipt
  này và lỗi assertion của harness; không ghi thành bốn phép đếm đều pass
  hoặc dùng phép đếm cửa sổ làm bộ đọc dấu tổng quát.
- Score hai ca thiếu chấm **0,86043/0,76239**; P05 sai codepoint dù score
  **0,95370**. Không chọn threshold từ các số này. Đồng thuận giữa nhiều
  frame cũng chưa được đo trong phép kiểm một ảnh/fixture này.

Vấn đề được chốt để kiểm tiếp là **giữ số lượng dấu chấm lặp và biểu diễn
dấu trong nhận dạng**, không phải lỗi cache/resume hoặc lọc text sau OCR.
Fixture hiện đã cho phản ví dụ cụ thể đối với quy tắc bù dấu chung: P01/P02
có nguồn bốn/năm chấm thật, P13 là dấu thập phân.

## Nhãn, render và ledger

- Đóng băng `labels.json` UTF-8 gồm codepoint trước khi tạo PNG; đóng băng
  manifest PNG/RGB SHA, font, renderer, profile/bridge và cap trước inference.
  SHA nhãn: `92188e9b6647d2b79643ccd0aadd0c1a068e4fe283e47d4387bd771c4a7d7c8c`.
- NotoSansSC-Regular hiện có, SHA
  `dc71173babc38dfd019912965f2b4b3421fb347ebd854e7b96f64ad63673924a`;
  Pillow12.3.0/FreeType2.14.3/BASIC trong runtime đã cài, font32, RGB800×120,
  trắng/đen, x30/y10, spacing8. Không blur/upscale hoặc đổi hình học.
- Dựng lại sáu fixture cũ **trong bộ nhớ**, cả sáu PNG khớp SHA đã lưu.
  Không ghi đè ảnh hoặc nhận dạng lại sáu fixture cũ. Mười sáu PNG mới có
  RGB SHA khác nhau; ink không chạm biên, P16 không có ink. Đã xem contact
  sheet và ảnh dòng/tensor hai ca thiếu chấm.
- Dùng runtime medium CPU hiện có trong gói OCR6. Python3.12.13 `-I -B`,
  RapidOCR3.9.2/ORT1.29.0; profile
  `ef54a9b0de3b6625bc3a6c0589f46a190103e2a37112c935f9630dd7d160abb9`,
  height48, batch1, CPU threads4/1. Worker không đọc file nhãn.
- **16 detector/16 recognizer/0 classifier** đã bắt đầu và kết thúc, mỗi
  ảnh một detector, dưới trần16/32/0. Có64 sự kiện begin/end ghép đủ32 cặp.
  Không retry inference, warmup, biến thể crop hoặc chọn lại response.
- 0 API vision/dịch/TTS, 0 lần gọi mạng qua các hook socket/download của
  worker; không tải/cài dependency/model. Đây không phải packet capture
  toàn hệ điều hành. Không mở GUI/FFmpeg hoặc import config/cache app.
- Lượt hoàn tất exit0, process3,531s; thời gian gồm trace và I/O, không dùng
  làm benchmark tốc độ. Raw SHA:
  `6d9409d32fa483d4870a41d0ff23e6fb97a1273051b5c5f91620c997aa4f6598`.

Harness đầu exit1 khi JSON không serialize được `WindowsPath` trong effective
config, **trước khi gọi detector/recognizer**. Giữ script/log/config dở trong
`measured/`; sửa riêng serializer vào `measure-v2.py` và lưu lượt hoàn tất
ở `measured-v2/`. Model đã được load ở lượt lỗi, nên không gọi đây là lần
startup duy nhất hay cold benchmark. Không có ảnh nào bị OCR hai lần.

## Gate, bảo toàn và bước còn thiếu

- Render/score/đối chiếu trace/ledger/SHA pass; P15 giữ newline và chữ đổi,
  P16 không hallucination. Đây là nghiệm thu đầu ra bộ fixture, không phải
  regression fail trước/pass sau của một bản vá ứng dụng.
- **87 đường dẫn theo dõi** giữ SHA/trạng thái tồn tại; gồm evidence cũ,
  font, EXE/profile/bridge/weights và settings/cache được chọn. **4.960 file**
  runtime giữ nguyên danh sách, size và mtime; đây không phải lượt hash
  toàn bộ runtime hay models49GB. Không thay media, raw/reference cũ,
  AppData, artifact hoặc junction; giữ `ffcachePuSHPB`.
- Không sửa app nên không chạy lại pytest/Ruff/Pyright/translations,
  build/native smoke, cache/resume hoặc sweep đã qua. Gate fail của harness
  ghi riêng ở trên; không biến chúng thành lỗi ứng dụng.
- Nếu thử thay đổi nhận dạng tiếp, phải chốt trước **một giả thuyết cụ thể**
  từ line/tensor/top-5 đã lưu và một thay đổi có thể kiểm soát, rồi so với
  baseline này. Không thử nhiều crop/cấu hình để chọn câu đúng. Bất kỳ bản
  vá app nào vẫn cần regression fail trước/pass sau và bảo toàn nguồn/raw/
  ID/review; ảnh nền đen này không đủ hiệu chuẩn auto-accept.
- Đo giảm review còn thiếu quyết định đúng với nhãn độc lập và thời gian/
  thao tác người dùng trên cùng ca. Không suy 11/16 exact thành 11 ca tự
  duyệt hoặc chỉ cần review5/16. Chưa mở corpus mới hay phân xử video cũ.

Evidence mới ngoài Git: `build/ocr-pilot-20260910/ocr-punctuation-29/`.
Có nhãn/PNG/manifest đóng băng, contact sheet, plan, harness và process log,
raw/bbox/ảnh dòng/tensor/top-5, score, chẩn đoán pixel, preservation và bản
sao tài liệu trước phiên. File Git cập nhật: biên bản này (mới), `status.md`,
plan OCR và prompt phiên sau; biên bản audit cũ giữ nguyên.
