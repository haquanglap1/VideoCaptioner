# Review/resume lời đọc và hoàn thiện GUI — 2026-09-09

Tiếp tục `f510846` và sửa handoff SRT hiển thị kế thừa. User yêu cầu chia
session để hoàn thành phần còn lại rồi commit/push. Ba session triển khai core,
GUI và downloader; session điều phối kiểm tra tích hợp, đóng gói và chốt Git.
[Plan/session](../plans/asr-completion-sessions-2026-09.md).

## Kết quả cuối

**Các phần triển khai và nghiệm thu GUI của lượt này đã hoàn tất.** Bản cuối
là `dist/VideoCaptioner-ReviewResume-20260909-R6/` (phân phối nguyên onedir).
Review sửa đúng nhóm, lưu/mở lại qua phiên EXE, dùng cache và xuất media đã đo
ở R4/R5; R6 nghiệm thu toàn đường điều phối từ video có phụ đề sẵn tới dubbing
cache và synthesis, giữ đúng hai dòng bản dịch/bản gốc trong track cuối.
Gate nguồn ASR/dịch/giọng thật kế thừa báo cáo trước; không chạy lại inference
đã xong hoặc thay các kết quả chất lượng/RTF lịch sử bằng kết quả fixture.

## Hành vi đã hoàn thiện

- Core giữ `DubbingReview` typed và metadata liên kết nguồn/cấu hình trong report
  v1. Chỉnh `tts_text` riêng group, giữ source/display text và cue membership.
  Resume giữ lời đã duyệt, không tự rewrite, tính cache key và kiểm tra WAV/timing
  lại trước mix. Lỗi/hủy giữ review và các WAV đã hoàn tất.
- Cache JSON lỗi, sai schema hoặc WAV bị cụt được coi là cache miss. Cache nhị
  phân cũ của provider được tắt trong batch synthesis vì thiếu endpoint/runtime
  trong key. Persistent WAV cache vẫn hoạt động; key managed WAV cũ được giữ.
  Các format/endpoint/options unmanaged khác nhau được tách key khi cần.
- GUI thêm duyệt/sửa lời đọc, lưu/mở kế hoạch, nhập checkpoint cũ và tiếp tục.
  Manual mode chọn được SRT hiển thị riêng để mở lại plan từ pipeline sau restart.
  File I/O, hash nguồn và import chạy ở worker. Chỉ sau native QThread completion
  mới mở dialog/thoát busy. Báo cáo thành công chỉ đọc trước pipeline handoff.
- Selector cache riêng chuyển lựa chọn của user qua `DubbingTask.cache_root`
  tới `DubbingEngine`; không lấy path từ JSON, không tự copy cache. Manual và
  pipeline giữ snapshot nguồn/cache khi tiếp tục. Các field mới được thêm cuối
  dataclass để giữ thứ tự positional constructor cũ.
- Checkpoint v1 cũ được nhập bằng thao tác riêng, kiểm tra mọi group/cue/text,
  provider và cache key. Provenance `legacy-user-bound` nói rõ liên kết được tạo
  lúc import; không tuyên bố đã xác minh media lịch sử nếu file cũ thiếu fingerprint.
  Không dùng `audio_path`, duration hoặc fit flags trong JSON để chọn audio/chấp nhận timing.
- OmniVoice giữ partial khi HTTP/socket ngắt, tiếp tục đúng Range; partial đã đủ
  byte được verify trước khi tải, có phục hồi HTTP 416. Kiểm tra disk trước ghi,
  giữ partial khi ENOSPC; repair thất bại không giữ marker Ready cũ. GUI hủy/lỗi
  mở lại controls, bỏ tín hiệu đến muộn và chỉ kích hoạt target sau prepare thành công.

## Kiểm tra source

Python 3.12.13 và tool/FFmpeg đã có trong môi trường project cạnh checkout;
không tạo môi trường mới, cài global hoặc đồng bộ dependency.

| Gate | Kết quả |
| --- | --- |
| Toàn bộ `tests/test_dubbing` | 118 pass, không skip; fake provider/WAV và FFmpeg integration |
| `tests/test_omnivoice` | 27 pass; HTTP loopback 2.210.000 byte, QThread thật, lỗi disk cô lập |
| UI/thread/editor/CLI/VieNeu offline | 333 pass, 1 fail, 1 skip, 10 deselected ở lần đầu; fail duy nhất là assertion kế thừa đếm 4 provider thay vì 5 |
| Sửa assertion provider | 1 pass; giữ kiểm tra Local AI/VieNeu và bổ sung OmniVoice |
| GUI review cuối | 34 behavior tests pass; 10 ca cache mới + 1 ca constructor bổ sung vào 23 ca review/display/scroll/thread đã có |
| Tích hợp sau selector cache / scroll | 129 pass, 10 deselected; toàn `test_ui`, `test_thread`, VieNeu UI, OmniVoice UI và editor voice regeneration; không skip |
| Ruff app/tests, Pyright app, translations | Pass; Pyright 0 error/0 warning. Dùng interpreter chỉ định vì worktree không có `.venv` |

Skip thuộc QtMultimedia trên offscreen; deselected là marker integration/slow/llm.
Không coi các mục này là nghiệm thu online. Các lần test đầu thiếu FFmpeg trên
PATH hoặc fixture sai được ghi và sửa đúng môi trường/fixture; không nới logic
fit hoặc dùng chúng làm bằng chứng pass.

## Kế thừa checkpoint và runtime thật

`build/session-completion-20260909/legacy-checkpoint-replay.json` ghi kết quả
load/validate/import bằng core mới trên checkpoint cuối của bài giảng. Hash
video/SRT khớp preflight đã có; giữ **121 nhóm đổi lời**, đủ **151/151 WAV cache**.
Replay scheduler: **1,00×**, trễ tối đa **2284 ms**, 0 nhóm cần review; cache không đổi.
Không chạy runtime, TTS, LLM, ASR hoặc render bài giảng.

`build/omnivoice-gui-prepare-20260909-s3/reuse-result.json`: source Qt QThread
xác minh và dùng lại model thật **13 file / 3.267.470.260 byte** trong **2,297 s**.
Không download/subprocess/GPU import; metadata file giữ nguyên. Các ca HTTP dùng
loopback/socket thật, không phải tải mới model remote; lỗi disk dùng ENOSPC cô lập,
không cố làm đầy ổ đĩa thật.

## EXE và nghiệm thu giao diện

Bản đầu `VideoCaptioner-ReviewResume-20260909` build **exit 0 / 214,792 s**, có
6 WARNING/0 ERROR của PyInstaller (module tùy chọn js/emscripten, curl_cffi,
yt_dlp_ejs, tzdata, sip, AppKit), cùng SyntaxWarning/deprecation từ dependency.
EXE 31.256.681 byte; SHA-256
`5416ea79160156f32b1fd76ea315219cf628c14fd7d0156e1037d9eb3d22c592`.

GUI native sống **111,717 s**, đóng đúng cửa sổ/process exit 0. Thao tác thật
phát hiện tab chưa có vùng cuộn, đẩy các nút review xuống ngoài màn hình; gate
workflow của bản đầu chưa pass, chưa gửi request TTS hoặc render. Giữ bản đầu
và receipt; thêm ScrollArea theo theme. Regression giữ cửa sổ ở 1050×800 và
cuộn được tới toàn bộ nút Lồng tiếng/review/save/resume; 21 UI review/handoff test
pass sau sửa. Không coi startup pass là workflow pass.

R2 build **exit 0 / 156,793 s / 6 WARNING / 0 ERROR**; EXE 31.257.014 byte,
timestamp local **2026-09-09 19:00:18**, SHA-256
`36261ba39cf01675d56eda3e2c7a01a0db10b5d9bc76352d212e55dc8de9a138`.
Computer Use bị user dừng bằng Escape ngay khi chọn cửa sổ R2, trước thao tác
workflow; chưa có request TTS hoặc render. Process R2 sau đó đóng exit 0, sống
678,335 s; thời gian sống không thay cho nghiệm thu thao tác GUI. R2 chưa chứa selector cache bổ sung.

R3 đã chứa selector cache: build **exit 0 / 146,189 s / 6 WARNING / 0 ERROR**;
EXE **31.258.386 byte**, **2026-09-09 19:11:25** local, SHA-256
`85d5c2015f9169af2e0fedf302f4a3b68364872a839938c261dd79645424410a`.
Đối chiếu bytecode 8 module core/UI/downloader trong PYZ khớp source; đây là
kiểm tra đóng gói, không phải workflow GUI.

Gate CLI R3 `--help` phát hiện lỗi entry point kế thừa: stdout/stderr đã có sẵn
với codec Windows cp1252 không được chuẩn hóa, nên ký tự `→` trong help làm
`UnicodeEncodeError` và cửa sổ lỗi PyInstaller xuất hiện. User cũng gửi ảnh lỗi.
Regression source tái hiện đúng vị trí 784: 1 fail/1 pass trước sửa. Entry point
nay đặt UTF-8 cho cả stream hiện hữu có `reconfigure`, giữ StringIO và giữ sink
cho GUI không có console. Sau sửa, **129 test CLI pass**, gồm 3 regression stream;
Ruff scoped pass.

R4 là bản sửa mới nhất: `dist/VideoCaptioner-ReviewResume-20260909-R4/` nguyên
onedir. PyInstaller **exit 0 / 144,020 s / 6 WARNING / 0 ERROR**; EXE
**31.258.522 byte**, **2026-09-09 19:18:34** local, SHA-256
`3595071618d8bdac3bb496e979140859aa0efd094bad31626986ca33cce358bc`.
Chính EXE R4 với `--help` và `dub --help` đều exit 0, output UTF-8 hợp lệ;
đối số Unicode không hợp lệ trả exit 2 và stderr UTF-8 thay vì crash. Không có
process R4 còn lại. Bytecode 8 module cùng entry point khớp source cuối.
Receipt ở `build/session-completion-20260909/{build-r4,artifact-r4,cli-r4,packaged-source-r4}.json`.
Tại checkpoint trước khi user cho tiếp tục, **R4 mới có gate CLI/import**, chưa
nghiệm thu GUI. Các lượt GUI được ghi riêng bên dưới.

User sau đó xác nhận cho phép tiếp tục GUI. R4 đã chạy bằng cửa sổ thật với
video fixture 12 s, SRT lời đọc/hiển thị riêng và cache do GUI chọn. Hai request
HTTP loopback tạo hai WAV; nhóm 8 s vượt khung 6,42 s dừng đúng để review. Sửa
riêng group 1 thành “Xin chào.” rồi **Lưu kế hoạch**: JSON giữ đúng wording,
group 2, display binding, không có cache path. R4 đóng exit 0 sau **516,742 s**.

Ca này phát hiện thêm tràn ngang khi nhãn lỗi dài làm content rộng hơn viewport.
Status/hint nay xuống dòng, hàng action dùng FlowLayout. Regression đòi horizontal
scroll maximum bằng 0 ở cả width 950/1050, height 800; trước sửa fail, sau sửa
**35 test review/handoff/thread pass**, Ruff/Pyright pass. Kế hoạch và hai WAV được
giữ cho lượt R5 tiếp tục, không gọi lại các request đã xong.

R5 build exit 0/**157,401 s**, 6 WARNING/0 ERROR; EXE **31.258.569 byte**,
**2026-09-09 20:02:53** local, SHA-256
`50a261113dfa7a9fe487cfbd2888c0825678df13176003f7fdb6ce35131a9515`.
GUI mở lại JSON đã lưu từ R4, hiển thị đúng “Xin chào.” và dùng cache riêng;
resume tạo đúng **1 WAV mới**, nhóm kia cache hit. Báo cáo 2 fit/1 cache/0 review/0
failed; video H.264/AAC 24 kHz **12,000 s**, decode audio exit 0. Input video/SRT
giữ nguyên, JSON giữ display binding; receipt `native-media-result.json`.

Trong cùng EXE, OmniVoice Prepare xác minh runtime/model đã cài tới trạng thái
Ready. 13 file/3.267.470.260 byte cùng marker giữ size/mtime, không child GPU;
`omni-gui-before.json`/`omni-gui-after.json`. GUI đóng exit 0 sau **553,866 s**,
không child còn lại; test AppData chuyển riêng vào evidence, EXE hash giữ nguyên.

Một gate khác chạy từ **Tạo tác vụ** qua toàn bộ điều phối GUI với phụ đề song
ngữ được cung cấp sẵn: ASR dùng đường reuse phụ đề, split/optimize/translate tắt;
dubbing **2 cache hits/0 request mới**, rồi tự sang synthesis. Video được mux đủ
3 stream, nhưng extract track cho thấy hai dòng bị đảo so với display SRT.
`native-pipeline-r5-not-accepted.json` giữ expected/actual và `accepted=false`;
không đổi nó thành pass. Process đóng exit 0 sau **562,712 s**.

Nguyên nhân: synthesis đọc lại display SRT thành source/translation rồi áp layout
lần hai. Đã thêm marker layout đầu vào riêng với layout render, truyền qua
producer/Home/factory/worker; helper core dùng chung GUI và CLI hard. File raw
standalone giữ contract cũ, CLI soft vẫn embed trực tiếp. Reexport/ghép lại cùng
file giữ marker phù hợp, đổi file bỏ marker. **54 test mới + 56 test liên quan
pass**; sau tích hợp toàn UI/thread/CLI **302 pass / 10 deselected**, Ruff/Pyright/
sync pass. Lượt R6 bên dưới dùng cache/file fixture mới, giữ toàn bộ output R5
có lỗi để đối chiếu.

R6 **exit 0 / 147,950 s / 6 WARNING / 0 ERROR**; EXE **31.260.697 byte**,
timestamp local **2026-09-09 20:48:55**, SHA-256
`aa1756106900ed3e8070b9fb6cd38927c9269e1b732a091ee4ddd60570d6fb2c`.
Bytecode **15 module + entry** khớp source; CLI help và lỗi đối số Unicode trả
0/0/2 đúng, stdout/stderr UTF-8. GUI native sống **281,840 s**, đóng đúng process
exit 0, không process app/child còn lại. `build-r6.json`, `artifact-r6.json`,
`packaged-source-r6.json`, `cli-r6.json`, `exe-r6-pipeline-exit.json` giữ từng gate.

`native-pipeline-r6-result.json`: GUI tự dùng phụ đề song ngữ đã có, chuyển qua
tab phụ đề → lồng tiếng **2 cache hits / 0 TTS request mới** → synthesis. File
cuối **12,000 s / 36.170 byte**, gồm H.264, AAC 24 kHz và mov_text. Extract bằng
FFmpeg xác nhận đủ 2 cue, **VI ở trên / English ở dưới** đúng display SRT, còn
SRT TTS chỉ có VI. Đây là workflow GUI với dữ liệu đã chuẩn bị, không phải
ASR/LLM/TTS inference mới. Output R5 sai thứ tự vẫn giữ riêng.

Model OmniVoice, video/checkpoint bài giảng và settings thật giữ nguyên theo
các kiểm tra hash/metadata. HTTP fixture đã dừng; test AppData của R6 chuyển
nguyên sang evidence `artifact-test-AppData-r6`, giữ EXE hash, để artifact không
mang cấu hình API/cache giả của ca thử.

## Đối chiếu các mục của plan gốc

| Mục | Bằng chứng và trạng thái |
| --- | --- |
| 1. Giữ transcript / TXT riêng | Kế thừa source/CLI/GUI và frozen TXT trong các báo cáo SentencePrep/ResumeGuard; regression CLI/UI liên quan pass trong gate tích hợp hiện tại |
| 2. Timestamp câu và chuyển LLM | Kế thừa 180 cue (164 Qwen + 16 Whisper), CLI source/frozen cached và dịch đủ 180 cue giữ timing; không gọi lại inference đã hoàn tất |
| 3. Chuẩn bị model | GUI source tải mới Qwen 0.6B, ForcedAligner source/EXE HTTP cancel-resume đã đo; OmniVoice runtime/model đã tải thật trước đó, reuse và lỗi transport/disk được bổ sung ở session 3 |
| 4. File dài / stall | Kế thừa bounded requests, EOS/retry và cache chunks; không đổi kết quả CER/RTF lịch sử. Mốc RTF ≤ 0,25 vẫn là mục tiêu chưa đạt, không được công bố thành SLA |
| 5. Người nói | Tùy chọn theo plan, giữ behavior lỗi không làm mất timed subtitle; gated model và chất lượng speaker vẫn là gate riêng chưa nghiệm thu lại |
| 6. Đóng gói / workflow GUI | R6 build/startup/CLI và GUI điều phối với dữ liệu có sẵn đã pass; track video cuối giữ đúng layout; fresh inference không được suy từ gate này |
| Handoff lời đọc / WAV cache | Replay 151 WAV/121 wording sửa; GUI sửa/lưu R4 → mở lại/resume R5 đúng cache, chỉ tạo một WAV mới; pipeline R6 dùng 2 cache hit |
| Commit/push | User yêu cầu chốt snapshot theo từng phần lên `origin/codex/asr-s3-native`; Git HEAD/tracking là nguồn trạng thái khi bàn giao |

Ưu tiên thực dụng và phạm vi dừng benchmark/OCR đã chốt trong plan gốc tiếp tục
có hiệu lực. Các mục chưa có bằng chứng được giữ đúng trạng thái, không đổi thành
pass chỉ vì code/test mới đã hoàn tất.

## File thay đổi của các session

- Core: `videocaptioner/core/dubbing/__init__.py`, `cache.py`, `engine.py`,
  `models.py`, `orchestrator.py`, `planner.py`, `review.py` trong cùng thư mục;
  `videocaptioner/core/entities.py`; `tests/test_dubbing/test_dubbing_review.py`.
- GUI: `videocaptioner/ui/task_factory.py`, `ui/thread/dubbing_thread.py`,
  `ui/view/dubbing_interface.py`, `ui/components/dubbing_review_dialog.py` dưới
  `videocaptioner/`; `tests/test_ui/test_dubbing_handoff.py`,
  `tests/test_ui/test_dubbing_review.py`, `tests/test_thread/test_dubbing_thread.py`,
  `tests/test_vieneu/test_ui_thread.py`.
- Downloader: `videocaptioner/core/tts/omnivoice/config.py`, `prepare.py` cùng
  thư mục, `videocaptioner/ui/components/omnivoice_panel.py`,
  `tests/test_omnivoice/conftest.py`, `test_prepare.py`, `test_prepare_ui.py` cùng thư mục.
- Đóng gói: `VideoCaptioner.spec`, `scripts/pyinstaller_gui.py`,
  `tests/test_cli/test_packaged_entry.py`.
- Layout synthesis: `videocaptioner/core/subtitle/synthesis.py`,
  `videocaptioner/ui/thread/video_synthesis_thread.py`,
  `videocaptioner/ui/view/home_interface.py`, `videocaptioner/ui/view/subtitle_interface.py`,
  `videocaptioner/ui/view/video_synthesis_interface.py`,
  `videocaptioner/cli/commands/process.py`, `videocaptioner/cli/commands/synthesize.py`,
  `tests/test_thread/test_synthesis_layout.py`, `tests/test_cli/test_synthesis_layout.py`;
  dùng chung các file entities/task_factory đã liệt kê phía trên.
- Tài liệu: `README.md`, `status.md`, `docs/dev/asr-completion-next-session-prompt.md`,
  `docs/dev/natural-dubbing.md`, `docs/dev/dubbing-gui-handoff-2026-09.md`,
  `docs/dev/dubbing-review-resume-2026-09.md`, `docs/plans/asr-completion-2026-09.md`,
  `docs/plans/asr-completion-sessions-2026-09.md`.

## Phạm vi và giới hạn

ASR thực dụng, dịch và audio OmniVoice thật kế thừa các báo cáo trước. Bản lồng
tiếng user đã chấp nhận giữ nguyên. Không mở lại benchmark corpus, key/API cũ,
gated model/người nói hoặc OCR. Nghiệm thu fixture không là đánh giá chất lượng
giọng, API thật, tốc độ inference, disk-full vật lý hoặc cài model trên máy khác.
Không thêm dependency/resource GPU, không đổi schema editor, không merge master
hoặc tạo tag/release. Build/dist/media/model/cache không đưa vào Git.
