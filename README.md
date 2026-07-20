PyONDE is a pure python library for reading, modifying, and writing ONDE data structures and files. PyONDE is built to handle the most challenging situations, such as multi-threaded applications and modifying the ONDE graph structure while ensuring consistency. It is also designed to be easy to use with a simple API that exposes the class structure of the ONDE data model for interactive use. 

Architecture
------------

PyONDE implements three different abstraction layers through which you can access OMDE data structures. The lowest level, the concrete objects layer, provides classes for representing ONDE information that could be stored in a file. Concrete objects can be changed only while they're being initialized. Then they become "frozen", at which point they are immutable and can no longer be changed.  The middle abstraction level, the writeable proxy layer, wraps the concrete objects so that they appear to be modifiable, but modifications instead result in replacement of an object by a modified copy. The highest abstraction layer, the class instance wrapper, wraps concrete objects or writeable proxies with a layer that is aware of the various classes of ONDE objects defined in the ONDE specification. 

The concrete objects layer is implemented by a hierarchy of classes that all derive from class ONDEBase. These classes represent the various forms of data that can be stored in an ONDE file. They are assembled in the form of a directed acyclic graph, just like the ONDE objects they represent, however, there are many cases where a single ONDE object might be represented using several linked concrete ONDEBase objects. For example, an ONDE field with an integer value conceptually is a single object. However, the integer object is represented in PyONDE as a separate ONDEValue object that is referenced by the parent ONDEObject that contains it. So the PyONDE graph structure may contain more elements than what would be obvious from the ONDE specification.

Concrete classes 
--

All concrete classes derive from ONDEBase And are immutable, and therefore thread safe, once frozen:
  * ONDEValue represents simple values such as integers, floating point numbers, and strings. These are represented in the hdf5 file as hdf5 attributes. 
  * ONDEArray represents arrays of strings, integers, or floating point numbers. these can be represented in the hdf5 file either as datasets or attributes. The choice of dataset or attribute is selected in the parent ONDEObject.
  * ONDEReferenceArray represents arrays of cross references to ONDEObjects. these can be represented in hdf5 file either as data sets or attributes
  * ONDEObject represents instances of classes from the ONDE specification. ONDEObjects contain a dictionary of fields or attributes, which can be instances of ONDEBase subclasses. ONDEObjects are represented in the hdf5 file as groups. 
  * ONDEFileGraphSnapshot is a derived class of
ONDEObject that references the entry points (root graph elements) for an ONDE file or in-memory data structure at an instant in time.

A conceptual ONDE file and its graph of objects is represented in memory by class ONDEFileGraph. Because the ONDE file can change over time, the ONDEFileGraph references the most current contents with its .latest_snap attribute. 

An open hdf5 ONDE file on disc is represented by class ONDEFile, which references the conceptual content as an ONDEFileGraph contained in its .graph attribute. ONDEFile supports reading or writing the file.
