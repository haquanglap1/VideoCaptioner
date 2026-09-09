# Hoàn thiện ASR theo mục tiêu speech-to-text

## Hoàn tất các session triển khai và GUI của lượt tiếp tục

[Báo cáo cuối](../dev/dubbing-review-resume-2026-09.md) và
[bảng session](asr-completion-sessions-2026-09.md) ghi kết quả R6: core review/
resume, GUI sửa/lưu/mở kế hoạch và cache riêng, downloader phục hồi lỗi, Unicode
entry point và layout synthesis. GUI chạy xuyên các tab với phụ đề/WAV có sẵn,
xuất track song ngữ đúng thứ tự; source, build và media gates được ghi riêng.
Các ghi chú “chưa triển khai review/resume” phía dưới là lịch sử. Bản bài giảng,
gated/người nói và quality/RTF giữ phạm vi đã chốt; không lặp inference/benchmark.

## Yêu cầu hiện tại: hoàn thiện theo session rồi commit/push

User đã yêu cầu tiếp tục hoàn thiện plan và commit/push sau khi kiểm tra.
[Bảng session](asr-completion-sessions-2026-09.md) là trạng thái điều phối hiện tại:
core review/resume, GUI sửa lời đọc, downloader OmniVoice và tích hợp/EXE/Git.
Quyền mới thay các ghi chú chưa có quyền commit/push trong lịch sử bên dưới.
Giữ bản lồng tiếng đã được chấp nhận, không mở lại benchmark sâu hoặc OCR.

## Rà luồng GUI lồng tiếng sau snapshot f510846

[Báo cáo handoff](../dev/dubbing-gui-handoff-2026-09.md) xác định khoảng trống
review/tiếp tục: GUI chưa chuyển kế hoạch wording/report/cache sang editor.
Checkpoint và đủ 151 WAV cuối còn nguyên. Đã sửa lỗi riêng khi tắt dubbing:
synthesis nhận SRT hiển thị thay vì SRT TTS; 139 test và Ruff/pyright/sync pass.
EXE GUIResume chưa rebuild, còn hành vi cũ. Ca nghiệm thu tiếp theo trong báo
cáo tập trung giữ kế hoạch, sửa đúng nhóm và reuse cache; chưa triển khai tính
năng resume, không mở lại inference/render bài giảng. Chưa commit/push.

## Tiếp tục được user chọn: GUI và tải model

Đã nghiệm thu phạm vi tải model ASR trên máy này, xem
[báo cáo](../dev/asr-gui-download-2026-09.md): source GUI tải mới Qwen 0.6B,
ForcedAligner HTTP cancel/resume nhận Range/206; EXE GUIResume tiếp tục cùng
file, hủy HTTP thật, resume/verify/health/reuse và đóng sạch. Sửa trạng thái hủy
và tiến độ partial vượt MAX_PATH; 150 test/Ruff/pyright/sync pass.

Các gate này thay trạng thái “tải mới/GUI HTTP cancel-resume chưa đo” bên dưới
cho **Qwen 0.6B và ForcedAligner trên máy này**. Không bao gồm cài máy khác,
OmniVoice GUI downloader, model gated hoặc toàn workflow video qua GUI/EXE.
User chưa yêu cầu chỉnh lại bản lồng tiếng đã chốt; OCR vẫn dừng.

## Chốt phạm vi hiện tại — user phản hồi “tạm ổn”

**Luồng thực tế trên bài giảng đã hoàn tất; chưa đóng toàn bộ nghiệm thu sản phẩm.**
User chấp nhận bản hiện tại ở mức “tạm ổn” và yêu cầu dừng chỉnh thêm.

- [x] ASR thực dụng Qwen + Whisper dự phòng, xuất đủ 180 cue có timing câu.
- [x] Dịch LLM đủ 180 cue sang tiếng Việt, giữ timestamp/provenance.
- [x] Tích hợp OmniVoice Local cạnh VieNeu; runtime/model và source/EXE đã có
  các gate được ghi riêng trong báo cáo, không đồng nhất cached check với inference.
- [x] Xuất toàn bài 12 phút 51 giây: 151 nhóm, tốc độ 1,00×, không chồng lời,
  độ trễ lớn nhất 2284 ms. User chấp nhận tạm bản đã giao.

Trạng thái/artifact cuối: [báo cáo toàn bài](../dev/full-lecture-dubbing-2026-09.md).
Bản cuối dùng helper nạp checkpoint và hai câu được Codex rút riêng; chưa là bằng
chứng rằng toàn bộ trường hợp dài đều tự hoàn tất qua một lượt bấm GUI.

Các mục còn chưa nghiệm thu của plan sản phẩm rộng hơn: cài mới model thật qua
mạng và GUI HTTP cancel/resume; toàn workflow GUI/EXE từ đầu đến cuối; người nói
là phần bổ sung riêng. Mục tiêu chất lượng/RTF trên corpus khó chưa được chứng
minh đạt; theo ưu tiên thực dụng của user, không tự mở lại vòng benchmark để đóng
các mục đó. OCR vẫn dừng. Không commit/push/release khi chưa có yêu cầu mới.

Các mục bên dưới ghi lịch sử triển khai và tiêu chí cũ; không dùng ghi chú “chưa
lồng tiếng/OmniVoice chưa triển khai” ở lịch sử để khởi động lại phần đã xong.

## Lịch sử: ưu tiên nhịp lồng tiếng đều

User không thích preview đổi tốc độ từng nhóm. Đã đổi sang một nhịp chung,
ưu tiên 1,00× và LLM rút riêng lời đã đo quá dài. Preview mới giữ 1,00×, không
overlap, trễ lớn nhất 2,12 s trong giới hạn 2,5 s; một group dùng rewrite thật,
các group khác giữ lời/audio gốc. [Báo cáo](../dev/sequential-dubbing-2026-09.md).
Không coi preview tăng tốc cục bộ là được user chấp nhận. Chưa nghiệm thu nghe
hoặc lồng tiếng toàn bài giảng; không chạy lại ASR/dịch/những TTS đã complete.

## OmniVoice đã được triển khai theo link user xác định

User xác nhận `https://github.com/k2-fsa/OmniVoice`; đã thêm **OmniVoice Local**
bên cạnh VieNeu Local. Runtime/model riêng đã chuẩn bị thật, có mẫu giọng Việt
và preview lồng tiếng 30 s. [Báo cáo triển khai](../dev/omnivoice-local.md) ghi
pins, giấy phép thành phần, UI/CLI, cache/hủy, build và các giới hạn còn lại.
Các mục “OmniVoice là hạng mục tương lai/chưa xác minh” bên dưới là lịch sử.
Chưa chấm chất lượng giọng hoặc lồng tiếng toàn bài giảng; ưu tiên phản hồi của
user trên mẫu giọng/preview, không quay lại benchmark ASR/dịch.

## Đã triển khai hướng được user duyệt: Qwen + Whisper dự phòng

[Báo cáo](../dev/asr-practical-sentences-2026-09.md): policy câu thực dụng dùng
biên câu mà không ép duration của từng token. Vùng lỗi dùng cả chữ và timing của
Whisper đã cài; original Qwen/raw vẫn giữ trong review. Legacy review/word strict
không đổi. CLI/GUI báo cue dự phòng, cache riêng, deadline/hủy và đóng GPU tuần tự.

Bài giảng đã xuất SRT **180 cue (164 Qwen, 16 Whisper)**. Kế thừa Qwen/aligner;
chỉ Whisper vùng 57,929 s cuối, một inference thành công 26,234 s. Source CLI và
frozen CLI cached đều exit 0; SRT giống nhau, editor adapter nhập đủ. Gate kỹ thuật
254 pass/2 skip, Ruff/pyright/sync pass. Không yêu cầu benchmark thêm để tăng %.
Các mục “SRT bài giảng còn bị chặn” phía dưới là lịch sử trước thay đổi này.

## Ưu tiên mới của user: mức dùng thực tế như Whisper (2026-09-09)

User chấp nhận nhận dạng tương đối khoảng **80–90%**, không yêu cầu 100%; ưu tiên
hoàn thiện luồng sử dụng thay vì tiếp tục kiểm thử Qwen quá sâu. Đây là mức kỳ vọng,
không phải kết quả đo đã đạt trên mọi video hoặc phép quy đổi trực tiếp từ CER.
Mục này thay thế các tiêu chí nghiệm thu cũ bên dưới khi có mâu thuẫn; giữ nguyên
kết quả và trạng thái của các phép đo lịch sử.

- Chốt theo phụ đề câu/đoạn dùng được: text có thể cần sửa, timing tương đối bám
  lời nói; không bắt từng token hay từng onset vượt đối chứng acoustic mới cho
  phép hoàn thiện sản phẩm. Sai số timing nhỏ là vấn đề chất lượng để review.
- Vẫn xử lý lỗi chức năng: treo/lặp vô hạn, mất chunk, báo complete khi thiếu,
  output không mở được hoặc timeline hỏng. Giữ transcript/raw và dữ liệu user.
- Dừng sweep model/dtype/window, ablation, CER toàn corpus và thử lặp cùng input.
  Dùng raw/cache bài giảng đã có để triển khai timing câu thực dụng; chỉ kiểm tra
  phần sửa và một luồng xuất SRT/mở phụ đề thật, sửa tiếp khi có lỗi cụ thể.
- Không lấy việc chấp nhận sai số để đổi các receipt cũ thành pass. Source hiện
  vẫn chặn năm chunk của bài giảng; cần sửa hành vi trước khi báo Qwen SRT dùng được.
- OmniVoice Studio tiếp tục sau ASR, bên cạnh VieNeu Local; OCR vẫn dừng.

## Cập nhật: đã hoàn tất raw alignment bài giảng

[Báo cáo mới](../dev/asr-lecture-complete-alignment-2026-09.md): chỉ căn nốt 20
chunk chưa gọi aligner; đủ raw **29/29**, 0 recognition, giữ nguyên TXT 4.783
ký tự. Policy sản phẩm qua geometry/energy ở **24/29**, còn lỗi index 8, 12,
26, 27, 28. Chưa acoustic acceptance hoặc SRT/LLM đầy đủ.

Quy tắc thử ưu tiên dấu phẩy trước cap 40 cũng chỉ qua 24/29, có hai regression;
đã loại và khôi phục source. Không chọn policy theo chunk lỗi hoặc thử tiếp
giới hạn/dấu câu để tích pass. Dùng `cue-clauses-20260909/all-raw.json` cùng
receipt/hash, không nhận dạng/căn lại các chunk đã xong. App/cache/runtime/EXE
không đổi; 142 test/ResumeGuard được kế thừa. Thứ tự timing → quality/stall →
download/GUI HTTP resume giữ nguyên; OmniVoice sau ASR, VieNeu giữ lại, OCR dừng.

## Cập nhật bài giảng user cung cấp trong phiên tiếp tục

[Báo cáo](../dev/asr-lecture-onset-2026-09.md): toàn video 12 phút 51 giây đã
hoàn tất TXT 4.783 ký tự; 29 chunk, hai cache reuse và 27 request mới đều EOS.
CLI SRT vẫn exit 5: biên token `token-001149` tại 228.050 ms có zero duration;
20 chunk sau chưa alignment. Kế thừa recognition/cache, không chạy lại từ đầu.
Chưa reference/CER hoặc timing/LLM acceptance. Đoạn 60 s riêng cũng fail vì
end vượt điểm cắt 30 ms. Không clamp, nới guard hoặc tự gộp cue theo lỗi.

Phép đo acoustic mới dùng lexical probability khi tắt dần audio cũng bị loại;
giữ raw trong `acoustic-token-onset-20260909/`, không thử lại bằng cách đổi
threshold. App/runtime/EXE không đổi; 142 test và ResumeGuard được kế thừa.
Thứ tự timing → quality/stall → model download/GUI HTTP resume giữ nguyên.
OmniVoice Studio sau ASR, VieNeu Local giữ lại, OCR dừng.

## Cập nhật từ b102ae9: native timestamp chưa qua đối chứng audio

[Báo cáo mới](../dev/asr-native-timestamp-control-2026-09.md): timestamp-token
head với prefix text Qwen giữ đủ chữ và đưa hai onset tới 44.150 / 49.150 ms.
Tuy nhiên, đối chứng chèn +1 s trong khoảng nghỉ có **6/8 biên lệch 500 ms**
so với kỳ vọng; tolerance 250 ms đã ghi trước inference. Không nới tolerance,
ghép mốc với DTW cũ hoặc tích hợp candidate. Giữ đầy đủ raw logits, hai receipt
lỗi helper và lần resume; không lặp native-prefix/gap control cùng cấu hình.

Timing/SRT/LLM vẫn mở. Không đổi code app/cache/runtime/EXE hoặc dịch; kế thừa
142 test/ResumeGuard. Sau timing mới xử lý quality/stall rồi tải model thật qua
mạng và GUI hủy/tiếp tục. Parent 88.950 ms đã EOS và ba trace loop giữ nguyên;
OmniVoice Studio sau ASR, OCR dừng.

## Cập nhật mới nhất: direct alignment và generation trace

[Báo cáo](../dev/asr-direct-alignment-stall-2026-09.md): đã căn trực tiếp text
Qwen cached bằng Whisper.align trên chunk cuối, không mượn timing transcript
khác. SRT thử nghiệm 9 cue đủ nguyên chữ, geometry/energy/roundtrip pass nhưng
onset còn chứa khoảng nghỉ; **chưa acoustic acceptance, chưa tích hợp vào app**.
Không lặp sparse slots/crop, không sửa raw hoặc nới guard. Wheel CT2 được giữ
riêng trong evidence; không tải model hoặc thay dependency project/runtime.

Mask recognition chỉ trên bốn request stall giúp một request có EOS (5,687 s),
ba request còn lặp cặp token hàng trăm lần. Một candidate ghép parent mới với
cache cũ giảm CER clip riêng 61,44% xuống 60,21%, chưa là quality/model-wide pass.
Giữ cả raw IDs và output parent đã complete; không replay chúng. Candidate chưa
vào bridge sản phẩm. Kế thừa 142 test/ResumeGuard; không test/build mới. Gate tải
model thật qua mạng và GUI HTTP cancel/resume vẫn mở. Timing Qwen tiếp tục ưu tiên;
OmniVoice Studio sau ASR, OCR dừng.

## Bổ sung mới nhất: generation budget và GUI resume

[Báo cáo tiếp tục d2dc518](../dev/asr-stall-resume-2026-09.md): hai thử nghiệm
timing mới vẫn fail, không tích hợp. Worker giới hạn token theo audio, bắt buộc
EOS; bốn request stall giảm từ ~181 s xuống 51,672–83,671 s, giữ process cho retry.
Cache cũ cho cùng TXT trên hai clip khó/stress, chưa cải thiện CER. GUI native
đã hủy verify model thật rồi tiếp tục/reuse cùng root; tải mới qua mạng chưa đo.
142 test liên quan pass, Ruff/pyright/sync pass. Không đổi ưu tiên timestamp câu
Qwen, không bắt đầu OmniVoice Studio/OCR, không commit/push.

## Cập nhật triển khai 2026-09-09 từ bàn giao d2dc518

- Đã thêm policy cue `qwen-sentence-anchors-v1` và giữ strict word khi được yêu cầu.
  Replay raw cũ giải phóng 11/32 chunk được chọn, nhưng chưa clip hoàn chỉnh nào qua
  SRT. Đo mẫu user với cửa sổ nhận dạng mới vẫn cần review; không tính TXT là pass.
- Core GUI/CLI tự chuẩn bị Qwen/aligner theo nhu cầu, xác minh file và dùng lại model
  đã cài. Có staging riêng, OS lock, hủy/resume và progress MiB. Không thay runtime
  cũ; dependency Qt/lock/model revision/default engine giữ nguyên. Cài mới thật qua
  mạng chưa được đo vì model phù hợp đã có; fixture tải nhỏ/activation đã kiểm tra.
- Nhận dạng giới hạn request 30 s; không có silence thì cắt ở năng lượng thấp gần
  cuối, giữ tất cả sample. Timeout retry một lần ở <=15 s, chunk thành công giữ cache.
  Cả bốn clip lỗi cũ và stress nay hoàn tất TXT. CER trên bốn clip khó 33,91–61,44%;
  stress 44,27%, còn xa mục tiêu quality. Stress 432,42 s tổng, 391,67 s request gồm
  một timeout, 22,34 s load. RTF request 0,249; bỏ load nhưng giữ điều phối là 0,261;
  tổng wall RTF 0,275. Chưa đạt mục tiêu <=0,25 cho toàn bước sau load.
  Không thay bảng common-28 phía dưới.
- Lỗi optional diarization không chặn hoặc làm mất recognition/timed subtitle.
  JSON giữ pending; không gán speaker cho từng chữ khi chỉ có cue timing.
- Có EXE onedir mới; chi tiết build/smoke/workflow và các gate chưa đạt nằm trong
  [báo cáo](../dev/asr-sentence-preparation-2026-09.md).

**ASR sản phẩm chưa nghiệm thu; OCR vẫn dừng. Không commit/push thay đổi mới.**
Các mục “chưa sửa” bên dưới mô tả snapshot bàn giao trước thay đổi này; dùng báo cáo
mới làm trạng thái triển khai hiện tại.

Ngày 2026-09-09, checkout ASR-S3, nền `669c0da`. User chốt ưu tiên: **nhận dạng
âm thanh đúng, nhanh và ổn định; phân biệt người nói là bổ sung**. Dịch tiếp tục
dùng gateway/gpt-5.6-terra đã chọn. Timestamp từng chữ không còn là điều kiện để
trả transcript hoặc công bố recognition thành công. OCR vẫn tạm dừng.

**Bổ sung mới nhất của user: đầu ra làm phụ đề vẫn cần timestamp câu/đoạn.**
LLM cần giữ các mốc đã đo từ audio khi dịch/chia/gộp cue; không thể suy chính xác
thời điểm lời nói chỉ từ văn bản. TXT dưới đây là đầu ra khi chọn chỉ lấy text và
bản bảo toàn khi timing thất bại, **chưa thay thế nghiệm thu SRT/ASS**.

## Đã xử lý trong lượt này

- Qwen có đường `recognize()` riêng. GUI chọn TXT và CLI xuất `.txt` chỉ chạy
  model nhận dạng; không tìm, verify, nạp hoặc gọi aligner/Community-1.
- Luồng xuất phụ đề chạy recognition trước khi kiểm tra aligner. Nếu aligner
  thiếu, sai manifest, lỗi load/inference hoặc trả span không hợp lệ, text hoàn
  chỉnh còn trong review và được GUI/CLI lưu thêm thành TXT cạnh output dự kiến.
  Nếu tên TXT đã có, dùng hậu tố số qua exclusive-create; giữ file của user.
- GUI nhận dạng riêng báo hoàn tất TXT, không ép mở editor sửa timestamp. GUI
  pipeline phụ đề vẫn dừng bước cần timing. CLI yêu cầu TXT trả exit 0; CLI yêu
  cầu SRT/ASS/JSON timed chưa tạo được output giữ exit 5 và báo vị trí TXT riêng.
  Nhờ đó script `process` không dịch/render một SRT cũ hoặc không tồn tại.
- Giữ text nguyên dấu/chữ/thứ tự. Không chuyển chunk boundaries thành timestamp
  lời nói, sửa raw span hoặc trả một `ASRData` có giờ giả. Recognition lỗi/hủy/
  thiếu chunk không được biến thành bản hoàn chỉnh. TXT không chứa speaker metadata.
- Không đổi checkpoint, frontend, chunk size, timeout, engine mặc định, cache
  recognition hoặc cấu hình LLM. Các lỗi nhận dạng/file dài đã đo vẫn cần xử lý.

CLI:

```powershell
uv run --frozen videocaptioner transcribe clip.wav --asr qwen-local --language zh `
  --qwen-model qwen-1.7b --qwen-runtime path/to/installed-runtime -o transcript.txt
```

GUI: Nhận dạng → chọn Qwen → định dạng TXT → bắt đầu. Model nhận dạng vẫn phải
đã cài; tự tải lúc bắt đầu chưa có, nằm ở bước tiếp theo. Nếu chọn SRT và timing
thất bại, bản TXT được giữ và review vẫn mở lại được bằng chức năng review hiện có.

## So sánh bằng dữ liệu đã đo

Nguồn: [S6](../dev/asr-s6-results-2026-09.md),
[sentence/stress](../dev/asr-s6-followup-2026-09.md) và
`VC-ASR-Completion-20260908-140534/reports/s6-measurements.json` trong evidence local.
Không chạy inference hoặc chấm CER lại để lập bảng này.

**CER là tỷ lệ lỗi ký tự, thấp hơn tốt hơn; không phải phần trăm audio nhận đúng.**
Tập so sánh chung gồm 28 clip meeting tiếng Quan thoại, 17.413 ký tự tham chiếu.
Giữ script/case/số và lời nói chồng; đây không phải cpCER chính thức của corpus.

| Model/config đã đo | CER cùng 28 clip | Transcript đầy đủ trên 32 clip | Nhận xét thực tế |
| --- | --- | --- | --- |
| Qwen 1.7B | **21,04%** | **28/32** | Chữ tốt nhất trong ba cấu hình đã đo; còn một timeout và ba lỗi chia audio |
| Qwen 0.6B | **22,00%** | **28/32** | Gần 1.7B trên meeting, dùng ít VRAM hơn; cùng bốn clip chưa hoàn tất |
| Faster-Whisper large-v3, word | **36,74%** | **32/32** | Hoàn tất recognition đủ corpus; lỗi timing cũ ghi riêng |
| Faster-Whisper large-v3, sentence | **36,78%** | **32/32** | Có biên câu native; chữ gần như word mode, chưa cải thiện quality |

Về timestamp trong app: Faster-Whisper có sentence/word timing; Qwen 0.6B/1.7B
nhận dạng text và cần ForcedAligner để tạo thời gian. API tùy model/profile:
Whisper có timed response, một số model transcription chỉ có text. Không phải
mọi model có timestamp native hoặc dùng được cho phụ đề ngay khi nhận dạng xong.

Trong report S6, trường `completed_valid_stage_output=5` của Faster-Whisper là
output **qua timing**, không phải số transcript nhận dạng thành công. Không dùng
trường đó để mô tả reliability speech-to-text; recognition có text ở 32 clip.

Clip user 60 s: CER chẩn đoán cũ Qwen 1.7B **6,38%**, Faster-Whisper **7,45%**,
Qwen 0.6B **12,77%**. Reference này là bản chép caption đã có, chưa kiểm định audio
độc lập; không dùng một clip để tuyên bố chất lượng mọi phim/phương ngữ.

Tốc độ trên RTX 5070 12 GB của lượt đo:

- 28 clip Qwen hoàn tất dài 105–150 s: median thời gian mỗi clip sau bước load
  là **17,032 s (1.7B)** và **17,008 s (0.6B)**. Chênh lệch này quá nhỏ để kết
  luận model nào nhanh hơn. Thời gian gồm điều phối/chunk, chưa phải kernel-only.
- Peak CUDA allocated trong receipt load: **4.698.543.616 byte (1.7B)** và
  **1.876.073.984 byte (0.6B)**; đây không phải toàn bộ VRAM/NVML của máy.
- Wall time batch Qwen 1.7B khoảng **689,4 s**, 0.6B **706,7 s**; Faster-Whisper
  word **1.365,8 s**. Batch Qwen có failure/restart, còn FWW gồm word timestamp;
  không lấy tỷ số này làm speedup recognition thuần hoặc dự báo tốc độ máy khác.
- Stress 26,23 phút: Qwen chưa hoàn tất; Faster-Whisper có text nhưng CER thô
  **64,94%**, có đuôi chưa nhãn. Có output chưa chứng minh ít bỏ lời trên file dài.

**Ứng viên ưu tiên cho máy hiện tại: Qwen 1.7B.** Chọn 0.6B khi cần ít VRAM hơn;
giữ Faster-Whisper large-v3 như lựa chọn có sentence timing và đã hoàn tất nhiều
file hơn. Đây là suy luận từ benchmark local, chưa đổi default của app.
SenseVoice/Parakeet/OmniASR/FireRed/head JazerJu chưa có phép so recognition tương
đương; không xếp hạng bằng coverage tokenizer. Community-1 là model người nói,
không phải model nhận dạng chữ; giữ báo cáo speaker riêng.

## Kế hoạch thực hiện theo thứ tự

### 1. Bảo toàn transcript, tách xuất TXT — đã sửa source

Phạm vi và hành vi như trên. Regression offline kiểm tra TXT không gọi aligner,
aligner thiếu vẫn giữ đủ text, không ghi đè TXT cũ, hủy/incomplete không thành
success, pipeline không tiếp tục khi thiếu timed subtitle.

Validation: **226 test local ASR/CLI/UI pass / 17,44 s**, trong đó 13 case mới.
Ruff/pyright app pass sau sửa import ordering. Chỉnh UI cuối bỏ modal timing
cho standalone recovery: **5 case pass / 2,36 s**; kiểm tra thêm task chạy lại
không giữ `ASRData` cũ. Không full
suite, tải weight, acoustic inference, API, build hoặc GUI EXE mới ở lượt này.
EXE TimingGuard cũ chưa chứa thay đổi; chưa gọi phiên bản đóng gói đã được sửa.
Việc này xử lý mất/chặn kết quả chữ khi aligner lỗi; **chưa sửa được Qwen timing
câu/đoạn để mọi input xuất SRT thành công**.

### 2. Timestamp câu/đoạn cho workflow phụ đề — ưu tiên kế tiếp

- Giữ nguyên yêu cầu interval dương, đúng media và text đầy đủ cho mỗi cue. LLM
  nhận text cùng start/end có nguồn từ audio; không được đặt giờ mới theo tốc độ
  đọc, chia đều duration hoặc tự đoán từ text.
- Tách kiểm tra timing câu khỏi timing từng chữ: internal word timing lỗi không
  tự động chứng minh cả biên câu sai. Cần thiết kế quy tắc lấy biên câu có cơ sở,
  lưu provenance/raw và chặn biên câu sai; không chỉ gom min/max để giấu outlier.
- Kiểm tra quy tắc mới bằng raw đã lưu trên clip user và các mẫu meeting có lỗi
  khác nhau trước; chỉ inference khi có thay đổi acoustic thực sự cần đo. Nếu
  chưa có biên đáng tin, giữ TXT/review và báo timed output chưa hoàn tất.
- Faster-Whisper sentence là đường có timing hiện tại; không tự chuyển engine
  hoặc lấy giờ của transcript khác gắn vào chữ Qwen mà chưa đối chiếu audio/text.
- Gate: chọn xuất SRT → có đủ text và timing câu/đoạn hợp lệ → chuyển nguyên dữ
  liệu cho LLM. Không tính TXT recovery thành pass của gate này. Word timestamp
  chỉ là yêu cầu riêng khi tính năng thật sự cần độ chi tiết đó.

### 3. Tự chuẩn bị model khi bắt đầu nhận dạng

- Xây `ensure selected model` trong core, dùng chung GUI/CLI. Chỉ tải model đang
  chọn và dependency cần cho tác vụ; TXT Qwen không kéo aligner hoặc Community-1.
  Mở settings chỉ hiển thị trạng thái. Lần sau dùng lại bản đã có.
- Dùng revision/hash cố định và kiểm tra file hoàn chỉnh; tải vào vị trí tạm do
  task sở hữu rồi activate. Không ghi đè runtime đang dùng. Có lock chống hai job
  cùng cài, báo dung lượng/tiến độ, hủy được và tiếp tục tải dở an toàn.
- Dùng runtime Python riêng theo recipe hiện có; không cài global hoặc đổi Qt
  dependencies. Thiếu `uv`/Python/GPU được báo trước khi nhận dạng.
- GUI bấm bắt đầu sẽ chuẩn bị model rồi tự tiếp tục đúng file/cấu hình đã chụp.
  Faster-Whisper dùng đúng executable/model directory được chọn. Không tự đổi model
  do lỗi tải/OOM. Community-1 chỉ tải khi user bật và cung cấp quyền/token hợp lệ.
- Gate: máy chưa có model → tải → nhận dạng; lần hai không tải; mất mạng/hủy/
  thiếu disk/file hỏng không thành ready. Kiểm tra bằng fixture tải nhỏ trước,
  một lượt tải thật chỉ khi cần xác minh tích hợp và chưa có model phù hợp tại máy.

### 4. File dài và tốc độ — giải quyết lỗi có sẵn

- Tách policy chia audio nhận dạng khỏi yêu cầu cửa sổ của aligner. Xử lý việc
  không tìm được khoảng lặng mà vẫn giữ đủ sample/lời nói; chọn cách chia từ đặc
  tính model/audio, không sửa text hoặc ghép chữ theo kết quả mong muốn.
- Xử lý timeout/EOS của job dài, giữ chunk đã hoàn tất, trạng thái phần thiếu rõ
  ràng, resume không inference lại chunk thành công. Không công bố partial là complete.
- Chỉ đo lại ba clip lỗi chia audio, một timeout và stress sau thay đổi liên quan;
  không lặp nguyên corpus để tích số pass. Giữ điểm cũ và mới riêng.
- Báo cold load, recognition, speaker và export riêng. Mục tiêu đề xuất trên máy
  hiện tại: nhận dạng sau load nhanh hơn audio ít nhất 4 lần (RTF ≤ 0,25), cold
  start hiển thị riêng; đây là mục tiêu, chưa là SLA đã đạt. Ưu tiên loại bỏ stage
  không cần cho TXT trước khi thay model/precision hoặc giữ GPU qua nhiều job.

### 5. Người nói tùy chọn

- Bật riêng sau khi recognition cơ bản ổn định; lỗi/thiếu model người nói không
  làm mất transcript. Giữ label ẩn danh, không đoán tên/quan hệ/xưng hô.
- Nếu chưa có timing để gắn text, trả track người nói riêng hoặc trạng thái chưa
  gắn; không giả gán từng chữ. Thiết kế nhận dạng theo turn cần phép đo riêng trên
  các mẫu overlap/returning speaker đã có trước khi chọn cho sản phẩm.
- Dùng evidence Community-1 cũ làm baseline; DER 20,66% không collar và 14,90%
  với collar 250 ms chưa đồng nghĩa speaker attribution của transcript đã đúng.

### 6. Đóng gói và nghiệm thu sản phẩm

- Sau khi bước 2–4 ổn: build onedir tên mới từ spec duy nhất; giữ artifact cũ.
- Từ EXE mới: chọn file → tự chuẩn bị model → TXT Qwen; Faster-Whisper sentence
  → SRT; hủy và mở lại. Bật người nói là phép thử riêng khi model ready.
- Xác nhận transcript đầy đủ, lỗi nhận dạng/speed trên phạm vi đã đo, output mở
  được và không mất dữ liệu. Không yêu cầu raw timestamp từng chữ của Qwen phải
  qua gate mới công nhận speech-to-text. SRT/render vẫn cần timing hợp lệ.
- Giữ dịch LLM hiện tại; không làm thêm benchmark dịch, tìm key cũ hoặc đổi route.
  Chỉ kiểm tra chuyển tiếp output đúng khi cần cho app. OCR chưa triển khai trong plan này.

## Hạng mục tương lai: OmniVoice Studio bên cạnh VieNeu

User bổ sung ngày 2026-09-09: muốn tích hợp thêm lồng tiếng bằng **OmniVoice Studio**
bên cạnh **VieNeu Local**. Đây là hạng mục sau ASR, chưa triển khai trong lượt bàn giao
prompt; giữ ưu tiên sửa timestamp câu/đoạn Qwen và chất lượng nhận dạng.

- Giữ VieNeu hoạt động và cho phép chọn thêm provider; không tự thay provider mặc định.
- Chưa xác minh dự án/repository, phiên bản, license, cách gọi API/SDK/CLI, hỗ trợ
  Windows/GPU hoặc tiếng Việt của OmniVoice Studio. Khi bắt đầu hạng mục, xác định
  đúng sản phẩm từ nguồn chính thức hoặc link user cung cấp; không đoán endpoint,
  không mặc định tương thích OpenAI và không đồng nhất tên model với tên Studio.
- Sau khi có contract thực, thiết kế adapter phù hợp với pipeline dubbing hiện có,
  dùng chung chọn giọng, đo duration, cache, timeline và hủy job ở nơi có thể.
  Nếu cần runtime GPU thì tách khỏi Qt process, pin dependency/model và giữ runtime
  VieNeu; cấu hình credential và lifecycle theo quy tắc repository.
- Nghiệm thu provider riêng: tổng hợp đoạn tiếng Việt, chất lượng lời đọc, duration,
  ghép timeline, lỗi/hủy, rồi kiểm tra cả source và EXE. Không lấy gate VieNeu hoặc
  ASR đã pass làm bằng chứng OmniVoice Studio đã hoạt động.

## Giới hạn kiểm tra và file thay đổi

Mỗi lần chạy phải trả lời lỗi mới hoặc xác nhận code đã thay đổi. Kế thừa các
benchmark/EXE gate cũ; không tiếp tục preflight CTC hoặc sweep dtype/window theo
chuỗi audit trước khi chưa có nhu cầu sản phẩm cụ thể.

Code lượt này: `core/asr/api_transcription.py`, `core/asr/local/pipeline.py`,
`core/asr/transcribe.py`, `core/entities.py`, `cli/commands/transcribe.py`,
`ui/thread/transcript_thread.py`, `ui/view/transcription_interface.py` dưới
`videocaptioner/`; ba file `test_qwen_text_result.py` ở `tests/test_asr`,
`tests/test_cli`, `tests/test_ui`. Tài liệu: plan này, README, status và prompt
bàn giao. Giữ toàn bộ các thay đổi tài liệu audit trước. User sau đó yêu cầu
submit/push snapshot bàn giao chứa plan này; quyền đó không áp dụng cho thay đổi
mới của phiên tiếp theo. Các ghi chú chưa commit ở lịch sử là trạng thái lúc đo.
