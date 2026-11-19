"""Saying that matplotlib is missing, in both places someone might be looking.

matplotlib is deliberately not declared as a dependency of PyONDE -- not a
required one, and not an extra either.  PyONDE itself, the viewer's model
layer, and ``ondeview --list`` / ``ondeview --info`` all work without it; only
the interactive front end needs it.  Declaring it, even optionally, would put
a GUI library in the dependency graph of a package whose main job is file
access.

The cost of that choice is that someone can install PyONDE, run ``ondeview``,
and meet an ImportError about a package they never asked for -- possibly from
a desktop launcher or a file association, with no terminal anywhere to read
the message in.  So :func:`report_missing_matplotlib` writes the explanation
to stderr *and* puts it in a message box, using whatever this machine has:
tkinter from the standard library first, then the platform's own dialog
helper.  Each attempt is allowed to fail; a machine with no way to draw a box
still gets the text.

Set ``ONDEVIEW_NO_DIALOG`` to any non-empty value to suppress the box -- for
unattended runs where a dialog nobody can dismiss would hang the process.
"""

import os
import sys

__all__ = ["MATPLOTLIB_MESSAGE", "MATPLOTLIB_REPORT", "DIALOG_TITLE",
           "require_matplotlib", "report_missing_matplotlib",
           "dialogs_are_possible"]


#: One line, for exceptions -- raised from library calls, where the caller
#: decides how to present it.
MATPLOTLIB_MESSAGE = (
    "the ONDE viewer needs matplotlib, which is not installed and is not a "
    "dependency of PyONDE. Install it with:  pip install matplotlib")

#: The full explanation, for the terminal and the message box.
MATPLOTLIB_REPORT = """\
The ONDE viewer needs matplotlib, which is not installed.

matplotlib is not a dependency of PyONDE, by design: PyONDE itself, and
"ondeview --list" and "ondeview --info", all work without it.  Only the
interactive viewer needs it.

Install it with:

    pip install matplotlib

or, in a conda environment:

    conda install matplotlib
"""

DIALOG_TITLE = "ondeview: matplotlib is required"

#: Suppresses the message box; the text still goes to stderr.
NO_DIALOG_VARIABLE = "ONDEVIEW_NO_DIALOG"


def require_matplotlib():
    """Import and return :mod:`matplotlib.pyplot`, or raise a useful ImportError."""
    try:
        import matplotlib.pyplot as pyplot
    except ImportError as err:
        raise ImportError(MATPLOTLIB_MESSAGE) from err
    return pyplot


def dialogs_are_possible():
    """Whether it is worth trying to draw a message box at all.

    A box nobody can see is worse than none: on a headless machine the attempt
    costs a subprocess or an X connection timeout, and a dialog that does open
    where nobody can dismiss it blocks the process indefinitely.
    """
    if os.environ.get(NO_DIALOG_VARIABLE):
        return False
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _show_with_tkinter(title, text):
    """The standard library's own dialog -- present wherever Tk is."""
    import tkinter
    from tkinter import messagebox

    root = tkinter.Tk()
    root.withdraw()
    try:
        messagebox.showerror(title, text)
    finally:
        root.destroy()
    return True


def _show_with_windows_api(title, text):
    import ctypes

    MB_OK_ICONERROR = 0x00000010
    # MessageBoxW returns the id of the button pressed, or zero if the box
    # could not be created.
    return bool(ctypes.windll.user32.MessageBoxW(None, text, title,
                                                 MB_OK_ICONERROR))


def _ran_and_drew_something(argv):
    """Run a dialog helper and say whether it actually put a box on screen.

    The exit status alone cannot tell us: a helper returns non-zero both when
    the user dismissed the box with the window manager rather than its button,
    and when it could not reach a display at all.  The two are told apart by
    stderr -- a toolkit that cannot open a display says so there ("cannot open
    display", "could not connect"), while a box the user closed is silent.

    Guessing wrong in the optimistic direction is the expensive one: claiming
    a box was drawn stops the caller trying the backends after this one, so
    the message reaches nobody.
    """
    import subprocess

    try:
        completed = subprocess.run(argv, check=False, capture_output=True)
    except OSError:
        return False
    if completed.returncode == 0:
        return True
    return not completed.stderr.strip()


def _show_with_osascript(title, text):
    import json

    script = (f"display dialog {json.dumps(text)} with title "
              f"{json.dumps(title)} buttons {{\"OK\"}} default button \"OK\" "
              f"with icon caution")
    return _ran_and_drew_something(["osascript", "-e", script])


def _show_with_desktop_helper(title, text):
    """zenity or kdialog -- the usual way out on a Linux box without Tk.

    Several distributions package tkinter separately (python3-tkinter on
    Fedora, python3-tk on Debian), so a perfectly ordinary desktop Python can
    be without it while the desktop itself has a dialog helper.
    """
    import shutil

    candidates = (
        ("zenity", lambda program: [program, "--error", f"--title={title}",
                                    f"--text={text}"]),
        ("kdialog", lambda program: [program, "--title", title,
                                     "--error", text]),
    )
    for name, build in candidates:
        program = shutil.which(name)
        if program is None:
            continue
        if _ran_and_drew_something(build(program)):
            return True
        # On PATH but unable to draw -- a display it cannot reach, most
        # likely.  Try the next helper rather than reporting success.
    return False


def _dialog_backends():
    """In order of preference; the first that draws a box wins.

    tkinter leads because it is the standard library and needs no desktop
    environment in particular.  The rest are per-platform fallbacks, each
    returning False when it is not applicable here.
    """
    backends = [("tkinter", _show_with_tkinter)]
    if sys.platform.startswith("win"):
        backends.append(("windows", _show_with_windows_api))
    elif sys.platform == "darwin":
        backends.append(("osascript", _show_with_osascript))
    else:
        backends.append(("desktop-helper", _show_with_desktop_helper))
    return backends


def report_missing_matplotlib(stream=None, dialog=True):
    """Explain the missing dependency on *stream*, and in a box if one is possible.

    Returns the name of the mechanism that drew the box, or None when none
    did -- which is not an error, and is the expected answer on a headless
    machine.
    """
    print("error: " + MATPLOTLIB_REPORT,
          file=sys.stderr if stream is None else stream)
    if not dialog or not dialogs_are_possible():
        return None
    for name, show in _dialog_backends():
        try:
            if show(DIALOG_TITLE, MATPLOTLIB_REPORT):
                return name
        except Exception:
            # Every one of these can fail for reasons that are not the user's
            # problem -- no Tk, no display after all, a helper that is on PATH
            # but broken.  Try the next; the text is already out.
            continue
    return None
