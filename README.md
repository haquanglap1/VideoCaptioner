# VideoCaptioner

VideoCaptioner là công cụ xử lý phụ đề video bằng AI, hỗ trợ nhận dạng giọng nói, tối ưu phụ đề, dịch phụ đề và ghép phụ đề vào video.

## Tính năng chính

- Chuyển âm thanh/video thành phụ đề SRT, ASS, VTT hoặc TXT.
- Tối ưu câu phụ đề bằng LLM để dễ đọc hơn. Tích hợp tính năng Tìm kiếm và Thay thế hàng loạt từ bị dịch sai.
- Dịch phụ đề bằng LLM, Bing, Google hoặc DeepLX.
- Ghép phụ đề mềm hoặc ghi phụ đề cứng vào video.
- Xử lý trọn quy trình từ video đầu vào đến video có phụ đề.
- Lồng tiếng Natural theo timeline đo từ audio thật: ưu tiên bản dịch, mượn khoảng lặng an toàn,
  cache WAV bền vững, viết lại câu vượt khung khi có LLM và không âm thầm cắt lời.
- Giữ kế hoạch review trong RAM để sửa lời đọc và tiếp tục; chỉ xuất JSON khi chọn Lưu kế hoạch hoặc CLI được truyền `--report`.
  Vẫn có chế độ Legacy cho workflow cần giới hạn tốc độ/cắt âm thanh như bản cũ.
- Có tab `Video Editor` native PyQt5 để chỉnh subtitle/TTS trên timeline V1/A1/TS1, xem trước,
  tạo lại đúng group giọng đã chọn và export từ editor state hiện tại.
- Có provider `VieNeu Local` tích hợp: tự quản lý GPU sidecar ẩn, voice/model revision, update có kiểm
  định và rollback; không cần chạy server, nhập API Base hay API key giả.
- Có CLI cho tự động hóa và GUI cho người dùng Windows.

## Cài đặt để chạy từ mã nguồn

Yêu cầu:

- Python 3.10 đến 3.12.
- FFmpeg có trong `PATH`.
- `uv` để đồng bộ môi trường.

```bash
uv sync
uv run videocaptioner --help
uv run videocaptioner
```

Khi chạy `uv run videocaptioner` không kèm tham số, ứng dụng sẽ mở giao diện desktop nếu đã có các gói GUI.

## Dùng CLI

```bash
# Nhận dạng giọng nói sang phụ đề
uv run videocaptioner transcribe video.mp4 --asr bijian

# Dùng Faster-Whisper và model đã cài ở vị trí riêng
uv run --frozen videocaptioner transcribe video.mp4 --asr faster-whisper \
  --fw-program path/to/faster-whisper-xxl.exe --fw-model-dir path/to/models \
  --fw-model large-v3 --fw-device cuda --language zh

# Dịch phụ đề
uv run videocaptioner subtitle input.srt --translator bing --target-language en

# Ghép phụ đề vào video
uv run videocaptioner synthesize video.mp4 -s subtitle.srt

# Lồng tiếng Natural từ phụ đề đã dịch
uv run videocaptioner dub video.mp4 --subtitle translated.srt \
  --tts-api-key <your-key> --tts-model tts-1 --voice alloy

# Lồng tiếng bằng VieNeu Local được quản lý, không cần API key/server riêng
uv run videocaptioner dub video.mp4 --subtitle translated.srt \
  --tts-provider vieneu-local --voice "Minh Đức"

# Kiểm tra/update/rollback model VieNeu theo commit SHA
uv run videocaptioner vieneu status
uv run videocaptioner vieneu update
uv run videocaptioner vieneu rollback

# Xử lý toàn bộ: nhận dạng -> tối ưu/dịch -> ghép video
uv run videocaptioner process video.mp4 --target-language vi

# Chỉ dịch các câu có timing từ ASR; không yêu cầu timestamp từng từ
uv run videocaptioner process video.mp4 --asr faster-whisper \
  --fw-program path/to/faster-whisper-xxl.exe --fw-model-dir path/to/models \
  --fw-device cuda --language zh --no-optimize --no-split --translator llm --target-language vi

# Toàn bộ pipeline với target-only artifact riêng cho TTS
uv run videocaptioner process video.mp4 --target-language vi --dub \
  --tts-api-key <your-key>

# Tải video trực tuyến
uv run videocaptioner download "https://youtube.com/watch?v=xxx"
```

Xem chi tiết tham số:

```bash
uv run videocaptioner <lenh> --help
```

## Cấu hình LLM

Các tính năng nhận dạng/dịch miễn phí có thể dùng ngay. Nếu dùng tối ưu phụ đề hoặc dịch bằng LLM, cấu hình API:

```bash
uv run videocaptioner config set llm.api_key <your-key>
uv run videocaptioner config set llm.api_base https://api.openai.com/v1
uv run videocaptioner config set llm.model gpt-4o-mini
```

Thứ tự ưu tiên cấu hình: tham số CLI, biến môi trường `VIDEOCAPTIONER_*`, file cấu hình, cấu hình GUI,
giá trị mặc định. Cấu hình GUI là `AppData/settings.json` của bản desktop: CLI chỉ đọc từ đó API key,
base URL, model của dịch vụ LLM đang chọn, Whisper API, DeepLX endpoint và TTS lồng tiếng, nên nhập key
một lần trong GUI là đủ; các tùy chọn hành vi (optimize, translate...) không được kế thừa.

## OCR phụ đề trong hình

Lệnh `ocr` đọc một ROI cố định bằng CPU runtime đã cài và lưu `ocr-document-v1`
để review; `ocr-review --source VIDEO` kiểm SHA toàn nguồn và tiếp tục tại máy.
JSON phụ đề đã duyệt giữ raw/candidate/PTS qua dịch và Video Editor, kể cả hai
dòng chữ nguồn. CLI `subtitle` với OCR mặc định giữ câu/giờ/chữ đã đo; chỉ
`--optimize` tường minh mới bật chỉnh text LLM.

Trong màn Nhận dạng, **OCR phụ đề trong hình** mở luồng chọn video/đoạn/ROI,
chạy CPU có hủy, xem crop và lưu/mở review. Nút kiểm tra model dùng runtime đã
cài; mở cửa sổ không tự tải/nạp. CLI tự tìm bridge/profile và `models/ocr/`
trong bộ portable, vẫn cho truyền runtime tường minh.

Profile hiện chưa hiệu chuẩn: đồng thuận không tự thành accepted; chưa giải
quyết review thì không xuất subtitle success. Không tự sửa/điền chữ hoặc gọi
vision. Xem [GUI, đóng gói và giới hạn](docs/dev/ocr-gui-2026-09.md),
[contract và lệnh OCR-3](docs/dev/ocr-document-2026-09.md).

Ứng viên ưu tiên chất lượng **PP-OCRv6 medium** dùng cùng CPU runtime đã ghim.
Nếu có `models/ocr-v6-medium/` (portable) hoặc `runtime/ocr-v6-medium/`
(source/pip), app ưu tiên bộ này; vẫn nhận bộ v5 cũ qua ô chọn runtime.
**Kiểm tra model đã cài** hiển thị profile thực tế. Hai profile giữ version,
model, language và dictionary theo từng stage; kết quả v6 vẫn cần review,
không thay raw của document v5 đã lưu. [Tích hợp và nghiệm thu v6](docs/dev/ocr-v6-integration-2026-09.md).

Ứng dụng có **cache bản đọc OCR** giữa các lần quét cùng nguồn/cấu hình,
mặc định 64 MiB dữ liệu chữ (chưa gồm metadata). Trong cửa sổ OCR chọn hạn mức
**0–512 MiB**, `0` tắt disk cache; **Dung lượng cache / Xóa cache OCR** chỉ
quản lý các bản đọc tạm. CLI dùng `ocr --cache-mib N`, `ocr-cache status` và
`ocr-cache clear`. Quét lại vẫn decode video, nhưng dùng lại crop đã đọc khi
khớp SHA; cache không giữ ảnh/video, quyết định duyệt hoặc sửa raw.
[Contract và gate cache](docs/dev/ocr-cache-2026-09.md). Gói OCR6-Medium-20260911
đã được cập nhật riêng phần app ngày 2026-09-12, dùng lại models hiện có;
[gate EXE/native và cách quay lui](docs/dev/ocr-cache-binary-2026-09.md).

Sau khi hủy, **Lưu review**, rồi mở lại cùng video/review và bấm **Tiếp tục quét**.
App giữ các câu và quyết định đã lưu, kiểm lại một cue ở điểm nối rồi quét phần
còn thiếu theo vùng/đoạn/profile của checkpoint. CLI dùng
`ocr-resume partial.ocr.json --source video.mp4 --review continued.ocr.json`.
Nguồn vẫn được hash toàn file; không tự lưu khi app bị kill/crash. Xem
[contract resume và nghiệm thu](docs/dev/ocr-resume-2026-09.md).

Trong review có nút **Dịch bản đọc đang chọn sang Việt**: chỉ khi bấm mới gửi
chữ của một candidate tới LLM đang cấu hình. Bản Việt nằm cạnh chữ OCR, chỉ giữ
trong phiên và không tự duyệt/sửa chữ; AI chưa nhìn ảnh nên bản dịch không xác
minh được chữ bị thiếu. [Cách dùng và giới hạn](docs/dev/ocr-review-assistance-2026-09.md).

**Nhật ký yêu cầu** ghi các request LLM có timeout/hủy, trạng thái và token
dịch vụ trả về. Thiếu số liệu hiện `—`; cached/reasoning nằm trong input/output.
OCR draft/vision chỉ ghi metadata và usage, không ảnh hoặc chữ riêng tư.
[Phục hồi logger và lượt test vision mới](docs/dev/ocr-request-logs-2026-09.md).

## ASR qua API tương thích OpenAI

Trong cài đặt Whisper API, chọn preset `VideoCaptioner API`, `Groq`, `OpenAI` hoặc `Custom`.
Base URL, model nhập tay, prompt và ngôn ngữ đã lưu vẫn dùng được. Key được giữ riêng theo endpoint;
đổi endpoint sẽ dùng key đã lưu cho endpoint đó hoặc để trống. Mở settings không tự gọi API.

```bash
uv run --frozen videocaptioner config set whisper_api.provider videocaptioner
uv run --frozen videocaptioner config set whisper_api.api_key <gateway-key>
uv run --frozen videocaptioner transcribe video.mp4 --asr whisper-api \
  --whisper-model whisper-1 --language zh
```

`--whisper-provider` và `--whisper-request-profile` cũng dùng được với `process`.
Profile `auto` nhận biết model trong preset; model ID khác giữ request Whisper cũ.
Với alias riêng, chọn rõ `whisper` (timestamp) hoặc `json-text` (văn bản JSON).
`gpt-4o-transcribe` và `gpt-4o-mini-transcribe` dùng JSON và có thể kiểm tra nhận dạng bằng nút probe;
**xuất phụ đề tiếng Trung qua runtime alignment S2 riêng** khi chọn `zh` và runtime đã ready.
Thiếu runtime/ngôn ngữ phù hợp sẽ dừng trước upload; span không khớp dừng để review, không tạo timestamp giả.
Xem [cài runtime, policy và giới hạn S2](docs/dev/asr-alignment-s2.md). Probe API báo riêng kết quả nhận dạng
và mức timing thực tế; nút kiểm tra căn thời gian chỉ probe local theo yêu cầu.
Nếu yêu cầu word timestamp nhưng response chỉ có segment, chọn lại chế độ câu hoặc model có word timing.

## ASR native có nhãn người nói (S3)

Chọn riêng `Soniox v5 [API]` (`stt-async-v5`) hoặc `ElevenLabs Scribe v2 [API]`
(`scribe_v2`). Cấu hình key đúng provider trong Cài đặt; hai engine này không dùng key gateway.
Nhãn người nói ẩn danh và timing native được giữ qua pipeline và Video Editor; audio events
tách khỏi lời thoại. `Check service` chỉ kiểm tra dịch vụ/quyền đọc, chưa kiểm thử inference.

```bash
uv run --frozen videocaptioner config set soniox.api_key <soniox-key>
uv run --frozen videocaptioner transcribe video.mp4 --asr soniox --language zh -o subtitles.json
```

JSON giữ metadata; SRT không tự chèn tên/nhãn speaker vào chữ. File xử lý nguyên vẹn trong giới
hạn provider/app, không tự chia rồi gán cùng speaker giữa các request. Hủy local không bảo đảm
hủy xử lý hoặc phí phía provider. Xem [hợp đồng, giới hạn và trạng thái nghiệm thu S3](docs/dev/asr-native-s3.md).
S3 chưa có nghiệm thu API thật; không thay trạng thái GPT gateway→SRT/phồn thể còn thiếu của S2.

Soniox xuất theo câu có thể giữ token dài 0 ms trong cue cùng người nói có span lời
nói hợp lệ ở gần, dùng nguyên mốc provider để xuất SRT. Không suy thành timestamp
từng từ. Chế độ word vẫn strict; thiếu/đảo/vượt thời lượng hoặc cue không có anchor
vẫn giữ review. Bản review câu cũ có thể **Kiểm tra và xuất** lại tại máy, không upload.

## Ngữ cảnh xưng hô Trung → Việt (S4)

Trong tab phụ đề hoặc Video Editor, mở **More → Ngữ cảnh xưng hô** để khai báo nhân vật,
người nghe và quy tắc theo cặp/cảnh. Lựa chọn user có xác nhận/khóa ưu tiên đề xuất từ text.
Dịch lại selection vẫn nhận ngữ cảnh tài liệu; Google/Bing/DeepLX không áp các quy tắc này.
Lưu JSON/project để giữ liên kết; SRT không giữ metadata. CLI hỗ trợ
`--conversation-context JSON` và đọc trực tiếp project JSON bằng lệnh `subtitle`.
Xem [cách dùng, snapshot/cache và giới hạn S4](docs/dev/asr-context-s4.md).
Chưa nghiệm thu chất lượng xưng hô bằng người đọc hoặc các workflow online còn thiếu S2/S3.

S4.1 thêm deadline dịch **1–600 giây**, mặc định **120**. Với `gpt-5.6-terra`, đặt **300** trong
Cài đặt → Dịch vụ dịch hoặc truyền `--llm-timeout 300` cho `subtitle`/`process`.
Kết quả Soniox/Scribe lỗi timing được giữ riêng để mở bằng **Nhận dạng → Mở bản review ASR**;
user sửa timing có undo/redo rồi validate/resume tại máy, không upload lại. CLI có lệnh `asr-review`.
Xem [hướng dẫn S4.1, cấu hình timeout và review/resume](docs/dev/asr-s41.md).

## Phân đoạn LLM để chuẩn bị lời đọc

Phân đoạn ưu tiên một câu trọn ý; câu dài mới tách theo mệnh đề trong giới hạn
ký tự/từ đã chọn. Dấu phẩy không tự tạo đoạn mới. Prompt giữ nguyên chữ, tên,
số, phủ định, từ lặp và dấu câu; không tự đoán sửa ASR hoặc chèn nhãn ngắt nghỉ.
Kết quả đổi lời/thiếu lời bị từ chối trước khi ghép timing. Dấu câu được giữ qua
tối ưu/dịch và SRT chuyển sang lồng tiếng để TTS có tín hiệu ngắt nghỉ.

CLI thực hiện phân đoạn khi tùy chọn split đang bật, kể cả SRT câu cũ;
`--no-split` bỏ qua bước này. Timing từ SRT cũ vẫn là **ước lượng** khi chia lại,
không thay thế timestamp theo từ của ASR. Dữ liệu native có metadata vẫn đi qua
cơ chế phân câu/timing native và giữ guard ngữ cảnh/người nói.
Xem [hợp đồng phân đoạn và validation](docs/dev/speech-segmentation-2026-09.md).

## Qwen local và hybrid người nói (S5)

Chọn `Qwen3-ASR [Local]` trong GUI hoặc `--asr qwen-local --language zh` trong CLI.
1.7B/0.6B và ForcedAligner chạy tuần tự trong runtime riêng; không đổi engine mặc định.
Khi bắt đầu, Qwen tự chuẩn bị model đang chọn nếu thiếu; xuất phụ đề mới chuẩn bị thêm
ForcedAligner. Mở **Quản lý mô hình** không tự tải/nạp. `--local-diarize` thêm Community-1 cho
Qwen hoặc Whisper API; model gated cần user chấp nhận điều kiện Hugging Face và nhập token ẩn.
`local-diarize` dùng JSON/SRT đã có với âm thanh gốc, không nhận dạng/upload lại.
Xem [cài đặt, cache/review, GPU và giới hạn nghiệm thu S5](docs/dev/asr-local-s5.md).
Qwen và Community-1 đã có smoke local/hybrid từ source và EXE trên audio public.
Chất lượng speaker/xưng hô vẫn chưa nghiệm thu.

Để lấy **văn bản nhận dạng** từ Qwen, chọn định dạng **TXT** trong GUI hoặc xuất
`.txt` qua CLI. Luồng này chỉ cần model nhận dạng, không nạp ForcedAligner hoặc
Community-1:

```bash
uv run --frozen videocaptioner transcribe clip.wav --asr qwen-local --language zh \
  --qwen-model qwen-1.7b --qwen-runtime path/to/installed-runtime -o transcript.txt
```

Nếu xuất phụ đề mà căn thời gian thất bại, transcript đầy đủ được lưu riêng thành
TXT (thêm hậu tố số nếu file đã có). GUI nhận dạng riêng báo kết quả TXT và giữ
review để mở sau; pipeline cần phụ đề vẫn dừng. CLI yêu cầu timed subtitle giữ
exit code lỗi nếu chưa tạo được định dạng đã yêu cầu. TXT không chứa nhãn người nói.
Xem [so sánh model và kế hoạch hoàn thiện ASR](docs/plans/asr-completion-2026-09.md).

Xuất câu/đoạn dùng mốc bắt đầu/kết thúc của câu từ aligner và kiểm tra âm thanh
trong câu; lỗi thời lượng của từng token không tự chặn câu có timing dùng được.
Vùng vẫn lỗi dùng Faster-Whisper dự phòng, lấy cả chữ và thời gian của Whisper.
Đuôi quá ngắn được xử lý cùng đoạn trước để có ngữ cảnh. App báo số câu dự phòng;
JSON giữ nguồn từng câu, bản review giữ nguyên chữ và raw Qwen ban đầu.

Whisper dự phòng dùng executable/model **đã cài** trong cài đặt Faster-Whisper;
CLI dùng `--fw-program`, `--fw-model-dir`, `--fw-model`, `--fw-device` ngay cả
khi chọn `--asr qwen-local`. Thiếu công cụ hoặc dự phòng lỗi vẫn giữ TXT/review.
`--word-timestamps` và các review policy cũ giữ kiểm tra timing nghiêm ngặt.
Chế độ câu hướng đến phụ đề tương đối khớp, không bảo đảm độ chính xác từng chữ.

Trang Qwen có lựa chọn ngôn ngữ nguồn. Trong GUI, Auto dùng preset Chinese (zh)
của luồng Qwen hiện tại, được ghi rõ trong cài đặt; đây không phải nhận diện ngôn ngữ.
Lựa chọn ngôn ngữ khác tường minh vẫn được giữ và báo chưa hỗ trợ trước khi chạy.
CLI tiếp tục chọn `--language zh`. Bật split trong GUI dùng timing câu native/Qwen,
không tự yêu cầu timestamp từng từ chỉ để phân đoạn.

Nhận dạng chia request tối đa 30 giây, giữ đủ sample khi không tìm được khoảng lặng.
Chunk timeout được thử lại một lần với cửa sổ tối đa 15 giây; cache giữ chunk đã xong,
không công bố phần thiếu là kết quả hoàn chỉnh. Lỗi model người nói không làm mất
phụ đề có timing; JSON giữ trạng thái chờ gán người nói. Tự tải Qwen dùng runtime riêng,
revision/hash cố định, khóa cài đồng thời và giữ tải dở để tiếp tục; cần Windows, `uv`,
Python 3.12 và CUDA phù hợp. Runtime cũ được giữ nguyên.
Xem [thay đổi và kết quả kiểm tra tháng 9](docs/dev/asr-sentence-preparation-2026-09.md).

Qwen còn giới hạn lượng token sinh theo độ dài audio; nếu chưa EOS thì thử lại
đúng chunk chưa xong, không trả text bị cắt. Model được giữ trong job cho retry,
runtime đã cài vẫn dùng lại sau cập nhật bridge. Manager có nút **Prepare / resume
selected model** để tiếp tục chuẩn bị cùng model. Thời gian chờ stall đã giảm,
nhưng chất lượng và timestamp Qwen vẫn chưa nghiệm thu đầy đủ.
Xem [kết quả stall, GUI hủy/tiếp tục và giới hạn](docs/dev/asr-stall-resume-2026-09.md).

S5.2 thêm kiểm tra recording khi mở JSON/review hoặc chạy `local-diarize`: fingerprint PCM toàn
nguồn, chặn audio khác dù cùng duration; dữ liệu cũ vẫn mở và báo chưa xác minh. Gateway Whisper
và GPT → alignment → Community-1 đã có smoke API từ source trên audio public ngắn; GPT cũng qua
EXE S5.2, còn Whisper API từ EXE gặp HTTP 429. Gate GUI teardown và chất lượng vẫn được ghi riêng.
Xem [liên kết nguồn, review và nghiệm thu S5.2](docs/dev/asr-s52.md).

## Lồng tiếng Natural

Trong tab Lồng tiếng, chọn nguồn text `Auto / Translation / Original` và timing `Natural / Legacy`.
Natural là mặc định mới: engine group các cue liên tiếp, tính sức chứa đến cue kế tiếp với silence guard,
tổng hợp ở tốc độ provider đã chọn, đo WAV thật rồi chỉ rewrite/re-synthesize group vượt ngưỡng. Nếu vẫn
không vừa, `Review` dừng trước bước mix và mở report; `Allow overlap` giữ nguyên lời nói đầy đủ và ghi cảnh
báo. Natural không dùng đường truncate của Legacy.

Để giữ nhịp đọc đều, chọn **Tự nhiên → Nhịp đọc đều, không chồng lời**. Gợi ý tốc
độ **1,00–1,05×**, độ trễ bắt đầu tối đa **2500 ms**; câu sau chờ
câu trước đọc xong. Bật **LLM rút gọn riêng lời đọc vượt khung** để chỉ viết lại
phần lời nói đã đo là quá dài, giữ phụ đề gốc. CLI dùng `--unresolved sequential`,
`--natural-max-speed 1.0`, `--max-start-delay-ms 2500`. Nếu cần tăng nhẹ, một hệ số
chung được dùng cho toàn job để giữ nhịp nhất quán. Nếu vẫn không đủ thời gian,
app yêu cầu rút gọn/xem lại. [Chi tiết](docs/dev/natural-dubbing.md).

Cache dùng `AppData/cache/dubbing_tts/v1/` với key SHA-256 không chứa API key hay transcript trong tên
file. Report mặc định giữ trong RAM; GUI chỉ ghi JSON khi chọn **Lưu kế hoạch**, CLI khi dùng `--report PATH`.

Khi cần review, dùng **Duyệt / sửa lời đọc** trong tab Lồng tiếng, sửa riêng nhóm
cần rút ngắn rồi chọn **Tiếp tục lời đã duyệt**. App giữ phụ đề hiển thị, lời đọc
của nhóm khác và tra lại cache; chỉ tổng hợp phần thiếu hoặc đã đổi. Lời đã duyệt
không bị LLM tự viết lại khi tiếp tục. Timing vẫn được đo và kiểm tra trước khi ghép.

**Lưu kế hoạch / Mở kế hoạch** cho phép tiếp tục sau khi đóng app; chọn lại đúng
video, phụ đề và cấu hình giọng. App kiểm tra nội dung nguồn và cấu hình trước khi
tạo audio. **Nhập checkpoint cũ** dành cho report v1 cũ: đối chiếu các nhóm và cache
key với nguồn đang chọn, rồi liên kết cho lần tiếp tục; không xác minh được lịch sử
nguồn nếu report cũ thiếu fingerprint. Review lời đọc thực hiện ở tab Lồng tiếng;
**Open in Video Editor** vẫn mở video/phụ đề. Xem [hướng dẫn review/resume](docs/dev/natural-dubbing.md).

Nếu WAV của checkpoint nằm ở một cache riêng, chọn **Thư mục WAV cache** chứa trực
tiếp các cặp `<key>.wav` / `<key>.json` trước khi mở/nhập kế hoạch. Để trống để dùng
cache mặc định. Thư mục này do bạn chọn, không lấy từ JSON và không tự chép cache.

Pipeline giữ thứ tự bản gốc/bản dịch đã chọn khi chuyển sang ghép video, kể cả
khi đổi kiểu hiển thị hoặc ghép lại. SRT đã định dạng không bị áp layout hai lần.

### VieNeu Local

Chọn `VieNeu Local` trong tab Lồng tiếng để ứng dụng tự khởi động sidecar ẩn khi tải voice hoặc synthesize.
Model active được giữ offline sau lần download thành công; check/update chạy nền, candidate chỉ được
activate sau health + voices + WAV 48 kHz smoke và không đổi revision giữa một dubbing job. `Local AI`
vẫn giữ nguyên cho server bên ngoài. Chi tiết runtime, updater, build và acceptance nằm tại
[`docs/dev/vieneu-one-app.md`](docs/dev/vieneu-one-app.md).

### OmniVoice Local

Tab **Lồng tiếng → OmniVoice Local** thêm engine từ
[k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice), bên cạnh VieNeu Local.
Bấm **Chuẩn bị / tiếp tục OmniVoice** để cài runtime Python 3.12/CUDA riêng và
tải model đã ghim revision (model + audio tokenizer khoảng 3,3 GB). Cần `uv`,
Windows và GPU NVIDIA phù hợp; môi trường/dependency của app không bị thay đổi.
Có thể hủy và tiếp tục tải; mở tab không tự tải model.

Chọn giọng `auto`, `male` hoặc `female`; hoặc chọn audio giọng mẫu 3–10 giây và
nhập đúng lời nói trong mẫu. Không cần API key. Mẫu giọng được giữ local, không
tải thêm Whisper để nhận dạng. Ngôn ngữ mặc định `vi`; có thể nhập mã khác mà
OmniVoice hỗ trợ. Giọng tự sinh có thể thay đổi giữa các câu; dùng mẫu giọng để
giữ người đọc nhất quán. Audio đầu ra là WAV 24 kHz, dùng chung cache và pipeline
Natural/Legacy đo thời lượng, ghép timeline và xử lý câu vượt khung.

Chuẩn bị từ source hoặc dùng CLI sau khi chuẩn bị trong GUI:

```powershell
uv run --frozen python scripts/prepare_omnivoice.py
uv run --frozen videocaptioner dub video.mp4 --subtitle translated.vi.srt --tts-provider omnivoice-local --voice auto --omnivoice-language vi
```

`--omnivoice-runtime` chọn runtime khác; `--omnivoice-reference-audio` đi cùng
`--omnivoice-reference-text-file` để dùng giọng mẫu. Xem
[pins, giấy phép thành phần và nghiệm thu](docs/dev/omnivoice-local.md).

## Video Editor

Tab `Video Editor` nằm ngay dưới `Kiểu phụ đề`. Chọn `Open` để mở video cùng SRT, hoặc dùng
`Open in Video Editor` từ màn Tối ưu/Dịch phụ đề hay Lồng tiếng. Workspace gồm preview QtMultimedia,
context inspector và timeline `V1 Video / A1 Original Audio / TS1 Subtitle + TTS`.

Editor dùng dark workspace riêng cho cả widget Qt chuẩn và QFluent: empty preview không còn native white
surface, loaded preview dùng thumbnail đầu làm poster trước khi Play, inspector/scrollbar/timeline cùng
palette và command bar tự thu action phụ vào `More` khi chiều rộng hạn chế.

Editor giữ riêng `source_text`, `display_text` và `tts_text`. Các thao tác text/timing, add, split,
delete, drag, resize, voice settings, mute/lock và visual layer đều đi qua undo/redo. Waveform và
thumbnail được tạo ở background và cache theo fingerprint media; timeline chỉ paint cue nằm trong
viewport.

`Save project` ghi atomically `editor-project-v1` cùng một file SRT cạnh project; đường dẫn video/phụ đề
trong JSON là relative, asset phụ như ảnh logo hoặc WAV cache giữ absolute khi nằm khác ổ đĩa, và JSON
không chứa API key. Normal save không persist ASS. Chỉ `Save as ASS` tạo file ASS lâu
dài; Fast Preview/export dùng SRT tạm từ live editor state và tự cleanup.

Nếu Dubbing đang bật, final export dùng Natural/Legacy config hiện có. `Regenerate voice` force-refresh
đúng cache key của cue/group được chọn; Fast Preview dùng ngay WAV đã regenerate và giữ riêng semantics
mute của A1 (audio gốc) với TS1 (subtitle/TTS). Fast Preview phát trong chế độ xem trước riêng và có
`Exit preview` để quay lại video gốc; `Cancel render` dừng được cả preview lẫn export đang chạy.

Tab `Lớp hình ảnh` có sẵn bốn nút thêm layer Blur/Logo/Mask/Text, danh sách layer và bảng thuộc tính
ngay bên dưới. Layer mới phủ đúng vùng đang chọn trên timeline, hoặc 5 giây tính từ playhead nếu chưa
chọn vùng; bảng thuộc tính chỉnh vị trí, kích thước, thời gian, opacity, ẩn/khóa và thuộc tính riêng
theo loại. Layer cũng chọn và kéo/resize được ngay trên track FX1. Nút V ở track header ẩn phụ đề (TS1)
hoặc toàn bộ visual layer (FX1) khi render. Preview và export dùng chung một filter graph, không cần
PySide6 hoặc MPV.

## Các module chính

- `videocaptioner.core.asr`: nhận dạng giọng nói và xuất dữ liệu phụ đề.
- `videocaptioner.core.split`: tách câu phụ đề theo thời gian và độ dài.
- `videocaptioner.core.optimize`: tối ưu nội dung phụ đề bằng LLM.
- `videocaptioner.core.translate`: dịch phụ đề qua LLM/Bing/Google/DeepLX.
- `videocaptioner.core.subtitle`: render phụ đề ASS hoặc nền bo góc.
- `videocaptioner.core.utils.video_utils`: tách âm thanh, đọc thông tin video và ghép phụ đề.
- `videocaptioner.ui`: giao diện desktop.
- `videocaptioner.cli`: giao diện dòng lệnh.

Hướng dẫn dùng module chi tiết nằm ở [docs/MODULE_USAGE.md](docs/MODULE_USAGE.md).

## Build EXE trên Windows

Project đã có file cấu hình PyInstaller:

```bash
uv run pyinstaller VideoCaptioner.spec --clean --noconfirm
```

Build tạo thư mục `dist/VideoCaptioner/` chứa `VideoCaptioner.exe` và các runtime file. Phải phân phối
nguyên thư mục hoặc đóng nó vào installer; không chép riêng file EXE. Chế độ `onedir` tránh bước tự giải
nén hơn 100 MB vào `%TEMP%` ở mỗi lần mở app. Nếu ứng dụng cần gọi FFmpeg bên ngoài, máy đích cũng cần
có FFmpeg trong `PATH` hoặc đi kèm thư mục công cụ tương ứng.

Bản EXE test của user mặc định kèm **`models/` cạnh EXE**, có marker
`portable-models.json`. App tự dùng thư mục này cho weights và runtime Qwen/aligner,
Community-1, OmniVoice, VieNeu; Faster-Whisper executable nằm trong
`models/tools/Faster-Whisper-XXL/`. Để trống các ô runtime để dùng gói đi kèm;
đường dẫn ngoài do user chọn tường minh vẫn được ưu tiên.

`scripts/package_test_models.py` stage từ cài đặt có sẵn bằng các tùy chọn
`--app-dir`, `--faster-whisper`, `--weights-dir`, `--qwen-runtime`,
`--diarization-runtime`, `--omnivoice-runtime`, `--vieneu-runtime`.
Script dùng Python 3.12 đã có, chép cả CPython base và dependency cần thiết để
không giữ `pyvenv.cfg` trỏ về máy dev. Không tải/cài package hoặc model.
Truyền `VC_TEST_MODELS_DIR` trỏ tới thư mục models đã stage khi chạy spec để kèm
payload. Giữ nguyên toàn thư mục ứng dụng khi chuyển ổ; không đưa key/settings,
media hoặc cache job cá nhân vào gói. Xem [nghiệm thu phục hồi ASR và model portable](docs/dev/asr-recovery-2026-09.md).

Để gói test tự có công cụ media, truyền thêm `VC_TEST_MEDIA_TOOLS_DIR` trỏ tới
thư mục **FFmpeg static đã cài**, có cả `ffmpeg.exe` và `ffprobe.exe`. Spec chỉ
bundle hai executable vào `resource/bin` bên trong `_internal`; app dùng cơ chế
tìm tool sẵn có. Không chép toàn bộ AppData, tải công cụ hoặc thay model inventory.
Nếu không truyền biến này, bản build vẫn cần media tools từ cài đặt/PATH phù hợp;
FFmpeg riêng của Faster-Whisper không bảo đảm có FFprobe.

Đặt tên build riêng mà không tạo thêm file spec:

```powershell
$env:VC_BUILD_NAME = 'VideoCaptioner-<label>'
uv run pyinstaller VideoCaptioner.spec --clean --noconfirm
Remove-Item Env:VC_BUILD_NAME
```

`VideoCaptioner.spec` đã bundle các prompt Natural Dubbing và module report dialog. EXE windowed vẫn định
tuyến tham số sang CLI, nên cùng EXE hỗ trợ `dub` và `vieneu` mà không mở GUI.

Gói VieNeu one-app cần runtime/model mutable cạnh EXE. Offline bundle dùng
`scripts/build_vieneu_runtime.py`, `scripts/build_vieneu_one_app.py` và
`installer/VideoCaptioner-VieNeu-OneApp.wxs`. Xem lệnh và layout tại
[`docs/dev/vieneu-one-app.md`](docs/dev/vieneu-one-app.md).

Để giảm file cài ban đầu, web installer dùng ba source trong `installer/`: base MSI được nhúng vào setup,
còn VieNeu runtime/model MSI + CAB được tải qua WiX Burn `DownloadUrl` và verify trước khi cài. Build test
loopback không phải artifact để phát hành cho máy khác; release phải rebuild với một `PayloadBaseUrl`
HTTPS bất biến. Chi tiết nằm trong tài liệu VieNeu one-app ở trên.

## Kiểm thử

```bash
uv run pytest tests/test_cli/ -q
uv run pytest tests/test_thread/test_video_synthesis_thread.py -q
```

Bộ test offline đầy đủ (bỏ các test cần dịch vụ ngoài hoặc API key):

```bash
uv run pytest tests/ -q -m "not integration and not slow and not llm"
```

GitHub Actions chạy `.github/workflows/ci.yml` trên mỗi push/PR: ruff, pyright cho toàn bộ
`videocaptioner/`, kiểm tra đồng bộ bản dịch, test CLI và bộ test offline ở trên trên Ubuntu có FFmpeg và
Qt offscreen.

## Giấy phép

VideoCaptioner sử dụng giấy phép [GPL-3.0](LICENSE).
