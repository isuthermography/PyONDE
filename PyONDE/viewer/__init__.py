"""Viewer for ONDE data files.

The model layer (:mod:`PyONDE.viewer.access`, :mod:`PyONDE.viewer.model`,
:mod:`PyONDE.viewer.state`) is pure Python and numpy and is always importable.
The interactive viewer additionally needs matplotlib, which PyONDE does not
declare as a dependency at all -- not required, and not an extra::

    pip install matplotlib

so nothing here imports matplotlib at module scope.  :func:`view_onde_file`
imports it lazily and raises a readable error when it is absent;
:func:`~PyONDE.viewer.dependency.report_missing_matplotlib`, which ``ondeview``
uses, additionally puts that error in a message box for anyone who started the
viewer without a terminal to read it in.
"""

from .dependency import (MATPLOTLIB_MESSAGE, report_missing_matplotlib,
                         require_matplotlib)
from .model import AxisDescriptor, OndeDatasetModel, OndeDocument
from .state import ViewState, default_state_for

__all__ = ["AxisDescriptor", "OndeDatasetModel", "OndeDocument",
           "ViewState", "default_state_for", "view_onde_file", "view_document",
           "require_matplotlib", "report_missing_matplotlib",
           "MATPLOTLIB_MESSAGE"]


def view_onde_file(path, onde_version=None, dataset=None, show=True):
    """Open *path* in the interactive viewer; returns the application object.

    *onde_version* defaults to
    :data:`PyONDE.viewer.access.DEFAULT_ONDE_VERSION`.

    With *show* true this blocks until the window is closed, under an
    interactive backend.  From IPython or a notebook, pass ``show=False`` and
    keep the returned object -- dropping the last reference to it lets the
    widgets be garbage collected, at which point they stop responding.
    """
    require_matplotlib()
    document = OndeDocument.open(path, onde_version=onde_version)
    application = view_document(document, dataset=dataset, show=show)
    return application


def view_document(document, dataset=None, show=True, **kwargs):
    """Open an already-loaded :class:`OndeDocument` in the viewer."""
    from .app import OndeViewerApp
    application = OndeViewerApp(document, dataset_key=dataset, **kwargs)
    if show:
        application.show()
    return application
