# Tài Liệu VideoCaptioner

Thư mục này chứa tài liệu sử dụng và tài liệu phát triển của VideoCaptioner.

## Tài Liệu Nên Đọc

- [Hướng dẫn sử dụng module](MODULE_USAGE.md)
- [Kiến trúc hệ thống](dev/architecture.md)
- [CLI](cli.md)
- [Cấu hình ASR](config/asr.md)
- [Cấu hình LLM](config/llm.md)
- [Cấu hình dịch phụ đề](config/translator.md)

## Chạy Tài Liệu Cục Bộ

```bash
npm install
npm run docs:dev
```

Mở `http://localhost:5173` để xem tài liệu.

## Build Tài Liệu

```bash
npm run docs:build
```

Kết quả build nằm trong `docs/.vitepress/dist/`.

## Cấu Trúc Chính

```text
docs/
├── config/        # Tài liệu cấu hình
├── dev/           # Tài liệu phát triển
├── guide/         # Hướng dẫn sử dụng
├── en/            # Tài liệu tiếng Anh
├── MODULE_USAGE.md
├── cli.md
└── index.md
```

Khi thêm tài liệu mới, dùng Markdown, đặt tên file bằng chữ thường và dấu gạch ngang nếu có nhiều từ.
