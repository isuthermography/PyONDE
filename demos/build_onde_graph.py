import PyONDE as onde

import os
import sys
onde_version='0.9.2'
class_def_csv_path =  os.path.join(os.path.split(sys.modules["PyONDE"].__file__)[0],"onde_versions",f"ONDE_fields_v{onde_version:s}.csv")


class_defs = onde.ONDEClassDefinitions.load_from_csv(class_def_csv_path)

leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"],  _frozen = True)
obj = onde.ONDEObject.new(None, None, ONDE_TYPE = onde.ONDEArray.new(["ONDE_DATASET"],_frozen=True), **{"TEST:leaf":leaf})
obj["ONDE:UUID"] = onde.ONDEValue.new("urn:uuid:01234567-89ab-cdef-0123-456789abcdef", _frozen = True)
obj["TEST:leaf2"] = leaf2
obj["TEST:leaf_secondreference"] = leaf
obj._set_dataset_attr("TEST:array", array)
obj._freeze()

snapshot = onde.ONDEFileGraphSnapshot.new(_frozen = False)
snapshot.add(obj)
graph = onde.ONDEFileGraph.new(class_defs,snapshot)

graph["01234567"]._set_attr("ONDE:LABEL",onde.ONDEValue.new("label value", _frozen = True))
assert(graph["01234567"]._get_attr("ONDE:LABEL").value=="label value")
