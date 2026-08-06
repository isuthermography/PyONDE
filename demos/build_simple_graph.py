import PyONDE as onde

leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"],  _frozen = True)
obj = onde.ONDEObject.new(None, None, ONDE_TYPE=onde.ONDEArray.new(["ONDE_DATASET"], _frozen = True), leaf = leaf)
obj["ONDE:UUID"] = onde.ONDEValue.new("2.25.12345", _frozen = True)
obj["TEST:leaf2"] = leaf2
obj["TEST:leaf_secondreference"] = leaf
obj._set_dataset_attr("TEST:array", array)
obj._freeze()

# Should really be able to provide a list of objects to add to the ONDEFileGraphSnapshot constructor so that we can initialize it frozen
snapshot = onde.ONDEFileGraphSnapshot.new(_frozen = False)
snapshot.add(obj)
graph = onde.ONDEFileGraph.new(None,snapshot)
