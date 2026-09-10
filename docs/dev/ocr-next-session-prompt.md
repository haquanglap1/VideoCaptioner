# Prompt phiên tiếp theo — bắt đầu OCR sau sửa Soniox/Qwen

Tiếp tục **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**. Không làm ở
checkout master. User ngày 2026-09-10 đã yêu cầu chuyển sang OCR sau khi sửa lỗi
Soniox/Qwen; chỉ đạo này thay thế phần “tạm dừng OCR” của prompt cũ. Không tự
mở lại toàn bộ nghiệm thu ASR để trì hoãn OCR, nhưng giữ riêng mọi giới hạn chưa đo.

## Bắt đầu

Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`,
`docs/dev/asr-recovery-2026-09.md` và
`docs/plans/video-subtitle-ocr-integration-plan.md`. Chạy `git status --short --branch`,
lấy HEAD thật và đối chiếu tracking/origin. Snapshot đã được user yêu cầu commit/push:
`9ae8465` sửa startup update, `1a10f69` sửa Soniox/Qwen và đóng gói model; commit tài
liệu theo sau. Không checkout về baseline `f03420c` hoặc coi commit code là HEAD cuối.
Giữ mọi thay đổi có sẵn; quyền push vừa cấp chỉ chốt snapshot này, không tự áp dụng
cho phiên OCR. Không reset, merge master, commit/push/tag/release nếu chưa được yêu cầu.

## Phần đã làm, không chạy lại

- Soniox SRT theo câu giữ token 0 ms khi cue có span lời nói cùng nguồn/người nói
  ở gần và mốc câu hợp lệ. Không nội suy timestamp từng từ. Chế độ word vẫn strict;
  thiếu/đảo/out-of-bounds timing, cue toàn 0 ms hoặc không có anchor vẫn review.
- Review Soniox của clip 111,333 s đã phục hồi **21 cue** ở
  `build/asr-recovery-20260910/output/soniox-recovered.zh.srt` và JSON cạnh đó,
  giữ đủ chữ, không sửa raw review, không thêm override, **0 request Soniox mới**.
- Qwen GUI có ô ngôn ngữ nguồn; Auto được ghi rõ là preset Chinese (zh) của luồng
  Qwen hiện tại, không phải language detection. Không đổi lựa chọn ngôn ngữ đã lưu
  của engine khác; ngôn ngữ khác chọn tường minh vẫn bị chặn trước recognition.
  CLI tiếp tục dùng `--language zh`. Bật split trong GUI không ép native/Qwen sang
  timestamp từng từ. Guard source/speaker/context không bị bỏ qua.
- Dùng biên bản và receipt cuối để lấy đúng build/hash/gate; không coi build đầu
  hoặc source replay là bằng chứng workflow frozen nếu biên bản chưa ghi nhận.
- Giữ clip 30 s/ASR/bản dịch/6 WAV, Soniox review và bài giảng đã chốt, 151 WAV/
  121 nhóm lời sửa. Không nhận dạng/dịch/TTS/render lại các job đã xong.

## Mục tiêu OCR phiên này

Tiếp tục **OCR-1: pilot trên cùng 13 crop** theo plan đã có, trước khi làm toàn GUI.
Giữ hai hướng **OCR local** và **AI đọc ảnh**; không tự kết luận hướng nào tốt/rẻ hơn.

Evidence có sẵn dưới:
`build/asr-session-evidence/VC-UserClip-20260908-114035/`

- `inputs/sample-zh.mp4`: sample cũ, không tải/cắt nguồn lại để tạo cùng input.
- `inputs/source-caption-refined.png`: contact sheet 13 câu do agent đã đọc.
- `reports/source-caption-visibility-refined.json`: khoảng hiển thị và representative_ms.
- `inputs/reference-zh.srt`, `reports/reference-provenance.json`: tham chiếu có ảnh,
  chưa phải ground truth được người bản ngữ xác nhận.

Đã xác nhận contact sheet và mapping còn tồn tại. Chưa có bộ 13 crop độc lập ở độ
phân giải gốc: trích đúng representative_ms và ROI từ sample để tạo một bộ input chung.
Không dùng contact sheet có header hoặc text đáp án làm input cho phép so sánh mù.

1. Đối chiếu plan/evidence, tạo một scratch OCR duy nhất; giữ mapping crop/PTS/hash.
2. Khảo sát và pin ứng viên RapidOCR + ONNX Runtime CPU theo nguồn chính thức:
   detector/recognizer/dictionary/preprocessing phải cụ thể, không dùng model mặc định
   ngầm theo phiên bản. Chuẩn bị runtime riêng; không cài NumPy/OpenCV/ONNX vào Qt
   process hoặc đổi môi trường ASR/TTS. Không sweep nhiều model hoặc benchmark toàn video.
3. Chạy OCR local trên 13 crop, giữ raw output/score và lỗi. Agent đối chiếu ảnh và
   giải thích bằng tiếng Việt; không giao user nhiệm vụ kiểm tra từng chữ Trung.
4. Với nhánh AI đọc ảnh, chưa có lựa chọn vision model/endpoint/ngân sách được chốt.
   Chuẩn bị input/prompt/metric trước; hỏi đúng lựa chọn còn thiếu nếu cần gọi vision API.
   Không tự cho rằng model dịch hiện tại nhận ảnh hoặc dùng STT key làm vision key.
5. Báo riêng độ đúng chữ/tên/số, bỏ sót, timing, load/inference/total, số crop/call,
   cache/fresh, RAM và usage thực có. Thiếu usage để null, không đoán số token/chi phí.
6. Chỉ sau pilot mới đề xuất engine và triển khai các bước OCR còn lại theo plan:
   ROI, decode theo PTS, bộ đệm giới hạn, gom thay đổi chữ, review và xuất SRT/JSON.
   OCR timing là thời gian chữ trên màn hình; không gọi là timestamp giọng nói.
   Không tự gán speaker/xưng hô hay đổi giản/phồn thể/đoán chữ thiếu.

## Cấu hình và artifact

- Python 3.12.13: `../VideoCaptioner/.venv/Scripts/python.exe`; FFmpeg/ffprobe đã có.
  Không dùng Python 3.13, cài global hoặc sync/nâng dependency app chỉ để chạy pilot.
- LLM dịch: `https://api.videocaptioner.cn/v1`, `gpt-5.6-terra`, timeout 300 s;
  không đổi gateway/model. Key user cấp ở `../../Api.txt`, chỉ đọc khi thực sự cần
  và đúng endpoint/phạm vi đã cho. Không ghi key vào settings/chat/argv/env/log/Git.
  Dùng LLMCredentials trong RAM và child_environment() cho subprocess.
- Bản EXE test từ nay **kèm model/runtime đã cài trong `models/` cạnh EXE**, tự tìm
  được sau khi chuyển ổ. Dùng `scripts/package_test_models.py` và `VC_TEST_MODELS_DIR`
  của spec; thêm runtime OCR đã cài vào quy trình này khi có. Không chỉ chép weights
  rồi để Python/venv trỏ về đường dẫn máy dev. Không tải lại model đã có.
- Không đưa key/settings cá nhân, media, WAV cache job hoặc log vào gói model.
  Giữ các runtime/models cũ, không xóa phần đã tải hoặc artifact khác để dọn ổ.
- Không bật Computer Use khi chỉ làm file/code. Nếu cần GUI, thao tác đúng process
  test, đóng sạch và kết thúc điều khiển ngay sau test. User nói dừng thì dừng UI ngay.
- DeepLX/Google/Bing/Bijian/Bilibili/Jianying/ElevenLabs vẫn ngoài phạm vi nghiệm thu này.
  Không tự dùng chúng làm fallback hoặc lấy video mới từ Bilibili.

Cập nhật status/biên bản bằng bằng chứng thực, phân biệt pass/fail/chưa chạy và
source/frozen/GUI. Không gọi OCR hoàn tất chỉ vì import được engine hoặc đọc tốt
một contact sheet. Bàn giao kết quả pilot và bước tiếp theo cụ thể.
