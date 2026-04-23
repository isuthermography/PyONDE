import onde


leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"], store_as_dataset = True,  _frozen = True)
obj = onde.ONDEObject.new(_ONDE_type = ["myobject"], leaf = leaf)
obj.leaf2 = leaf2
obj.leaf_secondreference = leaf
obj.array = array
obj._freeze()

snapshot = onde.ONDEGraphSnapshot.new(obj = obj, _frozen = True)
graph = onde.ONDEGraph(snapshot)


with onde.ONDETransaction(graph) as tr:
    #import pdb
    #pdb.set_trace()
    tr.graph.obj.leaf2.value = 5.0
    pass

graph.obj.leaf.value = 7.0
