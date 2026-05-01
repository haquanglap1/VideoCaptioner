import json

from videocaptioner.ui.common.json_translator import JsonTranslator


def test_json_translator_returns_source_for_missing_text(tmp_path):
    path = tmp_path / "translations.json"
    path.write_text(json.dumps({"Known": "Da biet"}), encoding="utf-8")

    translator = JsonTranslator(path)

    assert translator.translate("AnyContext", "Known") == "Da biet"
    assert translator.translate("AnyContext", "Missing") == "Missing"


def test_json_translator_ignores_empty_translation_values(tmp_path):
    path = tmp_path / "translations.json"
    path.write_text(json.dumps({"Missing Value": ""}), encoding="utf-8")

    translator = JsonTranslator(path)

    assert translator.translate("AnyContext", "Missing Value") == "Missing Value"
