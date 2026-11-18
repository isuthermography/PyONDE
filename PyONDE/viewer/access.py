"""Defensive accessors for the PyONDE object graph.

The viewer reads ONDE files written by other tools, at spec versions that may not
match the class definitions compiled into PyONDE.  Every sharp edge in the PyONDE
read API is absorbed here, in one place, so the model layer can be written as if
the graph were a plain nested mapping.

Behaviors this module papers over (each has a test in tests/test_viewer_access.py):

  * Field values come back as wrappers, not values: ``ds.DATA.value`` is the numpy
    array.  :func:`field_value` unwraps ONDEValue/ONDEArray transparently.
  * A field that is known to the class definitions but unset reads back as None in
    some code paths and raises in others.  :func:`field` returns a default either way.
  * A field belonging to a class PyONDE does not know about is unreachable by
    attribute access and needs bracket access with the full ``CLASS:FIELD`` name.
    :func:`field` tries both spellings.
  * ``ONDEReferenceArray`` exposes no usable ``.shape`` through the proxy layer;
    its length lives at ``.refs._shape[0]``.  See :func:`ref_len`.
  * ``ONDE:TYPE`` is the full inheritance chain, and arrives as a 1-D or 2-D
    array.  PyONDE decodes HDF5 fixed-length strings, but :func:`type_chain`
    decodes as well, so the viewer does not depend on that.
  * Arrays are frozen read-only (``value.flags.writeable = False``); anything that
    intends to modify data must copy first.

Nothing here imports matplotlib: this module must stay usable on a plain
``pip install PyONDE`` with no viewer extra.
"""

import os
import re
import warnings

import numpy as np

from ..onde import ONDEArray, ONDEObject, ONDEValue

__all__ = ["underlying", "unwrap", "field", "field_value", "has_field",
           "ref_len", "ref_list", "type_chain", "is_a", "leaf_type",
           "field_names", "dataset_entries", "open_onde_file",
           "available_onde_versions", "DEFAULT_ONDE_VERSION"]

#: Class definitions the viewer reads with unless told otherwise.
#:
#: Deliberately a fixed version rather than "whichever is newest installed":
#: which definitions are in force decides how field names resolve, so it should
#: be a decision, not a side effect of the PyONDE release someone happens to
#: have.  Bump it when the viewer has been checked against a newer set; pass
#: --onde-version (or onde_version=) to read with a different one.
DEFAULT_ONDE_VERSION = "0.9.2"

_VERSION_FILE = re.compile(r"^ONDE_fields_v(.+)\.csv$")


def available_onde_versions():
    """Every spec version PyONDE ships class definitions for.

    Used to say something useful when the requested definitions are missing,
    and by the tests that read a file under each version in turn.  It is
    deliberately *not* used to pick the default -- see DEFAULT_ONDE_VERSION.
    """
    from .. import onde_versions_path
    versions = []
    try:
        names = os.listdir(onde_versions_path)
    except OSError:
        return []
    for name in names:
        match = _VERSION_FILE.match(name)
        if match:
            versions.append(match.group(1))
    return sorted(versions)


def underlying(obj):
    """Return the concrete ONDEBase instance behind a wrapper or proxy.

    Wrappers intercept attribute access for names not starting with an
    underscore, so ``_get_obj`` reaches the real object.  Anything that is not a
    wrapper is returned unchanged.
    """
    if obj is None:
        return None
    get_obj = getattr(obj, "_get_obj", None)
    if get_obj is None:
        return obj
    try:
        return get_obj()
    except Exception:
        return obj


def unwrap(obj, default=None):
    """Return the plain Python or numpy value behind *obj*.

    ONDEValue and ONDEArray yield their ``.value``; plain scalars, strings and
    arrays pass through; anything else (an ONDEObject, a reference array) is
    returned as given, since there is no scalar value to extract.
    """
    if obj is None:
        return default
    raw = underlying(obj)
    if isinstance(raw, (ONDEValue, ONDEArray)):
        value = raw.value
        return default if value is None else value
    return obj


def _read_attr(obj, name):
    if ":" in name:
        # Attribute access cannot express a colon; bracket access is the only route.
        raise AttributeError(name)
    return getattr(obj, name)


def _read_item(obj, name):
    return obj[name]


def field(obj, name, default=None):
    """Read field *name* off ONDE object *obj*, or return *default*.

    *name* may be the short form (``"DATA"``) or the fully qualified form
    (``"ONDE_DATASET:DATA"``).  Both spellings are attempted, and every failure
    mode -- absent field, unknown class, exception from the proxy layer -- lands
    on *default*.
    """
    if obj is None:
        return default
    for reader in (_read_attr, _read_item):
        try:
            value = reader(obj, name)
        except Exception:
            continue
        if value is not None:
            return value
    return default


def field_value(obj, name, default=None):
    """:func:`field` followed by :func:`unwrap` -- the common case."""
    found = field(obj, name, None)
    if found is None:
        return default
    return unwrap(found, default)


def has_field(obj, name):
    """True if *obj* carries field *name* with a value."""
    if obj is None:
        return False
    try:
        if name in obj:
            return True
    except Exception:
        pass
    return field(obj, name, None) is not None


def ref_len(refarray):
    """Number of entries in an ONDEReferenceArray, 0 if it cannot be determined.

    ``.shape`` raises and ``._shape()`` is not callable; the length is carried by
    the underlying TwoWayArray's ``_shape`` tuple.
    """
    if refarray is None:
        return 0
    candidates = (
        lambda: refarray.refs._shape[0],
        lambda: underlying(refarray).refs._shape[0],
        lambda: underlying(refarray).refs._shape,
    )
    for candidate in candidates:
        try:
            result = candidate()
        except Exception:
            continue
        if isinstance(result, tuple):
            result = result[0] if result else None
        if result is not None:
            return int(result)
    return 0


def ref_list(refarray):
    """All entries of an ONDEReferenceArray as a list; unreadable slots are None."""
    entries = []
    for index in range(ref_len(refarray)):
        try:
            entries.append(refarray[index])
        except Exception:
            entries.append(None)
    return entries


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def type_chain(obj):
    """The ``ONDE:TYPE`` inheritance chain as a tuple of strings.

    The chain runs base class first, so the leaf type is the last element.  The
    stored value may be 1-D or 2-D and may hold bytes rather than str depending
    on the writer, so it is flattened and decoded here.
    """
    raw = field_value(obj, "ONDE:TYPE", None)
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)):
        return (_as_text(raw),)
    try:
        flat = np.asarray(raw).ravel()
    except Exception:
        return ()
    return tuple(_as_text(entry) for entry in flat)


def is_a(obj, class_name):
    """True if *class_name* appears anywhere in the object's type chain.

    Type dispatch must test membership of the chain rather than equality with the
    leaf, so that a future ``ONDE_DATASET_UT_ASCAN_SOMETHING`` still reads as an
    A-scan.
    """
    return class_name in type_chain(obj)


def leaf_type(obj):
    """The most derived class name in the type chain, or None."""
    chain = type_chain(obj)
    return chain[-1] if chain else None


def field_names(obj):
    """Field names present on *obj*, fully qualified, for the metadata inspector.

    Falls back to the class-definition listing when the concrete object cannot be
    reached, and to an empty list when neither works.
    """
    raw = underlying(obj)
    if isinstance(raw, ONDEObject):
        try:
            return sorted(raw._list_attrs())
        except Exception:
            pass
    try:
        return sorted(name for name in dir(obj) if not name.startswith("_"))
    except Exception:
        return []


def dataset_entries(onde_file):
    """[(full_key, short_key, dataset_wrapper)] for every entry point in the file.

    ``keys()`` and ``shortkeys()`` are both derived from the snapshot's item list
    in the same order, so they are zipped positionally.  A dataset that fails to
    resolve is skipped with a warning rather than taking the whole file down.
    """
    graph = onde_file.graph
    full_keys = list(graph.keys())
    try:
        short_keys = list(graph.shortkeys())
    except Exception:
        short_keys = list(full_keys)
    if len(short_keys) != len(full_keys):
        short_keys = list(full_keys)

    entries = []
    for full_key, short_key in zip(full_keys, short_keys):
        try:
            entries.append((full_key, short_key, graph[full_key]))
        except Exception as err:      # pragma: no cover - defensive
            warnings.warn(f"ONDE dataset {full_key} could not be read: {err}")
    return entries


def open_onde_file(path, onde_version=None, mode="r", filetype=None):
    """Open an ONDE file for reading.

    *onde_version* selects which class definitions PyONDE compiles in, not what
    the file is required to contain: a file written under a different version
    still loads, with unknown fields reachable through :func:`field` by their
    fully qualified names.  None means :data:`DEFAULT_ONDE_VERSION`.

    *filetype* is an optional set of ``ONDE:FILETYPE`` tags to require of the
    file; PyONDE raises if one of them is missing.  It defaults to None -- no
    requirement at all -- on purpose.  The viewer browses whatever datasets a
    file holds, so demanding ``ONDE_UT`` would lock it out of a conforming
    file from some other modality for no gain: a file with no dataset the
    viewer can show is already reported as such, by looking at the datasets
    rather than at a tag.  Callers wanting the check can ask for it.
    """
    from ..onde import ONDEDatasetFile
    if onde_version is None:
        onde_version = DEFAULT_ONDE_VERSION
    available = available_onde_versions()
    if available and onde_version not in available:
        # Otherwise this surfaces as a FileNotFoundError naming a CSV inside
        # PyONDE, which reads as if the data file were missing.
        raise ValueError(
            f"no ONDE class definitions for {onde_version!r} in this PyONDE "
            f"(it ships: {', '.join(available)})")
    extra = {}
    if filetype is not None:
        # Only passed when asked for: PyONDE gained this argument in v0.1.7,
        # and leaving it out keeps the call working on an older install.
        extra["filetype"] = set(filetype)
    return ONDEDatasetFile.new(str(path), mode, onde_version=onde_version,
                               **extra)
