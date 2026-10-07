# Qwen3-ASR tại máy — cách hoạt động và cách dùng

Hướng dẫn ngắn cho engine `Qwen3-ASR [Local]` trong tab **Nhận dạng**. Chi tiết kỹ thuật,
pin model và giới hạn nghiệm thu nằm ở [S5](../dev/asr-local-s5.md) và
[sentence/preparation](../dev/asr-sentence-preparation-2026-09.md).

## Qwen làm gì

- Nhận dạng **tiếng Trung (zh)** ngay trên GPU của máy; audio không được gửi lên dịch vụ nào.
  Chọn ngôn ngữ khác sẽ bị từ chối trước khi chạy.
- Chạy theo **ba bước**, mỗi bước là một model riêng:
  1. **Nhận dạng** (Qwen3-ASR 1.7B hoặc 0.6B) → chữ. Đủ để xuất **TXT**.
  2. **Căn thời gian** (Qwen ForcedAligner 0.6B) → mốc câu để xuất **SRT/ASS/VTT**.
  3. **Người nói** (pyannote Community-1) → nhãn người nói, **tùy chọn**, cần token Hugging Face.
- Khác Faster-Whisper: model nằm trong một runtime Python/CUDA riêng do app quản lý, weights ghim theo
  commit, kết quả từng chunk được cache nên chạy lại cùng audio rất nhanh.

## Dùng trong GUI

1. Tab **Nhận dạng** → nút chọn engine → **Qwen3-ASR [Local]**.
2. Trang cài đặt hiện ngay bên dưới: chọn **Qwen 1.7B** (khuyên dùng) hoặc **0.6B** (ít VRAM hơn);
   ngôn ngữ nguồn để **Tự động** (= tiếng Trung với Qwen) hoặc **Chinese**.
3. Chọn định dạng đầu ra ở nút bánh răng trên thanh công cụ: **TXT** nếu chỉ cần văn bản (nhanh nhất,
   không nạp aligner), **SRT** nếu cần phụ đề có thời gian.
4. Kéo video/audio vào và bấm **Bắt đầu**. Lần đầu app tự **chuẩn bị** model đang chọn: tạo runtime bằng
   `uv` + Python 3.12 + Torch CUDA rồi tải weights đã ghim (vài GB, có kiểm tra hash). Thanh tiến độ hiện
   `Preparing …`; có thể **hủy** và lần sau bấm lại sẽ **tiếp tục** phần đã tải.
5. Kết quả nằm cạnh file nguồn. Nếu căn thời gian thất bại, app vẫn lưu **TXT đầy đủ** và giữ bản
   review (mở bằng **Nhận dạng → Open ASR review**). Đoạn nào Qwen không căn được sẽ dùng
   **Faster-Whisper dự phòng** (lấy cả chữ và thời gian của Whisper) nếu Faster-Whisper đã cài; app báo
   số câu dự phòng khi xong.

**Quản lý mô hình** (nút trong trang cài đặt) không bắt buộc. Dùng khi muốn:

- **Kiểm tra cả 3 bước**: xem bước nào đã cài, bước nào chưa (chỉ kiểm file, không nạp GPU).
- **Chuẩn bị / tiếp tục model đã chọn**: tải trước để lần nhận dạng đầu không phải chờ.
- **Nâng cao…**: nạp thử lên GPU, cài vào thư mục mới hoặc trỏ tới runtime đã chuẩn bị ở nơi khác.

Mở trang cài đặt hoặc cửa sổ quản lý không tải, không nạp model và không gọi mạng.

## Model nằm ở đâu

- Mặc định: `runtime/local-qwen-managed/<model>-<revision>-<hash>/` cạnh ứng dụng; bản portable dùng
  `models/qwen-managed/…`. Cửa sổ Quản lý mô hình hiển thị đúng đường dẫn cho bước đang chọn.
- Thư mục runtime **không nên di chuyển** (venv chứa đường dẫn tuyệt đối). Cần Windows, `uv` trên PATH,
  GPU NVIDIA có driver hỗ trợ CUDA 12.8 và khoảng 10 GB trống cho runtime + weights.
- Community-1 là model gated: chấp nhận điều kiện trên Hugging Face rồi nhập read token trong cửa sổ
  quản lý; token chỉ dùng cho lần tải đó, không được lưu.

## Khi gặp lỗi

| Thông báo | Việc cần làm |
| --- | --- |
| `Qwen Local currently supports Chinese` | Đổi ngôn ngữ nguồn về Tự động/Chinese. |
| `Automatic local model preparation requires Windows and uv` | Cài `uv` và mở lại app. |
| `GPU out of memory` | Đóng app GPU khác hoặc chọn 0.6B; app không tự đổi model. |
| `Local runtime stage timed out` | Tăng **Thời gian chờ mỗi bước** (180 → 600 s) hoặc giảm **Độ dài đoạn âm thanh** xuống 60 s. |
| `Recognition is incomplete …` | Chunk đã xong được giữ trong cache; bấm Bắt đầu lại để chạy tiếp phần thiếu. |

## Đặt tên người nói bằng AI

Khi bật **Phân biệt người nói tại máy**, card **Đặt tên người nói bằng AI (LLM)** (mặc định bật) gửi một
yêu cầu tới dịch vụ LLM đang cấu hình để đặt tên cho từng cụm `SPEAKER_xx` dựa trên lời thoại và ô *Ngữ
cảnh bộ phim*. Tên đủ tin cậy vào thẳng Ngữ cảnh xưng hô; tên chưa chắc chờ bạn ở **More → Tên người nói
(AI)** trong tab phụ đề. Thiếu dịch vụ LLM thì bước này bị bỏ qua, phụ đề vẫn giữ nhãn ẩn danh. Chi tiết:
[speaker-naming-2026-10.md](../dev/speaker-naming-2026-10.md).

## CLI tương đương

```powershell
uv run --frozen videocaptioner transcribe clip.mp4 --asr qwen-local --language zh --qwen-model qwen-1.7b -o clip.srt
uv run --frozen videocaptioner transcribe clip.mp4 --asr qwen-local --language zh -o transcript.txt
uv run --frozen videocaptioner local-asr status
```
