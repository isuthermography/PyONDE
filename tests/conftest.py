"""Shared fixtures for the viewer tests.

The synthetic files are written once per test session; they are small (a few MB
in total) and writing them exercises PyONDE's writer as a side effect.
"""

import pytest

from PyONDE.viewer import testdata
from PyONDE.viewer.model import OndeDocument


@pytest.fixture(scope="session")
def onde_files(tmp_path_factory):
    """{name: path} for every synthetic file."""
    directory = tmp_path_factory.mktemp("onde")
    return testdata.write_all(directory)


@pytest.fixture(scope="session")
def ascan_document(onde_files):
    with OndeDocument.open(onde_files["ascan"]) as document:
        yield document


@pytest.fixture(scope="session")
def tscan_document(onde_files):
    with OndeDocument.open(onde_files["tscan"]) as document:
        yield document


@pytest.fixture(scope="session")
def cscan_document(onde_files):
    with OndeDocument.open(onde_files["cscan"]) as document:
        yield document


@pytest.fixture(scope="session")
def hostile_document(onde_files):
    with OndeDocument.open(onde_files["hostile"]) as document:
        yield document


@pytest.fixture(scope="session")
def ascan_model(ascan_document):
    return ascan_document.datasets[0]


def hostile_dataset(document, label_fragment):
    """Find a hostile-file dataset by a fragment of its label."""
    for model in document.datasets:
        if label_fragment.lower() in model.label.lower():
            return model
    raise AssertionError(f"no dataset labeled like {label_fragment!r}")
