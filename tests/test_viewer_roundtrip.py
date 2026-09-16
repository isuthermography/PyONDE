"""Independent verification: compare the model against raw h5py.

Every other test reads the file through PyONDE, so a shared misreading of the
storage would pass unnoticed.  These tests walk the HDF5 file directly and
recompute what the model claims, which is the only check here that would catch
PyONDE and the viewer being wrong in the same direction.
"""

import h5py
import numpy as np

from PyONDE.viewer.model import OndeDocument


def _find_dataset_group(handle, label):
    """Locate the HDF5 group of the dataset whose ONDE:LABEL is *label*."""
    found = []

    def visit(name, item):
        if isinstance(item, h5py.Group) and \
                item.attrs.get("ONDE:LABEL", None) == label:
            found.append(item)

    handle.visititems(visit)
    assert found, f"no group labeled {label!r}"
    return found[0]


def _read_field(handle, group, field):
    """Read a field that may be an attribute, a child dataset, or a reference."""
    if field in group:
        return group[field][...]
    value = group.attrs[field]
    if isinstance(value, h5py.Reference):
        return handle[value][...]
    return value


def test_slice_matches_a_direct_hdf5_read(onde_files):
    with OndeDocument.open(onde_files["ascan"]) as document:
        model = document.datasets[0]
        selector = (1, 2, 0, slice(None))
        through_model = model.slice(selector)
        scale = model.amplitude.scale
        offset = model.amplitude.offset

    with h5py.File(onde_files["ascan"], "r") as handle:
        group = _find_dataset_group(handle, "Synthetic A-scan raster")
        stored = _read_field(handle, group, "ONDE_DATASET:DATA")
        expected = stored[selector] * scale + offset

    np.testing.assert_allclose(through_model, expected)


def test_axis_values_match_the_stored_dimension_fields(onde_files):
    with OndeDocument.open(onde_files["ascan"]) as document:
        axis = document.datasets[0].axes[3]
        values = axis.values()

    with h5py.File(onde_files["ascan"], "r") as handle:
        group = _find_dataset_group(handle, "Synthetic A-scan raster")
        references = group.attrs["ONDE_DATASET:INDEX_DIMENSIONS"]
        time_dimension = handle[references[3]]
        scale = float(time_dimension.attrs["ONDE_DIMENSION:SCALE"])
        offset = float(time_dimension.attrs["ONDE_DIMENSION:OFFSET"])

    np.testing.assert_allclose(values, np.arange(values.size) * scale + offset)


def test_referenced_data_resolves_to_the_referenced_array(onde_files):
    """The 'byref' dataset's DATA is an HDF5 reference into an unrelated group."""
    with OndeDocument.open(onde_files["hostile"]) as document:
        model = [m for m in document.datasets
                 if "reference" in m.label.lower()][0]
        through_model = np.asarray(model.raw)

    with h5py.File(onde_files["hostile"], "r") as handle:
        expected = handle["/storage/blob"][...]

    np.testing.assert_array_equal(through_model, expected)


def test_reported_shapes_match_the_file(onde_files):
    for name in ("ascan", "tscan", "cscan"):
        with OndeDocument.open(onde_files[name]) as document:
            reported = {model.label: model.shape
                        for model in document.datasets if model.has_data}

        with h5py.File(onde_files[name], "r") as handle:
            for label, shape in reported.items():
                group = _find_dataset_group(handle, label)
                stored = _read_field(handle, group, "ONDE_DATASET:DATA")
                assert np.shape(stored) == shape, label
