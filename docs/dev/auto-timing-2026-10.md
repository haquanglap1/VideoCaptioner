# Tự căn timing/tốc độ — MVP source

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
  theo cùng video speed. Auto chỉ nằm trong tab Lồng tiếng/core API ở MVP này;
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
