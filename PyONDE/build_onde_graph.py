import onde

import os

class_def_csv_path =  os.path.join("..", "..", "ONDE-format", "ONDE_fields", "ONDE_fields.csv")

leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"], store_as_dataset = True,  _frozen = True)
obj = onde.ONDEObject.new(ONDE_TYPE = onde.ONDEArray.new(["ONDE_DATASET"],_frozen=True), leaf = leaf)
obj.leaf2 = leaf2
obj.leaf_secondreference = leaf
obj.array = array
obj._freeze()

snapshot = onde.ONDEGraphSnapshot.new(obj = obj, _frozen = True)
graph = onde.ONDEGraph.new(class_def_csv_path,snapshot)

graph.obj._set_attr("ONDE:LABEL",onde.ONDEValue.new("label value", _frozen = True))
assert(graph.obj._get_attr("ONDE:LABEL").value=="label value")
