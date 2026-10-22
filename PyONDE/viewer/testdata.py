"""Synthetic ONDE files for developing and testing the viewer.

Four generators, covering the shapes the viewer must handle and the ways real
files disappoint it:

  * :func:`write_ascan_file` -- 4-D ``[N_U, N_V, N_Ascan, N_time]`` A-scans with
    full dimension metadata and position-dependent time of flight, so a C-scan
    extracted from it has actual structure.
  * :func:`write_tscan_file` -- a T-scan reconstruction zone plus the A-scan
    dataset it references, the latter deliberately carrying no DATA (which the
    spec explicitly permits).
  * :func:`write_cscan_file` -- ``[N_U, N_V, N_A]`` scalar data on a grid.
  * :func:`write_legacy_file` -- the same shape as an A-scan file but written
    the way a pre-0.9.2 system would: SENSOR_LIST, FRAME, and a ``2.25.`` UUID.
  * :func:`write_hostile_file` -- written with raw h5py rather than PyONDE, so
    its structure is not shaped by PyONDE's own assumptions.  Every case in it
    is drawn from the specification's optional/alternative wordings.

One limit of PyONDE's loader that these files cannot exercise, because it makes
a file unreadable rather than awkward, and which the viewer can therefore only
report rather than survive: a dataset group with no ``ONDE:UUID`` raises during
load, taking the whole file with it.

Two further cases live in files of their own.  :func:`write_nested_file` (a
sub-group inside a dataset group) cannot be loaded at all while hierarchical
support waits on a specification update, and one such group would otherwise
take a whole corpus down with it.  :func:`write_bytestype_file` (``ONDE:TYPE``
stored as fixed-length bytes) is kept separate for the same reason -- PyONDE
reads it now, but its treatment has changed twice, and the failure mode when it
does not is the loss of every dataset in the file.
"""

import os
import uuid
from datetime import datetime

import h5py
import numpy as np

from .. import generate_onde_uuid
from ..onde import (ONDEArray,
                    ONDEDatasetFile,
                    ONDEObject,
                    ONDEReferenceArray)

__all__ = ["write_ascan_file", "write_tscan_file", "write_cscan_file",
           "write_hostile_file", "write_nested_file", "write_bytestype_file",
           "write_legacy_file", "write_all"]

#: The definitions the corpus is written with: what current PyONDE writes.
ONDE_VERSION = "0.9.2"

#: One file is written with these instead, to keep a pre-0.9.2 acquisition in
#: the corpus -- SENSOR_LIST rather than PROBE_LIST, and a DICOM-style UUID.
LEGACY_ONDE_VERSION = "0.9.1pre"

#: The UUID form every file written before ONDE v0.9.2 carries.  v0.9.2 moved
#: to "urn:uuid:" + a hyphenated hexadecimal 128-bit value; readers are told to
#: treat the string as opaque, which is what the viewer does.
LEGACY_UUID_PREFIX = "2.25."


def _stamp():
    """One timestamp per file: the UUID hashes it and DATE_AND_TIME records it.

    PyONDE 154afec made generate_onde_uuid hash the ISO 8601 rendering, so the
    two now have to come from the same aware datetime to stay consistent.
    """
    return datetime.now().astimezone()


def _uuid(stamp, suffix):
    return generate_onde_uuid("PyONDE-viewer-test", str(uuid.getnode()),
                              stamp, suffix)


def _timestamp(stamp):
    """ISO 8601 with microseconds and an offset, as the specification asks."""
    return stamp.isoformat(timespec="microseconds")


def _dimension(onde_file, coordinate, units, scale=1.0, offset=0.0):
    dimension = ONDEObject.new(onde_file, "ONDE_DIMENSION")
    dimension.COORDINATE = coordinate
    dimension.UNITS = units
    dimension.SCALE = scale
    dimension.OFFSET = offset
    return dimension


def _index_dimensions(onde_file, specs):
    """specs: sequence of (coordinate, units, scale, offset)."""
    references = ONDEReferenceArray.new(onde_file, shape=(len(specs),))
    for position, (coordinate, units, scale, offset) in enumerate(specs):
        references[position] = _dimension(onde_file, coordinate, units, scale, offset)
    return references


def _minimal_setup(onde_file, sample_rate=None, legacy=False):
    """A structurally valid ONDE_SETUP_UT with one probe and one trajectory.

    *legacy* writes the pre-0.9.2 spelling: SENSOR_LIST rather than PROBE_LIST,
    and FRAME rather than INDEX_POINT_FRAME.
    """
    setup = ONDEObject.new(onde_file, "ONDE_SETUP_UT")
    setup.GEOMETRIC_SETUP = ONDEObject.new(onde_file, "ONDE_GEOMETRIC_SETUP")

    setup.GEOMETRIC_SETUP.COMPONENT = ONDEObject.new(onde_file, "ONDE_COMPONENT")
    setup.GEOMETRIC_SETUP.COMPONENT.VELOCITIES = ONDEArray.new(
        value=np.array([5900.0, 3200.0]))

    probe = ONDEObject.new(onde_file, "ONDE_UT_PROBE")
    probe.FREQUENCY = 5e6
    frame = ONDEArray.new(value=np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
    probes = ONDEReferenceArray.new(onde_file, shape=(1,))
    if legacy:
        probe.FRAME = frame
        probes[0] = probe
        setup.GEOMETRIC_SETUP.SENSOR_LIST = probes
    else:
        probe.INDEX_POINT_FRAME = frame
        probes[0] = probe
        setup.GEOMETRIC_SETUP.PROBE_LIST = probes

    setup.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY = ONDEReferenceArray.new(
        onde_file, shape=(1,))
    trajectory = ONDEObject.new(onde_file, "ONDE_SPATIAL_TRAJECTORY")
    trajectory.TRAJECTORY = ONDEArray.new(
        value=np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
    setup.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0] = trajectory

    if sample_rate is not None:
        setup.ULTRASONIC_SETUP = ONDEObject.new(onde_file, "ONDE_ULTRASONIC_SETUP")
        setup.ULTRASONIC_SETUP.ASCAN_SAMPLE_RATE = sample_rate
        setup.ULTRASONIC_SETUP.GAIN = ONDEArray.new(value=np.array((10 ** (40 / 20),)))
    return setup


def _synthetic_ascans(n_u, n_v, n_ascan, n_time, dt, t0):
    """Tone bursts whose arrival time varies with position, plus a flat-bottom hole.

    Gives every derived view something to show: the B-scan curves, a gated
    C-scan has a blob in it, and the A-scan amplitude varies across the scan.
    """
    time = t0 + np.arange(n_time) * dt
    data = np.zeros((n_u, n_v, n_ascan, n_time), dtype=np.float64)
    center_u, center_v = (n_u - 1) / 2.0, (n_v - 1) / 2.0
    for iu in range(n_u):
        for iv in range(n_v):
            radius = np.hypot((iu - center_u) / max(center_u, 1),
                              (iv - center_v) / max(center_v, 1))
            depth_shift = 1.5e-6 * radius ** 2
            amplitude = 1.0 if radius < 0.6 else 0.35
            for ia in range(n_ascan):
                arrival = t0 + 4e-6 + depth_shift + ia * 0.4e-6
                envelope = np.exp(-((time - arrival) / 0.35e-6) ** 2)
                data[iu, iv, ia, :] = amplitude * envelope * \
                    np.cos(2 * np.pi * 5e6 * (time - arrival))
            # front-wall echo, same for every position
            front = np.exp(-((time - (t0 + 0.5e-6)) / 0.25e-6) ** 2)
            data[iu, iv, :, :] += 0.8 * front * np.cos(2 * np.pi * 5e6 *
                                                       (time - (t0 + 0.5e-6)))
    return data


def write_ascan_file(path, shape=(3, 4, 2, 1000)):
    """A 4-D A-scan dataset with complete dimension metadata."""
    n_u, n_v, n_ascan, n_time = shape
    dt, t0 = 1e-8, 1e-5
    du, dv = 1e-3, 2e-3

    onde_file = ONDEDatasetFile.new(str(path), "w", onde_version=ONDE_VERSION)
    stamp = _stamp()
    dataset = ONDEObject.new(onde_file, "ONDE_DATASET_UT_ASCAN")
    dataset.UUID = _uuid(stamp, "ascan")
    dataset.LABEL = "Synthetic A-scan raster"
    dataset.OPERATOR = "PyONDE viewer test data"
    dataset.DATE_AND_TIME = _timestamp(stamp)
    dataset.DATA = ONDEArray.new(
        value=_synthetic_ascans(n_u, n_v, n_ascan, n_time, dt, t0))
    dataset.INDEX_DIMENSIONS = _index_dimensions(onde_file, [
        ("U Position", "meters", du, 0.0),
        ("V Position", "meters", dv, 0.0),
        ("Ascan", "unitless", 1.0, 0.0),
        ("Time", "seconds", dt, t0)])
    dataset.AMPLITUDE_DIMENSION = _dimension(onde_file, "Voltage", "Volts", 0.01, 0.0)
    dataset.SETUP = _minimal_setup(onde_file, sample_rate=1.0 / dt)

    onde_file.graph.add(dataset)
    onde_file.flush()
    onde_file.close()
    return str(path)


def write_tscan_file(path, shape=(2, 1, 64, 80)):
    """A T-scan zone plus the (data-free) A-scan dataset it was reconstructed from."""
    n_u, n_v, n_row, n_col = shape
    onde_file = ONDEDatasetFile.new(str(path), "w", onde_version=ONDE_VERSION)
    stamp = _stamp()

    # The spec permits an A-scan dataset with no DATA when only the
    # reconstruction was kept.  SOURCE_ASCAN_DATASET is mandatory, so the
    # T-scan needs it to exist regardless.
    source = ONDEObject.new(onde_file, "ONDE_DATASET_UT_ASCAN")
    source.UUID = _uuid(stamp, "tscan-source")
    source.LABEL = "Elementary channels (not recorded)"
    source.DATE_AND_TIME = _timestamp(stamp)
    source.SETUP = _minimal_setup(onde_file, sample_rate=1e8)

    row = np.linspace(-1.0, 1.0, n_row)[:, None]
    col = np.linspace(-1.0, 1.0, n_col)[None, :]
    image = np.exp(-((row - 0.2) ** 2 + (col + 0.3) ** 2) / 0.05) + \
        0.4 * np.exp(-((row + 0.5) ** 2 + (col - 0.4) ** 2) / 0.02)
    data = np.zeros((n_u, n_v, n_row, n_col))
    for iu in range(n_u):
        data[iu, :, :, :] = image * (1.0 - 0.3 * iu)

    dataset = ONDEObject.new(onde_file, "ONDE_DATASET_UT_TSCAN")
    dataset.UUID = _uuid(stamp, "tscan")
    dataset.LABEL = "Synthetic TFM zone"
    dataset.DATE_AND_TIME = _timestamp(stamp)
    dataset.DATA = ONDEArray.new(value=data)
    dataset.INDEX_DIMENSIONS = _index_dimensions(onde_file, [
        ("U Position", "meters", 5e-3, 0.0),
        ("V Position", "meters", 5e-3, 0.0),
        ("Depth", "meters", 0.25e-3, 0.0),
        ("X Position", "meters", 0.25e-3, -10e-3)])
    dataset.AMPLITUDE_DIMENSION = _dimension(onde_file, "Amplitude", "arbitrary")
    dataset.SETUP = _minimal_setup(onde_file, sample_rate=1e8)
    # v0.9.2 moved ZONE_* and RECONSTRUCTION_MODE out of the T-scan dataset
    # into their own ONDE_UT_RECONSTRUCTION_SETUP, referenced from it.
    reconstruction = ONDEObject.new(onde_file, "ONDE_UT_RECONSTRUCTION_SETUP")
    reconstruction.ZONE_FRAME = ONDEArray.new(
        value=np.array((0.0, 0.0, 8e-3, 1.0, 0.0, 0.0, 0.0)))
    reconstruction.ZONE_DIMENSION = ONDEArray.new(
        value=np.array((20e-3, 16e-3, 0.0)))
    reconstruction.ZONE_SIZE = ONDEArray.new(value=np.array((n_col, n_row, 1)))
    reconstruction.RECONSTRUCTION_MODE = "TFM"
    # A scalar integer field.  HDF5 gives it back as numpy int64, which PyONDE
    # did not recognize until a6be485; the corpus carries one so the suite
    # notices if that regresses.
    reconstruction.REFERENCE_PROBE_INDEX = 0
    dataset.RECONSTRUCTION_SETUP = reconstruction
    dataset.SOURCE_ASCAN_DATASET = source

    onde_file.graph.add(source)
    onde_file.graph.add(dataset)
    onde_file.flush()
    onde_file.close()
    return str(path)


def write_cscan_file(path, shape=(5, 6, 1)):
    """A C-scan of scalar values on an acquisition grid."""
    n_u, n_v, n_a = shape
    onde_file = ONDEDatasetFile.new(str(path), "w", onde_version=ONDE_VERSION)
    stamp = _stamp()

    u_positions = np.arange(n_u) * 2e-3
    v_positions = np.arange(n_v) * 2e-3
    thickness = 12e-3 - 2e-3 * np.exp(
        -((u_positions[:, None] - 4e-3) ** 2 +
          (v_positions[None, :] - 6e-3) ** 2) / (8e-6))
    data = thickness[:, :, None] * np.ones((1, 1, n_a))

    grid = ONDEObject.new(onde_file, "ONDE_ACQUISITION_GRID")
    grid.TRAJECTORY = ONDEArray.new(
        value=np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
    grid.U_GRID_DATA = ONDEArray.new(value=u_positions)
    grid.V_GRID_DATA = ONDEArray.new(value=v_positions)

    dataset = ONDEObject.new(onde_file, "ONDE_DATASET_UT_CSCAN")
    dataset.UUID = _uuid(stamp, "cscan")
    dataset.LABEL = "Synthetic thickness C-scan"
    dataset.DATE_AND_TIME = _timestamp(stamp)
    dataset.DATA = ONDEArray.new(value=data)
    dataset.INDEX_DIMENSIONS = _index_dimensions(onde_file, [
        ("U Position", "meters", 2e-3, 0.0),
        ("V Position", "meters", 2e-3, 0.0),
        ("Ascan", "unitless", 1.0, 0.0)])
    dataset.AMPLITUDE_DIMENSION = _dimension(onde_file, "Thickness", "meters")
    dataset.SETUP = _minimal_setup(onde_file)
    dataset.CSCAN_GRID = grid

    onde_file.graph.add(dataset)
    onde_file.flush()
    onde_file.close()
    return str(path)


# -- the hostile file, written with raw h5py ------------------------------

_ASCAN_TYPE = ["ONDE_DATASET", "ONDE_DATASET_UT", "ONDE_DATASET_UT_ASCAN"]
_CSCAN_TYPE = ["ONDE_DATASET", "ONDE_DATASET_UT", "ONDE_DATASET_UT_CSCAN"]


def _h5_dimension(parent, name, coordinate=None, units=None,
                  scale=None, offset=None):
    group = parent.create_group(name)
    group.attrs["ONDE:TYPE"] = ["ONDE_DIMENSION"]
    if coordinate is not None:
        group.attrs["ONDE_DIMENSION:COORDINATE"] = coordinate
    if units is not None:
        group.attrs["ONDE_DIMENSION:UNITS"] = units
    if scale is not None:
        group.attrs["ONDE_DIMENSION:SCALE"] = float(scale)
    if offset is not None:
        group.attrs["ONDE_DIMENSION:OFFSET"] = float(offset)
    return group


def write_hostile_file(path):
    """Every legal-but-awkward structure the viewer has to tolerate, in one file.

    Datasets written, by short label:

      ``bare``      no INDEX_DIMENSIONS, no AMPLITUDE_DIMENSION, no SETUP;
                    integer DATA stored as a child HDF5 dataset.
      ``mismatch``  2-D DATA with four INDEX_DIMENSIONS listed.
      ``byref``     DATA as an HDF5 object reference into an unrelated part of
                    the tree, with only a partial dimension list (SCALE given,
                    UNITS omitted).
      ``nodata``    an A-scan entry point with no DATA at all.
      ``degenerate`` DATA whose non-time axes are all length 1.
    """
    with h5py.File(str(path), "w") as handle:
        handle.attrs["ONDE:VERSION"] = "0.9.2"
        handle.attrs["ONDE:FILETYPE"] = ["ONDE_UT"]

        storage = handle.create_group("storage")
        scratch = handle.create_group("acquisition")
        # ONDE_DIMENSION groups live outside the dataset groups: PyONDE's loader
        # rejects a sub-group inside a dataset group unless its hierarchical
        # support is enabled (it is off by default).  See write_nested_file.
        dims = handle.create_group("dimension_defs")

        # -- bare: integer data, no dimension metadata whatsoever ----------
        bare = handle.create_group("bare_ascan")
        bare.attrs["ONDE:TYPE"] = _ASCAN_TYPE
        bare.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999991"
        bare.attrs["ONDE:LABEL"] = "Integer A-scans, no dimensions"
        counts = (np.arange(2 * 1 * 1 * 64).reshape(2, 1, 1, 64) % 256) - 128
        bare.create_dataset("ONDE_DATASET:DATA", data=counts.astype(np.int16))

        # -- mismatch: rank 2 data, four dimensions listed -----------------
        mismatch = handle.create_group("mismatched_dims")
        mismatch.attrs["ONDE:TYPE"] = _CSCAN_TYPE
        mismatch.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999992"
        mismatch.attrs["ONDE:LABEL"] = "Rank/dimension mismatch"
        mismatch.create_dataset("ONDE_DATASET:DATA",
                                data=np.linspace(0, 1, 5 * 7).reshape(5, 7))
        references = [
            _h5_dimension(dims, "u", "U Position", "meters", 1e-3, 0.0).ref,
            _h5_dimension(dims, "v", "V Position", "meters", 1e-3, 0.0).ref,
            _h5_dimension(dims, "a", "Ascan", "unitless", 1.0, 0.0).ref,
            _h5_dimension(dims, "t", "Time", "seconds", 1e-8, 0.0).ref,
        ]
        mismatch.attrs["ONDE_DATASET:INDEX_DIMENSIONS"] = np.array(
            references, dtype=h5py.ref_dtype)

        # -- byref: DATA is a reference elsewhere; partial dimension info ---
        blob = storage.create_dataset(
            "blob", data=np.sin(np.linspace(0, 20, 3 * 128)).reshape(3, 128))
        byref = scratch.create_group("referenced_data")
        byref.attrs["ONDE:TYPE"] = _ASCAN_TYPE
        byref.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999993"
        byref.attrs["ONDE:LABEL"] = "DATA by HDF5 reference"
        byref.attrs["ONDE_DATASET:DATA"] = blob.ref
        byref.attrs["ONDE_DATASET:INDEX_DIMENSIONS"] = np.array([
            _h5_dimension(dims, "byref_pos", "U Position", None, 2.5e-3, None).ref,
            _h5_dimension(dims, "byref_t", None, None, 2e-8, 1e-6).ref,
        ], dtype=h5py.ref_dtype)

        # -- nodata: entry point with no DATA ------------------------------
        nodata = handle.create_group("no_data_ascan")
        nodata.attrs["ONDE:TYPE"] = _ASCAN_TYPE
        nodata.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999994"
        nodata.attrs["ONDE:LABEL"] = "Elementary channels not recorded"

        # -- degenerate: everything length 1 except time -------------------
        degenerate = handle.create_group("degenerate")
        degenerate.attrs["ONDE:TYPE"] = _ASCAN_TYPE
        degenerate.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999995"
        degenerate.attrs["ONDE:LABEL"] = "Single A-scan in a 4-D wrapper"
        degenerate.create_dataset(
            "ONDE_DATASET:DATA",
            data=np.cos(np.linspace(0, 40, 256)).reshape(1, 1, 1, 256))
        degenerate.attrs["ONDE_DATASET:INDEX_DIMENSIONS"] = np.array([
            _h5_dimension(dims, "deg_u", "U Position", "meters", 1e-3, 0.0).ref,
            _h5_dimension(dims, "deg_v", "V Position", "meters", 1e-3, 0.0).ref,
            _h5_dimension(dims, "deg_a", "None", "unitless", 1.0, 0.0).ref,
            _h5_dimension(dims, "deg_t", "Time", "seconds", 4e-9, 3e-6).ref,
        ], dtype=h5py.ref_dtype)
    return str(path)


def write_bytestype_file(path):
    """A dataset whose ONDE:TYPE is fixed-length bytes rather than str.

    h5py stores a numpy "S" array as fixed-length ASCII, which reads back as
    bytes; a writer in C or FORTRAN naturally produces exactly that.  The
    specification says H5T_STRING and does not require a particular width.

    PyONDE decodes these to str at load as of 39214f6, so the dataset reads
    like any other.  It lives in a file of its own because the behavior has
    changed twice and the failure mode is not contained: before 50e8c49 the
    group was invisible, and between 50e8c49 and 39214f6 it was discovered and
    then rejected, which aborted the load of every dataset in the file.
    """
    with h5py.File(str(path), "w") as handle:
        handle.attrs["ONDE:VERSION"] = "0.9.2"
        handle.attrs["ONDE:FILETYPE"] = ["ONDE_UT"]
        dataset = handle.create_group("bytes_typed")
        dataset.attrs["ONDE:TYPE"] = np.array(
            [entry.encode("ascii") for entry in _ASCAN_TYPE], dtype="S32")
        dataset.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999997"
        dataset.attrs["ONDE:LABEL"] = "Bytes-typed ONDE:TYPE"
        dataset.create_dataset(
            "ONDE_DATASET:DATA",
            data=np.sin(np.linspace(0, 12, 32)).reshape(1, 32))
    return str(path)


def write_nested_file(path):
    """A dataset group containing a sub-group -- which PyONDE cannot currently load.

    The specification says group locations and names are flexible, so a vendor
    may nest an ONDE_DIMENSION group inside the dataset group that references
    it.  PyONDE's loader raises ``ValueError: Unknown h5type Group`` on such a
    file, because hierarchical support is behind the module-level
    ``PyONDE.onde.enable_hierarchical`` flag, which is False.

    The viewer cannot fix that; it exists here so the limitation is pinned by a
    test and so ``ondeview`` is known to report it as a readable error rather
    than a traceback.  If hierarchical loading is enabled upstream, the test
    guarding this will start failing and can be turned into a positive one.
    """
    with h5py.File(str(path), "w") as handle:
        handle.attrs["ONDE:VERSION"] = "0.9.2"
        handle.attrs["ONDE:FILETYPE"] = ["ONDE_UT"]
        dataset = handle.create_group("nested_ascan")
        dataset.attrs["ONDE:TYPE"] = _ASCAN_TYPE
        dataset.attrs["ONDE:UUID"] = "urn:uuid:99999999-9999-9999-9999-999999999996"
        dataset.attrs["ONDE:LABEL"] = "Dimensions nested inside the dataset group"
        dataset.create_dataset("ONDE_DATASET:DATA",
                               data=np.zeros((1, 1, 1, 16)))
        nested = dataset.create_group("dimensions")
        dimension = _h5_dimension(nested, "t", "Time", "seconds", 1e-8, 0.0)
        dataset.attrs["ONDE_DATASET:INDEX_DIMENSIONS"] = np.array(
            [dimension.ref], dtype=h5py.ref_dtype)
    return str(path)


def write_legacy_file(path):
    """A file as a pre-0.9.2 acquisition system would have written it.

    Two things changed with v0.9.2 that a reader has to take in its stride,
    and this file still has the old form of both:

      * ``SENSOR_LIST`` (now ``PROBE_LIST``) and ``FRAME`` (now
        ``INDEX_POINT_FRAME``), so the current class definitions do not know
        these field names and they are reachable only by their fully
        qualified spelling;
      * a DICOM-style ``2.25.<decimal>`` UUID rather than ``urn:uuid:<hex>``.
        The specification tells readers to treat the string as opaque; PyONDE
        shortens only the ``urn:uuid:`` form, so this key comes back at full
        length and the viewer addresses the dataset by it unchanged.
    """
    n_time = 500
    dt, t0 = 2e-8, 5e-6
    onde_file = ONDEDatasetFile.new(str(path), "w",
                                    onde_version=LEGACY_ONDE_VERSION)
    stamp = _stamp()
    dataset = ONDEObject.new(onde_file, "ONDE_DATASET_UT_ASCAN")
    # The 2.25. form: "2.25." followed by the decimal 128-bit value.
    dataset.UUID = LEGACY_UUID_PREFIX + "124217692408202938307279138509891347358"
    dataset.LABEL = "Legacy 0.9.1pre acquisition"
    dataset.DATE_AND_TIME = _timestamp(stamp)
    dataset.DATA = ONDEArray.new(
        value=np.cos(2 * np.pi * 2e6 * (t0 + np.arange(n_time) * dt)
                     ).reshape(1, 1, 1, n_time))
    dataset.INDEX_DIMENSIONS = _index_dimensions(onde_file, [
        ("U Position", "meters", 1e-3, 0.0),
        ("V Position", "meters", 1e-3, 0.0),
        ("Ascan", "unitless", 1.0, 0.0),
        ("Time", "seconds", dt, t0)])
    dataset.AMPLITUDE_DIMENSION = _dimension(onde_file, "Voltage", "Volts")
    dataset.SETUP = _minimal_setup(onde_file, sample_rate=1.0 / dt, legacy=True)

    onde_file.graph.add(dataset)
    onde_file.flush()
    onde_file.close()
    return str(path)


def write_all(directory):
    """Write all four files into *directory*; returns {name: path}."""
    directory = str(directory)
    os.makedirs(directory, exist_ok=True)
    return {
        "ascan": write_ascan_file(os.path.join(directory, "ascan.onde")),
        "tscan": write_tscan_file(os.path.join(directory, "tscan.onde")),
        "cscan": write_cscan_file(os.path.join(directory, "cscan.onde")),
        "hostile": write_hostile_file(os.path.join(directory, "hostile.onde")),
        "nested": write_nested_file(os.path.join(directory, "nested.onde")),
        "bytestype": write_bytestype_file(
            os.path.join(directory, "bytestype.onde")),
        "legacy": write_legacy_file(os.path.join(directory, "legacy.onde")),
    }
