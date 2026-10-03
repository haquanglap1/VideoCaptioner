# Natural Dubbing

Natural Dubbing giữ ba lớp dữ liệu tách biệt: `source_text` để đối chiếu, `subtitle_text` để hiển thị và
`tts_text` để đọc. Full pipeline ghi một SRT target-only riêng cho TTS; file subtitle display vẫn giữ layout
song ngữ/đơn ngữ mà user đã chọn.

## Luồng xử lý

Độ phân giải đầu ra dùng `Video.OutputResolution` (0 giữ nguyên, 720/1080/1440/2160),
chụp vào `DubbingConfig`/`SynthesisConfig` theo từng job. Preset giới hạn khung
16:9 hoặc 9:16 tùy hướng nguồn, giữ tỷ lệ hiển thị và kích thước chẵn, không upscale.
Scale chạy trước khi vẽ phụ đề; ASS/PNG được dựng theo kích thước đích. Phụ đề
mềm và chế độ không phụ đề cũng xuất đúng độ phân giải. Intermediate dubbing
trong pipeline giữ nguyên nếu còn synthesis; resize chỉ ở lần xuất cuối.
Đổi độ phân giải không đổi cache giọng, lời đọc, tempo/video speed hoặc timing.

Pipeline phụ đề GUI ghi `.completed.json` sau khi publish thành công toàn bộ
kết quả. Identity gồm dữ liệu ASR đầu vào, SHA video, ngôn ngữ đích và chế độ
dialogue; không gồm key/model/prompt/concurrency theo lựa chọn của user.
Body có checksum, đầy đủ text/timing/translation và dữ liệu hội thoại; kiểm
hash file SRT/dialogue trước khi dùng lại. Có cả identity của bảng kết quả
để bấm xử lý lại trong cùng tab không dịch lặp, đồng thời giữ identity nguồn
ban đầu cho lần chạy Batch sau. Không dùng kết quả thiếu, hỏng hoặc đã đổi nguồn.

Đối với bản cũ chưa có checkpoint, chỉ nhận đúng cặp SRT/dialogue cạnh output,
ngôn ngữ khớp, SRT khớp nội dung document và video không mới hơn bản dịch.
Đây là liên kết theo tên/timestamp của bản cũ, không phải bằng chứng SHA của
video tại thời điểm dịch trước đây. Bản native giàu metadata không đi đường
import cũ này. Sau khi dùng lại, app ghi checkpoint để các lần sau kiểm SHA.
Tắt **Dùng lại bản dịch đã hoàn tất** để chủ động chạy lại toàn bộ các bước LLM.

1. `DubbingTextSource` chọn text rõ ràng. `AUTO` ưu tiên `translated_text`; `TRANSLATED` fail nếu thiếu.
2. Planner thuần sắp cue theo timeline, group câu liền nhau và mượn silence có `silence_guard_ms`.
   Với `sequential`, giữ mọi từ khi nối cue, kể cả lời lặp ở biên. Các policy khác giữ heuristic cũ:
   bỏ overlap 1-4 token khỏi `tts_text`, giữ display cue và ghi warning; cue lặp hoàn toàn vẫn giữ.
3. Persistent cache tra SHA-256 theo normalized text, provider host, model, voice, speed và sample rate.
4. TTS chạy ở provider-native speed. Duration từ WAV thật quyết định fit; prediction chỉ dùng routing.
5. Group vượt `fit_ratio_limit` mới được rewrite và synthesize lại, tối đa `max_rewrite_attempts`.
   Chỉ dùng thời lượng đã đo, không rewrite trước TTS dựa vào prediction. Rewrite dùng credential/deadline
   riêng của job và kiểm tra hủy; giữ `source_text`/`subtitle_text`, chỉ đổi `tts_text`.
6. Natural chỉ speed-adjust tới `natural_max_speed`, không truncate. Outlier còn lại đi `review` hoặc
   `allow-overlap`, hoặc chọn `sequential` để đọc lần lượt. Legacy giữ `max_speed` và truncate,
   với action `legacy_truncate` trong report.
7. Engine dựng voice track đúng vị trí group, giữ duration video và mix theo keep/reduce/mute.

Report version `dubbing-report-v1` luôn tồn tại trong RAM để GUI hiển thị chi tiết. Không có file JSON mặc
định; CLI ghi atomically khi user truyền `--report PATH`, GUI khi chọn **Lưu kế hoạch**. Dữ liệu report không serialize API key,
credential URL hay raw provider response.

GUI không tự mở `DubbingReportDialog` nữa. Dialog modal `exec_()` chạy trong slot `_on_finished` đứng
trước `finished.emit(...)`, nên ở pipeline mode bước synthesis phải chờ user đóng hộp thoại và UI trông
như bị treo. Report vẫn nằm nguyên trong `_pending_report_data`; lối vào là nút `Xem báo cáo` xuất hiện
sau khi có report, kèm số group cần xem lại (`needs_review`, `fit_status == "failed"`, hoặc có warning).
Hợp đồng report in-memory không đổi.

## Duyệt lời đọc và tiếp tục

Trong **Xử lý hàng loạt**, lệnh bắt đầu dùng luồng tự động: bản lời thoại đã
qua kiểm tra cấu trúc đi thẳng sang TTS, không tạo checkpoint duyệt thủ công
trước mỗi video. API engine mặc định và tab Lồng tiếng riêng vẫn giữ bước
duyệt. Chế độ tự động không đánh dấu lời là đã được người dùng duyệt và không
bỏ kiểm tra timing/WAV: thiếu lời, lỗi provider hoặc tràn thời lượng vẫn dừng.

Nếu phản hồi LLM có đủ cue và bản dịch hợp lệ, nhưng còn nhóm lời vượt giới
hạn 8/12 giây, translator chỉ thay nhóm quá dài ngay bằng nguyên
bản dịch hiển thị của từng cue. Nhóm hợp lệ giữ nguyên. Không suy đoán timing,
bỏ chữ hoặc chấp nhận cue thiếu/trùng/lạ. Lỗi cấu trúc/nội dung vẫn có tối đa
ba phản hồi; riêng lỗi gom nhóm thời gian không cần thêm lượt gọi mạng.

Batch có **Dừng xử lý** và trạng thái **Đang dừng / Đã dừng**. Queue do Qt main
thread điều phối; mỗi stage vẫn là worker. Chuyển stage/khởi chạy video tiếp
theo đợi native QThread kết thúc để cleanup xong, không chỉ đợi signal kết quả.
Hủy giữ kết quả đã hoàn tất, bỏ các hàng đang chờ, chặn signal muộn chuyển sang
bước tiếp và không `wait()` chặn GUI. Có thể thử lại hàng lỗi/đã dừng.

Faster-Whisper kiểm callback cả khi stdout im lặng và kết thúc process tree
khi hủy. FFmpeg extraction/mix/render dùng polling hoặc stream reader; scope
hủy theo job không patch subprocess toàn ứng dụng. Batch giữ phụ đề của bước
lồng tiếng nếu tắt synthesis; nếu bật, chỉ ghép phụ đề một lần theo timing mới.

Khi job dừng để review, mở **Duyệt / sửa lời đọc** ở tab Lồng tiếng. Bảng nhóm
giữ cue membership, nguyên văn nguồn, phụ đề, lời trước rewrite và thông tin
thời lượng/trễ. Chỉ ô lời đọc được sửa. **Áp dụng lời đọc** giữ thay đổi trong RAM;
**Tiếp tục lời đã duyệt** dùng snapshot cấu hình của job và kiểm tra nguồn lại.

Resume không gọi LLM để rewrite lại lời đã duyệt. Engine tính cache key từ lời đọc
và cấu hình TTS hiện hành, bỏ qua `audio_path`, duration và cờ fit trong file nạp.
WAV cache thiếu/hỏng được tổng hợp lại; WAV còn hợp lệ được dùng lại. Scheduler vẫn
đo và kiểm tra timing đầy đủ, chỉ mix khi không còn nhóm cần review.

**Lưu kế hoạch** ghi JSON atomically theo yêu cầu. Sau khi mở lại app, chọn video,
phụ đề và cấu hình giọng rồi **Mở kế hoạch**. Mở file không tự tạo audio. Fingerprint
SHA-256 của video, SRT lời đọc và SRT hiển thị (nếu có) được kiểm tra trong worker;
đổi vị trí file nhưng giữ nguyên nội dung được phép. Nguồn/cấu hình không khớp thì
dừng trước synthesis và giữ kế hoạch để sửa hoặc chọn lại nguồn đúng.

Nếu WAV nằm ở cache riêng của job cũ, chọn **Thư mục WAV cache (tùy chọn)** trước
khi mở/nhập kế hoạch. Chọn đúng thư mục `v1` chứa trực tiếp các cặp `<key>.wav` và
`<key>.json`; để trống dùng cache mặc định. Đường dẫn là lựa chọn tường minh của
user, không được nạp từ JSON hoặc tự chép vào AppData. Job chụp lựa chọn này;
thay ô nhập sau đó không đổi cache của job đang review. Sau restart, chọn lại
thư mục nếu cần vì report không lưu cache path. Thư mục sai bị chặn trong worker.

Report cũ chưa có `resume_metadata` vẫn đọc bằng core, nhưng GUI cần action riêng
**Nhập checkpoint cũ**. Import kiểm tra provider, mọi group/cue, source/display
text, hình học timeline và cache key, rồi ghi provenance `legacy-user-bound`.
Đây là liên kết với nguồn được chọn lúc import, không chứng minh danh tính media
hoặc cấu hình chưa được ghi của job lịch sử. Không dùng đường dẫn audio trong JSON.

Core contract: `DubbingReview.from_report(engine.last_report)`,
`review.with_group_text(group_id, text)`, `review.save/load`,
`engine.import_review(...)` và `engine.dub(..., review=review)`.
`DubbingTask.dubbing_review` chuyển snapshot typed qua QThread. GUI giữ signal
kết quả job tương thích và xử lý mở dialog/thoát busy sau khi QThread thực sự dừng.
Editor project schema và thao tác undo/redo không đổi; tab Lồng tiếng sở hữu
workflow review theo group.

## Chuyển layout sang synthesis

SRT hiển thị đã được bước phụ đề áp layout. Pipeline ghi layout đầu vào ở
`SynthesisTask.input_subtitle_layout`, tách khỏi layout đầu ra hiện chọn.
`core/subtitle/synthesis.py` phục hồi vai trò source/translation khi đọc SRT
đã định dạng, rồi renderer áp layout một lần. Marker đến từ producer, không
suy từ tên file/ngôn ngữ. Reexport thành công cập nhật marker; ghép lại cùng
file giữ marker, đổi file thì trở về contract standalone.

GUI soft/hard và CLI hard dùng helper chung. CLI soft vẫn nhúng file trực tiếp;
file standalone không có marker, các flag/config public giữ nguyên. JSON/ASS
giữ semantics của parser hiện có. Test gồm bốn layout, dòng đơn/ngôn ngữ đơn,
thay layout đầu ra và giữ timing/nội dung.

## Đọc lần lượt, không chồng lời

Để đọc hết lời với tốc độ **1,00×**, chọn **Tự nhiên → Nhịp đọc đều, không chồng
lời**, đặt **Tốc độ giọng = 1,00×**, **Tốc độ Natural tối đa = 1,00×**, **Độ trễ
bắt đầu tối đa = 1000 ms**, và **tắt LLM rút gọn riêng lời đọc vượt khung**.
Đây là cấu hình theo job; mặc định toàn app và settings đã lưu không tự đổi.
Giữ provider/voice đã chọn. Nguồn TTS phải đúng bản muốn đọc; tắt lọc CJK khi
đọc Trung/Nhật/Quảng hoặc lời có CJK cần giữ.

`playback_start = max(subtitle_start, previous_playback_end + 0.08)`.
Giới hạn 1000 ms là trễ so với subtitle, **không phải nghỉ 1 giây giữa câu**.
Planner vẫn gom các cue liền nhau thành group; giới hạn trễ được kiểm theo mốc
đầu group, không tạo alignment từng từ/cue bên trong một WAV đã gom.
Nối group giữ đầy đủ text, số lần lặp, thứ tự, display text và cue membership.
Với cấu hình trên, không rewrite/atempo/truncate; WAV thật quyết định timing.

Nếu nhiều câu dài làm vượt 1000 ms hoặc lời kết thúc sau video, job giữ review
và audio, báo group cùng giá trị/giới hạn vượt, và không xuất video. Không tự
nới trễ, tăng tốc, rút lời hoặc kéo dài video. Sequential dùng thời lượng video
stream `v:0` (kể cả tag duration của Matroska), không dùng thời lượng audio gốc
dài hơn hay đoán từ subtitle; không xác định được thì dừng trước TTS.
Khi tắt cache, audio của job lỗi vẫn nằm dưới `review-audio/vc_dub_*` trong
WAV cache root đã chọn; report/log ghi vị trí tương đối để kiểm tra. Resume
vẫn tôn trọng cache tắt và tổng hợp lại, không tự lấy đường dẫn từ report.
Khi bật cache, WAV đã hoàn tất được tái sử dụng và đo lại; lỗi provider giữ
trạng thái incomplete, không xuất bản kết quả thiếu group.

Mixer giữ voice track khi audio gốc kết thúc sớm hơn video ở cả keep/reduce;
video không audio stream vẫn dùng mute fallback. Export giữ giới hạn cuối video.
Chi tiết bằng chứng và giới hạn tại [báo cáo sequential](sequential-dubbing-2026-09.md).

Với cấu hình khác có trần lớn hơn 1×, scheduler ưu tiên tốc độ bình thường;
nếu cần tăng nhẹ, chọn một hệ số nhỏ nhất
áp dụng thống nhất cả job. LLM nhận thêm câu trước/sau từ subtitle gốc để rút
gọn có mạch nối; context chỉ đọc, không phụ thuộc output LLM trong cache key.
Câu sau bắt đầu sau khi WAV câu trước đọc xong và có
khoảng nghỉ (mặc định 80 ms, tối thiểu 20 ms). Sau atempo, đo lại WAV và xếp lượt
theo thời lượng thật. Không vượt giới hạn trễ hoặc cuối video; nếu vẫn không thể
xếp được thì giữ report cần review, không công bố video thiếu lời.

`start_time`/`subtitle_end_time` giữ mốc gốc. Report thêm `playback_start_time`,
`playback_end_time`, `start_delay`, `applied_speed`; GUI báo giờ đọc, độ trễ và
tốc độ thêm. `fit_ratio` vẫn so với khung phụ đề gốc, nên có thể lớn hơn 1 khi câu
đã được xếp trễ hợp lệ. Tốc độ postprocess không cộng dồn vượt trần với tốc độ
provider đã yêu cầu. Video/subtitle gốc giữ nguyên; giọng có thể trễ trong giới hạn.

```powershell
uv run --frozen videocaptioner dub video.mp4 --subtitle translated.vi.srt `
  --tts-provider omnivoice-local --voice auto --unresolved sequential `
  --timing-mode natural --tts-speed 1.0 --natural-max-speed 1.0 `
  --max-start-delay-ms 1000 --no-timing-rewrite --report review.json
```

Provider/voice trong ví dụ chỉ minh họa; giữ đúng lựa chọn đã dùng cho job.

## CLI

```powershell
uv run --frozen videocaptioner dub video.mp4 --subtitle translated.srt `
  --tts-provider openai --tts-api-key <key> --tts-model tts-1 --voice alloy `
  --text-source auto --timing-mode natural --unresolved review

uv run --frozen videocaptioner process video.mp4 --translator google `
  --target-language vi --dub --tts-api-key <key>
```

Exit code `6` nghĩa là Natural timing cần review; exit code `7` là provider không tạo audio hợp lệ. Cả hai
in nguyên nhân trực tiếp ra stderr; report path chỉ xuất hiện khi `--report` được yêu cầu. `-q` của lệnh
`dub` chỉ in output path khi thành công.

Full GUI pipeline persist SRT only. ASS chỉ được tạo khi user chọn Save as ASS hoặc tạm thời trong renderer;
render mode ASS không yêu cầu pipeline giữ một file `.ass` cạnh video.

## Acceptance boundary

Unit và FFmpeg integration dùng `FakeTTS` WAV deterministic, gồm cache miss/hit, measured rewrite, review,
allow-overlap, Legacy truncate, silent-source mix và provider failure. Đây là machine acceptance, không phải
bằng chứng chất lượng nghe, rate-limit hay chất lượng của OpenAI/MiniMax/local provider thật.

## Batch Faster-Whisper và console Windows — 2026-10-03

Lượt Batch user gọi là lồng tiếng thực tế dừng ở ASR: `NeedSplit=True` tự
ép Faster-Whisper xuất từng từ, trong khi dữ liệu native có cue lexical
start=end. GUI TaskFactory nay yêu cầu đầu ra theo câu cho Faster-Whisper,
giữ `need_split` của bước phụ đề và không sửa setting cá nhân. CLI/core khi
yêu cầu word timestamps tường minh vẫn reject các khoảng không hợp lệ;
không bỏ chữ hoặc tăng giả end time để vượt guard. Phân đoạn nhỏ hơn cue câu
vẫn dùng cơ chế ước lượng timing SRT hiện có, không phải word timing native.

pydub tự gọi ffprobe/ffmpeg không có creation flags, còn GPUtil gọi
nvidia-smi không có cờ ẩn. Adapter `core/utils/audio_segment.py` thay riêng
binding subprocess trong pydub để thêm `CREATE_NO_WINDOW` và scrub env;
không patch `subprocess.Popen` toàn app hoặc sửa dependency đã cài. GPU probe
dùng nvidia-smi trực tiếp, chạy ẩn với timeout5s, giữ nhận diện RTX50. Các
đường ASR dùng cùng adapter; mix/TTS đã có cờ ẩn tiếp tục giữ hành vi cũ.

Audit `.tools/batch-sentence-console-20261003/`: video1 từng lỗi word timing
đã qua TaskFactory + TranscriptThread + Faster-Whisper thật87,437s,13 cue,
0 khoảng thời gian lỗi, toàn bộ text non-whitespace từ raw mới được giữ.
Downstream split vẫn bật, preference OneWord và file/settings user không
đổi.9 child calls thực tế đều có cờ134217728 và env đã scrub; test Windows
riêng xác nhận child `GetConsoleWindow()==0`. Không nâng gate nghe/ASR lexical.

Focused45 pass/2 skip; full đầu2362 pass/1 fail/5 skip/58 deselected do child
Qt chụp Style thoát với access violation. Test tạo preview worker nhưng chưa
wait; bổ sung wait trước khi Qt bị hủy, giữ nguyên pixel assertion. Full cuối
**2363 pass/5 skip/58 deselected**,exit0/287,86s; Ruff/Pyright0/0/sync pass.

EXE `VideoCaptioner-20261003-quiet`: build exit0/204,203s,6 WARNING/0 ERROR,
31.684.773bytes,SHA256
`f5b61fcf98ede35d6b35a4ac49ec9e0a44960bd89da807f683dbe8211bdc0884`.
8 module bytecode khớp source,99.315 model/runtime files khớp size manifest.
Frozen ASR replay đúng cache native mới exit0/2,047s, SRT cùng SHA source,
không chạy inference ASR mới. OmniVoice thật một cue Việt, native1x,0 rewrite/
0 speed adjustment/0 review, xuất MP4 exit0/39,110s. Video12s/audio11,989s,
decode exit0/stderr trống, audio RMS2824; đây là smoke ngắn, không phải nghiệm
thu lồng tiếng trọn playlist hay chất lượng nghe. GUI20s/exit0,0 owned children.

Probe EXE đầu có lỗi script: JSON được đưa vào option CLI yêu cầu TOML,
khiến CLI cảnh báo rồi chọn Bijian mặc định; audio mẫu từ video Bilibili
công khai đã được gửi và polling trả HTTP412. Giữ log FAIL, không tính PASS.
Probe sửa dùng `--asr faster-whisper` tường minh và chặn HTTP bên ngoài chỉ
trong env của process test; không đổi proxy/config hệ thống hay bản E.

Đã backup delta và deploy khi E idle:602 file app khớp SHA, chỉ EXE và
base_library.zip thay,1615 file dữ liệu được bảo vệ không đổi; không chép
lại models. Live help exit0, giữ shortcut/tên EXE. GUI/media gates dùng
artifact cùng SHA. Không commit/push hoặc tự chạy lại toàn bộ lô user.
