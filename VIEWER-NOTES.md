# ONDE viewer — Phases 0–4, plus toolbar integration

This folder is a complete PyONDE working tree: upstream PyONDE at `5359d8d`
("Fix ONDE_FILETYPE and ONDE_VERSION…") with the viewer applied on top.
The screenshots show a B-scan, a T-scan zone, the export row and the metadata
window.

## Running it here, with no install

```sh
cd /home/sdh4/code/PyONDE-viewer
PYTHONPATH=. python -m pytest tests/test_viewer_*.py              # 167 tests
PYTHONPATH=. python -c "from PyONDE.viewer import testdata; print(testdata.write_all('/tmp/onde'))"
PYTHONPATH=. python -m PyONDE.bin.ondeview --list /tmp/onde/ascan.onde
PYTHONPATH=. python -m PyONDE.bin.ondeview /tmp/onde/ascan.onde   # the viewer
```

That is how I verified this tree before writing it here — a copy of exactly
these files, on PYTHONPATH, with nothing installed.

`pip install -e ".[viewer]"` works too, but only inside a git checkout:
`pyproject.toml` uses setuptools_scm, which needs git metadata to derive a
version. `PyONDE/_version.py` is written here so plain imports work without it;
delete it if you build from a real repo.

## Getting it into your own checkout

Five patches, applied in order:

```sh
cd /path/to/your/PyONDE
git am /home/sdh4/code/PyONDE-viewer/0001-viewer-phase1.patch
git am /home/sdh4/code/PyONDE-viewer/0002-viewer-phase2.patch
git am /home/sdh4/code/PyONDE-viewer/0003-viewer-phase3.patch
git am /home/sdh4/code/PyONDE-viewer/0004-viewer-phase4.patch
git am /home/sdh4/code/PyONDE-viewer/0005-viewer-toolbar.patch
```

Or fetch the five commits with their history from the bundle:

```sh
git remote add viewer /home/sdh4/code/PyONDE-viewer/PyONDE-viewer.bundle
git fetch viewer viewer-phase1
```

Either route brings the `pyproject.toml` (console script + `viewer` extra),
`doc/source/index.rst` and `doc/source/installation.rst` edits along with the
new files, and gives you the `ondeview` command rather than `python -m`.

In the viewer: pick a y axis to switch from waveform to image (time on x plus a
scan axis on y is a B-scan), sliders fix the remaining axes, arrow keys and the
scroll wheel step the active axis, and clicking reads out the value.

## What is here

| File | Purpose |
|---|---|
| `PyONDE/viewer/access.py` | Every PyONDE API sharp edge, isolated in one place |
| `PyONDE/viewer/model.py` | `AxisDescriptor`, `OndeDatasetModel`, `OndeDocument` |
| `PyONDE/viewer/state.py` | `ViewState` — the whole view as immutable data |
| `PyONDE/viewer/render.py` | The Line2D/AxesImage artists, extents, decimation |
| `PyONDE/viewer/controls.py` | The widget column, matplotlib.widgets only |
| `PyONDE/viewer/app.py` | Figure layout, state transitions, canvas events |
| `PyONDE/viewer/blit.py` | Background caching so a slider drag redraws only what moved |
| `PyONDE/viewer/export.py` | CSV/TSV/NPY/NPZ slices and figure saving, in SI units |
| `PyONDE/viewer/inspector.py` | The metadata window: scrollable, filterable text |
| `PyONDE/viewer/testdata.py` | Synthetic A/T/C-scan files + a hostile file built with raw h5py |
| `PyONDE/bin/ondeview.py` | `ondeview` — viewer, `--list`, `--info` |
| `tests/` | 167 tests, including a round-trip check against raw h5py |
| `doc/source/viewer.rst` | Sphinx page |

## Things found in PyONDE along the way

Three are pinned by tests, so they will tell you if they change upstream.

1. **`shortkeys()` never shortens a key that needs its full length.** When the
   candidate prefix equals the whole UUID, the `prefix in full_keys` check counts
   the key a second time, so `num_keys_matching_prefix` is 2 and the loop falls
   through to the unshortened branch. The result is a key that still carries the
   `2.25.` prefix, inconsistent with its shortened siblings. Only bites when two
   UUIDs differ solely in their final digits. The viewer zips `keys()` with
   `shortkeys()` positionally and doesn't care, but you may want to fix it.

2. **A dataset group containing a sub-group cannot be loaded** — `ValueError:
   Unknown h5type Group` — because `enable_hierarchical` is `False` at module
   scope in `onde.py`. The spec says group locations and names are flexible, so a
   conforming vendor file may well nest its `ONDE_DIMENSION` groups inside the
   dataset group that references them. `testdata.write_nested_file` builds such a
   file and `test_nested_groups_are_not_loadable_by_pyonde` pins the current
   behavior; if hierarchical loading is enabled upstream, that test fails and
   becomes a positive one.

3. **`ONDE:TYPE` stored as fixed-length bytes makes a dataset invisible.**
   `_search_h5_for_onde_datasets` compares `attrs["ONDE:TYPE"][0]` against the
   str `"ONDE_DATASET"`, which a `numpy.bytes_` never equals, so the group is not
   recognized as an entry point at all. `access.type_chain` decodes bytes anyway,
   but nothing downstream can help if the loader never finds the group.

Also worth knowing, though not a defect: a dataset group with no `ONDE:UUID`
raises during load and takes the whole file with it, so `ondeview` can only
report such a file, not partially display it.

## Two decisions in Phase 2 worth a look

**Decimation does not move the axis limits.** Above 4000 displayed samples an
axis is strided. The alternative convention — centering each drawn pixel exactly
on the sample it came from — makes the image's extent grow with the stride, so
the axis limits change when you toggle "full res". I kept the extent fixed at the
true axis span instead, which puts the sub-pixel slop in the pixel positions
rather than in the numbers you read off the axis.

**Sliders carry their label and value in an Axes title.** matplotlib draws a
Slider's label to its left and its value to its right, both outside the widget.
In a 16%-wide column they overlap the radio buttons and the plot's y label. The
title sits inside the column, and shows the calibrated position — "U Position
[2] = 2 mm" — rather than a bare index.

## Phase 3 notes

**Exports are in SI units, not display units.** The time axis is labeled in
microseconds on screen; the CSV says seconds. Anything else would make an
exported slice disagree with the ONDE file it came from. Text exports carry a
`#` header with the dataset UUID, source file, amplitude calibration and every
axis position, so a slice that ends up in someone's script is still traceable.

**The export controls are in a row under the plot, not in the left column.** The
column is allocated top-down and returns nothing when it runs out of room, so on
a high-rank dataset the last controls built would silently not exist — and those
must not be the export buttons.

**Typing a filename no longer drives the viewer.** matplotlib delivers
keystrokes to a focused TextBox *and* to every other key handler, so before the
guard, typing `finished.csv` stepped sliders (`f`, `i`) and flipped toggles.

## Phase 4 notes

**Blitting: 62 ms → 4 ms per step (waveform), 87 ms → 21 ms (image)**, measured
on a 20×20×4×4000 file. Turn it off with `OndeViewerApp(blit=False)` if it ever
misbehaves on your backend.

**Limits now come from the whole dataset, not the slice on screen.** This began
as a prerequisite — per-slice limits change the axes on every step, which
defeats blitting outright — but it is the better default anyway: amplitudes stay
comparable as you step across a scan instead of the axis rescaling under you.
The new "per slice" toggle restores the old behavior. This is the change most
worth disagreeing with if your instinct differs.

**Two things had to move for blitting to be worth anything.** The fixed-index
caption moved from the Axes title into the Axes, because only artists inside the
blitted region can be redrawn cheaply. And the suggested filename is no longer
rewritten as the sliders move: profiling showed `TextBox.set_val` redrawing the
whole canvas at 110 ms per step, more than the plot cost. It is regenerated when
you save, so the file still carries the indices it was saved at.

**The animated-artist trap.** Artists that blit are skipped by every ordinary
draw, `savefig` included — a saved figure would have come out missing its trace.
Saving un-animates them first, and a test reads the PNG back and checks the plot
area is not blank.

## The matplotlib toolbar

It was already there — every interactive backend adds one, and matplotlib
already marks widget axes non-navigable, so pan and zoom only ever grabbed the
plot. What was missing was cooperation:

- **A zoom now survives stepping through the data.** The viewer was re-applying
  computed limits on every update, throwing the navigation away. It now notices
  the limits are no longer its own and leaves them; Home hands control back.
- **The toolbar's Save button produced a figure with an empty plot box**, since
  it saves by the ordinary draw route and blitting marks the moving artists
  `animated`. Its `save_figure` is now wrapped in the same `static()` context
  the viewer's own save uses.
- The colorbar is marked non-navigable, and clicks are ignored while pan or zoom
  is active so starting a drag doesn't also print a readout.

Verified against a real `NavigationToolbar2` driven over the Agg canvas — zoom,
step, Home — not just a stand-in.

## Next

Phase 5, deferred by your call: the UT-specific layouts — linked A/B/C-scan
panels with a shared cursor, T-scan zone geometry from ZONE_DIMENSION, C-scan
positioning from CSCAN_GRID, and the interactive gate/extraction and
rectification/envelope work that was kept out of v1.
