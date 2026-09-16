"""The complete state of one view, as plain data.

Every widget callback in the eventual UI produces a new :class:`ViewState`; the
application diffs it against the previous one and touches only the artists that
changed.  Keeping the state immutable and matplotlib-free means the interaction
logic -- which axes are displayed, what a slider does, what happens when the
dataset changes rank -- is testable without a canvas.
"""

import numpy as np

__all__ = ["ViewState", "default_state_for"]


class ViewState(object):
    """An immutable description of what should currently be on screen.

    Attributes:
        dataset_key: short key of the dataset being displayed.
        display_axes: axis indices mapped to the display.  One entry means a
            waveform (that axis along x); two mean an image, ordered (y, x).
        indices: ``{axis_index: sample_index}`` for every axis not displayed.
        clim: explicit (low, high) limits, or None to scale automatically.
        per_slice_limits: with clim None, scale to the slice on screen rather
            than to the whole dataset.  Dataset-wide is the default because it
            makes amplitudes comparable as you step through positions -- and
            because limits that change on every step defeat blitting.
        cmap: colormap name.
        aspect: 'auto' or 'equal'.
        invert_y: draw the y axis increasing downward (natural for depth/time).
        full_resolution: bypass display decimation of long axes.
        cursor: last picked point in calibrated coordinates, or None.
    """

    __slots__ = ("dataset_key", "display_axes", "indices", "clim", "cmap",
                 "aspect", "invert_y", "full_resolution", "per_slice_limits",
                 "cursor")

    def __init__(self, dataset_key, display_axes, indices, clim=None,
                 cmap="viridis", aspect="auto", invert_y=False,
                 full_resolution=False, per_slice_limits=False, cursor=None):
        object.__setattr__(self, "dataset_key", dataset_key)
        object.__setattr__(self, "display_axes", tuple(int(a) for a in display_axes))
        object.__setattr__(self, "indices", dict(indices))
        object.__setattr__(self, "clim", None if clim is None else tuple(clim))
        object.__setattr__(self, "cmap", cmap)
        object.__setattr__(self, "aspect", aspect)
        object.__setattr__(self, "invert_y", bool(invert_y))
        object.__setattr__(self, "full_resolution", bool(full_resolution))
        object.__setattr__(self, "per_slice_limits", bool(per_slice_limits))
        object.__setattr__(self, "cursor", None if cursor is None else tuple(cursor))

    def __setattr__(self, name, value):
        raise AttributeError("ViewState is immutable; use .evolve(...)")

    def evolve(self, **changes):
        """Return a copy with *changes* applied."""
        fields = {name: getattr(self, name) for name in self.__slots__}
        fields.update(changes)
        return ViewState(**fields)

    # -- derived ----------------------------------------------------------

    @property
    def is_waveform(self):
        return len(self.display_axes) == 1

    @property
    def is_image(self):
        return len(self.display_axes) == 2

    @property
    def x_axis(self):
        """Axis index drawn along x (the last display axis in both modes)."""
        return self.display_axes[-1]

    @property
    def y_axis(self):
        """Axis index drawn along y, or None in waveform mode."""
        return self.display_axes[0] if self.is_image else None

    @property
    def free_axes(self):
        """Axis indices that are index-selected, in ascending order."""
        return tuple(sorted(self.indices))

    def selector(self):
        """Index tuple for :meth:`OndeDatasetModel.slice`.

        Displayed axes become full slices; every other axis becomes its fixed
        integer index.  The result indexes the array in its natural axis order,
        so an image whose display axes are (y, x) = (3, 1) comes back
        transposed relative to the screen -- :meth:`orient` handles that.
        """
        rank = max(list(self.indices) + list(self.display_axes), default=-1) + 1
        selector = []
        for axis in range(rank):
            if axis in self.display_axes:
                selector.append(slice(None))
            else:
                selector.append(int(self.indices.get(axis, 0)))
        return tuple(selector)

    def orient(self, extracted):
        """Put an extracted slice into display order.

        ``selector()`` preserves the array's own axis order, which matches the
        screen only when the display axes are already ascending.  When the user
        maps a later axis to y, the slice needs transposing.
        """
        array = np.asarray(extracted)
        if not self.is_image or array.ndim != 2:
            return array
        y_axis, x_axis = self.display_axes
        return array.T if y_axis > x_axis else array

    # -- validity ---------------------------------------------------------

    def conform(self, model):
        """Return a state valid for *model*, repairing anything that is not.

        Switching datasets can invalidate axis choices and indices wholesale, so
        every state that reaches the renderer goes through here first: out-of-
        range indices are clamped, missing axes are filled with 0, references to
        axes the new dataset does not have fall back to defaults.
        """
        if not model.has_data:
            return self
        rank = model.ndim
        display = tuple(a for a in self.display_axes if 0 <= a < rank)
        if not display or len(display) != len(set(display)):
            return default_state_for(model).evolve(
                cmap=self.cmap, aspect=self.aspect, invert_y=self.invert_y,
                full_resolution=self.full_resolution,
                per_slice_limits=self.per_slice_limits)

        indices = {}
        for axis in range(rank):
            if axis in display:
                continue
            wanted = int(self.indices.get(axis, 0))
            indices[axis] = int(np.clip(wanted, 0, model.axes[axis].length - 1))
        return self.evolve(dataset_key=model.short_key, display_axes=display,
                           indices=indices)

    def __eq__(self, other):
        if not isinstance(other, ViewState):
            return NotImplemented
        return all(getattr(self, name) == getattr(other, name)
                   for name in self.__slots__)

    def __repr__(self):
        mode = "waveform" if self.is_waveform else "image"
        return (f"ViewState({self.dataset_key!r}, {mode}, "
                f"display_axes={self.display_axes}, indices={self.indices})")


def default_state_for(model):
    """Choose a sensible initial view for *model*.

    The heuristic, in order:

      * rank 0/1, or a single non-degenerate axis -> waveform along it;
      * a time-like axis that is also the longest -> waveform along it, every
        other axis at index 0.  This is what makes an A-scan file open as a
        waveform without any A-scan-specific code;
      * otherwise -> image over the two longest axes, earlier axis on y.

    Degenerate axes (length 1) are never chosen for display when an alternative
    exists, since a one-pixel image is not a view of anything.
    """
    if not model.has_data:
        return ViewState(model.short_key, (0,), {})

    axes = model.axes
    rank = len(axes)
    if rank == 1:
        return ViewState(model.short_key, (0,), {})

    substantive = [axis.index for axis in axes if axis.length > 1]
    if not substantive:
        substantive = [axis.index for axis in axes]

    if len(substantive) == 1:
        display = (substantive[0],)
    else:
        by_length = sorted(substantive, key=lambda i: axes[i].length, reverse=True)
        longest = by_length[0]
        if axes[longest].kind == "time":
            # A-scan-shaped: the long time axis is the thing to plot.
            display = (longest,)
        else:
            chosen = sorted(by_length[:2])
            display = (chosen[0], chosen[1])

    indices = {axis.index: 0 for axis in axes if axis.index not in display}
    invert_y = False
    if len(display) == 2:
        y_kind = axes[display[0]].kind
        invert_y = y_kind in ("time",) or "depth" in axes[display[0]].coordinate.lower()
    aspect = "auto"
    if len(display) == 2:
        y_units = axes[display[0]].units.strip().lower()
        x_units = axes[display[1]].units.strip().lower()
        if y_units == x_units and axes[display[0]].kind == "space":
            aspect = "equal"
    return ViewState(model.short_key, display, indices,
                     aspect=aspect, invert_y=invert_y)
