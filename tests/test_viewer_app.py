"""Headless tests for the interactive viewer.

Everything here runs under the Agg backend and drives the app the way a user
would -- through the widgets and canvas events -- then asserts on what the
artists actually hold.  Checking ``line.get_ydata()`` against the array computed
from the model is what catches the bugs that clicking around by hand hides: an
axis transposed, an extent off by half a pixel, a stale slice left on screen.
"""

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=True)

from matplotlib.backend_bases import KeyEvent, MouseEvent   # noqa: E402

from PyONDE.viewer.app import OndeViewerApp                 # noqa: E402
from PyONDE.viewer.state import ViewState                   # noqa: E402


@pytest.fixture
def ascan_app(ascan_document):
    app = OndeViewerApp(ascan_document)
    yield app
    app.close()


@pytest.fixture
def tscan_app(tscan_document):
    app = OndeViewerApp(tscan_document)
    yield app
    app.close()


def _click(app, x_position, y_position, axes=None):
    axes = axes or app.plot_axes
    x_pixels, y_pixels = axes.transData.transform((x_position, y_position))
    event = MouseEvent("button_press_event", app.figure.canvas,
                       x_pixels, y_pixels, button=1)
    app.figure.canvas.callbacks.process("button_press_event", event)
    return event


def _press(app, key):
    event = KeyEvent("key_press_event", app.figure.canvas, key)
    app.figure.canvas.callbacks.process("key_press_event", event)


# -- initial view ---------------------------------------------------------

def test_ascan_opens_as_a_waveform_of_the_right_samples(ascan_app, ascan_model):
    line = ascan_app.plot.line
    assert line.get_visible()
    expected = ascan_model.slice((0, 0, 0, slice(None)))
    np.testing.assert_allclose(line.get_ydata(), expected)
    np.testing.assert_allclose(line.get_xdata(),
                               ascan_model.axes[3].values() * 1e6)


def test_axis_labels_carry_calibrated_units(ascan_app):
    assert ascan_app.plot_axes.get_xlabel() == "Time (us)"
    assert ascan_app.plot_axes.get_ylabel() == "Voltage (Volts)"


def test_tscan_opens_as_an_image_with_correct_extent(tscan_app, tscan_document):
    model = tscan_document.viewable[0]
    image = tscan_app.plot.image
    assert image is not None and image.get_visible()
    np.testing.assert_allclose(image.get_array(),
                               model.slice((0, 0, slice(None), slice(None))))
    left, right = model.axes[3].extent_edges()
    bottom, top = model.axes[2].extent_edges()
    np.testing.assert_allclose(image.get_extent(),
                               (left * 1e3, right * 1e3, bottom * 1e3, top * 1e3))


def test_image_y_axis_is_inverted_for_depth(tscan_app):
    low, high = tscan_app.plot_axes.get_ylim()
    assert low > high      # depth increases downward


def test_dataset_without_data_shows_a_message(tscan_document):
    empty = [m for m in tscan_document.datasets if not m.has_data][0]
    app = OndeViewerApp(tscan_document, dataset_key=empty.short_key)
    try:
        assert app.plot.message.get_visible()
        assert "no DATA" in app.plot.message.get_text()
        assert not app.plot.line.get_visible()
    finally:
        app.close()


# -- widgets --------------------------------------------------------------

def test_slider_changes_the_displayed_slice(ascan_app, ascan_model):
    ascan_app.controls.widgets["slider_0"].set_val(2)
    assert ascan_app.state.indices[0] == 2
    np.testing.assert_allclose(ascan_app.plot.line.get_ydata(),
                               ascan_model.slice((2, 0, 0, slice(None))))


def test_slider_title_reports_the_calibrated_position(ascan_app):
    ascan_app.controls.widgets["slider_1"].set_val(3)
    title = ascan_app.controls.widgets["slider_1"].ax.get_title(loc="left")
    assert "V Position [3]" in title
    assert "6 mm" in title


def test_choosing_a_y_axis_switches_to_an_image(ascan_app, ascan_model):
    ascan_app.controls.widgets["y_axis"].set_active(1)     # "0: U Position"
    assert ascan_app.state.is_image
    assert ascan_app.state.display_axes == (0, 3)
    assert ascan_app.plot.image.get_visible()
    assert not ascan_app.plot.line.get_visible()
    np.testing.assert_allclose(ascan_app.plot.image.get_array(),
                               ascan_model.slice((slice(None), 0, 0,
                                                  slice(None))))


def test_returning_to_no_y_axis_switches_back_to_a_waveform(ascan_app):
    ascan_app.controls.widgets["y_axis"].set_active(1)
    ascan_app.controls.widgets["y_axis"].set_active(0)     # "none (waveform)"
    assert ascan_app.state.is_waveform
    assert ascan_app.plot.line.get_visible()
    assert not ascan_app.plot.image.get_visible()


def test_image_is_transposed_when_the_y_axis_comes_later(ascan_app, ascan_model):
    """y = axis 3, x = axis 1: the extracted slice must be transposed to match."""
    ascan_app.set_state(ViewState(ascan_model.short_key, (3, 1), {0: 0, 2: 0}),
                        rebuild=True)
    drawn = ascan_app.plot.image.get_array()
    assert drawn.shape == (1000, 4)
    expected = ascan_model.slice((0, slice(None), 0, slice(None))).T
    np.testing.assert_allclose(drawn, expected)


def test_switching_the_x_axis_keeps_the_image_and_swaps_correctly(tscan_app):
    tscan_app.controls.widgets["x_axis"].set_active(0)     # "0: U Position"
    assert tscan_app.state.is_image
    assert tscan_app.state.x_axis == 0


def test_colormap_radio_changes_the_image(tscan_app):
    tscan_app.controls.widgets["cmap"].set_active(1)       # gray
    assert tscan_app.state.cmap == "gray"
    assert tscan_app.plot.image.get_cmap().name == "gray"


def test_value_limit_slider_sets_the_color_limits(tscan_app):
    tscan_app.controls.widgets["clim"].set_val((0.1, 0.6))
    assert tscan_app.state.clim == pytest.approx((0.1, 0.6))
    assert tscan_app.plot.image.get_clim() == pytest.approx((0.1, 0.6))


def test_setting_value_limits_unchecks_auto_limits(tscan_app):
    """Otherwise the checkbox claims automatic while explicit limits are in force."""
    checks = tscan_app.controls.widgets["toggles"]
    labels = [text.get_text() for text in checks.labels]
    assert checks.get_status()[labels.index("auto limits")]

    tscan_app.controls.widgets["clim"].set_val((0.1, 0.6))
    assert tscan_app.state.clim == pytest.approx((0.1, 0.6))
    assert not checks.get_status()[labels.index("auto limits")]


def test_auto_limits_toggle_returns_to_automatic_limits(tscan_app):
    tscan_app.controls.widgets["clim"].set_val((0.1, 0.6))
    tscan_app.on_toggle("auto limits")
    assert tscan_app.state.clim is None
    tscan_app.on_toggle("auto limits")
    assert tscan_app.state.clim == pytest.approx(tscan_app.data_limits())


def test_aspect_and_invert_toggles(tscan_app):
    before = tscan_app.plot_axes.get_aspect()
    tscan_app.on_toggle("equal aspect")
    assert tscan_app.plot_axes.get_aspect() != before
    low, high = tscan_app.plot_axes.get_ylim()
    tscan_app.on_toggle("invert y")
    assert tscan_app.plot_axes.get_ylim() == pytest.approx((high, low))


def test_dataset_selector_switches_datasets(tscan_document):
    app = OndeViewerApp(tscan_document)
    try:
        first = app.state.dataset_key
        app.on_dataset_step(+1)
        assert app.state.dataset_key != first
        app.on_dataset_step(-1)
        assert app.state.dataset_key == first
    finally:
        app.close()


def test_dataset_labels_disambiguate_when_keys_are_unshortenable(hostile_document):
    """The hostile file's UUIDs all share a 39-character prefix."""
    app = OndeViewerApp(hostile_document)
    try:
        texts = [text for _, text in app.dataset_labels]
        assert len(set(texts)) == len(texts)
        assert not any(text.startswith("2.25.") for text in texts)
    finally:
        app.close()


# -- canvas events --------------------------------------------------------

def test_arrow_keys_step_the_active_axis(ascan_app):
    ascan_app.active_axis = 1
    _press(ascan_app, "right")
    assert ascan_app.state.indices[1] == 1
    _press(ascan_app, "right")
    assert ascan_app.state.indices[1] == 2
    _press(ascan_app, "left")
    assert ascan_app.state.indices[1] == 1


def test_arrow_keys_clamp_at_the_ends(ascan_app):
    ascan_app.active_axis = 0
    for _ in range(10):
        _press(ascan_app, "right")
    assert ascan_app.state.indices[0] == 2      # length 3
    for _ in range(10):
        _press(ascan_app, "left")
    assert ascan_app.state.indices[0] == 0


def test_shift_arrow_steps_by_ten(ascan_app):
    ascan_app.active_axis = 1
    _press(ascan_app, "shift+right")
    assert ascan_app.state.indices[1] == 3      # length 4, clamped


def test_up_down_cycles_the_active_axis(ascan_app):
    ascan_app.active_axis = 0
    _press(ascan_app, "down")
    assert ascan_app.active_axis == 1
    _press(ascan_app, "up")
    assert ascan_app.active_axis == 0


def test_letter_keys_toggle_display_options(ascan_app):
    _press(ascan_app, "f")
    assert ascan_app.state.full_resolution
    _press(ascan_app, "i")
    assert ascan_app.state.invert_y
    _press(ascan_app, "s")
    assert ascan_app.state.per_slice_limits


def test_page_keys_change_dataset(tscan_document):
    app = OndeViewerApp(tscan_document)
    try:
        first = app.state.dataset_key
        _press(app, "pagedown")
        assert app.state.dataset_key != first
    finally:
        app.close()


def test_clicking_the_plot_reads_out_the_value(ascan_app, ascan_model):
    expected = ascan_model.slice((0, 0, 0, slice(None)))
    time_axis = ascan_model.axes[3]
    index = 400
    _click(ascan_app, time_axis.value_at(index) * 1e6, float(expected[index]))
    text = ascan_app.readout.get_text()
    assert "Time=" in text
    assert "Voltage=" in text
    assert f"{expected[index]:.6g}" in text


def test_value_at_returns_none_outside_the_data(ascan_app, ascan_model):
    assert ascan_app.plot.value_at(1e9, 0.0, ascan_model,
                                   ascan_app.state) is None


def test_scrolling_over_the_plot_steps_the_active_axis(ascan_app):
    ascan_app.active_axis = 1
    x_pixels, y_pixels = ascan_app.plot_axes.transData.transform((11e0, 0.0))
    event = MouseEvent("scroll_event", ascan_app.figure.canvas,
                       x_pixels, y_pixels, step=1)
    event.inaxes = ascan_app.plot_axes
    ascan_app.figure.canvas.callbacks.process("scroll_event", event)
    assert ascan_app.state.indices[1] == 1


# -- decimation -----------------------------------------------------------

def test_long_axes_are_decimated_for_display(ascan_document):
    app = OndeViewerApp(ascan_document, max_display_samples=100)
    try:
        assert app.plot.stride[1] == 10
        assert app.plot.line.get_ydata().size == 100
        assert "1:10" in app.plot_axes.get_title()
    finally:
        app.close()


def test_full_resolution_toggle_disables_decimation(ascan_document):
    app = OndeViewerApp(ascan_document, max_display_samples=100)
    try:
        app.on_toggle("full res")
        assert app.plot.stride == (1, 1)
        assert app.plot.line.get_ydata().size == 1000
    finally:
        app.close()


def test_decimation_does_not_move_the_axis_limits(tscan_document):
    """A decimated image still covers the whole axis, so its extent is unchanged."""
    model = tscan_document.viewable[0]
    full = OndeViewerApp(tscan_document)
    coarse = OndeViewerApp(tscan_document, max_display_samples=16)
    try:
        assert coarse.plot.stride[0] > 1
        np.testing.assert_allclose(coarse.plot.image.get_extent(),
                                   full.plot.image.get_extent())
        left, right, _, _ = coarse.plot.image.get_extent()
        assert left == pytest.approx(model.axes[3].extent_edges()[0] * 1e3)
        assert right == pytest.approx(model.axes[3].extent_edges()[1] * 1e3)
    finally:
        full.close()
        coarse.close()


# -- artist hygiene -------------------------------------------------------

def test_updating_does_not_accumulate_artists(ascan_app):
    """Artists are updated in place; re-plotting on every tick would leak."""
    before = (len(ascan_app.plot_axes.lines), len(ascan_app.plot_axes.images))
    for index in range(3):
        ascan_app.controls.widgets["slider_0"].set_val(index)
    ascan_app.controls.widgets["y_axis"].set_active(1)
    for index in range(3):
        ascan_app.controls.widgets["slider_1"].set_val(index)
    after = (len(ascan_app.plot_axes.lines), len(ascan_app.plot_axes.images))
    assert after == (before[0], before[1] + 1)   # exactly one image, created once


def test_every_synthetic_file_opens_and_renders(onde_files):
    from PyONDE.viewer.model import OndeDocument
    for name in ("ascan", "tscan", "cscan", "hostile"):
        with OndeDocument.open(onde_files[name]) as document:
            app = OndeViewerApp(document)
            try:
                app.figure.canvas.draw()
            finally:
                app.close()
