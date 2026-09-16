"""Tests for slice and figure export.

The important property is that an exported file can be read back and matched
against the ONDE file it came from -- so these read their own output rather than
just checking that a file appeared.
"""

import csv

import numpy as np
import pytest

from PyONDE.viewer import export
from PyONDE.viewer.state import ViewState, default_state_for


def _read_csv(path):
    comments, rows = [], []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("#"):
                comments.append(line[1:].strip())
            elif line.strip():
                rows.append(next(csv.reader([line.rstrip("\n")])))
    return comments, rows


# -- filenames ------------------------------------------------------------

def test_default_filename_describes_the_slice(ascan_model):
    state = default_state_for(ascan_model).evolve(indices={0: 1, 1: 2, 2: 0})
    name = export.default_filename(ascan_model, state, ".csv")
    assert name.endswith(".csv")
    assert "1971" in name or ascan_model.short_key in name
    assert "u_po1" in name and "v_po2" in name


def test_default_filename_omits_degenerate_axes(hostile_document):
    from conftest import hostile_dataset
    model = hostile_dataset(hostile_document, "Single A-scan")
    state = default_state_for(model)
    name = export.default_filename(model, state, ".csv")
    # the three length-1 axes contribute no index tokens
    assert "u_po0" not in name and "v_po0" not in name and "none0" not in name


def test_unsupported_extensions_are_rejected(ascan_model, tmp_path):
    state = default_state_for(ascan_model)
    with pytest.raises(ValueError, match="unsupported data format"):
        export.save_slice(ascan_model, state, str(tmp_path / "x.wav"))


# -- 1-D exports ----------------------------------------------------------

def test_csv_of_a_waveform_round_trips(ascan_model, tmp_path):
    state = default_state_for(ascan_model).evolve(indices={0: 1, 1: 2, 2: 0})
    path = export.save_slice(ascan_model, state, str(tmp_path / "wave.csv"))

    _, rows = _read_csv(path)
    positions = np.array([float(row[0]) for row in rows])
    values = np.array([float(row[1]) for row in rows])

    np.testing.assert_allclose(positions, ascan_model.axes[3].values())
    np.testing.assert_allclose(values, ascan_model.slice((1, 2, 0, slice(None))))


def test_csv_values_are_si_not_display_units(ascan_model, tmp_path):
    """The axis is labeled in microseconds on screen; the file says seconds."""
    state = default_state_for(ascan_model)
    path = export.save_slice(ascan_model, state, str(tmp_path / "wave.csv"))
    _, rows = _read_csv(path)
    assert float(rows[0][0]) == pytest.approx(1e-5)      # not 10.0


def test_csv_header_records_provenance(ascan_model, tmp_path):
    state = default_state_for(ascan_model).evolve(indices={0: 1, 1: 2, 2: 0})
    path = export.save_slice(ascan_model, state, str(tmp_path / "wave.csv"))
    comments, _ = _read_csv(path)
    joined = "\n".join(comments)
    assert ascan_model.full_key in joined
    assert "ONDE_DATASET_UT_ASCAN" in joined
    assert "Voltage [Volts] = stored*0.01" in joined
    assert "fixed: index 1 V Position [2] = 0.004 meters" in joined
    assert ascan_model.document.path in joined


def test_numpy_scalars_are_written_as_plain_numbers(ascan_model, tmp_path):
    """repr() of a numpy scalar is "np.float64(...)", which no reader parses."""
    state = default_state_for(ascan_model)
    path = export.save_slice(ascan_model, state, str(tmp_path / "wave.csv"))
    with open(path, encoding="utf-8") as stream:
        body = stream.read()
    assert "np.float64" not in body


# -- 2-D exports ----------------------------------------------------------

def test_csv_of_an_image_carries_axis_coordinates(tscan_document, tmp_path):
    model = tscan_document.viewable[0]
    state = default_state_for(model)
    path = export.save_slice(model, state, str(tmp_path / "image.csv"))

    _, rows = _read_csv(path)
    x_values = np.array([float(cell) for cell in rows[0][1:]])
    y_values = np.array([float(row[0]) for row in rows[1:]])
    matrix = np.array([[float(cell) for cell in row[1:]] for row in rows[1:]])

    np.testing.assert_allclose(x_values, model.axes[3].values())
    np.testing.assert_allclose(y_values, model.axes[2].values())
    np.testing.assert_allclose(matrix,
                               model.slice((0, 0, slice(None), slice(None))))


def test_exported_image_matches_the_displayed_orientation(ascan_model, tmp_path):
    """A transposed view must export as displayed, not as stored."""
    state = ViewState(ascan_model.short_key, (3, 1), {0: 0, 2: 0})
    path = export.save_slice(ascan_model, state, str(tmp_path / "t.csv"))
    _, rows = _read_csv(path)
    matrix = np.array([[float(cell) for cell in row[1:]] for row in rows[1:]])
    assert matrix.shape == (1000, 4)
    np.testing.assert_allclose(
        matrix, ascan_model.slice((0, slice(None), 0, slice(None))).T)


def test_tsv_uses_tabs(tscan_document, tmp_path):
    model = tscan_document.viewable[0]
    path = export.save_slice(model, default_state_for(model),
                             str(tmp_path / "image.tsv"))
    with open(path, encoding="utf-8") as stream:
        body = [line for line in stream if not line.startswith("#")]
    assert "\t" in body[0]


# -- numpy exports --------------------------------------------------------

def test_npy_holds_the_bare_array(ascan_model, tmp_path):
    state = default_state_for(ascan_model)
    path = export.save_slice(ascan_model, state, str(tmp_path / "w.npy"))
    np.testing.assert_allclose(np.load(path),
                               ascan_model.slice(state.selector()))


def test_npz_holds_the_array_axes_and_header(tscan_document, tmp_path):
    model = tscan_document.viewable[0]
    state = default_state_for(model)
    path = export.save_slice(model, state, str(tmp_path / "i.npz"))
    with np.load(path, allow_pickle=True) as bundle:
        np.testing.assert_allclose(bundle["data"],
                                   model.slice(state.selector()))
        assert any(name.startswith("axis2_") for name in bundle.files)
        assert any(name.startswith("axis3_") for name in bundle.files)
        assert any(model.full_key in str(line) for line in bundle["header"])


def test_export_refuses_a_dataset_without_data(tscan_document, tmp_path):
    empty = [m for m in tscan_document.datasets if not m.has_data][0]
    state = default_state_for(empty)
    with pytest.raises(ValueError, match="no DATA"):
        export.save_slice(empty, state, str(tmp_path / "nothing.csv"))


# -- figures --------------------------------------------------------------

def test_save_figure_writes_the_named_format(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg", force=True)
    from matplotlib.figure import Figure
    figure = Figure()
    figure.add_subplot().plot([0, 1], [1, 0])
    path = export.save_figure(figure, str(tmp_path / "plot.pdf"))
    with open(path, "rb") as stream:
        assert stream.read(4) == b"%PDF"


def test_save_figure_rejects_a_data_extension(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg", force=True)
    from matplotlib.figure import Figure
    with pytest.raises(ValueError, match="unsupported figure format"):
        export.save_figure(Figure(), str(tmp_path / "plot.csv"))
