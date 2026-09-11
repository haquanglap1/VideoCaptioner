# OCR-4: progress, nhãn candidate và chẩn đoán capture — 2026-09-10

Tiếp tục trên ASR-S3, `codex/asr-s3-native`, HEAD `a528d85`; đã đối chiếu trực
tiếp remote branch bằng `ls-remote`, ahead/behind 0/0. Giữ bốn tài liệu bàn giao
có sẵn. Source thay đổi trong phiên này chưa commit/push và chưa build lại EXE.

## Thay đổi source

- `OcrDialog` đặt progress 100% khi operation kết thúc không hủy/lỗi, khởi tạo
  lại giá trị khi bắt đầu operation kế tiếp. Scan complete chỉ nói về quét;
  document chưa duyệt vẫn có issue và khóa export/handoff. Hủy/lỗi giữ progress
  chưa hoàn tất cùng partial document.
- Nhãn candidate thay xuống dòng bằng ` / ` cho combo một dòng; tooltip giữ
  nguyên chuỗi engine đã đọc. Raw/edited, ID và quyết định review không đổi.
- Không sửa canvas/painter, decoder, model/profile, metadata hoặc worker lifetime.

## Crop đen và Computer Use

Đọc lại ảnh lưu `02-crop-black-after-verified.png` thấy **có đầy đủ chữ**, cũng
như ảnh `03` sau kéo splitter. Tên file không chứng minh pixel trong ảnh bị đen;
giữ nguyên evidence và ghi nhận hiện tượng quan sát trong phiên trước.

Harness native source phát lại `diagnostic-crop.png` đã lưu, không decode,
inference hoặc verify source mới. Computer Use trả metadata đúng cửa sổ harness
nhưng ảnh của một cửa sổ khác. Chọn/kích hoạt lại báo
`no screenshot targets found`; lần kiểm tiếp bị user dừng bằng Escape. Không
tiếp tục Computer Use sau đó. Không lưu nội dung cửa sổ không thuộc task.

Đã thấy bất thường của đường capture, **chưa xác định nguyên nhân crop đen của
EXE cũ** hoặc chứng minh native visual gate đã pass. Không sửa painter theo
suy đoán. Harness có timer tự đóng và ghi event Paint/Resize/Show/Hide/activation;
event vẽ không thay thế bằng chứng pixel thật trên desktop.
Harness tự đóng exit 0, ghi 15 Paint event của canvas, ảnh 640×160 không null,
0 worker/process harness còn lại. Không có request model hoặc vision trong
lượt phát lại này.

## Regression

- Test trước sửa: 7 pass, 2 fail đúng lỗi progress và nhãn; process gặp
  `0xC0000005` ở teardown trước khi in summary. Giữ log, không gọi lỗi teardown
  cũ đã sửa hoặc suy nguyên nhân từ một lần chạy.
- Sau sửa: GUI OCR **9 pass**, exit 0; scoped OCR/GUI/CLI **271 pass**, 24,44 s,
  exit 0. Test bảo vệ scan complete không auto-accept, cancel/error ở 0/94%,
  giữ partial/raw/ID và tooltip chứa nguyên text nhiều dòng.
- Full offline Qt offscreen **1.739 pass /5 skip /51 deselected**, 163,38 s,
  exit 0; 4 skip TTS cần key/service, 1 QtMultimedia cần backend native.
- Ruff app/tests pass, Pyright app 0 errors/0 warnings, translations in sync.
  Không đổi dependency; thông báo có Pyright mới không được dùng để nâng package.

## Video user cho phép kiểm tra trong phiên

User cho chọn một trong hai video trên máy. Đã dùng clip **111,333333 s**, chưa
chạy video bài giảng còn lại. Source 1920×1080, time base 1/16000; quét đoạn
0–111333 ms, ROI pixel 0/960/1920/80. Ảnh preview tại 80 s còn chữ trong dải này.
Không đọc file SRT bên cạnh làm đáp án, không ghi đè video/SRT hoặc recrop 13
ảnh pilot gốc.

Lượt thật đi qua **source OcrDialog/OcrThread với Qt offscreen**, dùng runtime
CPU sẵn trong bộ model của EXE cũ; FFmpeg/FFprobe từ bộ đã cài trên máy. Đây
không phải lượt native GUI hoặc EXE mới, cũng không phải benchmark sản phẩm.

- **3.340 frame /23 track /69 candidates**, 68 fresh /1 cache; **68 request/
  68 response, 68 detector/68 recognizer/0 classifier attempts**, 0 vision.
- Job **27,969 s**, worker inference **14,051 s**; decode/pipeline **26,469 s**
  có overlap, không cộng stage thành total. Full offline đã kết thúc trước scan.
- Document complete, progress worker cuối **94%** → GUI **100%**; vẫn **23 issue
  cần review**, export/handoff khóa. Save/load pending document pass, raw giữ
  nguyên; không auto-accept, dịch, TTS hoặc xuất SRT success.
- Crop cue 14 sau 60 s lấy đúng PTS và khớp SHA; PNG chứa chữ. Đây là crop mới
  ở phần ngoài sample cũ. Ảnh QDialog.grab dưới offscreen không vẽ glyph ở nhiều
  control, không dùng làm bằng chứng native visual gate hoặc bố cục đã pass.
- 13 cue đầu trùng toàn bộ raw của pilot trước; **10/13 exact với tham chiếu
  agent cũ**, chưa native-confirmed. Câu 4 vẫn cùng lỗi thiếu chữ “tháng”; không
  suy đồng thuận là đúng, không nâng chất lượng hoặc chấm toàn bộ 23 cue.
- Harness exit 0, **0 worker còn lại**, SHA video trước/sau khớp. Đối chiếu
  bảo toàn **13/13 crop pilot gốc** pass.

Kết quả tại scratch: `video-pending.ocr.json`, `video-receipt.json`,
`video-prior-comparison.json`, `video-later-crop.png` và log/harness. File review
cần mở cùng video nguồn; giữ trạng thái chưa duyệt. Một lệnh probe scratch ban
đầu lỗi giải mã ANSI, đã đổi sang đọc JSON bytes; không thay decoder app. Harness
paint lần đầu sai tên field identity, đã sửa thành `snapshot_sha256`; không
inference hoặc sửa model để khắc phục lỗi harness.

Evidence mới: `build/ocr-pilot-20260910/ocr4-ui-fixes-11/`. Mọi raw/media/log/
receipt nằm ngoài Git. Không gọi vision API hoặc tăng cap crop 5. Binary cũ
giữ nguyên, nên hai sửa đổi source chưa được xác minh trong EXE mới. Gate gói
khác ổ/tự đủ media tools, review hỗ trợ tiếng Việt và hiệu chuẩn vẫn còn mở.
Đối chiếu cuối: settings master/artifact, fixture tổng hợp và PNG diagnostic
cũ giữ SHA; settings ASR-S3 vẫn không tồn tại như đầu phiên. EXE cũ giữ SHA
`865c07a6104168bd6f7758abc04c70c0d45747a701aa779415bcf1d44664e7ff`.
