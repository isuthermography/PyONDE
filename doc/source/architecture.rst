Architecture
============

PyONDE implements three different abstraction layers through which you can access ONDE data structures. The lowest level, the concrete objects layer, provides classes for representing ONDE information that could be stored in a file. Concrete objects can be changed only while they're being initialized. Then they become "frozen", at which point they are immutable and can no longer be changed.  The middle abstraction level, the writeable proxy layer, wraps the concrete objects so that they appear to be modifiable, but modifications instead result in replacement of an object by a modified copy. The highest abstraction layer, the class instance wrapper, wraps concrete objects or writeable proxies with a layer that is aware of the various classes of ONDE objects defined in the ONDE specification. 

The concrete objects layer is implemented by a hierarchy of classes that all derive from class ONDEBase. These classes represent the various forms of data that can be stored in an ONDE file. They are assembled in the form of a directed acyclic graph, just like the ONDE objects they represent, however, there are many cases where a single ONDE object might be represented using several linked concrete ONDEBase objects. For example, an ONDE field with an integer value conceptually is a single object. However, the integer object is represented in PyONDE as a separate ONDEValue object that is referenced by the parent ONDEObject that contains it. So the PyONDE graph structure may contain more elements than what would be obvious from the ONDE specification.

Concrete classes 
-----------------

All concrete classes derive from ONDEBase And are immutable, and therefore thread safe, once frozen:
  * ONDEValue represents simple values such as integers, floating point numbers, and strings. These are represented in the hdf5 file as hdf5 attributes. 
  * ONDEArray represents arrays of strings, integers, or floating point numbers. these can be represented in the hdf5 file either as datasets or attributes. The choice of dataset or attribute is selected in the parent ONDEObject.
  * ONDEReferenceArray represents arrays of cross references to ONDEObjects. these can be represented in hdf5 file either as data sets or attributes
  * ONDEObject represents instances of classes from the ONDE specification. ONDEObjects contain a dictionary of fields or attributes, which can be instances of ONDEBase subclasses. ONDEObjects are represented in the hdf5 file as groups. 
  * ONDEFileGraphSnapshot is a derived class of
ONDEObject that references the entry points (root graph elements) for an ONDE file or in-memory data structure at an instant in time.



Classes representing the ONDE file as a whole
--
A conceptual ONDE file and its graph of objects is represented in memory by class ONDEFileGraph. Because the ONDE file can change over time, the ONDEFileGraph references the most current contents with its .latest_snap attribute. 

An open hdf5 ONDE file on disk is represented by class ONDEFile, which references the conceptual content as an ONDEFileGraph contained in its .graph attribute. ONDEFile supports reading or writing the file. Unlike other classes in PyONDE, ONDEFile is not thread safe because commanding simultaneous updates to the same disk file from multiple threads simultaneously doesn't make much sense.


Higher level wrappers 
--
The concrete classes that derive from ONDEBase are immutable once frozen. Immutability helps with thread safety and robustness. However, it is inconvenient not to be able to make changes. For this reason, we introduce a mutable proxy, ONDEProxy, that acts like it is modifiable, but instead copies the object being changed and repoints references to the modified copy. The ONDEProxy does not actually contain any data, but keeps track of the path of an object within the PyONDE graph structure. When accessed, it pulls data from the ONDEFileGraphSnapshot but when an attempt is made to modify data, the ONDEProxy creates a copy, applies to modification to the copy, and then searches for objects with in the modification scope of the transaction, replacing those objects as well with new objects that point to the changed version. 

ONDEClassInstanceWrapper provides a second layer of abstraction. It can operate on ONDEProxy or directly on ONDEBase instances. It makes ONDE objects appear as instances of the classes defined in the ONDE specification, based on the CSV/YAML class definitions. It allows the use of shorthand member variable names by supporting implicit prefixes. It also facilitates interactive use and introspection by listing fields defined in the specification, whether or not they are populated with values.

Accessing entry points from the ONDEFile or ONDEFileGraph gives ONDEClassInstanceWrappers around ONDEProxies that represent the underlying ONDEBase subclass instances. by this means, the ONDE graph data can be manipulated intuitively with abbreviated field names and with both read and write operations.

Transactions and scopes 
--

When ONDEProxy replaces an object with a modified copy, objects have to be replaced up the access chain because repointing a reference is itself a modification. With multiple changes that need to happen in a multi-threaded environment, simultaneity is important and therefore changes are grouped into transactions. For simple one line notifications the transaction is created automatically and implicitly, then ended when the change is complete. You can also create a transaction explicitly for use in a python context manager ("with" clause) ::
  
  with ONDETransaction(graph,include_paths=[...]) as tr:
      tr.graph[...].LABEL="New dataset"
      # More grouped changes here
      pass
    
(Note that the tr object here is not actually the transaction object created but the scope object resulting from the transaction)
 
In addition, there is a question as to what objects that point to the original get repointed to the copy. The default behavior is to assume the narrowest possible scope: that only access via the path you specified from the graph entry point will give the new value. However, sometimes a wider scope will be desirable.  For example, if modifying a ONDE_UT_PROBE, you want all of the laws that reference the probe as well as the geometric probe definition to change together. This is done by defining a broader scope. Scopes can be specified when creating a transaction, or within an existing transaction using class ONDEOpScope as a Python context manager ("with" clause) ::
  
  with ONDEOpScope(tr,include_paths=[...]) as sc:
      sc.graph[...].SETUP.GEOMETRIC_SETUP.SENSOR_LIST.FREQUENCY=2e6
      pass

The net result is fine grained control over the scope of changes. In general, you always want to select the narrowest sufficient scope. Be wary, for example, if datasets can reference other datasets from which they originated, of possibly changing those other datasets as well. For this reason, when creating a transaction or a scope, you can specify explicit exclusion paths to prevent modification of certain subgraphs.

The current version of PyONDE only propagates changes to other references to the same underlying object. This is because the current ONDE specification is silent on the definitions of object equality versus identity. A future version may well define object identity to be equality, and therefore a future version of PyONDE might well automatically change all objects that are in scope and equal to the one being changed, rather than the current behavior of changing all objects that are in scope and the same object as the one being changed. This is another reason why you always want to use the narrowest possible scope for any changes.
