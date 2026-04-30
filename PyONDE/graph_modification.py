import onde


leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
leaf3 = onde.ONDEValue.new("leaf value 3", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"], store_as_dataset = True,  _frozen = True)
obj = onde.ONDEObject.new(_ONDE_type = ["myobject"], leaf = leaf)
obj.leaf2 = leaf2
obj.leaf_secondreference = leaf
obj.leaf3 = leaf3
obj.leaf3_secondreference = leaf3
obj.array = array
obj._freeze()

snapshot = onde.ONDEGraphSnapshot.new(obj = obj, _frozen = True)
graph = onde.ONDEGraph.new(None,snapshot)


with onde.ONDETransaction(graph) as tr:
    #import pdb
    #pdb.set_trace()
    tr.graph.obj.leaf2.value = 5.0
    pass

graph.obj.leaf.value = 7.0

assert(graph.obj.leaf.value == 7.0)
assert(snapshot.obj.leaf.value == "leaf value")
assert(graph.obj.leaf_secondreference.value == "leaf value")

with onde.ONDETransaction(graph, [onde.ONDEPath(("obj",))]) as tr:
    # because of the scope specified for the transaction, this next line will change both obj.leaf and obj.leaf_secondreference
    tr.graph.obj.leaf3.value = 9.0
    pass

assert(graph.obj.leaf3.value == 9.0)
assert(graph.obj.leaf3_secondreference.value == 9.0)
