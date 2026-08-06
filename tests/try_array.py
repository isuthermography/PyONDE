from PyONDE import onde


twa = onde.TwoWayArray(shape=(2,))
target = ("target content",)
twa[0] = target
twa[1] = target
print(twa[0])
print(twa(target))

nditer = iter(twa)
for element in nditer:
    print(f"twa[{str(nditer.multi_index):s}] = {str(element[()]):s}")
    pass
