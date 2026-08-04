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

def generate_onde_uuid(vendor_name,equip_serial,timestamp,suffix):
    """Generate and return an ONDE UUID string beginning with "2.25.".
    If you have no way to extract an equipment serial number, suggest using the python UUID module str(uuid.getnode()) to use ethernet hardware interface information in its place. timestamp can come from datetime.now() and suffix should distinguish between multiple datasets that might have the same timestamp.""" 
    unique_string = f"{vendor_name:s} {equip_serial:s} {timestamp.year:d} {timestamp.month:d} {timestamp.day:d} {timestamp.hour:d} {timestamp.minute:d} {timestamp.second:d} {timestamp.microsecond:d} {suffix:s}"
    py_major = sys.version_info.major
    py_minor = sys.version_info.minor
    hl_kwargs = {}
    if py_major > 3 or py_minor >= 9 :
        hl_kwargs["usedforsecurity"] = False
        pass
    import hashlib
    m = hashlib.sha256(**hl_kwargs)
    m.update(unique_string.encode("utf8"))
    digest256 = m.digest()
    assert(len(digest256) == 32)
    digest128 = digest256[16:]
    int128 = int.from_bytes(digest128,signed = False)
    return f"2.25.{int128:d}"
