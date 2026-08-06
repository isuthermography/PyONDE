import PyONDE as onde


leaf = onde.ONDEValue.new("leaf value", _frozen = True)
leaf2 = onde.ONDEValue.new("leaf value 2", _frozen = True)
leaf3 = onde.ONDEValue.new("leaf value 3", _frozen = True)
array = onde.ONDEArray.new(["string1","string2"], _frozen = True)
obj = onde.ONDEObject.new(None, None, ONDE_TYPE = onde.ONDEArray.new(["ONDE_DATASET"], _frozen=True), **{"TEST:leaf":leaf})
obj["ONDE:UUID"] = onde.ONDEValue.new("2.25.123456", _frozen = True)
obj["TEST:leaf2"] = leaf2
obj["TEST:leaf_secondreference"] = leaf
obj["TEST:leaf3"] = leaf3
obj["TEST:leaf3_secondreference"] = leaf3
obj["TEST:array"] = array
obj._freeze()

snapshot = onde.ONDEFileGraphSnapshot.new(_frozen = False)
snapshot.add(obj)
graph = onde.ONDEFileGraph.new(None,snapshot)


with onde.ONDETransaction(graph) as tr:
    #import pdb
    #pdb.set_trace()
    tr.graph["123456"]["TEST:leaf2"].value = 5.0
    pass

graph["123456"]["TEST:leaf"].value = 7.0

assert(graph["123456"]["TEST:leaf"].value == 7.0)
assert(snapshot["123456"]["TEST:leaf"].value == "leaf value")
assert(graph["123456"]["TEST:leaf_secondreference"].value == "leaf value")
# In defining the scope, it would be good to be able to use a shorthand for the entry point directly.
with onde.ONDETransaction(graph, [onde.ONDEPath((graph["123456"]["ONDE:UUID"].value,))]) as tr:
    # because of the scope specified for the transaction, this next line will change both obj.leaf and obj.leaf_secondreference
    tr.graph["123456"]["TEST:leaf3"].value = 9.0
    pass

assert(graph["123456"]["TEST:leaf3"].value == 9.0)
assert(graph["123456"]["TEST:leaf3_secondreference"].value == 9.0)
