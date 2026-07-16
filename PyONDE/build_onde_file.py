import os
import os.path
import sys
import tempfile

import onde

class_def_csv_path =  os.path.join("..", "..", "ONDE-format", "ONDE_fields", "ONDE_fields.csv")

output_path = os.path.join(tempfile.gettempdir(), "pyonde_build_onde_file_output.onde")

of = onde.ONDEDatasetFile.new(output_path, "w",
                              class_defs_path = class_def_csv_path)

ds = of.graph.new_obj("ONDE_DATASET_UT_ASCAN")
ds.LABEL = "First dataset"
ds.SETUP=of.graph.new_obj("ONDE_SETUP_UT")
ds.SETUP.GEOMETRIC_SETUP=of.graph.new_obj("ONDE_GEOMETRIC_SETUP")
of.graph["ds"] = ds
of.flush()
of.close()
