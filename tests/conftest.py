"""Root-level test configuration and shared fixtures."""

import ast
import json
import os
import re
from types import SimpleNamespace
from typing import Dict, List

import pytest
from diskcache import Cache

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.translate import SubtitleProcessData, TargetLanguage
from videocaptioner.core.utils import cache
from videocaptioner.core.utils.text_utils import count_words, is_mainly_cjk

# Disable cache for testing
cache.disable_cache()


@pytest.fixture
def sample_asr_data():
    """Create sample ASR data for translation testing."""
    segments = [
        ASRDataSeg(start_time=0, end_time=1000, text="I am a student"),
        ASRDataSeg(start_time=1000, end_time=2000, text="You are a teacher"),
        ASRDataSeg(start_time=2000, end_time=3000, text="VideoCaptioner is a tool for captioning videos"),
    ]
    return ASRData(segments)


@pytest.fixture
def sample_translate_data():
    """Create sample translation data for testing."""
    return [
        SubtitleProcessData(index=1, original_text="I am a student", translated_text=""),
        SubtitleProcessData(index=2, original_text="You are a teacher", translated_text=""),
        SubtitleProcessData(index=3, original_text="VideoCaptioner is a tool for captioning videos", translated_text=""),
    ]


@pytest.fixture
def target_language():
    """Default target language for translation tests."""
    return TargetLanguage.SIMPLIFIED_CHINESE


@pytest.fixture
def check_env_vars():
    """Check if required environment variables are set."""
    def _check(*var_names):
        missing = [var for var in var_names if not os.getenv(var)]
        if missing:
            pytest.skip(f"Required environment variables not set: {', '.join(missing)}")
    return _check


@pytest.fixture
def expected_translations() -> Dict[str, Dict[str, List[str]]]:
    """Expected translation keywords for quality validation."""
    return {
        "简体中文": {
            "I am a student": ["学生"],
            "You are a teacher": ["老师", "教师"],
            "VideoCaptioner is a tool for captioning videos": ["工具"],
        },
        "日本語": {
            "I am a student": ["学生"],
            "You are a teacher": ["先生", "教師"],
        },
        "English": {
            "我是学生": ["student"],
            "你是老师": ["teacher"],
        },
    }


def assert_translation_quality(original: str, translated: str, expected_keywords: List[str]) -> None:
    """Validate translation contains expected keywords."""
    assert translated, f"Translation is empty for: {original}"
    found_keywords = [kw for kw in expected_keywords if kw in translated]
    assert found_keywords, (
        f"Translation quality issue:\n"
        f"  Original: {original}\n"
        f"  Translated: {translated}\n"
        f"  Expected keywords: {expected_keywords}"
    )


# ============================================================================
# Fake LLM
# ============================================================================


def _fake_llm_response(content: str) -> SimpleNamespace:
    """Minimal stand-in for an OpenAI ChatCompletion response object."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _greedy_split(text: str, limit: int) -> str:
    """Insert <br> so每段 stays within `limit` per count_words, content unchanged.

    Mirrors what the split prompt asks the model to do, using the project's own
    word-counting rules so _validate_split_result accepts the output.
    """
    if is_mainly_cjk(text):
        units = list(text)
        joiner = ""
    else:
        units = text.split(" ")
        joiner = " "

    segments, current = [], []
    for unit in units:
        current.append(unit)
        if count_words(joiner.join(current)) >= limit:
            segments.append(joiner.join(current))
            current = []
    if current:
        segments.append(joiner.join(current))
    return "<br>".join(segments)


def _limit_from_prompt(system_prompt: str, marker: str, default: int) -> int:
    match = re.search(marker + r"\D{0,4}(\d+)", system_prompt)
    return int(match.group(1)) if match else default


@pytest.fixture
def mock_llm_client(monkeypatch, tmp_path):
    """Deterministic stand-in for call_llm across translate / optimize / split.

    Every core module that talks to an LLM imports call_llm into its own
    namespace, so each one is patched separately. Dispatch is by system prompt
    because that is what identifies the task.

    Also redirects the translate disk cache into tmp_path: tests that enable
    caching must not write into the user's real AppData cache.
    """

    def fake_call_llm(messages, model, temperature=1, **kwargs):
        system_prompt = messages[0]["content"] if messages else ""
        user_content = messages[-1]["content"] if messages else ""

        # translate/context — bản brief dạng text thuần
        if "localization analyst" in system_prompt:
            return _fake_llm_response(
                "TOPIC & GENRE: test transcript\n"
                "TONE & REGISTER: neutral\n"
                "GLOSSARY:\n"
                "NOTES: none"
            )

        # split/sentence — trả lại đúng văn bản gốc, chỉ chèn <br>
        if "字幕分句专家" in system_prompt or "字幕分段专家" in system_prompt:
            text = user_content.split("\n", 1)[-1]
            cjk_limit = _limit_from_prompt(system_prompt, "CJK语言.{0,30}每段≤", 18)
            en_limit = _limit_from_prompt(system_prompt, "拉丁语言.{0,30}每段≤", 12)
            limit = cjk_limit if is_mainly_cjk(text) else en_limit
            return _fake_llm_response(_greedy_split(text, limit))

        # optimize/subtitle — giữ nguyên nội dung, chỉ trả về đúng schema
        if "subtitle correction expert" in system_prompt:
            match = re.search(
                r"<input_subtitle>(.*)</input_subtitle>", user_content, re.DOTALL
            )
            payload = {}
            if match:
                try:
                    payload = ast.literal_eval(match.group(1))
                except (ValueError, SyntaxError):
                    payload = {}
            return _fake_llm_response(json.dumps(payload, ensure_ascii=False))

        # translate/standard | translate/reflect — user content là JSON dict
        try:
            payload = json.loads(user_content)
        except (TypeError, ValueError):
            payload = {}

        if "reflective translation" in system_prompt:
            result = {
                key: {"native_translation": f"[translated] {value}"}
                for key, value in payload.items()
            }
        else:
            result = {key: f"[translated] {value}" for key, value in payload.items()}
        return _fake_llm_response(json.dumps(result, ensure_ascii=False))

    for target in (
        "videocaptioner.core.translate.llm_translator.call_llm",
        "videocaptioner.core.optimize.optimize.call_llm",
        "videocaptioner.core.split.split_by_llm.call_llm",
    ):
        monkeypatch.setattr(target, fake_call_llm)

    # Credential giả: get_llm_client() vẫn đòi env var dù call_llm đã bị patch,
    # và SubtitleConfig của test đọc trực tiếp từ env.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://mock.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")

    # SubtitleThread verify kết nối LLM thật trước khi chạy — bỏ qua khi dùng mock.
    # Import trong try: root conftest không được phụ thuộc PyQt5 (test CLI chạy
    # không cần GUI extras).
    try:
        import videocaptioner.ui.thread.subtitle_thread  # noqa: F401
    except Exception:
        pass
    else:
        monkeypatch.setattr(
            "videocaptioner.ui.thread.subtitle_thread.check_llm_connection",
            lambda *args, **kwargs: (True, ""),
        )

    isolated_cache = Cache(str(tmp_path / "translate_results"))
    monkeypatch.setattr(
        "videocaptioner.core.translate.base.get_translate_cache",
        lambda: isolated_cache,
    )

    was_enabled = cache.is_cache_enabled()
    try:
        yield fake_call_llm
    finally:
        # test_cache_works bật cache toàn cục — trả lại trạng thái trước đó.
        if was_enabled:
            cache.enable_cache()
        else:
            cache.disable_cache()
        isolated_cache.close()
