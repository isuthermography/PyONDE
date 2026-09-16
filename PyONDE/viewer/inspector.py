"""The metadata inspector: the ONDE subgraph behind a dataset, as text.

Opens in its own matplotlib figure, since the main window has no room for it and
matplotlib.widgets has no panel or tree widget.  The content is one monospace
Text artist showing a window onto the flattened tree, with a Slider acting as a
scrollbar and a TextBox filtering lines by substring.

The walk itself lives in :meth:`PyONDE.viewer.model.OndeDatasetModel.metadata_tree`,
which handles the sharing in the graph (SETUP reached by two paths is shown once)
and summarizes arrays rather than dumping them.
"""

__all__ = ["format_tree", "MetadataInspector"]

#: Fallback number of lines shown at once, when the figure cannot be measured.
#: The real count is computed from the window height by
#: :meth:`MetadataInspector.visible_lines`, so resizing the window shows more.
VISIBLE_LINES = 44


def format_tree(tree, indent=0):
    """Flatten a metadata tree into indented ``name: value`` lines."""
    pad = "  " * indent
    lines = []
    if isinstance(tree, dict):
        for name, value in tree.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{name}:")
                lines.extend(format_tree(value, indent + 1))
            else:
                lines.append(f"{pad}{name}: {_scalar(value)}")
    elif isinstance(tree, list):
        for position, value in enumerate(tree):
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}[{position}]:")
                lines.extend(format_tree(value, indent + 1))
            else:
                lines.append(f"{pad}[{position}]: {_scalar(value)}")
    else:
        lines.append(f"{pad}{_scalar(tree)}")
    return lines


def _scalar(value):
    if isinstance(value, float):
        return f"{value:g}"
    text = str(value)
    return text if len(text) <= 90 else text[:87] + "..."


class MetadataInspector(object):
    """A scrollable text view of one dataset's metadata, in its own figure."""

    def __init__(self, app, figsize=(9.0, 9.0)):
        self.app = app
        self.figsize = figsize
        self.figure = None
        self.lines = []
        self.filtered = []
        self.filter_text = ""
        self.widgets = {}

    # -- lifecycle ---------------------------------------------------------

    @property
    def is_open(self):
        if self.figure is None:
            return False
        from . import require_matplotlib
        return require_matplotlib().fignum_exists(self.figure.number)

    def show(self, model):
        """Open the inspector on *model*, or refresh it if already open."""
        from . import require_matplotlib
        pyplot = require_matplotlib()
        if not self.is_open:
            self._build(pyplot)
        self.load(model)
        try:
            self.figure.canvas.manager.show()
        except Exception:
            pass                       # headless backends have no manager
        return self.figure

    def _build(self, pyplot):
        self.figure = pyplot.figure(figsize=self.figsize)
        try:
            self.figure.canvas.manager.set_window_title("ondeview - metadata")
        except Exception:
            pass

        self.text_axes = self.figure.add_axes([0.02, 0.06, 0.93, 0.86])
        self.text_axes.axis("off")
        self.text = self.text_axes.text(
            0.0, 1.0, "", transform=self.text_axes.transAxes,
            family="monospace", fontsize=7.5, va="top", ha="left")

        scroll_axes = self.figure.add_axes([0.96, 0.06, 0.015, 0.86])
        filter_axes = self.figure.add_axes([0.10, 0.015, 0.5, 0.03])

        from matplotlib.widgets import Slider, TextBox
        # The scrollbar runs 0..1 as a fraction rather than over a line count:
        # the document length changes with every filter, and mutating a
        # Slider's valmax in place does not reliably move its handle.
        self.widgets["scroll"] = Slider(
            scroll_axes, "", 0.0, 1.0, valinit=1.0, orientation="vertical")
        self.widgets["scroll"].valtext.set_visible(False)
        self.widgets["scroll"].on_changed(lambda _value: self._render())

        self.widgets["filter"] = TextBox(filter_axes, "filter ", initial="")
        self.widgets["filter"].on_submit(self._on_filter)
        self.figure.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.figure.canvas.mpl_connect("resize_event", lambda _event:
                                       self._render())

    def close(self):
        if self.is_open:
            from . import require_matplotlib
            require_matplotlib().close(self.figure)
        self.figure = None

    # -- content -----------------------------------------------------------

    def load(self, model):
        """Replace the displayed metadata with *model*'s."""
        heading = [f"{model.label}",
                   f"{'=' * max(len(model.label), 8)}",
                   f"short key: {model.short_key}",
                   ""]
        self.lines = heading + format_tree(model.metadata_tree())
        self._apply_filter()

    def _on_filter(self, text):
        self.filter_text = (text or "").strip()
        self._apply_filter()

    def _apply_filter(self):
        if self.filter_text:
            needle = self.filter_text.lower()
            self.filtered = [line for line in self.lines
                             if needle in line.lower()]
            if not self.filtered:
                self.filtered = [f"(no line matches {self.filter_text!r})"]
        else:
            self.filtered = list(self.lines)

        scroll = self.widgets.get("scroll")
        if scroll is not None and scroll.val != 1.0:
            scroll.set_val(1.0)        # new content starts at the top
        else:
            self._render()

    def visible_lines(self):
        """How many lines fit in the window at the current size."""
        if self.figure is None:
            return VISIBLE_LINES
        height_points = self.figure.get_size_inches()[1] * 0.86 * 72.0
        line_points = self.text.get_fontsize() * 1.35
        return max(10, int(height_points / line_points))

    @property
    def _highest_offset(self):
        return max(len(self.filtered) - self.visible_lines(), 0)

    def _render(self):
        if self.figure is None:
            return
        scroll = self.widgets.get("scroll")
        # The slider runs bottom-to-top, so 1.0 is the top of the document:
        # dragging the handle up scrolls up, as a scrollbar should.
        fraction = 1.0 if scroll is None else float(scroll.val)
        offset = int(round((1.0 - fraction) * self._highest_offset))
        offset = max(0, min(offset, self._highest_offset))
        window = self.filtered[offset:offset + self.visible_lines()]
        self.text.set_text("\n".join(window))
        self.figure.canvas.draw_idle()

    def _on_scroll(self, event):
        scroll = self.widgets.get("scroll")
        if scroll is None or self._highest_offset == 0:
            return
        lines = 3.0 / self._highest_offset
        step = lines if event.step > 0 else -lines
        scroll.set_val(min(1.0, max(0.0, float(scroll.val) + step)))
