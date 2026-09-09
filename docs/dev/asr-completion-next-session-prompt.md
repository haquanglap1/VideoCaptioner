# Tiếp tục ASR và ghi nhớ hạng mục OmniVoice Studio

## Prompt mới nhất: sau Qt shutdown/Bing ErrorFix

Dùng [prompt phiên tiếp theo](error-fixes-next-session-prompt-2026-09.md) cho
snapshot mới. Qt/Bing đã có commit code `d1ab4ca`/`a5ba2be`, cùng commit tài liệu
theo sau; lấy HEAD cuối từ Git. Artifact mới là `VideoCaptioner-ErrorFix-20260909`,
409 test pass/24 deselected và hai ca shutdown EXE pass. R6 phía dưới vẫn là
bằng chứng pipeline GUI kế thừa. Không dùng các checkpoint lịch sử để reset hoặc
coi các thay đổi đã commit là chưa triển khai. Ưu tiên tiếp theo: tái hiện và sửa
đường Google/DeepLX có thể nuốt lỗi/cache bản dịch thiếu bằng test cô lập.

## Hoàn tất lượt theo session — artifact cuối R6

Đọc [báo cáo cuối](dubbing-review-resume-2026-09.md) và
[bảng session](../plans/asr-completion-sessions-2026-09.md). Review/resume, chọn
cache riêng, downloader, Unicode entry và input-layout synthesis đã hoàn thiện.
User đã cho phép tiếp tục GUI sau Escape; các ghi chú đang chờ bên dưới là lịch sử.

R6 build/startup/CLI và pipeline GUI với phụ đề/WAV có sẵn đã pass, track cuối
giữ đúng VI trên/English dưới. Artifact nguyên onedir ở
`dist/VideoCaptioner-ReviewResume-20260909-R6/`. Source/video/cache/settings giữ;
receipt lưu dưới `build/session-completion-20260909/`. Không chạy lại helper
exclusive-create, inference hoặc render bài giảng đã được chấp nhận.

User yêu cầu commit/push toàn snapshot lượt này theo từng phần lên
`origin/codex/asr-s3-native`; lấy HEAD thật bằng `git log -1`, đối chiếu tracking.
Không merge master/tag/release. Phần quality/RTF, model gated/người nói và fresh
online inference vẫn theo phạm vi đã chốt; không công bố pass vượt bằng chứng.

## Checkpoint mới: R4 sửa Unicode, GUI còn chờ sau Escape

R4 đã build và CLI check thành công. Core/downloader/review/scroll/chọn cache riêng
đã qua test; bytecode trong artifact khớp source. CLI R3 bị cp1252 trên `--help`
(user gửi ảnh); entry đã sửa UTF-8 và R4 `--help`/`dub --help` exit 0, arg Unicode
sai exit 2 đúng. Không chạy lại helper có receipt exclusive-create hoặc build
bản cùng tên. [Bảng session](../plans/asr-completion-sessions-2026-09.md) và
[báo cáo](dubbing-review-resume-2026-09.md) ghi hash/gate từng bản.

User nhấn Escape dừng Computer Use khi mở R2; chưa có xác nhận tiếp tục chuột/bàn
phím. R2 đã đóng exit 0; R4 chưa mở GUI. Workflow GUI review/save/open/resume và
OmniVoice reuse từ chính artifact còn chờ. Fixture HTTP/headless đã được dừng
đúng process do task tạo (`server-stopped.json` trong evidence); không coi
`server.json` cũ là server còn sống và không chạy lại helper exclusive-create
nguyên trạng. Khi có phép tiếp tục GUI, chuẩn bị server/receipt mới rồi dùng
video/SRT fixture đã có. Chưa có request TTS fixture hoặc render trong workflow native đã dừng.
Không reset thay đổi, không chạy lại bài giảng/model/API. Chưa commit/push; quyền
Git đã cấp vẫn giữ, thực hiện sau khi chốt nghiệm thu còn thiếu.

## Lượt hiện tại: hoàn thiện theo session và chốt Git

User yêu cầu hoàn thành phần còn lại theo session nhỏ rồi commit/push lên
`origin/codex/asr-s3-native`. Đọc [bảng session](../plans/asr-completion-sessions-2026-09.md)
trước các ghi chú lịch sử dưới đây. Nền là `f510846` cộng sửa handoff SRT hiển thị
chưa commit; không reset/ghi đè thay đổi đang làm. Các session mới triển khai
review/resume kế hoạch lời đọc, GUI, downloader và nghiệm thu EXE.
Không dùng các giới hạn quyền commit/push cũ để phủ nhận yêu cầu mới này.

## Sau snapshot f510846: đã rà luồng GUI lồng tiếng

User chọn tiếp tục rà GUI/EXE với artifact/cache. Đọc
[báo cáo handoff](dubbing-gui-handoff-2026-09.md): GUI hiện chưa khôi phục kế
hoạch lời đọc đã rút gọn của job cần review; đường mở editor chỉ mang video/SRT.
151 WAV cuối còn đủ, 121 nhóm đổi lời; replay timing khớp report, không inference.

Source sửa một lỗi riêng: bỏ qua dubbing phải chuyển SRT hiển thị sang synthesis.
139 test UI/thread/CLI pass, Ruff/pyright/sync pass. EXE GUIResume được kiểm tra
method trong PYZ và còn lỗi cũ; **chưa build lại, chưa có sửa mới trong EXE**.
HEAD vẫn `f510846`; working tree nay có code/test/tài liệu chưa commit, phải giữ.
Ca tiếp theo đã mô tả: review/tiếp tục giữ wording, ánh xạ cue/group và WAV cache;
chưa triển khai tính năng này. Không tự chạy lại helper/media/model hoặc tìm key.
Quyền commit/push cũ không áp dụng; OCR dừng. Phần bàn giao dưới là lịch sử snapshot.

## Snapshot bàn giao: user yêu cầu commit và push

User đã yêu cầu commit/push toàn bộ thay đổi hiện tại: ASR câu thực dụng có
Whisper dự phòng, OmniVoice Local, lồng tiếng nhịp đều, GUI download/cancel-resume
và tài liệu/evidence summary. Quyền này dành cho snapshot bàn giao, **không tự
áp dụng cho thay đổi mới của phiên sau**; không tạo tag/release hoặc merge master.

Làm tại checkout **VideoCaptioner-ASR-S3**, nhánh **`codex/asr-s3-native`**.
Snapshot có subject **`feat(asr): ship practical subtitles and OmniVoice dubbing`**,
parent **`b102ae9`**. Parent này không còn là HEAD sau commit; dùng `git log -1`,
`git status --short --branch` và đối chiếu SHA được gửi trong tin nhắn bàn giao.
Remote đích là `origin/codex/asr-s3-native`, không push lên `upstream`.
Các ghi chú “chưa commit trên b102ae9” bên dưới mô tả lịch sử trước snapshot.

Đọc `AGENTS.md`, `README.md`, đầu `status.md`, rồi báo cáo GUI/download, báo cáo
toàn bài và plan đã chốt. Phạm vi tiếp theo chưa được user chọn: full workflow
video qua GUI/EXE, OmniVoice GUI downloader, gated model/người nói và lỗi
disk/network thật vẫn còn mở. Chỉ tiếp tục theo yêu cầu mới; không dùng lịch sử
để khởi động lại benchmark, tải model đã hoàn tất hoặc chỉnh video “tạm ổn”.
Artifact/runtime/media/cache chỉ có tại máy, không nằm trong Git; clone trên
máy khác không tự có chúng. Giữ key hết scope, OCR dừng, VieNeu tiếp tục được giữ.

## Mới nhất: đã tiếp tục nghiệm thu GUI và tải model theo lựa chọn user

Đọc [báo cáo GUI/download](asr-gui-download-2026-09.md). Lượt này sửa trạng thái
GUI sau hủy và progress đọc `.incomplete` quá MAX_PATH. 150 test liên quan/CLI
pass, Ruff/pyright/sync pass. Qwen 0.6B tải mới/hash verified ở source; ForcedAligner
hủy giữ 280 MiB, resume HTTP Range/206 đúng offset, hủy tiếp giữ 630 MiB.

EXE cuối `VideoCaptioner-ASR-GUIResume-20260909`: build exit 0/6 warning/0 error;
chính GUI EXE hủy HTTP giữ 1340 MiB → tiếp tục hoàn tất → verify/health/reuse
pass. GUI sống 412,938 s, đóng exit 0, không child sót. Không chạy inference
ASR/alignment/LLM/TTS, không render lại video. Runtime/model mới chỉ nằm trong
`build/gui-download-acceptance-20260909/`; giữ cả cache/helper/lỗi cũ, không
chạy lại helper exclusive-create hoặc tải model đã hoàn tất để lặp gate.

Source còn mọi thay đổi chưa commit trên `b102ae9`, cộng bốn file code/test
và tài liệu của lượt này. Không commit/push/release. Full workflow video qua
GUI/EXE, OmniVoice GUI downloader, gated model/người nói và lỗi disk/network
thật còn chưa nghiệm thu. Quyết định dừng chỉnh bản lồng tiếng dưới đây giữ
nguyên; nó không phủ nhận gate GUI/download mới đã được user yêu cầu.

## Trạng thái bàn giao mới nhất: dừng chỉnh theo phản hồi “tạm ổn”

Luồng ASR → dịch Việt → OmniVoice → lồng tiếng toàn bài đã hoàn tất trên video
12 phút 51 giây. User phản hồi “thôi, tạm ổn rồi”; không tiếp tục rewrite,
inference, benchmark hoặc render lại nếu chưa có yêu cầu/lỗi cụ thể mới.

Đọc [plan đã chốt phạm vi](../plans/asr-completion-2026-09.md) và
[báo cáo toàn bài](full-lecture-dubbing-2026-09.md). Artifact cuối nằm trong
`build/full-lecture-dubbing-20260909/`: `lecture-vi-omnivoice.mp4`,
`lecture.spoken.vi.srt`, `report-final-r2.json`, `render-r2-state.json`.
151 nhóm, một tốc độ 1,00×, không overlap, trễ tối đa 2284 ms. Key hết scope;
không mở lại ô key/helper cũ. Phần cuối tái dùng 149 WAV, Codex rút hai câu và
tạo đúng hai WAV; không coi đây là nghiệm thu full GUI tự động trên mọi input.

Plan sản phẩm rộng hơn còn gate cài mới model/GUI HTTP cancel-resume và toàn
workflow GUI/EXE; người nói là phần bổ sung, quality/RTF corpus khó chưa đạt
nghiệm thu. Để các mục này ở trạng thái chưa nghiệm thu; không tự chạy tiếp vì
user đã chốt tạm bản hiện tại. Working tree vẫn có thay đổi chưa commit trên
b102ae9; giữ tất cả, không commit/push/release. OCR vẫn dừng.

Các phần tiếp theo là lịch sử, được thay thế bởi trạng thái này khi mâu thuẫn.

## Lịch sử phản hồi: user muốn nhịp đọc đều

User chê preview tăng tốc từng nhóm nghe lúc nhanh lúc chậm. Đã đổi policy
`sequential` thành một hệ số chung cho cả job, ưu tiên 1,00× và LLM rút câu dài.
Đọc [báo cáo](sequential-dubbing-2026-09.md). Mẫu mới trong
`build/steady-dubbing-20260909/lecture-steady-preview.mp4` giữ 1,00×, không
overlap, trễ lớn nhất 2120 ms trong giới hạn 2500 ms. Chưa có xác nhận nghe của user.

Một lượt LLM thật đã xử lý hai group dài: ba request, g-0003 có rewrite hợp lệ
và một WAV mới 6,6 s; g-0002 phản hồi lỗi JSON hai lần nên giữ lời gốc. Dùng cache
để hoàn tất preview, không gọi lại inference đã xong. Key hết scope, không lưu.
Giữ tất cả report/candidate/video cũ. Bản thử tăng tốc cục bộ trước đó không là
bản user chấp nhận; không quay lại sweep tốc độ từng câu. EXE mới tên Natural-Steady,
xem hash/gate trong báo cáo. Lượt tiếp tục đã xác nhận GUI 25 s/đóng exit 0 và
frozen cached workflow exit 0, tốc độ 1,00×, không overlap, không child sót;
không gọi lại LLM/TTS. Chưa có quyền commit/push, OCR vẫn dừng.

## Mới nhất: OmniVoice Local đã tích hợp theo repository user cung cấp

Đã xác định `k2-fsa/OmniVoice`, thêm provider GUI/CLI cạnh VieNeu. Đọc
[báo cáo OmniVoice Local](omnivoice-local.md) trước khi tiếp tục: runtime/model
riêng đã cài thật; code `08be0b4c`, model `c5fdb5cc`. Có WAV giọng Việt và preview
video 30 s dưới `build/omnivoice-integration-20260909/`; không chạy lại synthesis
đã xong để benchmark. EXE cuối `VideoCaptioner-OmniVoice-20260909-R2`; frozen
worker load/config + cached dubbing pass, 0 generation mới trong frozen check.

User chưa nghiệm thu giọng/độ khớp timeline. Preview dùng Natural/allow-overlap,
hai nhóm vượt khung; chưa lồng tiếng toàn bộ 180 cue. Chế độ clone thử bằng chính
giọng OmniVoice tự sinh, không clone người nói trong video. OmniVoice là code
Apache-2.0 nhưng audio tokenizer có license Boson riêng; giữ thông tin thành phần.
Working tree có thêm code/test/resource/docs chưa commit trên b102ae9; giữ mọi
thay đổi ASR/dịch trước đó. Chưa có quyền commit/push; OCR tiếp tục dừng.

## Bổ sung mới nhất: bản dịch tiếng Việt đã giao để user kiểm tra

Theo yêu cầu user, đã dịch **180/180 cue** bài giảng bằng gateway đã chốt và
`gpt-5.6-terra` (7 request thành công / 155,844 s, timeout 300 s). File nằm trong
evidence `practical-sentences-20260909/translation-vi/`: `lecture.vi.srt`,
`lecture.vi-zh.srt`, `lecture.vi.txt`, `lecture.translated.json`. Timestamp,
original text, cue ID và provenance giữ nguyên; không ASR/alignment lại.
Key nhập kín chỉ giữ RAM cho job đã kết thúc, không lưu để tái dùng. Không tìm
key trong log/receipt. Đợi lỗi hoặc phản hồi cụ thể của user; không tự dịch lại.
Chưa nghe đối chiếu chất lượng hoặc dịch bằng nút GUI/EXE; xem báo cáo cập nhật.

## Kết quả mới nhất: đã làm theo đề xuất được user đồng ý

Đọc [báo cáo Qwen câu thực dụng + Whisper dự phòng](asr-practical-sentences-2026-09.md).
Source đang có thay đổi code/test/docs chưa commit trên `b102ae9`; kiểm tra Git,
không reset về snapshot. User đã cho phép dùng Whisper thay **cả chữ và thời gian**
ở vùng Qwen không tạo được câu dùng được. Điều này thay thế cấm đổi engine trong
bàn giao cũ; word strict/review legacy vẫn giữ policy cũ.

Bài giảng có `lecture.zh.srt`: **180 cue = 164 Qwen + 16 Whisper**, trong evidence
`practical-sentences-20260909/`. Original Qwen, raw và receipt cũ giữ nguyên.
Chỉ một Whisper inference thành công vùng cuối 713.100–771.029 ms; **không chạy
lại** Qwen/aligner/Whisper đã xong. Source CLI và frozen cached CLI đều exit 0;
EXE cuối `VideoCaptioner-ASR-Practical-20260909-R2`, xem hash/gate trong báo cáo.

Không quay lại sweep/ablation hay coi thiếu CER bài giảng là lý do benchmark tiếp.
Ưu tiên lỗi sử dụng thực tế nếu user báo. Chưa nghe thủ công/% chính xác, GUI
button workflow, tải model mới, dịch/TTS. OmniVoice Studio vẫn là hạng mục kế tiếp
bên cạnh VieNeu Local khi user chuyển sang; OCR dừng. Chưa có quyền commit/push.

## Chỉ đạo mới nhất: hoàn thiện theo mức dùng thực tế như Whisper

User đã điều chỉnh yêu cầu ngày 2026-09-09: nhận dạng tương đối **80–90%** là đủ,
không cần 100% và không tiếp tục kiểm thử Qwen quá sâu. Ưu tiên này thay thế các
điều kiện nghiệm thu quá nghiêm trong phần bàn giao cũ bên dưới khi có mâu thuẫn.
80–90% là kỳ vọng sử dụng, chưa phải chất lượng đã đo cho mọi video.

Tập trung đưa ra SRT câu/đoạn dùng được với timing tương đối bám lời nói, cho phép
review sai sót; không buộc mọi word timestamp/onset qua đối chứng acoustic. Dừng
chuỗi sweep/ablation/benchmark lặp lại. Kế thừa raw/cache bài giảng, sửa đúng phần
chặn xuất phụ đề, chạy test gần phần sửa và một workflow thật. Vẫn xử lý treo,
mất chunk, output/timeline hỏng; không công bố kết quả thiếu là hoàn chỉnh.

Đây là đổi tiêu chí và hướng công việc, **chưa sửa code hoặc nghiệm thu SRT**.
Không đổi receipt fail cũ thành pass. OmniVoice Studio sau ASR, giữ VieNeu Local;
OCR dừng. Xem [kế hoạch cập nhật](../plans/asr-completion-2026-09.md).

## Bắt đầu đúng workspace

Làm tại checkout **VideoCaptioner-ASR-S3**, nhánh **`codex/asr-s3-native`**.
Snapshot chứa prompt này gom **30 file code/test/tài liệu** trên nền **`d2dc518`**,
với commit subject **`feat(asr): add resumable model preparation and bounded recognition`**.
`d2dc518` là parent của snapshot, **không còn là HEAD bàn giao**. Lấy SHA chính xác
bằng `git log -1`; đối chiếu SHA trong tin nhắn bàn giao và tracking branch.
HEAD và tracking branch đã xác nhận **b102ae9**. Sau các lượt tiếp tục có sáu
tài liệu chưa commit, không còn kỳ vọng working tree sạch. Chạy
`git status --short --branch`, đọc diff nếu có thay đổi mới và giữ tất cả chúng.
Không reset về d2dc518, 669c0da, 2f8e0a8 hoặc nền benchmark cũ.

Đọc `AGENTS.md`, `README.md`, mục mới nhất `status.md`, rồi:

- [Báo cáo mới nhất: raw alignment toàn bài giảng](asr-lecture-complete-alignment-2026-09.md).
- [Video bài giảng và lexical onset ablation được kế thừa](asr-lecture-onset-2026-09.md).
- [Native timestamp head và đối chứng audio được kế thừa](asr-native-timestamp-control-2026-09.md).
- [Direct Qwen-text alignment và generation trace được kế thừa](asr-direct-alignment-stall-2026-09.md).
- [Timing probes, stall và GUI resume được kế thừa](asr-stall-resume-2026-09.md).
- [Báo cáo SentencePrep được kế thừa](asr-sentence-preparation-2026-09.md).
- [Plan ASR và hạng mục OmniVoice Studio](../plans/asr-completion-2026-09.md).

Báo cáo cũ là lịch sử; số file chưa commit trong từng báo cáo mô tả thời điểm đo.
User đã yêu cầu submit/push snapshot này. Quyền đó **không áp dụng cho thay đổi
của phiên tiếp theo**: không tự commit/push, tạo tag/release. **OCR vẫn dừng.**

## Ưu tiên của user

- Nhận dạng đúng, nhanh, ổn định; **cần timestamp câu/đoạn** để làm phụ đề và chuyển
  cho LLM. Không bắt mọi word timestamp phải pass khi chỉ cần cue.
- TXT là đầu ra text và bản bảo toàn khi timing lỗi; **chưa thay SRT/ASS**.
  LLM không thể suy giờ nói chính xác chỉ từ text.
- User không biết tiếng Trung; cần tiến triển trên luồng thật. Mỗi phép đo phải
  trả lời lỗi/thay đổi cụ thể, không tiếp tục chuỗi audit/CTC hoặc sweep model,
  dtype, cửa sổ theo quán tính. Không tính RMS pass là nghiệm thu acoustic.
- Dịch giữ `https://api.videocaptioner.cn/v1`, `gpt-5.6-terra`, timeout 300 s.
  Không benchmark dịch thêm hoặc tìm key cũ. Nếu cần API mới, dùng credential nhập
  kín theo scope cần thiết, không đưa vào chat/argv/env/file.
- Scribe/ElevenLabs đã ngoài scope. Không xin key/tài khoản cho các engine đó.
- **Hạng mục sau ASR:** thêm lồng tiếng bằng **OmniVoice Studio**, bên cạnh
  **VieNeu Local** hiện có. Chưa yêu cầu triển khai OmniVoice Studio ngay.

## Source hiện có và giới hạn

1. **Recognition độc lập:** Qwen TXT không tìm/verify/nạp aligner hoặc Community-1.
   Timed export nhận dạng trước; lỗi timing giữ TXT/review, không overwrite TXT
   của user. CLI timed output chưa tạo được giữ exit 5; pipeline cần SRT dừng.
   Partial/hủy không được công bố complete.
2. **Cue policy:** `qwen-sentence-anchors-v1` chia theo text, lấy start token đầu
   và end token cuối, kiểm tra hai token biên với audio; mọi mốc raw phải nằm trong
   cue. Word strict giữ riêng. Không min/max, clamp, swap, interpolate, bỏ chữ
   hoặc lấy ranh giới chunk làm giờ nói. Review giữ raw/policy/ID/audio identity;
   cache raw alignment tách khỏi output đã validate.
3. **Tự chuẩn bị model:** core GUI/CLI dùng lại model đã verify; thiếu thì tải đúng
   model vào runtime managed riêng, có ownership/OS lock/hash/progress/hủy/resume.
   TXT không tải aligner; giữ runtime cũ. Mở manager không download.
   Cài mới thật qua mạng chưa đo vì runtime phù hợp đã có.
4. **File dài:** request nhận dạng tối đa 30 s; thiếu silence thì cắt theo năng
   lượng gần cuối, giữ đủ sample. Timeout retry một lần <=15 s; cache giữ chunk
   hoàn tất và retry plan. Worker mới dùng budget token theo audio, bắt buộc EOS;
   hết budget trả incomplete và giữ model cho retry nhỏ. Bốn stall cũ được chặn
   ở 51,672–83,671 s thay vì ~181 s, nhưng nguyên nhân generation chưa được sửa.
5. **Người nói tùy chọn:** lỗi giữ subtitle đã có timing và `pending_diarization`.
   Chỉ gán nguyên cue khi có sentence timing; không đoán danh tính/xưng hô hoặc
   giả gán từng chữ. Community-1 vẫn cần quyền/token khi cài model gated.

Implementation chính dưới `videocaptioner/`: `core/asr/local/{pipeline,audio,
sentence_timing,prepare,runtime,review}.py`, `core/asr/transcribe.py`,
`resources/local_asr/download.py`, `cli/commands/transcribe.py`,
`ui/thread/transcript_thread.py`, `ui/components/local_asr_cards.py`.
Bridge `resources/local_asr/bridge.py` và `ui/thread/local_asr_thread.py` cũng đã
sửa. Locator chạy bridge bundle với runtime đã verify, nhận đúng hash bridge cũ,
tìm cả managed path cũ để không tải trùng. GUI manager thêm Prepare / resume;
native Qt/QTest đã hủy verify rồi tiếp tục model thật, chưa hủy HTTP transfer.
Danh sách file và gate chi tiết nằm trong các báo cáo trên. Direct DTW và mask
recognition thử nghiệm chỉ nằm trong evidence, không có trong bridge app/EXE.

## Việc tiếp theo theo thứ tự

**Video mới do user cung cấp:** resolve đúng nguồn qua
`ai-lecture-full-20260909/source-preflight.json` trong Completion; user đã cho
phép dùng toàn video bài giảng 12 phút 51 giây để test. CLI source đã có TXT
**4.783 ký tự**, 29 chunk; hai chunk đầu reuse, 27 request mới đều EOS.
Lượt CLI cũ exit 5 / 118,016 s: timing dừng tại chunk 220.850–248.900 ms,
token biên `token-001149` start=end 228.050 ms.
**Lượt mới đã căn nốt 20 chunk sau** trong `cue-clauses-20260909/`: đủ raw cho
29/29, 0 recognition. Giữ `all-raw.json`, `chunk-09.raw.json` đến
`chunk-28.raw.json`, receipts/audio hashes và `validation.json`. Policy sản phẩm
qua geometry/energy **24/29**, còn lỗi index **8, 12, 26, 27, 28**: token biên
zero-duration hoặc cue overlap. Geometry/energy không là acoustic acceptance.
Không gọi lại 20 alignment đã xong; dùng raw/receipt mới bên cạnh review cũ.
ID của 20 chunk này trong review cũ là placeholder cả chunk, không tự gán chúng
thành word ID khi dùng raw mới.

Một quy tắc text thử ưu tiên dấu phẩy trước cap 40 đã bị loại: giải phóng
index 8/27 nhưng làm index 13/15 fail, tổng vẫn 24/29. Không chọn policy theo
chunk, đổi giới hạn/dấu câu để tìm pass hoặc tích hợp candidate. Source đã
khôi phục đúng snapshot; code thử chỉ ở `sentence_timing_candidate.py` trong
evidence. Helper cũ ghi lịch sử khi source candidate đang tạm có mặt; không
chạy lại helper. `validate_complete.py` dùng bản candidate đã lưu, chỉ replay.

Không nhận dạng lại từ đầu; dùng cache/raw/receipt của lượt full. Đoạn 60 s ở
`ai-lecture-20260909/` có cache riêng giữ nguyên và end raw vượt đoạn cắt 30 ms.
Không clamp/nới guard hoặc gộp lại cue theo lỗi. Chưa quality reference/CER,
SRT/LLM hoặc workflow GUI/EXE cho video mới.

`acoustic-token-onset-20260909/` đã thử lexical confidence với audio ablation,
prefix text không timestamp token: 25 encoder/decoder calls. Một onset chạm
đáy bracket, baseline gap không đủ confidence; onset còn lại shift +800 ms
nhưng vẫn quá sớm. `accepted=false`; không lặp bằng đổi threshold, không xuất
SRT/ghép mốc. App/runtime/EXE không đổi; kế thừa 142 test/ResumeGuard.

**Lượt sau b102ae9:** `timestamp-decoder-resume-20260909/` và
`timestamp-decoder-gap-20260909/` trong Completion giữ native timestamp logits
với prefix là chính text Qwen. Hai onset tốt hơn về vị trí (44.150 / 49.150 ms),
nhưng đối chứng chèn +1 s vào khoảng nghỉ **6/8 biên fail**, residual 500 ms,
tolerance 250 ms đã ghi trước inference. `validation.json` ghi `accepted=false`.
Không tăng tolerance, ghép mốc DTW/native hoặc xuất/integrate candidate này.
Hai lỗi helper trước đó ở `timestamp-decoder-20260909/` và
`timestamp-decoder-run02-20260909/` được giữ nguyên; lần resume dùng lại onset
đã lưu, không lặp nó. Tổng kể cả lỗi: 5 encoder forwards/25 decoder calls;
0 Qwen recognition, DTW, API hoặc download. Không lặp native-prefix/gap control
cùng input/config; dùng tensor đã lưu, chỉ inference khi có thay đổi acoustic
cụ thể. App/cache/runtime/EXE không đổi; kế thừa 142 test/ResumeGuard.
Theo thứ tự mới nhất: timing → quality/stall → tải model thật và GUI HTTP
cancel/resume. Chưa chuyển các gate sau thành pass khi timing còn mở.

**Evidence bổ sung mới nhất:** `direct-qwen-align-20260909/` trong Completion.
Một forward Whisper.align trên nguyên text Qwen của chunk cuối (không generation
Whisper) và một silence control. SRT trong `candidate-not-accepted/` đủ **9 cue**,
giữ nguyên chữ/ID/provenance, nhưng **chưa nghiệm thu acoustic** vì đầu cue 2/4
trong chunk còn chứa khoảng nghỉ. Không dùng nó làm đầu vào LLM/sản phẩm, không
gán giờ của transcript khác, clamp hoặc sửa raw. Không chạy lại direct DTW cùng
input/config; Community-1 cache cũng bỏ sót phần cue ngắn, không dùng để cắt lời.
Wheel CT2 19.470.040 byte chỉ giải nén riêng trong evidence; không tải weights,
không sửa dependency project/runtime. Tool audio không hỗ trợ nghe ở phiên này.

`mask-stall/` kiểm tra recognition mask đúng bốn WAV/hash từng stall: parent
R8001_M8004-c02 tại **88.950 ms** đã EOS **5,687 s / 111 token**, giữ output riêng
và **không chạy lại parent đã xong**. Ba request còn lại vẫn incomplete; có raw
token trace với cặp lặp **582/546/570 lần**. Không lặp phép đo mask để quan sát
cùng loop, không cắt repetition để giả EOS. Candidate ghép parent mới với cache
cũ có CER **60,21%** thay baseline **61,44%**, cùng 975 ký tự reference; đây là
output trộn policy ở một clip, không thay common-28 hoặc chứng minh quality tốt.
Mask chưa tích hợp app. `source-before/` ở lượt mới giữ snapshot đủ 29 file cũ.
Nếu cache hết TTL, chỉ phục hồi raw/receipt đã complete vào cache thử nghiệm
riêng sau khi khớp audio hash, sample interval, model revision và policy. Giữ
cache gốc; không gắn output mask candidate vào namespace recognition production.

1. **Qwen timing câu/đoạn còn chưa đạt.** Replay raw cũ chỉ cho 11/32 chunk được
   chọn qua guard, 0/8 cặp model/clip có timing hoàn chỉnh. Mẫu user 60 s chạy với
   cửa sổ mới vẫn TXT/review. Dùng raw đã lưu để định vị lỗi biên trước; chỉ
   inference khi có thay đổi acoustic cần kiểm chứng. Chốt biên có nguồn từ audio
   và đủ text, không nới guard chỉ để có SRT hoặc lấy giờ FWW gán cho chữ Qwen
   chưa đối chiếu. Gate thật: SRT đầy đủ, biên hợp lệ và chuyển nguyên timing cho LLM.
   Hai probe mới (sparse first/last slots, crop vùng cue lỗi theo cue trước) đều
   chưa qua guard; giữ raw trong `cue-slots-20260909/`, **không chạy lại chúng**.
2. **Quality và stall:** bốn clip lỗi cũ đã có TXT, CER thô 33,91–61,44%; stress
   26,23 phút hoàn tất trong 432,422 s, CER 44,27%. RTF sau load có điều phối
   0,261, chưa đạt mục tiêu 0,25. Text mẫu ngắn đã đổi; chưa chứng minh cap 30 s
   cải thiện quality clip ngắn. Kế thừa output/cache/retry plan; không chạy lại từ
   đầu các chunk đã xong. Báo load, request, timeout, speaker/export riêng.
   Ba job cache-resume mới cho TXT nguyên chữ, 0 inference; không lấy số cached
   làm tốc độ model hoặc coi token budget đã cải thiện CER/RTF toàn stress.
3. **Nghiệm thu luồng chuẩn bị model:** cài mới qua mạng khi thực sự cần, GUI
   cancel/resume, disk/network failure, lần hai dùng lại model. Fixture offline
   không thay thế end-to-end tải runtime thật. Người nói là bước bổ sung.
4. **EXE:** đã có bản mới bên dưới. Chỉ build tiếp khi code/resource thay đổi cần
   đóng gói; dùng spec duy nhất, tên mới và báo đủ các gate theo AGENTS.md.

## Hạng mục tương lai: OmniVoice Studio

Ghi nhớ mong muốn của user: thêm lựa chọn lồng tiếng OmniVoice Studio và tiếp tục
giữ VieNeu Local. Khi đến hạng mục này:

- Xác định đúng sản phẩm/repository, phiên bản, license và interface từ nguồn
  chính thức hoặc link user cung cấp. Hiện **chưa xác minh** các thông tin đó;
  không đoán endpoint, hỗ trợ tiếng Việt/Windows/GPU hay tương thích OpenAI.
- Sau khi có contract thực, thêm adapter/provider phù hợp với pipeline dubbing
  hiện có; dùng lại chọn giọng, cache, duration/timeline và hủy job ở nơi phù hợp.
  Nếu cần runtime GPU, tách khỏi Qt process; giữ runtime/model/config của VieNeu.
- Có gate riêng cho tổng hợp tiếng Việt, chất lượng lời đọc, đo duration, ghép
  timeline, lỗi/hủy và source/EXE. Không lấy gate VieNeu/ASR làm pass cho OmniVoice.

## Benchmark và validation được kế thừa

- Common-28: Qwen 1.7B 21,04% CER; 0.6B 22,00%; FWW large-v3 word 36,74%,
  sentence 36,78%. Không thay denominator hoặc ghép quality bốn clip khó vào bảng
  này để tự xếp hạng lại. 1.7B là ứng viên quality, chưa đổi default app.
- Gate cuối source liên quan: **142 pass / 13,16 s**, Ruff pass, pyright 0/0,
  translations in sync. Lượt rộng trước đó 648 pass/5 fail; có 45 pass kiểm tra
  lại sau sửa fixture cũ và rerun timeout race. Xem report để phân biệt fail/skip.
- Checkout không có `.venv`; lượt trước dùng Python 3.12.13 và tools đã có ở
  môi trường project chính bên cạnh. Không tự đồng bộ dependency/cài global.
- Chỉ kiểm tra lại phần thay đổi. Không full suite/build/GPU/API chỉ để lặp gate cũ.

## Evidence và artifact cần giữ

Root: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`.
Evidence mới: `sentence-20260909/`, đặc biệt `replay.json`, `measure/summary.json`,
`measure/traces.json`, raw/review/TXT và cache trong `measure/host/AppData/`.
Lượt ResumeGuard: `cue-slots-20260909/` chứa `probe/`, `refine/`, `stall/`,
`cache-resume/`, `gui-prepare/`, `frozen-txt/` và build/smoke receipts. `source-before/`
giữ snapshot 25 file đầu phiên. Chỉ hai forward aligner và bốn request recognition
đúng WAV/hash từng timeout; một normal TXT smoke riêng từ EXE mới.
Lượt mới nhất: `direct-qwen-align-20260909/` chứa `probe/` (speech/silence DTW),
`candidate-not-accepted/` (SRT/JSON 9 cue và validation accepted=false),
`mask-stall/` (bốn request, raw generation IDs; `1.complete.json` là parent đã
EOS), `quality/summary.json` và `handoff-validation.json`. Snapshot `source-before/`
giữ đủ 29 file đầu lượt đó. Các helper có exclusive-create; không chạy lại helper
để tạo lại output đã có. Evidence/library/media không nằm trong Git; checkout ở
máy khác không tự có các artifact này. Không tải lại corpus/model chỉ để lấp thiếu.
Dataset: `build/asr-session-evidence/datasets/AliMeeting-Eval/`; không tải/copy lại.
Clip user nằm ở `VC-UserClip-20260908-114035/` cạnh Completion; resolve nguồn qua
`reports/source-preflight.json`. Chỉ 60 s đầu đã được cho phép, không quét ổ.

EXE mới nhất: `dist/VideoCaptioner-ASR-ResumeGuard-20260909/`, nguyên onedir.
SHA-256 `6e8b68b9b67efab6eac9857e1f0577ea61c23e14c77e234c70eabb8e957bc4f3`.
Build exit 0 / 214,516 s, 6 warning đáng chú ý/0 ERROR; GUI sống 25 s, đóng đúng
PID exit 0. Frozen Qwen TXT public 10 s **thực gọi worker**, exit 0 / 27,812 s,
23 ký tự giống bản cũ, không child còn sống. Không chạy lại FWW/translation/synthesis;
chưa frozen GUI button download/cancel hoặc Qwen SRT trên mẫu lỗi.

EXE SentencePrep giữ lại: `dist/VideoCaptioner-ASR-SentencePrep-20260909/`.
SHA-256 `22495164beef9977300c5bf5b83b6c31086f836fe4eb7a2d79eab58604a89f80`.
Build exit 0, 6 warning đáng chú ý/0 ERROR; GUI sống 25 s, đóng đúng PID exit 0.
FWW sentence smoke thật 10 s xuất SRT hợp lệ. Qwen TXT tạo được text; helper lần
đầu race sau khi file đã tạo, lượt xác nhận exit 0 dùng cache. Không coi thời gian
cached là inference. Chưa GUI button workflow/cài mới qua mạng/Qwen SRT trên mẫu lỗi.

Giữ TimingGuard cũ, mọi runtime/model, AppData/cache, media/raw. Junction
`s6-final-build/smoke-app/_internal` từng bị automatic approval review chặn gỡ;
không retry/xóa qua parent. Helper thường dùng exclusive-create; đọc trước chạy.
Kiểm tra process/VRAM trước GPU, chỉ đóng process thuộc task. Không force-add
build/dist hoặc dọn artifact để commit. Bàn giao đúng trạng thái, file sửa và
`git status --short`; không gọi ASR hoặc OmniVoice Studio hoàn tất vượt bằng chứng.
