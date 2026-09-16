"""Matplotlib artists for the plot area.

One :class:`PlotArea` owns a single Axes carrying both a Line2D and an
AxesImage; whichever the current :class:`~PyONDE.viewer.state.ViewState` calls
for is made visible and updated in place.  Artists are created once and updated
with ``set_data``: re-calling ``plot``/``imshow`` on every slider tick leaks
artists, resets the user's zoom, and is the usual reason matplotlib UIs get
slower the longer they are open.

This module knows nothing about PyONDE -- it takes a model object with
``axes``/``amplitude``/``slice`` and a ViewState.
"""

import numpy as np

__all__ = ["PlotArea", "MAX_DISPLAY_SAMPLES"]

#: Longest axis drawn at full resolution before display decimation kicks in.
#: A 100k-sample A-scan cannot show more than a few thousand distinguishable
#: points on screen, and striding keeps slider drags responsive.
MAX_DISPLAY_SAMPLES = 4000


def _stride_for(length, limit):
    if limit is None or length <= limit:
        return 1
    return int(np.ceil(length / float(limit)))


def _strided_values(axis, stride, factor):
    """Calibrated sample positions after striding, in display units."""
    return (np.arange(0, axis.length, stride) * axis.scale + axis.offset) * factor


def _image_edges(axis, factor):
    """Outer edges of the whole axis, for imshow extent.

    Decimation deliberately does not change these.  A decimated image still
    covers the entire axis -- its pixels are just coarser bins of it -- so the
    axis limits stay truthful and do not shift when "full res" is toggled.  The
    cost is that a drawn pixel sits at its bin center rather than exactly at the
    sample it was taken from, which is sub-pixel by construction.
    """
    low, high = axis.extent_edges()
    return (low * factor, high * factor)


def _image_centers(axis, stride, factor):
    """Centers of the drawn (possibly binned) pixels, for the cursor readout."""
    low, high = _image_edges(axis, factor)
    count = int(np.ceil(axis.length / float(stride)))
    if count <= 0:
        return np.zeros(0)
    step = (high - low) / count
    return low + (np.arange(count) + 0.5) * step


def _finite_limits(array):
    """(low, high) over the finite entries, with a fallback for empty/flat data."""
    finite = array[np.isfinite(array)] if array.size else array
    if finite.size == 0:
        return (0.0, 1.0)
    low = float(np.min(finite))
    high = float(np.max(finite))
    if low == high:
        pad = abs(low) * 0.05 or 0.5
        return (low - pad, high + pad)
    return (low, high)


class PlotArea(object):
    """The main plot: a waveform or an image, plus its colorbar."""

    def __init__(self, figure, axes, colorbar_axes=None,
                 max_display_samples=MAX_DISPLAY_SAMPLES):
        self.figure = figure
        self.axes = axes
        self.colorbar_axes = colorbar_axes
        self.max_display_samples = max_display_samples

        (self.line,) = axes.plot([], [], linewidth=1.0)
        self.line.set_visible(False)
        self.image = None
        self.colorbar = None
        #: Set when the last update decimated the data for display.
        self.stride = (1, 1)
        self._limits = None
        #: The limits this class last applied, and the view they belonged to.
        #: Used to notice that the toolbar (or anything else) has changed them.
        self._applied_limits = None
        self._view_identity = None
        self._user_navigated = False
        #: The array as last drawn, in display orientation.
        self.displayed = None
        #: True when the last update changed something a blit cannot show
        #: (limits, color limits, colormap, aspect, or the kind of plot).
        self.needs_full_draw = True
        self.message = axes.text(0.5, 0.5, "", transform=axes.transAxes,
                                 ha="center", va="center", visible=False)
        #: The fixed-index caption.  It lives inside the Axes rather than in the
        #: title because it changes on every slider step, and only artists
        #: inside the blitted region can be updated without a full redraw.
        self.annotation = axes.text(
            0.006, 0.994, "", transform=axes.transAxes, va="top", ha="left",
            fontsize=8, color="0.15",
            bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=2.0))

    # -- public -----------------------------------------------------------

    def update(self, model, state, limits=None):
        """Draw *model* according to *state*.  Returns the array drawn, or None.

        *limits* is the dataset-wide (low, high), used when the state asks for
        automatic limits and not for per-slice ones.  The caller supplies it
        because scanning the whole array on every slider step would cost more
        than the drawing does.
        """
        before = self._signature()
        self._limits = limits
        self._preserve = self._check_user_navigation(state)
        if not model.has_data:
            drawn = self._show_message(
                f"{model.label}\n\nThis dataset carries no DATA.\n"
                "(permitted by the specification when only a derived\n"
                "dataset was recorded)")
        elif state.is_image:
            drawn = self._update_image(model, state)
        else:
            drawn = self._update_waveform(model, state)
        self.needs_full_draw = self._signature() != before
        return drawn

    def _check_user_navigation(self, state):
        """True when the user's own pan/zoom should be left alone.

        The matplotlib toolbar changes the axis limits behind our back, and
        re-applying computed limits on the next slider step would throw that
        away.  So: remember the limits we applied, notice when the current ones
        differ, and from then on leave them be -- until something structural
        changes (dataset, axes, mode, explicit limits), which is a new view and
        gets fresh limits.  The toolbar's Home button restores the first view,
        as it does anywhere else.
        """
        identity = (state.dataset_key, state.display_axes, state.clim,
                    state.per_slice_limits, state.invert_y, state.aspect,
                    state.full_resolution)
        if identity != self._view_identity:
            self._view_identity = identity
            self._user_navigated = False
            return False
        if self._applied_limits is not None:
            current = (tuple(self.axes.get_xlim()), tuple(self.axes.get_ylim()))
            # Equality means the axes are showing our own view again -- the
            # toolbar's Home button, typically -- which hands control back.
            self._user_navigated = current != self._applied_limits
        return self._user_navigated

    def _apply_limits(self, xlim, ylim):
        """Set the axis limits unless the user has navigated away from ours."""
        if getattr(self, "_preserve", False):
            return
        self.axes.set_xlim(*xlim)
        self.axes.set_ylim(*ylim)
        self._applied_limits = (tuple(self.axes.get_xlim()),
                                tuple(self.axes.get_ylim()))

    @property
    def user_navigated(self):
        """True when the plot is showing a pan/zoom the user chose."""
        return self._user_navigated

    def animated_artists(self):
        """The artists a blit needs to redraw: whatever moves with the state."""
        artists = [self.annotation, self.line]
        if self.image is not None:
            artists.append(self.image)
        return artists

    def _signature(self):
        """Everything about the figure that a blit cannot bring up to date."""
        return (self.line.get_visible(),
                self.image is not None and self.image.get_visible(),
                self.message.get_visible(),
                tuple(self.axes.get_xlim()), tuple(self.axes.get_ylim()),
                str(self.axes.get_aspect()),
                self.axes.get_xlabel(), self.axes.get_ylabel(),
                self.axes.get_title(),
                None if self.image is None else tuple(self.image.get_clim()),
                None if self.image is None else self.image.get_cmap().name,
                self.colorbar_axes is not None and
                self.colorbar_axes.get_visible())

    def value_at(self, x_position, y_position, model, state):
        """Sample value under a point in data coordinates, or None if outside.

        Used for the cursor readout, so it works off the array as displayed
        (including any decimation) rather than re-slicing.
        """
        if self.displayed is None:
            return None
        x_axis = model.axes[state.x_axis]
        x_factor, y_factor = self._factors(model, state)
        if state.is_waveform:
            x_index = self._nearest(_strided_values(x_axis, self.stride[1],
                                                    x_factor), x_position)
            return None if x_index is None else float(self.displayed[x_index])
        y_axis = model.axes[state.y_axis]
        x_index = self._nearest(_image_centers(x_axis, self.stride[1], x_factor),
                                x_position)
        y_index = self._nearest(_image_centers(y_axis, self.stride[0], y_factor),
                                y_position)
        if x_index is None or y_index is None:
            return None
        return float(self.displayed[y_index, x_index])

    # -- internals --------------------------------------------------------

    def _factors(self, model, state):
        """Display-unit scale factors for the x and y axes.

        Axes are labeled in whatever SI prefix suits their span, but an equal
        aspect ratio is only meaningful when both axes use the *same* factor, so
        matched units share the x axis's choice.
        """
        x_axis = model.axes[state.x_axis]
        x_factor, _ = x_axis.display_scale()
        if not state.is_image:
            return (x_factor, 1.0)
        y_axis = model.axes[state.y_axis]
        y_factor, _ = y_axis.display_scale()
        if state.aspect == "equal" and x_axis.units == y_axis.units:
            y_factor = x_factor
        return (x_factor, y_factor)

    def _unit_label(self, axis, factor):
        native_factor, unit_label = axis.display_scale()
        if factor == native_factor:
            return unit_label
        # a matched-unit override: re-derive the prefix from the factor
        for candidate, prefix in ((1e9, "n"), (1e6, "u"), (1e3, "m"), (1.0, "")):
            if factor == candidate:
                base = "s" if axis.units.lower().startswith("s") else "m"
                return f"{prefix}{base}"
        return axis.units

    def _axis_label(self, axis, factor):
        return f"{axis.coordinate} ({self._unit_label(axis, factor)})"

    @staticmethod
    def _nearest(positions, position):
        """Index of the drawn sample nearest *position*, or None if beyond it."""
        if position is None or not np.isfinite(position) or positions.size == 0:
            return None
        index = int(np.argmin(np.abs(positions - position)))
        step = abs(positions[1] - positions[0]) if positions.size > 1 else np.inf
        if abs(positions[index] - position) > max(step, 0.0):
            return None
        return index

    def show_error(self, model, error):
        """Put a failure where the data would have been.

        A dataset whose DATA cannot be sliced -- a truncated file, an HDF5
        reference that does not resolve -- must not take the window down; the
        user still needs the controls to move to a dataset that does work.
        """
        self._show_message(f"{model.label}\n\n"
                           f"This dataset could not be displayed:\n"
                           f"{type(error).__name__}: {error}")
        self.needs_full_draw = True
        return None

    def _show_message(self, text):
        self.line.set_visible(False)
        if self.image is not None:
            self.image.set_visible(False)
        self._hide_colorbar()
        self.axes.set_xlabel("")
        self.axes.set_ylabel("")
        self.axes.set_title("")
        self.annotation.set_visible(False)
        self.message.set_text(text)
        self.message.set_visible(True)
        self.displayed = None
        return None

    def _update_waveform(self, model, state):
        self.message.set_visible(False)
        if self.image is not None:
            self.image.set_visible(False)
        self._hide_colorbar()

        axis = model.axes[state.x_axis]
        stride = 1 if state.full_resolution else \
            _stride_for(axis.length, self.max_display_samples)
        self.stride = (1, stride)

        values = model.slice(state.selector())
        values = np.asarray(state.orient(values)).ravel()[::stride]
        factor, _ = self._factors(model, state)
        positions = _strided_values(axis, stride, factor)

        self.line.set_data(positions, values)
        self.line.set_visible(True)
        self.displayed = values

        self.axes.set_xlabel(self._axis_label(axis, factor))
        self.axes.set_ylabel(f"{model.amplitude.coordinate} "
                             f"({model.amplitude.units})")
        self.axes.set_aspect("auto")
        low, high = self._limits_for(state, values)
        if state.invert_y:
            low, high = high, low
        span = ((float(positions[0]), float(positions[-1])) if positions.size
                else tuple(self.axes.get_xlim()))
        self._apply_limits(span, (low, high))
        self.axes.set_title(self._title(model, state))
        self.annotation.set_text(self._annotation_text(model, state))
        self.annotation.set_visible(True)
        return values

    def _update_image(self, model, state):
        self.message.set_visible(False)
        self.line.set_visible(False)

        y_axis = model.axes[state.y_axis]
        x_axis = model.axes[state.x_axis]
        if state.full_resolution:
            y_stride = x_stride = 1
        else:
            y_stride = _stride_for(y_axis.length, self.max_display_samples)
            x_stride = _stride_for(x_axis.length, self.max_display_samples)
        self.stride = (y_stride, x_stride)

        array = state.orient(model.slice(state.selector()))
        array = np.asarray(array)[::y_stride, ::x_stride]
        self.displayed = array

        x_factor, y_factor = self._factors(model, state)
        left, right = _image_edges(x_axis, x_factor)
        bottom, top = _image_edges(y_axis, y_factor)
        extent = (left, right, bottom, top)

        if self.image is None:
            self.image = self.axes.imshow(array, origin="lower", extent=extent,
                                          interpolation="nearest", aspect="auto")
        else:
            self.image.set_data(array)
            self.image.set_extent(extent)
        self.image.set_visible(True)
        self.image.set_cmap(state.cmap)
        self.image.set_clim(*self._limits_for(state, array))

        self.axes.set_xlabel(self._axis_label(x_axis, x_factor))
        self.axes.set_ylabel(self._axis_label(y_axis, y_factor))
        self.axes.set_aspect(state.aspect)
        self._apply_limits((left, right),
                           (top, bottom) if state.invert_y else (bottom, top))
        self.axes.set_title(self._title(model, state))
        self.annotation.set_text(self._annotation_text(model, state))
        self.annotation.set_visible(True)
        self._show_colorbar(model)
        return array

    def _limits_for(self, state, drawn):
        """Explicit limits, the dataset range, or this slice's range."""
        if state.clim:
            return tuple(state.clim)
        if not state.per_slice_limits and getattr(self, "_limits", None):
            return tuple(self._limits)
        return _finite_limits(drawn)

    def _title(self, model, state):
        """The heading: what does not change as the sliders move."""
        title = model.label
        if max(self.stride) > 1:
            title += f"   (displayed at 1:{max(self.stride)})"
        return title

    def _annotation_text(self, model, state):
        """The caption: where the fixed axes currently sit."""
        fixed = []
        for axis_index in state.free_axes:
            axis = model.axes[axis_index]
            if axis.length == 1:
                continue
            index = state.indices[axis_index]
            fixed.append(f"{axis.coordinate}={axis.format_value(index)} "
                         f"[{index}]")
        return "   ".join(fixed)

    def _show_colorbar(self, model):
        if self.colorbar_axes is None or self.image is None:
            return
        self.colorbar_axes.set_visible(True)
        if self.colorbar is None:
            self.colorbar = self.figure.colorbar(self.image,
                                                 cax=self.colorbar_axes)
        else:
            self.colorbar.update_normal(self.image)
        self.colorbar.set_label(f"{model.amplitude.coordinate} "
                                f"({model.amplitude.units})")

    def _hide_colorbar(self):
        if self.colorbar_axes is not None:
            self.colorbar_axes.set_visible(False)
