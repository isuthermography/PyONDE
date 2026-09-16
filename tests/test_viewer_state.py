"""Tests for PyONDE.viewer.state: default views, selectors and state repair."""

import pytest

from PyONDE.viewer.state import ViewState, default_state_for

from conftest import hostile_dataset


# -- default view choice --------------------------------------------------

def test_ascan_opens_as_a_waveform_along_time(ascan_model):
    """The A-scan default falls out of the dimension metadata, not a type check."""
    state = default_state_for(ascan_model)
    assert state.is_waveform
    assert state.x_axis == 3
    assert state.indices == {0: 0, 1: 0, 2: 0}


def test_tscan_opens_as_an_image_over_the_zone(tscan_document):
    model = tscan_document.viewable[0]
    state = default_state_for(model)
    assert state.is_image
    assert state.display_axes == (2, 3)
    assert state.indices == {0: 0, 1: 0}
    assert state.invert_y            # depth increases downward
    assert state.aspect == "equal"   # both axes in meters


def test_cscan_opens_as_a_position_image(cscan_document):
    model = cscan_document.viewable[0]
    state = default_state_for(model)
    assert state.is_image
    assert state.display_axes == (0, 1)
    assert state.aspect == "equal"
    assert state.indices == {2: 0}


def test_degenerate_axes_are_not_chosen_for_display(hostile_document):
    """A 1x1x1xN dataset is a waveform, not a one-pixel image."""
    model = hostile_dataset(hostile_document, "Single A-scan")
    state = default_state_for(model)
    assert state.is_waveform
    assert state.x_axis == 3


def test_dataset_without_data_still_yields_a_state(tscan_document):
    empty = [m for m in tscan_document.datasets if not m.has_data][0]
    state = default_state_for(empty)
    assert state.dataset_key == empty.short_key


# -- selectors ------------------------------------------------------------

def test_selector_fixes_free_axes_and_keeps_display_axes(ascan_model):
    state = default_state_for(ascan_model).evolve(indices={0: 2, 1: 1, 2: 0})
    assert state.selector() == (2, 1, 0, slice(None))
    extracted = ascan_model.slice(state.selector())
    assert extracted.shape == (1000,)


def test_selector_for_an_image_keeps_two_axes(tscan_document):
    model = tscan_document.viewable[0]
    state = default_state_for(model)
    assert state.selector() == (0, 0, slice(None), slice(None))
    assert model.slice(state.selector()).shape == (64, 80)


def test_orient_transposes_when_the_y_axis_comes_later(ascan_model):
    """Mapping a later axis to y means the extracted slice needs transposing."""
    ascending = ViewState(ascan_model.short_key, (1, 3), {0: 0, 2: 0})
    extracted = ascan_model.slice(ascending.selector())
    assert extracted.shape == (4, 1000)
    assert ascending.orient(extracted).shape == (4, 1000)

    descending = ViewState(ascan_model.short_key, (3, 1), {0: 0, 2: 0})
    extracted = ascan_model.slice(descending.selector())
    assert extracted.shape == (4, 1000)          # array order, not screen order
    assert descending.orient(extracted).shape == (1000, 4)


def test_orient_leaves_waveforms_alone(ascan_model):
    state = default_state_for(ascan_model)
    extracted = ascan_model.slice(state.selector())
    assert state.orient(extracted).shape == (1000,)


# -- immutability and repair ---------------------------------------------

def test_state_is_immutable():
    state = ViewState("k", (0,), {})
    with pytest.raises(AttributeError):
        state.cmap = "gray"
    assert state.evolve(cmap="gray").cmap == "gray"
    assert state.cmap == "viridis"


def test_conform_clamps_out_of_range_indices(ascan_model):
    state = ViewState(ascan_model.short_key, (3,), {0: 99, 1: -4, 2: 0})
    conformed = state.conform(ascan_model)
    assert conformed.indices == {0: 2, 1: 0, 2: 0}


def test_conform_fills_in_missing_axes(ascan_model):
    state = ViewState(ascan_model.short_key, (3,), {})
    assert state.conform(ascan_model).indices == {0: 0, 1: 0, 2: 0}


def test_conform_repairs_display_axes_from_another_dataset(ascan_model,
                                                           cscan_document):
    """Switching datasets can invalidate the axis choice wholesale."""
    cscan_model = cscan_document.viewable[0]
    stale = default_state_for(ascan_model).evolve(cmap="gray")
    repaired = stale.conform(cscan_model)
    assert repaired.display_axes == (0, 1)
    assert repaired.dataset_key == cscan_model.short_key
    assert repaired.cmap == "gray"      # user preferences survive the repair


def test_conform_is_a_fixed_point_for_a_valid_state(ascan_model):
    state = default_state_for(ascan_model)
    assert state.conform(ascan_model) == state


def test_equality_compares_every_field():
    left = ViewState("k", (0, 1), {2: 3})
    assert left == ViewState("k", (0, 1), {2: 3})
    assert left != ViewState("k", (0, 1), {2: 4})
