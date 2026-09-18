import os
import os.path
import sys
import tempfile
from datetime import datetime,timezone
import uuid
import numpy as np

from PyONDE import (ONDEDatasetFile,
                    ONDEObject,
                    ONDEArray,
                    ONDEReferenceArray,
                    ONDEValue,
                    generate_onde_uuid)

#class_def_csv_path =  os.path.join("..", "..", "ONDE-format", "build", "ONDE_fields.csv")

output_path = os.path.join(tempfile.gettempdir(), "pyonde_build_onde_file_output.onde")

dt = 0.1e-6
nt = 1000
t0 = 10e-6

t = t0 + np.arange(nt)*dt

value = np.cos(2*np.pi*800e3*t)

of = ONDEDatasetFile.new(output_path, "w",
                         #class_defs_path = class_def_csv_path,
                         onde_version = "0.9.2pre"
                         )

ds = ONDEObject.new(of,"ONDE_DATASET_UT_ASCAN")
ds["ONDE:TYPE"]
# Use these extra two lines to test out modifying the dataset once finalized by being added into the graph
#of.graph["ds"] = ds
#ds = of.graph["ds"]
ds.LABEL = "First dataset"
timestamp = datetime.now().astimezone()
ds.UUID = generate_onde_uuid("ISUCNDE",str(uuid.getnode()),timestamp,"")
ds.AMPLITUDE_DIMENSION = ONDEObject.new(of,"ONDE_DIMENSION")
ds.AMPLITUDE_DIMENSION.COORDINATE = "Voltage"
ds.AMPLITUDE_DIMENSION.OFFSET = 0.0
ds.AMPLITUDE_DIMENSION.SCALE = 1.0
ds.AMPLITUDE_DIMENSION.UNITS = "Volts"
ds.DATA = ONDEArray.new(value = value[np.newaxis,np.newaxis,np.newaxis,:])
ds.DATE_AND_TIME = timestamp.isoformat(timespec="microseconds")
ds.INDEX_DIMENSIONS = ONDEReferenceArray.new(of,refs = np.empty(4,dtype = "O"))
ds.INDEX_DIMENSIONS[0] = ONDEObject.new(of,"ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[0].COORDINATE = "U Position"
ds.INDEX_DIMENSIONS[0].OFFSET = 0.0
ds.INDEX_DIMENSIONS[0].SCALE = 1.0
ds.INDEX_DIMENSIONS[0].UNITS = "meters"
ds.INDEX_DIMENSIONS[1] = ONDEObject.new(of,"ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[1].COORDINATE = "V Position"
ds.INDEX_DIMENSIONS[1].OFFSET = 0.0
ds.INDEX_DIMENSIONS[1].SCALE = 1.0
ds.INDEX_DIMENSIONS[1].UNITS = "meters"
ds.INDEX_DIMENSIONS[2] = ONDEObject.new(of,"ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[2].COORDINATE = "None"
ds.INDEX_DIMENSIONS[2].OFFSET = 0.0
ds.INDEX_DIMENSIONS[2].SCALE = 1.0
ds.INDEX_DIMENSIONS[2].UNITS = "unitless"
ds.INDEX_DIMENSIONS[3] = ONDEObject.new(of,"ONDE_DIMENSION")
ds.INDEX_DIMENSIONS[3].COORDINATE = "Time"
ds.INDEX_DIMENSIONS[3].OFFSET = 0.0
ds.INDEX_DIMENSIONS[3].SCALE = 1.0
ds.INDEX_DIMENSIONS[3].UNITS = "seconds"
ds.OPERATOR = "Nemo"

ds.SETUP=ONDEObject.new(of,"ONDE_SETUP_UT")
ds.SETUP.GEOMETRIC_SETUP=ONDEObject.new(of,"ONDE_GEOMETRIC_SETUP")
ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY = ONDEReferenceArray.new(of, shape = (1,))
ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0] = ONDEObject.new(of,"ONDE_SPATIAL_TRAJECTORY")
#This next line should work but doesn't ( fails silently)
#ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0].TRAJECTORY = np.array(((e0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),))
ds.SETUP.GEOMETRIC_SETUP.ACQUISITION_TRAJECTORY[0].TRAJECTORY = ONDEArray.new(value = np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
ds.SETUP.GEOMETRIC_SETUP.COMPONENT = ONDEObject.new(of,"ONDE_COMPONENT")
ds.SETUP.GEOMETRIC_SETUP.COMPONENT.VELOCITIES = ONDEArray.new(value = [np.nan,np.nan])
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST = ONDEReferenceArray.new(of,shape = (1,))
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0] = ONDEObject.new(of,"ONDE_UT_PROBE")
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].COUPLING = ONDEObject.new(of,"ONDE_UT_COUPLING")
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].COUPLING.INCIDENCE_ANGLE = 0.0
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].COUPLING.MEDIUM_VELOCITY = ONDEArray.new(shape = (2,))
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].COUPLING.MEDIUM_VELOCITY[0] = np.nan
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].COUPLING.MEDIUM_VELOCITY[1] = np.nan
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].FRAME = ONDEArray.new(value = np.array(((0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),)))
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].FREQUENCY = 1e6 # Hz
# SHAPE type is currently documented as integer but in fact it should be a string
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].SHAPE = ONDEArray.new(value = np.array(("ELE_GEOM_RING_PART",),dtype = "O"))
ds.SETUP.GEOMETRIC_SETUP.PROBE_LIST[0].SIZE = ONDEArray.new(value = np.array(((0, (0.5/2)*25.4e-3, 0, 360, 0, 0),)))
ds.SETUP.ULTRASONIC_SETUP = ONDEObject.new(of,"ONDE_ULTRASONIC_SETUP")
ds.SETUP.ULTRASONIC_SETUP.ASCAN_SAMPLE_RATE = 1/dt
ds.SETUP.ULTRASONIC_SETUP.ASCAN_START = ONDEArray.new(value = np.array(0.0))
#This next line should work but doesn't ( fails silently)
#ds.SETUP.ULTRASONIC_SETUP.GAIN = np.array((10**(60/20),))
ds.SETUP.ULTRASONIC_SETUP.GAIN = ONDEArray.new(value = np.array((10**(60/20),)))
# Not quite clear what other rectification options mean (?)
ds.SETUP.ULTRASONIC_SETUP.RECTIFICATION = "FULL_WAVE"

# Indexing of the graph is by UUID
of.graph.add(ds)
of.flush()
# of.close()
