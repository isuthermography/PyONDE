"""The PyONDE behaviours the model layer reads ONDE files through.

This file used to test PyONDE.viewer.access, a layer of defensive accessors
that stood between the model and the library.  That layer is gone: PyONDE
answers these questions itself now, and the model calls it directly.  What is
pinned here is therefore the library's own read API, in the shapes the viewer
depends on -- if one of these fails, the model layer is what needs updating,
and the viewer stops being a usable example of reading an ONDE file.
"""

import numpy as np
import pytest

from PyONDE.onde import ONDEReferenceArray


# -- reading a field ------------------------------------------------------

def test_field_value_takes_short_and_qualified_names(ascan_model):
    dataset = ascan_model.dataset
    assert dataset._field_value("DATA") is not None
    assert dataset._field_value("ONDE_DATASET:DATA") is not None


def test_field_value_unwraps_what_it_returns(ascan_model):
    """The common case comes back as data, not as a handle to unwrap."""
    assert isinstance(ascan_model.dataset._field_value("LABEL"), str)
    assert isinstance(ascan_model.dataset._field_value("DATA"), np.ndarray)


def test_a_field_holding_a_node_comes_back_as_a_handle(ascan_model):
    """There is no value to take, and the caller wants to keep navigating."""
    setup = ascan_model.dataset._field_value("SETUP")
    assert setup._field_value("ONDE_SETUP:GEOMETRIC_SETUP") is not None


def test_an_absent_declared_field_gives_the_default(ascan_model, tscan_document):
    """How the spec's optional fields are read, calibration included."""
    dimension = list(ascan_model.dataset._field_value("INDEX_DIMENSIONS"))[0]
    assert dimension._field_value("SCALE", 1.0) == pytest.approx(0.001)
    # OPERATOR is declared for ONDE_DATASET and left out of these datasets.
    absent = tscan_document.datasets[0].dataset
    assert not absent._has_attr("ONDE_DATASET:OPERATOR")
    assert absent._field_value("OPERATOR", "fallback") == "fallback"


def test_a_field_of_a_different_class_is_a_mistake_not_an_absence(ascan_model):
    """ZONE_FRAME belongs to a T-scan; asking an A-scan for it is an error.

    This is the discrimination that makes a default safe to rely on: it is
    offered only where the field could legitimately have been present.
    """
    with pytest.raises(NameError):
        ascan_model.dataset._field_value("ONDE_DATASET_UT_TSCAN:ZONE_FRAME",
                                         "fallback")


def test_a_name_that_is_neither_carried_nor_declared_is_an_error(ascan_model):
    """The distinction the viewer relies on: absence versus mistake.

    A typo, or a field renamed between specification versions, must not read
    as data that is legitimately missing.
    """
    with pytest.raises(NameError):
        ascan_model.dataset._field_value("TOTAL_NONSENSE", "fallback")
    with pytest.raises(AttributeError):
        ascan_model.dataset.TOTAL_NONSENSE
    assert not hasattr(ascan_model.dataset, "TOTAL_NONSENSE")


def test_stored_arrays_are_read_only(ascan_model):
    """PyONDE freezes arrays; anything modifying data must copy first."""
    data = ascan_model.dataset._field_value("DATA")
    assert not data.flags.writeable


# -- reference arrays -----------------------------------------------------

def test_a_reference_array_is_a_container(ascan_model):
    """.shape is the size; len() and iteration are there for ordinary code.

    This replaces a test that pinned the opposite -- that .shape raised, which
    is why the viewer once reached into refs._shape[0] for a length.
    """
    dimensions = ascan_model.dataset._field_value("INDEX_DIMENSIONS")
    assert isinstance(dimensions._get_obj(), ONDEReferenceArray)
    assert dimensions.shape == (4,)
    assert len(dimensions) == 4
    entries = list(dimensions)
    assert len(entries) == 4
    assert entries[0]._field_value("COORDINATE") == "U Position"


# -- the type chain -------------------------------------------------------

def test_the_type_chain_is_the_whole_inheritance_chain(ascan_model):
    assert ascan_model.type_chain == ("ONDE_DATASET", "ONDE_DATASET_UT",
                                      "ONDE_DATASET_UT_ASCAN")
    assert ascan_model.leaf_type == "ONDE_DATASET_UT_ASCAN"


def test_is_a_tests_membership_not_equality(ascan_model):
    """A dataset is an ONDE_DATASET even though its leaf type is the A-scan.

    _onde_class_name answers with the base of the chain, which is why the
    viewer reads ONDE:TYPE itself rather than using it for dispatch.
    """
    assert ascan_model.is_a("ONDE_DATASET")
    assert ascan_model.is_a("ONDE_DATASET_UT_ASCAN")
    assert not ascan_model.is_a("ONDE_DATASET_UT_TSCAN")
    assert ascan_model.dataset._onde_class_name == "ONDE_DATASET"


# -- enumerating what an object holds -------------------------------------

def test_list_attrs_reports_qualified_names(ascan_model):
    names = ascan_model.dataset._list_attrs()
    assert "ONDE_DATASET:DATA" in names
    assert "ONDE:UUID" in names


def test_membership_agrees_with_what_is_there(ascan_model):
    dataset = ascan_model.dataset
    assert "ONDE_DATASET:DATA" in dataset
    assert "DATA" in dataset
    assert "TOTAL_NONSENSE" not in dataset


# -- the graph ------------------------------------------------------------

def test_the_graph_pairs_its_keys_with_its_datasets(ascan_document):
    """items() and shortkeys() are what the document is built from."""
    graph = ascan_document.onde_file.graph
    assert len(graph) == 1
    items = graph.items()
    shortkeys = graph.shortkeys()
    assert len(items) == len(shortkeys) == 1

    (full_key, dataset) = items[0]
    short_key = shortkeys[0]
    assert full_key.startswith("urn:uuid:")      # the ONDE v0.9.2 UUID form
    # A short key is a unique leading piece of the UUID with its scheme prefix
    # removed -- "urn:uuid:" since ONDE v0.9.2, "2.25." before it -- so rather
    # than hardcoding either, check it appears in the full key.
    assert short_key in full_key
    assert dataset._field_value("ONDE:TYPE") is not None

    # shortitems() pairs them inside the library, so a caller never has to
    # rely on the two listings being in the same order.
    (paired_short_key, paired_dataset) = graph.shortitems()[0]
    assert paired_short_key == short_key
    assert paired_dataset._get_obj() is dataset._get_obj()
