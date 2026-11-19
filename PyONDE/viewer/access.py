"""Opening an ONDE file: which class definitions to read it with.

This module used to hold a layer of defensive accessors that stood between the
model layer and PyONDE -- unwrapping values, trying two spellings of every
field name, reaching a reference array's length out of a private attribute,
pairing keys with short keys.  None of that is here any more, because none of
it is needed: PyONDE answers those questions itself, through ``_field_value``,
``_list_attrs``, ``len()`` and ``graph.items()``, so the model layer calls the
library directly and reads as an example of using it.

What is left is a decision rather than a workaround.  Which class definitions
are in force determines how field names resolve, so the viewer fixes that
version deliberately instead of inheriting whatever a given PyONDE release
happens to ship, and says something useful when the requested definitions are
not installed.

Nothing here imports matplotlib: this module must stay usable on a plain
``pip install PyONDE`` with no plotting library present.
"""

import os
import re

__all__ = ["open_onde_file", "available_onde_versions", "DEFAULT_ONDE_VERSION"]

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


def open_onde_file(path, onde_version=None, mode="r", filetype=None):
    """Open an ONDE file for reading.

    *onde_version* selects which class definitions PyONDE compiles in, not what
    the file is required to contain: a file written under a different version
    still loads, and a field belonging to a class those definitions do not know
    is still reachable by its fully qualified ``CLASS:FIELD`` name.  None means
    :data:`DEFAULT_ONDE_VERSION`.

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
