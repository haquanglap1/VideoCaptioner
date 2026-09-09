# Căn trực tiếp chữ Qwen và định vị generation loop — 2026-09-09

Tiếp tục ASR-S3 / `codex/asr-s3-native`, HEAD **d2dc518**, kế thừa nguyên 29 file
chưa commit. **Chưa có Qwen SRT được nghiệm thu trên mẫu user 60 s.** Có SRT thử
nghiệm đủ chữ để review, không phải đầu ra sản phẩm được chấp nhận. Không đổi
code app, runtime cũ, guard, cache hoặc EXE; không reset/commit/push. OCR dừng,
OmniVoice Studio vẫn sau ASR và phải xác minh interface chính thức.

Evidence riêng:
`build/asr-session-evidence/VC-ASR-Completion-20260908-140534/direct-qwen-align-20260909/`.
`source-before/` và `source-before.json` giữ snapshot/hash/mtime của đủ 29 file
đầu phiên. Hai probe sparse slots và crop cue cũ **không chạy lại**.

## Timing: căn chính transcript Qwen với audio

[CTranslate2 Whisper.align](https://opennmt.net/CTranslate2/python/ctranslate2.models.Whisper.html#ctranslate2.models.Whisper.align)
nhận text tokens cần căn. Dùng đúng text Qwen đã cache của chunk cuối
**37.650–60.000 ms**, tokenizer roundtrip giữ từng ký tự/dấu câu. Không gọi
Whisper generation hoặc lấy giờ từ bản nhận dạng Faster-Whisper khác.

- Giữ model large-v3 đã cài, SHA-256 weights
  `69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1`.
- Tải riêng **một wheel CTranslate2 4.6.0 / 19.470.040 byte**, xác minh SHA-256
  `511cdf810a5bf6a2cec735799e5cd47966e63f8f7688fdee1b97fed621abda00` từ PyPI.
  Giải nén vào `diagnostic-libs/` trong evidence, không cài vào project/runtime,
  không sửa pyproject/lock. **Không tải model weights.**
- Worker riêng dùng Python 3.12.13 và thư viện đã có, socket bị chặn; GPU lease
  và deadline hữu hạn. Bước import đầu thiếu `pkg_resources` trong setuptools 84;
  dùng bản đã có ở môi trường project chính qua đường import cuối, không cài gói.
  Không inference ở bước import lỗi.
- Một forward speech và một đối chứng silence cùng độ dài/text. Giữ raw DTW
  path, token IDs, xác suất token, phép đổi frame 20 ms và Unicode units. Không
  clamp, sửa endpoint, chia đều, dùng heuristic trim của Faster-Whisper hoặc sửa
  raw Qwen. Nguồn thuật toán đối chiếu:
  [find_alignment, v1.2.1](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py).

Speech qua geometry/energy của policy cue hiện có; silence bị geometry chặn.
Kết quả bốn cue cuối, theo thứ tự text:

| Cue trong chunk | Start ms | End ms | Đánh giá |
| --- | ---: | ---: | --- |
| 1 | 37.650 | 41.790 | Raw DTW bắt đầu ngay đầu chunk; chưa xác nhận onset |
| 2 | 41.890 | 45.970 | Đầu cue chứa khoảng nghỉ trước lời nói |
| 3 | 46.050 | 46.910 | Interval dương, không còn token biên đảo chiều như Qwen |
| 4 | 47.150 | 54.510 | Đầu cue chứa khoảng nghỉ; end mới có nguồn acoustic trực tiếp |

**Geometry/RMS pass chưa là acoustic acceptance.** DTW gán khoảng nghỉ vào token
đầu, nên không tích hợp làm fallback tự động. Community-1 đã cache có onset quanh
44.277 và 49.289 ms, nhưng cũng bỏ sót một phần cue ngắn ở 46 s; không dùng các
span này để clamp/cắt audio hoặc gán giờ. Không chạy thêm VAD/crop/window sweep.
Tool audio hiện tại báo không hỗ trợ audio input; không tuyên bố đã nghe/duyệt
thủ công các biên. Issues upstream về silence chỉ là thông tin bổ sung, không
chứng minh nguyên nhân từng cue local hoặc cung cấp fix:
[Qwen #153](https://github.com/QwenLM/Qwen3-ASR/issues/153).

Host **exit 0 / 23,015 s**, load **4,093 s**, speech request **11,172 s** gồm
frontend và alignment. Giữ **14 file nguồn/model** nguyên hash/mtime, process
đã đóng. Không xem đây là benchmark inference thuần hoặc nghiệm thu cả 60 s.

## Artifact review cụ thể

`candidate-not-accepted/user-60s.candidate-not-accepted.srt` có **9 cue**, giữ
nguyên text Qwen 60 s. Hai chunk đầu dùng raw Qwen đã qua policy; chunk cuối dùng
raw DTW mới của chính text đó. Không chọn mốc tốt từ nhiều lần thử trong một cue,
không trộn giờ từ transcript khác hoặc sửa raw. JSON cùng tên giữ audio identity,
ID token Qwen gốc, recognition provenance và alignment provider riêng từng cue.

- SRT roundtrip giữ nguyên text/start/end; geometry và energy pass.
- SHA-256 SRT:
  `fa15d0f8368fc906e5da5d131ff6fe9a61942a87f77cba6f9bf6bd7fe3a971ed`.
- `validation.json` ghi **accepted=false**, nguyên nhân và nguồn endpoint.
- Đây là artifact thử nghiệm để review, **không phải CLI/GUI Qwen tự xuất thành
  công hoặc SRT được duyệt**. Không gửi sang LLM, không coi TXT recovery hay file
  SRT có cú pháp hợp lệ là thay thế gate audio. App vẫn giữ hành vi review/exit 5.

## Generation: kiểm tra mask trên đúng request chưa hoàn tất

Kế thừa CPU validation của audit attention trước, chỉ nối block mask đã có vào
encoder **recognition** trong RAM của worker thử nghiệm. Đây không phải chạy lại
probe aligner mask cũ. Giữ checkpoint, BF16/SDPA, prompt Chinese, WAV/hash,
generation budget và EOS guard. Không replay request nhận dạng đã hoàn tất.

| Request / offset ms | Kết quả mask candidate | Wall request s | Token sinh |
| --- | --- | ---: | ---: |
| R8001_M8004-c02 / 59.700 | Incomplete | 53,047 | 1.192 / 1.192 |
| R8001_M8004-c02 / 88.950 | **EOS complete** | **5,687** | **111 / 1.176** |
| R8007_M8010-c02 / 51.100 | Incomplete | 66,891 | 1.188 / 1.188 |
| Stress / 640.700 | Incomplete | 88,859 | 1.170 / 1.170 |

Trace xác nhận mask ở encoder thật, bốn block mỗi request. Ba output incomplete
lặp terminal pair **582 / 546 / 570 lần**, chưa EOS; worker vẫn chạy generation,
không phải chỉ đang chờ download hoặc host bị deadlock. Raw ID/text chẩn đoán giữ
trong evidence riêng, không vào cache complete hoặc TXT sản phẩm; không cắt chuỗi
lặp để giả hoàn tất. Đây là định vị failure mode, **chưa xác định/sửa hết nguyên
nhân generation loop**. Mask ảnh hưởng một request nhưng không đủ giải quyết ba
request còn lại. Không đổi sampling/repetition penalty hoặc sweep tiếp.

Host **exit 0 / 232,781 s**, bốn request cùng worker; **20 file bảo vệ** giữ
hash/mtime, process/lease đóng. Có UnrealEditor-Cmd của công việc khác sử dụng
GPU; không đóng process đó và không dùng wall time để suy speedup tổng file.

## Chất lượng: một phép so từ cache, không chấm lại corpus

Chỉ thay vùng parent vừa complete **88.950–117.700 ms** trong TXT clip
R8001_M8004-c02; ba retry con cũ phủ đúng **460.000 sample**. Giữ nguyên mọi chữ
của các chunk khác, không inference lại. Candidate nằm ở
`quality/R8001_M8004-c02.mask-parent-candidate.txt`.

Với cùng **975 ký tự tham chiếu**, baseline kế thừa **599 lỗi / CER 61,44%**;
candidate ghép cache có **587 lỗi / CER 60,21%**. Cả hai 444 ký tự hypothesis.
Đây là kết quả **trộn output policy cũ với một parent mask candidate**, không là
CER của model mask trên toàn clip/corpus, không đổi common-28 hoặc chứng minh
quality đã đạt. `quality/summary.json` giữ nguồn ba retry con và trace generation.

## Gate và bước tiếp theo

- Không thay code app/worker sản phẩm, guard, dependency project, raw/cache cũ,
  runtime đã cài hoặc cấu hình dịch. Kế thừa **142 test pass**, Ruff/pyright/sync
  và smoke ResumeGuard; **không rerun test/build** khi chưa có source candidate
  đủ căn cứ tích hợp. Không gọi API dịch/ASR hoặc tìm credential.
- Verify/reuse model thật và GUI cancel verify cũ vẫn được kế thừa. **Chưa tải mới
  model qua mạng, chưa GUI cancel HTTP/resume mới, chưa workflow EXE đầy đủ.**
  Wheel chẩn đoán không được tính là tải model hoặc gate installer GUI.
- Không chạy lại direct DTW nguyên chunk để tích số pass: đã biết vấn đề onset.
  Hướng tiếp theo phải giải quyết pause/onset có nguồn acoustic và giữ đủ chữ,
  không ghép mốc, chỉnh raw hay đưa candidate SRT này vào pipeline mặc định.
- Ba request loop còn lại đã có token trace; kế thừa chúng khi điều tra EOS,
  không chạy lại chỉ để quan sát cùng chuỗi lặp. Parent vừa complete đã có output;
  không chạy lại. Retry plan/cache gốc vẫn là đường hoàn tất TXT đang có.
- Chỉ ba tài liệu có sẵn được bổ sung (prompt, plan, status) và báo cáo mới này.
  Các helper/raw/candidate/library nằm dưới evidence bị Git ignore. ASR sản phẩm
  vẫn mở; OmniVoice Studio chưa bắt đầu, VieNeu Local giữ nguyên, OCR tiếp tục dừng.
