# Chẩn đoán video 2 từ evidence — 2026-09-13

Worktree ASR-S3, nhánh `codex/asr-s3-native`, HEAD/tracking **81ba84d**.
Tiếp tục theo yêu cầu user: OCR xuất thẳng, không review bắt buộc hoặc đòi
bản chữ gốc; giữ EXE/models/dữ liệu, không API/download. Không commit/push.

## Kết luận

Đoạn **14–16 s** có chữ/icon giao diện cuộn **chồng vào cùng vùng phụ đề**.
Tracker hiện so cạnh của toàn ROI nên thay đổi nền cũng tách cue. Detector
đọc cả chữ nhỏ của giao diện; bước consensus chọn một bản đọc nguyên vẹn,
chưa có bước phân biệt lớp phụ đề với chữ nền trong bản đọc đó.

Đây là hạn chế cụ thể của tracking/lựa chọn vùng chữ trên đoạn này, không
phải bằng chứng lỗi PTS, ánh xạ ROI hoặc decoder OCR. Trần **8 request** chỉ
khiến lượt smoke dừng sớm; tăng trần không loại chữ nền hoặc sửa cue vụn.
Không kết luận model nhận sai mọi dòng chỉ từ số recognizer call.

Không sửa source, profile, raw hoặc quyết định cũ trong lượt chẩn đoán.
Không thay ROI bằng một vùng hẹp hơn: các ảnh đã kiểm cho thấy chữ/icon
nền nằm ngay trên nét phụ đề, nên cắt hình chữ nhật đơn giản không tách
được hai lớp mà vẫn giữ trọn dòng. Chưa đo một phương án tách lớp thay thế.

## Evidence và phạm vi đo

Nguồn lấy đúng mapping video 2 tại
`build/ocr-pilot-20260910/ocr-direct-export-32/video-inputs.json`.
Đọc checkpoint, receipt, stdout/stderr và ảnh 15 s đã lưu trước khi decode.
Không quét corpus khác; path, ảnh và raw riêng chỉ nằm ngoài Git.

Evidence mới: `build/ocr-pilot-20260910/ocr-video2-diagnosis-33/`.
`plan.json` được ghi trước decode. Harness `diagnose.py` dùng Python 3.12
hiện có, `-B`, FFmpeg/ffprobe có sẵn, `child_environment()` và process ẩn.
Không khởi động runtime OCR, GUI hoặc EXE để inference.

- Decode một lượt ROI gốc **60 frame**, PTS **420–479**, time base **1/30**,
  timeline origin **0**, SAR **1**, rotation **0**; thêm một ảnh toàn khung
  tại PTS420 để nhìn nền trong ngữ cảnh. Decoder có preroll/lookahead;
  60 là số frame trong selection, không phải tổng frame FFmpeg nội bộ.
- ROI `0.28,0.90,0.44,0.065` ánh xạ đúng thành **x716/y1296/w1128/h94**
  trên khung 2560×1440. Hash toàn video khớp evidence và checkpoint.
- **7/7 crop SHA/PTS** và **5/5 nhóm đầu** khớp checkpoint: exact timing,
  first/last PTS, thứ tự candidate đều giữ nguyên.
- `verify_analysis.py` đối chiếu bytecode **8 module** source/PYZ trong
  EXE đang giữ: tracking, geometry, decoder, pipeline, consensus, models,
  runtime, service. Tất cả khớp sau khi bỏ riêng `co_filename`.
- Hai harness exit0. **0 OCR request / 0 model load / 0 API**; hook host
  không thấy network attempt. Decoder/process/readers đã đóng hết.
- **63 đường dẫn** giữ SHA hoặc trạng thái không tồn tại, gồm video 2,
  evidence32, EXE, marker models, các settings/cache được theo dõi và
  `ffcachePuSHPB`. Không suy đây là một lần hash mới toàn models49GB.

## Tracking tái hiện điều gì

Replay chỉ dùng pixel và thuật toán tracking hiện có, không đưa chữ nhận
dạng vào tracker. Kết quả **18 nhóm / 28 crop ứng viên**, cả 28 crop có SHA
khác nhau. Mỗi nhóm giữ tối đa 3 candidate như contract.

| PTS bắt đầu nhóm | Số tile vượt ngưỡng so với frame tham chiếu | Đối chiếu ảnh |
| --- | ---: | --- |
| 422, 423, 424, 429, 431–436, 439 | 46–127 | Chữ/icon nền cuộn hoặc chuyển giao diện, dòng phụ đề lớn vẫn hiện |
| 425, 437, 440, 446 | 1–4 | Khác biệt cạnh nhỏ vẫn đủ tách khi dòng phụ đề nhìn không đổi |
| 471 | 172 | Quan sát được dòng phụ đề lớn đổi tại 15,700 s |
| 472 | 2 | Tách thêm ngay frame sau khi dòng mới đã xuất hiện |

Đã nhìn toàn bộ 28 ảnh candidate tại máy, không chép lại transcript hoặc
dùng quan sát đó làm nhãn đo độ chính xác OCR. Các điểm tách ngoài PTS471
đều có tile gây tách từ **x282 trở đi trong ROI**; tiền tố bên trái không
có tile vượt ngưỡng ở những điểm này. Nền chồng vào phần giữa/phải dòng.
Các khác biệt 1–4 tile chưa đủ để phân xử riêng codec, rendering hay dịch
chuyển nhỏ; không gọi tất cả là lỗi codec.

`same_shape()` chỉ cần một tile đổi ít nhất 6 bit và trên 30% số bit
occupied để đóng nhóm. `_finish()` chọn first/best/latest; do nền làm
đổi hình/crop, nhóm mới lại có các candidate mới. Bước này xảy ra **trước**
recognizer, nên không phải OCR trả text khác rồi làm tracker vỡ nhóm.

Không nới ngưỡng toàn cục hoặc ghép theo text OCR: cách đó có thể nuốt
thay đổi một chữ, dấu hoặc dòng thứ hai. Nền còn lẫn trong candidate dù
chỉ giải quyết được số nhóm.

## Giải thích 8 request / 73 rec / 5 cue

Checkpoint lưu **7 candidate**, mỗi candidate có **5–12 vùng chữ**, tổng
**62 vùng**. Bbox và ảnh tại cùng PTS xác nhận có dòng giao diện nhỏ ngoài
dòng phụ đề lớn. Một số box giao diện và box phụ đề còn chồng nhau.
`EngineRead.text` ghép tất cả dòng bằng newline; `choose_read()` chọn cả
bản đọc, không lọc các dòng nền. Vì vậy raw và output tương lai đều có thể
lẫn chữ nền ngay cả khi scan đủ và export không cần review.

Thứ tự candidate đầu được tracker tái hiện:
**420, 421, 422, 423, 424, 425, 428, 429, 430**.
Lượt cũ đã hoàn thành request8 tại PTS429; request9 cho PTS430 bị guard
chặn trước gửi. Nhóm thứ6 cần cả hai candidate, nên chưa được yield vào
document. Checkpoint chỉ giữ 5 nhóm đến **14,300 s**, còn `frames=12`
tính cả frame PTS431 đã khiến nhóm thứ6 đóng.

Vì thế **8 response không có nghĩa 8 candidate đã được persist**. Raw
response thứ8 không có trong checkpoint này; không dựng lại raw đó từ
metric. Chênh lệch 73 rec so với 62 dòng đã lưu không chứng minh 11 dòng
bị app xóa khỏi một cue hoàn chỉnh. Profile dùng `Rec.rec_batch_num=1`,
worker đếm từng `session.run`, còn checkpoint được tạo theo nhóm hoàn tất.

**28** là số candidate/crop khác SHA dự kiến cho một scan đầy đủ cùng
cấu hình; **21** candidate còn sau 7 candidate đã persist. Đây là dự báo
từ tracking, **không phải số request OCR đã chạy** và không là cap sản
phẩm. Lượt cũ tắt disk cache; raw chưa persist không tự được phục hồi từ
cache. Không resume chỉ để đổi exit5 thành exit0 và tạo 18 cue lẫn nền.

## Bước phát triển tiếp theo

Phạm vi đã có cơ sở là tách **lớp phụ đề mục tiêu** khỏi chữ nền tại hai
chỗ: tín hiệu tracking và các dòng được chọn để xuất. Trước khi đổi app,
đặt phép kiểm offline có phụ đề tổng hợp biết trước trên nền chữ cuộn:
phụ đề giữ nguyên, đổi một chữ/dấu, hai dòng, fade, khoảng trống và lặp
lại. Dùng các PNG đã lưu ở evidence33 để đối chiếu hình học, không decode
lại hoặc OCR video chỉ để lấy số mới. Không sweep ROI/preprocessing.

Chưa chọn hoặc nghiệm thu thuật toán tách lớp. Nếu thay policy tracking/
selection, phải giữ raw toàn bộ, snapshot/IDs/source/PTS và provenance
phần chữ được chọn; không âm thầm áp policy mới vào checkpoint cũ hoặc
merge raw theo chữ đoán. Export vẫn trực tiếp sau scan đầy đủ hợp lệ;
scan dở, source/profile mismatch và timing lỗi vẫn dừng.

Không có regression code cần chạy trong lượt chỉ chẩn đoán/tài liệu này.
Không chạy lại full suite/build/native smoke/cache/resume đã pass.
Video 2 vẫn **chưa có scan OCR hoàn tất hoặc subtitle success**; chưa
chạy hết hai video, chưa nghiệm thu dịch/TTS/vision hay chất lượng sản phẩm.
