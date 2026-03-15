import onde
import os

defs = onde.ONDEClassDefinitions.load_from_csv(
    os.path.join("..", "..", "ONDE-format", "ONDE_fields", "ONDE_fields.csv")
)

print(defs)