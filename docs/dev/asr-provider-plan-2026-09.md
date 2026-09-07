# Nghiên cứu và kế hoạch mở rộng speech-to-text

Ngày kiểm tra: 2026-09-07. Trạng thái: user đã chấp nhận hướng triển khai; chưa triển khai
hoặc benchmark engine mới tại thời điểm bàn giao task đầu.

Kế hoạch thực thi: [các gói triển khai và tiêu chí nghiệm thu](asr-implementation-2026-09.md).
Prompt task đầu: [ASR bước 1](asr-step-1-prompt.md).

Phạm vi đã được user làm rõ: nhận dạng audio/video **tiếng Trung**, chủ yếu để dịch video
Trung; đích dịch trong kế hoạch là tiếng Việt theo ngữ cảnh hiện tại. **Không cần nhận dạng
tiếng Việt.** Tạm lấy tiếng Trung phổ thông làm bộ thử chính; Quảng Đông/phương ngữ và câu
xen tiếng Anh là nhóm kiểm thử riêng khi có trong video thực tế, không giả định tất cả model
đều hỗ trợ như nhau. Chưa đưa live microphone/voice agent vào bản tích hợp đầu. “Miễn phí” ở
local nghĩa là không trả phí API theo phút; vẫn có chi phí máy, điện, lưu trữ và bảo trì.

## 1. Đề xuất lựa chọn

Không có bằng chứng để gọi một model là tốt nhất cho mọi video. Các benchmark do nhà cung cấp
công bố khác nhau về dữ liệu, ngôn ngữ và cách tính lỗi. Cần chấm riêng lời thoại, timestamp,
phân biệt người nói và thời gian sửa phụ đề trên cùng một tập video.

- **Ưu tiên theo yêu cầu:** hỗ trợ đúng videocaptioner.cn qua API tương thích OpenAI.
- **Cloud có timestamp và speaker diarization để thử đầu tiên:** Soniox v5 và ElevenLabs
  Scribe v2. Yêu cầu bổ sung của user: nếu có thể, phân biệt người nói và tránh lẫn ngôi/xưng hô.
- **Cloud tiết kiệm, ít thay đổi kiến trúc:** Groq Whisper large-v3/turbo.
- **Local mới ưu tiên cho tiếng Trung:** Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B;
  ASR 0.6B để so tốc độ và bộ nhớ. Diarization dùng bước riêng khi cần.
- **Giữ chuẩn so sánh local:** Faster-Whisper large-v3 và large-v3-turbo đã có.
- **Căn thời gian dùng lại cho nhiều engine:** ưu tiên Qwen ForcedAligner cho tiếng Trung,
  đối chứng bằng WhisperX/CTC nếu cần. Bỏ nhánh nghiên cứu alignment tiếng Việt và PhoWhisper
  khỏi phạm vi triển khai. WhisperX không phải một model nhận dạng độc lập.

Đây là thứ tự thử nghiệm theo độ phù hợp với dự án, không phải bảng xếp hạng WER đã đo.

## 2. Cloud đáng cân nhắc

Giá USD dưới đây quy về một giờ audio khi có đơn giá rõ ràng, chưa tính thuế, lưu trữ,
phần audio overlap gửi lại, retry hay tính năng phụ. Giá theo token chỉ là ước tính theo
định nghĩa của nhà cung cấp. Giá trực tiếp không phải giá của videocaptioner.cn.

| Dịch vụ/model | Vai trò đề xuất | Timestamp/ngôn ngữ và giới hạn | Giá tham khảo |
| --- | --- | --- | --- |
| Soniox `stt-async-v5` | Thử đầu cho video tiếng Trung, cần phân biệt người nói | Có Chinese; timestamp cho token/subword theo ms, phải ghép thành từ/cue | Khoảng **$0.10/giờ** async; realtime khoảng $0.12/giờ, tính theo token. [Giá](https://soniox.com/pricing), [model](https://soniox.com/docs/stt/models), [ngôn ngữ](https://soniox.com/docs/stt/concepts/supported-languages), [timestamp](https://soniox.com/docs/stt/concepts/timestamps) |
| ElevenLabs `scribe_v2` | Thử đầu cho phụ đề, nhiều người nói, thuật ngữ | Đánh giá trên video tiếng Trung; trả words và speaker ID; cần adapter riêng | **$0.22/giờ** cơ bản; keyterms +$0.05/giờ, entity detection +$0.07/giờ theo bảng giá. [Giá](https://elevenlabs.io/pricing/api), [STT/ngôn ngữ](https://elevenlabs.io/speech-to-text), [API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert) |
| OpenAI `gpt-transcribe` | Đối chứng chất lượng văn bản và thuật ngữ, audio trộn ngôn ngữ | Model hiện được OpenAI khuyên dùng cho file transcription; không dùng request timestamp kiểu Whisper, cần bước alignment cho phụ đề | **$0.27/giờ** ($0.0045/phút). [Model](https://developers.openai.com/api/docs/models/gpt-transcribe), [hướng dẫn](https://developers.openai.com/api/docs/guides/speech-to-text) |
| OpenAI `gpt-4o-transcribe`, `gpt-4o-mini-transcribe` | Quan trọng cho gateway người dùng yêu cầu | Đã thấy trong danh mục videocaptioner.cn; phải hỗ trợ response JSON chỉ có text | Giá gateway tùy model, token và nhóm; chưa xác minh hóa đơn audio thực. [Danh mục](https://docs.videocaptioner.cn/models?type=audio) |
| Groq `whisper-large-v3`, `whisper-large-v3-turbo` | Lựa chọn cloud kinh tế và dễ tích hợp | OpenAI-compatible; `verbose_json`, timestamp word/segment; multilingual | **$0.111/giờ** large-v3; **$0.04/giờ** turbo. Có free tier giới hạn. [API và giá](https://console.groq.com/docs/speech-to-text) |
| Deepgram `nova-3` | Video nhiễu, workload cần tốc độ; mở rộng streaming sau | Hỗ trợ Mandarin và Cantonese theo mã ngôn ngữ; không suy hỗ trợ Chinese của monolingual sang chế độ `language=multi` | Prerecorded PAYG **$0.258/giờ** monolingual; **$0.312/giờ** multilingual, chưa add-on. [Giá](https://deepgram.com/pricing), [ngôn ngữ](https://developers.deepgram.com/docs/models-languages-overview/) |
| Google Cloud `chirp_3` | Đối chứng cloud cho tiếng Trung, triển khai Google Cloud | Có `cmn-Hans-CN`; tính năng theo region/ngôn ngữ; tài liệu giới hạn batch có word timestamps tới 20 phút mỗi audio | V2 standard **$0.96/giờ** ở bậc đầu; dynamic batch standard **$0.18/giờ**, cần kiểm tra cấu hình/region đủ điều kiện. [Model](https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3), [giá](https://cloud.google.com/speech-to-text/pricing) |
| AssemblyAI Universal-3.5 Pro / Universal-2 | Hội thoại và metadata, ưu tiên khi ngôn ngữ phù hợp | 3.5 Pro có 18 ngôn ngữ; Universal-2 có 99 và liệt kê Mandarin Chinese. Kiểm tra đúng model và tính năng cho tiếng Trung | **$0.21/giờ** 3.5 Pro, **$0.15/giờ** U2; diarization +$0.02/giờ. [Giá](https://www.assemblyai.com/pricing), [ngôn ngữ](https://www.assemblyai.com/docs/pre-recorded-audio/supported-languages) |
| Mistral Voxtral Mini Transcribe 2 | Ứng viên đối chứng cho tiếng Trung | Có word timestamps, diarization; Chinese nằm trong 13 ngôn ngữ được hỗ trợ | **$0.18/giờ**. Bản batch này khác bản open-weight Realtime. [API/ngôn ngữ](https://docs.mistral.ai/studio/audio/speech_to_text), [giá](https://mistral.ai/pricing/api/) |

Các gói free/trial cloud có quota và điều kiện riêng; không coi là miễn phí vô hạn.
Bijian/JianYing vẫn có thể giữ cho workflow hiện tại, nhưng không nên làm nền tảng duy nhất
cho khả năng mở rộng ASR của ứng dụng.

## 3. Local và mô hình mở

| Lựa chọn | Điểm phù hợp | Điều cần giải quyết |
| --- | --- | --- |
| Faster-Whisper large-v3 / turbo | Baseline đang có, hỗ trợ GPU và timestamp trong pipeline hiện tại | Đây là model/runtime đã tích hợp, không tính là engine mới. So riêng large-v3 và turbo về chất lượng/tốc độ |
| Qwen3-ASR 1.7B / 0.6B | Model mới ưu tiên thử cho tiếng Trung và phương ngữ; Apache-2.0 | Qwen3-ForcedAligner-0.6B có Chinese và Cantonese, nên phù hợp hơn với phạm vi đã chốt. Kiểm tra riêng từng phương ngữ; ASR hỗ trợ không tự bảo đảm aligner tương đương. [Nguồn](https://github.com/QwenLM/Qwen3-ASR) |
| WhisperX | Pipeline ASR + forced alignment + diarization, có thể cung cấp phần alignment cho ASR khác | Phương án đối chứng alignment tiếng Trung; kiểm tra tên riêng, số, chữ giản/phồn thể, câu xen tiếng Anh và đoạn không căn được. [Pipeline](https://github.com/m-bain/whisperX), [mapping](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py) |
| NVIDIA Parakeet TDT 0.6B v3 | Throughput cao, timestamp từ/câu cho Anh và ngôn ngữ châu Âu | 25 ngôn ngữ được công bố không có Việt/Trung; ưu tiên thấp nếu đây là nguồn video chính. [Model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) |
| Microsoft VibeVoice-ASR | Đáng theo dõi cho bản ghi dài và nhiều người nói; tích hợp speaker/timestamp/text | 9B BF16, nặng hơn đáng kể. Riêng trọng số xấp xỉ 18 GB theo phép tính 9B × 2 byte, chưa activation; không coi RTX 12 GB chạy nguyên bản vừa. Quantization/offload cần đo riêng. [Model card](https://huggingface.co/microsoft/VibeVoice-ASR) |

`status.md` ghi máy nghiệm thu có RTX 5070 12 GB. Đây là cấu hình được ghi nhận trước đó,
không phải phép đo GPU mới trong phiên nghiên cứu. Qwen 0.6B/1.7B đáng làm thử nghiệm trên
máy này, nhưng chưa cam kết VRAM, tốc độ hay tương thích Windows trước khi chạy thực.

## 4. Kết quả kiểm tra videocaptioner.cn

Đã mở console và theo các liên kết công khai tới trang tài liệu/model bằng trình duyệt.
Danh mục audio tại thời điểm kiểm tra có ba model STT chuyên dụng:

- `whisper-1`
- `gpt-4o-transcribe`
- `gpt-4o-mini-transcribe`

Trong chi tiết `gpt-4o-transcribe`, ví dụ cURL công khai xác nhận:

```text
API Base: https://api.videocaptioner.cn/v1
Method: POST
Endpoint: /audio/transcriptions
Authentication: Authorization: Bearer <gateway API key>
Body: multipart/form-data
Fields: file, model=gpt-4o-transcribe, response_format=json, prompt (optional)
```

Nguồn: [chi tiết model và ví dụ gọi](https://docs.videocaptioner.cn/models?type=audio&model=gpt-4o-transcribe).
`/console` là giao diện quản lý, không phải API Base. Key dùng ở đây phải là key cấp bởi
gateway. Các model MiniMax speech, OpenAI TTS, Gemini TTS trên cùng tab audio là tạo giọng nói,
không phải lựa chọn ASR. Model audio chat cần giao thức và cách chấm khác; chưa đưa vào MVP.

Giá hiển thị trong chi tiết model là theo nhóm token, có hệ số khác nhau. Ví dụ nhóm mặc định
hiển thị GPT-4o Transcribe input ¥2.5 / output ¥10 trên 1M token; đây là số trên catalog,
chưa đủ để quy ra tiền/giờ audio hay xác nhận cách tính audio token trên tài khoản cụ thể.

Chưa thấy Scribe, Soniox hoặc Qwen3-ASR trong danh mục audio đã đọc. Không suy ra gateway
chắc chắn không cung cấp chúng qua mọi route; cần danh sách model được key/nhóm thực tế cho
phép trước khi thêm preset. Cũng chưa xác minh `gpt-transcribe` mới trên gateway này.

**Chưa thực hiện:** đọc/copy API key, tạo token, gửi audio, gọi inference có phí hoặc đối chiếu
hóa đơn. Danh mục và cURL là bằng chứng về giao diện được công bố, chưa chứng minh inference
hoạt động trên một token hoặc mọi nhóm giá.

## 5. Những điểm cần thay đổi trong code

Đã đối chiếu mã nguồn, không chỉ dựa trên tài liệu ASR cũ:

1. `core/asr/whisper_api.py` luôn gửi `verbose_json` và word+segment timestamp; parser cần
   `words` hoặc `segments`. JSON chỉ có `text` không đi qua được pipeline này.
2. `core/llm/check_whisper.py` dùng cùng request kiểu Whisper để kiểm tra kết nối. Phải sửa
   cả probe, nếu không GUI có thể báo lỗi dù token/model nhận dạng text hoạt động.
3. `TranscribeConfig`, GUI settings và CLI đã có base/key/model/prompt cho Whisper API.
   Giữ các key/flag này tương thích; thêm provider profile theo hướng mở rộng, không reset
   cấu hình người dùng.
4. `ASR_LANGUAGE_CAPABILITIES` hiện theo engine; cần capability theo provider/model vì
   language, timestamp và diarization không đồng nhất.
5. `ASRDataSeg` hiện có text, translated_text và start/end ms, chưa có speaker ID. Thêm
   metadata tùy chọn mà giữ constructor/call site cũ; rà soát clone/merge/split/export để
   tránh mất metadata. `EditorCue` đã có trường `speaker` được serialize và command sửa speaker;
   tái sử dụng khi đưa ASR vào editor. MVP giữ nguyên `editor-project-v1`, chưa thêm tự gán giọng
   theo speaker. SRT đơn lẻ không bảo toàn metadata người nói như project JSON.
6. Cache của Whisper API chưa phân biệt base URL/timestamp mode; key còn chứa prompt dạng
   thô và được BaseASR ghi log. Khi thêm nhiều gateway/model, chuyển sang fingerprint hash
   có version, provider/base không chứa secret, model, language, prompt, timing mode và
   cấu hình alignment. Không ghi prompt hay key vào tên cache/log.
7. `ChunkedASR` hiện mặc định 10 phút, overlap 10 giây, concurrency 3, dùng
   `submit_with_context`. Tách policy theo engine/giới hạn byte/thời lượng. Provider async
   nên dùng job upload/poll khi hợp lý, tránh tách mọi file theo mặc định cũ; speaker ID
   giữa các chunk không tự động là cùng một người.
8. Kiểm tra MIME/filename theo dữ liệu thật: Whisper API hiện gắn tên `audio.mp3` cho bytes
   dù BaseASR có thể nhận WAV/FLAC/M4A. Đây là điểm cần chuẩn hóa khi mở adapter chung.

## 6. Thiết kế đề xuất

Giữ luồng `transcribe() -> ASRData -> split/optimize -> translate -> subtitle/editor`.
Thêm lớp capability và adapter nhỏ dưới `core/asr/`, UI chỉ điều phối:

```text
Provider + model + credentials
           |
           v
Capability-aware request -> Recognition result
                                  |
                   native timing or forced alignment
                                  |
                                  v
                        ASRData (milliseconds)
                                  |
                         Existing subtitle pipeline
```

Các model mới chỉ trả text cần result trung gian có timing tùy chọn. Chỉ tạo `ASRData` dùng
cho subtitle khi đã có timing hợp lệ. Không gán đều mỗi từ theo độ dài audio và gọi đó là
word timestamp chính xác. Nếu thiếu aligner cho ngôn ngữ đã chọn: báo rõ trước khi chạy;
cho xuất TXT hoặc chọn engine có timing. Không đổi provider có phí âm thầm.

- `capabilities.py` (dự kiến): dataclass/registry cho language, response format, word/segment
  timestamps, speaker labels, hotwords, giới hạn upload, sync/async và chunk policy.
- `openai_compatible.py` (dự kiến) hoặc mở rộng có kiểm soát lớp hiện tại: preset OpenAI,
  Groq, videocaptioner.cn, Custom. Nhận model ID nhập tay; `GET /models` chỉ dùng khi server
  hỗ trợ và không coi thành công của nó là bằng chứng ASR đã chạy được.
- `alignment/` (dự kiến): giao diện nhận audio + text + language + offset; CTC/WhisperX cho
  tiếng Trung để đối chứng; ưu tiên Qwen aligner cho Chinese/Cantonese trong phạm vi tài liệu
  công bố (tối đa 5 phút cho mỗi input alignment). Không áp dụng mặc định chunk ASR 10 phút
  cho aligner. Đánh dấu từ không căn được, không tự tạo timestamp
  giả. Ghim revision model và cấu hình trong một job.
- Adapter Soniox: upload -> submit -> poll có backoff -> đọc tokens -> ghép từ/cue. Dừng polling
  phải phân biệt với hủy job phía dịch vụ. Giới hạn retry tránh upload/tính tiền lặp vô hạn.
- Adapter Scribe: multipart riêng, header `xi-api-key`, `model_id`, lọc loại token audio event
  theo lựa chọn người dùng; không đưa tiếng cười/nhạc thành câu thoại mặc định.
- Runtime local: process/sidecar ẩn, tách Torch/Transformers khỏi Qt và base EXE. Tận dụng bài học
  VieNeu về health check, shutdown, revision, tải theo yêu cầu; không gộp dependency ASR vào
  runtime VieNeu khi chưa kiểm tra tương thích. Chạy tuần tự với VieNeu nếu thiếu VRAM.

Credentials truyền tường minh, không ghi vào `os.environ`. Subprocess dùng argument list và
`child_environment()`. Worker giữ contextvars, cancellation và signal UI đúng thread. Không
truyền đường dẫn local vào prompt hoặc metadata gửi dịch vụ; dùng basename trung tính khi upload.

GUI dự kiến có Provider, Model, Language, Timing, API Base/Key cho cloud; nút kiểm tra model
báo riêng kết nối / nhận dạng / timestamp. Local hiện trạng thái runtime và tải model theo yêu
cầu. Không tự tải nhiều GB hoặc gọi inference chỉ vì người dùng mở trang settings.

### Người nói và cách xưng hô nhất quán (bổ sung theo yêu cầu)

Ba vấn đề cần đánh giá riêng: người phát ngôn, người được nói tới/nói với, và cách dịch đại từ.
Diarization cung cấp nhãn Speaker A/B theo audio; nhãn này không tự cho biết tên, quan hệ hay
người đang được gọi là “you”. Không thể cam kết hết nhầm ngôi chỉ bằng cách đổi ASR.

- **Cloud:** Soniox async hỗ trợ speaker label trên token và khuyến nghị async cho diarization
  do có nhiều ngữ cảnh audio hơn; Scribe trả `speaker_id` trong words khi bật diarization.
  Thử trên cùng bộ hội thoại trước khi chọn mặc định.
  [Soniox](https://soniox.com/docs/stt/concepts/speaker-diarization),
  [Scribe](https://elevenlabs.io/docs/api-reference/speech-to-text/convert).
- **Local/hybrid:** đánh giá `pyannote/speaker-diarization-community-1` cho bước diarization
  độc lập, phối hợp với Faster-Whisper/Qwen hoặc ASR từ videocaptioner.cn. Community-1 chạy
  local/offline sau khi tải; truy cập model cần chấp nhận điều kiện trên Hugging Face.
  Không nhầm bản này với Precision-2 chạy trên server. Chưa tải hoặc thử runtime trong phiên này.
  [Model card](https://huggingface.co/pyannote/speaker-diarization-community-1).
- **Gateway:** ba model đã thấy không được xem là đã có diarization. Nếu dùng chúng, thêm bước
  local nói trên khi bật phân biệt người nói. Sau alignment, gán speaker theo giao nhau của
  thời gian từ/lượt nói; đoạn chồng lời hoặc khó phân biệt phải có trạng thái cần kiểm tra.
  Không bật dịch vụ cloud thứ hai ngầm. Model diarization khác trên gateway phải xác minh riêng.

Thiết kế ngữ cảnh dịch:

1. Giữ `speaker_id` ổn định trong một video; không coi Speaker 1 ở hai request là cùng người.
   Ưu tiên diarize toàn file hoặc gom speaker trên toàn job. Khi thiếu bằng chứng liên kết,
   giữ nhãn chưa xác định thay vì gán chắc chắn. Không gộp câu của hai người khi split/optimize.
2. Cho user đặt tên Speaker A/B, sửa câu bị gán nhầm, gộp/tách nhãn bằng CommandStack.
   Tên/vai trò lấy từ nội dung rõ ràng hoặc user; không suy tuổi, giới hay quan hệ từ âm sắc.
3. Bảng xưng hô có hướng theo cặp người nói → người nghe và có phạm vi cảnh/lượt thoại.
   Ví dụ user xác định A là anh, B là em: A→B dùng “anh/em”, B→A dùng “em/anh”.
   A nói với C có thể dùng “tôi/bạn”. Không gán một đại từ cố định cho A trong toàn phim.
4. Phân biệt lời kể, lời trích dẫn, người nói, người nghe và người thứ ba. Với Trung→Việt,
   kiểm tra câu lược chủ ngữ, đại từ 他/她/它 cùng âm “tā”, danh xưng thân tộc/chức vị và đổi
   cách gọi theo cảnh. Không suy chữ đại từ hay quan hệ chỉ từ âm thanh; dùng ngữ cảnh và
   user override, giữ trạng thái chưa rõ khi bằng chứng không đủ. Người nghe có thể là
   một người, một nhóm hoặc chưa xác định. Không mặc định người vừa nói trước là người nghe.
   Dùng câu trước/sau và ngữ cảnh cảnh phim; trường hợp mơ hồ cho user xem lại, không tự bịa quan hệ.
5. Mở rộng `core/translate/llm_translator.py` và prompt dịch: truyền cue ID, speaker, đối tượng
   được nói với nếu biết, bảng xưng hô và cửa sổ ngữ cảnh cùng text. Hiện `_translate_chunk`
   chỉ gửi map index→text; context hiện là brief chủ đề/tone/glossary, dưới 10 cue còn bị bỏ qua,
   trên 12.000 ký tự chỉ lấy mẫu đầu/giữa/cuối. Brief này không đủ làm sổ nhân vật cho cả phim.
6. Chuẩn bị bản đồ nhân vật/xưng hô có cấu trúc trước khi dịch song song; mọi chunk dùng chung
   snapshot, user override có ưu tiên cao nhất. Dịch lại một vài câu vẫn nhận mapping đã có.
   Khi thiếu mapping mới, đánh dấu cần xem lại thay vì để từng worker tự đổi quy tắc.
7. Cache phụ thuộc fingerprint nguồn, speaker assignments, override, phiên bản policy và phạm vi
   ngữ cảnh tất định. Không đưa output LLM ngẫu nhiên vào cache key. Đổi xưng hô phải làm mất hiệu
   lực kết quả dịch liên quan; không trả lại bản cũ từ cache.
8. Duy trì speaker trong project JSON qua trường sẵn có. Quy tắc xưng hô cần cơ chế persist tùy
   chọn tương thích reader cũ, được kiểm tra trước khi triển khai; normal save vẫn JSON + SRT.
   Export SRT không tự thêm “Speaker A:” vào câu trừ khi user chọn hiển thị nhãn.

Nghiệm thu thêm: hội thoại 2–4 người, đổi người nghe, cùng người nói trở lại sau cảnh dài,
trích dẫn “tôi/bạn”, câu lược chủ ngữ, chồng lời và dịch qua ranh chunk. Đo riêng tỷ lệ câu gán
sai speaker, lỗi ngôi 1/2/3, lỗi người được nhắc đến và lỗi xưng hô trên tập đã gán nhãn.
Kiểm tra save/load không mất speaker, merge không trộn người, override còn hiệu lực khi
dịch lại/đổi model và cache được vô hiệu đúng. LLM kiểm tra lại chỉ là hỗ trợ; người đọc đối
chiếu hội thoại là chuẩn nghiệm thu. Ngữ cảnh riêng không được ghi nguyên văn vào log.

Nếu dịch vụ dịch không nhận metadata/ngữ cảnh, giao diện phải nêu giới hạn của chế độ đó;
không quảng cáo mọi translator hiện có đều bảo đảm nhất quán xưng hô.

## 7. Lộ trình và đầu ra nghiệm thu

Ước lượng sơ bộ cho một người phát triển, chưa gồm thời gian chờ token/service hay gán nhãn
thủ công. Các mốc là phạm vi công việc đề xuất, không phải lịch đã cam kết.

| Mốc | Công việc | Đầu ra/gate | Ước lượng |
| --- | --- | --- | --- |
| A | Chốt bộ audio và kiểm tra giao thức gateway | Gọi thật clip công khai/tổng hợp ngắn cho 3 model đã thấy, tắt cache; ghi format, quota, usage, lỗi; không dùng media riêng khi chưa được chọn | 0.5–1 ngày |
| B | Capability, request/parser/probe, cache và preset gateway/Groq | Whisper cũ không hồi quy; model text-only báo đúng khả năng; config GUI/CLI giữ tương thích | 2–3 ngày |
| C | Alignment tiếng Trung cho model text-only | Thử Qwen ForcedAligner trong runtime riêng với text từ gateway; xuất SRT có timing đã đo, xử lý từ không align được và chunk offset; CTC là phương án đối chứng | 3–5 ngày |
| D | Soniox v5 và Scribe v2 | Adapter native, progress/cancel, speaker metadata trong RAM; xuất SRT vào pipeline/editor đúng | 2–4 ngày |
| D2 | Duy trì người nói và ngữ cảnh xưng hô Trung→Việt | Truyền speaker xuyên pipeline, sửa nhãn trong editor, bảng xưng hô theo cặp/cảnh, dịch lại giữ ngữ cảnh, persistence/cache và đánh giá lỗi ngôi; thử pyannote cho local/hybrid | 4–7 ngày |
| E | Qwen3-ASR local 0.6B/1.7B | Runtime Windows tách riêng, đo RAM/VRAM, cold/warm speed, offline sau tải; GUI không treo, không process sót | 3–5 ngày |
| F | Benchmark video Trung→Việt và build EXE | Chọn default theo lỗi chữ Hán, timing, speaker và bản dịch/xưng hô; smoke từ artifact và một workflow video thật | 1–2 ngày |

Tổng phạm vi ban đầu khoảng 12–20 ngày phát triển; bổ sung D2 đưa ước lượng lên khoảng
16–27 ngày là khung dự trù trước khi thu hẹp ngôn ngữ, cần hiệu chỉnh sau thử nghiệm
alignment/diarization tiếng Trung trên Windows. Không dành thời gian cho ASR tiếng Việt.
Có thể phát hành từng mốc;
**B+C là phạm vi đầu
tiên để đáp ứng model GPT Transcribe của videocaptioner.cn cho phụ đề thực sự**. Với yêu cầu
người nói/xưng hô, ưu tiên D+D2 ngay sau nền capability; có thể đưa D lên trước C để sớm có
cloud với timestamp và speaker native. Mở thêm Google/Deepgram/Voxtral
khi thử nghiệm cho thấy cải thiện đáng kể; chưa cần thêm toàn bộ provider trong một đợt.

## 8. Cách quyết định model nào tốt nhất cho dự án

Chuẩn bị khoảng 30 clip **nguồn tiếng Trung**, tổng 60–90 phút: phổ thông rõ tiếng, giọng
vùng miền, tên nhân vật/địa danh/số/thuật ngữ, video có nhạc, hội thoại chồng lời, khoảng lặng
và câu Trung xen Anh nếu có. Tập chính dùng đúng thể loại video user thường dịch; Quảng Đông
hoặc phương ngữ khác chỉ thêm khi có nhu cầu và báo kết quả riêng. Không cần audio tiếng Việt.
Thêm một video 30–60 phút để kiểm tra độ bền/chunking; không cần đưa toàn bộ vào chấm thủ công.
Reference transcript và timing phải được người nghe kiểm tra, không lấy output ASR/LLM làm nhãn.

Chấm cùng audio, cùng preprocessing; tắt cache khi đo engine, đo cache riêng. Tắt optimize/dịch
để đo ASR thô; sau đó đo end-to-end để biết số phút phải sửa phụ đề. Ghi rõ model/revision,
provider, region, ngày đo, hints, chunk policy và cấu hình máy.

- ASR tiếng Trung ưu tiên CER; thống nhất chính sách dấu câu, số, giản/phồn thể và báo thêm
  lỗi trước chuẩn hóa để không che mất lỗi. Nếu báo WER phải ghi tokenizer. Tiếng Việt chỉ
  được chấm ở đầu ra dịch: đúng ý, đúng ngôi/xưng hô và dễ đọc phụ đề.
- Lỗi tên riêng/số và lời bị thêm trong đoạn im lặng; tỷ lệ bỏ lời/trùng lời tại ranh chunk.
- Sai lệch start/end median và p95 trên các mốc được gán nhãn; tỷ lệ từ không căn được.
- Nếu bật diarization: DER và lỗi gán speaker giữa chunk; không suy speaker ID là danh tính thật.
- Tổng latency kể cả upload/poll/alignment, cold/warm, peak VRAM, chi phí thực trên 1 giờ nguồn.
- Số phút chỉnh tay trên 10 phút video và chất lượng ngắt dòng/câu; đây là tiêu chí sản phẩm chính.

Ngưỡng thử nghiệm ban đầu, chưa phải kết quả đã đạt: 0 timestamp âm/đảo start-end/vượt audio;
p95 sai lệch cue boundary không quá 300 ms trên tập clean đã gán nhãn; không phát sinh câu thoại
trong bộ silence kiểm thử. Ngưỡng tiếng ồn/chồng lời phải báo riêng. Chỉ đổi engine mặc định
khi thời gian chỉnh tay giảm và không có hồi quy đáng kể về timing, độ ổn định, ngân sách.

## 9. Validation khi triển khai

- Unit/contract tests mock response `words`, `segments`, text-only, `diarized_json`, Soniox tokens,
  Scribe words/audio events; thiếu timing không crash kiểu KeyError và không âm thầm bịa timing.
- Lỗi 401/403, 404 model/route, 413, 429/Retry-After, timeout/5xx; retry hữu hạn, cancel,
  cache cách ly provider/model/prompt/alignment, không lộ key/prompt/path trong log.
- Regression chunk overlap/offset, code-switching, config precedence GUI/CLI, `--asr whisper-api`
  và key cũ; test dùng fixture cô lập dữ liệu dev. QThread test phải `wait()`.
- Gate theo repo: ruff toàn `videocaptioner/ tests/`, pyright `videocaptioner/`, CLI tests,
  test ASR/LLM probe/UI/thread gần thay đổi, sync translations; full offline khi thay đổi core
  cross-provider. Online phải báo riêng khỏi offline/skip.
- PyInstaller dùng duy nhất `VideoCaptioner.spec`; update resource/dynamic imports khi cần.
  Kiểm tra artifact, hash, startup và workflow từ chính EXE; runtime local thiếu phải disable
  action có giải thích. Không overwrite artifact hoặc AppData của user để nghiệm thu.

Phiên nghiên cứu này chỉ tạo tài liệu kế hoạch. Không thay đổi code, dependency, settings,
model hoặc artifact build; không chạy test/build vì chưa có implementation mới.
