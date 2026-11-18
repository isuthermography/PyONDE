Viewer
======

``PyONDE.viewer`` provides a dimension-driven view of the data in an ONDE file,
plus the ``ondeview`` command line tool.  The interactive front end is built
entirely on matplotlib and ``matplotlib.widgets``, with no other GUI toolkit.

Installation
------------

matplotlib is not declared as a dependency of PyONDE at all -- neither
required nor an extra -- because the library, the model layer described below,
and ``ondeview --list`` / ``ondeview --info`` all work without it.  Only the
interactive viewer needs it, so install it yourself when you want one::

  pip install matplotlib

If you open the viewer without it, ``ondeview`` says so and exits with status
3.  It writes that message to standard error *and* puts it in a message box,
because the viewer is the one command likely to be started from a desktop
launcher or a file association, where there is no terminal to read it in.  The
box is drawn with tkinter if that is installed, otherwise with the platform's
own dialog helper (``zenity`` or ``kdialog`` on Linux, ``osascript`` on macOS,
``MessageBoxW`` on Windows); if none of them can draw one, the message still
reaches standard error.  Set ``ONDEVIEW_NO_DIALOG=1`` to suppress the box
entirely, which is worth doing in scripts and CI, where a dialog nobody can
dismiss would hang the run.

Command line
------------

List the datasets in a file::

  $ ondeview --list scan.onde
  scan.onde
    ONDE:VERSION 0.9.2   ONDE:FILETYPE ONDE_UT   read with class definitions 0.9.2
         key  type                     shape                        label
        3075  ONDE_DATASET_UT_ASCAN    3x4x2x1000 float64           Synthetic A-scan raster

Describe one dataset -- its axes, their calibration, and the metadata subgraph
reached from the entry point::

  $ ondeview --info 3075 scan.onde

Open the interactive viewer::

  $ ondeview scan.onde
  $ ondeview --dataset 3075 scan.onde      # start on a particular dataset

An interactive matplotlib backend is required; ``ondeview`` says so rather than
opening nothing if the current backend cannot show a window::

  $ MPLBACKEND=QtAgg ondeview scan.onde

``--onde-version`` selects which class definitions PyONDE compiles in.  It
controls which fields are known by their short names, not what the file is
required to contain: a file written under a different version of the
specification still loads, its data is identical either way, and its unfamiliar
fields remain reachable by their fully qualified ``CLASS:FIELD`` names.  (v0.9.2
renamed ``SENSOR_LIST`` to ``PROBE_LIST`` and ``FRAME`` to
``INDEX_POINT_FRAME``, for instance, so an older file read with 0.9.2
definitions carries fields the definitions do not know -- and the metadata
window still shows them.)

The default is ``0.9.2`` (``PyONDE.viewer.access.DEFAULT_ONDE_VERSION``),
fixed deliberately rather than derived from whichever definitions happen to be
installed: which definitions are in force decides how field names resolve, so it
should be a decision rather than a side effect of a PyONDE release.  Bump the
constant once the viewer has been checked against a newer set.  ``ondeview
--list`` reports which set it read with, and asking for definitions PyONDE does
not ship is reported as such rather than as a missing file.

The file's ``ONDE:FILETYPE`` tags are reported in that same line, but nothing
is required of them.  PyONDE lets a reader demand tags -- it raises if one is
missing -- and the viewer deliberately demands none, because whether a file is
worth opening depends on whether it holds a dataset that can be displayed, not
on how it is labelled; requiring ``ONDE_UT`` would shut the viewer out of a
conforming file from another modality.  Callers who do want the check can pass
``filetype=`` to :func:`PyONDE.viewer.access.open_onde_file`, which forwards it
to PyONDE only when given::

  from PyONDE.viewer import access
  onde_file = access.open_onde_file("scan.onde", filetype={"ONDE_UT"})

Writing is the other way round: since PyONDE v0.1.7 the tags are mandatory when
a file is created, which is why ``PyONDE.viewer.testdata`` passes
``{"ONDE_DATASET", "ONDE_UT"}`` for the synthetic corpus.

Using the viewer
----------------

The viewer is dimension-driven: it shows the DATA array of one dataset, with one
or two axes mapped to the display and every other axis fixed by a slider.  What
opens by default follows from the dimension metadata rather than from the
dataset type -- a long time axis becomes a waveform, two long spatial axes
become an image -- so an A-scan file opens as an A-scan and a T-scan file as a
zone image without either being a special case.

Controls, down the left of the window:

  ``dataset``       which dataset to show (prev/next buttons past eight)
  ``x axis``        the axis along the horizontal
  ``y axis``        the axis along the vertical, or "none" for a waveform
  index sliders     one per remaining axis, labeled with the calibrated position
  ``colormap``      image colormap
  ``value limits``  explicit color (or amplitude) limits
  toggles           auto limits, per slice, equal aspect, invert y, full res

Choosing a y axis of the time axis and an x axis of a scan axis gives a B-scan;
two scan axes give a C-scan-shaped view of whatever the third axis is fixed at.

Keyboard and mouse, over the plot:

  ``left``/``right``        step the active axis by one
  ``shift`` + those         step by ten
  ``up``/``down``           change which axis is active
  ``pgup``/``pgdn``         previous/next dataset
  scroll wheel              step the active axis (also works over a slider)
  click                     read out the value under the pointer
  ``a`` ``s`` ``e`` ``i`` ``f``
                            auto limits, per slice, equal aspect, invert y,
                            full resolution

Amplitude and color limits are taken from the **whole dataset** by default, not
from the slice on screen, so amplitudes stay comparable as you step across a
scan and the axis does not jump under you.  Tick "per slice" to rescale to each
slice instead, or untick "auto limits" and set them by hand with the value
limits slider.

Long axes are decimated for display above 4000 samples, which keeps slider drags
responsive on large datasets; the title says so when it is in effect and the
"full res" toggle disables it.  Decimation never moves the axis limits -- a
decimated image covers the same span, with coarser pixels.

The matplotlib toolbar
----------------------

The backend's own navigation toolbar is present as usual, and works on the plot:
pan, box zoom, back/forward, Home, and Save.  The viewer makes room for it
rather than replacing it, and three things are arranged so the two do not fight:

* Only the plot answers to pan and zoom.  Every control is an Axes too, and
  matplotlib already marks widget axes non-navigable; the colorbar is marked
  non-navigable here for the same reason.
* **A pan or zoom survives stepping through the data.**  The viewer notices that
  the limits are no longer the ones it set and stops re-applying its own, so you
  can zoom into a time window and walk across the scan inside it.  Anything
  structural -- a different dataset, axis, or mode, or new value limits --
  starts a new view with computed limits, and the toolbar's **Home** button
  hands control back to the automatic limits.
* Saving from the toolbar produces a complete figure.  Blitting marks the moving
  artists ``animated``, which ordinary draws skip, so the viewer un-marks them
  around the toolbar's save just as it does around its own.

While the pan or zoom tool is active, clicking in the plot does not also print a
value readout.

Exporting
---------

The row under the plot holds a filename and three buttons.  A name is suggested
from the dataset and its indices; type over it and yours is kept.  Relative
names are written to the working directory.

The suggestion is not rewritten as you move the sliders -- writing to a
matplotlib TextBox redraws the whole window, which costs more than the plot does
-- so it is brought up to date when you save.  The file you get always carries
the indices it was saved at, and the box then shows the name actually used.

  ``save figure``   the window as PNG, PDF, SVG, EPS, JPEG or TIFF
  ``save slice``    the data behind the plot as CSV, TSV, TXT, NPY or NPZ
  ``metadata``      opens the metadata window described below

Each button corrects the extension for what it saves, so the same name can be
used for both.  The path written is reported under the plot.

**Exports are in SI units, not in the units the axes are labeled with.**  A time
axis displayed in microseconds exports in seconds -- the values in the file are
the values in the ONDE file.  Text exports begin with ``#`` comment lines naming
the dataset, its UUID, the source file, the amplitude calibration and the
position of every axis, so an exported slice can be traced back to the
acquisition it came from; ``.npz`` carries the same header plus the axis vectors
alongside the array, while ``.npy`` is the bare array.

A 1-D export is two columns, coordinate and amplitude.  A 2-D export puts the x
coordinates in the first row and the y coordinates in the first column, and is
written in display orientation -- what you exported is what you were looking at.

Older files
-----------

ONDE v0.9.2 changed two things a reader meets head-on, and the viewer handles
both without special-casing:

* **UUIDs.**  v0.9.2 uses ``urn:uuid:`` followed by a hyphenated hexadecimal
  128-bit value; earlier files carry the DICOM-style ``2.25.<decimal>`` form.
  The specification tells readers to treat the string as opaque, so the viewer
  never parses or reconstructs one: it takes the keys and the short keys
  PyONDE reports, pairs them positionally, and addresses datasets by whichever
  it was given.  A legacy key that PyONDE leaves unshortened works like any
  other.
* **Renamed fields.**  ``SENSOR_LIST`` and ``FRAME`` are not in the 0.9.2
  definitions, so in an older file they resolve only by their fully qualified
  names -- which is how the metadata window reads everything anyway, so they
  are still shown.

``PyONDE.viewer.testdata.write_legacy_file`` writes such a file, and the test
suite reads every synthetic file under every set of definitions PyONDE ships,
asserting the samples, axes and calibration come out identical.

Metadata
--------

The ``metadata`` button opens a second window showing the ONDE subgraph reached
from the dataset: setup, geometric setup, probes, trajectory, ultrasonic setup,
dimensions, and any fields from spec versions PyONDE does not know about, which
appear under their fully qualified names.  Arrays are summarized by shape, dtype
and range rather than dumped, and an object reached by two paths is shown once.
Drag the scrollbar or use the wheel to scroll; the box at the bottom filters
lines by substring (try ``FREQUENCY`` or ``UNITS``).

Programmatic use
----------------

The model layer is useful on its own, without any plotting::

  >> from PyONDE.viewer import OndeDocument
  >> document = OndeDocument.open("scan.onde")
  >> model = document[0]
  >> model.shape
  (3, 4, 2, 1000)
  >> [axis.coordinate for axis in model.axes]
  ['U Position', 'V Position', 'Ascan', 'Time']
  >> waveform = model.slice((1, 2, 0, slice(None)))     # calibrated, in Volts
  >> time = model.axes[3].values()                      # calibrated, in seconds

The viewer can also be driven from a script or an IPython session::

  >> from PyONDE.viewer import view_onde_file
  >> application = view_onde_file("scan.onde", show=False)

Keep a reference to the returned application: matplotlib widgets stop responding
once they are garbage collected, so dropping it leaves a window that looks fine
and ignores every click.

:meth:`~PyONDE.viewer.model.OndeDatasetModel.slice` is the single path by which
bulk data is read.  Amplitude calibration (``value*SCALE + OFFSET``) is applied
to the extracted slice rather than to the whole array, so browsing a large
dataset does not cost a second copy of it.

Every axis is described by an :class:`~PyONDE.viewer.model.AxisDescriptor`
carrying the ONDE_DIMENSION coordinate, units, scale and offset, with the
defaults from the specification filled in where the file omits them (index
dimensions default to Time in seconds, amplitude to Amplitude in arbitrary
units, scale 1.0 and offset 0.0).  ``axis.is_default`` records where that
happened, and ``document.warnings`` collects structural complaints such as an
INDEX_DIMENSIONS list whose length disagrees with the rank of DATA.

Performance
-----------

Stepping an index redraws only the artists that moved, by blitting: the
background is cached and restored rather than the figure being drawn again.  On
a 20x20x4x4000 A-scan file this is the difference between 62 ms and 4 ms per
step for a waveform, and 87 ms and 21 ms for an image.  Two consequences worth
knowing:

* Anything that changes the axes -- switching dataset or axis, changing the
  colormap, moving the value limits -- falls back to a full redraw, which is why
  dataset-wide limits are the default: limits that changed on every step would
  defeat the mechanism entirely.
* Artists that blit are marked ``animated``, which excludes them from ordinary
  draws.  The viewer un-marks them around ``savefig`` so that saved figures are
  complete; if you render the figure yourself by some other route, do the same
  with ``application.blitter.static()``, or construct the viewer with
  ``blit=False``.

Memory
------

PyONDE reads every HDF5 dataset in a file eagerly when the file is opened, so
opening a file costs approximately its size in RAM and slicing afterwards is
free.  ``ondeview`` warns before opening files larger than a gigabyte.

Test data
---------

:mod:`PyONDE.viewer.testdata` writes synthetic ONDE files for development:
A-scan, T-scan and C-scan datasets with full metadata, and a "hostile" file --
written with raw h5py rather than PyONDE -- collecting the legal-but-awkward
structures the viewer has to tolerate: absent dimension metadata, integer data,
a dataset with no DATA, DATA stored as an HDF5 reference, and an
INDEX_DIMENSIONS list that disagrees with the rank of the data.
