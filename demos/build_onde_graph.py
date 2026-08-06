import PyONDE as onde

import os

class_def_csv_path =  os.path.join("..", "..", "ONDE-format", "build", "ONDE_fields.csv")
class_defs = onde.ONDEClassDefinitions.load_from_csv(class_def_csv_path)

leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"],  _frozen = True)
obj = onde.ONDEObject.new(None, None, ONDE_TYPE = onde.ONDEArray.new(["ONDE_DATASET"],_frozen=True), **{"TEST:leaf":leaf})
obj["ONDE:UUID"] = onde.ONDEValue.new("2.25.1234567", _frozen = True)
obj["TEST:leaf2"] = leaf2
obj["TEST:leaf_secondreference"] = leaf
obj._set_dataset_attr("TEST:array", array)
obj._freeze()

snapshot = onde.ONDEFileGraphSnapshot.new(_frozen = False)
snapshot.add(obj)
graph = onde.ONDEFileGraph.new(class_defs,snapshot)

graph["1234567"]._set_attr("ONDE:LABEL",onde.ONDEValue.new("label value", _frozen = True))
assert(graph["1234567"]._get_attr("ONDE:LABEL").value=="label value")
