# Bài giảng: đã có raw alignment toàn video, chưa đạt SRT

Tiếp tục ASR-S3 / `codex/asr-s3-native`, HEAD và tracking branch **b102ae9**.
Giữ năm tài liệu thay đổi đầu phiên. **Đã căn nốt 20 chunk chưa từng gọi
aligner; đủ raw cho 29/29 chunk. Policy sản phẩm vẫn bị chặn ở năm chunk.**
TXT 4.783 ký tự giữ nguyên. Không nhận dạng lại, commit/push hoặc bắt đầu OCR.

## Phép đo và kết quả

Dùng nguồn trong `ai-lecture-full-20260909/source-preflight.json`, xác minh
hash/mtime/size video và decoded audio identity. Mỗi WAV request khớp SHA-256
với receipt recognition cũ và cùng sample interval; giữ model ForcedAligner
revision `c7cbfc2048c462b0d63a45797104fc9db3ad62b7`, BF16/SDPA, bridge sản phẩm.
Chín alignment đầu lấy nguyên từ review; chỉ gọi model cho chunk index 9–28.
Helper giữ raw của các chunk sau dù chunk trước không qua guard; đây là thu
thập phần timing còn thiếu, không thay hành vi dừng của CLI sản phẩm.

- Host **exit 0 / 14,844 s**, load aligner **8,609 s**.
- **20 request mới / 3,002 s** ở host; receipt worker cộng **2,484 s** inference.
- **0 recognition**, 0 API, 0 download; không dùng thời gian trên làm RTF ASR
  toàn video vì recognition và chín alignment đã được kế thừa.
- Policy hiện tại `qwen-sentence-anchors-v1`: **24/29 chunk** qua geometry và
  kiểm tra năng lượng biên. Đây **chưa là nghiệm thu acoustic** hoặc SRT đầy đủ.

Lỗi đầu tiên của mỗi chunk bị chặn, index tính từ 0, giờ tuyệt đối tính bằng ms:

| Chunk | Interval chunk | Lỗi đầu tiên theo policy sản phẩm |
| --- | --- | --- |
| 8 | 220.850–248.900 | Token biên cuối start=end 228.050; lỗi đã có từ lượt trước |
| 12 | 331.900–360.550 | Token biên đầu start=end 355.260 |
| 26 | 713.100–740.400 | Cue bắt đầu 727.100 trước khi cue trước kết thúc |
| 27 | 740.400–770.250 | Token biên cuối start=end 755.440 |
| 28 | 770.250–771.029 | Token duy nhất có raw local start=end 0 |

Không sửa raw, bỏ phần cuối, clamp, ghép mốc từ provider khác hoặc lấy ranh giới
chunk làm giờ nói. Các lỗi này không chứng minh text sai hay đúng; chưa có
reference audio độc lập/CER cho bài giảng. Chưa chuyển timing sang LLM.

## Phương án chia theo dấu câu đã bị loại

Ở chunk 8, giới hạn 40 ký tự cắt giữa một cụm từ. Thử **một quy tắc chỉ nhận
text**: khi vượt 40 ký tự, ưu tiên dấu phẩy/hai chấm cuối cùng trước giới hạn;
giữ sentence ends và token boundaries. Không đọc timestamp để chọn nhóm, không
thay guard hoặc áp lựa chọn riêng cho từng cue lỗi. Contract được ghi trước
lượt replay, tên thử nghiệm `qwen-clause-anchors-v2`.

Replay chín raw cũ giải phóng chunk 8; guard vẫn chặn end vượt đoạn 60 s 30 ms.
Nhưng khi áp cùng quy tắc lên toàn bộ raw đã hoàn tất, **vẫn 24/29 chunk pass**:
giải phóng chunk 8 và 27, đồng thời làm chunk 13 và 15 bị chặn bởi token biên
zero-duration; chunk 12, 26, 28 vẫn lỗi. Không chọn policy theo từng chunk hoặc
tiếp tục đổi dấu câu/giới hạn để tìm tổ hợp pass.

**Không tích hợp phương án này.** Bản thử được giữ riêng trong evidence;
`sentence_timing.py` đã khôi phục đúng từng byte từ snapshot đầu phiên.
Source app, policy mặc định, review cũ, runtime, cache và EXE không thay đổi.
Không xuất thêm SRT candidate. Kết quả không cung cấp một fix acoustic cho
zero-duration/overlap, và việc đổi nhóm text không giải quyết được toàn video.

## Evidence, preservation và bước tiếp tục

Dưới `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/cue-clauses-20260909/`:

- `source-before/`, `source-before.json`: chín file chạm/đối chiếu đầu phiên,
  gồm đủ năm tài liệu kế thừa. `sentence_timing_candidate.py` là bản thử đã loại.
- `partition-contract.json`, `raw-replay.json`: quy tắc text và replay cũ.
- `completion-contract.json`, `chunk-09.raw.json` đến `chunk-28.raw.json`,
  receipt từng chunk, `all-raw.json`, `completion-result.json`: toàn bộ raw,
  audio hashes, offsets, model receipt và thời gian. Chín raw đầu kế thừa nguyên
  review. Không đưa output này vào cache validated của sản phẩm.
- `boundary-failures.json`, `validation.json`: vị trí lỗi đầu tiên mỗi chunk,
  so sánh hai policy, `accepted=false`, `integration_allowed=false`.
  Hai mươi chunk chưa căn trong review cũ dùng ID placeholder cho cả chunk;
  raw mới giữ index token riêng, **không giả coi placeholder cũ là word ID**.
- `preservation.json`: **72 file** giữ nguyên hash/mtime trong phép đo.
  Sau khi khôi phục source, validator xác nhận source bằng snapshot và các
  file còn lại vẫn nguyên vẹn; worker PID đã đóng, GPU lease đã thả.

Validation offline đối chiếu đủ text, raw/receipt, audio hashes, legacy policy
trên 29 chunk và preservation pass. Không chạy lại unit/Ruff/pyright/translations
hoặc build vì code sản phẩm cuối phiên không đổi; kế thừa 142 test/ResumeGuard.
Chưa GUI/EXE, quality reference, SRT/LLM, sửa generation loop, tải model mới qua
mạng hoặc GUI HTTP cancel/resume.

**Lượt sau dùng toàn bộ raw/receipt này; không gọi lại 20 alignment đã xong hoặc
recognition bài giảng.** Không tiếp tục chỉnh cách nhóm cue để che lỗi. Timing
cần xử lý các dự đoán biên zero/overlap dựa trên audio và có kiểm định độc lập;
chưa có phương án được chấp nhận trong phiên này. Quality/stall và tải model/GUI
HTTP resume vẫn sau timing. OmniVoice Studio đã được giữ trong plan sau ASR,
bên cạnh VieNeu Local; chưa triển khai, OCR tiếp tục dừng.

Phiên này chỉ bổ sung báo cáo này và cập nhật `status.md`, plan ASR, prompt
tiếp tục. Hai báo cáo chưa commit từ các lượt trước giữ nguyên. Git cuối phiên
có sáu tài liệu thay đổi tổng cộng; không có thay đổi code/test sản phẩm.
