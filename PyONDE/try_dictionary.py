import onde


twd = onde.TwoWayDictionary()
target = ("target content",)
twd.key = target
twd.key2 = target
print(twd.key)
print(twd[target])

for key in twd:
    print(f"twd.{key:s} = {str(twd.key):s}")
