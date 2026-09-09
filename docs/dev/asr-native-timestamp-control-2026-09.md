# Native timestamp decoder trên text Qwen — 2026-09-09

Tiếp tục đúng checkout ASR-S3, `codex/asr-s3-native`, HEAD **b102ae9**; working
tree đầu phiên sạch. **Timing Qwen vẫn chưa nghiệm thu.** Thử nghiệm mới cải
thiện vị trí hai onset so với direct DTW, nhưng không qua đối chứng dịch chuyển
audio đã định trước. Không tích hợp vào app, tạo SRT mới hoặc chuyển sang LLM.
Giữ nguyên SRT thử nghiệm 9 cue cũ ở trạng thái chưa được chấp nhận.

## Phép đo khác với DTW

Dùng timestamp-token head của Whisper large-v3 đã có, với prefix là **chính
text Qwen cached** của chunk cuối 37.650–60.000 ms. Chia bốn cue theo text đã
có; tokenizer roundtrip và chuỗi BPE khớp nguyên text của probe trước.
Không gọi Whisper.align, không nhận dạng lại Qwen, không lấy giờ từ transcript
khác, không cắt cue/audio, sửa raw hoặc chọn mốc giữa nhiều provider.

Interface được đối chiếu với
[CTranslate2 v4.6.0](https://github.com/OpenNMT/CTranslate2/blob/v4.6.0/src/models/whisper.cc)
và [decoder cùng phiên bản](https://github.com/OpenNMT/CTranslate2/blob/v4.6.0/src/decoding.cc).
Mỗi cue có prefix chứa text gốc và timestamp trước đó của chính candidate.
Giữ toàn bộ logits trả về; lấy argmax trong vocabulary timestamp rồi đổi ID
thành ms theo lưới 20 ms. Không làm tròn sang 500 ms: các giá trị bên dưới là
ID model dự đoán. Prefix continuation của CT2 không áp đầy đủ quy tắc timestamp
như generation từ đầu; report lưu riêng global winner và tổng xác suất timestamp,
không gọi candidate này là native transcription mặc định.

CT2 4.6.0 được import từ wheel chẩn đoán đã có. Giữ nguyên weights SHA-256
`69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1`, float16,
frontend và runtime Python 3.12 cũ. Không tải wheel/weights mới, cài package,
đổi dependency project, cache production hoặc bridge.

## Kết quả và đối chứng

| Cue trong chunk cuối | Start ms tuyệt đối | End ms tuyệt đối |
| --- | ---: | ---: |
| 1 | 37.650 | 42.150 |
| 2 | 44.150 | 46.150 |
| 3 | 46.150 | 47.650 |
| 4 | 49.150 | 55.150 |

Speech giữ nguyên đủ text, interval dương, trong audio và không overlap. Hai
onset có khoảng nghỉ ở direct DTW (41.890 / 47.150 ms) chuyển sang
44.150 / 49.150 ms. **Chưa chứng minh toàn bộ biên đúng với lời nói.**
Đối chứng silence cùng text/độ dài cũng tạo interval hợp lệ; no-speech probability
0,7080 so với 0,000495 trên speech. Đây là bằng chứng geometry đơn thuần không
đủ, không phải một gate acoustic sản phẩm mới đã được nghiệm thu.

Để kiểm tra timestamp có đi theo audio hay chỉ có vẻ hợp lý, contract thứ hai
được ghi **trước inference**: chèn đúng 16.000 sample zero tại sample 80.000
của chunk (local 5 s, trong khoảng nghỉ), giữ mọi sample gốc. Chỉ một biến đổi,
không sweep/crop. Hai biên cue đầu phải giữ giờ; sáu biên sau phải dịch +1.000 ms,
với tolerance 250 ms đã định trước. Đối chứng này không thay audio gốc hoặc tạo
mốc dùng để xuất phụ đề.

- Delta kỳ vọng: `0, 0, 1000, 1000, 1000, 1000, 1000, 1000` ms.
- Delta đo: `0, 500, 500, 500, 500, 1000, 500, 500` ms.
- **6/8 biên fail**, mỗi biên lệch 500 ms so với kỳ vọng.
- Ở onset cue 2 sau chèn gap, global winner là **EOS**, tổng xác suất timestamp
  vẫn lớn hơn từng token riêng lẻ. Không coi đây là Qwen generation loop hoặc
  sửa EOS/text để hợp thức hóa kết quả; đó là output của decoder timing thử nghiệm.

Không tăng tolerance sau khi thấy kết quả, ghép onset mới với end DTW cũ hoặc
chọn timestamp có xác suất thấp hơn để khớp audio. **Candidate bị từ chối; chưa
có gate CLI/GUI/SRT/LLM mới pass.** Không xuất thêm một SRT thử nghiệm sau khi
đối chứng đã fail.

## Evidence, lỗi helper và preservation

Các thư mục dưới
`build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`:

- `timestamp-decoder-20260909/`: helper lỗi serialization sau lần decode onset
  đầu; exit 1 / 22,500 s. Không có logits đã lưu cho lần này.
- `timestamp-decoder-run02-20260909/`: vẫn thiếu chuyển StorageView từ GPU sang
  CPU; exit 1 / 8,906 s. Giữ token onset và shape trả về. CPU check sau đó xác
  nhận `.to_device(Device.cpu)`; lớp output có padding 51.872 phần tử, vocabulary
  thật lấy từ tokenizer. Không dùng padding làm class timestamp.
- `timestamp-decoder-resume-20260909/`: dùng lại onset đã lưu từ run02, không
  inference lại onset đó; chạy bảy biên speech còn thiếu và tám biên silence.
  **Exit 0 / 16,796 s**; speech encoder 0,344 s, phần speech 4,281 s có reuse onset.
  Đây là thời gian helper, không benchmark ASR. `validation.json` tổng hợp kết
  quả, `accepted=false`, `integration_allowed=false`.
- `timestamp-decoder-gap-20260909/`: một encoder/eight boundary requests cho
  đối chứng chèn gap; **exit 0 / 14,016 s**, control fail như trên.

Tổng gồm cả hai lần helper lỗi: **5 encoder forwards, 25 decoder generate calls**;
onset đầu từng chạy hai lần do lỗi instrumentation, được ghi rõ thay vì che
thành một lượt thành công. 0 Qwen recognition, 0 direct DTW, 0 API ASR/dịch và
0 download. Worker offline, có GPU lease/deadline; process do task tạo đã đóng.
Mỗi lượt giữ **41 file bảo vệ** nguyên hash/mtime, gồm source liên quan,
audio/model/runtime và raw/candidate/generation trace được kế thừa. Validation
cuối kiểm tra lại preservation, không inference.

Không đổi app source, translation config, raw/cache/retry plan gốc hoặc EXE.
Parent Qwen tại **88.950 ms** đã EOS vẫn nguyên vẹn, không chạy lại; ba trace
generation loop cũ giữ nguyên. Kế thừa **142 test**, Ruff/pyright/sync và EXE
ResumeGuard; không rerun full/static/test/build khi app không thay đổi.

## Điểm dừng và thứ tự tiếp tục

Timing chưa đủ căn cứ tích hợp. Không lặp direct DTW, sparse slots/crop, mask
probe cũ hoặc native-prefix/gap control này để tích pass. Các tensor đã lưu đủ
để phân tích tiếp; inference mới phải kiểm chứng một thay đổi thuật toán acoustic
cụ thể. Cần kiểm định biên tuyệt đối với audio, giữ toàn bộ text/provenance và
qua đối chứng trước khi đưa phương án vào pipeline. Không lấy geometry, energy
hoặc sự đồng thuận giữa model làm nhãn timing tham chiếu.

Theo thứ tự user yêu cầu, **quality/stall, tải model thật qua mạng và GUI HTTP
cancel/resume chưa chuyển sang nghiệm thu** vì timing vẫn mở. Không coi lần tải
wheel cũ hoặc reuse model là cài mới qua mạng. OmniVoice Studio sau ASR, cần
xác minh interface chính thức; VieNeu Local giữ nguyên, OCR tiếp tục dừng.
