# S5.2 — liên kết recording và nghiệm thu gateway hybrid

Baseline `27be883`, code S5.1 `8599965`, nhánh `codex/asr-s3-native`. Giữ nguyên model/pin,
dependency Qt, runtime S5/S5.1 và các artifact cũ. Không chọn engine mặc định hoặc mở S6.

## Liên kết audio khi mở lại

JSON mới có `audio_identity` typed tùy chọn ở cấp tài liệu: policy
`pcm-s16le-mono-16000-v1`, SHA-256 của toàn bộ PCM16 little-endian mono 16 kHz và số sample.
Không lưu tên/path file, endpoint, key hoặc transcript trong identity. Dùng FFmpeg chọn audio
track đầu (`0:a:0`), cùng định dạng recognition/alignment/local diarization; hash giữ cả sample
đuôi chưa đủ một millisecond. Fingerprint không phải chứng nhận chất lượng hoặc độ phủ ASR.

Đổi tên/di chuyển file hoặc đổi container lossless nhưng giữ cùng PCM vẫn khớp. Recording khác
dù cùng duration bị từ chối. Nén lossy lại, đổi audio track hoặc giải mã cho PCM khác sẽ mismatch;
không fuzzy match, tự nới tolerance hoặc liên kết lại. Với video nhiều track, dùng đúng bản audio
của track đã chọn khi nhận dạng. Fingerprint không chứng minh video hình ảnh giống nhau.

Qwen và API text-only lấy identity từ PCM toàn job trong RAM trước chia chunk. Đường ứng dụng
Whisper/native dùng snapshot file riêng trước nhận dạng; native review nhận identity của chính
snapshot. Preflight text-only vẫn kiểm tra ngôn ngữ/runtime trước audio IO. JSON kết quả/review,
table export/handoff, editor normal save, split/optimize/translate giữ identity và cue/token IDs.
Không đổi `asr-native-v1`, `editor-project-v1`, `local-asr-review-v1` hay `asr-review-v1`.

`local-diarize` so identity sau decode, **trước đọc cache, preflight/nạp model hoặc inference**.
Sai nguồn: chọn lại audio gốc; không có output partial, không nhận dạng/upload lại. Cache
diarization v2 gồm identity/trạng thái nguồn bên cạnh PCM/model/policy/association; cache cũ
không được dùng như bằng chứng liên kết mới. Policy overlap/union/coverage ≥80% không đổi.

JSON/SRT/review cũ vẫn mở được. Khi thiếu identity, app báo **chưa xác minh recording** và không
tự nâng dữ liệu legacy thành đã xác minh sau một lượt diarization. SRT vẫn không giữ metadata;
giữ JSON nếu cần tiếp tục review. Identity chỉ có tác dụng khi còn được giữ trong file.

## Review tại máy

Trong **Mở bản review ASR**, bấm **Chọn âm thanh gốc…**. Kiểm tra FFmpeg/hash chạy ở QThread,
không nạp model hoặc gọi API. Sai nguồn hoặc kiểm tra chưa xong chặn export trong dialog; chọn
đúng nguồn để tiếp tục. Đóng dialog hủy hợp tác và giữ worker đến khi cleanup, bỏ signal cũ.
Mở JSON đơn thuần không có nghĩa đã kiểm tra audio. Sửa timing vẫn qua CommandStack/undo/redo.

```powershell
uv run --frozen videocaptioner asr-review recognition.asr-review.json `
  --audio original.wav -o reviewed.json

uv run --frozen videocaptioner local-diarize reviewed.json --audio original.wav `
  --runtime build/S51-Community1-Runtime-20260907 -o speakers.json
```

`--audio` là tùy chọn của `asr-review`; bỏ tùy chọn này vẫn validate/export timing tại máy,
giữ fingerprint để bước sau kiểm tra và báo chưa kiểm tra audio ở lượt mở này. Mismatch trả
exit 5 trước save/export. Không sửa trực tiếp raw/checksum để vượt guard.

`pending_diarization` được giữ qua JSON/editor và chỉ xóa sau diarization hoàn tất. Review timing
không trở thành full hybrid success. GUI/CLI báo rõ cần bước speaker. Pending lưu trong review
gốc vẫn giữ nguyên kể cả sau khi xuất một kết quả mới; không overwrite review gốc.

## Gateway text-only và runtime đã cài

Có thể chọn tường minh aligner của runtime Qwen S5 bằng `--qwen-runtime` / `local_asr.runtime_root`.
Model/policy vẫn là ForcedAligner S2 đã pin; không chạy Qwen recognition thay gateway. Khi không
chọn root S5, đường runtime alignment S2 cũ vẫn giữ nguyên. Không move/copy venv hoặc tự tải model.

```powershell
uv run --frozen videocaptioner transcribe public-zh.wav --asr whisper-api --language zh `
  --whisper-provider videocaptioner --whisper-model gpt-4o-transcribe `
  --qwen-runtime build/S5-Qwen-Runtime-20260907-R2 --local-diarize `
  --diarization-runtime build/S51-Community1-Runtime-20260907 -o hybrid.json
```

Health Community-1 và aligner phải pass trước upload. API text-only giữ recognition toàn bộ
chunk trước alignment; timing/acoustic failure giữ raw, chunk offsets, tail, token IDs, identity
và pending trong `local-asr-review-v1`. Chunk chưa align có timing missing; không tạo timing giả.
Text rỗng trên audio có năng lượng được giữ là recognition chưa đầy đủ, không thể biến thành
success chỉ bằng mở lại hoặc sửa timing. Cancel không publish review/success và luôn đóng runtime.

## Bằng chứng source và giới hạn

User nhập key gateway qua password, giữ trong RAM phiên nghiệm thu. Dùng đúng preset
`videocaptioner`, endpoint `https://api.videocaptioner.cn/v1`, không đọc cache và
[audio Trung public Qwen 4,204 s](https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_zh.wav).
Catalog HTTP 200 có hai model được yêu cầu; catalog và inference là các gate riêng.

| Actual CLI/core source pipeline | Kết quả |
| --- | --- |
| `whisper-1` → Community-1 → JSON/SRT | exit 0; 1 cue, 0–4000 ms, 1 speaker; 43,390 s |
| `gpt-4o-transcribe` → strict alignment → Community-1 → JSON/SRT | exit 0; 1 cue, 400–3680 ms, 13 token IDs, 1 speaker; 70,859 s |

Cả hai giữ cùng identity **67.263 sample**, mở JSON và parse SRT đủ cue, pending false. Timing
Whisper là segment do API trả, không có word IDs để suy thêm. GPT request text mất 3,188 s;
diarization trong hai job mất 12,063/10,110 s, gồm load/verify. Đây là smoke nhỏ, không so tốc độ
model hoặc suy chất lượng ngôn ngữ/speaker. Model nêu trên là model được gửi trong request;
app không thể kiểm chứng nội bộ routing của gateway.

Scribe không có credential riêng trong phiên: chưa probe/inference. Không gọi lại Soniox hoặc
mini để vượt parser/HTTP 429. **Scribe online, phồn thể strict, speaker accuracy và xưng hô do
người đọc chấm** vẫn chưa nghiệm thu. Không mở corpus S6, auto voice, commit/push hoặc release.
Gate offline, artifact EXE và manifest cuối được ghi tại phần bàn giao S5.2 trong implementation.

## Gate EXE S5.2

Artifact mới `dist/VideoCaptioner-ASR-S52-Review-20260907-Final/`, phân phối nguyên onedir.
PyInstaller exit 0; 6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream.
EXE **31.161.859 byte**, local **2026-09-07 19:11:44**, SHA-256
**`457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649`**.
**218 module / 39 resource** so với source pass; resource gồm TS và script sidecar dạng data.
Không bundle GPU libraries. Onedir trước GUI: **580 file / 237.667.163 byte**.

Nghiệm thu runtime trên bản sao binary/resources riêng, cache ban đầu trống. Key truyền qua
named pipe local với ACL chỉ current user, chỉ tồn tại trong RAM; reader/owner đã thoát.

| Gate từ EXE | Kết quả |
| --- | --- |
| GPT gateway → strict alignment → Community-1 → JSON/SRT | exit 0; 58,312 s; 1 cue 400–3680 ms, 13 token IDs, 1 speaker, identity khớp source, pending false |
| Whisper gateway → Community-1 toàn pipeline | **exit 5 / HTTP 429**, 39,187 s; không output partial. Không nghiệm thu thành công gate này |
| `local-diarize` từ timed Whisper JSON của lượt source, đúng audio | exit 0; 10,157 s; identity giữ nguyên, pending false; không ASR/upload lại |
| `local-diarize` từ SRT legacy | exit 0; 9,609 s; báo unverified, không tự thêm identity |
| JSON + audio sai cùng duration + runtime không tồn tại | exit 5 / mismatch trước runtime, 0,406 s; không output |
| Review tổng hợp timing lỗi → override → reopen | exit 5 rồi 0; giữ identity, IDs, edited và pending; sai audio exit 5; không upload |

HTTP 429 được xử lý bằng policy retry hữu hạn S1 hiện có (tối đa 3 attempt); không chạy thêm
lệnh transcribe để ép pass, không gọi mini/đổi provider. Thời gian là toàn command, không benchmark.
Source Whisper đã pass không thay thế gate Whisper API từ EXE đang thiếu.

GUI artifact mới sống **25,047 s**, 1 Qt window, RSS **101.412.864 byte**, WM_CLOSE → exit 0,
0 process còn lại, binary hash không đổi. **Gate log teardown chưa sạch:** khi đóng sau thông báo
cập nhật, QFluentWidgets báo `BottomInfoBarManager has been deleted`. Bản sao riêng S5.1 Final
cũng tái hiện cùng lỗi, sống 25,047 s / exit 0 / không process sót. Đây là lỗi đã có trước S5.2;
chưa xác định quan hệ với crash SIP của test Settings, không đổi framework hoặc gọi nó đã sửa.

Review tiếng Việt đã xem render trên Qt Windows native; worker Qt thực kiểm tra audio public bằng
FFmpeg pass. Render Windows offscreen không vẽ chữ nên không dùng làm bằng chứng layout.
Các khoản còn mở trước nghiệm thu tiếp: Whisper API từ EXE sau HTTP 429, Scribe online,
Qt/SIP/InfoBar teardown, phồn thể strict, speaker accuracy và xưng hô bằng người đọc. Dừng review.
