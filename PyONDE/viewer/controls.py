"""The control column, built only from matplotlib.widgets.

Every control lives in its own Axes in a column down the left of the figure.
:class:`WidgetColumn` hands out those axes from a running cursor so the set of
controls can vary with the dataset (one slider per index-selected axis).

Working within matplotlib.widgets means a few things are done differently than
they would be with a GUI toolkit, and deliberately so:

  * there is no list widget, so datasets are chosen with RadioButtons up to
    :data:`MAX_RADIO_ENTRIES` and with prev/next buttons plus a text entry
    beyond that;
  * there is no file dialog, so export filenames are typed into a TextBox,
    which also means guarding the key handler while one has the keyboard;
  * sliders are the only way to fix an axis, so long ranks are paged rather
    than allowed to squeeze every slider into invisibility.

The whole column is rebuilt when the dataset changes.  That is cheap (dataset
switching is rare) and avoids a class of stale-widget bug that comes from
reconfiguring sliders in place.
"""

from matplotlib.widgets import (Button, CheckButtons, RadioButtons, RangeSlider,
                                Slider, TextBox)

__all__ = ["WidgetColumn", "Controls", "COLORMAPS", "MAX_RADIO_ENTRIES",
           "MAX_VISIBLE_SLIDERS"]

#: Colormaps offered in the column.  A short curated list, because RadioButtons
#: has no scrolling: perceptually uniform, grayscale, and a diverging map for
#: signed amplitude data.
COLORMAPS = ("viridis", "gray", "seismic", "turbo")

#: Above this many datasets, the radio list is replaced by prev/next buttons.
MAX_RADIO_ENTRIES = 8

#: Above this many index-selected axes, sliders are paged.
MAX_VISIBLE_SLIDERS = 6

_NO_Y_AXIS = "— none (waveform) —"


class WidgetColumn(object):
    """Allocates stacked axes downward within a rectangle of the figure."""

    def __init__(self, figure, left, width, top, bottom=0.04, gap=0.012):
        self.figure = figure
        self.left = left
        self.width = width
        self.top = top
        self.bottom = bottom
        self.gap = gap
        self.cursor = top
        self.axes = []

    @property
    def remaining(self):
        return self.cursor - self.bottom

    def add(self, height, label=None, indent=0.0, pad_before=0.0):
        """Allocate an Axes of *height* (figure fraction), or None if no room.

        *pad_before* leaves room above for a control that carries its caption in
        an Axes title, which would otherwise sit on top of the widget above it.
        """
        if height + self.gap + pad_before > self.remaining:
            return None
        self.cursor -= height + pad_before
        axes = self.figure.add_axes([self.left + indent, self.cursor,
                                     self.width - indent, height])
        self.cursor -= self.gap
        if label:
            axes.set_title(label, fontsize=8, loc="left", pad=2)
        self.axes.append(axes)
        return axes

    def add_row(self, height, weights):
        """Allocate several axes side by side; returns a list."""
        if height + self.gap > self.remaining:
            return []
        self.cursor -= height
        total = float(sum(weights))
        row = []
        x = self.left
        for weight in weights:
            w = self.width * weight / total
            axes = self.figure.add_axes([x, self.cursor, w * 0.92, height])
            row.append(axes)
            self.axes.append(axes)
            x += w
        self.cursor -= self.gap
        return row

    def clear(self):
        for axes in self.axes:
            try:
                self.figure.delaxes(axes)
            except Exception:
                pass
        self.axes = []
        self.cursor = self.top


class Controls(object):
    """Builds and owns every widget, and routes their callbacks to the app.

    The app supplies the handlers; this class knows nothing about ONDE beyond
    the model object it is handed for labels.
    """

    def __init__(self, app, figure, left=0.035, width=0.16, top=0.95):
        self.app = app
        self.figure = figure
        self.column = WidgetColumn(figure, left, width, top)
        self.widgets = {}
        #: Export/inspect widgets, which live in a row under the plot rather
        #: than in the column: the column can run out of room on a
        #: high-rank dataset, and these must never be the controls that vanish.
        self.actions = {}
        self.axis_page = 0
        self._x_labels = []
        self._y_labels = []
        self._slider_axes = []

    # -- construction ------------------------------------------------------

    def rebuild(self, model, state, documents_labels):
        """Recreate the whole column for *model* / *state*."""
        self.column.clear()
        self.widgets = {}
        self._slider_axes = []

        self._build_dataset_selector(documents_labels, state)
        if model.has_data:
            self._build_axis_selectors(model, state)
            self._build_sliders(model, state)
        self._build_appearance(model, state)

    def _build_dataset_selector(self, labels, state):
        if not labels:
            return
        if len(labels) <= MAX_RADIO_ENTRIES:
            height = min(0.03 + 0.022 * len(labels), 0.22)
            axes = self.column.add(height, "dataset")
            if axes is None:
                return
            active = max(0, [key for key, _ in labels].index(state.dataset_key)
                         if state.dataset_key in [key for key, _ in labels] else 0)
            radio = RadioButtons(axes, [text for _, text in labels], active=active)
            _shrink(radio)
            radio.on_clicked(self._make_guarded(
                lambda text: self.app.on_dataset_chosen(
                    dict((t, k) for k, t in labels)[text])))
            self.widgets["dataset"] = radio
        else:
            axes = self.column.add(0.035, f"dataset ({len(labels)})")
            if axes is None:
                return
            axes.axis("off")
            row = self.column.add_row(0.035, (1, 1))
            if len(row) == 2:
                previous = Button(row[0], "< prev")
                following = Button(row[1], "next >")
                previous.on_clicked(self._make_guarded(
                    lambda _event: self.app.on_dataset_step(-1)))
                following.on_clicked(self._make_guarded(
                    lambda _event: self.app.on_dataset_step(+1)))
                self.widgets["dataset_prev"] = previous
                self.widgets["dataset_next"] = following
            current = dict(labels).get(state.dataset_key, "")
            axes.text(0, 0.2, current, fontsize=8, transform=axes.transAxes)

    def _build_axis_selectors(self, model, state):
        self._x_labels = [f"{axis.index}: {axis.coordinate}" for axis in model.axes]
        x_axes = self.column.add(min(0.03 + 0.022 * len(self._x_labels), 0.20),
                                 "x axis")
        if x_axes is not None:
            radio = RadioButtons(x_axes, self._x_labels,
                                 active=state.x_axis)
            _shrink(radio)
            radio.on_clicked(self._make_guarded(
                lambda text: self.app.on_x_axis_chosen(
                    self._x_labels.index(text))))
            self.widgets["x_axis"] = radio

        self._y_labels = [_NO_Y_AXIS] + self._x_labels
        y_axes = self.column.add(min(0.03 + 0.022 * len(self._y_labels), 0.22),
                                 "y axis")
        if y_axes is not None:
            active = 0 if state.is_waveform else state.y_axis + 1
            radio = RadioButtons(y_axes, self._y_labels, active=active)
            _shrink(radio)
            radio.on_clicked(self._make_guarded(self._on_y_axis))
            self.widgets["y_axis"] = radio

    def _on_y_axis(self, text):
        if text == _NO_Y_AXIS:
            self.app.on_y_axis_chosen(None)
        else:
            self.app.on_y_axis_chosen(self._y_labels.index(text) - 1)

    def _build_sliders(self, model, state):
        free = list(state.free_axes)
        if not free:
            return
        paged = len(free) > MAX_VISIBLE_SLIDERS
        if paged:
            self.axis_page = max(0, min(self.axis_page,
                                        len(free) - MAX_VISIBLE_SLIDERS))
            visible = free[self.axis_page:self.axis_page + MAX_VISIBLE_SLIDERS]
        else:
            self.axis_page = 0
            visible = free

        for axis_index in visible:
            axis = model.axes[axis_index]
            axes = self.column.add(0.026, pad_before=0.014)
            if axes is None:
                break
            self._slider_axes.append((axes, axis_index))
            index = state.indices.get(axis_index, 0)
            # The label and value go in the title above the track: matplotlib
            # draws a Slider's own label to its left and its value to its
            # right, both of which land outside a narrow column and collide
            # with the plot.
            slider = Slider(axes, "", 0, max(axis.length - 1, 1),
                            valinit=index, valstep=1)
            slider.valtext.set_visible(False)
            # The app redraws by blitting, so the slider must not call
            # draw_idle() on every step of a drag; its handle and track are
            # registered as animated artists instead.
            slider.drawon = False
            axes.set_title(_slider_title(axis, index), fontsize=7,
                           loc="left", pad=1)
            slider.on_changed(self._make_guarded(
                lambda value, index=axis_index:
                self.app.on_index_changed(index, int(value))))
            self.widgets[f"slider_{axis_index}"] = slider
            if axis.length == 1:
                axes.set_facecolor("0.92")

        if paged:
            row = self.column.add_row(0.03, (1, 1))
            if len(row) == 2:
                up = Button(row[0], "^ axes")
                down = Button(row[1], "axes v")
                up.on_clicked(self._make_guarded(
                    lambda _event: self.app.on_axis_page(-1)))
                down.on_clicked(self._make_guarded(
                    lambda _event: self.app.on_axis_page(+1)))
                self.widgets["axis_page_up"] = up
                self.widgets["axis_page_down"] = down

    def _build_appearance(self, model, state):
        axes = self.column.add(min(0.03 + 0.022 * len(COLORMAPS), 0.14), "colormap")
        if axes is not None:
            active = COLORMAPS.index(state.cmap) if state.cmap in COLORMAPS else 0
            radio = RadioButtons(axes, list(COLORMAPS), active=active)
            _shrink(radio)
            radio.on_clicked(self._make_guarded(self.app.on_cmap_chosen))
            self.widgets["cmap"] = radio

        limits = self.app.data_limits()
        axes = self.column.add(0.026, pad_before=0.014)
        if axes is not None and limits is not None:
            low, high = limits
            if low == high:
                high = low + 1.0
            initial = state.clim if state.clim else (low, high)
            slider = RangeSlider(axes, "", low, high, valinit=initial)
            slider.valtext.set_visible(False)
            axes.set_title(f"value limits: {initial[0]:.4g} .. {initial[1]:.4g}",
                           fontsize=7, loc="left", pad=1)
            slider.on_changed(self._make_guarded(self._on_clim))
            self.widgets["clim"] = slider
            self._clim_axes = axes
        elif axes is not None:
            axes.axis("off")

        axes = self.column.add(0.115)
        if axes is not None:
            labels = ["auto limits", "per slice", "equal aspect", "invert y",
                      "full res"]
            actives = [state.clim is None, state.per_slice_limits,
                       state.aspect == "equal", state.invert_y,
                       state.full_resolution]
            checks = CheckButtons(axes, labels, actives)
            for text in checks.labels:
                text.set_fontsize(8)
            checks.on_clicked(self._make_guarded(self.app.on_toggle))
            self.widgets["toggles"] = checks

    # -- the action row -----------------------------------------------------

    def build_actions(self, initial_filename, bottom=0.055, height=0.032):
        """Build the export/inspect row once; it does not depend on the dataset."""
        filename_axes = self.figure.add_axes([0.34, bottom, 0.22, height])
        box = TextBox(filename_axes, "save as ", initial=initial_filename)
        box.label.set_fontsize(8)
        box.text_disp.set_fontsize(8)
        box.on_submit(self.app.on_filename_submitted)
        self.actions["filename"] = box

        for offset, (key, text, handler) in enumerate((
                ("save_figure", "save figure", self.app.on_save_figure),
                ("save_slice", "save slice", self.app.on_save_slice),
                ("inspect", "metadata", self.app.on_inspect))):
            axes = self.figure.add_axes([0.58 + offset * 0.115, bottom,
                                         0.105, height])
            button = Button(axes, text)
            button.label.set_fontsize(8)
            button.on_clicked(self._make_guarded(
                lambda _event, call=handler: call()))
            self.actions[key] = button

    @property
    def filename(self):
        box = self.actions.get("filename")
        return "" if box is None else box.text.strip()

    def set_filename(self, text):
        box = self.actions.get("filename")
        if box is not None and box.text != text:
            box.set_val(text)

    def is_typing(self):
        """True while a TextBox has the keyboard.

        matplotlib TextBoxes capture keystrokes but do not stop them reaching
        other key handlers, so without this check typing a filename would also
        drive the sliders and toggles.
        """
        for widget in list(self.actions.values()) + list(self.widgets.values()):
            if getattr(widget, "capturekeystrokes", False):
                return True
        return False

    # -- updates that do not need a rebuild --------------------------------

    def sync_slider(self, axis, axis_index, value):
        """Reflect an index change made elsewhere (keyboard, scroll)."""
        slider = self.widgets.get(f"slider_{axis_index}")
        if slider is None:
            return
        if slider.val != value:
            slider.set_val(value)
        slider.ax.set_title(_slider_title(axis, value), fontsize=7,
                            loc="left", pad=1)

    def set_toggle(self, label, value):
        """Force a checkbox to *value* without firing its callback."""
        checks = self.widgets.get("toggles")
        if checks is None:
            return
        labels = [text.get_text() for text in checks.labels]
        if label not in labels:
            return
        position = labels.index(label)
        if checks.get_status()[position] != value:
            checks.set_active(position)

    def _on_clim(self, limits):
        axes = getattr(self, "_clim_axes", None)
        if axes is not None:
            axes.set_title(f"value limits: {limits[0]:.4g} .. {limits[1]:.4g}",
                           fontsize=7, loc="left", pad=1)
        self.app.on_clim_changed(limits)

    def axis_index_at(self, event_axes):
        """The axis whose slider owns *event_axes*, or None."""
        for axes, axis_index in self._slider_axes:
            if axes is event_axes:
                return axis_index
        return None

    # -- callback plumbing --------------------------------------------------

    def _make_guarded(self, function):
        """Wrap a callback so programmatic widget updates do not re-enter."""
        def guarded(*arguments):
            if self.app.suspended:
                return
            return function(*arguments)
        return guarded


def _slider_title(axis, index):
    """"U Position [2] = 2 mm" -- everything the slider needs to say, above it."""
    return f"{axis.coordinate} [{index}] = {axis.format_value(index)}"


def _shrink(radio):
    """Make RadioButtons legible in a narrow column across matplotlib versions."""
    for text in radio.labels:
        text.set_fontsize(8)
    circles = getattr(radio, "circles", None)          # matplotlib < 3.7
    if circles is not None:
        for circle in circles:
            circle.set_radius(0.03)
