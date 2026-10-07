# Tự căn timing/tốc độ

## Cách dùng

Trong tab **Lồng tiếng**, mở kế hoạch lời đã duyệt và chọn đúng cache chứa WAV
nguồn 1×. Bấm **Tự căn timing/tốc độ**. Hai switch cho phép dùng LLM đang chọn
trong app và cho phép giảm tốc video. Mở tab không gọi mạng. Auto chỉ dùng audio
đã có; thiếu WAV sẽ báo group thiếu, không chạy lại ASR/dịch/TTS.

Bảng tách **Dự báo** và **Đã đo / chọn**, hiển thị tempo/video, thời lượng video,
trễ max/p95, vượt cuối video, vượt biên cảnh/thoại và số nhóm cần review. Chỉ
phương án đã đo và hợp lệ mới bật **Áp dụng** / **Áp dụng / Xem trước**. Có thể
đổi tempo/video/trễ bằng control hiện có; thay đổi bỏ binding Auto và quay về
playback chỉnh tay, vẫn kiểm WAV/video khi xuất. Lời vẫn phải được duyệt riêng.

Chọn **Ghi vào hình (nền đen)** để chữ có hộp đen đặc, che chữ nguồn bên dưới.
Burn-in giữ font/cỡ chữ/màu chữ/vị trí đã chọn, chỉ ép nền đen và padding 6 ASS
units. File style/settings không bị sửa. Phụ đề mềm `mov_text` phụ thuộc player
và không mang cam kết nền đen; dùng burn-in cho kết quả cố định.

## Contract

- Native TTS 1×, một voice tempo 1,00–1,20× và một video speed 0,50–1,00× cho
  cả job. Gap 80 ms, start delay mặc định 2000 ms; giữ control trễ hiện có.
- Solver tất định duyệt lưới 0,01×: với mỗi tempo lấy video speed lớn nhất hợp
  lệ, xếp theo video ít chậm nhất rồi tempo thấp hơn. Không hard-code 0,77.
  Dùng chung `measured_slot` với renderer: làm tròn start lên millisecond,
  giữ silence, source start, hard scene/speaker/overlap boundaries và cuối video.
- Duration dự báo từ WAV nguồn / tempo, cộng 30 ms/group khi đổi tempo. Đây
  không phải số đo WAV dẫn xuất. Validator render đúng tempo được chọn rồi
  probe WAV/video thật; tối đa 3 video thử (giảm 0,01× mỗi refinement trong caps).
  Không render mọi tổ hợp. WAV tempo cache riêng theo native SHA + tempo.
- LLM nhận text dưới dạng dữ liệu và tập candidate typed, chọn đúng ID rồi
  giải thích mật độ thông tin/tên/số/thuật ngữ. JSON strict, không nhận rate,
  text sửa lại hay IDs ngoài allowlist. Budget 1 request + tối đa 2 sửa schema;
  lỗi transport/timeout/missing config chuyển solver ngay, không tự đổi model.
- Dùng `LLMCredentials`, `OwnedLLMRequest(log_content=False)`, contextvars và
  cancellation. Không gửi local paths hoặc đưa key vào argv/env/report.
- Bind nguồn, settings sinh giọng, membership, đủ lời và SHA của 60 WAV native.
  Recheck sau LLM/render và trước export. Cache/path từ report không cấp quyền
  đọc audio. Plan cũ/thiếu WAV/nguồn đổi bị từ chối trước synthesis.
- Không tự rút lời, bỏ nhóm, gán speaker, giả timestamp từng từ, đổi grouping,
  cắt đuôi hoặc tăng tempo ngoài trần. Không feasible thì giữ review/audio.
- Preview và export dùng cùng plan + pipeline hiện có, retime audio nền/caption
  theo cùng video speed. Auto có nút thủ công ở tab Lồng tiếng và tự phục hồi overflow trong Batch;
  CLI flags và Editor schema không đổi. Editor Fast Preview vẫn là nguồn.

Auto plan hiện giữ trong RAM; **Lưu kế hoạch** vẫn lưu review lời như trước.
Sau mở lại app, tính Auto lại từ cùng native cache. Review phải khớp cấu hình
native 1×/sequential hiện tại; không tự migrate checkpoint khác policy/giọng.
Validator timing không xác minh nội dung audio đã đọc đúng từng từ; cần nghe.

## Validation

Audit riêng: `.tools/auto-timing-20261002/`. Baseline master/origin/master
`15ae806652b1ad15e8073817d8aceaec5e094bbd`, hai stash giữ nguyên. Không deploy
bản chính, commit/push, tải/cài model hoặc thay settings/API key.

- Focused đầu 56 pass; sau UI và nền đen 55 pass (suite overlap, không cộng).
  Covers caps/NaN, strict schema/duplicate/unknown ID, bounded retry, timeout,
  cancel, no feasible, hard boundary/silence, source/text/WAV stale, missing
  cache, no-audio/audio, native cache unchanged, preview/export không tempo hai lần.
- LLM thật dùng cấu hình app đọc lại: `gpt-5.6-terra`, timeout 300 s. Receipt
  `live-budget.json` khóa trước request. Một request hợp lệ, không sửa schema.
  Chọn 1,18× / 0,76× vì nội dung dày tên riêng/thuật ngữ/số liệu. Không nâng
  kết luận lexical/ASR: 7 cụm nguồn chưa nghe độc lập vẫn chưa được xác minh.
- Đo selected: video retimed 385,164875 s; max delay 1652 ms, p95 1013 ms,
  end/boundary overrun 0, review 0. Dự báo được lưu riêng trong `live-plan.json`.
- Bản nền đen xuất lại từ video gốc, cùng lựa chọn LLM: 60 cache hit / 0 TTS /
  0 rewrite / 0 review. 8782 frames; video 385,182482 s, audio 385,149002 s;
  lời cuối nằm trong cả hai stream. Decode exit 0, stderr trống.
  `black-media.json` + `black-export-report.json` + snapshots giữ evidence.
  Report cũ `max_end_overrun_ms=2138` đo vượt **cue subtitle end**, không phải
  vượt cuối video; bảng Auto ghi hai hard overrun là 0.
- Source GUI: real QThread tests Apply/Preview/manual/cancel/context pass;
  native Qt snapshots đã đọc lại. Snapshot offscreen trên máy này mất text,
  nên được giữ như probe lỗi; dùng native Qt snapshots để kiểm visual.
  `gui-real-solver.json` còn chạy AutoTimingThread/core thật trên 60 WAV, LLM
  tắt: solver chọn 1,20×/0,78×, đo max1718ms/p951112ms,0 review,23,61s.
  Đây là validation WAV/retimed video, chưa xuất thêm một video hoàn chỉnh hoặc nghe.
- Full offline đầu 2311 pass /5 skip /58 deselected nhưng teardown 1 error
  `WinError 145` trong Windows Temp. Không gọi lượt này PASS. Suite subtitle
  kiểm lại 8 pass /2 deselected với temp trong repo. Full final **2311 pass /
  5 skip /58 deselected**, exit 0, 210,54 s. Ruff toàn app/tests pass,
  Pyright 0 errors/0 warnings, translations in sync.
- Nghe chủ quan và thao tác đầy đủ bằng người dùng vẫn OPEN. EXE/build và
  full final có receipts riêng sau source gates; không lấy receipt cũ làm pass.

## File thay đổi

- Core mới: `videocaptioner/core/dubbing/auto_timing.py`.
- Nối API/cache/validator: `videocaptioner/core/dubbing/engine.py`,
  `orchestrator.py`, `scheduling.py`, `videocaptioner/core/entities.py`.
- Nền đen khi burn-in: `videocaptioner/core/dubbing/playback.py`.
- GUI: `videocaptioner/ui/thread/auto_timing_thread.py`, `dubbing_thread.py`,
  `videocaptioner/ui/components/auto_timing_dialog.py`,
  `videocaptioner/ui/view/dubbing_interface.py`.
- Bundle: `VideoCaptioner.spec` giữ rõ ba module mới.
- Regression: `tests/test_dubbing/test_auto_timing.py`, `test_playback.py`,
  `tests/test_ui/test_dubbing_review.py`.
- Documentation: file này, `README.md`, `status.md`.

Không đổi dependencies, CLI flags, Editor schema, translation resources,
provider implementation hoặc settings/version-control state ngoài allowlist.

## Artifact riêng

`dist/VideoCaptioner-20261002-auto-timing/` build từ `VideoCaptioner.spec`,
exit0/203,563s;6 WARNING cấp build/0 ERROR (thêm7 Python dependency warnings).
EXE31.659.456 bytes,SHA256
`e94a8daa2a838215e972ae3ffdc575b2fc15ef2cd11be3c1cad9a69fc6f0bf3b`.
Timestamp artifact: 2026-10-02 18:49:16 +07:00.
Ba module Auto mới được kiểm trong PYZ. GUI từ chính artifact sống20s,
đóngexit0 và không còn owned children.

Frozen playback probe dùng EXE cùng SHA tại `audit/frozen-runtime`, junction
`_internal`/`models` tới artifact và AppData riêng. Không đưa corpus/cache/key
vào gói phát hành. Giữ các junction test, không dọn đệ quy. Cặp tốc độ lấy
từ lựa chọn source đã đo; không gọi LLM thêm. Đây là gate frozen playback,
không phải kiểm toàn bộ thao tác Auto/LLM bằng GUI EXE.

Frozen CLI help/prepare/render đều exit0, không còn owned children. Render
124,234s,60 cache hit/0 TTS/0 rewrite/0 review; video **cùng SHA256** với source
nền đen `fc70df433cae565ec0b502f8afeeb5bc869884ead3d7d224dc6c363be4eb9be3`.
99.315 model/runtime files khớp size manifest: Faster-Whisper executable và
large-v3/tiny, Qwen, OmniVoice, VieNeu/runtime, OCR-v6-medium. Payload không có
Community-1 riêng; không tải/cài hoặc mở lại gate ASR.

| Gate | Trạng thái và phạm vi |
|---|---|
| Solver | PASS: regression + corpus60 WAV, chọn theo caps/mục tiêu và đo thật |
| LLM | PASS:1 request thật hợp lệ; strict schema/fallback/timeout/cancel có test |
| FFmpeg | PASS: source/frozen byte parity,8782frames,full decode,nền đen,đủ audio cuối |
| GUI | PARTIAL: source real QThread/Apply/manual/cancel tests/native visual pass; thao tác người dùng còn mở |
| EXE | PARTIAL:build/startup20s/frozen playback/cache/bundle pass; Auto/LLM GUI trọn luồng chưa kiểm |
| Nghe | OPEN:chưa nghe duyệt cặp1,18×/0,76× mới; không suy từ timing hoặc bản1,20×/0,77× cũ |

`closeout.json` ghi đủ17 file thay đổi và SHA, HEAD/index/stash, cùng kiểm tra
main EXE/settings và60 WAV gốc giữ nguyên. Không commit/push/deploy.

## Cập nhật bản chính theo yêu cầu tiếp theo

User đã yêu cầu cập nhật EXE chạy thật rồi commit/push. Bản chính tại E đã nhận
đúng artifact Auto timing trên; tên EXE cũ được giữ để shortcut tiếp tục dùng.
602 file app đối chiếu SHA; chỉ EXE và `base_library.zip` cần thay. Backup hai
file cũ nằm trong `.tools/auto-timing-publish-20261002/rollback-payload/`.
1601 file dữ liệu/settings/cookies/giọng/shortcut/manifest giữ nguyên SHA;
model không bị chép lại. CLI help trực tiếp tại bản E exit0.

Không mở GUI thật với settings user trong probe. Gate startup20s/exit0 và
frozen playback sử dụng artifact cùng SHA đã kiểm; không coi việc deploy là
nghiệm thu nghe hoặc Auto/LLM GUI trọn luồng. Phạm vi công bố là17 file phía
trên; source code giữ nguyên SHA so với closeout, chỉ thêm tài liệu triển khai.
Commit/remote/stash cuối được ghi trong audit publish, không sửa raw evidence.


## Sửa hiển thị bảng Auto và nhãn trạng thái — 2026-10-07

User báo lỗi hiển thị ở phần Auto timing. Ảnh chụp native (`QWidget.grab`, không hiện cửa sổ)
cho thấy `AutoTimingDialog` là `QDialog` trần nên giữ palette sáng của Windows, trong khi
`BodyLabel`/`TableWidget`/`PushButton` của QFluentWidgets vẽ chữ trắng theo theme tối bị ép
trong `ui/common/config.py`; toàn bộ chữ gần như không đọc được. Sửa:

- Dialog đặt `objectName` và stylesheet nền/chữ theo `isDarkTheme()` (cùng cách với
  `PlaylistDialog`), ẩn cột số thứ tự, in đậm dòng đã đo, căn giữa số, nút Áp dụng là primary.
- Thêm dòng kết luận (đã đo/chưa áp dụng được/không có phương án) và dịch `decision_source`
  (`llm`, `solver`, `solver-fallback`, hậu tố `+refined`) sang tiếng Việt qua `decision_label`.
- Tab Lồng tiếng: `review_label` thêm dòng "Auto timing đang áp dụng …" sau khi áp dụng và đổi thành
  cảnh báo "đã chỉnh tay" khi tempo/video/trễ khác phương án đo; đóng bảng không áp dụng cũng báo rõ.
- Core/contract không đổi; test GUI mới kiểm stylesheet theo theme, nhãn, dòng đo in đậm và nhãn tab.

## Batch tự phục hồi khi speech vượt khung — 2026-10-04

User chọn giữ đủ lời, chỉ tự căn timing/tốc độ. `DubbingThread(automatic=True)`
bật một recovery trong core sau `DubbingReviewRequired` của speech sequential
đã có đủ WAV, native1× và cache. Không tự vượt checkpoint duyệt lời, chạy lại TTS,
đổi giọng hay rewrite. Provider failure, thiếu WAV và policy khác giữ lỗi gốc.

Recovery dùng lại solver/LLM allowlist và validator đã có, kiểm lại binding rồi
xuất với một cặp rates áp dụng riêng cho job. Một recovery duy nhất; lần đo/xuất
sau còn lỗi thì giữ review. Missing LLM/timeout dùng solver, cancellation và typed
quota/429 truyền ra để Batch dừng đúng admission contract. Tab thủ công vẫn opt-in.

Kiểm video thật còn phát hiện độ chính xác timestamp bị mất khi encode caption
sau retime. Các nhánh encode của playback nay dùng `-enc_time_base:v demux`
cùng `-fps_mode passthrough`, theo [FFmpeg encoder time base](https://ffmpeg.org/ffmpeg.html#Advanced-options).
Bản trước có104 PTS trùng trong16.821 packet; retime stream-copy riêng vẫn sạch.
Probe cùng video với encoder time base từ demux giữ16.821 frame/0 PTS trùng và
full decode0/stderr0. Ba regression hard/soft-resize/resize giữ frame count và
PTS sai lệch dưới1ms; PRE theo command cũ cả3 fail (lệch tới5,167ms), POST pass.

Audit `.tools/batch-auto-timing-20261004/`: tái hiện đúng nhóm
`dialogue-f5d95331215430dd`, end728,321s/video728,182s/vượt0,138s bằng106 WAV
đã có của giọng user. Copy cache trong audit, xác minh identity theo settings,
voice/reference/runtime metadata; cache-only provider chặn synthesis mới.
LLM thật đúng1 request chọn1,18×/0,73×; đo0 end/boundary overrun, max delay546ms.
Giữ nguyên106 group IDs/membership/tts_text,106 cache hits/0 TTS/0 rewrite.
Lượt đầu105,766s; xuất lại cùng proposal sau sửa encoder107,265s,0 request mới.
Output cuối: video768,070250s/audio768,069002s, lời cuối767,791458s,852×480;
full decode passthrough/demux0/stderr0. Settings, source, native WAV và reference
được bảo vệ nguyên hash. Không coi đây là nghiệm thu nghe hoặc lexical ASR/TTS.

Offline cuối:2534 pass/5 skip/58 deselected, chia5 process bao phủ mọi test path,
không bỏ test lỗi. Full một process giữ các lần thất bại: Qt teardown0xC0000005,
UI cancel race, một FFmpeg test child bị kẹt đã dừng có receipt. Fixture hủy
OmniVoice nay giữ transfer tại progress bằng Event tới khi GUI bấm hủy, thay
cho dựa vào sleep5ms; giữ toàn bộ assertions và không sửa product OmniVoice.
Focused417 pass trước encoder,46 pass gồm encoder/cancel cuối; các suite overlap.
Ruff pass với cache ACL warning, Pyright0/0, translations in sync.

Final EXE `VideoCaptioner-20261004-batch-auto-timing-r2`: build0/242,407s,
6 WARNING/0 ERROR,31.751.831bytes,SHA256
`87adb072207ed96984f9639a6c42a63d017ddb63b76c305ce87c2a3f9bfc493c`.
4 runtime modules source-match;99.315 model/runtime files/8 components size-match,
không cài/tải mới. Native GUI Batch dùng fixture3s + cache3,169s + loopback LLM:
tự căn rồi `Đã hoàn tất`,1 LLM/0 TTS,2 lượt cùng1 cache hit, output audio/video/
subtitle và decode0/stderr0, input/native WAV nguyên SHA. Preset đầu sai enum
LLM đã sửa trước workflow; giữ startup diagnostic/timeout, không gọi các lượt
đó là pass. Startup smoke183,501s/exit0/0 survivors; GUI sau workflow xuất đúng
nhưng lúc đóng402,452s exit0xC0000005/0 survivors. Lỗi Qt teardown còn mở,
không tuyên bố đã sửa nó. Native workflow chỉ có LLM loopback; LLM thật là gate source.

Các file của lượt Batch recovery này: `README.md`, `status.md`, tài liệu này;
`core/dubbing/auto_timing.py`, `core/dubbing/engine.py`, `core/dubbing/playback.py`,
`ui/thread/dubbing_thread.py` (đều dưới `videocaptioner/`);
`tests/test_dubbing/test_auto_recovery.py`, `tests/test_dubbing/test_dialogue.py`,
`tests/test_thread/test_dubbing_thread.py`, `tests/test_omnivoice/test_prepare_ui.py`.
Sau bàn giao, user đã đóng app và yêu cầu cập nhật/commit/push. Deploy E có602
file app SHA-match,delta2 đã backup tại `final/rollback-payload/`,12.928 protected
files nguyên hash. Không chép models,giữ tên EXE/shortcut; live CLI help exit0.
GUI/media gate kế thừa artifact cùngSHA. Lỗi Qt shutdown đã báo vẫn giữ nguyên
trong receipt, không đổi FAIL thành PASS. Artifact, output đã kiểm và raw failures
được giữ trong audit; publication receipt nằm trong `closeout.json`.
