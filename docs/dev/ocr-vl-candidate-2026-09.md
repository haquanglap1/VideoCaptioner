# PaddleOCR-VL candidate cho OCR nguồn

Candidate `paddleocr-vl-1.5-anchor-v1` là lựa chọn thử nghiệm, chưa đổi OCR mặc định.
CPU PP-OCRv6 giữ detection/tracking; PaddleOCR-VL-1.5 nhận dạng crop dòng được chọn
trong Python GPU riêng. Không đưa chữ CTC, reference hoặc tên file vào prompt.

## Chọn runtime đã có

Chuẩn bị một thư mục chứa `paddle-vl-runtime.json`:

```json
{
  "schema": "paddle-vl-runtime-v1",
  "python": "../gpu-env/Scripts/python.exe",
  "model": "../paddle-vl-model",
  "dependencies": "../paddle-vl-deps"
}
```

Các path được resolve tương đối với thư mục manifest. Manifest không tự cài hoặc
tải model. Recipe đóng gói tại `videocaptioner/resources/ocr/paddle-vl.json` ghim
model revision, hash weights/tokenizer/processor/custom code và phiên bản package.
Worker kiểm inventory/output classes/tokenizer trước inference; chỉ dùng CUDA,
BF16/SDPA, prompt `OCR:`, greedy 96 tokens, không KV cache. Adapter chỉ đổi keyword
masking `inputs_embeds` thành `input_embeds` cho runtime đã ghim.

Trong cửa sổ OCR, chọn runtime CPU hiện có và thêm thư mục PaddleOCR-VL; để trống
ô PaddleOCR-VL dùng OCR cũ. Candidate cần chọn đúng một dòng. CLI:

```powershell
uv run --frozen videocaptioner ocr clip.mp4 --ocr-runtime runtime/ocr-v6-medium `
  --recognizer-runtime runtime/paddle-vl --roi 0.05,0.88,0.90,0.10 `
  --start-ms 1000 --end-ms 4000 --line-anchors 0.5 --tracking characters-v3 `
  --consensus punctuation-v2 --max-requests 40 --timeout 90 `
  --checkpoint candidate.ocr.json -o candidate.srt
```

Thử trên đoạn ngắn: cap cứng 40 recognition requests cho cả CPU geometry và VL,
360 giây/job; timeout từng request không quá 90 giây. Không tự retry hoặc fallback
model. Một GPU lease được giữ trong suốt worker; timeout/hủy đóng đúng process và
join reader. Phần checkpoint đã hoàn thành được giữ incomplete nếu scan lỗi.

## Chữ, geometry và identity

Chọn nguyên các box của dòng theo line-selection hiện có, lấy union rồi thêm
margin nửa chiều cao dòng theo ngang, một phần tư theo dọc, clip trong ROI. Crop
giữ RGB gốc, không sửa contrast hoặc glyph. Đây là routing mới, có identity riêng;
tracking v1/v2/v3 và consensus giữ semantics cũ.

Raw read mới giữ token IDs, raw decode, EOS, crop hash/bounds và các line CTC dùng
lấy geometry. Điểm score bằng 0 vì chưa có confidence được hiệu chuẩn. Bounding
box của text sinh là vùng input crop, không phải localization do VL cung cấp.
Khi tracking dùng cached read, chỉ tái dùng box CTC gốc.

Config/cache/cue IDs bao gồm recognizer recipe và worker hash; dữ liệu nhận dạng
cũ không được dùng nhầm cho VL. Checkpoint cũ bỏ hoàn toàn field mới khi serialize,
giữ ID/bytes tương thích. Resume candidate phải chọn lại đúng runtime CPU và VL;
thiếu hoặc khác identity bị từ chối. Thiếu EOS, sai token range, worker identity,
crop hash hoặc protocol không được ghi thành cache success. Không nới export guard.

Raw/provenance đi qua subtitle JSON và editor metadata; SRT chỉ chứa text/time.
Reference đánh giá là `AI visual reference`, không phải transcript lời nói đã được
xác minh. Diagnostic nhỏ không thay thế gate window, native GUI hoặc EXE.

Kết quả và giới hạn của lượt đo được ghi trong
[báo cáo quality-first](ocr-asr-quality-first-results-2026-09.md). Build/EXE, portable
runtime và quality trên toàn video vẫn cần nghiệm thu riêng.
