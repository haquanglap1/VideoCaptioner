# Trạng thái dự án - VideoCaptioner

> Cập nhật: 2026-05-01 14:10

## Build hiện tại

- **Exe**: `dist/VideoCaptioner-PhaseD-20260501.exe` (~107 MB)
- **Build mới nhất**: 2026-05-01 14:09
- **Spec**: `VideoCaptioner.spec` (dat ten exe qua bien moi truong `VC_BUILD_NAME`)
- **Python**: 3.12.13 (`.venv`)
- **PyInstaller**: 6.20.0

---

## Phase D: Lồng tiếng video bằng TTS API — DONE ✅

### File mới tạo:
| File | Mô tả |
|------|--------|
| `core/dubbing/__init__.py` | Module exports |
| `core/dubbing/config.py` | DubbingConfig, AudioMixMode, TTSProviderEnum |
| `core/dubbing/audio_mixer.py` | FFmpeg wrappers (duration, speed, concat, mix) |
| `core/dubbing/engine.py` | DubbingEngine orchestrator |
| `ui/thread/dubbing_thread.py` | DubbingThread QThread |
| `ui/view/dubbing_interface.py` | Tab "Lồng tiếng" (pipeline + thủ công) |
| `tests/test_dubbing/test_dubbing_engine.py` | 8 unit tests |

### File đã sửa:
| File | Thay đổi |
|------|----------|
| `core/entities.py` | Thêm DubbingTask, dubbing_config vào FullProcessTask |
| `ui/common/config.py` | 9 dubbing config items (provider, voice, API, mix mode, volume) |
| `ui/task_factory.py` | create_dubbing_task() và create_dubbing_config() |
| `ui/view/home_interface.py` | Thêm tab "Lồng tiếng" vào pipeline |
| `ui/thread/subtitle_pipeline_thread.py` | Dubbing step (optional) giữa subtitle và synthesis |

### Tính năng:
- Tái sử dụng `core/tts`: OpenAI TTS, SiliconFlow TTS, OpenAI.fm, voice clone + cache
- 3 chế độ audio gốc: giữ nguyên, giảm âm nền (mặc định 40%), tắt audio gốc
- Căn chỉnh timeline bằng FFmpeg atempo (0.75x–1.5x), truncate nếu vượt quá
- Tab "Lồng tiếng" hỗ trợ pipeline tự động + dub thủ công từ SRT có sẵn

---

## Dọn dẹp UI — DONE ✅

### Đã xoá:
| Phần tử | File | Chi tiết |
|---------|------|----------|
| "Trợ giúp" (helpCard) | `ui/view/setting_interface.py` | Xoá card + signal |
| "Gửi phản hồi" (feedbackCard) | `ui/view/setting_interface.py` | Xoá card + signal |
| GitHub icon (sidebar) | `ui/view/main_window.py` | Xoá nav item dưới cùng |

---

## Tự động cập nhật phiên bản — DONE ✅

### File mới tạo:
| File | Mô tả |
|------|--------|
| `ui/thread/auto_update_thread.py` | Tải exe mới trên background thread + resolve GitHub URL |
| `ui/components/UpdateDialog.py` | Dialog cập nhật: progress bar, tải exe, batch script thay thế + restart |

### File đã sửa:
| File | Thay đổi |
|------|----------|
| `ui/view/main_window.py` | `onNewVersion()` → dùng UpdateDialog thay vì mở browser |
| `ui/view/setting_interface.py` | `checkUpdate()` → kiểm tra API + hiện UpdateDialog (fallback browser) |

### Luồng cập nhật:
1. App khởi động → VersionChecker gọi `vc.bkfeng.top/api/version`
2. Nếu có phiên bản mới → hiện UpdateDialog
3. User bấm "Cập nhật ngay" → AutoUpdateThread tải exe
4. Tải xong → tạo batch script → đóng app → thay thế exe → restart

---

## Bản dịch tiếng Việt — CẬP NHẬT ✅

- **File**: `resource/translations/VideoCaptioner_vi_VN.json` (698 entries)
- Bổ sung 8 string còn thiếu (update dialog, whisper connection, etc.)
- Đồng bộ sang `videocaptioner/resources/translations/`

---

## Plan tiếp theo

### Còn lại:
- [ ] Batch processing — tích hợp dubbing vào FULL_PROCESS batch flow
- [x] Thêm provider local AI: Hỗ trợ OpenAI-Compatible (Piper, xTTS, v.v) và MiniMax TTS
- [ ] CLI: `videocaptioner dub <video> -s subtitle.srt --provider openai --voice alloy`
- [ ] Test end-to-end dubbing với TTS API key thật
- [ ] Build tối ưu (UPX, exclude unused modules)
