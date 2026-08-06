from PyONDE import onde
import os

defs = onde.ONDEClassDefinitions.load_from_csv(
    os.path.join("..", "..", "ONDE-format", "build", "ONDE_fields.csv")
)

print(defs)
