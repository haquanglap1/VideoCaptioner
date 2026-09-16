# Rà luồng phụ đề → lồng tiếng → GUI/EXE, 2026-09-09

Tiếp tục snapshot `f510846` trên `codex/asr-s3-native`, working tree đầu lượt sạch.
User chọn rà luồng điều phối với artifact/report/cache đã có để xác định bước
còn phụ thuộc helper. Bản toàn bài đã được chấp nhận “tạm ổn” giữ nguyên.

## Kết quả chính

Core đã có planner, WAV cache, rewrite sau đo audio và lịch đọc tuần tự. Khoảng
trống để tiếp tục một job cần review là **giữ và khôi phục kế hoạch lời đọc trong
GUI**. Có WAV cache chưa đủ để tự chọn lại wording cuối cùng đã duyệt.

Đã sửa một lỗi chuyển tiếp riêng: khi lồng tiếng tắt, GUI từng gửi SRT target-only
dành cho TTS sang synthesis, làm mất layout song ngữ của file hiển thị. Nay dùng
`display_subtitle_path`, fallback về `subtitle_path` khi không có file riêng.
Luồng bật lồng tiếng vẫn đọc file TTS và chuyển file display sang synthesis.

## Luồng đang được GUI sử dụng

| Bước | Đường code | Kết quả rà soát |
| --- | --- | --- |
| Kết thúc tối ưu/dịch | `SubtitleInterface.on_subtitle_optimization_finished` → `HomeInterface.switch_to_dubbing` | Task giữ hai đường dẫn: SRT lời đọc và SRT hiển thị. |
| Chụp cấu hình | `TaskFactory.create_dubbing_config` | Có OmniVoice, giọng mẫu/ngôn ngữ, Natural/sequential, tốc độ chung, giới hạn trễ, LLM timeout và cache. |
| Lồng tiếng | `DubbingInterface.process` → `DubbingThread` → `DubbingEngine` | Core lập group, tra cache, tổng hợp phần thiếu, rewrite outlier và kiểm tra timing trước mix. |
| Cần review | `report_ready` → `_pending_report_data` → `DubbingReportDialog` | Report giữ trong RAM và được hiển thị; không chuyển sang synthesis khi engine báo review. Dialog chỉ đọc, chưa có chỉnh lời/tiếp tục hoặc mở lại report từ file. |
| Mở Video Editor | `_open_in_video_editor` → signal hai đường dẫn → `open_in_editor` | Chỉ chuyển video và SRT, chưa chuyển report, wording đã rewrite, provider identity hoặc liên kết group/WAV. |
| Tạo lại giọng trong editor | `regenerate_selected_voice` → `regenerate_groups` | Có tạo lại selection; chưa nối với kế hoạch của job dừng ở tab Lồng tiếng. |
| Hoàn tất hoặc bỏ qua dubbing | `_on_finished` hoặc `process` | Sau sửa, cả hai chuyển đúng SRT hiển thị sang synthesis. |

`apply_dubbing_report` hiện không có call site trong app; adapter này cũng chưa
khôi phục `tts_text` của group. Không thể chỉ nối thêm signal rồi coi đã resume:
SRT import tạo cue ID khác và một group có thể chứa nhiều cue. Cần kiểm tra ánh
xạ cue/group và giữ ba lớp source/display/spoken text.

`SubtitlePipelineThread` là một đường điều phối khác chưa có call site trong
app ở snapshot này. Test placeholder của nó không được tính là nghiệm thu
pipeline GUI; lượt này kiểm tra đường `HomeInterface`/tab Lồng tiếng đang dùng.

## Đối chiếu artifact thật, không chạy model

Evidence mới: `build/gui-dubbing-handoff-20260909/inspection.json`.
Helper kiểm tra mới nằm trong `work-dir/`; không chạy lại helper hoàn tất media.

- SRT Việt hiện có dựng lại **180 cue / 151 group**; group ID, cue membership,
  text hiển thị và hình học timeline khớp report cuối.
- Cache riêng của bài giảng còn **151/151 WAV cho wording gốc** và **151/151 WAV
  cho wording cuối**. **121 group** có lời cuối khác lời dựng từ SRT ban đầu.
  Kiểm tra key bằng model/voice/provider identity đã ghi, không nạp runtime.
- WAV cuối còn đầy đủ, duration khớp report. Replay policy sequential bằng duration
  đã đo cho lịch đọc khớp report: **1,00×**, không group cần review, trễ tối đa
  **2284 ms**. Không gọi FFmpeg, TTS, LLM hoặc tạo video mới.
- Helper render trước đây nạp wording từ report checkpoint rồi áp hai sửa riêng
  vào g-0051/g-0074 trước khi tra WAV cache. GUI bắt đầu từ SRT hiện chưa thực hiện
  bước khôi phục này. Rewrite cache có key riêng phụ thuộc model, context, style,
  attempt và duration; nó không phải bản lưu quyết định cuối cùng của cả job.
- Cache bài giảng thuộc host nghiệm thu riêng. Source/EXE có AppData riêng theo
  `config.py`; lượt này không chép cache hoặc đổi settings thật để giả cache hit GUI.
- Hash/mtime của video cuối, phụ đề, hai report, trạng thái cuối, EXE và settings
  được kiểm tra giữ nguyên; inventory size/mtime của WAV cache không đổi.

## EXE bàn giao và kiểm tra source

Đọc PYZ ngay trong `VideoCaptioner-ASR-GUIResume-20260909.exe`, không khởi động
GUI hoặc sửa artifact. Bytecode `DubbingInterface.process` khớp source trước sửa.
Chạy riêng method đóng gói với task/signal giả tái hiện việc gửi `spoken.vi.srt`
thay vì `display.vi-en.srt` khi tắt dubbing. Đây là kiểm tra method đóng gói,
**không phải thao tác cửa sổ EXE hay nghiệm thu media**.

- Regression trước sửa: **2 fail / 4 pass**; hai fail đúng ca có SRT hiển thị
  riêng khi config absent/disabled. Lượt test đầu có thêm hai lỗi thiết lập test
  do chưa bật parent settings widget; đã sửa fixture trước khi đo baseline này.
- Sau sửa: **139 passed / 2 warning**, gồm sáu test handoff mới, UI subtitle,
  OmniVoice UI, cooperative stop của DubbingThread và toàn CLI; không skip.
  Test dùng Qt offscreen, QThread thật và engine giả trả report, không provider.
  Thread luôn `wait()` trước khi đóng view.
- Ruff app/tests pass; pyright dùng interpreter Python 3.12 project đã có:
  **0 error / 0 warning**; translations in sync. Không sync/cài dependency.
- Probe ban đầu thiếu đối số của helper và dùng lịch lý tưởng chưa làm tròn
  millisecond nên dừng; đã dùng policy xếp giờ thực tế của orchestrator để đối
  chiếu report. Không đổi tolerance, dữ liệu hay code scheduling của app.
- **Không build mới.** EXE GUIResume giữ nguyên hash
  `6187f8789f577c1def90cd596eda3dc2a817b03883337397046e70cda91a3b90` và **chưa có
  sửa handoff mới**. Gate build/startup/download trước vẫn chỉ thuộc artifact cũ.

## Ca nghiệm thu tiếp theo đã xác định

Ưu tiên tính năng review/tiếp tục trên chính tab Lồng tiếng hoặc Video Editor:

1. Job cần review giữ một kế hoạch có liên kết nguồn, cue/group và cấu hình giọng;
   giao diện hiển thị đúng các nhóm bị trễ, lời gốc và lời đã rút. Nếu chuyển sang
   editor, mutation phải qua `CommandStack`; normal save vẫn theo editor-project-v1.
2. Sửa riêng lời đọc của nhóm đã chọn, giữ phụ đề hiển thị và wording các nhóm
   khác. Tiếp tục tra đúng cache, chỉ tạo WAV cho text/config thực sự thay đổi.
3. Kiểm tra nguồn hoặc cấu hình không còn khớp thì báo rõ, không nạp nhầm kế hoạch.
   Không mở JSON report như một lệnh chạy, không mặc định tin đường dẫn audio.
4. Xếp lịch/đo lại phần cần thiết; nếu vẫn vượt giới hạn thì giữ review. Khi vừa
   khung mới cho phép mix, rồi synthesis nhận file hiển thị đúng layout.
5. Kiểm tra bằng fixture offline và checkpoint hiện có trước. Sau triển khai,
   build tên riêng và nghiệm thu GUI của artifact mới; một workflow media mới là
   gate riêng, không render lại bài giảng đã chốt để tích số pass.

Chưa triển khai resume/review ở lượt rà này. Toàn workflow video qua GUI/EXE,
OmniVoice GUI downloader, gated/người nói và lỗi disk/network thật tiếp tục mở.
Không ASR, dịch, TTS, benchmark, download, render, tìm key cũ, commit/push; OCR dừng.
