"""Tests for the metadata inspector and the app controls that reach it."""

import os

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=True)

from PyONDE.viewer.app import OndeViewerApp                    # noqa: E402
from PyONDE.viewer.inspector import format_tree                 # noqa: E402


@pytest.fixture
def ascan_app(ascan_document):
    app = OndeViewerApp(ascan_document)
    yield app
    app.close()


# -- flattening -----------------------------------------------------------

def test_format_tree_indents_nested_mappings():
    lines = format_tree({"a": 1, "b": {"c": 2}})
    assert lines[0] == "a: 1"
    assert lines[1] == "b:"
    assert lines[2] == "  c: 2"


def test_format_tree_numbers_list_entries():
    lines = format_tree({"refs": [{"x": 1}, {"x": 2}]})
    assert "  [0]:" in lines
    assert "    x: 1" in lines


def test_format_tree_truncates_very_long_scalars():
    lines = format_tree({"long": "y" * 500})
    assert len(lines[0]) < 120
    assert lines[0].endswith("...")


def test_format_tree_renders_the_real_metadata(ascan_model):
    lines = format_tree(ascan_model.metadata_tree())
    joined = "\n".join(lines)
    assert "ONDE_DATASET:SETUP:" in joined
    assert "ONDE_GEOMETRIC_SETUP:SENSOR_LIST:" in joined
    assert "ONDE_UT_PROBE:FREQUENCY: 5e+06" in joined


# -- the window -----------------------------------------------------------

def test_inspector_opens_with_the_dataset_metadata(ascan_app, ascan_model):
    ascan_app.on_inspect()
    inspector = ascan_app.inspector
    assert inspector.is_open
    assert inspector.lines[0] == ascan_model.label
    assert any("ONDE:UUID" in line for line in inspector.lines)


def test_inspector_shows_a_window_of_lines(ascan_app):
    ascan_app.on_inspect()
    inspector = ascan_app.inspector
    shown = inspector.text.get_text().split("\n")
    assert len(shown) <= inspector.visible_lines()
    assert len(inspector.lines) > inspector.visible_lines()  # there is more below


def test_scrolling_reveals_later_lines(ascan_app):
    ascan_app.on_inspect()
    inspector = ascan_app.inspector
    top = inspector.text.get_text()
    inspector.widgets["scroll"].set_val(0)      # slider at the bottom
    bottom = inspector.text.get_text()
    assert top != bottom
    assert inspector.lines[-1] in bottom


def test_filter_restricts_the_lines(ascan_app):
    ascan_app.on_inspect()
    inspector = ascan_app.inspector
    inspector._on_filter("FREQUENCY")
    shown = inspector.text.get_text()
    assert "FREQUENCY" in shown
    assert "ONDE:UUID" not in shown
    inspector._on_filter("")
    assert "ONDE:UUID" in inspector.text.get_text()


def test_filter_with_no_match_says_so(ascan_app):
    ascan_app.on_inspect()
    ascan_app.inspector._on_filter("zzz-nothing")
    assert "no line matches" in ascan_app.inspector.text.get_text()


def test_reopening_reuses_the_window_and_reloads(tscan_document):
    app = OndeViewerApp(tscan_document)
    try:
        app.on_inspect()
        first_figure = app.inspector.figure
        first_lines = list(app.inspector.lines)
        app.on_dataset_step(+1)
        app.on_inspect()
        assert app.inspector.figure is first_figure    # same window
        assert app.inspector.lines != first_lines      # new content
    finally:
        app.close()


def test_closing_the_app_closes_the_inspector(ascan_document):
    app = OndeViewerApp(ascan_document)
    app.on_inspect()
    assert app.inspector.is_open
    app.close()
    assert not app.inspector.is_open


def test_inspector_survives_a_dataset_with_no_data(tscan_document):
    empty = [m for m in tscan_document.datasets if not m.has_data][0]
    app = OndeViewerApp(tscan_document, dataset_key=empty.short_key)
    try:
        app.on_inspect()
        assert app.inspector.is_open
        assert any("ONDE:UUID" in line for line in app.inspector.lines)
    finally:
        app.close()


# -- the action row -------------------------------------------------------

def test_action_row_exists_even_on_a_high_rank_dataset(ascan_document):
    """The column can run out of room; the export controls must not be what goes."""
    app = OndeViewerApp(ascan_document)
    try:
        assert set(app.controls.actions) == {"filename", "save_figure",
                                             "save_slice", "inspect"}
    finally:
        app.close()


def test_the_filename_box_is_not_rewritten_while_stepping(ascan_app):
    """Writing to a TextBox redraws the whole canvas; that cannot happen per step."""
    first = ascan_app.controls.filename
    ascan_app.on_index_changed(1, 3)
    assert ascan_app.controls.filename == first


def test_a_saved_file_carries_the_current_indices(ascan_app, tmp_path, monkeypatch):
    """The suggestion is regenerated at save time, so it is never stale."""
    monkeypatch.chdir(tmp_path)
    ascan_app.on_index_changed(1, 3)
    ascan_app.on_save_slice()
    written = ascan_app.status.get_text()
    assert "v_po3" in written
    assert os.path.exists(os.path.join(tmp_path, ascan_app.controls.filename))


def test_a_typed_filename_is_not_overwritten(ascan_app):
    ascan_app.controls.set_filename("mine.csv")
    ascan_app.on_index_changed(1, 2)
    assert ascan_app.controls.filename == "mine.csv"


def test_save_buttons_write_files_and_report_the_path(ascan_app, tmp_path):
    ascan_app.controls.set_filename(str(tmp_path / "out.csv"))
    ascan_app.on_save_slice()
    assert os.path.exists(tmp_path / "out.csv")
    assert "saved slice to" in ascan_app.status.get_text()

    ascan_app.controls.set_filename(str(tmp_path / "out.png"))
    ascan_app.on_save_figure()
    assert os.path.exists(tmp_path / "out.png")
    assert "saved figure to" in ascan_app.status.get_text()


def test_extension_is_corrected_per_button(ascan_app, tmp_path):
    """"save figure" on a .csv name writes the .png, rather than refusing."""
    ascan_app.controls.set_filename(str(tmp_path / "thing.csv"))
    ascan_app.on_save_figure()
    assert os.path.exists(tmp_path / "thing.png")


def test_save_failure_is_reported_not_raised(ascan_app):
    ascan_app.controls.set_filename("/nonexistent-directory/out.csv")
    ascan_app.on_save_slice()
    status = ascan_app.status.get_text()
    assert "could not save slice" in status
    assert ascan_app.status.get_color() == "firebrick"


def test_saving_a_dataset_without_data_is_reported(tscan_document):
    empty = [m for m in tscan_document.datasets if not m.has_data][0]
    app = OndeViewerApp(tscan_document, dataset_key=empty.short_key)
    try:
        app.on_save_slice()
        assert "no DATA" in app.status.get_text()
    finally:
        app.close()


def test_typing_in_the_filename_box_does_not_drive_the_viewer(ascan_app):
    """matplotlib delivers keystrokes to both the TextBox and our key handler."""
    from matplotlib.backend_bases import KeyEvent
    box = ascan_app.controls.actions["filename"]
    box.capturekeystrokes = True
    try:
        before = dict(ascan_app.state.indices)
        for key in ("right", "right", "f", "i"):
            event = KeyEvent("key_press_event", ascan_app.figure.canvas, key)
            ascan_app.figure.canvas.callbacks.process("key_press_event", event)
        assert ascan_app.state.indices == before
        assert not ascan_app.state.full_resolution
        assert not ascan_app.state.invert_y
    finally:
        box.capturekeystrokes = False


def test_keys_work_again_once_typing_stops(ascan_app):
    from matplotlib.backend_bases import KeyEvent
    ascan_app.active_axis = 1
    event = KeyEvent("key_press_event", ascan_app.figure.canvas, "right")
    ascan_app.figure.canvas.callbacks.process("key_press_event", event)
    assert ascan_app.state.indices[1] == 1


def test_exported_slice_matches_what_is_on_screen(ascan_app, ascan_model,
                                                  tmp_path):
    """End to end: whatever the line shows is what lands in the file."""
    ascan_app.on_index_changed(0, 2)
    ascan_app.controls.set_filename(str(tmp_path / "screen.npy"))
    ascan_app.on_save_slice()
    saved = np.load(tmp_path / "screen.npy")
    np.testing.assert_allclose(saved, ascan_app.plot.line.get_ydata())
