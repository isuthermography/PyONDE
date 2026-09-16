"""Tests for blitting, limit stability, and the error surface.

Blitting only pays off if a plain slider step leaves the axes alone, so most of
these are really tests that stepping an index changes nothing but the data.
"""

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=True)

from PyONDE.viewer.app import OndeViewerApp                # noqa: E402


@pytest.fixture
def ascan_app(ascan_document):
    app = OndeViewerApp(ascan_document)
    app.figure.canvas.draw()          # gives the blitter a background to cache
    yield app
    app.close()


# -- limit stability ------------------------------------------------------

def test_limits_do_not_move_when_stepping_an_index(ascan_app):
    """Amplitudes must stay comparable as you walk across the scan."""
    before = ascan_app.plot_axes.get_ylim()
    ascan_app.on_index_changed(0, 2)
    assert ascan_app.plot_axes.get_ylim() == pytest.approx(before)


def test_automatic_limits_span_the_whole_dataset(ascan_app, ascan_model):
    low, high = ascan_app.plot_axes.get_ylim()
    assert (low, high) == pytest.approx(ascan_app.data_limits())
    # the first slice alone is smaller than the whole dataset
    first = ascan_model.slice((0, 0, 0, slice(None)))
    assert float(np.max(first)) <= high


def test_per_slice_limits_follow_the_slice(ascan_app):
    ascan_app.on_toggle("per slice")
    assert ascan_app.state.per_slice_limits
    # In the synthetic file only the interior positions carry the flaw echo;
    # elsewhere the front-wall echo sets the amplitude, so those slices tie.
    ascan_app.on_index_changed(0, 1)
    ascan_app.on_index_changed(1, 0)
    outer = ascan_app.plot_axes.get_ylim()
    ascan_app.on_index_changed(1, 1)
    assert ascan_app.plot_axes.get_ylim() != pytest.approx(outer)


def test_explicit_limits_survive_stepping(ascan_app):
    ascan_app.on_clim_changed((-0.001, 0.001))
    ascan_app.on_index_changed(0, 1)
    assert ascan_app.plot_axes.get_ylim() == pytest.approx((-0.001, 0.001))


def test_image_colour_limits_are_stable_too(tscan_document):
    app = OndeViewerApp(tscan_document)
    app.figure.canvas.draw()
    try:
        before = app.plot.image.get_clim()
        app.on_index_changed(0, 1)
        assert app.plot.image.get_clim() == pytest.approx(before)
    finally:
        app.close()


# -- the fast path --------------------------------------------------------

def test_stepping_an_index_takes_the_blit_path(ascan_app):
    ascan_app.on_index_changed(0, 1)
    assert not ascan_app.plot.needs_full_draw
    assert ascan_app.blitter.update() is True


def test_changing_the_view_forces_a_full_redraw(ascan_app):
    ascan_app.controls.widgets["y_axis"].set_active(1)     # waveform -> image
    assert ascan_app.plot.needs_full_draw


def test_invalidating_drops_the_cached_background(ascan_app):
    assert ascan_app.blitter.background is not None
    ascan_app.blitter.invalidate()
    assert ascan_app.blitter.background is None
    assert ascan_app.blitter.update() is False      # falls back to a full draw


def test_changing_the_colormap_forces_a_full_redraw(tscan_document):
    app = OndeViewerApp(tscan_document)
    app.figure.canvas.draw()
    try:
        app.on_cmap_chosen("gray")
        assert app.plot.needs_full_draw
    finally:
        app.close()


def test_sliders_do_not_trigger_their_own_redraw(ascan_app):
    """With drawon left on, every drag step would cost a full canvas draw."""
    assert ascan_app.controls.widgets["slider_0"].drawon is False


def test_slider_handles_are_registered_as_animated(ascan_app):
    """Nothing else redraws them once drawon is off."""
    slider = ascan_app.controls.widgets["slider_0"]
    registered = ascan_app.blitter.artists
    assert slider.poly in registered
    handle = getattr(slider, "_handle", None)
    if handle is not None:
        assert handle in registered
    assert all(artist.get_animated() for artist in registered)


def test_data_artists_are_registered(ascan_app):
    assert ascan_app.plot.line in ascan_app.blitter.artists
    assert ascan_app.plot.annotation in ascan_app.blitter.artists


def test_the_fixed_index_caption_is_inside_the_axes(ascan_app):
    """It changes on every step, so it has to be blittable."""
    ascan_app.on_index_changed(1, 2)
    assert "V Position" in ascan_app.plot.annotation.get_text()
    assert ascan_app.plot.annotation.axes is ascan_app.plot_axes
    assert "V Position" not in ascan_app.plot_axes.get_title()


# -- the animated-artist trap ---------------------------------------------

def _plot_region_variance(path, axes, figure):
    """Spread of pixel values inside the plot box of a saved figure."""
    image = matplotlib.image.imread(path)
    height, width = image.shape[:2]
    box = axes.get_position()
    rows = slice(int((1 - box.y1) * height), int((1 - box.y0) * height))
    columns = slice(int(box.x0 * width), int(box.x1 * width))
    return float(np.var(image[rows, columns, :3]))


def test_saved_figure_still_contains_the_data(ascan_app, tmp_path):
    """Animated artists are skipped by ordinary draws, savefig included."""
    path = str(tmp_path / "saved.png")
    ascan_app.controls.set_filename(path)
    ascan_app.on_save_figure()
    assert "saved figure" in ascan_app.status.get_text()
    variance = _plot_region_variance(path, ascan_app.plot_axes,
                                     ascan_app.figure)
    assert variance > 1e-4, "the plot area came out blank"


def test_saving_leaves_blitting_working(ascan_app, tmp_path):
    ascan_app.controls.set_filename(str(tmp_path / "saved.png"))
    ascan_app.on_save_figure()
    assert all(artist.get_animated() for artist in ascan_app.blitter.artists)
    ascan_app.figure.canvas.draw()
    ascan_app.on_index_changed(0, 1)
    assert ascan_app.blitter.update() is True


# -- opting out -----------------------------------------------------------

def test_blitting_can_be_switched_off(ascan_document):
    app = OndeViewerApp(ascan_document, blit=False)
    try:
        assert app.blitter is None
        app.on_index_changed(0, 2)          # must still work
        assert app.state.indices[0] == 2
        assert not app.plot.line.get_animated()
    finally:
        app.close()


# -- error surface --------------------------------------------------------

def test_a_slice_that_cannot_be_read_shows_a_message(ascan_app, monkeypatch):
    """A broken dataset must not take the window down with it."""
    model = ascan_app.model

    def explode(*_args, **_kwargs):
        raise OSError("Can't read data (file read failed)")

    monkeypatch.setattr(model, "slice", explode)
    ascan_app.on_index_changed(0, 1)

    assert ascan_app.plot.message.get_visible()
    assert "could not be displayed" in ascan_app.plot.message.get_text()
    assert "OSError" in ascan_app.plot.message.get_text()
    assert "could not display" in ascan_app.status.get_text()
    assert ascan_app.status.get_color() == "firebrick"


def test_the_viewer_recovers_once_the_data_reads_again(ascan_app, monkeypatch):
    model = ascan_app.model
    original = model.slice
    monkeypatch.setattr(model, "slice",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))
    ascan_app.on_index_changed(0, 1)
    assert ascan_app.plot.message.get_visible()

    monkeypatch.setattr(model, "slice", original)
    ascan_app.on_index_changed(0, 2)
    assert not ascan_app.plot.message.get_visible()
    assert ascan_app.plot.line.get_visible()
