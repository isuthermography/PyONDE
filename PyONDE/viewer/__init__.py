"""Viewer for ONDE data files.

The model layer (:mod:`PyONDE.viewer.access`, :mod:`PyONDE.viewer.model`,
:mod:`PyONDE.viewer.state`) is pure Python and numpy and is always importable.
The interactive viewer additionally needs matplotlib, which ships as an optional
extra::

    pip install PyONDE[viewer]

so nothing here imports matplotlib at module scope.  :func:`view_onde_file`
imports it lazily and raises a readable error when the extra is absent.
"""

from .model import AxisDescriptor, OndeDatasetModel, OndeDocument
from .state import ViewState, default_state_for

__all__ = ["AxisDescriptor", "OndeDatasetModel", "OndeDocument",
           "ViewState", "default_state_for", "view_onde_file", "view_document",
           "require_matplotlib"]


def require_matplotlib():
    """Import and return matplotlib.pyplot, or raise a useful ImportError."""
    try:
        import matplotlib.pyplot as pyplot
    except ImportError as err:
        raise ImportError(
            "the ONDE viewer needs matplotlib, which is an optional dependency "
            "of PyONDE. Install it with:  pip install PyONDE[viewer]") from err
    return pyplot


def view_onde_file(path, onde_version="0.9.1pre", dataset=None, show=True):
    """Open *path* in the interactive viewer; returns the application object.

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
