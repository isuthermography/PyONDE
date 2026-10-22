"""Tests around the ONDE specification version and PyONDE's own behaviors.

Which class definitions the viewer reads with is a decision, not a discovery:
:data:`PyONDE.viewer.access.DEFAULT_ONDE_VERSION` fixes it, and ``--onde-version``
overrides it.  The version decides how field names resolve; it must never decide
what the data is.

Two PyONDE behaviors are covered here rather than in the access-layer tests,
because they are properties of the library that the viewer has to live with:
short keys that cannot be meaningfully shortened, and hierarchical files.
"""

import numpy as np
import pytest

from PyONDE.viewer import access
from PyONDE.viewer.model import OndeDocument


# -- which class definitions to read with ---------------------------------

def test_the_default_version_is_fixed_not_discovered():
    """A pinned version; bumping it is a deliberate act, tested against."""
    assert access.DEFAULT_ONDE_VERSION == "0.9.2"
    assert access.DEFAULT_ONDE_VERSION in access.available_onde_versions()


def test_the_default_is_what_a_document_reads_with(onde_files):
    with OndeDocument.open(onde_files["ascan"]) as document:
        assert document.onde_version == access.DEFAULT_ONDE_VERSION


def test_an_explicit_version_is_honored(onde_files):
    with OndeDocument.open(onde_files["ascan"],
                           onde_version="0.9.1pre") as document:
        assert document.onde_version == "0.9.1pre"
        assert document.datasets[0].has_data


def test_a_version_pyonde_does_not_ship_is_reported_clearly(onde_files):
    """Otherwise this surfaces as a FileNotFoundError naming a CSV inside PyONDE,
    which reads as though the data file were the thing that was missing."""
    with pytest.raises(ValueError, match="no ONDE class definitions"):
        OndeDocument.open(onde_files["ascan"], onde_version="9.9.9pre")

    from PyONDE.bin import ondeview
    assert ondeview.main(["--list", "--onde-version", "9.9.9pre",
                          onde_files["ascan"]]) == 1


@pytest.mark.parametrize("name", ["ascan", "tscan", "cscan", "hostile",
                                  "legacy"])
def test_the_data_is_the_same_under_every_set_of_definitions(onde_files, name):
    """The class definitions decide name resolution, never the data.

    0.9.2 renamed SENSOR_LIST to PROBE_LIST and FRAME to INDEX_POINT_FRAME, so
    the legacy file has fields the current definitions do not know -- which
    must not change a single sample, axis or calibration.
    """
    views = {}
    for version in access.available_onde_versions():
        with OndeDocument.open(onde_files[name], onde_version=version) as doc:
            views[version] = [
                (model.label, model.shape, model.leaf_type,
                 tuple((axis.coordinate, axis.units, axis.scale, axis.offset)
                       for axis in model.axes),
                 None if not model.has_data
                 else float(np.nansum(model.slice(
                     tuple(0 for _ in model.axes[:-1]) + (slice(None),)))))
                for model in doc.datasets]
    distinct = {repr(view) for view in views.values()}
    assert len(distinct) == 1, f"{name} reads differently per version: {views}"


def test_a_field_the_definitions_do_not_know_is_still_reachable(onde_files):
    """SENSOR_LIST is pre-0.9.2; under 0.9.2 it needs its fully qualified name."""
    with OndeDocument.open(onde_files["legacy"]) as document:
        setup = access.field(document.datasets[0].dataset, "ONDE_DATASET:SETUP")
        geometric = access.field(setup, "ONDE_SETUP:GEOMETRIC_SETUP")
        sensors = access.field(geometric, "ONDE_GEOMETRIC_SETUP:SENSOR_LIST")
        assert access.ref_len(sensors) == 1
        probe = access.ref_list(sensors)[0]
        assert access.field_value(probe, "ONDE_UT_PROBE:FREQUENCY") == \
            pytest.approx(5e6)


def test_the_metadata_inspector_shows_unknown_fields(onde_files):
    from PyONDE.viewer.inspector import format_tree
    with OndeDocument.open(onde_files["legacy"]) as document:
        lines = format_tree(document.datasets[0].metadata_tree())
    assert any("SENSOR_LIST" in line for line in lines)


# -- bytes-typed ONDE:TYPE ------------------------------------------------

def test_a_bytes_typed_dataset_is_read_and_decoded(onde_files):
    """HDF5 fixed-length strings read back as bytes; PyONDE decodes them.

    A writer in C or FORTRAN produces exactly this, and h5py does too for a
    numpy "S" array.  The viewer's type_chain decodes as well, so the two
    together mean nothing downstream ever sees bytes.
    """
    with OndeDocument.open(onde_files["bytestype"]) as document:
        assert len(document.datasets) == 1
        model = document.datasets[0]
        assert model.type_chain == ("ONDE_DATASET", "ONDE_DATASET_UT",
                                    "ONDE_DATASET_UT_ASCAN")
        assert all(isinstance(entry, str) for entry in model.type_chain)
        assert model.label == "Bytes-typed ONDE:TYPE"      # a bytes attribute
        assert model.leaf_type == "ONDE_DATASET_UT_ASCAN"
        assert model.shape == (1, 32)


def test_a_bytes_typed_dataset_displays(onde_files):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg", force=True)
    from PyONDE.viewer.app import OndeViewerApp

    with OndeDocument.open(onde_files["bytestype"]) as document:
        app = OndeViewerApp(document)
        try:
            assert app.plot.line.get_visible()
            assert app.plot.line.get_ydata().size == 32
        finally:
            app.close()


def test_type_chain_decodes_bytes_on_its_own(onde_files):
    """Independent of the library: the viewer would decode these regardless."""

    class Fake(object):
        def __getitem__(self, name):
            return np.array([b"ONDE_DATASET", b"ONDE_DATASET_UT"], dtype="S32")

    assert access.type_chain(Fake()) == ("ONDE_DATASET", "ONDE_DATASET_UT")


# -- UUIDs and short keys -------------------------------------------------

def test_short_keys_can_be_fed_back_to_the_graph():
    """shortkeys() output must address the dataset it came from.

    3fb8328 moved UUIDs to the "urn:uuid:" prefix but left shortkeys() slicing
    at the old prefix length of 5, so short keys came back with four characters
    of the prefix still attached -- "uid:..." -- which _get_item() could not
    resolve.  Fixed upstream in 99f917d / a6be485, which slice by
    len(UUID_prefix); this test is what notices if that regresses.
    """
    import tempfile

    import h5py

    path = tempfile.mkdtemp() + "/probe.onde"
    with h5py.File(path, "w") as handle:
        handle.attrs["ONDE:VERSION"] = "0.9.2"
        handle.attrs["ONDE:FILETYPE"] = ["ONDE_UT"]
        for number, key in enumerate(("urn:uuid:1234abcd-0000-0000-0000-000000000001",
                                      "urn:uuid:9876fedc-0000-0000-0000-000000000002")):
            group = handle.create_group(f"ds{number}")
            group.attrs["ONDE:TYPE"] = ["ONDE_DATASET", "ONDE_DATASET_UT",
                                        "ONDE_DATASET_UT_ASCAN"]
            group.attrs["ONDE:UUID"] = key
            group.create_dataset("ONDE_DATASET:DATA", data=np.zeros((1, 4)))
    onde_file = access.open_onde_file(path)
    try:
        shorts = list(onde_file.graph.shortkeys())
        assert shorts and not any(short.startswith("uid:") for short in shorts)
        for short in shorts:
            assert onde_file.graph[short] is not None
    finally:
        onde_file.close()

def test_uuids_are_the_v0_9_2_urn_form(ascan_document):
    """v0.9.2 moved from "2.25.<decimal>" to "urn:uuid:<hyphenated hex>"."""
    full_key = ascan_document.datasets[0].full_key
    assert full_key.startswith("urn:uuid:")
    hexadecimal = full_key[len("urn:uuid:"):]
    assert [len(part) for part in hexadecimal.split("-")] == [8, 4, 4, 4, 12]
    assert hexadecimal == hexadecimal.lower()


def test_a_key_that_cannot_be_shortened_is_left_alone(hostile_document):
    """Designed PyONDE behavior, not a defect.

    The hostile file's UUIDs differ only in their final digit, so no prefix of
    any of them is unique and there is no meaningful short form; shortkeys()
    returns them at full length, with only the "urn:uuid:" every key shares
    removed.  The viewer never reconstructs one key from the other -- it zips
    keys() with shortkeys() positionally -- so a long short key addresses its
    dataset the same as any other.
    """
    for model in hostile_document.datasets:
        # whatever the library returns, the viewer can address the dataset by
        # it, because it pairs keys() with shortkeys() positionally
        assert hostile_document[model.short_key] is model
        assert hostile_document[model.full_key] is model

    long_keys = [model for model in hostile_document.datasets
                 if len(model.short_key) > 8]
    assert long_keys, "expected the colliding UUIDs to resist shortening"
    for model in long_keys:
        assert not model.short_key.startswith("urn:uuid:")
        assert model.full_key[len("urn:uuid:"):] == model.short_key


def test_distinct_uuids_shorten_to_a_few_characters(tscan_document):
    """The ordinary case: two datasets, two short unique prefixes."""
    for model in tscan_document.datasets:
        assert len(model.short_key) <= 8
        assert model.full_key.startswith("urn:uuid:" + model.short_key)
        assert tscan_document[model.short_key] is model


def test_a_legacy_2_25_uuid_still_addresses_its_dataset(onde_files):
    """The specification tells readers to treat the UUID as an opaque string.

    PyONDE shortens only the "urn:uuid:" form, so a pre-0.9.2 key comes back
    unshortened; the viewer takes it as given rather than assuming a prefix.
    """
    with OndeDocument.open(onde_files["legacy"]) as document:
        model = document.datasets[0]
        assert model.full_key.startswith("2.25.")
        assert model.short_key == model.full_key
        assert document[model.short_key] is model
        assert model.has_data and model.shape == (1, 1, 1, 500)


def test_short_keys_address_their_dataset(ascan_document):
    model = ascan_document.datasets[0]
    assert len(model.short_key) < len(model.full_key)
    assert ascan_document[model.short_key] is model


def test_dataset_labels_stay_distinct_when_keys_are_long(hostile_document):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg", force=True)
    from PyONDE.viewer.app import OndeViewerApp

    app = OndeViewerApp(hostile_document)
    try:
        texts = [text for _, text in app.dataset_labels]
        assert len(set(texts)) == len(texts)
        assert not any(text.startswith("2.25.") for text in texts)
    finally:
        app.close()


# -- hierarchical files ---------------------------------------------------

def test_nested_groups_behave_per_library_capability(onde_files):
    """A dataset group containing a sub-group.

    Hierarchical layout is waiting on a specification update, so PyONDE keeps
    it behind the module-level enable_hierarchical flag.  Probing the flag
    rather than asserting one outcome means this suite keeps passing on both
    sides of that change.
    """
    from PyONDE import onde

    if getattr(onde, "enable_hierarchical", False):
        with OndeDocument.open(onde_files["nested"]) as document:
            assert document.datasets
            assert document.datasets[0].has_data
    else:
        with pytest.raises(ValueError, match="Unknown h5type Group"):
            OndeDocument.open(onde_files["nested"])


def test_the_cli_reports_an_unloadable_file_either_way(onde_files, capsys):
    from PyONDE import onde
    from PyONDE.bin import ondeview

    code = ondeview.main(["--list", onde_files["nested"]])
    if getattr(onde, "enable_hierarchical", False):
        assert code == 0
    else:
        assert code == 1
        assert "cannot read" in capsys.readouterr().err


# -- scalar attributes ----------------------------------------------------

def _file_with_scalar_attribute(value):
    """A minimal loadable A-scan carrying one scalar attribute of `value`'s type."""
    import tempfile

    import h5py

    path = tempfile.mkdtemp() + "/scalar.onde"
    with h5py.File(path, "w") as handle:
        handle.attrs["ONDE:VERSION"] = "0.9.2"
        handle.attrs["ONDE:FILETYPE"] = ["ONDE_UT"]
        group = handle.create_group("ds")
        group.attrs["ONDE:TYPE"] = ["ONDE_DATASET", "ONDE_DATASET_UT",
                                    "ONDE_DATASET_UT_ASCAN"]
        group.attrs["ONDE:UUID"] = "urn:uuid:1234abcd-0000-0000-0000-000000000001"
        group.attrs["ONDE_DATASET_UT_ASCAN:PROBE_INDEX"] = value
        group.create_dataset("ONDE_DATASET:DATA", data=np.zeros((1, 4)))
    return path


def test_an_integer_scalar_attribute_reads_back(tscan_document):
    """HDF5 widens a Python int to int64 on the way out.

    Before a6be485 the loader's isinstance check did not accept numpy's
    integers, so a file carrying one raised "Unknown hdf5 attribute type:
    int64" and took the whole file with it -- the synthetic T-scan had to omit
    REFERENCE_PROBE_INDEX to stay readable.  It carries one again now.
    """
    model = [dataset for dataset in tscan_document.datasets
             if dataset.leaf_type.endswith("TSCAN")][0]
    setup = access.field(model.dataset,
                         "ONDE_DATASET_UT_TSCAN:RECONSTRUCTION_SETUP")
    assert access.field_value(
        setup, "ONDE_UT_RECONSTRUCTION_SETUP:REFERENCE_PROBE_INDEX") == 0


@pytest.mark.parametrize("value", [np.int64(2), np.int32(2), np.float64(1.5)])
def test_the_scalar_types_pyonde_accepts(value):
    document = OndeDocument.open(_file_with_scalar_attribute(value))
    try:
        assert document.datasets[0].has_data
    finally:
        document.close()


def _narrow_scalars_load():
    """True when this PyONDE accepts numpy scalars beyond int and float64."""
    try:
        OndeDocument.open(_file_with_scalar_attribute(np.float32(1.5))).close()
    except ValueError:
        return False
    return True


NARROW_SCALARS_LOAD = _narrow_scalars_load()


@pytest.mark.parametrize("value,expected", [(np.float32(1.5), 1.5),
                                            (np.bool_(True), True)])
def test_narrow_scalar_attributes_behave_per_library_capability(value, expected,
                                                                capsys):
    """The remaining half of the gap, probed rather than worked around.

    a6be485 added numpy's integers to the accepted types, and numpy's float64
    rides along because it subclasses Python's float.  float32 and bool_
    subclass neither, so an attribute a vendor wrote in single precision still
    raises and takes the whole file with it.  The viewer cannot route around
    that -- the loader never returns a file to work with -- so what it owes
    the user is a readable error, which is what this asserts until
    pyonde-generic-scalar-attributes.patch (or an equivalent) lands.
    """
    from PyONDE.bin import ondeview

    path = _file_with_scalar_attribute(value)
    if NARROW_SCALARS_LOAD:
        with OndeDocument.open(path) as document:
            assert document.datasets[0].has_data
            assert access.field_value(
                document.datasets[0].dataset,
                "ONDE_DATASET_UT_ASCAN:PROBE_INDEX") == expected
        assert ondeview.main(["--list", path]) == 0
    else:
        with pytest.raises(ValueError, match="Unknown hdf5 attribute type"):
            OndeDocument.open(path)
        assert ondeview.main(["--list", path]) == 1
        assert "cannot read" in capsys.readouterr().err


# -- the generator keeps up -----------------------------------------------

def test_the_synthetic_files_load_without_warnings_about_structure(onde_files):
    for name in ("ascan", "tscan", "cscan"):
        with OndeDocument.open(onde_files[name]) as document:
            assert document.warnings == []
