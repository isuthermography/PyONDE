import sys

from setuptools import setup, Extension
import numpy as np
import os
import os.path
import re
import shutil
import subprocess
import glob
from setuptools.command.install import install
try:
    from setuptools.command.build import build
    pass
except ModuleNotFoundError:
    from distutils.command.build import build
    pass

ext_modules = []
package_data = {
    "PyONDE": ["onde_versions/*.csv"]
}


console_scripts=[] #["example_script"]

console_scripts_entrypoints = [ "%s = PyONDE.bin.%s:main" % (script,script.replace("-",'_')) for script in console_scripts ]



setup(name="PyONDE",
      description="PyONDE library for reading, modifying, and writing ONDE files",
      author="Stephen D. Holland",
      #version=version,
      url="http://github.com/isuthermography/PyONDE",
      ext_modules=ext_modules,
      zip_safe=False,
      #cmdclass={
      #    "install": InstallCommand,
      #    "build": BuildCommand
      #},
      packages=["PyONDE","PyONDE.bin"],
      package_data=package_data,
      entry_points={"console_scripts": console_scripts_entrypoints })
