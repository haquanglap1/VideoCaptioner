# Lồng tiếng toàn bài giảng — 2026-09-09

User yêu cầu lồng tiếng toàn bộ video 12 phút 51 giây theo bản nhịp đều đã chọn:
OmniVoice với cùng giọng tham chiếu tự sinh, ưu tiên 1,00×, không chồng lời,
giới hạn trễ 2500 ms và LLM rút riêng phần đã đo là quá dài. Giữ video/subtitle gốc.

Evidence và kết quả của job: `build/full-lecture-dubbing-20260909/`.

## Kết quả cuối

- Video **`lecture-vi-omnivoice.mp4`** đã xuất; phụ đề lời thực đọc nằm trong
  `lecture.spoken.vi.srt`. Giữ đủ **151 group / 180 cue**, tốc độ **1,00×**,
  không overlap/cắt lời, độ trễ lớn nhất **2284 ms**, 0 group cần review.
- `render-r2-state.json` và `report-final-r2.json` là trạng thái/report cuối.
  121 group có lời đọc khác subtitle gốc; subtitle nguồn giữ nguyên hash.
  Trường `rewritten_groups` của riêng lượt render bằng 0 vì nạp wording đã
  chuẩn bị từ report trước; không dùng nó làm tổng số rewrite cả job.
- FFprobe: **771,072 s**, video H.264 **2560×1440**, audio AAC mono **24 kHz**;
  **366.792.373 byte**, timestamp local **2026-09-09 17:03:57**.
  SHA-256: `d7a1cd419f6db61c7f34c275359f090eb65df6a6104f828cce2787dc4de0345b`.
- Render exit 0; decode toàn audio bằng FFmpeg exit 0/không lỗi. Worker và
  GPU lease đã đóng. User phản hồi “thôi, tạm ổn rồi”; chấp nhận tạm bản hiện
  tại và dừng chỉnh thêm. Không suy thành đánh giá chất lượng định lượng hoặc
  nghiệm thu đầy đủ workflow GUI/EXE trên mọi video.

## Audio ban đầu

- Resolve video từ source-preflight cũ, đối chiếu SHA-256; dùng SRT Việt đã dịch,
  không chạy lại ASR hoặc dịch. 180 cue được planner ghép thành **151 group**.
- Audio nguyên bản của **151/151 group** hoàn tất: **5 cache hits / 146 synthesis
  mới**, khoảng **204,578 s**; mọi WAV được đo và lưu cache ngay sau từng group.
  Worker/model đóng, GPU lease trả lại. Không chạy lại `prepare_audio.py` từ đầu.
- Tổng audio native **969,65 s** so với video **771,07 s**; **131 group** vượt
  fit ratio 1,05. Đây là thời lượng lời Việt, không phải tỷ lệ lỗi nhận dạng.

## Hoàn thiện từ checkpoint

- Helper mở ô password cho key gateway/`gpt-5.6-terra`, timeout 300 s. Key chỉ
  trong RAM, không ghi chat/file/argv/env. Không tìm key cũ trong log/cache.
- Chỉ các outlier đã đo được gửi LLM, tối đa 2 lần/group; ba request song song,
  TTS tuần tự. Dùng core rewrite/validation/cache, context lân cận từ subtitle
  gốc. Helper giữ model response text/usage riêng trong evidence để có thể
  kiểm tra lỗi JSON mà không gọi lại; không lưu HTTP headers/credentials.
- Ô cũ `finish.py` đã timeout không có key/request. Ô `finish-visible.py` được
  mở lại, center/activate trên màn hình hiện hành; đã nhận input nhưng 260 lần
  gọi dừng tại lỗi mã hóa ASCII (`UnicodeEncodeError`), không có response mới.
  Report không xuất video; cache giữ đủ audio, TTS attempt mới bằng 0.
- Helper `work-dir/full-lecture-finish-retry-20260909.py`, trạng thái
  `finish-state-retry.json`, đã hoàn tất xử lý 131 outlier qua **180 response
  API thành công / 1878,594 s**; 119 wording thay đổi, 165 TTS attempt mới.
  Còn 10 group trễ quá giới hạn nên lượt đó dừng trước khi mix. Ô key kiểm tra
  ASCII/whitespace ngay khi
  nhận input và dừng job khi gặp lỗi credential/Unicode thay vì lặp cả bài.
  Report/checkpoint/response của lượt retry dùng tên riêng để giữ evidence cũ.
- Xác định g-0051 và g-0074 gây dồn lời; Codex rút riêng hai câu, giữ nội dung
  và thuật ngữ, dùng lại 149 WAV. `focused-wording-r2.json` lưu đối chiếu riêng.
  Helper `work-dir/full-lecture-render-r2-20260909.py` nạp nguyên wording đã
  chuẩn bị, **2 synthesis mới / 0 API request**, hoàn tất trong **45,953 s**.
- Một lần chuẩn bị trước render dừng do guard negation nhận cả “chẳng hạn” là
  phủ định. Bản cuối giữ cụm này; chưa thay đổi guard của app trong lượt media.
- Không chạy lại helper trên output đã có. Nếu user yêu cầu sửa đoạn nghe,
  dùng `report-final-r2.json` và cache, chỉ tạo lại group được chỉ định.

Không sửa code app, test hoặc build thêm trong lượt chạy media này. Không commit/push.
