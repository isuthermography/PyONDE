Installation
============


* Clone the repository::
    
    git clone https://github.com/isuthermography/PyONDE.git
    
* Install pre-requisites
  
  - Python, numpy, h5py
    
* Change to directory and install with pip::

    cd PyONDE
    pip install .

The ``ondeview`` command is installed either way.  Its listing modes
(``--list``, ``--info``) need nothing further; the interactive viewer needs
matplotlib, which PyONDE does not install for you -- it is not a requirement
and not an extra, so that a package whose job is file access does not drag a
plotting library in behind it::

    pip install matplotlib

Running ``ondeview`` on a file without matplotlib installed is harmless: it
says what to install, both on the terminal and in a message box, and exits.


    
