"""Dimension-driven model of an ONDE file, for viewing.

This layer turns the ONDE graph into something a plotting front end can consume
without knowing anything about PyONDE: a list of datasets, each with a shape, an
:class:`AxisDescriptor` per data axis, an amplitude descriptor, and a
:meth:`OndeDatasetModel.slice` method that is the single path by which bulk data
is read.

Two deliberate properties:

  * **No matplotlib.**  Everything here is testable headless and usable from a
    script or notebook without the viewer extra installed.
  * **One bulk-read chokepoint.**  PyONDE currently reads every HDF5 dataset
    eagerly at open time, so slicing is a cheap in-memory view today.  Routing
    every read through :meth:`OndeDatasetModel.slice` is what will make a lazy
    (h5py-backed) implementation a change to this file alone.

Spec defaults implemented here, from ONDE_DATASET / ONDE_DIMENSION:

  * a missing index dimension is coordinate "Time", units "seconds";
  * a missing amplitude dimension is coordinate "Amplitude", units "arbitrary";
  * OFFSET defaults to 0.0, SCALE to 1.0;
  * calibrated value = stored*SCALE + OFFSET, applied to zero-based indices for
    index dimensions and to the data itself for the amplitude dimension.
"""

import warnings

import numpy as np

from . import access
from ..onde import ONDEArray, ONDEReferenceArray, ONDEValue

__all__ = ["AxisDescriptor", "OndeDatasetModel", "OndeDocument"]

#: Warning categories the document collects rather than letting them escape to
#: stderr.  Anything else PyONDE raises is re-raised for whoever was listening.
try:
    from ..onde import ONDEClassDerivationWarning as _ONDEClassDerivationWarning
    _COLLECTED_WARNINGS = (_ONDEClassDerivationWarning,)
except ImportError:                 # pragma: no cover - older PyONDE
    _COLLECTED_WARNINGS = ()


#: Coordinate/units defaults for an absent index dimension (ONDE_DATASET).
DEFAULT_INDEX_COORDINATE = "Time"
DEFAULT_INDEX_UNITS = "seconds"

#: Coordinate/units defaults for an absent amplitude dimension (ONDE_DATASET).
DEFAULT_AMPLITUDE_COORDINATE = "Amplitude"
DEFAULT_AMPLITUDE_UNITS = "arbitrary"

_TIME_WORDS = ("time", "tof", "flight")
_SPACE_WORDS = ("position", "depth", "distance", "thickness", "row", "col",
                "plane", "x", "y", "z", "u", "v")
_CHANNEL_WORDS = ("ascan", "a-scan", "law", "channel", "element", "probe",
                  "shot", "sequence")

_SI_PREFIXES = ((1e-9, 1e9, "n"), (1e-6, 1e6, "u"), (1e-3, 1e3, "m"), (1.0, 1.0, ""))


def _unit_is(units, *names):
    text = (units or "").strip().lower()
    return text in names


class AxisDescriptor(object):
    """One axis of a dataset: its length and its ONDE_DIMENSION calibration.

    Calibrated coordinate of sample *i* is ``i*scale + offset``, in ``units``.
    """

    def __init__(self, index, length, coordinate=None, units=None,
                 scale=1.0, offset=0.0, is_default=False):
        self.index = int(index)
        self.length = int(length)
        self.coordinate = coordinate if coordinate else DEFAULT_INDEX_COORDINATE
        self.units = units if units else DEFAULT_INDEX_UNITS
        self.scale = 1.0 if scale is None else float(scale)
        self.offset = 0.0 if offset is None else float(offset)
        #: True when no ONDE_DIMENSION was present and spec defaults were applied.
        self.is_default = bool(is_default)

    @classmethod
    def from_dimension(cls, index, length, dimension,
                       default_coordinate=DEFAULT_INDEX_COORDINATE,
                       default_units=DEFAULT_INDEX_UNITS):
        """Build from an ONDE_DIMENSION object, filling in the documented defaults."""
        if dimension is None:
            return cls(index, length, default_coordinate, default_units,
                       1.0, 0.0, is_default=True)
        coordinate = dimension._field_value("COORDINATE", None)
        units = dimension._field_value("UNITS", None)
        scale = dimension._field_value("SCALE", 1.0)
        offset = dimension._field_value("OFFSET", 0.0)
        # A COORDINATE of "None" is how the demo writer spells "unused axis".
        if isinstance(coordinate, str) and coordinate.strip().lower() == "none":
            coordinate = None
        return cls(index, length,
                   coordinate if coordinate else default_coordinate,
                   units if units else default_units,
                   scale, offset)

    # -- calibration ------------------------------------------------------

    def values(self):
        """Calibrated coordinate of every sample along this axis."""
        return np.arange(self.length) * self.scale + self.offset

    def value_at(self, index):
        """Calibrated coordinate of one sample."""
        return index * self.scale + self.offset

    def extent_edges(self):
        """(low, high) outer edges, for use as imshow ``extent``.

        Sample centers are at ``i*scale + offset``, so the edges sit half a step
        beyond the first and last centers.  Using centers as extent would shift
        the image by half a pixel, which matters when reading a position off a
        C-scan.
        """
        half = 0.5 * self.scale
        first = self.value_at(0) - half
        last = self.value_at(max(self.length - 1, 0)) + half
        return (first, last)

    # -- presentation -----------------------------------------------------

    @property
    def kind(self):
        """Advisory classification: 'time', 'space', 'channel' or 'index'.

        Used only to choose default axis assignment; the user can display any
        axis against any other.
        """
        # The coordinate name is checked before the units, because units are the
        # field most often left out: a dimension named "U Position" with no
        # UNITS inherits the spec default "seconds", and reading that as a time
        # axis would be exactly wrong.
        coordinate = self.coordinate.lower()
        coordinate_words = coordinate.replace("_", " ").split()
        if any(word in _SPACE_WORDS for word in coordinate_words):
            return "space"
        if any(word in coordinate for word in _TIME_WORDS):
            return "time"
        if any(word in coordinate for word in _CHANNEL_WORDS):
            return "channel"
        if _unit_is(self.units, "seconds", "second", "s"):
            return "time"
        if _unit_is(self.units, "meters", "meter", "m", "millimeters", "mm"):
            return "space"
        return "index"

    def display_scale(self):
        """(factor, unit_label) for human-readable axis labels.

        UT data lives at microseconds and millimeters; showing ``1.2e-05 seconds``
        on a slider helps nobody.  Only the two SI units the spec mandates are
        rescaled, and only the label changes -- stored values stay SI.
        """
        if not _unit_is(self.units, "seconds", "second", "s", "meters", "meter", "m"):
            return (1.0, self.units)
        span = abs(self.scale) * max(self.length - 1, 1)
        if span <= 0 or not np.isfinite(span):
            return (1.0, self.units)
        base = "s" if _unit_is(self.units, "seconds", "second", "s") else "m"
        for threshold, factor, prefix in _SI_PREFIXES:
            if span < threshold * 1000.0:
                return (factor, f"{prefix}{base}")
        return (1.0, self.units)

    @property
    def label(self):
        """Axis label including units, e.g. ``"U Position (mm)"``."""
        _, unit_label = self.display_scale()
        suffix = " [default]" if self.is_default else ""
        return f"{self.coordinate} ({unit_label}){suffix}"

    def format_value(self, index):
        """Calibrated value of *index* as a short display string with units."""
        factor, unit_label = self.display_scale()
        return f"{self.value_at(index) * factor:.4g} {unit_label}"

    def __repr__(self):
        return (f"AxisDescriptor(index={self.index}, length={self.length}, "
                f"coordinate={self.coordinate!r}, units={self.units!r}, "
                f"scale={self.scale!r}, offset={self.offset!r})")


class OndeDatasetModel(object):
    """One ONDE dataset entry point, presented as an N-dimensional array."""

    def __init__(self, document, full_key, short_key, dataset):
        self.document = document
        self.full_key = full_key
        self.short_key = short_key
        self.dataset = dataset
        #: Structural complaints found while interpreting this dataset.
        self.warnings = []
        self._array = None
        self._array_read = False
        self._axes = None
        self._amplitude = None

    # -- identity ---------------------------------------------------------

    @property
    def label(self):
        text = self.dataset._field_value("LABEL", None)
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        return str(text) if text else f"(unlabeled {self.short_key})"

    @property
    def type_chain(self):
        """ONDE:TYPE as a tuple of strings, base class first.

        Not _onde_class_name, which is the *base* of the chain: the viewer
        dispatches on the most derived class, and on membership of the chain
        rather than equality with its end, so that a future
        ONDE_DATASET_UT_ASCAN_SOMETHING still reads as an A-scan.
        """
        raw = self.dataset._field_value("ONDE:TYPE", None)
        if raw is None:
            return ()
        return tuple(str(entry) for entry in np.atleast_1d(raw).ravel())

    @property
    def leaf_type(self):
        chain = self.type_chain
        return chain[-1] if chain else "ONDE_DATASET"

    def is_a(self, class_name):
        return class_name in self.type_chain

    # -- data -------------------------------------------------------------

    @property
    def raw(self):
        """The stored array, or None when the dataset carries no DATA.

        DATA is optional on A-scan datasets (T/C-scan recorded, raw A-scans not),
        and may be stored either inline or as an HDF5 reference; PyONDE resolves
        the reference at load time, so both arrive here as a plain array.  The
        array is frozen read-only by PyONDE -- copy before modifying.
        """
        if not self._array_read:
            self._array_read = True
            value = self.dataset._field_value("DATA", None)
            if value is None:
                self._array = None
            else:
                array = np.asarray(value)
                if array.ndim == 0:
                    self.warnings.append("DATA is a scalar; treating it as a "
                                         "single-sample 1-D array")
                    array = array.reshape(1)
                self._array = array
        return self._array

    @property
    def has_data(self):
        return self.raw is not None

    @property
    def shape(self):
        return None if self.raw is None else self.raw.shape

    @property
    def ndim(self):
        return 0 if self.raw is None else self.raw.ndim

    @property
    def dtype(self):
        return None if self.raw is None else self.raw.dtype

    @property
    def size_bytes(self):
        return 0 if self.raw is None else int(self.raw.nbytes)

    # -- axes -------------------------------------------------------------

    @property
    def axes(self):
        """One :class:`AxisDescriptor` per data axis.

        INDEX_DIMENSIONS is padded with spec defaults when short and ignored
        past the data rank when long; either mismatch is recorded in
        :attr:`warnings` rather than raised, because files in the wild have it
        (the PyONDE demo writes 1-D DATA with four index dimensions).
        """
        if self._axes is None:
            self._axes = self._build_axes()
        return self._axes

    def _build_axes(self):
        array = self.raw
        if array is None:
            return []
        dimensions = self.dataset._field_value("INDEX_DIMENSIONS", None)
        dimensions = [] if dimensions is None else list(dimensions)
        if dimensions and len(dimensions) != array.ndim:
            self.warnings.append(
                f"INDEX_DIMENSIONS lists {len(dimensions)} dimension(s) but DATA "
                f"has rank {array.ndim}; using spec defaults where they disagree")
        axes = []
        for position, length in enumerate(array.shape):
            dimension = dimensions[position] if position < len(dimensions) else None
            axes.append(AxisDescriptor.from_dimension(position, length, dimension))
        return axes

    @property
    def amplitude(self):
        """Descriptor for the stored values (AMPLITUDE_DIMENSION or defaults)."""
        if self._amplitude is None:
            dimension = self.dataset._field_value("AMPLITUDE_DIMENSION", None)
            length = 0 if self.raw is None else int(self.raw.size)
            self._amplitude = AxisDescriptor.from_dimension(
                -1, length, dimension,
                default_coordinate=DEFAULT_AMPLITUDE_COORDINATE,
                default_units=DEFAULT_AMPLITUDE_UNITS)
        return self._amplitude

    @property
    def is_calibrated(self):
        """True when the amplitude calibration is not the identity."""
        return self.amplitude.scale != 1.0 or self.amplitude.offset != 0.0

    # -- the one bulk-read path -------------------------------------------

    def slice(self, selector, calibrate=True):
        """Extract a sub-array, with amplitude calibration applied.

        *selector* is anything numpy accepts as an index tuple -- ints to fix an
        axis, slices to keep one.  Calibration (``value*SCALE + OFFSET``) is
        applied to the extracted slice, never to the whole array, so browsing a
        multi-gigabyte dataset does not cost a second copy of it.

        When the calibration is the identity, the returned array may be a
        read-only view of PyONDE's frozen storage.  Copy it before modifying.
        """
        array = self.raw
        if array is None:
            raise ValueError(f"dataset {self.short_key} has no DATA to slice")
        extracted = array[selector]
        if not calibrate or not self.is_calibrated:
            return np.asarray(extracted)
        return np.asarray(extracted, dtype=float) * self.amplitude.scale + \
            self.amplitude.offset

    # -- metadata ---------------------------------------------------------

    def metadata_tree(self, max_depth=8):
        """Nested dict of the dataset's subgraph, for the inspector and --info.

        Shared objects are visited once (the graph is a DAG with sharing, so
        SETUP reached twice must not be walked twice) and arrays are summarized
        rather than dumped.
        """
        return _walk(self.dataset, max_depth, set())

    def summary(self):
        """One-line human summary, used by ``ondeview --list``."""
        if self.raw is None:
            shape_text = "no DATA"
        else:
            shape_text = "x".join(str(n) for n in self.raw.shape)
            shape_text += f" {self.dtype}"
        return f"{self.short_key:>8}  {self.leaf_type:<24} {shape_text:<28} {self.label}"


def _summarize_array(array):
    array = np.asarray(array)
    summary = {"shape": array.shape, "dtype": str(array.dtype)}
    if array.size and np.issubdtype(array.dtype, np.number):
        finite = array[np.isfinite(array)] if np.issubdtype(array.dtype, np.floating) \
            else array
        if finite.size:
            summary["min"] = float(np.min(finite))
            summary["max"] = float(np.max(finite))
    if array.size <= 8:
        summary["values"] = array.ravel().tolist()
    return summary


def _walk(obj, depth, seen):
    """Recursive metadata walk with cycle/sharing detection and a depth cap."""
    if obj is None:
        return None
    if depth <= 0:
        return "<max depth reached>"

    # The one place the viewer looks past the handle it was given: sharing is
    # a property of the object, not of the path taken to it, so two fields
    # pointing at one object have to compare equal here.
    raw = obj._get_obj()
    identity = id(raw)
    if identity in seen:
        return "<already shown above>"

    # Which of PyONDE's three reading modes applies is decided by the class
    # underneath: items for a reference array, data for a value or an array,
    # attributes for an object.
    if isinstance(raw, ONDEReferenceArray):
        seen = seen | {identity}
        return [_walk(entry, depth - 1, seen) for entry in obj]

    if isinstance(raw, (ONDEValue, ONDEArray)):
        value = obj.value
        if isinstance(value, np.ndarray):
            return _summarize_array(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    # Sorted, so the metadata window reads the same way every time rather
    # than in whatever order the fields were written.
    names = sorted(obj._list_attrs())
    if not names:
        return repr(obj)

    seen = seen | {identity}
    tree = {}
    for name in names:
        # The field itself is wanted here rather than its value, so that the
        # walk can recurse into it.  _get_attr rather than bracket access:
        # bracket access never consults the class definitions, so it takes
        # only fully qualified names and answers KeyError for everything
        # missing, losing the distinction between a field that is absent and
        # a name that was never a field of this class.
        child = obj._get_attr(name)
        if child is None:
            continue
        tree[name] = _walk(child, depth - 1, seen)
    return tree


class OndeDocument(object):
    """An open ONDE file and the datasets it contains."""

    def __init__(self, onde_file, path, onde_version, load_warnings=()):
        self.onde_file = onde_file
        self.path = str(path)
        self.onde_version = onde_version
        #: Complaints PyONDE made while reading the file, as text.
        self.load_warnings = list(load_warnings)
        self.datasets = []
        self._by_short_key = {}
        self._load_datasets()

    @classmethod
    def open(cls, path, onde_version=None):
        """Open *path* read-only.

        *onde_version* defaults to
        :data:`PyONDE.viewer.access.DEFAULT_ONDE_VERSION`.

        PyONDE reads the whole file into memory at open time, so this call costs
        roughly the file size in RAM; see the viewer's size warning in
        PyONDE.bin.ondeview.
        """
        if onde_version is None:
            onde_version = access.DEFAULT_ONDE_VERSION
        # PyONDE reports a file whose ONDE:TYPE disagrees with the class
        # definitions as a warning while it reads.  Collected here rather
        # than left to stderr, so it reaches the viewer's own warning
        # surfaces -- "ondeview --list" prints it, the metadata window shows
        # it -- alongside the structural complaints the model raises itself.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            onde_file = access.open_onde_file(path, onde_version=onde_version)
            pass
        load_warnings = [str(entry.message) for entry in caught]
        for entry in caught:
            if not issubclass(entry.category, _COLLECTED_WARNINGS):
                # Not ours to swallow: let it reach whoever was listening.
                warnings.warn_explicit(entry.message, entry.category,
                                       entry.filename, entry.lineno)
                pass
            pass
        return cls(onde_file, path, onde_version, load_warnings)

    def _load_datasets(self):
        # items() and shortkeys() are both derived from the graph's one
        # ordered item list, so they correspond element by element.
        graph = self.onde_file.graph
        for (full_key, dataset), short_key in zip(graph.items(), graph.shortkeys()):
            model = OndeDatasetModel(self, full_key, short_key, dataset)
            self.datasets.append(model)
            self._by_short_key[short_key] = model

    # -- file-level metadata ----------------------------------------------

    @property
    def file_version(self):
        """The ONDE:VERSION recorded in the file (may differ from onde_version)."""
        return getattr(self.onde_file, "version", None)

    @property
    def filetype(self):
        raw = getattr(self.onde_file, "filetype", None)
        if raw is None:
            return ()
        return tuple(sorted(str(entry) for entry in raw))

    # -- access -----------------------------------------------------------

    def __len__(self):
        return len(self.datasets)

    def __iter__(self):
        return iter(self.datasets)

    def __getitem__(self, key):
        """Index by short key, full UUID, or position."""
        if isinstance(key, int):
            return self.datasets[key]
        if key in self._by_short_key:
            return self._by_short_key[key]
        for model in self.datasets:
            if model.full_key == key:
                return model
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    @property
    def viewable(self):
        """Datasets that actually carry an array to display."""
        return [model for model in self.datasets if model.has_data]

    @property
    def warnings(self):
        """Every complaint about this file: PyONDE's at load, then each dataset's."""
        collected = list(self.load_warnings)
        for model in self.datasets:
            model.axes            # force interpretation so warnings are populated
            for message in model.warnings:
                collected.append(f"{model.short_key}: {message}")
        return collected

    def close(self):
        try:
            self.onde_file.close()
        except Exception as err:      # pragma: no cover - defensive
            warnings.warn(f"closing {self.path}: {err}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def __repr__(self):
        return f"OndeDocument({self.path!r}, {len(self.datasets)} dataset(s))"
