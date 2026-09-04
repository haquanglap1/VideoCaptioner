"""Regression tests for the subtitle command's credential handling."""

import os

from videocaptioner.cli.main import main
from videocaptioner.core.llm.client import get_llm_credentials

_SRT = (
    "1\n00:00:00,000 --> 00:00:01,000\nHello world\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"
)


def test_subtitle_registers_credentials_without_exporting_them(tmp_path, mock_llm_client):
    source = tmp_path / "in.srt"
    source.write_text(_SRT, encoding="utf-8")
    target = tmp_path / "out.srt"
    environ_before = dict(os.environ)

    code = main(
        [
            "subtitle",
            str(source),
            "-o",
            str(target),
            "--api-key",
            "sk-cli-secret",
            "--api-base",
            "https://cli.invalid/v1",
            "--model",
            "gpt-test",
            "--no-translate",
            "--no-split",
            "-q",
        ]
    )

    assert code == 0
    assert target.exists()
    # The key reached the LLM client as an object...
    assert get_llm_credentials().api_key == "sk-cli-secret"
    # ...and never touched the process environment that child processes inherit.
    assert "sk-cli-secret" not in os.environ.values()
    assert os.environ.get("OPENAI_API_KEY") == environ_before.get("OPENAI_API_KEY")
    assert os.environ.get("OPENAI_BASE_URL") == environ_before.get("OPENAI_BASE_URL")
