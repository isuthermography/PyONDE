import sys
import os
import os.path

from .onde import (ONDEAccessoryClass,
                   ONDEArray,
                   ONDEBase,
                   ONDEClass,
                   ONDEClassDefinitions,
                   ONDEClassInstanceWrapper,
                   ONDEDatasetFile,
                   ONDEDatasetFileGraph,
                   ONDEField,
                   ONDEFile,
                   ONDEFileGraph,
                   ONDEFileGraphSnapshot,
                   ONDEFileObject,
                   ONDEObject,
                   ONDEOpScope,
                   ONDEPath,
                   ONDEProxy,
                   ONDEReferenceArray,
                   ONDETransaction,
                   ONDEValue)
                 
class dummy(object):
    pass


pkgpath = sys.modules[dummy.__module__].__file__
pkgdir=os.path.split(pkgpath)[0]

onde_versions_path = os.path.join(pkgdir,"onde_versions")
