"""Tests for the ondeview command line entry point."""

import pytest

from PyONDE.bin import ondeview


def test_list_succeeds_on_every_synthetic_file(onde_files, capsys):
    for name in ("ascan", "tscan", "cscan", "hostile"):
        assert ondeview.main(["--list", onde_files[name]]) == 0
        output = capsys.readouterr().out
        assert "ONDE:VERSION" in output


def test_list_shows_shape_type_and_label(onde_files, capsys):
    ondeview.main(["--list", onde_files["ascan"]])
    output = capsys.readouterr().out
    assert "ONDE_DATASET_UT_ASCAN" in output
    assert "3x4x2x1000" in output
    assert "Synthetic A-scan raster" in output


def test_list_reports_a_dataset_with_no_data(onde_files, capsys):
    ondeview.main(["--list", onde_files["tscan"]])
    assert "no DATA" in capsys.readouterr().out


def test_list_surfaces_structural_warnings(onde_files, capsys):
    ondeview.main(["--list", onde_files["hostile"]])
    assert "warning:" in capsys.readouterr().out


def test_info_describes_axes_and_calibration(onde_files, ascan_document, capsys):
    key = ascan_document.datasets[0].short_key
    assert ondeview.main(["--info", key, onde_files["ascan"]]) == 0
    output = capsys.readouterr().out
    assert "U Position" in output
    assert "Voltage" in output
    assert "metadata:" in output


def test_info_on_an_unknown_key_reports_the_known_ones(onde_files, capsys):
    assert ondeview.main(["--info", "nope", onde_files["ascan"]]) == 2
    assert "known keys" in capsys.readouterr().err


def test_a_closed_pipe_is_not_a_traceback(onde_files):
    """`ondeview --list file | head` must stop quietly."""
    import subprocess
    import sys
    listing = subprocess.Popen(
        [sys.executable, "-m", "PyONDE.bin.ondeview", "--list",
         onde_files["ascan"]],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    head = subprocess.Popen(["head", "-1"], stdin=listing.stdout,
                            stdout=subprocess.PIPE)
    listing.stdout.close()
    head.communicate()
    errors = listing.stderr.read().decode()
    listing.wait()
    assert "BrokenPipeError" not in errors, errors
    assert "Traceback" not in errors, errors


def test_missing_file_is_reported_not_raised(tmp_path, capsys):
    assert ondeview.main(["--list", str(tmp_path / "absent.onde")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_unloadable_file_is_reported_not_raised(onde_files, capsys):
    """A file PyONDE cannot load must produce a message, not a traceback."""
    assert ondeview.main(["--list", onde_files["nested"]]) == 1
    error = capsys.readouterr().err
    assert "cannot read" in error
    assert "Unknown h5type Group" in error


def test_viewer_launch_refuses_a_non_interactive_backend(onde_files, capsys):
    """Under Agg there is no window to open, so say so instead of hanging."""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg", force=True)
    assert ondeview.main([onde_files["ascan"]]) == 4
    error = capsys.readouterr().err
    assert "non-interactive" in error
    assert "MPLBACKEND=QtAgg" in error
