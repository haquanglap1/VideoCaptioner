# Phép kiểm tách lớp phụ đề offline — 2026-09-13

## Kết quả

Đã đo một giả thuyết cố định trên fixture tổng hợp và PNG video 2 đã lưu:
**cạnh bền qua 3/5 frame + chọn dòng cao ít nhất 60% dòng cao nhất chưa đạt**.
Không đưa policy này vào scan/resume/export. OCR vẫn xuất thẳng theo yêu cầu
user; không thêm review hoặc yêu cầu bản chữ gốc.

Script `scripts/ocr_layer_probe.py` là phép thử riêng, không được app import
hoặc đóng gói. Bộ test `tests/test_ocr/test_layer_probe.py` giữ cả các phản ví
dụ gây mất chữ/dấu. Đạt test harness không có nghĩa thuật toán được nghiệm thu.

## Phương pháp đã cố định trước khi đo

- Dùng `edge_signature` hiện có, không đổi ngưỡng/tile/ROI. Với cửa sổ năm
  frame thật, lấy bit cạnh xuất hiện trong ít nhất ba frame rồi giao với
  frame giữa. Không thêm nét không có trong frame giữa, không padding.
- So tín hiệu bằng `same_shape`; giữ frame tham chiếu đầu mỗi đoạn. Đây là
  phép đo tín hiệu riêng, **không phải số cue/candidate của RegionTracker**:
  không có first/best/latest, holding limit hoặc tính cửa sổ bất định.
- Hai frame đầu/cuối không đủ ngữ cảnh được ghi rõ chưa đo, không kéo dài
  timing hoặc giả quan sát. Khoảng đo dùng chỉ số frame/PTS thật, end exclusive.
- Chọn các dòng raw có chiều cao bbox ≥ 0,6 × chiều cao lớn nhất, giữ thứ
  tự, codepoint và newline giữa các dòng đã chọn. Không OCR lại, ghép chữ
  trong box, sửa raw hoặc dùng confidence để phân loại nguồn chữ.
- Tiêu chí tracking: đúng các khoảng phụ đề do tác giả fixture đặt và
  tín hiệu tương đương overlay sạch ở mọi frame được đo. Tiêu chí chọn
  dòng: đủ các dòng/dấu mục tiêu, không giữ chữ nền, đúng nguyên văn.
- Một policy, không sweep tham số. CLI cấm socket và subprocess bằng audit
  hook; không mở video gốc, model, GUI, dịch, TTS hoặc vision.

Fixture dùng font NotoSansSC có sẵn, ROI **1128×94** như evidence33, chữ lớn
trắng có bóng trên nền sáng và chữ/icon nhỏ cuộn chồng vào. Đây là nội dung
tổng hợp do tác giả đặt; không chép transcript hoặc nhãn từ video riêng.
Hai dòng dùng font nhỏ hơn để nằm trọn ROI. Có control nền dừng và không phụ đề.

## Kết quả fixture

9 ca × 24 frame, mỗi ca đo 20 frame giữa. `plan.json` được ghi trước khi
chạy. Cột đoạn sau lọc dùng cùng phép so tile với cột trước lọc.

| Ca | Đoạn yêu cầu | Trước lọc | Sau lọc | Frame khác overlay sạch | Đạt |
| --- | ---: | ---: | ---: | ---: | --- |
| Dòng cố định | 1 | 20 | 6 | 3 | Không |
| Đổi một chữ | 2 | 20 | 7 | 3 | Không |
| Đổi dấu câu | 2 | 20 | 7 | 3 | Không |
| Đổi dòng thứ hai | 2 | 20 | 7 | 7 | Không |
| Fade | 1 | 20 | 13 | 11 | Không |
| Blank rồi lặp lại | 2 | 20 | 10 | 6 | Không |
| Đổi một chữ trong một frame | 3 | 20 | 8 | 4 | Không |
| Nền dừng cuộn | 1 | 1 | 1 | 20 | Không |
| Blank trên nền cuộn | 0 | 20 | 0 | 0 | Có |

Giảm số đoạn không đủ: ca nền dừng cho đúng một đoạn nhưng vẫn giữ cạnh
chữ nền ở cả 20 frame. Ca fade ngay trên overlay sạch cũng cho bảy đoạn;
không quy toàn bộ lỗi fade cho nền cuộn hoặc riêng bộ lọc mới. Test mask
lý tưởng không nền còn chứng minh một thay đổi một frame bị bỏ, trong khi
thay đổi ba frame và blank dài được giữ. Không nới tiêu chí để gọi là pass.

Năm fixture dòng dùng **response/bbox do tác giả đặt**, không gọi detector:
hai ca chữ nền nhỏ/hai dòng đạt; ba ca dấu câu thành box nhỏ riêng, chữ nền
cùng cỡ và raw chứa cả phụ đề/nền trong một box đều không đạt. Bộ chọn có
thể giữ đúng box mà text vẫn lẫn nền; chọn dòng không làm sạch chữ trong box.

## Đối chiếu video 2 từ PNG cũ

Đọc mapping nguồn tại evidence32 và document đã lưu, dùng đúng PNG evidence33.
Đã nhìn context PTS420 và crop PTS420/435/471, đối chiếu hình học với fixture
tổng hợp. Chỉ xác nhận lớp chữ/bbox, không chấm chữ nhận dạng.

- **60/60 PNG RGB SHA** khớp `frame-observations.json`; **7/7 candidate**
  khớp crop SHA/PTS của checkpoint. Kiểm thêm kích thước ROI và timing theo
  time base/origin/selection của document. Không decode video lại.
- Đo 56 frame giữa, **PTS422–477**, chưa đo **420/421/478/479**. Phép so
  tín hiệu cho **17 đoạn trước và 17 đoạn sau lọc**; vẫn giữ đổi lớn PTS471
  nhưng còn nhiều điểm tách khác. Không so số 17 này như một cải thiện so
  với **18 nhóm/28 crop** của tracker toàn 60 frame ở evidence33.
- Đề xuất giữ **16/62 dòng raw**, loại 46 dòng theo chiều cao. Đây chỉ là
  hình học: chưa chứng minh 16 dòng đúng/đủ hoặc hết chữ nền. Không tạo SRT.
- File `line-proposals.local.json` giữ source identity, SHA checkpoint,
  document/cue/candidate ID, PTS, crop/profile SHA, chỉ số dòng chọn/loại và
  text lấy nguyên từ raw. `signal-provenance.local.json` giữ PTS/SHA của năm
  crop dùng cho từng frame. Các file này là sidecar thử nghiệm, không phải
  `ocr-document-v1` hoặc checkpoint để resume.
- Checkpoint nguồn giữ nguyên byte; không đổi raw, decisions, complete,
  schema, profile hoặc cache key. Video 2 vẫn là scan dở, chưa subtitle success.

Evidence mới độc quyền: `build/ocr-pilot-20260910/ocr-layer-probe-34/`.
Có plan, receipt (`harness_completed=true`, cả hai hypothesis=false), snapshot
script, ảnh tổng hợp, provenance local và log test. Không đưa dữ liệu riêng vào Git.

## Gate và phạm vi bàn giao

- **34 test pass** (19 test harness mới + tracking/consensus/direct-export),
  2 warning, 1,99 s; host Python **3.12.13**, môi trường có sẵn.
- Lượt test đầu 14 pass/1 fail vì assertion dự đoán sai rằng blank cuộn nhanh
  vẫn còn cạnh; đo thực tế cho thấy bị loại hết. Sửa assertion thành control
  tích cực theo dữ liệu; thuật toán/tham số và tiêu chí nghiệm thu không đổi.
- Ruff `scripts/ocr_layer_probe.py videocaptioner/ tests/` sạch; Pyright
  script + app với `--venvpath ../VideoCaptioner`: **0 error/0 warning**.
  Chỉ có thông báo phiên bản Pyright mới; không cài/nâng dependency.
- **0 OCR/API/model load/video decode mới**. Không chạy lại full suite,
  build/native smoke hoặc cache/resume. Không đổi EXE/models/AppData,
  media/evidence cũ hay `ffcachePuSHPB`; không commit/push.
- Sáu file của lượt này: script, test, biên bản này, plan OCR, status và
  prompt phiên sau. Giữ các thay đổi tài liệu chẩn đoán trước đó.

## Hướng tiếp tục được giới hạn bởi phép đo

Không đưa majority 3/5 + lọc chiều cao vào pipeline hoặc rerun với trần
request cao hơn để lấy exit0. Một giả thuyết khác cần xử lý nền dừng/chồng
nét, dấu rời, box hỗn hợp, chuyển chữ ngắn và biên fade trên các fixture này
trước; đồng thời đo riêng phần tracking và phần text chọn. Chưa chọn thuật
toán thay thế. Việc này không chặn người dùng xuất thẳng scan đầy đủ hợp lệ.
