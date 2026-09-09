# OmniVoice Local — 2026-09-09

User xác định dự án cần tích hợp là [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice),
đồng ý tiếp tục sau khi kiểm tra bản dịch bài giảng. Provider mới là **OmniVoice
Local**, thêm cạnh VieNeu Local, không thay engine/config/model VieNeu.

## Nguồn và phiên bản

- Code upstream **0.2.1**, commit `08be0b4ccbac3e13e374e86fbfead4b4cac343e2`.
  [API Python tại commit](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/omnivoice/models/omnivoice.py)
  có auto voice, voice design, reference audio + transcript, language, speed và
  số bước diffusion. Không giả định một endpoint OpenAI-compatible.
- Model `k2-fsa/OmniVoice`, revision `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`,
  gồm model khoảng 2,45 GB và audio tokenizer khoảng 0,81 GB. [Danh sách ngôn ngữ](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/docs/languages.md)
  có tiếng Việt với mã `vi`.
- Code upstream dùng Apache-2.0; **audio tokenizer có Boson Higgs Audio 2 Community
  License Agreement riêng** trong `model/audio_tokenizer/LICENSE`. Không gọi toàn
  bộ weights là Apache-2.0. Installer giữ các README/license từ model repository.

## Tích hợp

- `core/tts/omnivoice` cung cấp options, cài đặt/verify runtime, owner process và
  adapter `BaseTTS`. Worker nằm ở `resources/omnivoice/worker.py`, chỉ chạy bằng
  interpreter riêng. Qt process không import OmniVoice/torch/CUDA.
- Installer Windows/CUDA dùng Python 3.12, lock export từ upstream (torch và
  torchaudio 2.8.0+cu128, transformers 5.3.0), install có hash vào env riêng.
  Không đổi `pyproject.toml`, `uv.lock` hoặc `.venv` của app. `.gitattributes`
  giữ LF cho dependency lock để hash không đổi theo checkout Windows.
- Runtime mặc định nằm trong local application data, dùng chung source/EXE;
  có thể chọn root riêng. Có ownership marker, OS install lock, download `.part`
  theo Range và kiểm tra Git-blob/SHA-256 của model. Thiếu/hỏng model không thành
  ready. Mở tab chỉ đọc trạng thái, không tải model; Prepare có hủy/resume.
- CLI `--tts-provider omnivoice-local` không cần key. GUI có Prepare / resume,
  runtime directory, language và reference audio/text. Reference thiếu một phần
  bị từ chối; không gọi Whisper hoặc tải model ASR để tự chép lời mẫu.
- Một worker/GPU lease cho toàn job; request tuần tự, timeout/cancel chấm dứt
  worker để tránh dùng nhầm late response cho câu sau. Context đóng process tree
  và hoàn trả config sau job. Có guard không lọc rỗng lời CJK khi chọn tiếng CJK.
- Cache Natural dùng code/model revision, hash worker, language, steps/seed,
  hash reference audio/text; không phụ thuộc đường dẫn giọng mẫu. Bỏ lớp cache
  BaseTTS cũ cho provider này. Audio mono PCM16 WAV 24 kHz, đo duration bằng pipeline
  hiện có; không đặt duration model để ép cắt lời cho vừa khung.
- Giọng `auto`/`male`/`female` là auto/design, chưa bảo đảm cùng người đọc qua mọi
  câu. Dùng reference để ổn định giọng; không tự clone người nói trong video.

## Kết quả trên máy này

Evidence: `build/omnivoice-integration-20260909/`.

- Chuẩn bị runtime/model thật hoàn tất. Lần install đầu vướng ưu tiên index của
  uv với certifi; chuyển `unsafe-best-match` giữa PyPI/PyTorch trong khi vẫn bắt
  buộc phiên bản và wheel hash của upstream lock. Resume thành công; model/hash
  được verify trước job. Không cài package global/app.
- RTX 5070: một câu tiếng Việt lấy từ bản dịch đã được user kiểm tra tạo WAV
  **4,75 s / 24 kHz**, synthesis **1,953 s**, load/verify lần đầu **43,484 s**.
  Process/GPU lease đóng sạch. Đây là một mẫu, không là benchmark toàn model.
- CLI dubbing thật: 30 s đầu video, 6 cue tiếng Việt, dùng chính WAV tự sinh trên
  làm reference cùng transcript; **5 nhóm TTS thành công**, 0 failed. Video h264
  + AAC 24 kHz, **30,033 s**, audio gốc mute. Hai nhóm được tăng tốc; maximum fit
  ratio 1,627, preview chọn **Natural / allow-overlap** để giữ lời, chưa nghiệm
  thu độ khớp timeline/giọng đọc. Không dùng audio người thật làm giọng mẫu.
- `lecture-omnivoice-preview.mp4`: **16.231.195 byte**, SHA-256
  `6f4ecc168d6a571bda1f085bb26832b1f74ae24b541e61fdd8efc35007e759cc`.
  CLI hoàn tất; helper đọc report mặc định cp1252 bị UnicodeDecodeError sau khi
  đã tạo video. Đọc lại UTF-8 xác nhận report/output, không chạy lại TTS đã xong.
- Offline: **204 pass**, gồm OmniVoice, dubbing, CLI, VieNeu integration và
  DubbingThread. Lần đầu fixture chưa có FFmpeg trên PATH và fake Popen bắt nhầm
  taskkill; sửa fixture/phạm vi patch và chạy lại đúng suite. Không sửa media code
  để che lỗi fixture. OmniVoice cuối 10 pass, UI rerun 1 pass; không cộng lặp.
- Ruff app/tests pass, pyright 0/0, translations in sync. Worker có import-type
  suppression riêng vì dependency GPU ở runtime khác; synthesis thật đã đo ở trên.

## Bản EXE

Bản cuối: `dist/VideoCaptioner-OmniVoice-20260909-R2/`. Dùng nguyên onedir;
runtime/model ở managed data riêng, không nhúng weights vào EXE. R2 bổ sung guard
ngôn ngữ CJK theo ngôn ngữ OmniVoice; bản build đầu được giữ nguyên.

Build, hash, GUI startup và frozen workflow được lưu riêng trong evidence. Không
coi build/fixture offline là nghiệm thu lồng tiếng toàn bài giảng 12 phút 51 giây.
Chưa có đánh giá nghe của user, tải/hủy HTTP bằng thao tác GUI thật hoặc workflow
đầy đủ cho các ngôn ngữ khác; không chạy ASR/dịch lại, không benchmark sweep.

Các gate bản R2:

1. PyInstaller **exit 0 / 128,964 s** theo log; **6 WARNING / 0 ERROR**, gồm
   js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip và AppKit như các bản trước.
2. EXE **31.217.674 byte**, **2026-09-09 13:38:12** local, SHA-256
   `492fee8115b09106a22575d58993ef37e6673b37e2b6e25b5107f937e109b9ff`.
3. GUI smoke được lưu trong `artifact-smoke.json`; mở cửa sổ chính từ chính
   artifact, giữ sống 25 s rồi gửi đóng đúng PID, không force.
4. Frozen CLI **exit 0 / 17,937 s**, nạp OmniVoice worker/model thật từ recipe
   đã đóng gói, cấu hình reference; ghép lại preview bằng **5 cache hits / 0 TTS
   generation mới**, output tạo được, không child sót. Đây không phải tốc độ
   synthesis mới từ EXE; speech generation mới đã đo từ source ở trên.

## File thuộc lượt OmniVoice

- Thêm `core/tts/omnivoice/{config,prepare,runtime,provider,__init__}.py`,
  `resources/omnivoice/{worker.py,recipe.json,requirements.lock}` dưới `videocaptioner/`.
- Thêm `ui/components/omnivoice_panel.py`, `scripts/prepare_omnivoice.py`,
  `tests/test_omnivoice/{test_provider,test_ui}.py`, `.gitattributes` và tài liệu này.
- Sửa `core/dubbing/{config,engine,presets}.py`, `cli/{main,config}.py`,
  `cli/commands/dub.py`, `ui/common/config.py`, `ui/task_factory.py`,
  `ui/view/dubbing_interface.py`, `VideoCaptioner.spec`, `README.md`, `status.md`,
  plan ASR và prompt bàn giao. Các thay đổi ASR/dịch trước đó được giữ nguyên.

Không commit/push; không đụng media gốc, runtime VieNeu hoặc cấu hình credential.
