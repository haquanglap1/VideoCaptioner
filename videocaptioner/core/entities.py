import datetime
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.translate.types import TargetLanguage


def _generate_task_id() -> str:
    """Generate an 8-character task ID."""
    return uuid.uuid4().hex[:8]


@dataclass
class SubtitleProcessData:
    """Subtitle processing payload shared by translation and optimization."""

    index: int
    original_text: str
    translated_text: str = ""
    optimized_text: str = ""


class SupportedAudioFormats(Enum):
    """Supported audio formats."""

    AAC = "aac"
    AC3 = "ac3"
    AIFF = "aiff"
    AMR = "amr"
    APE = "ape"
    AU = "au"
    FLAC = "flac"
    M4A = "m4a"
    MP2 = "mp2"
    MP3 = "mp3"
    MKA = "mka"
    OGA = "oga"
    OGG = "ogg"
    OPUS = "opus"
    RA = "ra"
    WAV = "wav"
    WMA = "wma"


class SupportedVideoFormats(Enum):
    """Supported video formats."""

    MP4 = "mp4"
    WEBM = "webm"
    OGM = "ogm"
    MOV = "mov"
    MKV = "mkv"
    AVI = "avi"
    WMV = "wmv"
    FLV = "flv"
    M4V = "m4v"
    TS = "ts"
    MPG = "mpg"
    MPEG = "mpeg"
    VOB = "vob"
    ASF = "asf"
    RM = "rm"
    RMVB = "rmvb"
    M2TS = "m2ts"
    MTS = "mts"
    DV = "dv"
    GXF = "gxf"
    TOD = "tod"
    MXF = "mxf"
    F4V = "f4v"


class SupportedSubtitleFormats(Enum):
    """Supported subtitle formats."""

    SRT = "srt"
    ASS = "ass"
    VTT = "vtt"


class OutputSubtitleFormatEnum(Enum):
    """Subtitle output formats."""

    SRT = "srt"
    ASS = "ass"
    VTT = "vtt"
    JSON = "json"
    TXT = "txt"


class TranscribeOutputFormatEnum(Enum):
    """Transcription output formats."""

    SRT = "SRT"
    ASS = "ASS"
    VTT = "VTT"
    TXT = "TXT"
    ALL = "All"


class LLMServiceEnum(Enum):
    """LLM services."""

    OPENAI = "OpenAI 兼容"
    SILICON_CLOUD = "SiliconCloud"
    DEEPSEEK = "DeepSeek"
    OLLAMA = "Ollama"
    LM_STUDIO = "LM Studio"
    GEMINI = "Gemini"
    CHATGLM = "ChatGLM"


class TranscribeModelEnum(Enum):
    """Transcription models."""

    BIJIAN = "B 接口"
    JIANYING = "J 接口"
    WHISPER_API = "Whisper [API] ✨"
    FASTER_WHISPER = "FasterWhisper ✨"
    WHISPER_CPP = "WhisperCpp"


class TranslatorServiceEnum(Enum):
    """Translator services."""

    OPENAI = "LLM 大模型翻译"
    DEEPLX = "DeepLx 翻译"
    BING = "微软翻译"
    GOOGLE = "谷歌翻译"


class VadMethodEnum(Enum):
    """VAD methods."""

    SILERO_V3 = "silero_v3"  # Usually less accurate than v4, but without some of v4's quirks
    SILERO_V4 = (
        "silero_v4"  # Same as silero_v4_fw but runs the original Silero code instead of the adapted one
    )
    SILERO_V5 = (
        "silero_v5"  # Same as silero_v5_fw but runs the original Silero code instead of the adapted one
    )
    SILERO_V4_FW = (
        "silero_v4_fw"  # Default. The most accurate Silero version, with a few non-fatal quirks
    )
    # SILERO_V5_FW = "silero_v5_fw"  # Poor accuracy: more a random speech detector than a VAD, with fatal quirks. Avoid.
    PYANNOTE_V3 = "pyannote_v3"  # Best accuracy, CUDA capable
    PYANNOTE_ONNX_V3 = "pyannote_onnx_v3"  # Lightweight pyannote_v3: accuracy close to or slightly above Silero v4, CUDA capable
    WEBRTC = "webrtc"  # Low accuracy, outdated VAD. Only honours 'vad_min_speech_duration_ms' and 'vad_speech_pad_ms'
    AUDITOK = "auditok"  # Not a VAD but an AAD: audio activity detection


class SubtitleLayoutEnum(Enum):
    """Subtitle layouts."""

    TRANSLATE_ON_TOP = "Bản dịch ở trên"
    ORIGINAL_ON_TOP = "Bản gốc ở trên"
    ONLY_ORIGINAL = "Chỉ bản gốc"
    ONLY_TRANSLATE = "Chỉ bản dịch"


class SubtitleRenderModeEnum(Enum):
    """Subtitle render modes."""

    ASS_STYLE = "Kiểu ASS"  # FFmpeg ASS render
    ROUNDED_BG = "Nền bo góc"  # Pillow rounded background


class VideoQualityEnum(Enum):
    """Video synthesis quality."""

    ULTRA_HIGH = "Cực cao"
    HIGH = "Cao"
    MEDIUM = "Trung bình"
    LOW = "Thấp"

    def get_crf(self) -> int:
        """CRF value for this quality (lower means better quality and larger files)."""
        crf_map = {
            VideoQualityEnum.ULTRA_HIGH: 18,
            VideoQualityEnum.HIGH: 23,
            VideoQualityEnum.MEDIUM: 28,
            VideoQualityEnum.LOW: 32,
        }
        return crf_map[self]

    def get_preset(
        self,
    ) -> Literal[
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    ]:
        """FFmpeg preset for this quality (affects encoding speed)."""
        preset_map: dict[
            VideoQualityEnum,
            Literal[
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ],
        ] = {
            VideoQualityEnum.ULTRA_HIGH: "slow",
            VideoQualityEnum.HIGH: "medium",
            VideoQualityEnum.MEDIUM: "medium",
            VideoQualityEnum.LOW: "fast",
        }
        return preset_map[self]


class TranscribeLanguageEnum(Enum):
    """Transcription languages."""

    AUTO = "自动检测"
    ENGLISH = "英语"
    CHINESE = "中文"
    JAPANESE = "日本語"
    KOREAN = "韩语"
    YUE = "粤语"
    FRENCH = "法语"
    GERMAN = "德语"
    SPANISH = "西班牙语"
    RUSSIAN = "俄语"
    PORTUGUESE = "葡萄牙语"
    TURKISH = "土耳其语"
    POLISH = "Polish"
    CATALAN = "Catalan"
    DUTCH = "Dutch"
    ARABIC = "Arabic"
    SWEDISH = "Swedish"
    ITALIAN = "Italian"
    INDONESIAN = "Indonesian"
    HINDI = "Hindi"
    FINNISH = "Finnish"
    VIETNAMESE = "Vietnamese"
    HEBREW = "Hebrew"
    UKRAINIAN = "Ukrainian"
    GREEK = "Greek"
    MALAY = "Malay"
    CZECH = "Czech"
    ROMANIAN = "Romanian"
    DANISH = "Danish"
    HUNGARIAN = "Hungarian"
    TAMIL = "Tamil"
    NORWEGIAN = "Norwegian"
    THAI = "Thai"
    URDU = "Urdu"
    CROATIAN = "Croatian"
    BULGARIAN = "Bulgarian"
    LITHUANIAN = "Lithuanian"
    LATIN = "Latin"
    MAORI = "Maori"
    MALAYALAM = "Malayalam"
    WELSH = "Welsh"
    SLOVAK = "Slovak"
    TELUGU = "Telugu"
    PERSIAN = "Persian"
    LATVIAN = "Latvian"
    BENGALI = "Bengali"
    SERBIAN = "Serbian"
    AZERBAIJANI = "Azerbaijani"
    SLOVENIAN = "Slovenian"
    KANNADA = "Kannada"
    ESTONIAN = "Estonian"
    MACEDONIAN = "Macedonian"
    BRETON = "Breton"
    BASQUE = "Basque"
    ICELANDIC = "Icelandic"
    ARMENIAN = "Armenian"
    NEPALI = "Nepali"
    MONGOLIAN = "Mongolian"
    BOSNIAN = "Bosnian"
    KAZAKH = "Kazakh"
    ALBANIAN = "Albanian"
    SWAHILI = "Swahili"
    GALICIAN = "Galician"
    MARATHI = "Marathi"
    PUNJABI = "Punjabi"
    SINHALA = "Sinhala"
    KHMER = "Khmer"
    SHONA = "Shona"
    YORUBA = "Yoruba"
    SOMALI = "Somali"
    AFRIKAANS = "Afrikaans"
    OCCITAN = "Occitan"
    GEORGIAN = "Georgian"
    BELARUSIAN = "Belarusian"
    TAJIK = "Tajik"
    SINDHI = "Sindhi"
    GUJARATI = "Gujarati"
    AMHARIC = "Amharic"
    YIDDISH = "Yiddish"
    LAO = "Lao"
    UZBEK = "Uzbek"
    FAROESE = "Faroese"
    HAITIAN_CREOLE = "Haitian Creole"
    PASHTO = "Pashto"
    TURKMEN = "Turkmen"
    NYNORSK = "Nynorsk"
    MALTESE = "Maltese"
    SANSKRIT = "Sanskrit"
    LUXEMBOURGISH = "Luxembourgish"
    MYANMAR = "Myanmar"
    TIBETAN = "Tibetan"
    TAGALOG = "Tagalog"
    MALAGASY = "Malagasy"
    ASSAMESE = "Assamese"
    TATAR = "Tatar"
    HAWAIIAN = "Hawaiian"
    LINGALA = "Lingala"
    HAUSA = "Hausa"
    BASHKIR = "Bashkir"
    JAVANESE = "Javanese"
    SUNDANESE = "Sundanese"
    CANTONESE = "Cantonese"


class WhisperModelEnum(Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V1 = "large-v1"
    LARGE_V2 = "large-v2"


class FasterWhisperModelEnum(Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V1 = "large-v1"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"
    LARGE_V3_TURBO = "large-v3-turbo"


LANGUAGES = {
    "自动检测": "",
    "英语": "en",
    "中文": "zh",
    "日本語": "ja",
    "德语": "de",
    "粤语": "yue",
    "西班牙语": "es",
    "俄语": "ru",
    "韩语": "ko",
    "法语": "fr",
    "葡萄牙语": "pt",
    "土耳其语": "tr",
    "English": "en",
    "Chinese": "zh",
    "German": "de",
    "Spanish": "es",
    "Russian": "ru",
    "Korean": "ko",
    "French": "fr",
    "Japanese": "ja",
    "Portuguese": "pt",
    "Turkish": "tr",
    "Polish": "pl",
    "Catalan": "ca",
    "Dutch": "nl",
    "Arabic": "ar",
    "Swedish": "sv",
    "Italian": "it",
    "Indonesian": "id",
    "Hindi": "hi",
    "Finnish": "fi",
    "Vietnamese": "vi",
    "Hebrew": "he",
    "Ukrainian": "uk",
    "Greek": "el",
    "Malay": "ms",
    "Czech": "cs",
    "Romanian": "ro",
    "Danish": "da",
    "Hungarian": "hu",
    "Tamil": "ta",
    "Norwegian": "no",
    "Thai": "th",
    "Urdu": "ur",
    "Croatian": "hr",
    "Bulgarian": "bg",
    "Lithuanian": "lt",
    "Latin": "la",
    "Maori": "mi",
    "Malayalam": "ml",
    "Welsh": "cy",
    "Slovak": "sk",
    "Telugu": "te",
    "Persian": "fa",
    "Latvian": "lv",
    "Bengali": "bn",
    "Serbian": "sr",
    "Azerbaijani": "az",
    "Slovenian": "sl",
    "Kannada": "kn",
    "Estonian": "et",
    "Macedonian": "mk",
    "Breton": "br",
    "Basque": "eu",
    "Icelandic": "is",
    "Armenian": "hy",
    "Nepali": "ne",
    "Mongolian": "mn",
    "Bosnian": "bs",
    "Kazakh": "kk",
    "Albanian": "sq",
    "Swahili": "sw",
    "Galician": "gl",
    "Marathi": "mr",
    "Punjabi": "pa",
    "Sinhala": "si",
    "Khmer": "km",
    "Shona": "sn",
    "Yoruba": "yo",
    "Somali": "so",
    "Afrikaans": "af",
    "Occitan": "oc",
    "Georgian": "ka",
    "Belarusian": "be",
    "Tajik": "tg",
    "Sindhi": "sd",
    "Gujarati": "gu",
    "Amharic": "am",
    "Yiddish": "yi",
    "Lao": "lo",
    "Uzbek": "uz",
    "Faroese": "fo",
    "Haitian Creole": "ht",
    "Pashto": "ps",
    "Turkmen": "tk",
    "Nynorsk": "nn",
    "Maltese": "mt",
    "Sanskrit": "sa",
    "Luxembourgish": "lb",
    "Myanmar": "my",
    "Tibetan": "bo",
    "Tagalog": "tl",
    "Malagasy": "mg",
    "Assamese": "as",
    "Tatar": "tt",
    "Hawaiian": "haw",
    "Lingala": "ln",
    "Hausa": "ha",
    "Bashkir": "ba",
    "Javanese": "jw",
    "Sundanese": "su",
    "Cantonese": "yue",
}


@dataclass
class ASRLanguageCapability:
    """Language support of the ASR engines."""

    supported_languages: list[TranscribeLanguageEnum]
    supports_auto: bool


def _get_all_languages_except_auto() -> list[TranscribeLanguageEnum]:
    """Every language except AUTO."""
    return [lang for lang in TranscribeLanguageEnum if lang != TranscribeLanguageEnum.AUTO]


ASR_LANGUAGE_CAPABILITIES: dict[TranscribeModelEnum, ASRLanguageCapability] = {
    TranscribeModelEnum.BIJIAN: ASRLanguageCapability(
        supported_languages=[
            TranscribeLanguageEnum.CHINESE,
            TranscribeLanguageEnum.ENGLISH,
        ],
        supports_auto=True,
    ),
    TranscribeModelEnum.JIANYING: ASRLanguageCapability(
        supported_languages=[
            TranscribeLanguageEnum.CHINESE,
            TranscribeLanguageEnum.ENGLISH,
        ],
        supports_auto=True,
    ),
    TranscribeModelEnum.FASTER_WHISPER: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=False,
    ),
    TranscribeModelEnum.WHISPER_CPP: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=True,
    ),
    TranscribeModelEnum.WHISPER_API: ASRLanguageCapability(
        supported_languages=_get_all_languages_except_auto(),
        supports_auto=True,
    ),
}


def get_asr_language_capability(model: TranscribeModelEnum) -> ASRLanguageCapability:
    """Language capabilities of the given model."""
    return ASR_LANGUAGE_CAPABILITIES.get(
        model,
        ASRLanguageCapability(
            supported_languages=_get_all_languages_except_auto(),
            supports_auto=True,
        ),
    )


@dataclass
class AudioStreamInfo:
    """Audio stream information."""

    index: int  # Real stream index inside the video (0, 1, 2 or 2, 3, 4 ...)
    codec: str  # Audio codec (aac, mp3, opus ...)
    language: str = ""  # Language tag (eng, chi, deu ...)
    title: str = ""  # Track title (optional)


@dataclass
class VideoInfo:
    """Video information."""

    file_name: str
    file_path: str
    width: int
    height: int
    fps: float
    duration_seconds: float
    bitrate_kbps: int
    video_codec: str
    audio_codec: str
    audio_sampling_rate: int
    thumbnail_path: str
    audio_streams: list[AudioStreamInfo] = field(default_factory=list)  # Audio streams


@dataclass
class TranscribeConfig:
    """Transcription configuration."""

    transcribe_model: Optional[TranscribeModelEnum] = None
    transcribe_language: str = ""
    need_word_time_stamp: bool = True
    output_format: Optional[TranscribeOutputFormatEnum] = None
    # Whisper.cpp settings
    whisper_model: Optional[WhisperModelEnum] = None
    # Whisper API settings
    whisper_api_key: Optional[str] = None
    whisper_api_base: Optional[str] = None
    whisper_api_model: Optional[str] = None
    whisper_api_prompt: Optional[str] = None
    # Faster Whisper settings
    faster_whisper_program: Optional[str] = None
    faster_whisper_model: Optional[FasterWhisperModelEnum] = None
    faster_whisper_model_dir: Optional[str] = None
    faster_whisper_device: str = "cuda"
    faster_whisper_vad_filter: bool = True
    faster_whisper_vad_threshold: float = 0.5
    faster_whisper_vad_method: Optional[VadMethodEnum] = VadMethodEnum.SILERO_V3
    faster_whisper_ff_mdx_kim2: bool = False
    faster_whisper_one_word: bool = True
    faster_whisper_prompt: Optional[str] = None
    whisper_api_provider: str = "custom"
    whisper_api_request_profile: str = "auto"

    def _mask_key(self, key: Optional[str]) -> str:
        """Mask sensitive key for display"""
        if not key or len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def print_config(self) -> str:
        """Print transcription configuration"""
        lines = ["=========== Transcription Task ==========="]
        lines.append(
            f"Model: {self.transcribe_model.value if self.transcribe_model else 'None'}"
        )
        lines.append(f"Language: {self.transcribe_language or 'Auto'}")
        lines.append(f"Word Timestamp: {self.need_word_time_stamp}")
        lines.append(
            f"Output Format: {self.output_format.value if self.output_format else 'None'}"
        )

        if self.transcribe_model == TranscribeModelEnum.WHISPER_API:
            lines.append("OpenAI-compatible ASR (endpoint, key and prompt omitted)")

        elif self.transcribe_model == TranscribeModelEnum.FASTER_WHISPER:
            lines.append(
                f"Model: {self.faster_whisper_model.value if self.faster_whisper_model else 'None'}"
            )
            lines.append(f"Device: {self.faster_whisper_device}")
            lines.append(f"VAD Filter: {self.faster_whisper_vad_filter}")
            if self.faster_whisper_vad_filter:
                lines.append(
                    f"VAD Method: {self.faster_whisper_vad_method.value if self.faster_whisper_vad_method else 'None'}"
                )
                lines.append(f"VAD Threshold: {self.faster_whisper_vad_threshold}")
            lines.append(f"One Word Per Segment: {self.faster_whisper_one_word}")

        elif self.transcribe_model == TranscribeModelEnum.WHISPER_CPP:
            lines.append(
                f"Model: {self.whisper_model.value if self.whisper_model else 'None'}"
            )

        lines.append("=" * 42)
        return "\n".join(lines)


@dataclass
class SubtitleConfig:
    """Subtitle processing configuration."""

    # Translation settings
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    llm_model: Optional[str] = None
    deeplx_endpoint: Optional[str] = None
    # Translation service
    translator_service: Optional[TranslatorServiceEnum] = None
    need_translate: bool = False
    need_optimize: bool = False
    need_reflect: bool = False
    thread_num: int = 10
    batch_size: int = 10
    # Subtitle layout and splitting
    subtitle_layout: SubtitleLayoutEnum = SubtitleLayoutEnum.ORIGINAL_ON_TOP
    max_word_count_cjk: int = 12
    max_word_count_english: int = 18
    need_split: bool = True
    target_language: Optional["TargetLanguage"] = None
    subtitle_style: Optional[str] = None
    custom_prompt_text: Optional[str] = None

    def _mask_key(self, key: Optional[str]) -> str:
        """Mask sensitive key for display"""
        if not key or len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    def print_config(self) -> str:
        """Print subtitle processing configuration"""
        lines = ["=========== Subtitle Processing Task ==========="]

        if self.need_split:
            lines.append("Split: Yes")
            lines.append(f"  Max Words (CJK): {self.max_word_count_cjk}")
            lines.append(f"  Max Words (English): {self.max_word_count_english}")

        if self.need_optimize:
            lines.append("Optimize: Yes")
            lines.append(f"  Model: {self.llm_model or 'None'}")
            if self.custom_prompt_text:
                lines.append(f"  Custom Prompt: {self.custom_prompt_text[:30]}...")

        if self.need_translate:
            lines.append("Translate: Yes")
            lines.append(
                f"  Service: {self.translator_service.value if self.translator_service else 'None'}"
            )
            if self.translator_service == TranslatorServiceEnum.OPENAI:
                lines.append(f"  API Base: {self.base_url}")
                lines.append(f"  API Key: {self._mask_key(self.api_key)}")
                lines.append(f"  Model: {self.llm_model}")
                lines.append(f"  Reflect Translation: {self.need_reflect}")
            elif self.translator_service == TranslatorServiceEnum.DEEPLX:
                lines.append(f"  DeepLX Endpoint: {self.deeplx_endpoint}")
            lines.append(
                f"  Target Language: {self.target_language.value if self.target_language else 'None'}"
            )
            lines.append(f"  Concurrency: {self.thread_num}")
            lines.append(f"  Batch Size: {self.batch_size}")

        lines.append(f"Layout: {self.subtitle_layout.value}")
        lines.append("=" * 48)
        return "\n".join(lines)


@dataclass
class SynthesisConfig:
    """Video synthesis configuration."""

    need_video: bool = True
    soft_subtitle: bool = True
    render_mode: SubtitleRenderModeEnum = SubtitleRenderModeEnum.ASS_STYLE
    video_quality: VideoQualityEnum = VideoQualityEnum.MEDIUM
    subtitle_layout: SubtitleLayoutEnum = SubtitleLayoutEnum.ORIGINAL_ON_TOP
    # Subtitle style settings
    ass_style: str = ""  # ASS style string
    rounded_style: Optional[dict] = None  # Rounded background style settings

    def print_config(self) -> str:
        """Print video synthesis configuration"""
        lines = ["=========== Video Synthesis Task ==========="]
        lines.append(f"Generate Video: {self.need_video}")
        if self.need_video:
            lines.append(f"Subtitle Type: {'Soft' if self.soft_subtitle else 'Hard'}")
            if not self.soft_subtitle:
                lines.append(f"Render Mode: {self.render_mode.value}")
            lines.append(f"Video Quality: {self.video_quality.value}")
            lines.append(f"  CRF: {self.video_quality.get_crf()}")
            lines.append(f"  Preset: {self.video_quality.get_preset()}")
        lines.append("=" * 44)
        return "\n".join(lines)


@dataclass
class TranscribeTask:
    """Transcription task."""

    # Task identity
    task_id: str = field(default_factory=_generate_task_id)

    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    # Input file
    file_path: Optional[str] = None

    # Output subtitle file
    output_path: Optional[str] = None

    # Whether the next task (subtitle processing) follows
    need_next_task: bool = False

    # Selected audio track index
    selected_audio_track_index: int = 0

    transcribe_config: Optional[TranscribeConfig] = None


@dataclass
class SubtitleTask:
    """Subtitle task."""

    # Task identity
    task_id: str = field(default_factory=_generate_task_id)

    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    # Input: original subtitle file
    subtitle_path: str = ""
    # Input: original video file
    video_path: Optional[str] = None

    # Output: subtitle file after splitting, optimization and translation
    output_path: Optional[str] = None
    # Monolingual artifact for dubbing, independent from the display layout.
    dubbing_subtitle_path: Optional[str] = None

    # Whether the next task (video synthesis) follows
    need_next_task: bool = True

    subtitle_config: Optional[SubtitleConfig] = None


@dataclass
class SynthesisTask:
    """Video synthesis task."""

    # Task identity
    task_id: str = field(default_factory=_generate_task_id)

    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    # Input
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None

    # Output
    output_path: Optional[str] = None

    # Whether a next task follows (reserved)
    need_next_task: bool = False

    synthesis_config: Optional[SynthesisConfig] = None


@dataclass
class DubbingTask:
    """Dubbing (lồng tiếng) task."""

    # Task identity
    task_id: str = field(default_factory=_generate_task_id)

    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    # Input
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    display_subtitle_path: Optional[str] = None

    # Output — video with dubbed audio
    output_path: Optional[str] = None
    report_path: Optional[str] = None
    dubbing_report: Optional[dict] = None

    need_next_task: bool = False

    dubbing_config: Optional["DubbingConfig"] = None


@dataclass
class TranscriptAndSubtitleTask:
    """Transcription plus subtitle task."""

    # Task identity
    task_id: str = field(default_factory=_generate_task_id)

    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    # Input
    file_path: Optional[str] = None

    # Output
    output_path: Optional[str] = None

    transcribe_config: Optional[TranscribeConfig] = None
    subtitle_config: Optional[SubtitleConfig] = None


@dataclass
class FullProcessTask:
    """Full pipeline task (transcription, subtitles, synthesis)."""

    # Task identity
    task_id: str = field(default_factory=_generate_task_id)

    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None

    # Input
    file_path: Optional[str] = None
    # Output
    output_path: Optional[str] = None

    transcribe_config: Optional[TranscribeConfig] = None
    subtitle_config: Optional[SubtitleConfig] = None
    dubbing_config: Optional["DubbingConfig"] = None
    synthesis_config: Optional[SynthesisConfig] = None


class BatchTaskType(Enum):
    """Batch task types."""

    TRANSCRIBE = "批量转录"
    SUBTITLE = "批量字幕"
    TRANS_SUB = "转录+字幕"
    FULL_PROCESS = "全流程处理"
    DUBBING = "Lồng tiếng hàng loạt"

    def __str__(self):
        return self.value


class BatchTaskStatus(Enum):
    """Batch task states."""

    WAITING = "等待中"
    RUNNING = "处理中"
    COMPLETED = "已完成"
    FAILED = "失败"

    def __str__(self):
        return self.value


def enum_from_display(enum_cls, text, translate=None):
    """Resolve a member from its raw value or its translated display text.

    Combos show ``tr(member.value)``, so ``currentText()`` may be the
    translated string; ``EnumCls(text)`` alone would fail on it.
    """
    for member in enum_cls:
        if member.value == text:
            return member
        if translate is not None and translate(member.value) == text:
            return member
    raise ValueError(f"{text!r} is not a valid {enum_cls.__name__}")
