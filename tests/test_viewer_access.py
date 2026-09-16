"""Tests for PyONDE.viewer.access.

Each test here pins one PyONDE API behavior the viewer depends on.  If PyONDE
changes such that a test fails, the access layer -- not the rest of the viewer
-- is what needs updating.
"""

import numpy as np
import pytest

from PyONDE.viewer import access


def test_field_accepts_short_and_full_names(ascan_model):
    dataset = ascan_model.dataset
    assert access.field(dataset, "DATA") is not None
    assert access.field(dataset, "ONDE_DATASET:DATA") is not None


def test_field_missing_returns_default(ascan_model):
    dataset = ascan_model.dataset
    # A field that is known to the class definitions but unset:
    assert access.field(dataset, "ONDE_DATASET_UT_TSCAN:ZONE_FRAME", "fallback") \
        == "fallback"
    # A field belonging to a class PyONDE has never heard of:
    assert access.field(dataset, "MYORG_ACCESSORY:WHATEVER", None) is None


def test_field_value_unwraps(ascan_model):
    label = access.field_value(ascan_model.dataset, "LABEL")
    assert isinstance(label, str)
    data = access.field_value(ascan_model.dataset, "DATA")
    assert isinstance(data, np.ndarray)


def test_unwrap_passes_through_plain_values():
    assert access.unwrap(None, "default") == "default"
    assert access.unwrap("text") == "text"
    array = np.arange(3)
    assert access.unwrap(array) is array


def test_stored_arrays_are_read_only(ascan_model):
    """PyONDE freezes arrays; anything modifying data must copy first."""
    data = access.field_value(ascan_model.dataset, "DATA")
    assert not data.flags.writeable


def test_ref_len_and_ref_list(ascan_model):
    """ONDEReferenceArray has no usable .shape; ref_len reaches its length."""
    dimensions = access.field(ascan_model.dataset, "INDEX_DIMENSIONS")
    with pytest.raises(Exception):
        _ = dimensions.shape          # the behavior ref_len exists to work around
    assert access.ref_len(dimensions) == 4
    entries = access.ref_list(dimensions)
    assert len(entries) == 4
    assert access.field_value(entries[0], "COORDINATE") == "U Position"


def test_ref_len_of_none_is_zero():
    assert access.ref_len(None) == 0
    assert access.ref_list(None) == []


def test_type_chain_is_the_whole_inheritance_chain(ascan_model):
    chain = access.type_chain(ascan_model.dataset)
    assert chain == ("ONDE_DATASET", "ONDE_DATASET_UT", "ONDE_DATASET_UT_ASCAN")
    assert access.leaf_type(ascan_model.dataset) == "ONDE_DATASET_UT_ASCAN"


def test_is_a_tests_membership_not_equality(ascan_model):
    """A dataset is an ONDE_DATASET even though its leaf type is the A-scan."""
    assert access.is_a(ascan_model.dataset, "ONDE_DATASET")
    assert access.is_a(ascan_model.dataset, "ONDE_DATASET_UT_ASCAN")
    assert not access.is_a(ascan_model.dataset, "ONDE_DATASET_UT_TSCAN")


def test_dataset_entries_align_keys_with_short_keys(ascan_document):
    entries = access.dataset_entries(ascan_document.onde_file)
    assert len(entries) == 1
    full_key, short_key, dataset = entries[0]
    assert full_key.startswith("2.25.")
    # a short key is a unique prefix of the UUID digits after "2.25."
    assert full_key[5:].startswith(short_key) or short_key == full_key
    assert access.type_chain(dataset)


def test_field_names_lists_populated_fields(ascan_model):
    names = access.field_names(ascan_model.dataset)
    assert "ONDE_DATASET:DATA" in names
    assert "ONDE:UUID" in names
