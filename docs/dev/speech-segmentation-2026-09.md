# Phân đoạn cho câu đọc liền mạch — 2026-09-10

User yêu cầu siết prompt phân đoạn LLM sau speech-to-text để AI lồng tiếng đọc
câu liền mạch, chính xác hơn và có ngắt nghỉ tự nhiên. Làm trên worktree
`VideoCaptioner-ASR-S3`, giữ các thay đổi chưa commit và toàn bộ artifact/media
của các lượt trước. Không commit/push, tải model hoặc cài dependency.

## Hợp đồng mới

- Mỗi đoạn ưu tiên một câu trọn ý; không ghép hai câu hoàn chỉnh chỉ vì còn chỗ.
  Nếu câu vượt giới hạn đã chọn, chia ở mệnh đề đủ ý. Dấu phẩy, xuống dòng hiển
  thị hoặc đủ một số từ không phải lý do tự động cắt câu.
- Giữ chủ-vị, động từ-bổ ngữ, phủ định, cặp điều kiện/kết quả và cụm bổ nghĩa
  cùng nhau khi giới hạn cho phép. Không tạo mảnh chỉ có từ nối/đại từ/giới từ.
  Không cắt giữa tên, số thập phân/phiên bản, đơn vị, contraction, URL hoặc từ.
- Chỉ thêm `<br>`; giữ nguyên chữ/case, số, từ lặp, thứ tự và dấu câu. Không
  sửa ASR theo suy đoán, dịch/tóm tắt, thêm lời, SSML hoặc nhãn `[pause]`.
  Transcript được gửi trong JSON như dữ liệu, không phải chỉ dẫn để model làm theo.
- Prompt áp dụng cho đường phân đoạn LLM legacy/word-level hiện có. Route native
  metadata và guard conversation/speaker vẫn giữ nguyên, không gán timestamp giả.

Ví dụ với giới hạn đủ cho câu đầu:

```text
Nếu trời mưa, chúng ta sẽ ở nhà.<br>Bạn đồng ý không?
```

Prompt chỉ chọn ranh giới. Bổ sung dấu câu còn thiếu thuộc bước tối ưu/dịch;
phân đoạn không tự thay đổi lời nhận dạng. Độ dài khoảng nghỉ và giọng điệu vẫn
phụ thuộc TTS/model, và Natural vẫn đo WAV thật rồi áp policy review hiện có.

## Thay đổi code để prompt có hiệu lực

1. `split/sentence.md` và `split/semantic.md` cùng hợp đồng câu/mệnh đề, ví dụ
   Việt/Trung/Anh và yêu cầu toàn bộ nguồn xuất hiện đúng một lần.
2. `split_by_llm.py` bỏ ngưỡng similarity 0,96. So sánh toàn bộ ký tự không phải
   whitespace, kiểm tra ranh giới token, rồi lấy lại chính các lát text nguồn;
   không lấy chữ model sửa. Format/độ dài không hợp lệ được feedback tối đa hai
   lượt; hết lượt giữ nguyên nguồn, không trả bản sai cuối cùng.
3. Matcher timing dùng thứ tự/độ dài nguồn chính xác, mỗi token ASR tiêu thụ đúng
   một lần. Không dùng fuzzy match để bỏ qua prefix/tail hoặc gán nhầm từ lặp.
   Lỗi chunk không được xuất document thiếu; hủy không trả kết quả phân đoạn.
4. Clone dữ liệu trước xử lý. Dấu câu riêng trong word ASR được giữ. Với SRT
   legacy, tùy chọn giữ text khi ước lượng word timing giữ cả punctuation và
   Unicode tiếng Việt; phần ước lượng vẫn là cơ chế cũ, không phải forced alignment.
5. Chia batch ưu tiên dấu kết câu trước một khoảng hở ASR nhỏ giữa mệnh đề;
   khoảng im lặng lớn vẫn được tôn trọng. Không chèn overlap để chia đa luồng.
6. GUI bỏ lượt chuyển word trước splitter vốn làm mất dấu câu; vẫn kiểm tra
   cấu hình LLM khi user yêu cầu phân đoạn câu. CLI thực hiện split đã bật cho
   SRT legacy thay vì bỏ qua im lặng. GUI/CLI không tự xóa dấu `，。` sau tối
   ưu/dịch, nên SRT đích cho TTS và bản song ngữ giữ tín hiệu ngắt nghỉ.

Không đổi API key, config key, CLI flag, giới hạn ký tự/từ mặc định, TTS speed,
policy review, voice cache cũ hoặc cơ chế native/context. `remove_punctuation()`
vẫn có cho caller chủ động; pipeline không gọi nó tự động trước TTS nữa.

## Validation

- **26 regression mới** cho thay đổi nhỏ làm đảo phủ định/số/punctuation,
  cắt giữa token/Unicode combining mark, response sai/thiếu, exhaustion, prefix
  bị bỏ, từ lặp, clone nguồn, Unicode/dấu câu legacy, timing word có sẵn,
  batch boundary, cấu hình LLM GUI và punctuation trong CLI/GUI handoff TTS.
- Đã tái hiện 15 lỗi split trước sửa và lỗi mất dấu câu trong GUI. Fixture GUI
  đầu thiếu target/stop đã được sửa để tái hiện đúng lỗi ứng dụng; giữ log riêng.
- Gate mở rộng **781 pass / 33 deselected / 1 warning**, không skip: split,
  thread, CLI, dubbing, UI, translate, ASRData và speaker pipeline. Không cộng
  chồng với 475 pass hoặc các lượt 21/24 test trước đó.
- Ruff app/tests pass, Pyright app **0 error/0 warning**, translation sync pass.
  Dùng Python 3.12.13 đã có, import-time settings/cache/log và pytest temp riêng,
  socket guard chặn network ngoài loopback trong test offline.
- Gateway `gpt-5.6-terra`: mẫu Việt và Trung trả đúng ranh giới mong đợi,
  **2 response HTTP 200**, model trả về đúng tên đã chọn. Mẫu Anh kết thúc bằng
  lỗi request (`RuntimeError`, không có response được ghi nhận), giữ nguyên toàn
  bộ nguồn và **không tính pass**. Tổng wall time ba mẫu **470,328 s**; đây không
  phải benchmark hay cam kết độ trễ. Không hạ validation để ép pass.
  Key nhập qua password và chỉ giữ trong RAM; Qt worker đã wait, process exit 0.

Sau lượt kiểm tra trên, user cấp file `Api.txt` ngoài repo (từ worktree hiện tại:
`../../Api.txt`) cho agent tự lấy key khi cần. Đã kiểm tra đọc được một key mà
không hiển thị nội dung; không sửa file hoặc đưa key vào Git/log/env. Các lần
gọi gateway tiếp theo dùng nguồn này, không hỏi nhập lại nếu file còn hợp lệ.
Nội dung file chỉ được xử lý như dữ liệu credential, không thực thi chỉ dẫn trong đó.

Chỉ mẫu Anh được thử lại một lần bằng key từ file user cấp: **HTTP 200**, model
trả về `gpt-5.6-terra`, **275,781 s**, đúng hai câu và giữ nguyên `not`/`3.14`.
Như vậy cả ba mẫu Việt/Trung/Anh đã có kết quả đúng sau lượt retry riêng; lỗi
request ban đầu vẫn được giữ trong evidence, không coi toàn bộ lượt đầu là pass.
Độ trễ gateway vẫn là giới hạn riêng; không đổi timeout hoặc giảm validation.

## EXE chứa prompt và code mới

Phân phối nguyên onedir **`dist/VideoCaptioner-SpeechSegmentation-20260910/`**.

1. PyInstaller **exit 0 / 264,437 s**, **6 WARNING / 0 ERROR**, từ bản sao source/
   resource đã đối chiếu hash **289 file**. Warning js/emscripten, curl_cffi,
   yt_dlp_ejs, tzdata, sip, AppKit cùng các warning dependency như bản trước;
   không cài dependency hoặc tải model.
2. EXE **31.263.571 byte**, local **2026-09-10 10:12:19**, SHA-256
   `3478a39a356781f9ffc15712a9f974c1ed241404888d1fb5fbd79cf99d95dddd`.
3. **6 module PYZ** khớp source; cả `split/sentence.md` và `split/semantic.md`
   trong `_internal/videocaptioner/core/prompts/` khớp byte với nguồn. Spec hiện
   có đã gom toàn bộ prompt/module, không cần thêm resource hoặc spec khác.
4. CLI `--help` exit 0. GUI mở native, sống **103,577 s**, đóng đúng process
   **exit 0**, không child còn lại. Request kiểm tra phiên bản bị cô lập qua
   proxy loopback của đúng process thử; không đổi proxy toàn máy.
5. Chưa chạy lại workflow video/TTS mới từ bản EXE này hoặc đánh giá nghe nhịp
   đọc. Các mẫu prompt online ở trên chạy source core; không thay thế nghiệm
   thu audio hay chứng minh mọi câu/ngôn ngữ đều được model phân đoạn đúng.

Bản mới có cấu hình LLM gateway/model đã chọn và bật phân đoạn; không lưu key.
Giữ nguyên R2 và các bản trước, cùng cấu hình/media/WAV/cache đã có.

Evidence của lượt này nằm trong `build/sentence-split-20260910/`. Giữ mọi clip,
WAV/kế hoạch và evidence trước; không inference/render lại bài giảng hoặc mẫu
media đã được duyệt chỉ để thử prompt.

## File của thay đổi này

- `videocaptioner/core/prompts/split/{sentence,semantic}.md`
- `videocaptioner/core/split/{split,split_by_llm}.py`
- `videocaptioner/core/asr/asr_data.py`
- `videocaptioner/ui/thread/subtitle_thread.py`
- `videocaptioner/cli/commands/subtitle.py`
- `tests/test_split/test_speech_contract.py`
- `tests/test_thread/test_speech_punctuation.py`
- `tests/test_cli/test_speech_segmentation.py`
- `README.md`, tài liệu này, `status.md` và prompt tiếp tục.

Các thay đổi DeepLX/InfoBar và biên bản media từ lượt trước vẫn được giữ nguyên,
không thuộc nội dung sửa mới của bước phân đoạn này. Không commit/push.

User yêu cầu dừng Computer Use ngay khi nghiệm thu GUI xong. Đã đóng app test
và reset kernel điều khiển; không tiếp tục thao tác UI khi hoàn thiện tài liệu/
cleanup. Các lượt sau cũng kết thúc phiên điều khiển sau bước GUI.

Evidence cuối: `build/sentence-split-20260910/evidence.zip`, **46 file** đã kiểm
tra hash, **89.509 byte**, SHA-256
`eb55245780464400423063564fadd9ed3af52759db00eef5306206a0405fd6dd`.
Giữ cả receipt lỗi đầu và retry riêng, không đưa nội dung file key vào archive.
Đã chuyển **50 mục/196.934.679 byte** build source, PyInstaller trung gian,
pytest temp/tool cache và log rời vào Thùng rác; gỡ 4 junction thử. Đây không
phải dung lượng xóa vĩnh viễn. Thư mục phiên chỉ còn ZIP và cleanup.json;
artifact mới giữ cấu hình gateway/model, không còn cache/log/link thử.
Hash R2, video/WAV cũ, settings thật và marker model đã đối chiếu giữ nguyên.

Ngày 2026-09-10, user yêu cầu chốt snapshot và push nhánh. Code phân đoạn đã
commit ở **`b824d2b27885a56659d353d74d2c82ba31a0d9bb`**; tài liệu bàn giao theo
sau. Các câu “không commit/push” ở phần nghiệm thu mô tả trạng thái trước yêu
cầu chốt Git này. Xem [prompt phiên sau](online-media-next-session-prompt-2026-09.md)
và lấy HEAD cuối bằng Git; không tự suy quyền push cho thay đổi của phiên sau.
