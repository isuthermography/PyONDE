import onde


leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
obj = onde.ONDEObject.new(_ONDE_type = ["myobject"], leaf = leaf)
obj.leaf2 = leaf2
obj.leaf_secondreference = leaf
obj.freeze()

snapshot = onde.ONDEGraphSnapshot.new(obj = obj, _frozen = True)
graph = onde.ONDEGraph(snapshot)
