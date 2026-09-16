"""The viewer application: figure, wiring, and the state transitions.

Every interaction -- widget, key, scroll, click -- produces a new
:class:`~PyONDE.viewer.state.ViewState`, which is conformed to the current
dataset and then applied.  Rendering reads only from the state, so the same
transitions are exercised by the tests without a canvas.
"""

import os

import numpy as np

from . import export
from .blit import BlitManager
from .controls import Controls
from .inspector import MetadataInspector
from .render import MAX_DISPLAY_SAMPLES, PlotArea, _finite_limits
from .state import ViewState, default_state_for

__all__ = ["OndeViewerApp"]

#: How far the arrow keys and the scroll wheel move the active axis.
STEP_SMALL = 1
STEP_LARGE = 10

_HELP = ("arrows: step index    shift+arrows: x10    up/down: change active axis"
         "    pgup/pgdn: dataset    scroll: step    click: read value    "
         "a/s/e/i/f: auto limits, per slice, aspect, invert, full-res")


class OndeViewerApp(object):
    """An interactive view of one :class:`~PyONDE.viewer.model.OndeDocument`."""

    def __init__(self, document, dataset_key=None, figsize=(13.0, 7.5),
                 max_display_samples=MAX_DISPLAY_SAMPLES, figure=None,
                 blit=True):
        from . import require_matplotlib
        pyplot = require_matplotlib()

        self.document = document
        self.suspended = False
        self.active_axis = None
        self._limits_cache = {}

        self.figure = figure if figure is not None else \
            pyplot.figure(figsize=figsize)
        self.figure.canvas.manager.set_window_title(
            f"ondeview - {document.path}") if getattr(
                self.figure.canvas, "manager", None) else None

        self.plot_axes = self.figure.add_axes([0.27, 0.22, 0.62, 0.70])
        self.colorbar_axes = self.figure.add_axes([0.905, 0.22, 0.015, 0.70])
        self.colorbar_axes.set_visible(False)
        # Only the plot itself should answer to the toolbar's pan and zoom.
        # matplotlib already marks widget axes non-navigable; a colorbar is not
        # a widget, and panning it does nothing useful.
        self.colorbar_axes.set_navigate(False)
        self.plot = PlotArea(self.figure, self.plot_axes, self.colorbar_axes,
                             max_display_samples=max_display_samples)

        self.readout = self.figure.text(0.27, 0.155, "", fontsize=9,
                                        family="monospace")
        self.status = self.figure.text(0.27, 0.115, "", fontsize=8,
                                       color="0.25")
        self.figure.text(0.035, 0.012, _HELP, fontsize=7, color="0.4")

        self.controls = Controls(self, self.figure)
        self.inspector = MetadataInspector(self)
        self.blitter = BlitManager(self.figure) if blit else None

        model = self._initial_model(dataset_key)
        self.state = default_state_for(model).conform(model) if model else \
            ViewState("", (0,), {})
        self._rebuild_controls()
        self._auto_filename = self._default_filename()
        self.controls.build_actions(self._auto_filename)
        self._apply()
        self._connect()
        self._adopt_toolbar()

    # -- model access -------------------------------------------------------

    def _initial_model(self, dataset_key):
        if dataset_key:
            chosen = self.document.get(dataset_key)
            if chosen is not None:
                return chosen
        viewable = self.document.viewable
        if viewable:
            return viewable[0]
        return self.document.datasets[0] if self.document.datasets else None

    @property
    def model(self):
        """The dataset currently displayed."""
        return self.document.get(self.state.dataset_key)

    @property
    def dataset_labels(self):
        """[(short_key, display text)] for the dataset selector.

        The label leads and the key only disambiguates, because keys are not
        always short: PyONDE's shortkeys() returns the full UUID for any key
        that needs its maximum length, and a column of identical
        "2.25.90000000000..." prefixes identifies nothing.
        """
        texts = [model.label[:22] for model in self.document.datasets]
        duplicated = {text for text in texts if texts.count(text) > 1}
        labels = []
        for model, text in zip(self.document.datasets, texts):
            if text in duplicated:
                text = f"{text[:16]} ({model.short_key[-4:]})"
            labels.append((model.short_key, text))
        return labels

    def data_limits(self):
        """(low, high) over the whole current dataset, cached per dataset."""
        model = self.model
        if model is None or not model.has_data:
            return None
        if model.short_key not in self._limits_cache:
            raw = np.asarray(model.raw)
            low, high = _finite_limits(raw)
            if model.is_calibrated:
                scale, offset = model.amplitude.scale, model.amplitude.offset
                low, high = low * scale + offset, high * scale + offset
                if scale < 0:
                    low, high = high, low
            # A little air, so the largest peak in the dataset does not sit
            # exactly on the frame of the plot.
            margin = 0.03 * (high - low)
            self._limits_cache[model.short_key] = (low - margin, high + margin)
        return self._limits_cache[model.short_key]

    # -- state transitions --------------------------------------------------

    def set_state(self, state, rebuild=False):
        """Conform *state* to the current dataset, apply it, and redraw."""
        model = self.document.get(state.dataset_key)
        if model is None:
            return
        self.state = state.conform(model)
        if self.active_axis not in self.state.free_axes:
            free = self.state.free_axes
            self.active_axis = free[0] if free else None
        if rebuild:
            self._rebuild_controls()
            self._refresh_filename()
        self._apply()

    def _apply(self):
        model = self.model
        if model is None:
            return
        try:
            self.plot.update(model, self.state, limits=self.data_limits())
        except Exception as err:
            # A slice that cannot be read must not take the window down with
            # it: show what went wrong where the data would have been.
            self.plot.show_error(model, err)
            self._set_status(f"could not display {model.short_key}: {err}",
                             error=True)
            self.figure.canvas.draw_idle()
            return
        self._draw()

    def _draw(self):
        """Blit if the change was only to the data; redraw fully otherwise."""
        if self.blitter is None:
            self.figure.canvas.draw_idle()
            return
        if self._artists_changed():
            self.blitter.reset(self._registered_artists)
        if self.plot.needs_full_draw:
            self.blitter.invalidate()
            self.figure.canvas.draw_idle()
        else:
            self.blitter.update()

    def _animated_artists(self):
        artists = list(self.plot.animated_artists())
        for name, widget in self.controls.widgets.items():
            if not name.startswith("slider_"):
                continue
            # The slider's own handle and filled track move with it; with
            # drawon off, nothing else is going to redraw them.
            artists.append(getattr(widget, "poly", None))
            artists.append(getattr(widget, "_handle", None))
        return [artist for artist in artists if artist is not None]

    def _artists_changed(self):
        current = self._animated_artists()
        registered = getattr(self, "_registered_artists", None)
        if registered == current:
            return False
        self._registered_artists = current
        return True

    def _rebuild_controls(self):
        model = self.model
        if model is None:
            return
        self.suspended = True
        try:
            self.controls.rebuild(model, self.state, self.dataset_labels)
        finally:
            self.suspended = False
        if self.blitter is not None:
            self._registered_artists = self._animated_artists()
            self.blitter.reset(self._registered_artists)

    # -- widget handlers ----------------------------------------------------

    def on_dataset_chosen(self, short_key):
        model = self.document.get(short_key)
        if model is None:
            return
        # Carry the user's appearance preferences across, but let the axis
        # choice be recomputed for the new shape.
        fresh = default_state_for(model).evolve(
            cmap=self.state.cmap, full_resolution=self.state.full_resolution,
            clim=None)
        self.set_state(fresh, rebuild=True)

    def on_dataset_step(self, delta):
        keys = [key for key, _ in self.dataset_labels]
        if not keys:
            return
        try:
            position = keys.index(self.state.dataset_key)
        except ValueError:
            position = 0
        self.on_dataset_chosen(keys[(position + delta) % len(keys)])

    def on_x_axis_chosen(self, axis_index):
        state = self.state
        if state.is_image and axis_index == state.y_axis:
            # Swap rather than collapse the image to one axis.
            display = (state.x_axis, axis_index)
        elif state.is_image:
            display = (state.y_axis, axis_index)
        else:
            display = (axis_index,)
        self.set_state(self._with_display(display), rebuild=True)

    def on_y_axis_chosen(self, axis_index):
        state = self.state
        if axis_index is None:
            display = (state.x_axis,)
        elif axis_index == state.x_axis:
            display = (axis_index, state.y_axis) if state.is_image else \
                (axis_index,)
        else:
            display = (axis_index, state.x_axis)
        self.set_state(self._with_display(display), rebuild=True)

    def _with_display(self, display):
        """A state with new display axes, keeping indices for axes still free."""
        model = self.model
        indices = dict(self.state.indices)
        for axis in display:
            indices.pop(axis, None)
        for axis in range(model.ndim):
            if axis not in display:
                indices.setdefault(axis, 0)
        return self.state.evolve(display_axes=display, indices=indices)

    def on_index_changed(self, axis_index, value):
        indices = dict(self.state.indices)
        if axis_index not in indices:
            return
        indices[axis_index] = int(value)
        self.active_axis = axis_index
        self.set_state(self.state.evolve(indices=indices))
        axis = self.model.axes[axis_index]
        self._suspend_widgets(lambda: self.controls.sync_slider(
            axis, axis_index, self.state.indices[axis_index]))

    def on_axis_page(self, delta):
        self.controls.axis_page += delta
        self._rebuild_controls()
        self.figure.canvas.draw_idle()

    def on_cmap_chosen(self, name):
        self.set_state(self.state.evolve(cmap=name))

    def on_clim_changed(self, limits):
        self.set_state(self.state.evolve(clim=(float(limits[0]),
                                               float(limits[1]))))
        # Setting explicit limits means autoscale is no longer in effect; the
        # checkbox has to say so, or the two controls drift apart.
        self._suspend_widgets(
            lambda: self.controls.set_toggle("auto limits", False))

    def on_toggle(self, label):
        state = self.state
        if label == "auto limits":
            state = state.evolve(clim=None if state.clim else self.data_limits())
        elif label == "per slice":
            state = state.evolve(per_slice_limits=not state.per_slice_limits,
                                 clim=None)
        elif label == "equal aspect":
            state = state.evolve(
                aspect="auto" if state.aspect == "equal" else "equal")
        elif label == "invert y":
            state = state.evolve(invert_y=not state.invert_y)
        elif label == "full res":
            state = state.evolve(full_resolution=not state.full_resolution)
        self.set_state(state)

    # -- export and inspection ----------------------------------------------

    def _default_filename(self, extension=".csv"):
        model = self.model
        if model is None:
            return "onde_slice" + extension
        return export.default_filename(model, self.state, extension)

    def _refresh_filename(self):
        """Update the suggested filename, without discarding a typed one.

        Deliberately NOT called on every slider step.  Writing to a matplotlib
        TextBox redraws the whole canvas (TextBox.set_val re-renders its
        cursor), which measured at 110 ms per step on a large dataset -- it was
        costing more than the plot did and defeating the blitting entirely.
        The suggestion is refreshed when the dataset changes, and regenerated
        from the current indices at the moment of saving.
        """
        if self.controls.actions.get("filename") is None:
            return
        current = self.controls.filename
        if current and current != self._auto_filename:
            return                      # the user typed something; leave it
        self._auto_filename = self._default_filename()
        self._suspend_widgets(
            lambda: self.controls.set_filename(self._auto_filename))

    def on_filename_submitted(self, _text):
        pass                            # the text box is read when saving

    def _target_path(self, extensions, fallback):
        """The path to save to, regenerating the suggestion if untouched.

        The box is not rewritten as the sliders move (see _refresh_filename), so
        a suggested name is brought up to date here instead -- meaning the file
        always carries the indices it was actually saved at.
        """
        name = self.controls.filename
        if not name or name == self._auto_filename:
            self._auto_filename = self._default_filename(fallback)
            name = self._auto_filename
            self._suspend_widgets(
                lambda: self.controls.set_filename(self._auto_filename))
        stem, extension = os.path.splitext(name)
        if extension.lower() not in extensions:
            name = stem + fallback
        return name

    def on_save_figure(self):
        path = self._target_path(export.FIGURE_EXTENSIONS, ".png")
        try:
            # savefig draws the figure by the ordinary route, which skips
            # animated artists -- without this the saved image would be missing
            # the trace, the image and the slider handles.
            if self.blitter is None:
                written = export.save_figure(self.figure, path)
            else:
                with self.blitter.static():
                    written = export.save_figure(self.figure, path)
        except Exception as err:
            return self._set_status(f"could not save figure: {err}", error=True)
        self._set_status(f"saved figure to {os.path.abspath(written)}")

    def on_save_slice(self):
        model = self.model
        if model is None or not model.has_data:
            return self._set_status("nothing to export: this dataset has no DATA",
                                    error=True)
        path = self._target_path(export.DATA_EXTENSIONS, ".csv")
        try:
            written = export.save_slice(model, self.state, path)
        except Exception as err:
            return self._set_status(f"could not save slice: {err}", error=True)
        self._set_status(f"saved slice to {os.path.abspath(written)}")

    def on_inspect(self):
        model = self.model
        if model is None:
            return
        try:
            self.inspector.show(model)
        except Exception as err:        # pragma: no cover - backend dependent
            self._set_status(f"could not open the metadata window: {err}",
                             error=True)

    def _set_status(self, message, error=False):
        self.status.set_text(message)
        self.status.set_color("firebrick" if error else "0.25")
        self.figure.canvas.draw_idle()

    # -- the matplotlib toolbar ---------------------------------------------

    @property
    def toolbar(self):
        """The backend's navigation toolbar, or None on a bare canvas."""
        return getattr(getattr(self.figure.canvas, "manager", None),
                       "toolbar", None)

    def navigating(self):
        """True while the toolbar's pan or zoom tool has the mouse."""
        return bool(getattr(self.toolbar, "mode", ""))

    def _adopt_toolbar(self):
        """Make the backend toolbar's Save produce a complete figure.

        The toolbar saves by the ordinary draw route, which skips animated
        artists -- the same trap the viewer's own save button avoids -- so
        without this the toolbar would write out an empty plot box.
        """
        toolbar = self.toolbar
        if toolbar is None or self.blitter is None:
            return
        original = getattr(toolbar, "save_figure", None)
        if original is None or getattr(original, "_onde_wrapped", False):
            return

        def save_figure(*arguments, **keywords):
            with self.blitter.static():
                return original(*arguments, **keywords)

        save_figure._onde_wrapped = True
        toolbar.save_figure = save_figure

    # -- canvas events ------------------------------------------------------

    def _connect(self):
        canvas = self.figure.canvas
        self._connections = [
            canvas.mpl_connect("key_press_event", self.on_key),
            canvas.mpl_connect("scroll_event", self.on_scroll),
            canvas.mpl_connect("motion_notify_event", self.on_motion),
            canvas.mpl_connect("button_press_event", self.on_click),
        ]

    def on_key(self, event):
        if self.controls.is_typing():
            # A TextBox has the keyboard: matplotlib delivers the keystroke here
            # as well, and without this the filename being typed would also step
            # sliders and flip toggles.
            return
        key = (event.key or "").lower()
        if key in ("pageup", "pagedown"):
            self.on_dataset_step(-1 if key == "pageup" else +1)
            return
        toggles = {"a": "auto limits", "s": "per slice", "e": "equal aspect",
                   "i": "invert y", "f": "full res"}
        if key in toggles:
            self.on_toggle(toggles[key])
            self._rebuild_controls()
            self.figure.canvas.draw_idle()
            return
        step = 0
        if key in ("left", "shift+left"):
            step = -STEP_SMALL if key == "left" else -STEP_LARGE
        elif key in ("right", "shift+right"):
            step = STEP_SMALL if key == "right" else STEP_LARGE
        elif key in ("up", "down"):
            self._cycle_active_axis(-1 if key == "up" else +1)
            return
        if step:
            self._step_active_axis(step)

    def on_scroll(self, event):
        if event.inaxes is None:
            return
        axis_index = self.controls.axis_index_at(event.inaxes)
        if axis_index is not None:
            self.active_axis = axis_index
        elif event.inaxes is not self.plot_axes:
            return
        self._step_active_axis(int(np.sign(event.step)) or 1)

    def on_motion(self, event):
        if event.inaxes is not self.plot_axes:
            return
        self._update_readout(event.xdata, event.ydata)

    def on_click(self, event):
        if self.navigating():
            # A rubber-band zoom or a pan drag starts with a click in the plot;
            # reading out a value there as well would be noise.
            return
        if event.inaxes is self.plot_axes:
            self.set_state(self.state.evolve(cursor=(event.xdata, event.ydata)))
            self._update_readout(event.xdata, event.ydata)
            return
        axis_index = self.controls.axis_index_at(event.inaxes)
        if axis_index is not None:
            self.active_axis = axis_index

    # -- helpers ------------------------------------------------------------

    def _step_active_axis(self, step):
        if self.active_axis is None:
            return
        model = self.model
        axis = model.axes[self.active_axis]
        current = self.state.indices.get(self.active_axis, 0)
        new_index = int(np.clip(current + step, 0, axis.length - 1))
        if new_index == current:
            return
        self.on_index_changed(self.active_axis, new_index)

    def _cycle_active_axis(self, delta):
        free = list(self.state.free_axes)
        if not free:
            return
        if self.active_axis in free:
            position = free.index(self.active_axis)
        else:
            position = 0
        self.active_axis = free[(position + delta) % len(free)]
        self._update_readout(None, None)

    def _update_readout(self, x_position, y_position):
        model = self.model
        if model is None or not model.has_data:
            self.readout.set_text("")
            return
        parts = []
        if self.active_axis is not None:
            axis = model.axes[self.active_axis]
            parts.append(f"active: {axis.coordinate}"
                         f"[{self.state.indices.get(self.active_axis, 0)}]")
        if x_position is not None:
            value = self.plot.value_at(x_position, y_position, model, self.state)
            x_axis = model.axes[self.state.x_axis]
            _, x_unit = x_axis.display_scale()
            location = f"{x_axis.coordinate}={x_position:.4g} {x_unit}"
            if self.state.is_image:
                y_axis = model.axes[self.state.y_axis]
                _, y_unit = y_axis.display_scale()
                location += f"  {y_axis.coordinate}={y_position:.4g} {y_unit}"
            if value is not None:
                location += (f"  {model.amplitude.coordinate}={value:.6g} "
                             f"{model.amplitude.units}")
            parts.append(location)
        self.readout.set_text("    ".join(parts))
        self.figure.canvas.draw_idle()

    def _suspend_widgets(self, action):
        self.suspended = True
        try:
            action()
        finally:
            self.suspended = False

    # -- lifecycle ----------------------------------------------------------

    def show(self):
        """Show the figure (blocks under an interactive backend)."""
        from . import require_matplotlib
        require_matplotlib().show()

    def close(self):
        from . import require_matplotlib
        self.inspector.close()
        require_matplotlib().close(self.figure)
