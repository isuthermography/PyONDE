"""Tests for living alongside matplotlib's navigation toolbar.

The toolbar comes free with any interactive backend, but three things have to
hold for it to be usable: it must only grab the plot, a pan or zoom must survive
the next slider step, and its Save button must write a figure that is not
missing the animated artists.

Agg has no toolbar, so the Save wrapping is exercised against a stand-in that
behaves like one.
"""

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=True)

from PyONDE.viewer.app import OndeViewerApp                # noqa: E402


@pytest.fixture
def ascan_app(ascan_document):
    app = OndeViewerApp(ascan_document)
    app.figure.canvas.draw()
    yield app
    app.close()


class FakeToolbar(object):
    """Stands in for a backend toolbar: a mode string and a save_figure."""

    def __init__(self, figure):
        self.figure = figure
        self.mode = ""
        self.saved_animated = None

    def save_figure(self, *_arguments, **_keywords):
        # Record what savefig would have seen at this moment.
        self.saved_animated = [artist.get_animated()
                               for artist in self.figure.get_children()]
        return "saved"


def _attach(app, toolbar=None):
    toolbar = toolbar if toolbar is not None else FakeToolbar(app.figure)
    app.figure.canvas.manager.toolbar = toolbar
    app._adopt_toolbar()
    return toolbar


def _attach_real(app):
    """A real NavigationToolbar2 on the Agg canvas: no buttons, full behavior."""
    from matplotlib.backend_bases import NavigationToolbar2
    return _attach(app, NavigationToolbar2(app.figure.canvas))


def _drag(toolbar, axes, canvas, start, end):
    from matplotlib.backend_bases import MouseEvent
    first = axes.transData.transform(start)
    last = axes.transData.transform(end)
    toolbar.press_zoom(MouseEvent("button_press_event", canvas, *first, button=1))
    toolbar.release_zoom(MouseEvent("button_release_event", canvas, *last,
                                    button=1))


# -- what the toolbar may touch -------------------------------------------

def test_only_the_plot_answers_to_pan_and_zoom(ascan_app):
    navigable = [axes for axes in ascan_app.figure.axes if axes.get_navigate()]
    assert navigable == [ascan_app.plot_axes]


def test_the_colorbar_is_not_navigable(tscan_document):
    app = OndeViewerApp(tscan_document)
    try:
        assert app.colorbar_axes.get_visible()      # an image, so it is shown
        assert not app.colorbar_axes.get_navigate()
    finally:
        app.close()


# -- a zoom has to survive the next slider step ---------------------------

def test_a_zoom_survives_stepping_an_index(ascan_app):
    ascan_app.plot_axes.set_xlim(13.5, 15.0)
    ascan_app.plot_axes.set_ylim(-0.002, 0.002)
    ascan_app.on_index_changed(0, 2)
    assert ascan_app.plot_axes.get_xlim() == pytest.approx((13.5, 15.0))
    assert ascan_app.plot_axes.get_ylim() == pytest.approx((-0.002, 0.002))
    assert ascan_app.plot.user_navigated


def test_the_data_still_updates_while_zoomed(ascan_app, ascan_model):
    ascan_app.plot_axes.set_xlim(13.5, 15.0)
    ascan_app.on_index_changed(0, 2)
    np.testing.assert_allclose(ascan_app.plot.line.get_ydata(),
                               ascan_model.slice((2, 0, 0, slice(None))))


def test_blitting_still_works_while_zoomed(ascan_app):
    ascan_app.plot_axes.set_xlim(13.5, 15.0)
    ascan_app.figure.canvas.draw()
    ascan_app.on_index_changed(0, 1)
    assert not ascan_app.plot.needs_full_draw
    assert ascan_app.blitter.update() is True


def test_changing_the_view_discards_the_zoom(ascan_app):
    ascan_app.plot_axes.set_xlim(13.5, 15.0)
    ascan_app.on_index_changed(0, 1)
    ascan_app.controls.widgets["y_axis"].set_active(1)     # waveform -> image
    assert not ascan_app.plot.user_navigated
    assert ascan_app.plot_axes.get_xlim() != pytest.approx((13.5, 15.0))


def test_new_value_limits_override_a_zoom(ascan_app):
    """Moving the limits slider is an instruction about the axis, so it wins."""
    ascan_app.plot_axes.set_ylim(-0.002, 0.002)
    ascan_app.on_clim_changed((-0.005, 0.005))
    assert ascan_app.plot_axes.get_ylim() == pytest.approx((-0.005, 0.005))


def test_switching_dataset_discards_the_zoom(tscan_document):
    app = OndeViewerApp(tscan_document)
    try:
        app.plot_axes.set_xlim(-5.0, 0.0)
        app.on_dataset_step(+1)
        app.on_dataset_step(-1)
        assert not app.plot.user_navigated
    finally:
        app.close()


# -- against a real NavigationToolbar2 ------------------------------------

def test_a_real_toolbar_zoom_is_kept_and_home_gives_it_back(ascan_app):
    toolbar = _attach_real(ascan_app)
    automatic = ascan_app.plot_axes.get_xlim()

    toolbar.zoom()
    assert ascan_app.navigating()
    _drag(toolbar, ascan_app.plot_axes, ascan_app.figure.canvas,
          (13.5, -0.002), (15.0, 0.002))
    zoomed = ascan_app.plot_axes.get_xlim()
    # the drag goes through pixel coordinates, so allow a pixel of slop
    assert zoomed == pytest.approx((13.5, 15.0), abs=0.05)

    ascan_app.on_index_changed(0, 2)
    assert ascan_app.plot_axes.get_xlim() == pytest.approx(zoomed)
    assert ascan_app.plot.user_navigated

    toolbar.home()
    ascan_app.on_index_changed(0, 1)
    assert ascan_app.plot_axes.get_xlim() == pytest.approx(automatic)
    assert not ascan_app.plot.user_navigated


def test_a_real_toolbar_gets_its_save_wrapped(ascan_app):
    toolbar = _attach_real(ascan_app)
    assert getattr(toolbar.save_figure, "_onde_wrapped", False)


# -- clicks during pan/zoom -----------------------------------------------

def test_clicking_while_zooming_does_not_read_out_a_value(ascan_app):
    from matplotlib.backend_bases import MouseEvent
    toolbar = _attach(ascan_app)
    toolbar.mode = "zoom rect"
    assert ascan_app.navigating()

    x_pixels, y_pixels = ascan_app.plot_axes.transData.transform((14.0, 0.0))
    event = MouseEvent("button_press_event", ascan_app.figure.canvas,
                       x_pixels, y_pixels, button=1)
    ascan_app.figure.canvas.callbacks.process("button_press_event", event)
    assert ascan_app.readout.get_text() == ""

    toolbar.mode = ""
    ascan_app.figure.canvas.callbacks.process("button_press_event", event)
    assert "Time=" in ascan_app.readout.get_text()


# -- the toolbar's own Save button ----------------------------------------

def test_toolbar_save_is_wrapped_to_include_the_data(ascan_app):
    toolbar = _attach(ascan_app)
    assert ascan_app.plot.line.get_animated()      # blitting is on

    toolbar.save_figure()
    # Inside the wrapped call nothing may be animated, or savefig skips it.
    assert toolbar.saved_animated is not None
    assert not any(toolbar.saved_animated)
    # and afterwards blitting is back on
    assert ascan_app.plot.line.get_animated()


def test_toolbar_save_is_wrapped_only_once(ascan_app):
    toolbar = _attach(ascan_app)
    first = toolbar.save_figure
    ascan_app._adopt_toolbar()
    assert toolbar.save_figure is first          # not wrapped a second time
    assert getattr(first, "_onde_wrapped", False)


def test_no_toolbar_is_not_an_error(ascan_app):
    assert ascan_app.toolbar is None or hasattr(ascan_app.toolbar, "mode")
    assert ascan_app.navigating() is False
    ascan_app._adopt_toolbar()      # must be a no-op, not a crash


def test_toolbar_save_untouched_when_blitting_is_off(ascan_document):
    app = OndeViewerApp(ascan_document, blit=False)
    try:
        toolbar = FakeToolbar(app.figure)
        app.figure.canvas.manager.toolbar = toolbar
        app._adopt_toolbar()
        # nothing to protect against: no artist is animated without blitting
        assert not getattr(toolbar.save_figure, "_onde_wrapped", False)
    finally:
        app.close()
