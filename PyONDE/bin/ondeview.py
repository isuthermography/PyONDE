"""Command line entry point for the ONDE viewer.

``ondeview FILE``            open the interactive viewer (Phase 2)
``ondeview --list FILE``     one line per dataset: key, type, shape, label
``ondeview --info KEY FILE`` axes, calibration and metadata for one dataset

The listing paths need only numpy and h5py, so they work on a plain
``pip install PyONDE``.  The viewer additionally needs matplotlib, which
PyONDE does not declare as a dependency; ``ondeview FILE`` says so, in a
message box as well as on stderr, when it is not installed.
"""

import argparse
import os
import sys

from ..viewer.model import OndeDocument

#: Opening a file costs roughly its size in RAM, because PyONDE reads every
#: HDF5 dataset eagerly.  Warn rather than let a big file look like a hang.
LARGE_FILE_BYTES = 1 << 30


def _print_warnings(document, stream):
    for message in document.warnings:
        print(f"warning: {message}", file=stream)


def _format_axes(model):
    lines = []
    for axis in model.axes:
        span_low, span_high = axis.extent_edges()
        factor, unit_label = axis.display_scale()
        lines.append(
            f"    axis {axis.index}: {axis.length:>6} x {axis.coordinate:<14} "
            f"[{axis.kind:<7}] "
            f"{span_low * factor:.4g} .. {span_high * factor:.4g} {unit_label}"
            + ("  (spec defaults)" if axis.is_default else ""))
    return lines


def _dump_tree(tree, stream, indent=6):
    pad = " " * indent
    if isinstance(tree, dict):
        for name, value in tree.items():
            if isinstance(value, (dict, list)):
                print(f"{pad}{name}:", file=stream)
                _dump_tree(value, stream, indent + 2)
            else:
                print(f"{pad}{name}: {value}", file=stream)
    elif isinstance(tree, list):
        for position, value in enumerate(tree):
            if isinstance(value, (dict, list)):
                print(f"{pad}[{position}]:", file=stream)
                _dump_tree(value, stream, indent + 2)
            else:
                print(f"{pad}[{position}]: {value}", file=stream)
    else:
        print(f"{pad}{tree}", file=stream)


def command_list(document, stream):
    print(f"{document.path}", file=stream)
    version = document.file_version or "unknown"
    filetype = ", ".join(document.filetype) or "unspecified"
    print(f"  ONDE:VERSION {version}   ONDE:FILETYPE {filetype}   "
          f"read with class definitions {document.onde_version}", file=stream)
    if not document.datasets:
        print("  (no dataset entry points found)", file=stream)
        return 0
    header = f"{'key':>8}  {'type':<24} {'shape':<28} label"
    print(f"  {header}", file=stream)
    for model in document.datasets:
        print(f"  {model.summary()}", file=stream)
    _print_warnings(document, stream)
    return 0


def command_info(document, key, stream):
    model = document.get(key)
    if model is None:
        print(f"error: no dataset {key!r}; known keys: "
              f"{', '.join(m.short_key for m in document.datasets)}",
              file=sys.stderr)
        return 2
    print(f"{model.short_key}  {model.label}", file=stream)
    print(f"  UUID          {model.full_key}", file=stream)
    print(f"  type chain    {' -> '.join(model.type_chain)}", file=stream)
    if not model.has_data:
        print("  DATA          absent (permitted by the specification)", file=stream)
    else:
        print(f"  DATA          {'x'.join(str(n) for n in model.shape)} "
              f"{model.dtype} ({model.size_bytes / 1e6:.1f} MB in memory)",
              file=stream)
        amplitude = model.amplitude
        print(f"  amplitude     {amplitude.coordinate} ({amplitude.units}) "
              f"scale={amplitude.scale:g} offset={amplitude.offset:g}"
              + ("  (spec defaults)" if amplitude.is_default else ""), file=stream)
        for line in _format_axes(model):
            print(line, file=stream)
    for message in model.warnings:
        print(f"  warning: {message}", file=stream)
    print("  metadata:", file=stream)
    _dump_tree(model.metadata_tree(), stream)
    return 0


#: Backends that can render a figure but cannot show a window.
NON_INTERACTIVE_BACKENDS = frozenset(
    ("agg", "cairo", "pdf", "pgf", "ps", "svg", "template"))


def command_view(document, key, stream):
    from ..viewer import (report_missing_matplotlib, require_matplotlib,
                          view_document)
    try:
        require_matplotlib()
    except ImportError:
        # Not just a message on stderr: this is the one command that may have
        # been started from a desktop launcher or a file association, with
        # nowhere for the text to land.  report_missing_matplotlib also puts
        # it in a box when the machine can draw one.
        report_missing_matplotlib()
        return 3

    import matplotlib
    backend = matplotlib.get_backend()
    if backend.lower() in NON_INTERACTIVE_BACKENDS:
        print(f"error: matplotlib is using the non-interactive {backend!r} "
              f"backend, so no window can be opened. Try:\n"
              f"    MPLBACKEND=QtAgg ondeview {document.path}\n"
              f"(or TkAgg, or install PyQt5/PySide6). "
              f"'ondeview --list' works on any backend.", file=sys.stderr)
        return 4

    if not document.viewable:
        print("error: no dataset in this file carries DATA to display",
              file=sys.stderr)
        return 5

    for message in document.warnings:
        print(f"warning: {message}", file=sys.stderr)
    view_document(document, dataset=key, show=True)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ondeview",
        description="View multidimensional data stored in ONDE files.")
    parser.add_argument("file", help="path to an .onde (HDF5) file")
    parser.add_argument("-l", "--list", action="store_true",
                        help="list the datasets in the file and exit")
    parser.add_argument("-i", "--info", metavar="KEY",
                        help="describe one dataset (axes, calibration, metadata)")
    parser.add_argument("-d", "--dataset", metavar="KEY",
                        help="dataset to show first in the viewer")
    from ..viewer.access import DEFAULT_ONDE_VERSION
    parser.add_argument("--onde-version", default=DEFAULT_ONDE_VERSION,
                        help="ONDE class definitions to read with (default: "
                             "%(default)s). This selects which fields PyONDE "
                             "knows about by their short names, not what the "
                             "file must contain.")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    stream = sys.stdout

    if not os.path.exists(arguments.file):
        print(f"error: no such file: {arguments.file}", file=sys.stderr)
        return 2

    size = os.path.getsize(arguments.file)
    if size > LARGE_FILE_BYTES:
        print(f"note: {size / 1e9:.1f} GB file; PyONDE loads ONDE files entirely "
              f"into memory, so this may take a while and needs comparable RAM.",
              file=sys.stderr)

    try:
        document = OndeDocument.open(arguments.file,
                                     onde_version=arguments.onde_version)
    except Exception as err:
        print(f"error: cannot read {arguments.file}: "
              f"{type(err).__name__}: {err}", file=sys.stderr)
        return 1

    try:
        if arguments.info:
            return command_info(document, arguments.info, stream)
        if arguments.list:
            return command_list(document, stream)
        return command_view(document, arguments.dataset, stream)
    except BrokenPipeError:
        # `ondeview --list big.onde | head` closes the pipe under us; a
        # listing tool should stop quietly rather than print a traceback.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    finally:
        document.close()


if __name__ == "__main__":
    sys.exit(main())
