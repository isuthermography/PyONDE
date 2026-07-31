import os
import os.path
import sys
import tempfile
from datetime import datetime,timezone
import numpy as np

import onde

class_def_csv_path =  os.path.join("..", "..", "ONDE-format", "build", "ONDE_fields.csv")

output_path = os.path.join(tempfile.gettempdir(), "pyonde_build_onde_file_output.onde")

dt = 0.1e-6
nt = 1000
t0 = 10e-6

t = t0 + np.arange(nt)*dt

value = np.cos(t)

of = onde.ONDEDatasetFile.new(output_path, "w",
                              class_defs_path = class_def_csv_path)

ds = of.graph.new_obj("ONDE_DATASET_UT_ASCAN")
ds.LABEL = "First dataset"
ds.AMPLITUDE_DIMENSION = of.graph.new_obj("ONDE_DIMENSION")
ds.AMPLITUDE_DIMENSION.COORDINATE = "Voltage"
ds.AMPLITUDE_DIMENSION.OFFSET = 0.0
ds.AMPLITUDE_DIMENSION.SCALE = 1.0
ds.AMPLITUDE_DIMENSION.UNITS = "Volts"
ds.DATA = onde.ONDEArray.new(value = value)
ds.DATE_AND_TIME = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
ds.INDEX_DIMENSIONS = onde.ONDEReferenceArray.new(refs = np.zeros(4,dtype = "O"))
ds.INDEX_DIMENSIONS[0] = of.graph.new_obj("ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[0].COORDINATE = "U Position"
ds.INDEX_DIMENSIONS[0].OFFSET = 0.0
ds.INDEX_DIMENSIONS[0].SCALE = 1.0
ds.INDEX_DIMENSIONS[0].UNITS = "meters"
ds.INDEX_DIMENSIONS[1] = of.graph.new_obj("ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[1].COORDINATE = "V Position"
ds.INDEX_DIMENSIONS[1].OFFSET = 0.0
ds.INDEX_DIMENSIONS[1].SCALE = 1.0
ds.INDEX_DIMENSIONS[1].UNITS = "meters"
ds.INDEX_DIMENSIONS[2] = of.graph.new_obj("ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[2].COORDINATE = "None"
ds.INDEX_DIMENSIONS[2].OFFSET = 0.0
ds.INDEX_DIMENSIONS[2].SCALE = 1.0
ds.INDEX_DIMENSIONS[2].UNITS = "unitless"
ds.INDEX_DIMENSIONS[3] = of.graph.new_obj("ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[3].COORDINATE = "Time"
ds.INDEX_DIMENSIONS[3].OFFSET = 0.0
ds.INDEX_DIMENSIONS[3].SCALE = 1.0
ds.INDEX_DIMENSIONS[3].UNITS = "seconds"
ds.OPERATOR = "Nemo"

ds.SETUP=of.graph.new_obj("ONDE_SETUP_UT")
ds.SETUP.GEOMETRIC_SETUP=of.graph.new_obj("ONDE_GEOMETRIC_SETUP")
ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY = onde.ONDEReferenceArray.new(shape = (1,))
ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0] = of.graph.new_obj("ONDE_SPATIAL_TRAJECTORY")
#This next line should work but doesn't ( fails silently)
#ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0].TRAJECTORY = np.array(((e0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),))
ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0].TRAJECTORY = onde.ONDEArray.new(value = np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
ds.SETUP.GEOMETRIC_SETUP.COMPONENT = of.graph.new_obj("ONDE_COMPONENT")
ds.SETUP.GEOMETRIC_SETUP.COMPONENT.VELOCITIES = onde.ONDEArray.new(value = [np.nan,np.nan])
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST = onde.ONDEReferenceArray.new(shape = (1,))
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0] = of.graph.new_obj("ONDE_UT_PROBE")
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].COUPLING = of.graph.new_obj("ONDE_UT_COUPLING")
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].COUPLING.INCIDENCE_ANGLE = 0.0
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].COUPLING.MEDIUM_VELOCITY = onde.ONDEArray.new(shape = (2,))
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].COUPLING.MEDIUM_VELOCITY[0] = np.nan
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].COUPLING.MEDIUM_VELOCITY[1] = np.nan
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].FRAME = onde.ONDEArray.new(value = np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].FREQUENCY = 1e6 # Hz
# SHAPE type is currently documented as integer but in fact it should be a string
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].SHAPE = onde.ONDEArray.new(value = np.array(("ELE_GEOM_RING_PART",),dtype = "O"))
ds.SETUP.GEOMETRIC_SETUP.SENSOR_LIST[0].SIZE = onde.ONDEArray.new(value = np.array(((0, (0.5/2)*25.4e-3, 0, 360, 0, 0),)))
ds.SETUP.ULTRASONIC_SETUP = of.graph.new_obj("ONDE_ULTRASONIC_SETUP")
ds.SETUP.ULTRASONIC_SETUP.ASCAN_SAMPLE_RATE = 1/dt
ds.SETUP.ULTRASONIC_SETUP.ASCAN_START = onde.ONDEArray.new(value = np.array(0.0))
#This next line should work but doesn't ( fails silently)
#ds.SETUP.ULTRASONIC_SETUP.GAIN = np.array((10**(60/20),))
ds.SETUP.ULTRASONIC_SETUP.GAIN = onde.ONDEArray.new(value = np.array((10**(60/20),)))
# Not quite clear what other rectification options mean (?)
ds.SETUP.ULTRASONIC_SETUP.RECTIFICATION = "FULL_WAVE"

of.graph["ds"] = ds
of.flush()
# of.close()
