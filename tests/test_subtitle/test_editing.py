"""Tests for core/subtitle/editing: the table operations behind the subtitle tab."""

from pathlib import Path

import pytest

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SubtitleLayoutEnum
from videocaptioner.core.subtitle import editing


def _table(*rows):
    return {
        str(i): {
            "start_time": start,
            "end_time": end,
            "original_subtitle": original,
            "translated_subtitle": translated,
        }
        for i, (start, end, original, translated) in enumerate(rows, 1)
    }


@pytest.fixture
def table():
    return _table(
        (0, 1000, "one", "một"),
        (1000, 2000, "two", "hai"),
        (2000, 3000, "three", "ba"),
        (3000, 4000, "four", "bốn"),
    )


class TestMergeRows:
    def test_merges_contiguous_selection(self, table):
        merged = editing.merge_rows(table, [1, 2])
        assert list(merged) == ["1", "2", "3"]
        assert merged["2"] == {
            "start_time": 1000,
            "end_time": 3000,
            "original_subtitle": "two three",
            "translated_subtitle": "hai ba",
        }
        assert merged["3"]["original_subtitle"] == "four"

    def test_gap_in_selection_merges_the_whole_span(self, table):
        merged = editing.merge_rows(table, [3, 0])
        assert list(merged) == ["1"]
        assert merged["1"]["original_subtitle"] == "one two three four"
        assert (merged["1"]["start_time"], merged["1"]["end_time"]) == (0, 4000)

    def test_single_row_is_a_no_op_copy(self, table):
        assert editing.merge_rows(table, [2]) == table
        assert editing.merge_rows(table, [2]) is not table

    def test_out_of_range_raises(self, table):
        with pytest.raises(IndexError):
            editing.merge_rows(table, [2, 9])

    def test_input_is_not_mutated(self, table):
        before = {k: dict(v) for k, v in table.items()}
        editing.merge_rows(table, [0, 1])
        assert table == before


class TestDeleteAndSelect:
    def test_delete_renumbers(self, table):
        result = editing.delete_rows(table, [0, 2])
        assert list(result) == ["1", "2"]
        assert [r["original_subtitle"] for r in result.values()] == ["two", "four"]

    def test_delete_nothing(self, table):
        assert editing.delete_rows(table, []) == table

    def test_select_keeps_original_keys(self, table):
        assert editing.select_rows(table, [3, 1]) == {"2": table["2"], "4": table["4"]}


class TestReplaceText:
    def test_replaces_in_both_columns_and_counts_rows(self, table):
        table["1"]["translated_subtitle"] = "one một"
        changed = editing.replace_text(table, "one", "1")
        assert changed == 1
        assert table["1"]["original_subtitle"] == "1"
        assert table["1"]["translated_subtitle"] == "1 một"
        assert table["2"]["original_subtitle"] == "two"

    def test_empty_search_changes_nothing(self, table):
        assert editing.replace_text(table, "", "x") == 0

    def test_non_string_fields_are_skipped(self, table):
        table["1"]["translated_subtitle"] = None
        assert editing.replace_text(table, "one", "1") == 1


def test_playback_range_stops_before_cue_end():
    assert editing.playback_range({"start_time": 1000, "end_time": 2000}) == (1000, 1950)
    # Very short cue: keep the real end rather than going before the start.
    assert editing.playback_range({"start_time": 1000, "end_time": 1030}) == (1000, 1030)


class TestFindSupportedSubtitle:
    def test_first_supported_existing_file_wins(self, tmp_path):
        bad = tmp_path / "notes.txt"
        bad.write_text("x", encoding="utf-8")
        good = tmp_path / "movie.SRT"
        good.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        missing = tmp_path / "ghost.srt"

        path, rejected = editing.find_supported_subtitle(
            [str(missing), str(bad), str(good), str(tmp_path / "later.ass")]
        )

        assert path == str(good)
        assert rejected == ["txt"]

    def test_nothing_supported(self, tmp_path):
        bad = tmp_path / "a.mp4"
        bad.write_bytes(b"")
        assert editing.find_supported_subtitle([str(bad)]) == (None, ["mp4"])

    def test_extension_list(self):
        assert "srt" in editing.supported_subtitle_extensions()


class TestExport:
    def test_export_srt_and_ass(self, table, tmp_path):
        srt = tmp_path / "out.srt"
        ass = tmp_path / "out.ASS"

        editing.export_subtitle(table, str(srt), SubtitleLayoutEnum.ONLY_ORIGINAL)
        editing.export_subtitle(table, str(ass), SubtitleLayoutEnum.ONLY_ORIGINAL, style=None)

        assert "one" in srt.read_text(encoding="utf-8")
        assert ass.read_text(encoding="utf-8").startswith("[Script Info]")
        assert len(ASRData.from_subtitle_file(str(srt)).segments) == 4

    def test_pipeline_targets_only_existing_pipeline_files(self, tmp_path):
        video = tmp_path / "clip.mp4"
        sidecar = tmp_path / "clip.srt"
        sidecar.write_text("", encoding="utf-8")
        output = tmp_path / "out" / "clip-optimized.srt"

        targets = editing.pipeline_reexport_targets(str(output), str(video))
        assert targets == [str(sidecar)]

        output.parent.mkdir()
        output.write_text("", encoding="utf-8")
        assert editing.pipeline_reexport_targets(str(output), str(video)) == [
            str(output),
            str(sidecar),
        ]
        # Same file given twice is written once.
        assert editing.pipeline_reexport_targets(str(sidecar), str(video)) == [str(sidecar)]

    def test_reexport_rewrites_layout(self, table, tmp_path):
        video = tmp_path / "clip.mp4"
        sidecar = tmp_path / "clip.srt"
        sidecar.write_text("", encoding="utf-8")

        written = editing.reexport_pipeline_outputs(
            table, None, str(video), SubtitleLayoutEnum.ONLY_TRANSLATE
        )

        assert written == [str(sidecar)]
        text = sidecar.read_text(encoding="utf-8")
        assert "một" in text and "one" not in text


def test_task_folder_prefers_existing_output(tmp_path):
    subtitle = tmp_path / "in" / "a.srt"
    output = tmp_path / "out" / "a.srt"
    assert editing.task_folder(str(output), str(subtitle)) == str(subtitle.parent)
    output.parent.mkdir()
    output.write_text("", encoding="utf-8")
    assert editing.task_folder(str(output), str(subtitle)) == str(output.parent)


def test_editor_handoff_writes_srt_named_after_task(table, tmp_path):
    handoff = editing.write_editor_handoff(table, tmp_path / "handoff", "task42", "/v/clip.mp4")
    assert handoff == tmp_path / "handoff" / "task42.srt"
    assert handoff.exists()
    fallback = editing.write_editor_handoff(table, tmp_path / "handoff", "", str(Path("clip.mp4")))
    assert fallback.name == "clip.srt"
