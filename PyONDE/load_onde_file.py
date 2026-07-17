# Try loading the output from build_onde_file.py


import os
import os.path
import sys
import tempfile

import onde

class_def_csv_path =  os.path.join("..", "..", "ONDE-format", "ONDE_fields", "ONDE_fields.csv")

output_path = os.path.join(tempfile.gettempdir(), "pyonde_build_onde_file_output.onde")

of = onde.ONDEDatasetFile.new(output_path, "r",
                              class_defs_path = class_def_csv_path)
