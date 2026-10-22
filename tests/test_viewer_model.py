"""Tests for PyONDE.viewer.model: axis calibration, slicing and file structure."""

import numpy as np
import pytest

from PyONDE.viewer.model import AxisDescriptor

from conftest import hostile_dataset


# -- AxisDescriptor -------------------------------------------------------

def test_axis_calibration_is_index_times_scale_plus_offset():
    axis = AxisDescriptor(0, 5, "Time", "seconds", scale=2e-8, offset=1e-6)
    assert axis.value_at(0) == pytest.approx(1e-6)
    assert axis.value_at(4) == pytest.approx(1e-6 + 4 * 2e-8)
    np.testing.assert_allclose(axis.values(),
                               1e-6 + np.arange(5) * 2e-8)


def test_axis_extent_edges_are_half_a_sample_beyond_the_centers():
    """imshow extent must use edges, or the image sits half a pixel off."""
    axis = AxisDescriptor(0, 4, "U Position", "meters", scale=1e-3, offset=0.0)
    low, high = axis.extent_edges()
    assert low == pytest.approx(-0.5e-3)
    assert high == pytest.approx(3.5e-3)


def test_axis_defaults_follow_the_specification():
    axis = AxisDescriptor.from_dimension(0, 10, None)
    assert (axis.coordinate, axis.units) == ("Time", "seconds")
    assert (axis.scale, axis.offset) == (1.0, 0.0)
    assert axis.is_default


def test_axis_kind_prefers_the_coordinate_name_over_the_units():
    """UNITS is the field most often omitted; the spec default is 'seconds'.

    A dimension called "U Position" with no units must not read as a time axis.
    """
    positional = AxisDescriptor(0, 10, "U Position", "seconds")
    assert positional.kind == "space"
    assert AxisDescriptor(0, 10, "Time", "seconds").kind == "time"
    assert AxisDescriptor(0, 10, "Time of flight", "seconds").kind == "time"
    assert AxisDescriptor(0, 10, "Ascan", "unitless").kind == "channel"
    assert AxisDescriptor(0, 10, "Gizmos", "gizmos").kind == "index"


def test_axis_display_scale_rescales_only_labels():
    axis = AxisDescriptor(0, 1000, "Time", "seconds", scale=1e-8)
    factor, unit_label = axis.display_scale()
    assert unit_label == "us"
    assert axis.value_at(100) == pytest.approx(1e-6)      # stored value stays SI
    assert "us" in axis.format_value(100)


def test_axis_display_scale_leaves_unknown_units_alone():
    axis = AxisDescriptor(0, 10, "Ascan", "unitless", scale=1.0)
    assert axis.display_scale() == (1.0, "unitless")


# -- datasets -------------------------------------------------------------

def test_ascan_axes_come_from_index_dimensions(ascan_model):
    assert ascan_model.shape == (3, 4, 2, 1000)
    coordinates = [axis.coordinate for axis in ascan_model.axes]
    assert coordinates == ["U Position", "V Position", "Ascan", "Time"]
    assert ascan_model.axes[3].scale == pytest.approx(1e-8)
    assert ascan_model.axes[3].offset == pytest.approx(1e-5)
    assert not any(axis.is_default for axis in ascan_model.axes)


def test_slice_applies_amplitude_calibration(ascan_model):
    """Calibrated value = stored*SCALE + OFFSET, applied to the slice only."""
    assert ascan_model.amplitude.scale == pytest.approx(0.01)
    stored = ascan_model.raw[1, 2, 0, :]
    calibrated = ascan_model.slice((1, 2, 0, slice(None)))
    np.testing.assert_allclose(calibrated, stored * 0.01)
    assert ascan_model.slice((1, 2, 0, slice(None)), calibrate=False)[5] == \
        pytest.approx(stored[5])


def test_slice_of_uncalibrated_dataset_matches_storage(tscan_document):
    model = [m for m in tscan_document.datasets if m.has_data][0]
    assert not model.is_calibrated
    np.testing.assert_array_equal(model.slice((0, 0, slice(None), slice(None))),
                                  model.raw[0, 0, :, :])


def test_slice_rejects_a_dataset_with_no_data(tscan_document):
    empty = [m for m in tscan_document.datasets if not m.has_data][0]
    assert empty.shape is None
    assert empty.axes == []
    with pytest.raises(ValueError, match="no DATA"):
        empty.slice((0,))


def test_integer_data_survives_slicing(hostile_document):
    model = hostile_dataset(hostile_document, "Integer A-scans")
    assert model.dtype == np.int16
    extracted = model.slice((0, 0, 0, slice(None)))
    assert extracted.shape == (64,)


def test_missing_dimensions_fall_back_to_spec_defaults(hostile_document):
    model = hostile_dataset(hostile_document, "Integer A-scans")
    assert len(model.axes) == model.ndim
    assert all(axis.is_default for axis in model.axes)
    assert model.amplitude.coordinate == "Amplitude"
    assert model.amplitude.units == "arbitrary"


def test_rank_and_dimension_count_mismatch_warns_but_works(hostile_document):
    model = hostile_dataset(hostile_document, "mismatch")
    assert model.ndim == 2
    assert len(model.axes) == 2
    assert any("INDEX_DIMENSIONS lists 4" in message for message in model.warnings)
    # the first two listed dimensions are still honored
    assert model.axes[0].coordinate == "U Position"


def test_data_stored_as_an_hdf5_reference_is_read(hostile_document):
    model = hostile_dataset(hostile_document, "by HDF5 reference")
    assert model.shape == (3, 128)
    assert model.axes[0].coordinate == "U Position"
    # UNITS omitted on that dimension -> spec default, but not a time axis
    assert model.axes[0].units == "seconds"
    assert model.axes[0].kind == "space"


def test_partial_dimension_metadata_keeps_the_given_fields(hostile_document):
    model = hostile_dataset(hostile_document, "by HDF5 reference")
    assert model.axes[0].scale == pytest.approx(2.5e-3)
    assert model.axes[1].offset == pytest.approx(1e-6)


# -- documents ------------------------------------------------------------

def test_document_indexes_by_short_key_full_key_and_position(ascan_document):
    model = ascan_document.datasets[0]
    assert ascan_document[model.short_key] is model
    assert ascan_document[model.full_key] is model
    assert ascan_document[0] is model
    assert ascan_document.get("nonexistent") is None


def test_document_separates_viewable_datasets(tscan_document):
    assert len(tscan_document) == 2
    assert len(tscan_document.viewable) == 1


def test_document_reports_file_level_metadata(ascan_document):
    from PyONDE.viewer import access
    assert ascan_document.file_version
    assert ascan_document.onde_version == access.DEFAULT_ONDE_VERSION


def test_metadata_tree_walks_the_setup_and_dedupes_sharing(ascan_model):
    tree = ascan_model.metadata_tree()
    assert "ONDE_DATASET:SETUP" in tree
    setup = tree["ONDE_DATASET:SETUP"]
    assert "ONDE_SETUP:GEOMETRIC_SETUP" in setup
    # arrays are summarized, not dumped
    data = tree["ONDE_DATASET:DATA"]
    assert data["shape"] == (3, 4, 2, 1000)
    assert "min" in data and "max" in data


def test_metadata_tree_respects_the_depth_cap(ascan_model):
    shallow = ascan_model.metadata_tree(max_depth=2)
    assert "<max depth reached>" in repr(shallow)


# The nested-group case moved to test_viewer_library_versions.py, where it
# probes PyONDE's enable_hierarchical flag instead of assuming it is off.
