# 架构设计

VideoCaptioner 的系统架构设计。

## 技术栈

- **UI 框架**: PyQt5 + QFluentWidgets
- **ASR 引擎**: Whisper (FasterWhisper/WhisperCpp)
- **LLM 集成**: OpenAI/DeepSeek/Gemini/Ollama 等
- **视频处理**: FFmpeg

## 核心模块

### 1. ASR 模块 (`videocaptioner/core/asr/`)

语音识别模块，支持多种 ASR 引擎。

### 2. 字幕处理模块 (`videocaptioner/core/split/`, `videocaptioner/core/optimize/`)

字幕分割和优化模块，使用 LLM 进行智能处理。

### 3. 翻译模块 (`videocaptioner/core/translate/`)

字幕翻译模块，支持多种翻译服务。

### 4. UI 模块 (`videocaptioner/ui/view/`)

PyQt5 用户界面模块。

## 数据流

```
视频/音频 → ASR → ASRData → 分割 → 优化 → 翻译 → 字幕文件 → 视频合成
```

更详细的模块职责与数据流说明见 `README.md` 的"各模块"章节，以及 `docs/MODULE_USAGE.md`。

---

相关文档：
- [API 文档](/dev/api)
- [贡献指南](/dev/contributing)
