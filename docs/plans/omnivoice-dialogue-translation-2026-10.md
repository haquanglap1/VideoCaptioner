# Dịch lời thoại và chuẩn bị câu đọc OmniVoice

Ngày: 2026-10-02. Trạng thái: **ĐÃ TRIỂN KHAI CORE/GUI/CLI/EDITOR; NGHIỆM THU CÒN MỞ**.

User đã yêu cầu thực hiện plan. P1–P3 có implementation và tests; P4 đã thử
LLM/GPU trên66 cue của video được chỉ định. Cả hai phương án không đạt timing2s;
chưa có nghiệm thu nghe. [Triển khai, cách dùng và số đo](../dev/dialogue-translation-2026-10.md).
Các mục bên dưới giữ contract/lộ trình; không coi chúng là checklist đã pass.

## 1. Mục tiêu người dùng

Ưu tiên bản dịch tiếng Việt nói tự nhiên, câu trọn ý và ngắt nghỉ hợp lý.
Cho phép lời đọc chậm/trễ hơn thoại gốc một chút, không yêu cầu khớp timing
100%. Đủ ý, đúng lượt thoại và dễ nghe được ưu tiên hơn việc ép từng WAV vào
từng cue SRT. Yêu cầu này mở hướng nới timing so với profile thử trước đây.

User đã chọn thử giới hạn trễ bắt đầu **2.000 ms** trong lượt lập kế hoạch này.
Đã chốt giá trị cho phương án thử; chưa thay settings đang dùng (1.000 ms).
Đây là độ trễ so với mốc gốc, không phải cộng thêm 2 giây ở mỗi câu.

## 2. Những gì đã kiểm tra trực tiếp

| Thành phần | Hiện trạng | Ý nghĩa với kế hoạch |
| --- | --- | --- |
| `core/prompts/translate/standard.md` | Dịch tự nhiên nhưng buộc output theo cue 1–1, không gộp/tách | Đổi prompt đơn thuần không đủ để có đơn vị lời thoại vượt qua ranh giới cue |
| `core/prompts/translate/reflect.md` | Có xét tính tự nhiên và liên kết câu; output vẫn theo từng số cue | Giữ khả năng xét ngữ cảnh, bổ sung contract dành riêng cho lời đọc |
| `core/translate/llm_translator.py` | `_translate_chunk` kiểm đúng tập key, ghi `translated_text`; cache có nguồn/model/config nhưng không có hash nội dung prompt chuẩn | Chế độ mới cần output typed và cache policy/prompt version riêng |
| `ui/thread/subtitle_thread.py` | Split → optimize → translate → xuất phụ đề đích cho dubbing | Split trước dịch chưa đảm bảo ranh giới câu tiếng Việt sau dịch |
| `core/dubbing/planner.py` | Chuẩn hóa xuống dòng thành dấu cách; gộp dựa vào gap, speaker, span và dấu kết câu; span mặc định tối đa 8 s | Xuống dòng SRT không phải lệnh nghỉ; cần dùng ranh giới lời thoại đã duyệt |
| `core/dubbing/models.py` | Đã tách `source_text`, `subtitle_text`, `tts_text`, `cue_ids` và playback timing | Tái sử dụng separation hiện có, giữ trace từ lời đọc về nguồn |
| `core/dubbing/review.py` | Review v1 từ chối một cue thuộc nhiều group | Không nhét các fragment dùng trùng cue ID vào group v1 hoặc bỏ guard này |
| `core/dubbing/vietnamese_text.py` | Gợi ý số/đơn vị/viết tắt theo rule, có cảnh báo mơ hồ | Dùng lại sau dịch; chưa có biên tập toàn câu lời thoại bằng LLM |
| `core/tts/omnivoice/effects.py` | Chỉ thêm silence cuối group theo dấu kết thúc | Chưa điều khiển pause ở từng dấu câu bên trong group |
| `resources/omnivoice/worker.py` | Gửi text, language, reference prompt, speed và steps vào `model.generate` | Timestamp SRT được app lập lịch; model không tự hiểu timestamp của file |
| `core/dubbing/scheduling.py` và `orchestrator.py` | Có sequential, đo WAV thật, trễ tối đa, review khi vượt video | Dùng scheduler hiện có; nới trễ không cần viết lại toàn bộ scheduler |

Đây là khảo sát code, chưa phải tái hiện một câu dịch hoặc đoạn audio thực tế
của user bị lỗi. Không suy kết quả khảo sát thành nghiệm thu chất lượng.

## 3. Hợp đồng lời thoại

### Dịch để nói

- Thêm lựa chọn **Dịch cho lời thoại**. Chế độ dịch phụ đề hiện có tiếp tục
  dùng contract hiện tại; không âm thầm áp lời đọc mới cho các bản dịch cũ.
- LLM đọc một cụm thoại liên tiếp và ngữ cảnh trước/sau, glossary và thông tin
  xưng hô đã xác nhận. Context chỉ để tham khảo, không được phát lại trong
  output. Chia request theo biên lượt thoại/câu; không cắt cứng tại số cue.
- Tiếng Việt rõ, tự nhiên, phù hợp vai nói; tránh văn viết dài dòng và lạm dụng
  thành ngữ/slang không có trong ngữ cảnh. Giữ sự phủ định, điều kiện, con số,
  đơn vị, tên riêng, thái độ và từ lặp có ý nghĩa. Không thêm ý hay tóm tắt.
- Cho phép đổi cách diễn đạt trong bản dịch mới để nói tự nhiên; sau khi user
  duyệt lời đọc, timing/resume không tự rút gọn hoặc diễn đạt lại lời đó.
- Dấu chấm, hỏi, cảm và phẩy phục vụ cấu trúc nghĩa. Không thêm dấu `...` để
  kéo dài, dấu phẩy mỗi vài từ, SSML hoặc nhãn `[pause]` khi chưa có hỗ trợ
  đã kiểm chứng. Không cam kết một dấu phẩy tương đương N millisecond.
- Nội dung nguồn và custom reference được gửi như dữ liệu; không làm theo
  chỉ dẫn nhúng trong subtitle. Không đưa absolute local path vào prompt.

### Tách phụ đề hiển thị và bản đọc

Chế độ lời thoại nên trả về hai phần trong cùng lượt dịch có schema rõ ràng:
`subtitle_translations` giữ mapping 1–1 phục vụ hiển thị; `speech_blocks`
chứa lời đọc liền mạch và danh sách cue nguồn có thứ tự. Dùng model domain
typed để chuyển giữa các tầng, không truyền dict tự do qua pipeline.

- Mỗi cue thuộc đúng một parent speech block; các block theo đúng thứ tự,
  không bỏ cue, không sử dụng lại cue để phát lặp. Các cue chỉ làm context
  không nằm trong membership của kết quả request.
- Một block có thể gồm vài cue của một câu/lượt thoại. Không gộp qua speaker
  hoặc voice đã biết khác nhau, khoảng ngắt/lượt thoại tường minh hoặc mốc
  cảnh được user đánh dấu. Thiếu speaker không chứng minh là cùng người nói;
  nhóm mơ hồ phải hiện để duyệt, không tự nhận diện người từ câu chữ.
- Chia câu đọc theo câu/mệnh đề hoàn chỉnh. Giữ chủ-vị, động từ-bổ ngữ, tên,
  số và đơn vị cùng nhau. Giữ câu đáp ngắn như “Vâng.”; không ép mọi câu dài.
- Khi một block cần nhiều fragment, lưu fragment bên trong parent, kèm span
  của **lời đọc đã duyệt**. Các span phủ đúng một lần toàn bộ text, không mất
  hay lặp từ; parent vẫn sở hữu cue IDs duy nhất. Chốt schema/migration trước
  khi hỗ trợ fragment; không làm lỏng validator của review v1.
- Số/viết tắt được chuẩn hóa trong `tts_text` bằng helper hiện có. Mơ hồ như
  ngày tháng, mã số, `1.234`, tên viết tắt phải được đánh dấu để duyệt.
- SRT chỉ chứa text/timing, không đủ lưu mọi mapping và quyết định lời thoại.
  Giữ plan typed trong RAM; lưu/mở bằng JSON khi user chọn, nối vào workflow
  review hiện có. SRT lời đọc nếu xuất riêng là artifact mới, không ghi đè
  phụ đề hiển thị. Reimport SRT đơn lẻ không được giả vờ còn mapping cũ.
- Phụ đề hiển thị giữ cue IDs và timing nguồn. Nếu cần phụ đề bám audio đã
  tổng hợp thì xuất riêng từ playback timing, ghi rõ đó là timing mới.

Ví dụ minh họa grouping, không phải kết quả LLM đã đo:

| Cue hiển thị | Câu đưa vào TTS |
| --- | --- |
| “Nếu sáng mai trời mưa,” + “chúng ta sẽ ở nhà.” | “Nếu sáng mai trời mưa, chúng ta sẽ ở nhà.” |
| “Còn nếu trời tạnh,” + “mình đi sớm nhé.” | “Còn nếu trời tạnh, mình đi sớm nhé.” |

## 4. Timing và nhịp đọc

- Baseline dùng một reference cố định, batch1, 32-step FP16, native speed1.00,
  pitch0. Native speed1.00 là nhịp tự nhiên của model/reference, không có nghĩa
  thời lượng bằng thoại gốc. Không tự truyền `duration` bằng độ dài cue để ép khớp.
- Câu sau bắt đầu khi đến mốc nguồn hoặc câu trước đã đọc xong cộng gap80ms,
  lấy mốc muộn hơn. Được mượn khoảng im lặng phía sau và nới start delay theo
  giới hạn đã chọn; không tự tăng tốc, cắt đuôi, xóa lời hoặc kéo dài video.
- Đo duration của WAV sau toàn bộ xử lý. Tính trễ từ mốc nguồn của từng parent
  block, kiểm trên toàn chuỗi để phát hiện trễ tích lũy; không reset mốc theo
  câu vừa trễ. Khi gặp khoảng trống đủ dài, lịch tự trở lại mốc gốc.
- Trễ bắt đầu không bảo đảm từng cue bên trong một block khớp miệng. Hiện cả
  end overrun và cảnh báo block quá dài; mục tiêu span8s, cho tối đa12s chỉ
  khi nguồn tiếp câu chưa kết thúc. Cặp cue thật9,664s đã cho thấy cần ngoại lệ
  để tránh tách chủ ngữ/vị ngữ. Không hứa sync từng từ
  hoặc tự bịa timestamp cho fragment tiếng Việt từ tỷ lệ ký tự.
- Mốc chuyển lượt thoại/cảnh tường minh và cuối video là giới hạn cần review
  nếu audio vượt qua. Không bổ sung model nhận diện cảnh/speaker trong scope này.
- Nếu còn cần đọc chậm hơn, thử riêng native speed0.95 so với1.00 trên cùng
  lời đã duyệt; đây là tùy chọn thử tiếp, chưa đổi mặc định. Không dùng FFmpeg
  `atempo` để che một bản dịch/chia câu chưa đạt.
- Trước hết dùng dấu câu và câu đọc mạch lạc. Pause định lượng chỉ triển khai
  sau nếu nghe thật cho thấy cần: đặt silence giữa các fragment text đã biết,
  giữ cùng reference và đo lại tổng WAV. Không chèn/cắt theo vị trí waveform
  ước lượng. Không cộng cả terminal pause và fragment pause trùng nhau.

## 5. Các phase triển khai đề xuất

| Phase | Công việc | Điều kiện qua phase |
| --- | --- | --- |
| P0 — corpus và contract | Chọn một đoạn video/SRT thật2–3 phút, khoảng20–40 lượt thoại; khóa hashes, giọng, LLM, preset, giới hạn trễ; ghi các câu vụn/khó đọc cần sửa | Có before case cụ thể và không thay ASR nguồn |
| P1 — dịch lời thoại | Lựa chọn dialogue, context đọc riêng/owned cue rõ ràng; prompt và schema hai phần; domain model, validator, cache policy; thử cả standard/reflect hoặc từ chối tổ hợp chưa hỗ trợ một cách rõ ràng | Đủ cue, không lặp/đảo, có bản dịch và lời đọc để review; kiểm độc lập các nghĩa quan trọng |
| P2 — câu đọc và review | Tạo/duyệt parent blocks, chuẩn hóa lời Việt, ranh giới câu; ghép vào `prepare_review`; map GUI/CLI/Editor; lưu/mở và invalidation khi user sửa text | Nguồn/timing không đổi; lời đọc duyệt được round-trip; mapping ổn định qua save/cache/resume |
| P3 — timing linh hoạt | Tái dùng sequential/WAV measurement; đưa lựa chọn start delay vào preset user; chặn mốc cứng và báo trễ thực tế | Đủ lời, không overlap/cut-tail, không vượt giới hạn đã chọn; overflow giữ audio và review |
| P4 — kiểm thực tế | A/B trước/sau trên corpus đã khóa, sau đó một video dài nếu clip ngắn đạt; build có prompts/resources rồi kiểm chính artifact | User nghe chấp nhận, native thao tác và EXE đạt riêng; còn fail ở đâu ghi đúng ở đó |
| P5 — tùy chọn sau nghe | Native speed0.95 hoặc fragment pause định lượng nếu có testcase cần | Chỉ triển khai tính năng tương ứng khi nó cải thiện testcase; không coi là phụ thuộc bắt buộc của P1–P4 |

Thực hiện P1 → P2 → P3 theo từng patch nhỏ; không chỉ sửa prompt rồi gọi toàn
luồng hoàn tất. P5 vẫn là tùy chọn sau nghe, không phải tính năng đã triển khai.

## 6. Validation, cache và fallback

- Offline: schema sai/thiếu/extra IDs, đảo thứ tự, ownership trùng, context
  bị lặp vào lời đọc, split giữa số/tên, speaker/voice khác, Unicode, câu đáp
  ngắn, phủ định/từ lặp, dấu hỏi và câu kéo qua biên request. So sánh structural
  coverage không được gọi là bằng chứng dịch đúng nghĩa; nghĩa cần người đọc/nghe.
- LLM phản hồi sai: retry với feedback hữu hạn (tối đa2 lượt sửa), sau đó giữ
  bản nguồn/bản dịch đã có và trạng thái cần review. Không lưu response thiếu
  vào cache thành công hoặc lặng lẽ thay lời đọc lỗi bằng tiếng nguồn.
- Dịch lại selection dùng đúng context snapshot; nếu boundary ảnh hưởng block
  bên cạnh, invalidate các block bị ảnh hưởng và yêu cầu duyệt lại chúng.
  Cancel/network failure giữ kết quả hoàn chỉnh đã có, không xuất thiếu.
- Cache dịch/lời thoại gồm prompt/schema/policy version hoặc hash, purpose,
  nguồn và context fingerprint tất định, glossary, language, endpoint/model,
  config và phạm vi selection. Không lấy output global-context ngẫu nhiên làm
  key. Cache TTS tiếp tục theo text đã duyệt/reference/model/preset/seed/speed;
  có fragment/pause thì bao gồm cả segmentation/pause policy.
- Metadata plan giữ producer/policy và source fingerprints. Lưu/mở kế hoạch
  không gọi lại LLM hoặc tự rewrite. Sửa câu nào chỉ vô hiệu cache phụ thuộc
  câu/block đó và tính lại timeline các câu phía sau.
- Review cũ tiếp tục đúng schema cũ. Chế độ mới cần schema version rõ ràng và
  adapter; trường hợp không thể chuyển đổi an toàn yêu cầu chuẩn bị plan mới.
- A/B ban đầu: cùng source và reference, A là luồng hiện tại, B là dialogue;
  batch1/speed1.00 cố định. Một lượt dịch và một lượt TTS mỗi phương án, giữ
  raw output/hashes/config. Lượt sau chỉ cho lỗi có hypothesis cụ thể; chưa
  đồng thời đổi voice, speed, steps và dấu câu để tránh không biết cải thiện từ đâu.
- Nghe kiểm đầu/giữa/cuối và các ca khó: đủ ý/từ, phủ định/số/tên, không lặp,
  nhịp câu, ngắt nghỉ, xưng hô, giọng cố định. Đo max/p95 start delay, end
  overrun, số group cần review và lời vượt cuối video. Gate thời gian dùng
  WAV thật; không dùng số từ hoặc tốc độ LLM làm bằng chứng.
- Offline, LLM live, GPU/WAV, native UI, packaged EXE, nghe chủ quan và
  whole-video có kết quả riêng. Các gate OCR/ASR cũ không thay đổi.

## 7. Phạm vi file dự kiến và điểm dừng

Phạm vi này là gợi ý cho từng phase, chưa phải allowlist sửa toàn bộ cùng lúc:

- P1: `core/translate/`, prompt dialogue mới trong `core/prompts/translate/`,
  entities/config/cache và test translator/context gần thay đổi.
- P2: `core/dubbing/models.py`, `planner.py`, `review.py`, `engine.py`,
  `vietnamese_text.py`; typed contract mới nếu cần; UI review/task factory,
  thread/CLI pipeline, Editor adapter và test tương ứng.
- P3: `core/dubbing/config.py`, `scheduling.py`, `orchestrator.py`, presets và
  GUI/CLI controls cần thiết; tận dụng những gì đã hỗ trợ start delay.
- Packaging: `VideoCaptioner.spec`/package resources để prompt mới có trong
  source, pip và frozen; giữ translation mirrors nếu chạm chuỗi UI.
- Mỗi patch chạy test gần thay đổi và các quality gates trong AGENTS.md phù hợp
  phạm vi. Toàn pipeline/suite rộng chỉ khi thay đổi schema/data flow cần thiết.

Không sửa ASR/OCR, model/runtime, settings đang chạy, giọng cá nhân, media,
raw evidence hoặc dirty state từ các phase OmniVoice trước. Lượt thực hiện mới
đã được user cho phép code, kiểm LLM/GPU và build artifact riêng; không deploy,
commit/push. Khi triển khai,
snapshot live Git và chốt allowlist nhỏ trước từng patch; quyền lập kế hoạch
không đồng nghĩa các phase đã được triển khai hoặc nghiệm thu.

## 8. Nguồn và hồ sơ liên quan

- [Phân đoạn hiện có](../dev/speech-segmentation-2026-09.md): bảo toàn source,
  chỉ chèn ranh giới; thêm dấu câu thuộc bước dịch/biên tập.
- [OmniVoice P1–P4](../dev/omnivoice-batching-2026-10.md): batch1 ưu tiên,
  chuẩn bị review, helper lời Việt và giới hạn pause cuối group.
- [Sequential hiện có](../dev/sequential-dubbing-2026-09.md): profile thử trước
  dùng trễ1s, giữ đủ lời1x và gap80ms; user nay chọn thử budget2s cho kế hoạch mới.
- [OmniVoice API tại revision đang ghim](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/README.md#python-api)
  và [generation parameters](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/docs/generation-parameters.md):
  text/reference là input; speed nhỏ hơn1 tạo audio dài hơn, duration ghi đè
  speed. [Model code](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/omnivoice/models/omnivoice.py)
  dùng punctuation khi chunk long-form; không có cam kết mỗi dấu câu tạo một
  pause chính xác. Tác động chất lượng tiếng Việt cụ thể vẫn cần đo/nghe.
