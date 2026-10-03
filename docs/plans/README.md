# Trạng thái các plan của VideoCaptioner

Rà soát ngày **2026-09-29**. Dùng trang này để chọn plan đang áp dụng;
[status.md](../../status.md) giữ lịch sử thay đổi và validation theo ngày.
Các số đo trong tài liệu liên kết thuộc đúng lần chạy/artifact được ghi ở đó;
không suy validation offline thành nghiệm thu chất lượng nhận dạng.

## 2026-10-03 — Batch nhiều video đồng thời

- Điều phối theo công đoạn, giới hạn video/ASR/subtitle/TTS/export, chung số luồng LLM và một suất GPU.
- [Kế hoạch triển khai và các gate](concurrent-batch-2026-10.md).

## 2026-10-02 — kế hoạch dịch lời thoại cho OmniVoice

- **Đã triển khai, nghiệm thu còn mở**: thêm cách dịch lời thoại, chuẩn bị câu đọc liền mạch sau dịch,
  giữ mapping với phụ đề nguồn và dùng sequential timing có giới hạn trễ.
  User ưu tiên lời nói tự nhiên, cho phép chậm hơn thoại gốc một chút.
- [Kế hoạch, khảo sát code, contract và các phase](omnivoice-dialogue-translation-2026-10.md).
  User đã chọn thử trễ tối đa2s; preset áp riêng cho job kịch bản, settings cũ giữ.
  A/B trên đoạn150s cần khoảng199s/208s lời đọc, cả hai chưa đạt timing2s.
  [Triển khai và kiểm chứng](../dev/dialogue-translation-2026-10.md).

## Tiến triển mới nhất — TTS tuần tự giữ đủ lời ở 1×

- Đã kiểm/sửa đường Natural sequential hiện có với speed/cap 1×, trễ 1000 ms,
  rewrite tắt, gap 80 ms. Giữ lời lặp có chủ ý; sửa export mất đuôi khi audio gốc
  ngắn hơn video và đo đúng video stream khi audio dài hơn. Vượt giới hạn giữ
  review/audio, không tự rút lời/tăng tốc/kéo dài video; cache/resume giữ contract.
- **201 targeted pass/0 skip**, 30 ca mới, fake TTS và FFmpeg fixture ngắn;
  Ruff/Pyright scoped pass. Nghe thật/native/EXE chưa nghiệm thu. Không nhận
  dạng mới, không đổi các gate OCR/ASR, commit/push hoặc settings/Pages.
  [Báo cáo và evidence](../dev/sequential-dubbing-2026-09.md),
  [cách chọn cấu hình](../dev/natural-dubbing.md#đọc-lần-lượt-không-chồng-lời).

## Mốc 29/09 — giữ các dòng raw ASR SRT trong text gốc

- Parser import SRT tự đoán song ngữ từng chuyển dòng lời thứ hai sang
  `translated_text`. Đã tái hiện bằng SRT tổng hợp; ba đường raw ASR (Faster-Whisper,
  whisper.cpp, Whisper sentence fallback) nay tắt đoán song ngữ, giữ đủ lời/ms/lặp.
  Import SRT người dùng và raw cache giữ hành vi cũ.
- **10 fail/2 pass baseline;83 targeted pass sau sửa**, gồm16 ca mới;
  Ruff/Pyright scoped pass. Audit `.tools/asr-srt-20260929-093753/` giữ cả lỗi
  fake-cache fixture ban đầu. Đây là offline data-flow proof, không lexical D1/D3.
- User đã yêu cầu chốt sửa SRT; xem Git live/receipt publication trong bàn giao
  để lấy SHA sau push. Hai sửa coverage/merger ở `69803d7` đã publish trước đó.
  [Bàn giao](ocr-asr-quality-next-session-2026-09.md) và
  [evidence/gate](../dev/ocr-asr-quality-first-results-2026-09.md).

Ưu tiên TTS độc lập đã được thực hiện ở mục mới nhất phía trên; còn nghiệm thu
nghe bằng provider/voice đã chọn. Không đóng gate OCR/ASR hoặc mở whole-video.
Xem [contract và bàn giao](ocr-asr-quality-next-session-2026-09.md).

## Mốc 2026-09-28 — giữ lời ở các mốc riêng khi merge

- `ChunkMerger` từng xóa lần nói khác thời điểm vì text trùng ở rìa hai chunk.
  Guard mới nối nguyên các span không overlap; giữ matcher cho overlap thật.
  **7 fail/2 pass trước sửa;55 targeted pass sau sửa**, gồm12 regression mới.
  Sửa sáu fixture có timestamp sai, tăng ca10 chunk thành kiểm đủ32 câu/ms.
- Giữ nguyên bản sửa coverage27/09. User yêu cầu chốt hai sửa vào master29/09;
  xem [mốc Git và prompt tiếp theo](ocr-asr-quality-next-session-2026-09.md).
  Audit sửa merger `.tools/asr-merge-20260928/`. Không inference, không chứng minh lexical D1/D3
  đã sửa, không mở lại cap. [Evidence và gate](../dev/ocr-asr-quality-first-results-2026-09.md).

## Mốc 2026-09-27 — coverage audio và kiểm tra Pages

- Sửa `ChunkedASR` bỏ đuôi audio dưới 1 giây: giữ phần đuôi trong chunk cuối
  trước khi encode, gồm sample lẻ dưới 1 ms. Giữ số chunk/offset/overlap;
  chunk cuối có thể dài hơn mức danh nghĩa dưới 1 giây. **59 targeted tests pass**,
  có FFmpeg thật + fake provider, không nhận dạng mới. Đây là sửa coverage ở
  tầng app, **không sửa lỗi nội dung Qwen D1/D3**. [Evidence và gate](../dev/ocr-asr-quality-first-results-2026-09.md).
- CI `36331752246` tại `ee972d1` **success**. Docs run `36331752245` build/upload
  **success**, deploy **fail 404**. Kiểm read-only xác nhận repo `has_pages=false`,
  Pages API 404 với quyền admin: Pages chưa được bật. Chưa đổi workflow/settings
  hoặc rerun. Nếu muốn xuất bản, user quyết định bật Pages với source **GitHub Actions**.
- Mốc27/09 chưa commit/push; coverage và merger đã publish29/09 tại `69803d7`.
  Tiếp tục từ Git live, giữ audit `.tools/asr-coverage-20260927/` và attempt cap.

## Các plan và phần còn mở

| Plan | Trạng thái đã ghi nhận | Phần còn mở / tài liệu tiếp tục |
| --- | --- | --- |
| [OCR/ASR quality-first](ocr-asr-quality-first-2026-09.md) | Đã triển khai một phần, không còn PLAN ONLY. Tracking v2/v3, consensus punctuation-v2, candidate PaddleOCR-VL và sửa UI checkpoint đã có; chưa đổi mặc định nhận dạng. | **P1/P2 unresolved; D3 content FAIL**, D1 onset unresolved. D2 saved-data native pass chỉ chứng minh luồng dữ liệu đã lưu. P3 chưa có nghiệm thu native đầy đủ với kết quả mới; P4 holdout/whole-video/EXE và P5 translation/TTS chưa mở từ pilot này. |
| [Bàn giao OCR/ASR](ocr-asr-quality-next-session-2026-09.md) | Coverage/merger đã publish; sửa raw SRT29/09 đã kiểm offline và được yêu cầu chốt Git. Ưu tiên tiếp theo là TTS tuần tự1x trên sub có sẵn. | Numerical frontend **NOT PASS**, real-model cache parity **UNKNOWN**. Giữ attempt cap và các kết quả thất bại; không chạy lại nhận dạng chỉ vì chuyển sang master. Xem [kết quả](../dev/ocr-asr-quality-first-results-2026-09.md). |
| [Tích hợp OCR video](video-subtitle-ocr-integration-plan.md) | Luồng CLI/GUI, checkpoint, direct export, cache/resume, v6 medium và chọn dòng đã triển khai. | Đánh giá chất lượng tiếp tục ở quality-first phía trên. Auto-accept chưa hiệu chuẩn, downloader và mở rộng vision chưa được coi là hoàn thành. Các đoạn yêu cầu review bắt buộc ở lịch sử đã được thay bằng direct export. |
| [Hoàn thiện ASR/OmniVoice](asr-completion-2026-09.md) | Phạm vi bài giảng và các session R6 đã được chốt; Qwen + Whisper fallback, OmniVoice, review/resume và handoff GUI đã có. | Không mở lại bản bài giảng đã được chấp nhận. Chất lượng/RTF trên corpus khó, speaker/xưng hô, gated model và nghiệm thu rộng trên máy khác còn giới hạn; xem [báo cáo R6](../dev/dubbing-review-resume-2026-09.md). |
| [Session ASR/OmniVoice](asr-completion-sessions-2026-09.md) | Bốn session triển khai đã hoàn thành trong phạm vi R6. | Đây là bảng closeout lịch sử; không tiếp tục theo chỉ dẫn Git của nhánh cũ. Không suy fixture/cache thành fresh online inference. |
| [Natural Dubbing](natural-dubbing-end-to-end-plan.md) | P-1 đến P8 machine complete theo biên bản 21/08; review/resume và sequential timing được bổ sung trong tháng 9. | Subjective listening, chất lượng provider và video đa dạng không tự thành pass từ test offline. Danh sách CapCap follow-up là backlog lịch sử, phải đối chiếu tính năng đã có trước khi triển khai. |
| [Video Editor](video-editor-tab-integration-plan.md) | E0–E7 machine complete; style/preset/nền bo góc và handoff đã có trong code hiện tại. | UX chủ quan, âm thanh provider thật và tập video đa dạng có ranh giới nghiệm thu riêng. Giữ schema, stable IDs, CommandStack và cùng filter graph cho preview/export. |
| [VieNeu one-app](vieneu-one-app-integration-plan.md) | V0–V5 implemented/machine-validated. Bản sửa portable tháng 9 giữ native DLL trong `.libs` cho scikit-learn/NumPy. | Giữ subjective listening riêng; giant single self-extracting EXE vẫn deferred. Xem [runtime/build/update](../dev/vieneu-one-app.md) và status 21–23/09; smoke runtime không đóng gate chất lượng OCR/ASR. |
| [Lộ trình ASR S1–S6](../dev/asr-implementation-2026-09.md) | Các bước triển khai và smoke S1–S5.2, phép đo S6 đã được ghi nhận; câu “chưa triển khai” trong [nghiên cứu ban đầu](../dev/asr-provider-plan-2026-09.md) là lịch sử. | S6 chưa đạt nghiệm thu sản phẩm; native online, phồn thể strict, speaker/xưng hô và corpus khó giữ giới hạn trong báo cáo. Các yêu cầu thực dụng sau đó nằm trong plan ASR/OmniVoice và quality-first. |

## Chuẩn hóa nhánh về master

Phạm vi user chọn: gộp các nhánh `codex` hiện tại vào `master`, giữ nguyên các
nhánh lịch sử/upstream. Đối chiếu sau `git fetch origin --no-prune`:

| Nhánh nguồn | Tip trước đồng bộ | Quan hệ với master trước đồng bộ |
| --- | --- | --- |
| `codex/asr-s1-api-profiles` | `43bb76f` | Đã là ancestor của `62abaca`; không còn commit riêng cần gộp. |
| `codex/asr-s2-alignment` | `d21251a` | Đã là ancestor của `62abaca`. |
| `codex/asr-s3-native` | `bed964e` | Đã là ancestor của `62abaca`; worktree riêng sạch và được giữ nguyên. |
| `codex/vieneu-one-app-editor-ui` | `3bef9fe` | Đã là ancestor của `62abaca`. |
| `codex/ocr-asr-quality-pilot` | `e2e7863` | Đi trước `62abaca` đúng 23 commit; master không có commit riêng. Bổ sung commit sửa portable `6a6fcd1` và mục lục plan trước khi fast-forward master. |

`master` là điểm bắt đầu chung sau đồng bộ. Các nhánh nguồn vẫn giữ lịch sử;
không cần ép tất cả branch tip bằng nhau để đưa toàn bộ công việc vào master.
Hai stash và các worktree khác được giữ nguyên. Không merge nhánh lịch sử,
không force-push, xóa nhánh hoặc áp/pop/drop stash trong lần này.

## Tiếp tục công việc

1. Đọc trang này, mục mới nhất của `status.md`, rồi báo cáo domain tương ứng.
2. Kiểm tra Git live; các SHA, branch và quyền của session cũ chỉ là mốc lịch sử.
3. Với OCR/ASR, bắt đầu từ bàn giao quality-first mới nhất; giữ riêng OCR text,
   speech text và translation. Thiếu listening reference vẫn ghi unknown.
4. Bản đồng bộ Git chỉ bổ sung regression/static validation. Không dùng nó để
   đóng gate native GUI, packaged EXE, real GPU/provider hoặc chất lượng nội dung.
