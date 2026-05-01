# Trang thai du an - VideoCaptioner

> Cap nhat: 2026-05-01

## Build hien tai

- Exe: `dist/VideoCaptioner-PhaseC-20260429.exe`
- Build moi nhat: 2026-05-01
- Spec: `VideoCaptioner-PhaseC-20260429.spec`
- Ghi chu: app da co co che goi y cai FFmpeg tu dong khi GUI Windows phat hien thieu FFmpeg.

## Plan tiep theo

### Phase D: Long tieng video bang API hoac local AI

- Tao `core/dubbing`: doc subtitle/ASR, tao `TTSData`, canh timeline, tao voice track va mix vao video bang FFmpeg.
- Tai su dung `core/tts` hien co: OpenAI-compatible TTS, SiliconFlow TTS, voice clone va cache audio.
- Ho tro che do audio goc: giu nguyen, giam am luong nen, hoac tat audio goc.
- Them provider local AI sau khi API workflow chay on dinh: local OpenAI-compatible server hoac adapter engine nhu Piper/Coqui/ChatTTS.
- Them UI "Long tieng" va CLI du kien: `videocaptioner dub <video> -s subtitle.srt --provider openai --voice alloy`.
- Kiem thu: test `core/dubbing`, test `tests/test_tts/`, build lai exe bang PyInstaller.
