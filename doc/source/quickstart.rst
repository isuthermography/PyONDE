Creating new ONDE files
-----------------------

Import the basic PyONDE classes and helper functions::

  >> from PyONDE import (ONDEDatasetFile,
                         ONDEObject,
                         ONDEArray,
                         ONDEReferenceArray,
                         ONDEValue,
                         generate_onde_uuid)

Create a new file object::

  >> of = ONDEDatasetFile.new("myfile.onde", "w", onde_version = "0.9.1pre")

The mode parameter ("w") is passed directly to h5py.File() and is usually "w" for writing or "r" for reading. The onde_version parameter selects a version of the onde specification that is embedded in PyONDE. As an alternative you can pass a parameter `class_defs_path` pointing to the ONDE csv field definitions, and also pass additional class definitions with the `extra_class_defs` parameter.

The next step is to create an instance of an ONDE_DATASET subclass::

  >> ds = ONDEObject.new(of,"ONDE_DATASET_UT_ASCAN")

Before it can be added to the file, the new dataset needs a unique identifier (UUID). Such an identifier can be created using the `generate_onde_uuid()` helper function::

  >> import uuid
  >> from datetime import datetime 
  >> ds.UUID = generate_onde_uuid("ISUCNDE",str(uuid.getnode()),datetime.now(),"")

The parameters are intended to be unique in combination. They indicate a vendor name, some kind of serial number, a microsecond-accurate timestamp, and a suffix. The UUID is a 128-bit hash of those parameters that is stored as a decimal string following the fixed prefix `2.25.` for interoperability with the DICOM/DICONDE universe. Let us view the UUID::

  >> ds.UUID
  ONDEValue
                  ID: 7fb4b681dbe0
                type: str
               value: 2.25.124217692408202938307279138509891347358

(Your UUID value will be different)

Now we can fill out more fields. For example,::

  >> ds.LABEL="My Dataset"
  >> ds
  InstanceWrapper(ONDE_DATASET_UT_ASCAN)(ONDEObject)
                  ID: 7fb4b681c6e0
  AMPLITUDE_DIMENSION: None
                DATA: None
       DATE_AND_TIME: None
    INDEX_DIMENSIONS: None
               LABEL: ONDEValue(My Dataset)
           ONDE:TYPE: ONDEArray([['ONDE_DATASET', 'ONDE_DATASET_UT', 'ONDE_DATASET_UT_ASCAN']])
            OPERATOR: None
               SETUP: None
                UUID: ONDEValue(2.25.124217692408202938307279138509891347358)
            
At any point after the UUID is set, the dataset can be added to the ONDE file::

  >> of.graph.add(ds) 

The dataset is identified within the file by its UUID. Because the UUID is very long, you can access the dataset using a shortened version (omitting the `2.25.`). If we just ask Python to show us a representation of the file graph, it will show us a handy shortened version::

  >> of.graph
  ONDEFileGraph (ONDE v0.9.1 class definitions)
  ONDEFileGraphSnapshot
                    ID: 7fb4b681c2f0
                  1242: ONDEObject(ID=7fb4b681c6e0)

The representation indicates that within the ONDEFileGraphSnapshot, index 1242 refers to an ONDEObject. Notice that in the `ds.UUID` output above, after the `2.25.` was the same 1242. This is a shortened index you can use to access the dataset (in fact, you can shorten it further so long as it is unique).

Therefore, we can access the dataset by indexing of.graph::

  >> of.graph["1242"]
  InstanceWrapper(ONDE_DATASET_UT_ASCAN)(ONDEObject)
                  ID: 7fb4b681c6e0
  AMPLITUDE_DIMENSION: None
                DATA: None
       DATE_AND_TIME: None
    INDEX_DIMENSIONS: None
               LABEL: ONDEValue(My Dataset)
           ONDE:TYPE: ONDEArray([['ONDE_DATASET', 'ONDE_DATASET_UT', 'ONDE_DATASET_UT_ASCAN']])
            OPERATOR: None
               SETUP: None
                UUID: ONDEValue(2.25.124217692408202938307279138509891347358)

A full example of creating a UT dataset is included in the demos folder as `build_onde_file.py`. In general, scalar numeric values, strings, and integers can be assigned as we did with the LABEL above. More sophisticated types will need to be created explicitly.

Once objects are assigned into the graph, they are frozen and can no longer be changed. So, for example, if we were to try to change `ds.LABEL`, we would get an error::

  >> ds.LABEL="Your Dataset"
  Traceback (most recent call last):
  [...]
  RuntimeError: Attempting to modify an object that is already frozen

We can indeed change objects after they are inserted into the graph, but we have to do so by changing the graph: i.e. replacing them with copies. When you access an object from the graph, you actually get a reference to a proxy class that helps perform the graph modification. So all you have to do is make the change via the graph itself::

  >> of.graph["1242"].LABEL="Your Dataset"
  >> of.graph["1242"]
  InstanceWrapper(ONDE_DATASET_UT_ASCAN)(ONDEObject)
                  ID: 7fb4b68551d0
  AMPLITUDE_DIMENSION: None
                DATA: None
       DATE_AND_TIME: None
    INDEX_DIMENSIONS: None
               LABEL: ONDEValue(Your Dataset)
           ONDE:TYPE: ONDEArray([['ONDE_DATASET', 'ONDE_DATASET_UT', 'ONDE_DATASET_UT_ASCAN']])
            OPERATOR: None
               SETUP: None
                UUID: ONDEValue(2.25.124217692408202938307279138509891347358)


Performing the assignment automatically and implicitly started a transaction for changing the graph. It then duplicated the ONDE_DATASET_UT_ASCAN object, replacing the LABEL as requested. It then walked the graph back to the corresponding entry point, `of.graph["2.25.124217692408202938307279138509891347358"]` abbreviated as `of.graph["1242"]`, replacing all nodes with copies now pointing at new versions that lead to the updated LABEL. Finally, it ended the transaction creating an atomic update to `of.graph`.

WARNING: The variable `ds` refers to the original `ONDE_DATASET_UT_ASCAN` `ONDEObject` instance that was added to the graph. It was frozen when it was added to the graph. Any changes made since it was added will not appear when you look at `ds`.
  
Let us return to filling out the dataset object. The ONDEReferenceArray class represents an array of references to ONDE objects. We can create such an array to represent the dataset index dimensions::

  >> ind_dims = ONDEReferenceArray.new(of,shape=(4,))
  >> ind_dims
  ONDEReferenceArray
                  ID: 7fbc6248c2f0
               shape: (4,)

We can then populate the array with `ONDE_DIMENSION` instances::

  >> ind_dims[0] = ONDEObject.new(of,"ONDE_DIMENSION")
  >> ind_dims[0].COORDINATE = "U Position"
  >> ind_dims[0].OFFSET = 0.0
  >> ind_dims[0].SCALE = 1.0
  >> ind_dims[0].UNITS = "meters"

and similarly for the remaining three dimensions. When instantiating an ONDE class `ONDEObject.new()`, the first parameter is the `ONDEFile` or `ONDEFileGraph` object and the second parameter is the name of the ONDE class.

We created ind_dims and stored it in a temporary variable so that it would not be frozen and we could still modify it before assigning it into our dataset (if we had not yet added the dataset to the graph, this would not be necessary). So we still need to assign it into the dataset::

  >> of.graph["1242"].INDEX_DIMENSIONS = ind_dims

Numeric arrays can be similarly stored with the `ONDEArray` class. For example::

  >> import numpy as np
  >> of.graph["1242"].DATA = ONDEArray.new(value=np.zeros((1,1,1,1000), dtype="d"))

Using the above methods, the rest of the dataset can be filled out.

Once you have created and added all the datasets, you can write them to the disk file using the `.flush()` method::

  >> of.flush()

Finally, you can close the disk file with the `.close()` method::

  >> of.close()

Reading existing ONDE files
---------------------------

As with creating new files, it is a good idea to import the basic PyONDE classes and helper functions::

  >> from PyONDE import (ONDEDatasetFile,
                         ONDEObject,
                         ONDEArray,
                         ONDEReferenceArray,
                         ONDEValue,
                         generate_onde_uuid)

Create a new file object from an on-disk file::

  >> of = ONDEDatasetFile.new("myfile.onde", "r", onde_version = "0.9.1pre")

The mode parameter ("r") is passed directly to h5py.File() and is usually "w" for writing or "r" for reading. The onde_version parameter selects a version of the onde specification that is embedded in PyONDE. As an alternative you can pass a parameter `class_defs_path` pointing to the ONDE csv field definitions, and also pass additional class definitions with the `extra_class_defs` parameter.

The `onde_version` that you specify for reading does NOT need to match the version stored in the file itself. Rather, the version that you specify controls which classes are defined and the known fields of those classes. Therefore, when reading ONDE files programmatically, you should specify the ONDE version corresponding to the fields you reference in your code. PyONDE can happily manage unknown fields, but such fields will need to be accessed using brackets and with class definition prefixes, e.g. `ds.graph["12345"]["MYORG_MY_ACCESSORY_CLASS:MYFIELD"]` rather than through the usual Python attribute shorthand.

Once the file has been loaded, it is accessible just like when it was written. You index the various datasets by their UUID or a shortened version. For example::

  >> of
  ONDEFile open on "myfile.onde"
  ONDEFileGraph (ONDE v0.9.1 class definitions)
    ONDEFileGraphSnapshot
                      ID: 7f9ca6c0f4d0
                    1242: ONDEObject(ID=7f9ca6c0f750)

Then index into the dataset we saved above (note that its UUID is the same as when we generated it above)::

  >> of.graph["1242"]
  InstanceWrapper(ONDE_DATASET_UT_ASCAN)(ONDEObject)
                  ID: 7f9ca6c0f750
  AMPLITUDE_DIMENSION: None
                DATA: ONDEArray(shape=(1, 1, 1, 1000),dtype=float64)
       DATE_AND_TIME: None
    INDEX_DIMENSIONS: InstanceWrapper of ONDEReferenceArray(shape=(4,))
               LABEL: ONDEValue(Your Dataset)
           ONDE:TYPE: ONDEArray([['ONDE_DATASET', 'ONDE_DATASET_UT', 'ONDE_DATASET_UT_ASCAN']])
            OPERATOR: None
               SETUP: None
                UUID: ONDEValue(2.25.124217692408202938307279138509891347358)

You can get a list of all of the datasets with the `.keys()` method::

  >> of.graph.keys()
  ['2.25.124217692408202938307279138509891347358']

Since the UUID's are very long, there is also a `.shortkeys()` method::

  >> of.graph.shortkeys()
  ['1242']

For regular objects, you can show the various fields with the `._keys()` method::

  >> of.graph["1242"]._keys()
  ['ONDE_DATASET:OPERATOR', 'ONDE_DATASET:INDEX_DIMENSIONS', 'ONDE_DATASET:SETUP', 'ONDE_DATASET:AMPLITUDE_DIMENSION', 'ONDE:UUID', 'ONDE:TYPE', 'ONDE:LABEL', 'ONDE_DATASET:DATE_AND_TIME', 'ONDE_DATASET:DATA']

To get the shorthand version, you can instead use the `.shortkeys()` method::

  >> of.graph["1242"]._shortkeys()
  ['OPERATOR', 'SETUP', 'DATA', 'DATE_AND_TIME', 'LABEL', 'UUID', 'ONDE:TYPE', 'AMPLITUDE_DIMENSION', 'INDEX_DIMENSIONS']

You can also list attributes with `dir()`::

  >> dir(of.graph["1242"])
   ['AMPLITUDE_DIMENSION', 'DATA', 'DATE_AND_TIME', 'INDEX_DIMENSIONS', 'LABEL', 'ONDE:TYPE', 'OPERATOR', 'SETUP', 'UUID', '_freeze', '_frozen', '_get_attr', '_has_attr', '_list_attrs', '_set_attr']

If a class or accessory class is unknown, even the short version of the field name will contain a colon, so you won't be able to access it with the usual Python attribute notation. You can always use brackets as an alternative::

  >> of.graph["1242"]["ONDE_DATASET:INDEX_DIMENSIONS"]
  ONDEReferenceArray
                  ID: 7fc425754980
               shape: (4,)

Note that just because a field is listed in `dir()` or `._keys()` or `._shortkeys()`, doesn't mean the field has a value. If the field has no value, attempting to read it will raise an exception. You should always be able to assign a field.
