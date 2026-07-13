import onde


leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"], store_as_dataset = True,  _frozen = True)
obj = onde.ONDEObject.new(ONDE_TYPE=onde.ONDEArray.new(["myobject"], _frozen=True), leaf = leaf)
obj.leaf2 = leaf2
obj.leaf_secondreference = leaf
obj.array = array
obj._freeze()

snapshot = onde.ONDEFileGraphSnapshot.new(obj = obj, _frozen = True)
graph = onde.ONDEFileGraph.new(None,snapshot)
