# Kiểm giả thuyết greedy CTC từ trace đã lưu — 2026-09-13

ASR-S3, `codex/asr-s3-native`, HEAD/tracking **8b6bb8c**. Tiếp tục từ
[16 fixture dấu câu](ocr-punctuation-fixtures-2026-09.md); giữ mọi diff cũ.
Lượt này chỉ tính trên JSON top-5 có sẵn, không chạy model hoặc đổi ảnh.

## Kết quả và quyết định

**Không có căn cứ thay greedy bằng decoder tối đa hóa tổng điểm CTC để sửa
năm fixture đang sai.** Với cùng score đã lưu, cận dưới của tổng điểm raw
đều lớn hơn cận trên của nhãn tác giả. Kết luận có điều kiện theo mô hình
score chuẩn hóa và dung sai nêu dưới đây; không phải xác suất chữ đúng.

| Fixture | Khác biệt nhãn → raw | Cận dưới raw | Cận trên nhãn |
| --- | --- | ---: | ---: |
| P02 | 5 → 4 dấu U+002E | 0,427266 | 0,183836 |
| P03 | 6 → 5 dấu U+002E | 0,176394 | 0,073437 |
| P05 | U+002E ×6 → U+2026 ×2, đầu dòng | 0,441302 | 0,003308 |
| P07 | U+002E ×6 → U+2026 ×2, giữa chữ | 0,231172 | 0,021162 |
| P09 | U+0021 → U+FF01 | 0,595921 | 0,404089 |

Một decoder tìm chuỗi có tổng điểm lớn nhất có thể trả chuỗi khác raw,
nhưng không thể chọn nhãn trong bảng nếu đã có raw với điểm cao hơn.
Không chạy beam search, thêm language model, thưởng độ dài hoặc ép số chấm.
Kết quả này không loại mọi cách cải thiện nhận dạng; nó loại lý do cụ thể
để thay decoder thuần CTC trên score hiện có. Không chứng minh lỗi weights,
huấn luyện, ONNX export hoặc tương đương với Paddle native.

**Không sửa source/test/profile hoặc auto-accept.** Chất lượng baseline vẫn
11/16 fixture exact, không có phép đo chất lượng mới hoặc giảm review.
Hai ca Unicode của video vẫn chưa phân xử; 19/23 exact trên video vẫn chỉ
so với tham chiếu agent. Không chuẩn hóa hay sửa raw/reference để đổi số đó.

## Giả thuyết, phương pháp và giới hạn

Giả thuyết được ghi vào `plan.json` trước phép tính: việc lấy ký tự cao nhất
ở từng timestep có thể bỏ qua chuỗi đúng có tổng điểm CTC cao hơn khi cộng
các đường đi. Chỉ so hai chuỗi đã có là raw và nhãn, cho toàn bộ dòng của
P01–P16; không sinh/tìm candidate mới hoặc thử nhiều decoder.

- Đọc implementation đã cài `rapidocr/ch_ppocr_rec/utils.py`: argmax từng
  timestep, loại token trùng liên tiếp rồi blank. P02 có các run chấm ở
  t=8,10,13,15–16; run cuối đúng quy tắc collapse thành một dấu. P03 có
  năm run chấm riêng t=8,10,12,14,17, nên tắt collapse cũng không giải thích
  được cả hai ca. Không gán mỗi timestep cho một pixel/glyph vật lý.
- Tensor P02/P03 vẫn có năm/sáu dấu nhìn thấy; đọc lại ảnh đã lưu, không
  đếm lại cửa sổ pixel từng lỗi hoặc coi số timestep toàn dòng là nguyên
  nhân đã chứng minh. Mỗi trace có 40 timestep/18.710 lớp.
- Dùng CTC forward sum: chuỗi trạng thái xen blank; cho phép giữ trạng
  thái, tiến một bước và bỏ qua blank chỉ khi hai nhãn kế tiếp khác nhau.
  Nhãn lặp phải đi qua blank. Không chuẩn hóa lại top-5.
- Chỉ có top-5 cho bộ fixture, không có toàn bộ vector score. Với mỗi
  score p, cho khoảng `[max(0,p−10^-6), min(1,p+10^-6)]`. Tính forward
  trên cận dưới/cận trên của các score giữ lại. Cận trên còn cộng tổng
  lượng score có thể bị bỏ ở từng timestep (union bound, chặn tại 1).
  Do đó không coi top-5 là đủ toàn bộ phân bố hoặc đặt score thiếu bằng 0
  rồi khẳng định đó là tổng điểm chính xác.
- Các khoảng là điều kiện cho mọi vector xác suất không âm, tổng 1 ở
  mỗi timestep, nhất quán với score đã lưu trong dung sai trên. Không đo
  lại vector đầy đủ, không chứng nhận sai số export/softmax chỉ từ top-5.
  Cận vẫn tách biệt ở cả năm ca ngay với phần thiếu và dung sai này.
- Kiểm dictionary/index/char, thứ tự timestep/line, SHA tensor, nhãn/raw
  đã đóng băng. Greedy dựng lại khớp recognizer và raw bridge **16/16 dòng**;
  P15 giữ hai dòng; P16 không có dòng/trace recognizer. Đây là đối chiếu
  receipt cũ, không phải 16 lần inference hoặc regression của bản vá app.

## Gate và bảo toàn

- Harness chỉ dùng Python 3.12 hiện có với `-I -B` và thư viện chuẩn;
  không import app/config/cache, NumPy, OCR, ONNX, Qt hoặc gọi subprocess.
- Kiểm công thức với phép liệt kê độc lập **1.092 đường đi**, độ dài 1–6,
  ba token gồm blank: **110 phép so tổng điểm và 110 phép kiểm cận pass**.
  Có chuỗi lặp, blank xen giữa, chuỗi rỗng, nhãn dài bất khả thi và score
  bị bỏ. Đây là kiểm harness phân tích, không tính vào pytest của app.
- Prepare, phân tích và hậu kiểm đều exit0. **226 đường dẫn** giữ SHA/
  trạng thái tồn tại; **4.960 file runtime** giữ danh sách/size/mtime.
  Không phải hash mới toàn bộ runtime hoặc payload 49 GB.
- **0 inference / 0 API mới**, không decode, mở GUI, tải/cài hoặc đổi model.
  Không chạy lại full suite, lint/typecheck/translations, build, smoke,
  cache/resume hoặc sweep. Không đổi app nên không có gate fail-trước/
  pass-sau cho ứng dụng; các gate cũ không được tính là validation mới.
- Giữ artifact, models/AppData/work-dir, raw/reference/evidence cũ,
  `ffcachePuSHPB` và junction. Chưa commit/push.

Evidence ngoài Git: `build/ocr-pilot-20260910/ocr-ctc-audit-30/`, gồm script,
plan đóng băng, result, analysis log, preservation trước/sau và bản sao
tài liệu đầu phiên. Script/result có hash liên kết; không chứa nhãn mới
cho video. File tài liệu cập nhật: biên bản này, status, plan và prompt.

## Phép đo tiếp theo, chưa thực thi

Hướng kiểm có cơ sở tiếp theo là **độ tách biệt theo chiều ngang của đầu
vào recognizer**, vì ảnh còn dấu nhưng score không ưu tiên đủ dấu. Chưa
kết luận hình học là nguyên nhân. Một phép thử có thể kiểm soát: nhân đôi
chiều rộng của từng tensor đã lưu bằng lặp pixel ngang, giữ height48,
dtype/kênh/normalization/padding, weights/dictionary/decoder và CPU như cũ.
Đây là đúng một biến đổi cố định, không sweep hệ số hoặc chọn crop theo đáp án.

Nếu thực hiện phép đo này, đóng băng manifest/SHA tensor dẫn xuất và protocol
trước inference; worker không đọc nhãn. Chạy một lần trên **16 tensor dòng
đã lưu của 15 fixture có chữ**, trần 16 rec/0 det/0 cls/0 API, không retry/
warmup; lưu toàn bộ score để tránh thiếu vector ở lần phân tích sau.
Baseline dùng nguyên evidence29. P16 không có tensor recognizer nên ghi
**không áp dụng** cho thử chỉ-recognizer, không tính như một empty pass mới.

Tiêu chí quyết định trước: P02/P03 phải exact về số dấu; không mất exact ở
bất kỳ ca đúng cũ, chữ/số/newline không đổi; báo riêng P05/P07/P09, giữ mọi
output sai và không thay raw baseline. Không đạt thì dừng giả thuyết này,
không tự nối các hệ số khác. Dù đạt, đây vẫn chỉ là ứng viên preprocessing
trên một font, cần chứng minh và regression ở điểm nối thực trước khi sửa
app; không đủ tự duyệt cue hoặc tuyên bố chất lượng video tăng.

Giảm review vẫn cần **nhãn độc lập và phép đo thao tác**, chưa có ở lượt này:
phân xử gói bốn ca hiện có bằng nguồn text xác thực/người đọc độc lập, để
codepoint chưa xác định nếu chỉ có raster; muốn đánh giá trên 23 cue phải
xác nhận cả 23, không mặc định 19 ca khớp agent là chuẩn. Trên cùng các ca
đã phân xử, so đúng/sai quyết định, số sửa chữ và thời gian/thao tác giữa
luồng hiện tại và thay đổi đề xuất, với thứ tự đối cân bằng để hạn chế học
thuộc. Người đánh giá nhãn độc lập với người dùng thao tác; người dùng không
biết tiếng Trung không phải nguồn ground truth. Chưa có thay đổi UI cụ thể,
lượt người dùng đo thời gian, liên hệ bên ngoài hoặc corpus mới.
