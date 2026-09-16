"""Saving what is on screen: the figure, or the data behind it.

Exports are written in SI units -- the units the file itself uses -- not in the
rescaled units the axes are *labeled* with.  A time axis shown in microseconds
exports in seconds.  Anything else would make an exported CSV disagree with the
ONDE file it came from, which is a worse surprise than a column of small numbers.

Every text export carries a header naming the dataset, its UUID, the source
file, the amplitude calibration and the position of every axis, so a slice that
ends up in someone's analysis script can still be traced back to the acquisition
it came from.
"""

import os

import numpy as np

__all__ = ["save_figure", "save_slice", "slice_header", "default_filename",
           "FIGURE_EXTENSIONS", "DATA_EXTENSIONS"]

FIGURE_EXTENSIONS = (".png", ".pdf", ".svg", ".eps", ".jpg", ".jpeg", ".tif",
                     ".tiff")
DATA_EXTENSIONS = (".csv", ".txt", ".tsv", ".npy", ".npz")


def _sanitize(text):
    keep = [character if character.isalnum() else "_" for character in str(text)]
    return "".join(keep).strip("_").lower() or "unnamed"


def default_filename(model, state, extension=".csv"):
    """A filename describing the current slice, e.g. ``ascan_3075_v2_a0.csv``."""
    # Kept short on purpose: a matplotlib TextBox neither clips nor scrolls
    # its text, so a long suggestion spills out past the widget.
    parts = [_sanitize(model.label)[:16], _sanitize(model.short_key)[:8]]
    for axis_index in state.free_axes:
        axis = model.axes[axis_index]
        if axis.length > 1:
            parts.append(f"{_sanitize(axis.coordinate)[:4]}"
                         f"{state.indices[axis_index]}")
    return "_".join(parts) + extension


def slice_header(model, state):
    """Provenance lines for a text export (without comment markers)."""
    amplitude = model.amplitude
    lines = [
        f"ONDE dataset: {model.label}",
        f"UUID: {model.full_key}",
        f"type: {' -> '.join(model.type_chain)}",
        f"source file: {model.document.path}",
        f"amplitude: {amplitude.coordinate} [{amplitude.units}] "
        f"= stored*{amplitude.scale:g} + {amplitude.offset:g}",
        "values below are in SI units, as stored in the file",
    ]
    for position, axis_index in enumerate(state.display_axes):
        axis = model.axes[axis_index]
        role = "x" if axis_index == state.x_axis else "y"
        lines.append(
            f"{role} axis: index {axis.index} {axis.coordinate} [{axis.units}] "
            f"{axis.length} samples, value = i*{axis.scale:g} + {axis.offset:g}")
    for axis_index in state.free_axes:
        axis = model.axes[axis_index]
        index = state.indices[axis_index]
        lines.append(f"fixed: index {axis.index} {axis.coordinate} "
                     f"[{index}] = {axis.value_at(index):g} {axis.units}")
    return lines


def save_figure(figure, path, dpi=150):
    """Write the figure to *path*; the format follows the extension."""
    path = str(path)
    extension = os.path.splitext(path)[1].lower()
    if extension not in FIGURE_EXTENSIONS:
        raise ValueError(f"unsupported figure format {extension!r}; "
                         f"use one of {', '.join(FIGURE_EXTENSIONS)}")
    figure.savefig(path, dpi=dpi, bbox_inches=None)
    return path


def save_slice(model, state, path):
    """Write the currently displayed slice to *path*.

    ``.npy`` stores the bare array; ``.npz`` adds the axis vectors and the
    provenance header as named entries; ``.csv``/``.tsv``/``.txt`` write the
    header as ``#`` comments followed by the data, with axis coordinates in the
    first row and column of a 2-D export.
    """
    path = str(path)
    extension = os.path.splitext(path)[1].lower()
    if extension not in DATA_EXTENSIONS:
        raise ValueError(f"unsupported data format {extension!r}; "
                         f"use one of {', '.join(DATA_EXTENSIONS)}")
    if not model.has_data:
        raise ValueError(f"dataset {model.short_key} has no DATA to export")

    array = np.asarray(state.orient(model.slice(state.selector())))
    header = slice_header(model, state)

    if extension == ".npy":
        np.save(path, array)
        return path

    if extension == ".npz":
        entries = {"data": array, "header": np.array(header, dtype=object)}
        for axis_index in state.display_axes:
            axis = model.axes[axis_index]
            entries[f"axis{axis.index}_{_sanitize(axis.coordinate)}"] = \
                axis.values()
        np.savez(path, **entries)
        return path

    delimiter = "\t" if extension == ".tsv" else ","
    with open(path, "w", encoding="utf-8") as stream:
        for line in header:
            stream.write(f"# {line}\n")
        if array.ndim == 1:
            axis = model.axes[state.x_axis]
            stream.write(f"# columns: {axis.coordinate} [{axis.units}]"
                         f"{delimiter}{model.amplitude.coordinate} "
                         f"[{model.amplitude.units}]\n")
            for position, value in zip(axis.values(), array):
                # float() first: repr() of a numpy scalar is "np.float64(1e-05)"
                # under numpy 2, which is not a number any reader will parse.
                stream.write(f"{float(position)!r}{delimiter}"
                             f"{float(value)!r}\n")
        else:
            y_axis = model.axes[state.y_axis]
            x_axis = model.axes[state.x_axis]
            stream.write(f"# rows: {y_axis.coordinate} [{y_axis.units}], "
                         f"columns: {x_axis.coordinate} [{x_axis.units}]\n")
            stream.write(delimiter.join(
                [""] + [repr(float(value)) for value in x_axis.values()]) + "\n")
            for row_value, row in zip(y_axis.values(), array):
                stream.write(delimiter.join(
                    [repr(float(row_value))] +
                    [repr(float(value)) for value in row]) + "\n")
    return path
