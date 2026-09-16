# Giữ người nói khi chuẩn bị lồng tiếng — 2026-09-16

Khi phụ đề JSON đã có metadata người nói, `ASRDataSeg.speaker` trả về định danh
có scope hoặc lựa chọn override của user. `DubbingEngine._create_dubbing_cues`
trước đây bỏ trường này, khiến planner có thể gộp hai lượt thoại khác người
thành một group nếu khoảng cách/thời lượng cho phép. Nay cue lồng tiếng giữ
nguyên định danh đó để áp dụng ranh giới người nói đã có trong planner.

Không suy nhãn từ nội dung, tên nhân vật hoặc SRT. Hai cue chưa có nhãn vẫn
dùng hành vi cũ. Không đổi schema, cache key, timing, text hiển thị, tốc độ,
provider hay thêm voice mapping tự động. Phân biệt được nhóm khác người
không tự tạo hai giọng: job OmniVoice hiện vẫn nhận một reference/config.

Regression đi qua đường `ASRData → engine → plan`: khác người, khác scope,
known/unknown, cùng người, hai unknown, override khác nhau và override xóa
nhãn. Trước sửa **4 fail/3 pass**, sau sửa suite dubbing **131 pass**, CLI
**149 pass**. Ruff app/tests và translations sync pass. Pyright working tree:
**0 errors/0 warnings**. Lượt snapshot trước đó có một warning thiếu
`_version.py` sinh tự động vì Git archive không chứa file đó. Không build
hoặc smoke EXE mới.

## Mẫu nghe và bằng chứng local

Audit `bv1gf-prosody-20260916-171148` dùng source snapshot từ `7e2cb10`, sau
đó chép đúng engine/test đã sửa và kiểm bytes trước validation. Evidence riêng
ở `.tools/`; bàn giao trong `work-dir/BV1GFbk6LEVm-prosody-20260916-171148/`.
Media, transcript, model và reference giọng không đưa vào Git.

- C thử tag nonverbal có tài liệu cùng punctuation, giữ reference B/seed/model
  và tốc độ 1×: 3 WAV mới, max delay 670 ms. **User không chấp nhận C** và chỉ ra
  đoạn thoại có hai người; fit kỹ thuật không là nghiệm thu độ tự nhiên.
- D giữ nguyên WAV hai câu của người khách từ B, chỉ tạo reference tổng hợp
  thứ hai và WAV cho câu người chủ mời ăn. Gán lượt thủ công theo cảnh/lời
  thoại; không clone diễn viên hoặc tự nhận là đã pass diarization. Scheduler
  và mixer của app chạy với WAV thật, tốc độ 1×, max delay 530 ms. Video 11 s,
  H.264/AAC/mov_text, phụ đề không lộ tag. User xác nhận D tách được vai nhưng
  giọng chưa hợp: người vào phòng là đệ tử, người mời ăn là sư phụ/tiên nhân trẻ.
  D chưa đạt chọn giọng cho vai.
- E theo lựa chọn user **nữ trẻ, điềm tĩnh**: tạo reference với các thuộc tính
  OmniVoice có tài liệu `female, young adult, moderate pitch`, giữ transcript/
  seed/steps của reference D. Tạo lại một WAV sư phụ, giữ hai WAV đệ tử; 1×,
  max delay 530 ms, video/track subtitle sạch đã kiểm. Đây là thử voice design
  tiếng Việt, chưa có đánh giá nghe E; không bịa tham số emotion. Lượt harness
  đầu sai đường dẫn Python, dừng trước inference; sửa locator rồi chạy thành công.

Ngữ cảnh xưng hô trong **More → Ngữ cảnh xưng hô** hiện phục vụ nhân vật/người
nói/người nghe/quy tắc dịch. Nó chưa tự định tuyến reference TTS cho từng vai.
OmniVoice Local đã có audio reference + transcript để clone; các mẫu B–E này
vẫn dùng reference tổng hợp, chưa kiểm clone giọng diễn viên từ clip gốc.

## OCR/ASR: kết quả có giới hạn

- Checkpoint cũ vẫn 94 cue/18 `empty_engine_read`; 58 cue dưới 100 ms. Có 13
  cue được chọn text không rỗng nhưng một candidate khác rỗng; 5 cue text rỗng.
  Giữ nguyên guard và SHA checkpoint, không fake review hoặc sửa raw.
- Probe frame 30 s: OCR CPU đọc được dòng cao 32 px; tracking dùng ngưỡng
  40% của ROI cao 90 px, tức 36 px, nên báo `present=false` cả khi dùng
  detector mới lẫn geometry của raw đã đọc. Đây là lỗi mất vùng có chữ trước
  recognition, khác lỗi chọn dòng v3 đã sửa. Chưa đổi tracking policy.
- A/B ROI 28,8–32,3 s: ROI cũ complete/5 cue nhưng bỏ khoảng có chữ ở giữa;
  ROI hẹp giữ thêm chữ, lại tách vụn và chạm cap 18 request, `complete=false`,
  exit5. Không nâng cap, không coi đây là cấu hình sửa lỗi đã đạt.
- ASR CUDA hai cửa sổ 27–34 s/57–63 s, cùng large-v3/VAD bật/không prompt,
  lấy lại nhiều lời bị mất trong lượt dài. Vẫn sai một số chữ/tên riêng và
  câu đáp, có cue gộp nhiều lượt; không nghiệm thu transcript hoặc speaker.
- Không gọi gateway thêm, không gửi audio, không chạy lại toàn video.
