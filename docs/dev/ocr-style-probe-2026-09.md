# Phép kiểm nét sáng và bóng lệch — 2026-09-13

## Kết quả và quyết định

**Chưa tách được lớp phụ đề; không tích hợp policy vào ứng dụng.** Phép thử
mới dùng đặc điểm nét sáng/bóng lệch trên từng frame, không chạy lại policy
3/5 + chiều cao. Cả **10/10 ca** không đạt tiêu chí tracking và pixel.
Giữ luồng OCR xuất thẳng sau scan đầy đủ hợp lệ; không thêm review hoặc
yêu cầu transcript của user. Video 2 vẫn là checkpoint dở.

Worktree ASR-S3, HEAD và tracking cùng **aef0107**. Hai file mới
`scripts/ocr_style_probe.py` và `tests/test_ocr/test_style_probe.py` chỉ phục
vụ phép kiểm offline; không đổi app, profile, cache key, schema hoặc EXE.

## Giả thuyết và phép đo đã cố định

Ảnh ROI/context evidence33 cho thấy chữ phụ đề lớn sáng, có bóng lệch xuống
phải trên nền giao diện chủ yếu sáng với chữ tối. Giả thuyết: kết hợp hình
dạng nét sáng hẹp và bóng lệch có thể loại nền ngay từng frame, giữ cả dấu
rời và thay đổi chỉ một frame mà không cần majority theo thời gian.

`plan.json` ghi trước phép đo, cùng SHA và snapshot script:

- Trên ảnh xám gốc, lấy residual so với phép mở hình thái 11×11
  (MinFilter rồi MaxFilter). Pixel phải có mức sáng ≥248, residual ≥3 và
  sáng hơn pixel lệch (+3,+3) ít nhất 16 mức. Các giá trị là giả thuyết cố
  định, chưa hiệu chuẩn; không sweep hoặc điều chỉnh sau khi thấy kết quả.
- Không loại component theo chiều cao, thêm nét, nối lỗ, vote thời gian
  hoặc lấy chữ từ frame khác. Biên không đủ mẫu bóng được loại tường minh;
  không wrap pixel sang cạnh đối diện. Đây là mask nhị phân, chưa ảnh OCR.
- Tái sử dụng đúng chín fixture/renderer của evidence34, 24 frame/ca;
  thêm control thứ mười: chữ cùng hình thức thuộc **nền**, không có phụ đề.
  Không dùng chữ hoặc nhãn từ video riêng. Không chạy thuật toán cũ.
- Tracking phải đúng khoảng do tác giả đặt, và mỗi frame phải tương đương
  `same_shape` với mask tạo độc lập từ overlay sạch. Không chỉ đếm số đoạn.
- Kiểm pixel riêng: phải giữ mọi pixel sáng mục tiêu nhìn thấy trên
  overlay sạch (`L > 248` của renderer cũ), không chọn pixel ngoài mask sạch.
  Số này không đo toàn glyph/bóng hoặc pixel đã mất do lượng tử hóa, cũng
  không phải độ chính xác OCR. Một mask rỗng không thể pass nhờ so hai mask rỗng.
- Text: kiểm khả năng biểu diễn target tổng hợp bằng bất kỳ tập con dòng
  raw nguyên vẹn, giữ thứ tự/newline/codepoint. Đây là cận khả năng của mọi
  bộ chọn nguyên dòng, **không phải thuật toán chọn dòng hay phép đo OCR**.
- Không OCR khi các gate trên chưa đạt. CLI có audit hook cấm socket và
  subprocess; không mở video gốc, runtime, GUI, dịch/TTS/vision.

## Kết quả tổng hợp

Mọi ca đều có 24 frame khác tín hiệu sạch. Dưới đây số pixel là tổng qua
24 frame, không phải số chữ hoặc pixel độc nhất trên toàn clip.

| Ca | Đoạn yêu cầu | Đoạn mask | Pixel sáng mục tiêu mất | Pixel ngoài mask sạch |
| --- | ---: | ---: | ---: | ---: |
| Dòng cố định | 1 | 24 | 43.054 / 124.776 | 27.721 |
| Đổi một chữ | 2 | 24 | 43.690 / 126.636 | 27.721 |
| Đổi dấu | 2 | 24 | 43.594 / 125.556 | 27.721 |
| Đổi dòng thứ hai | 2 | 24 | 10.454 / 65.388 | 31.197 |
| Fade | 1 | 24 | 30.429 / 81.858 | 29.366 |
| Blank rồi lặp lại | 2 | 24 | 28.705 / 83.184 | 28.751 |
| Đổi một chữ một frame | 3 | 24 | 43.107 / 124.931 | 27.721 |
| Nền dừng | 1 | 1 | 43.080 / 124.776 | 24.528 |
| Blank trên nền cuộn | 0 | 24 | 0 / 0 | 30.952 |
| Chữ nền cùng hình thức | 0 | 1 | 0 / 0 | 83.640 |

Mask lấy cả phần sáng nằm **bên trong lỗ của chữ tối**; các pixel đó cũng
thỏa residual và có pixel tối lệch xuống phải. Regression hình học tái
hiện trực tiếp, không cần detector. Ngược lại, nhiều nét phụ đề không có
bóng đúng offset ở từng pixel nên bị cắt. Ảnh mask tổng hợp và video đã
được nhìn tại máy, phù hợp với số pixel mất/nền lọt.

Trên overlay sạch, thay đổi chữ/dấu/hai dòng/một frame và blank/lặp còn
được giữ; fade vẫn cho **5 đoạn**, dù chưa có chữ nền. Nền dừng cho một đoạn
đúng số lượng nhưng sai hình/pixel ở cả 24 frame, nên vẫn fail.

Dấu tổng hợp 3×3 được mask giữ đủ chín pixel, nhưng tín hiệu riêng dấu này
chưa đạt ngưỡng `present` hiện có của tracker. Regression giữ giới hạn đó;
phép kiểm đổi một frame dùng ký hiệu hai cụm nét đủ ngưỡng. Không sửa
`edge_signature`, `same_shape` hoặc ngưỡng tracking của app.

## Giới hạn của lựa chọn nguyên dòng

Ở bốn fixture raw tách box (chữ nền nhỏ, hai dòng, dấu rời, chữ nền cùng
cỡ), **tồn tại** tập con giữ đúng target tổng hợp. Điều này không chứng
minh một selector có thể tìm được tập con đó từ video.

Ở fixture **box hỗn hợp**, không tập con nào trả đúng target: chọn box thì
còn chữ nền, bỏ box thì mất cả phụ đề. Vì vậy không thể khắc phục ca này
bằng thay ngưỡng chiều cao/score hoặc chọn nguyên dòng thông minh hơn.
Không lấy substring hoặc sửa raw để làm fixture pass.

Control chữ nền cùng hình thức còn cho thấy một bộ phân loại chỉ nhìn
hình thức ở một frame không phân biệt được hai cách gán lớp có cùng pixel.
Kết luận giới hạn ở thông tin đầu vào đó; không suy mọi phương pháp dùng
ngữ cảnh rộng hơn đều bất khả thi.

Nếu sau này có ảnh tách lớp đạt kiểm pixel, OCR trên ảnh đó phải là **bản
đọc dẫn xuất mới** với raw riêng, crop/mask/policy SHA, source/PTS và liên
kết tới candidate gốc. Không tái sử dụng raw cũ như thể engine đã đọc ảnh
lọc. Chưa chọn hoặc triển khai phương án này trong app.

## Đối chiếu evidence đã lưu

Evidence mới độc quyền: `build/ocr-pilot-20260910/ocr-style-probe-35/`.
Đọc mapping video 2 từ evidence32, đối chiếu SHA/size với document; không
mở đường dẫn video gốc. **60/60 PNG và 7/7 candidate SHA/PTS khớp**.
Kích thước ROI, selection, time base/origin giữ đúng checkpoint.

- Đo đủ **PTS420–479**, không cần bỏ frame biên theo thời gian. Có **23
  đoạn tín hiệu mask**, còn tách tại PTS471. Đây không phải số cue của
  RegionTracker hoặc số request OCR. Không so trực tiếp với 17 đoạn trên
  56 frame của policy cũ như một benchmark cùng phạm vi.
- `signal-provenance.local.json` giữ source, checkpoint SHA, PTS/timeline,
  crop SHA và mask SHA; mỗi frame chỉ có chính PTS đó làm nguồn pixel.
- `line-evidence.local.json` giữ ID document/cue/candidate, profile/crop/
  mask SHA và chỉ số toàn bộ 62 dòng raw. Cả bảy candidate ghi
  `unresolved_no_derived_read`, selected indices/text là null. Không đo
  chữ đúng/sai, không đề xuất 16 dòng cũ như kết quả được nghiệm thu.
- Checkpoint nguyên byte, `complete=false`, không đổi raw/decision hoặc
  tạo SRT. Sidecar có schema riêng, không thể mở như OCR document để xuất.

## Validation và bảo toàn

- **36 test pass**, gồm 21 test mới + 15 tracking/consensus/direct-export,
  2 warning, 3,55 s; Python **3.12.13** có sẵn. Sau chỉnh cách đăng ký fixture
  dùng chung, kiểm lại riêng sáu ca evidence để xác nhận collection/fixture.
- Lượt đầu **33 pass/2 fail** do hai test dùng dấu chín pixel như tín hiệu
  đủ ngưỡng tracking; giữ `tests-first.log`. Đổi ký hiệu test sang hai cụm
  nét, thêm test chốt giới hạn dấu đơn; không đổi policy hoặc tiêu chí của
  phép đo 10 ca. Ruff ban đầu F811 ở cách import fixture, đã sửa đăng ký.
- Ruff script + app/tests sạch; Pyright script + app **0 error/0 warning**.
  Không chạy lại full suite, translation sync, build/native smoke/cache/
  resume vì không sửa production/resource. Các gate binary cũ vẫn riêng.
- Harness hoàn thành và trả mã từ chối giả thuyết **2**; PowerShell wrapper
  chạy qua stdin hiển thị exit1 cho native nonzero. Receipt có
  `harness_completed=true`, `hypothesis_accepted=false`; không phải OCR
  success hoặc crash trong phép đo. Không rerun để đổi exit code thành 0.
- **96 file được đối chiếu SHA giữ nguyên**, gồm evidence33/34, bảy file
  đầu vào evidence32, EXE đang giữ và `ffcachePuSHPB`. Không tuyên bố đã hash
  lại toàn models49GB hoặc dữ liệu AppData chưa nằm trong tập đo.
- **0 OCR/API/model load/video decode mới**. Không mở GUI, cài/tải/nâng
  dependency hoặc đổi model/AppData/media. Không commit/push.

Sáu file thay đổi: script/test mới, biên bản này, plan OCR, status và prompt
phiên sau. Dừng policy nét sáng/bóng lệch này; không thử ngưỡng/kernel khác
để lấy pass. Hai phép thử đã bác bỏ hai giả thuyết cụ thể, chưa tạo phương
pháp tách lớp đủ cơ sở tích hợp hoặc hoàn tất OCR video 2.
