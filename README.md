
PyONDE Python library for reading modifying writing ONDE files
--------------------------------------------------------------

PyONDE is a pure python library for reading, modifying, and writing
ONDE data structures and files. PyONDE is built to handle the most
challenging situations, such as multi-threaded applications and
modifying the ONDE graph structure while ensuring consistency. It is
also designed to be easy to use with a simple API that exposes the
class structure of the ONDE data model for interactive use.

More information and documentation in the doc/ folder and at
https://isuthermography.github.io/PyONDE/ and at
https://github.com/isuthermography/PyONDE

Viewing ONDE files
------------------

PyONDE includes ``ondeview``, a dimension-driven viewer for the data in an ONDE
file, built entirely on matplotlib and matplotlib.widgets::

    pip install PyONDE[viewer]
    ondeview --list scan.onde     # datasets, shapes, axes (no matplotlib needed)
    ondeview scan.onde            # the interactive viewer

It shows any DATA array with one or two axes mapped to the display and a slider
fixing each of the rest, reading the coordinates, units and calibration from
INDEX_DIMENSIONS, so an A-scan file opens as a waveform and a T-scan file as a
zone image without either being a special case.  Slices and figures can be
exported, and a second window shows the ONDE subgraph behind the dataset.

See doc/source/viewer.rst, or https://isuthermography.github.io/PyONDE/ , for
details.


Acknowledgments
---------------

Thanks to Abhigyaan Deep for helping with some of the coating


   Copyright 2026 Stephen D. Holland and Iowa State University
   Research Foundation
   
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
