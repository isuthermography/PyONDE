"""matplotlib is not a dependency of PyONDE, so everything else must work without it.

Not a requirement and not an extra: the library, the viewer's model layer and
the ``--list`` / ``--info`` paths all have to import and run on an interpreter
that has never heard of matplotlib.  What the viewer owes someone in that
position is a clear instruction, in a message box as well as on stderr, since
``ondeview`` may have been started from a launcher with no terminal attached.

Some of these run in subprocesses: the point is what happens at import time in
a fresh interpreter, which cannot be observed once the test session has itself
imported matplotlib.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from PyONDE.viewer import dependency


#: Injected into the subprocesses that must behave as if matplotlib were absent.
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


def _run(source, **environment):
    env = dict(os.environ)
    env.update(environment)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(source)],
                          capture_output=True, text=True, env=env)


def _run_without_matplotlib(source, **environment):
    return _run(_BLOCK_MATPLOTLIB + textwrap.dedent(source), **environment)


# -- nothing drags matplotlib in ------------------------------------------

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


def test_importing_the_viewer_does_not_import_a_gui_toolkit_either():
    """The dialog machinery must stay as lazy as matplotlib itself.

    tkinter is slow to import and absent on plenty of installations; nothing
    may touch it until there is actually a box to draw.
    """
    result = _run("""
        import sys
        import PyONDE.viewer
        from PyONDE.viewer import report_missing_matplotlib
        assert "tkinter" not in sys.modules
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


# -- what the user is told ------------------------------------------------

def test_missing_matplotlib_produces_an_actionable_message():
    """Simulate matplotlib not being installed."""
    result = _run_without_matplotlib("""
        from PyONDE.viewer import require_matplotlib
        try:
            require_matplotlib()
        except ImportError as err:
            assert "pip install matplotlib" in str(err), str(err)
            print("ok")
        else:
            raise AssertionError("expected ImportError")
    """)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_no_message_offers_an_extra_that_no_longer_exists():
    """Pins the packaging decision where the user would see it break.

    "pip install PyONDE[viewer]" now fails with a warning about an unknown
    extra and installs nothing, which is a worse place to send someone than
    the ImportError they already have.
    """
    for message in (dependency.MATPLOTLIB_MESSAGE, dependency.MATPLOTLIB_REPORT):
        assert "[viewer]" not in message
        assert "pip install matplotlib" in message


def test_pyproject_declares_matplotlib_nowhere():
    """Not a requirement, not an extra -- the point of the exercise."""
    tomllib = pytest.importorskip("tomllib")
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():          # installed copy rather than a checkout
        pytest.skip("no pyproject.toml beside the tests")
    with pyproject.open("rb") as handle:
        parsed = tomllib.load(handle)

    project = parsed["project"]
    assert "optional-dependencies" not in project
    declared = (project.get("dependencies", [])
                + parsed.get("build-system", {}).get("requires", []))
    assert not [item for item in declared if "matplotlib" in item]


# -- the message box ------------------------------------------------------

class _Recorder:
    """Stands in for a dialog backend."""

    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, title, text):
        self.calls.append((title, text))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def on_a_desktop(monkeypatch):
    monkeypatch.delenv(dependency.NO_DIALOG_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")


def test_the_report_goes_to_the_stream_and_into_a_box(on_a_desktop, monkeypatch,
                                                      capsys):
    recorder = _Recorder()
    monkeypatch.setattr(dependency, "_dialog_backends",
                        lambda: [("recorder", recorder)])

    assert dependency.report_missing_matplotlib() == "recorder"

    printed = capsys.readouterr().err
    assert "pip install matplotlib" in printed
    assert len(recorder.calls) == 1
    title, text = recorder.calls[0]
    assert "matplotlib" in title
    assert "pip install matplotlib" in text


def test_a_backend_that_fails_hands_on_to_the_next(on_a_desktop, monkeypatch):
    """Tk can be missing, a helper can be on PATH and broken, a display can lie."""
    broken = _Recorder(error=RuntimeError("no display after all"))
    inapplicable = _Recorder(result=False)
    working = _Recorder()
    monkeypatch.setattr(dependency, "_dialog_backends",
                        lambda: [("broken", broken), ("n/a", inapplicable),
                                 ("working", working)])

    assert dependency.report_missing_matplotlib() == "working"
    assert broken.calls and inapplicable.calls and working.calls


def test_the_text_still_appears_when_no_box_can_be_drawn(on_a_desktop,
                                                         monkeypatch, capsys):
    monkeypatch.setattr(dependency, "_dialog_backends",
                        lambda: [("n/a", _Recorder(result=False))])

    assert dependency.report_missing_matplotlib() is None
    assert "pip install matplotlib" in capsys.readouterr().err


def test_no_box_is_attempted_without_a_display(monkeypatch, capsys):
    """A dialog nobody can dismiss would hang an unattended run outright."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv(dependency.NO_DIALOG_VARIABLE, raising=False)
    never = _Recorder()
    monkeypatch.setattr(dependency, "_dialog_backends",
                        lambda: [("never", never)])

    assert dependency.dialogs_are_possible() is False
    assert dependency.report_missing_matplotlib() is None
    assert not never.calls
    assert "pip install matplotlib" in capsys.readouterr().err


def test_wayland_counts_as_a_display(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv(dependency.NO_DIALOG_VARIABLE, raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert dependency.dialogs_are_possible() is True


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_windows_and_macos_always_have_somewhere_to_draw(monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv(dependency.NO_DIALOG_VARIABLE, raising=False)
    assert dependency.dialogs_are_possible() is True


def test_the_box_can_be_switched_off(on_a_desktop, monkeypatch, capsys):
    monkeypatch.setenv(dependency.NO_DIALOG_VARIABLE, "1")
    never = _Recorder()
    monkeypatch.setattr(dependency, "_dialog_backends",
                        lambda: [("never", never)])

    assert dependency.report_missing_matplotlib() is None
    assert not never.calls
    assert "pip install matplotlib" in capsys.readouterr().err


def test_the_real_backends_degrade_quietly(monkeypatch, capsys):
    """The one test that runs the actual dialog code rather than a stand-in.

    A display that does not exist is the safe way to do that: every backend
    gets its real chance and every one of them fails, which is precisely the
    path that must not raise, hang, or lose the message.  (It stays safe on a
    developer's machine -- :99 is not their session, so nothing opens.)
    """
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv(dependency.NO_DIALOG_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    assert dependency.report_missing_matplotlib() is None
    assert "pip install matplotlib" in capsys.readouterr().err


def test_each_platform_offers_a_backend_after_tkinter(monkeypatch):
    for platform, expected in (("win32", "windows"), ("darwin", "osascript"),
                               ("linux", "desktop-helper")):
        monkeypatch.setattr(sys, "platform", platform)
        names = [name for name, _ in dependency._dialog_backends()]
        assert names[0] == "tkinter"
        assert expected in names


# -- the command line -----------------------------------------------------

def test_cli_list_works_without_matplotlib(tmp_path):
    """The headless listing path must not need matplotlib."""
    result = _run_without_matplotlib(f"""
        from PyONDE.viewer import testdata
        from PyONDE.bin import ondeview
        path = testdata.write_cscan_file({str(tmp_path / 'c.onde')!r})
        raise SystemExit(ondeview.main(["--list", path]))
    """)
    assert result.returncode == 0, result.stderr
    assert "ONDE_DATASET_UT_CSCAN" in result.stdout


def test_cli_view_without_matplotlib_explains_and_exits(tmp_path):
    """End to end, in an interpreter that really cannot import matplotlib."""
    result = _run_without_matplotlib(f"""
        from PyONDE.viewer import testdata
        from PyONDE.bin import ondeview
        path = testdata.write_ascan_file({str(tmp_path / 'a.onde')!r})
        raise SystemExit(ondeview.main([path]))
    """, **{dependency.NO_DIALOG_VARIABLE: "1"})
    assert result.returncode == 3, (result.returncode, result.stderr)
    assert "pip install matplotlib" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_view_without_matplotlib_tries_the_box(monkeypatch, onde_files,
                                                   capsys):
    """That the CLI asks for a box at all, rather than only printing."""
    from PyONDE import viewer
    from PyONDE.bin import ondeview

    recorder = _Recorder()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv(dependency.NO_DIALOG_VARIABLE, raising=False)
    monkeypatch.setattr(dependency, "_dialog_backends",
                        lambda: [("recorder", recorder)])

    def no_matplotlib():
        raise ImportError(dependency.MATPLOTLIB_MESSAGE)

    monkeypatch.setattr(viewer, "require_matplotlib", no_matplotlib)

    assert ondeview.main([onde_files["ascan"]]) == 3
    assert len(recorder.calls) == 1
    assert "pip install matplotlib" in capsys.readouterr().err
