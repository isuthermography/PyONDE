"""matplotlib is an extra, so the model layer must work without it.

These run in subprocesses: the point is what happens at import time in a fresh
interpreter, which cannot be observed once the test session has already imported
matplotlib.
"""

import subprocess
import sys
import textwrap


#: Injected into the subprocesses that must behave as if the extra were absent.
#: Uses find_spec rather than the find_module protocol, which Python 3.12 removed.
_BLOCK_MATPLOTLIB = """
import sys
class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "matplotlib":
            raise ImportError(f"no module named {name} (blocked for test)")
        return None
sys.meta_path.insert(0, _Blocker())
"""


def _run(source):
    return subprocess.run([sys.executable, "-c", textwrap.dedent(source)],
                          capture_output=True, text=True)


def _run_without_matplotlib(source):
    return _run(_BLOCK_MATPLOTLIB + textwrap.dedent(source))


def test_importing_the_viewer_does_not_import_matplotlib():
    result = _run("""
        import sys
        import PyONDE.viewer
        from PyONDE.viewer import OndeDocument, ViewState, default_state_for
        assert "matplotlib" not in sys.modules, sorted(
            m for m in sys.modules if m.startswith("matplotlib"))
        print("ok")
    """)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_importing_pyonde_does_not_import_the_viewer():
    """PyONDE itself must not pull in the viewer package."""
    result = _run("""
        import sys
        import PyONDE
        assert "PyONDE.viewer" not in sys.modules
        print("ok")
    """)
    assert result.returncode == 0, result.stderr


def test_missing_matplotlib_produces_an_actionable_message():
    """Simulate the extra not being installed."""
    result = _run_without_matplotlib("""
        from PyONDE.viewer import require_matplotlib
        try:
            require_matplotlib()
        except ImportError as err:
            assert "pip install PyONDE[viewer]" in str(err), str(err)
            print("ok")
        else:
            raise AssertionError("expected ImportError")
    """)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_cli_list_works_without_matplotlib(tmp_path):
    """The headless listing path must not need the extra."""
    result = _run_without_matplotlib(f"""
        from PyONDE.viewer import testdata
        from PyONDE.bin import ondeview
        path = testdata.write_cscan_file({str(tmp_path / 'c.onde')!r})
        raise SystemExit(ondeview.main(["--list", path]))
    """)
    assert result.returncode == 0, result.stderr
    assert "ONDE_DATASET_UT_CSCAN" in result.stdout
