# ONDE viewer — Phases 0–4, toolbar integration, ONDE v0.9.2

This folder is a complete PyONDE working tree: upstream PyONDE at `66caad2`
("Better robustness in handling numpy types") with the viewer applied on
top, reading ONDE v0.9.2.
The screenshots show a B-scan, a T-scan zone, the export row and the metadata
window.

## Running it here, with no install

```sh
cd /home/sdh4/code/PyONDE-viewer
PYTHONPATH=. python -m pytest tests/test_viewer_*.py              # 197 tests
PYTHONPATH=. python -c "from PyONDE.viewer import testdata; print(testdata.write_all('/tmp/onde'))"
PYTHONPATH=. python -m PyONDE.bin.ondeview --list /tmp/onde/ascan.onde
PYTHONPATH=. python -m PyONDE.bin.ondeview /tmp/onde/ascan.onde   # the viewer
```

That is how I verified this tree before writing it here — a copy of exactly
these files, on PYTHONPATH, with nothing installed.

`pip install -e .` works too, but only inside a git checkout:
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

Either route brings the `pyproject.toml` (the `ondeview` console script),
`doc/source/index.rst` and `doc/source/installation.rst` edits along with the
new files, and gives you the `ondeview` command rather than `python -m`.

In the viewer: pick a y axis to switch from waveform to image (time on x plus a
scan axis on y is a B-scan), sliders fix the remaining axes, arrow keys and the
scroll wheel step the active axis, and clicking reads out the value.

## What is here

| File | Purpose |
|---|---|
| `PyONDE/viewer/access.py` | Every PyONDE API sharp edge, isolated in one place |
| `PyONDE/viewer/dependency.py` | The missing-matplotlib message, on stderr and in a box |
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
| `tests/` | 197 tests, including a round-trip check against raw h5py |
| `doc/source/viewer.rst` | Sphinx page |

## Two bugs in the v0.9.2 PyONDE update — both now fixed upstream

Both were found by running the new library against the corpus, and both are
fixed in `a6be485` and `66caad2`; the suite passes on stock upstream with
nothing applied.

1. **`shortkeys()` sliced at the old prefix length.** `3fb8328` changed the UUID
   prefix to `urn:uuid:` and updated `_get_item()`, but `shortkeys()` kept the
   literal 5 from `"2.25."`, so short keys came back as `uid:aaaaaaaa-…` — four
   characters of the prefix still attached — and could not be fed back:
   `_get_item()` prepends `urn:uuid:` and searched for `urn:uuid:uid:…`. Fixed
   with a `UUID_prefix` constant used everywhere a prefix is sliced.
   `test_short_keys_can_be_fed_back_to_the_graph` is what notices a regression.

2. **A scalar integer attribute could not be read back.** h5py returns scalar
   attributes as numpy scalars; `np.float64` subclasses `float` so it slipped
   through, but `np.int64` does not subclass `int`, so an `H5T_INTEGER` field of
   dimension 1 fell through every branch in `load_from_hdf5` and raised
   `Unknown hdf5 attribute type: int64`. `REFERENCE_PROBE_INDEX` on the new
   reconstruction setup was the first field to hit it. Fixed by accepting
   `np.integer`, so `write_tscan_file` carries `REFERENCE_PROBE_INDEX` again
   and the corpus exercises the path.

### Scalar attribute types, and the ones still outside the net

`a6be485` added `np.integer`; `66caad2` added `np.float32`, `np.float64`,
`bool` and `np.bool_`. Between them that covers every scalar type the corpus
and any ordinary acquisition system produce, and each reads back as the plain
Python equivalent:

| written as | read back |
|---|---|
| `np.int64`, `np.int32`, `np.uint8` | `int` |
| `np.float32`, `np.float64` | `float` |
| `np.bool_` | `bool` |
| `np.float16`, `np.longdouble`, `np.complex128` | `ValueError: Unknown hdf5 attribute type` |

The last row is the enumeration's remaining edge. None of them is plausible in
an ONDE file today — h5py widens Python floats to float64, and a complex
amplitude would be an array rather than a scalar attribute — so this is a note
rather than a defect. If one ever does turn up, the whole file fails to load,
not just that field, and the general form of the fix is to convert any
`np.generic` with `.item()` at the boundary where fixed-length strings are
decoded, instead of listing the types that pass.

`test_narrow_scalar_attributes_behave_per_library_capability` probes the
library rather than assuming it, so the suite reads correctly on both sides of
that change: it asserts the value round-trips where the type is accepted, and
that `ondeview` reports a readable error rather than a traceback where it is
not.

## PyONDE behaviors the viewer lives with

**Fixed-length (bytes) strings — fixed upstream in `39214f6`.** PyONDE now
decodes them at load, so `ONDE:TYPE`, `ONDE:LABEL` and the rest arrive as `str`
whatever the writer produced. `testdata.write_bytestype_file` builds such a file
and the tests read it unconditionally; `access.type_chain` still decodes on its
own, so the viewer does not depend on that.

One note for the record: between `50e8c49` and `39214f6` this case was worse
than before the first fix — discovery accepted bytes while `add()` still
compared against `str`, so one such group aborted the load of the entire file
rather than being skipped. That is why the case lives in a file of its own, and
why `write_nested_file` does too.

**`shortkeys()` returning a key at full length is by design.** When no prefix of
a UUID is unique — the hostile file's keys differ only in their last digit —
there is no meaningful short form, so the key is not shortened (it just loses
the `2.25.` every key shares). The viewer never reconstructs one key from the
other; it zips `keys()` with `shortkeys()` positionally, so a long short key
addresses its dataset like any other. The dataset selector leads with the
label and only falls back to the key's last four characters to disambiguate,
which is what keeps a column of near-identical UUIDs readable.

**Hierarchical files are waiting on a specification update.** A dataset group
containing a sub-group raises `Unknown h5type Group` while
`enable_hierarchical` stays `False`. `testdata.write_nested_file` builds one and
the test branches on the flag, so the suite keeps passing on both sides of that
change.

Also worth knowing, though not a defect: a dataset group with no `ONDE:UUID`
raises during load and takes the whole file with it, so `ondeview` can only
report such a file, not partially display it.

## Following the specification version

The default is the fixed constant `access.DEFAULT_ONDE_VERSION = "0.9.2"` — a
decision rather than "whatever is newest installed", since that would make
field-name resolution depend on which PyONDE someone happens to have. Bump the
constant when the viewer has been checked against a newer set; `--onde-version`
overrides it per run, and asking for definitions PyONDE does not ship says so
instead of surfacing a `FileNotFoundError` naming a CSV inside the package.

**What v0.9.2 changed, and what it cost here:**

- `SENSOR_LIST` → `PROBE_LIST`, `FRAME` → `INDEX_POINT_FRAME`. The generator
  writes the new names; nothing in the viewer itself names either.
- The T-scan's `ZONE_FRAME`, `ZONE_DIMENSION`, `ZONE_SIZE`,
  `RECONSTRUCTION_MODE` and `REFERENCE_PROBE_INDEX` moved into a separate
  `ONDE_UT_RECONSTRUCTION_SETUP`, referenced by `RECONSTRUCTION_SETUP`.
  `write_tscan_file` follows; the viewer reads the zone through the metadata
  window either way, since it never depended on those fields to draw.
- UUIDs became `urn:uuid:<hyphenated hex>`. The viewer treats them as opaque
  strings, as the specification instructs — see "Older files" in `viewer.rst`.
- `DATE_AND_TIME` and the UUID now come from one aware timestamp
  (`datetime.now().astimezone()`), since `generate_onde_uuid` hashes the ISO
  rendering.

The corpus is now written at 0.9.2, with one file —
`testdata.write_legacy_file` — deliberately written the old way (SENSOR_LIST,
FRAME, a `2.25.` UUID) so every run still exercises reading an older
acquisition. A parametrized test reads each file under every available version
and asserts the label, shape, type chain, axis calibration and samples come out
identical.

## matplotlib is not a dependency, in any form

Not required, and no longer an extra either: `pyproject.toml` does not mention
matplotlib at all, and `pip install PyONDE[viewer]` is gone. A package whose
job is file access should not put a plotting library in anyone's dependency
graph, and the only thing an extra bought was a name to put in an error
message.

What replaces it is `PyONDE/viewer/dependency.py`. `require_matplotlib()`
still raises a one-line `ImportError` for library callers, who decide how to
present it. `ondeview` instead calls `report_missing_matplotlib()`, which
writes the full explanation to stderr **and puts it in a message box**, then
exits 3.

The box matters because the viewer is the one command that may be started
from a desktop launcher or a file association, where stderr goes nowhere. It
is drawn by the first mechanism that works:

1. **tkinter**, from the standard library — no desktop environment assumed;
2. **the platform's own helper** — `zenity` or `kdialog` on Linux,
   `osascript` on macOS, `MessageBoxW` through ctypes on Windows.

Two is not redundancy for its own sake: several distributions package tkinter
separately (`python3-tkinter` on Fedora, `python3-tk` on Debian), so an
ordinary desktop Python can be without it while the desktop has a dialog
helper standing by. Every attempt may fail, and when they all do the text has
already gone to stderr.

No box is attempted without somewhere to draw it — `DISPLAY` or
`WAYLAND_DISPLAY` on Linux, always on Windows and macOS — because a dialog
nobody can dismiss blocks the process. `ONDEVIEW_NO_DIALOG=1` suppresses it
outright, which is what scripts and CI should set.

`test_viewer_optional_dependency.py` covers this in three layers: subprocesses
with matplotlib blocked at the import hook, for what the user actually
meets; stand-in backends, for the fallback order and the display rules; and
one test that runs the real backends against a display that does not exist,
which is the path that must not raise, hang, or lose the message. A further
test parses `pyproject.toml` and fails if matplotlib reappears in it.

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
