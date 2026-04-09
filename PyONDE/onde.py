import h5py
import sys
import os
import os.path
import threading
import ast
import csv
import copy
import numbers
import collections
import collections.abc
from dataclasses import dataclass, field
import numpy as np

class TwoWayDictionary(object):
    """A dictionary that is indexable by strings using
    getattr() or dot notation to get objects. Can be
    reverse indexed by those objects using bracket notation
    to get strings, which will return a tuple because
    multiple index values can point to the same object."""
    _bystrings = None # String index dictionary, contains objects
    _byobjid = None # id(object) dictionary, contains frozensets of strings
    _lock = None # threading.Lock object protecting _bystrings and _byobjid from changes. This lock is last in the locking order, ie you may not acquire any other lock while holding this lock.
    _frozen = None # Boolean. Dictionary cannot be modified once frozen
    
    def __init__(self, bystrings=None):
        """Pass an existing dictionary or None as bystrings"""
        if bystrings is None:
            bystrings = {}
            pass

        if isinstance(bystrings, TwoWayDictionary):
            bystrings = object.__getattribute__(bystrings, "_bystrings")
            pass
        
        object.__setattr__(self, "_bystrings", dict(bystrings))
        byobjid = dict()
        for s in bystrings:
            obj = bystrings[s]
            
            if obj is not None:
                if id(obj) in self._byobjid:
                    idx_set = self._byobjid[id(obj)]
                    pass
                else:
                    idx_set = frozenset()
                    pass
                
                byobjid[id(obj)] = idx_set | { s }
                pass
            pass
        object.__setattr__(self, "_byobjid",byobjid)
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_frozen", False)
        pass

    def __iter__(self):
        _bystrings = object.__getattribute__(self, "_bystrings")
        return _bystrings.__iter__() # Just use iterator of underlying dictionary

    def __getattribute__(self, name):
        if name.startswith("_"):
            if name == "_freeze" or name == "_frozen":
                return object.__getattribute__(self, name)
            raise IndexError("TwoWayDictionary: Indexes are not allowed to have leading underscores")

        _get_attr = object.__getattribute__(self, "_get_attr")

        return _get_attr(name)

    def __call__(self, obj):
        _byobjid = object.__getattribute__(self, "_byobjid")
        objidx = _byobjid[id(obj)]
        return objidx # Returns frozenset
    
    
    def __setattr__(self, name, value):
        _set_attr = object.__getattribute__(self, "_set_attr")
        _set_attr(name, value)

        pass

    def _set_attr(self, name, value):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")
        _bystrings = object.__getattribute__(self, "_bystrings")
        _byobjid = object.__getattribute__(self, "_byobjid")
        _lock = object.__getattribute__(self, "_lock")
        _frozen = object.__getattribute__(self, "_frozen")

        if _frozen:
            raise AttributeError("Not allowed to modify a frozen TwoWayDictionary")
        with _lock:
            if name in _bystrings:
                # Remove old back-reference
                oldobj = _bystrings[name]
                _byobjid[id(oldobj)] = _byobjid[id(oldobj)] - frozenset({name})
                pass
            
            _bystrings[name] = value

            nameset = frozenset({name})
            # Check if this object already has an existing set of references
            if id(value) in _byobjid:
                nameset = _byobjid[id(value)] | nameset
                pass
            _byobjid[id(value)] = nameset
            pass
        pass

    def _get_attr(self, name):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _bystrings = object.__getattribute__(self, "_bystrings")
        return _bystrings[name]

    def _freeze(self):
        object.__setattr__(self, "_frozen", True)
        pass
    pass

class TwoWayArray(object):
    """An Array that is indexable by integers using
    bracket notation. Can be
    reverse indexed by those objects using parenthesis notation
    to get index tuples, which will be wrapped in another layer
    of tuple because
    multiple index values can point to the same object."""
    _byindex = None # numpy array, contains objects
    _byobjid = None # id(object) dictionary, contains frozensets of strings
    _lock = None # threading.Lock object protecting _byindex and _byobjid from changes. This lock is last in the locking order, ie you may not acquire any other lock while holding this lock.
    _frozen = None # Boolean. Dictionary cannot be modified once frozen

    def __init__(self, byindex=None,shape = None):
        """Pass an existing array or None as byindex"""
        if shape is None:
            shape = ()
            pass
        
        if byindex is None:
            byindex = np.zeros(shape,dtype="O")
            pass

        if isinstance(byindex, TwoWayArray):
            byindex = byindex.byindex
            pass

        self._byindex = copy.copy(byindex)
        self._byobjid = {}
        nditer = np.nditer(self._byindex, flags = ("multi_index","refs_ok"))
        for objarray in nditer:
            obj = objarray[()]
            if obj is not None:
                if id(obj) in self._byobjid:
                    idx_set = self._byobjid[id(obj)]
                    pass
                else:
                    idx_set = frozenset()
                    pass
                
                self._byobjid[id(obj)] = idx_set | { tuple(nditer.multi_index) }
                pass
            pass

        self._lock = threading.Lock()
        self._frozen = False
                
        pass

    def __iter__(self):
        return np.nditer(self._byindex,flags=("multi_index","refs_ok")) # Just use iterator of underlying array

    def __getitem__(self, index):
        
        return self._byindex[index]


    def __call__(self, obj):
        objidx = self._byobjid[id(obj)]
        return objidx # Returns frozenset
    
    
    def __setitem__(self, index, obj):
        if not isinstance(index,tuple):
            index = (index,)
            pass

        if self._frozen:
            raise AttributeError("Not allowed to modify a frozen TwoWayArray")
        with self._lock:
            oldobj = self._byindex[index]
            if  oldobj is not None:
                # Remove old back-reference
                self._byobjid[id(oldobj)] = self._byobjid[id(oldobj)] - frozenset({tuple(obj)})
                pass
            
            self._byindex[index] = obj

            indexset = frozenset({index})
            # Check if this object already has an existing set of references
            if id(obj) in self._byobjid:
                indexset = self._byobjid[id(obj)] | indexset
                pass
            self._byobjid[id(obj)] = indexset
            pass
        pass

    def _freeze(self):
        self._byindex.writable = False
        self._frozen = True
        pass
    pass


class ONDEGraph(object):
    """Represents the graph of interconnected ONDE objects
    and attributes. May relate to any number of actual files."""
    _lock = None # threading.Lock that protects access to replace the snapshot.
    _latest_snap = None # class ONDEGraphSnapshot

    def __init__(self, snapshot = None):
        # self._lock = threading.Lock()
        object.__setattr__(self, "_lock", threading.Lock())

        if snapshot is None:
            snapshot = ONDEGraphSnapshot.new()

            pass

        # self._latest_snap = snapshot
        object.__setattr__(self, "_latest_snap", snapshot)

        pass
    
    def __getattribute__(self, name):
        _get_attr = object.__getattribute__(self, "_get_attr")
        return _get_attr(name)
    
    def __setattr__(self, name, value):
        _set_attr = object.__getattribute__(self, "_set_attr")
        _set_attr(name, value)
        pass

    def _get_attr(self, name):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")
        
        _latest_snap = object.__getattribute__(self, "_latest_snap")
        
        # call ONDEProxy
        
        snap_proxy = ONDEProxy.new_from_snapshot(self, _latest_snap)
        obj_proxy = ONDEProxy.new_from_proxy(snap_proxy, name)

        return _latest_snap._get_attr(name)
    
    # def _set_attr(self, name, value):
    #     if name.startswith("_"):
    #         raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

    #     _latest_snap = object.__getattribute__(self, "_latest_snap")
        
    #     return _latest_snap._get_attr(name)


    pass


class ONDETransaction(object):
    """Represents a transaction in which the ONDEGraph is modified"""
    graph = None # ONDEGraph object
    scope = None
    snap = None # This is the snapshot we're modifying

    def __init__(self, graph, include_scope=None, exclude_scope=None):
        self.graph = graph
        self.scope = ONDEOpScope(include_scope, exclude_scope)
        
        pass

    def __enter__(self):
        _lock = object.__getattribute__(self.graph, "_lock")
        _lock.acquire()

        snap = object.__getattribute__(self.graph, "_latest_snap")
        self.snap = ONDEGraphSnapshot(_orig=snap) # Create mutable copy of most recent snapshot
        
        return ONDEProxy.new_from_transaction(self)

    def __exit__(self, exc_type, exc, tb):
        self.snap._freeze()
        object.__setattr__(self.graph, "_latest_snap",self.snap)
        _lock = object.__getattribute__(self.graph, "_lock")
        _lock.release()

        pass

    pass


class ONDEOpScope(object):
    """Represents scope of an operation. This includes a list of paths originating at entry points that are included in the scope, and an overriding list of paths originating at entry points that are excluded from the scope"""
    include_paths = None # List of ONDEPath objects
    exclude_paths = None # frozenset of ONDEPath objects
    exclude_objects = None #  frozenset of objects to be excluded

    def __init__(self, include_paths, exclude_paths = None, exclude_objects = None):
        self.include_paths = include_paths
        if exclude_paths is None:
            exclude_paths = []
            pass
        self.exclude_paths = frozenset(exclude_paths)
        
        if exclude_objects is None:
            exclude_objects = []
            pass
        self.exclude_objects = frozenset(exclude_objects)
        pass
        
    def __hash__(self):
        return hash((tuple(self.include_paths), self.exclude_paths, self.exclude_objects))
        
    # to do: the paths in the onde op scope will generally end with an
    # attribute name or an array index and the scope starts from only that
    # attribute of the object

    pass


class ONDEPath(tuple):
    """A path, essentially a tuple of strings or indexes/tuples, starting
    with an entry_point name and followed by attribute names
    for ONDEObjects or ONDEReferenceArray indexes, that leads to an ONDEBase.

    An ONDEPath is evaluated by calling the _follow_path method on the object it is relative to, passing the path as the parameter."""

    def __new__(cls, *args, **kwargs):
        return super().__new__(cls,*args, **kwargs)

    pass

class ONDEBase(object):
    # _graph = None # ONDEGraph object
    _referencedby = None # set of ONDEBase objects that reference this object. They should all be part of the given ONDEGraph. The _referencedby member can still be changed even after an instance is frozen becuase new objects can reference it. Note that the _referencedby field is generally only updated to include new objects when those objects become frozen.
    _frozen = None # True/False: has this object been finalized and therefore become immutable
    _modification_scopes = None # A set of scopes for which the ancestor nodes in the graph have been replaced for the transaction in which this node is being updated. It is only valid for use within the context of the transaction in which the node is being created and it is cleared when the node is frozen.

    def __init__(self, _orig = None, **kwargs):
        _referencedby = None
        #if _orig is not None:
        #    _referencedby = object.__getattribute__(_orig, "_referencedby")
        #    pass
        if "_referencedby" in kwargs:
            _referencedby = kwargs["_referencedby"]
            del kwargs["_referencedby"]
            pass
        _frozen = False
        if "_frozen" in kwargs:
            _frozen = kwargs["_frozen"]
            del kwargs["_frozen"]
            pass
        if len(kwargs) > 0:
            raise AttributeError(f"Unknown constructor parameters to {self.__class__.__name__:s}: {str(list(kwargs.keys())):s}")
        if _referencedby is None:
            _referencedby = set()
            pass
        object.__setattr__(self, "_referencedby", _referencedby)
        object.__setattr__(self, "_frozen", False)
        if _frozen:
            self._freeze() # Derived class may have additional operations
            pass
        else:
            object.__setattr__(self, "_modification_scopes", set())
            pass
        pass

    def _get_attr(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        raise ValueError("ONDEBase does not have attributes")
    
    def _set_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """

        raise ValueError("ONDEBase does not have attributes")

    def __copy__(self):
        new = self.__class__(self)
        return new

    def __hash__(self):
        return id(self) # For now we identify ourself by our pointer. In the future perhaps we might use a content hash.
    
    def _freeze(self):
        _frozen = object.__getattribute__(self, "_frozen")
        if _frozen:
            raise RuntimeError("Attempting to freeze an object that is already frozen")
        object.__setattr__(self, "_modification_scopes", None)
        object.__setattr__(self, "_frozen", True)
        pass

    def _add_referencedby(self, obj_that_references_us):
        _referencedby = object.__getattribute__(self, "_referencedby")
        _referencedby.add(obj_that_references_us)
        pass

    def _follow_path(self, path):
        if len(path) == 0:
            return self

        raise AttributeError(f"{self.__class__.__name__} is a leaf node attempting to follow path {str(path)}")

    def _list_edges(self):
        return []
        
    @classmethod
    def new(cls):
        raise RuntimeError("ONDEBase class is not independently instantiatable")

    pass

class ONDEValue(ONDEBase):
    """ONDEValue represents a string, integer, float,
    or other simple value. An ONDEValue
    cannot reference other objects, but can be referenced
    by other objects."""
    value = None # Immutable value

    def __init__(self, _orig = None, **kwargs):
        if _orig is not None:
            self.value = _orig.value
            pass
        if "value" in kwargs:
            value = copy.copy(kwargs["value"])
            if isinstance(value, numbers.Integral):
                value = int(value)
                pass
            elif isinstance(value, numbers.Real):
                value = float(value)
                pass
            elif isinstance(value, numbers.Complex):
                value = complex(value)
                pass
            elif isinstance(value, str):
                pass
            else:
                raise ValueError(f"ONDEValue: Cannot understand value type {value.__class__.__name__:s}")
            del kwargs["value"]
            pass
        super().__init__(_orig, **kwargs)
        pass

    @classmethod
    def new(cls, value = None, **kwargs):
        return cls(None, value = value, **kwargs)
    
    def _get_attr(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        if name == "value":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEValue does not have attributes other than \"value\"")
    
    def _set_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """

        if name == "value":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEValue does not have attributes other than \"value\"")
    
    pass

class ONDEArray(ONDEBase):
    """ONDEArray represents an array. An ONDEArray
    cannot reference other objects, but can be referenced
    by other objects. For an array of references, see
    ONDEReferenceArray.

    An ONDEArray can be stored either as an HDF5
    attribute or an HDF5 dataset depending on the
    value of the store_as_dataset boolean.

    """
    value = None # numpy array
    store_as_dataset = None # boolean; store as an HDF5 dataset if True, otherwise and an HDF5 attribute
    
    def __init__(self, _orig = None, **kwargs):
        store_as_dataset = False
        
        if _orig is not None:
            value = _orig.value
            store_as_dataset = _orig.store_as_dataset
            pass

        
        if "store_as_dataset" in kwargs:
            store_as_dataset = bool(kwargs["store_as_dataset"])
            del kwargs["store_as_dataset"]
            pass
        
        if "value" in kwargs:
            value = copy.copy(kwargs["value"])
            if isinstance(value, collections.abc.Sequence):
                value = np.array(value)
                pass
            elif isinstance(value, np.ndarray):
                # value.flags.writeable = False
                pass
            else:
                raise ValueError(f"ONDEArray: Cannot understand value type {value.__class__.__name__:s}")
            del kwargs["value"]
            pass
        self.store_as_dataset = store_as_dataset
        self.value = value
        super().__init__(_orig, **kwargs)
        pass

    def __getitem__(self,index):
        return self.value[index]

    def __setitem__(self,index,el_value):
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        self.el_value[index] = el_value
        pass

    def _get_attr(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        if name == "value" or name == "store_as_dataset":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEArray does not have attributes other than \"value\" and \"store_as_dataset\"")
    
    def _set_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """

        if name == "value" or name == "store_as_dataset":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEArray does not have attributes other than \"value\" and \"store_as_dataset\"")

    def _freeze(self):
        self.value.flags.writeable = False
        super()._freeze()
        pass

    @classmethod
    def new(cls, value = None, **kwargs):
        return cls(None, value = value, **kwargs)
    
    pass


class ONDEReferenceArray(ONDEBase):
    """Represents an array of references to other ONDEObjects.

    An ONDEReferenceArray can be stored either as an HDF5
    attribute or an HDF5 dataset depending on the value
    of the store_as_dataset boolean."""
    refs = None # TwoWayArray of ONDEBase references
    store_as_dataset = None # True to store as an HDF5 dataset, False to store as an HDF5 attribute
    

    def __init__(self,_orig, **kwargs):
        """Private constructor for internal use only.
        Use .new() classmethod or copy.copy()
        """
        store_as_dataset = False
        refs = None
        if _orig is not None:
            refs = _orig.refs
            store_as_dataset = _orig.store_as_dataset
            pass

        
        if "store_as_dataset" in kwargs:
            store_as_dataset = bool(kwargs["store_as_dataset"])
            del kwargs["store_as_dataset"]
            pass
        
        shape = ()

        if "shape" in kwargs:
            shape = tuple(kwargs["shape"])
            del kwargs["shape"]
            pass
        
        if "refs" in kwargs:
            refs = TwoWayArray(byindex=kwargs["refs"])
            del kwargs["refs"]
            pass

        if refs is None:
            refs = TwoWayArray(shape=shape)
            pass
        
        self.store_as_dataset = store_as_dataset
        self.refs = refs
        super().__init__(_orig,**kwargs)
        pass

    def __getitem__(self,index):
        return self.refs[index]

    def __setitem__(self,index,ref):
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        self.refs[index] = ref
        pass

    def _get_attr(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        if name == "refs" or name == "store_as_dataset":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEReferenceArray does not have attributes other than \"refs\" and \"store_as_dataset\"")
    
    def _set_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """

        if name == "refs" or name == "store_as_dataset":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEReferenceArray does not have attributes other than \"refs\" and \"store_as_dataset\"")

    def _freeze(self):
        if self._frozen:
            raise RuntimeError("Attempting to freeze an object that is already frozen")
        self.refs._freeze()
        
        nditer = self.refs.iter()
        for arrayref in nditer:
            obj = arrayref[()]
            obj._add_referencedby(self)
            pass
        super()._freeze()
        pass

    def _follow_path(self, path):
        if len(path) == 0:
            return self

        path_entry = path[0]

        if isinstance(path_entry, numbers.Integral) or isinstance(path_entry, collections.abc.Sequence):
            return self.refs[path_entry]._follow_path(ONDEPath(path[1:]))
        else:
            raise AttributeError(f"Cannot index {self.__class__.__name__} by {path_entry}")
        
        pass

    def _list_edges(self):
        nditer = self.refs.iter() #np.nditer object
        sz = nditer.itersize()
        
        edgelist= []
        for cnt in range(sz):
            edgelist.append(nditer.multi_index)
            if cnt < sz-1:
                next(nditer)
                pass
            pass
        return edgelist
    
    @classmethod
    def new(cls, refs = None, shape = None, **kwargs):
        return cls(None, refs = refs, shape = shape, **kwargs)
    
    pass


class ONDEObject(ONDEBase):
    """ONDEObject represents a (non-leaf) node in the graph
    that can point at other objects."""
    _ONDE_type = None # List of classes starting with base class
    _ONDE_attrs = None # TwoWayDictionary by name of attributes that should be ONDEBase (or subclass) objects

    def __init__(self, _orig, **kwargs):
        """Private constructor for internal use only.
        Use .new() classmethod or copy.copy()
        """
        
        _ONDE_type = None
        if _orig is not None:
            _ONDE_type = object.__getattribute__(_orig, "_ONDE_type")
            pass
        if "_ONDE_type" in kwargs:
            _ONDE_type = kwargs["_ONDE_type"]
            del kwargs["_ONDE_type"]
            pass

        _ONDE_attrs = None
        if _orig is not None:
            _ONDE_attrs = object.__getattribute__(_orig, "_ONDE_attrs")
            pass
        if "_ONDE_attrs" in kwargs:
            #if _ONDE_attrs is not None:
            #    _ONDE_attrs.update(kwargs["_ONDE_attrs"])
            #    pass
            #else:
            _ONDE_attrs = kwargs["_ONDE_attrs"]
            #    pass
            del kwargs["_ONDE_attrs"]
            pass
        
        
        object.__setattr__(self, "_ONDE_type", list(_ONDE_type))
        ONDE_attrs = TwoWayDictionary(_ONDE_attrs)
        object.__setattr__(self, "_ONDE_attrs", ONDE_attrs)
        super().__init__(_orig, **kwargs)
        pass

    def __getattribute__(self, name):
        if name.startswith("_"):
            if name in {"_freeze", "_frozen", "_add_referencedby", "__class__", "__dir__", "_get_attr", "_set_attr"}:
                return object.__getattribute__(self, name)
            raise IndexError("ONDEObject: Attributes may not have leading underscores")

        _get_attr = object.__getattribute__(self, "_get_attr")
        
        return _get_attr(name)

    def __setattr__(self, name, value):
        _frozen = object.__getattribute__(self, "_frozen")
        if _frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")
        
        _set_attr = object.__getattribute__(self, "_set_attr")
        _set_attr(name, value)

        pass

    def _get_attr(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """
        
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")

        return _ONDE_attrs._get_attr(name)
    
    def _set_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """

        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")

        return _ONDE_attrs._set_attr(name, value)

    def __dir__(self):
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        return ["_freeze","_frozen"] + [attrname for attrname in _ONDE_attrs]
    
    def _freeze(self):
        _frozen = object.__getattribute__(self, "_frozen")
        if _frozen:
            raise RuntimeError("Attempting to freeze an object that is already frozen")
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        _ONDE_attrs._freeze()
        for attrname in _ONDE_attrs:
            obj = getattr(_ONDE_attrs, attrname)
            obj._add_referencedby(self)
            pass
        
        super()._freeze()
        pass

    def _follow_path(self, path):
        if len(path) == 0:
            return self

        path_entry = path[0]

        if isinstance(path_entry, str):
            return self._get_attr(path_entry)._follow_path(ONDEPath(path[1:]))
        else:
            raise AttributeError(f"Cannot index {self.__class__.__name__} by {path_entry}")
        
        pass

    
    def _list_edges(self):
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        edgelist= list(_ONDE_attrs.keys())
        return edgelist
    
    @classmethod
    def new(cls, _ONDE_type = None, _ONDE_attrs = None, **kwargs):
        """Main constructor to call"""
        constructargs = {}
        if _ONDE_type is not None:
            constructargs["_ONDE_type"] = _ONDE_type
            pass
        if _ONDE_attrs is not None:
            constructargs["_ONDE_attrs"] = _ONDE_attrs
            pass
        newobj = cls(None, **constructargs)
        for attrname in kwargs:
            setattr(newobj, attrname, kwargs[attrname])
            pass
        return newobj
    pass

class ONDEGraphSnapshot(ONDEObject):
    """ Not allowed to be referenced by any other ONDEObject.
    The _ONDE_type field should be empty.
    Attributes represent entry points of the graph."""
    def __init__(self, _orig = None, **kwargs):
        super().__init__(_orig, **kwargs)
        pass

    #@classmethod
    #def new(cls, entry_points = None):
    #    if entry_points is None:
    #        entry_points = TwoWayDictionary()
    #        pass
    #    return cls(None, _ONDE_type = [], _ONDE_attrs = entry_points)
    @classmethod
    def new(cls, **kwargs):
        _frozen = False
        if "_frozen" in kwargs:
            _frozen = kwargs["_frozen"]
            del kwargs["_frozen"]
            pass
        newobj = cls(None, _ONDE_type = [])
        for attrname in kwargs:
            newobj._set_attr(attrname, kwargs[attrname])
            pass
        if _frozen:
            newobj._freeze()
            pass
        return newobj
    pass

class ONDEField(object):
    """Represents a field from the .csv spec."""

    defining_class = None # Name of the defining class
    class_prefix = None # Prefix on the field
    name = None # Field name, not including prefix or separating colon
    comments = None # Documentation string
    mandatory = None # True for mandatory attributes/datasets
    dataset = None # True for dataset storage, False for attribute storage
    content_class_string = None # Referenced type
    dimensionality_string = None # Dimensionality field from .csv
    size_or_content_string = None # Value field from .csv

    def __init__(self, **kwargs):
        for arg in kwargs:
            if hasattr(self, arg):
                setattr(self, arg, kwargs[arg])
                pass
            else:
                raise ValueError(f"ONDEField; unknown attribute {arg:s}")
            pass
        pass

    @classmethod
    def from_csv_line(cls, row, class_derivation):
        (classname, name, comments, mandatory_optional, dataset_attribute, content_class, dims, size_or_content) = row

        name_split = name.split(":")
        class_prefix = name_split[0]
        class_derivation = (classname,) if class_derivation is None else class_derivation

        if len(name_split) != 2:
            raise ValueError(f"Field name {name:s} should have one colon")

        if class_prefix not in class_derivation and not (class_prefix == "ONDE" and name in ["ONDE:LABEL", "ONDE:TYPE_TAGS"]):
            raise ValueError(f"Mismatch between class name or super classes and prefix defining {name:s}")
        
        if mandatory_optional not in ["M", "O"]:
            raise ValueError(f"Mandatory/Optional field is not either O or M defining {name:s}")
        
        if dataset_attribute not in ["D", "A"]:
            raise ValueError(f"Dataset/Attribute field is not either D or A defining {name:s}")
        
        name_only = name_split[1]
        mandatory = mandatory_optional == "M"
        dataset = dataset_attribute == "D"

        return cls(
            defining_class=classname,
            class_prefix=class_prefix,
            name=name_only,
            comments=comments,
            mandatory=mandatory,
            dataset=dataset,
            content_class_string=content_class,
            dimensionality_string=dims,
            size_or_content_string=size_or_content
        )
    pass
    

class ONDEAccessoryClass(object):
    """Represents an accessory class defined in the ONDE .csv spec."""

    classname = None # Name of the accessory class
    attributes = None # Dictionary by name of ONDEField references
    comments = None # Comments about thhis class (sourced from the .csv file)

    def __init__(self):
        self.attributes = collections.OrderedDict()
        pass
    pass

class ONDEClass(object):
    """Represents a class defined in the ONDE .csv spec."""
    classname = None
    class_derivation = None # tuple of strings starting with base class and ending with this current class
    superclass = None # Reference the ONDEClass object for our superclass, or None
    type_tags = None # Dictionary by name of (truth value for mandatory, ONDEAccessoryClass object)
    attributes = None # Dictionary by name of ONDEField references
    comments = None # Comments about thhis class (sourced from the .csv file)

    def __init__(self):
        self.attributes = collections.OrderedDict()
        pass
    pass

class ONDEClassInstanceWrapper(object):
    """Represents an ONDEObject that is an instance of a known class. References the underlying ONDEObject and the class definition."""

    pass

class ONDEClassDefinitions(object):
    """Represents the set of class definitions from the ONDE .csv file."""
    classes = None # Dictionary by name of classes
    acc_classes = None # Dictionary by name of accessory classes
    file_type = None # From the size_or_content of the blank ONDE:TYPE entry at the top of the csv file
    
    def __init__(self):
        self.classes = collections.OrderedDict()
        self.acc_classes = collections.OrderedDict()
        pass

    @classmethod
    def load_from_csv(cls, filename):
        class_defs = ONDEClassDefinitions()
        
        with open(filename,mode="r",encoding="utf-8") as csvfh:
            reader = csv.reader(csvfh, delimiter=";")

            for row in reader:
                if len(row) < 8:
                    row += [""]*(8-len(row))
                    pass

                stripped_row = [col.strip() for col in row]
                (classname, name, comments, mandatory_optional, dataset_attribute, content_class, dims, size_or_content) = stripped_row

                if classname == "Class":
                    # header csv line
                    continue

                if classname == "" and name == "ONDE:VERSION":
                    # to do: store version
                    continue

                if name == "ONDE:TYPE":
                    # class definition
                    if classname in class_defs.classes:
                        raise ValueError(f"Class {classname:s} multiply defined in {filename:s}")
                    newclass = ONDEClass()
                    newclass.classname = classname
                    newclass.comments = comments
                    # size_or_content should be a list of base classes terminated with this class, written roughly like a python list of strings
                    baseclasses = ast.literal_eval(size_or_content)
                    assert(type(baseclasses) is list)
                    if classname == "":
                        # Blank ONDE:TYPE entry specifying the file type
                        assert(len(baseclasses) == 1)
                        assert(type(baseclasses[0]) is str)
                        class_defs.file_type = baseclasses[0]
                        superclasses = []
                        superclass_def = None
                        pass
                    else:
                        assert(baseclasses[-1] == classname)

                        # check superclasses
                        superclasses = baseclasses[:-1]

                        if len(superclasses) > 0:
                            immediate_superclass = superclasses[-1]
                            if immediate_superclass not in class_defs.classes:
                                raise ValueError(f"Superclass {immediate_superclass:s} of {classname:s} in {filename:s} is unknown")
                            superclass_def = class_defs.classes[immediate_superclass]
                            # Superclass definition list of class names should match our superclasses
                            if tuple(superclasses) != superclass_def.class_derivation:
                                raise ValueError(f"Superclass {immediate_superclass:s} derviation {str(superclass_def.class_derivation):s} does not match superclass list {str(tuple(superclasses)):s} from class {classname:s} in csv file {filename:s}")
                            pass
                        else:
                            superclass_def = None
                            pass
                        pass
                    
                    newclass.class_derivation = tuple(superclasses) + (classname,)
                    newclass.superclass = superclass_def # ONDEClassObject
                    class_defs.classes[classname] = newclass
                    pass

                elif name == "ONDE:TYPE_TAGS" and classname not in class_defs.classes:
                    # accessory class definition

                    if classname in class_defs.acc_classes:
                        raise ValueError(f"Accessory class {classname:s} multiply defined in {filename:s}")

                    newclass = ONDEAccessoryClass()
                    newclass.classname = classname
                    newclass.comments = comments
                    # size_or_content should be a list of base classes terminated with this class, written roughly like a python list of strings
                    acc_classes = ast.literal_eval(size_or_content)

                    assert(type(acc_classes) is list)
                    assert(len(acc_classes) == 1)
                    assert(acc_classes[0] == classname)

                    class_defs.acc_classes[classname] = newclass

                    pass

                else:
                    # populating class with a field

                    class_derivation = None
                    class_or_acc = None

                    if classname in class_defs.classes:
                        class_or_acc = class_defs.classes[classname]
                        class_derivation = class_or_acc.class_derivation
                        pass
                    elif classname in class_defs.acc_classes:
                        class_or_acc = class_defs.acc_classes[classname]
                        pass
                    else:
                        raise ValueError(f"Class {classname:s} not found; not a known Class or AccessoryClass while defining attribute {name:s}")

                    if name in class_or_acc.attributes:
                        raise ValueError(f"Attribute {name} already in Class or AccessoryClass")
                    

                    class_or_acc.attributes[name] = ONDEField.from_csv_line(stripped_row, class_derivation)

                    pass
                pass
            pass
        
        return class_defs
    pass


@dataclass
class ScopeNode(object):
    referrers: Optional[set[ONDEBase]]=field(default_factory=set) # Set of referring objects.
    edges: Optional[set[Any]]=field(default_factory=set) # Set of edge indexes. If it is None, then all edges are in scope. Usually either each edge index is either a string for an ONDEObject or a tuple of integers for an ONDEReferenceArray.
    pass

def graph_replace_node__walk(starting_path, starting_obj,referring_obj, scope, scope_nodes, trans):
    """Trans is a transaction that has a mutable graph snapshot.

    scope_nodes is a mutable dictionary, which may be already partially prepopulated, indexed by node, of ScopeNode instances.

    scope is an ONDEOpScope.
    starting_obj is the object corresponding to starting_path. It is not assumed to already be inserted into scope_nodes. It is assumed that starting_obj has already been checked against the exclude_objs of scope.
    starting_path is an ONDEPath indicating the full path of starting_obj. It is assumed that starting_path has been already checked against the include_paths of scope.

    Walk the graph starting at the given starting_path, ignoring explicitly excluded paths and nodes from the scope, while accumulating nodes into scope_nodes, keeping track of which edges are fair game (represented by a set corresponding to the node in scope_nodes), or where all edges are fair game (represented by None instead of the set)
    """

    snap = trans.snap

    # Register starting_obj into scope_nodes
    if starting_obj in scope_nodes:
        new=False
        scope_node = scope_nodes[starting_obj]
        pass
    else:
        new=True
        scope_node = ScopeNode()
        scope_nodes[starting_obj] = scope_node
        pass
    
    #if starting_scope_set is not None:
    # If we are traversing this object, then all edges are in scope, so we replace any set with None
    
    scope_node.edges = None
    scope_node.referrers.add(referring_obj)
    
    if new:
        edges = starting_obj._list_edges()

        for edge in edges:
            current_path = ONDEPath(starting_path + (edge,))
            current_obj = starting_obj._follow_path(ONDEPath((edge,)))

            if current_path in scope.exclude_paths:
                continue

            if current_obj in scope.exclude_objs:
                continue
        
            graph_replace_node__walk(current_path, current_obj, starting_obj,scope, scope_nodes, trans)
        
            pass
        pass
    pass


@dataclass
class ReplacedNode(object):
    replacement: Optional[ONDEBase]
    refersto: set[ONDEBase]=field(default_factory=set) # Set of objects this node refers to that we might want to replace.
    
    pass


def graph_replace_node__reversewalk(current_node,refersto,scope_nodes,changed_nodes):
    if current_node not in changed_nodes:
        new = True
        changed_nodes[current_node] = ReplacedNode()
        pass
    else:
        new = False
        pass
    
    changed_nodes[current_node].refersto.add(refersto)
    
    if new: 
        referrers = scope_nodes[current_node].referrers
        
        for referrer in referrers:
            if referrer in changed_nodes:
                continue

            graph_replace_node__reversewalk(referrer,current_node,scope_nodes,changed_nodes)
            pass
        pass
    pass
    
def graph_replace_node(trans, scope, path, orig_node, replacement_node):
    # to do: proposed algorithm:
    # 
    # step 1: follow each starting location path to its end; then, continue to walk the graph, ignoring explicitly excluded (edges or paths?) while accumulating all nodes into a dict (indexed by pre-existing nodes) of scope_nodes and keeping track of which edges are "fair game" for each node (i.e. all edges, if we were walking the graph, or edges called out explicitly in a starting location path)
    snap = trans.snap
    scope_nodes = collections.OrderedDict()
    scope_nodes[snap] = ScopeNode() # Give the snapshot itself a blank ScopeNode
    
    for starting_path in scope.include_paths:
        if starting_path in scope.exclude_paths:
            continue
        current_parent = snap
        current_path = ONDEPath((,))
        pending_path = starting_path
        current_scope_set = scope_nodes[snap].edges

        # Follow the starting path, element by element, because we need to accumulate all referrers into the scope dictionary.
        while len(current_path) < len(starting_path)-1:
            
        
            current_parent = current_parent._follow_path(ONDEPath(pending_path[0],))
            pending_path = ONDEPath(pending_path[1:])
            if current_parent in scope_nodes:
                current_scope_node = scope_nodes[current_parent]
                current_scope_set = current_scope_node.edges
                pass
            else:
                current_scope_node = ScopeNode()
                current_scope_set = current_scope_node.edges
                scope_nodes[current_parent] = current_scope_node
                pass
            current_scope_node.referrers.add(current_parent)
            pass

        
        if current_scope_set is not None:
            current_scope_set.add(starting_path[-1])
            pass
        
        starting_obj = starting_parent._follow_path(ONDEPath((starting_path[-1],)))
        if starting_obj in scope.exclude_objs:
            continue
        
        graph_replace_node__walk(starting_path, starting_obj, starting_parent, scope, scope_nodes, trans)
        pass
    
    #
    # step 2: identify the node to be changed within the set (if it's not included, the new node is not referenced)
    #
    if not orig_node in scope_nodes:
        return
    # step 3: reverse walk the set of nodes, starting at the node to be changed, identifying these nodes into a new (and probably smaller) dict called changed_nodes, the keys of which are a set of nodes through which the change will propagate while the values are ReplacedNode objects with the replacement set to None
    #
    changed_nodes = collections.OrderedDict()

    current_node = orig_node

    graph_replace_node__reversewalk(current_node,,scope_nodes,changed_nodes)

    

    
    # step 4: iterate through the second set creating a replacement for each where we update changed_nodes, populating each entry's value with the replacement stored in a ReplacedNode object
    #
    changed_node_indexes = list(changed_nodes.keys())
    
    for changed_node in changed_node_indexes:
        if changed_node is not orig_node:
            # check to see if the changed node is frozen; if has modification scopes been cleared?
            if changed_node._modification_scopes is None:
                replacement = changed_node.__class__(_orig = changed_node)
                pass
            else:
                replacement = changed_node
                pass

            replacement._modification_scopes.add(scope)

            pass
        else:
            replacement = replacement_node
            pass
        changed_nodes[changed_node] = replacement
        pass
        


    
    # step 5: iterate through the replacements, identifying every "fair game" reference to changed_nodes, and re-pointing that to the replacements
    #

    for replaced_node in changed_nodes:
        replacement = changed_nodes[replaced_node].replacement
        scope_node = scope_nodes[replaced_node]
        fair_game_edges = scope_node.edges
        refersto = changed_nodes[replaced_node].refersto
        # refersto is a set of ONDEBase that includes all of the outgoing-referenced-objects reffered to by replacement that may need to be repointed at a newly created copy that is findable by changed_nodes
        # Only those edges listed in fair_game_edges (or all edges if fair_game_edges is None) need to be swapped out.

    # step 6: the result is potential replacement for the entry point for each scope starting location

    # implementation plan:
    # 
    # we need a set of node, with each node having a set of "fair game" edges, stored globally for this operation as a dict, indexed by nodes with the values being either None (all possible edges) or a set of edges identifiers
    # 
    # we also need a set of references of all scope nodes that point at any given scope node of intereset
    # 
    # for the task above, we'll need a ScopeNode class that has a set of "fair game" edges (or None indicating that all edges are fair game) and it will need a set of referring nodes; as we assemble the scope_nodes dictionary, any time we find a node that we have seen before, we add to the referring node set of the ScopeNode, rather than creating a new ScopeNode

    pass

class ONDEProxy(object):
    """Mutable proxy reference to a graph entry that remembers context."""
    _graph = None # ONDEGraph object we started with 
    _path = None # ONDEPath of the object we are proxying
    # _obj = None # The actual object we are proxying
    # _obj_snap = None # Snapshot from which we obtained _obj
    _trans = None # Transaction may be none not inside a transaction
    _scope = None # A scope separate from the one in _trans (if None, use the scope from _trans)
    _snap = None # Snapshot; only used if there is no transaction

    def __init__(self, **kwargs):
        __dict__ = object.__getattribute__(self, "__dict__")

        for arg in kwargs:
            if arg in __dict__:
                # setattr(self, arg, kwargs[arg])
                object.__setattr__(self, arg, kwargs[arg])

                pass
            else:
                raise ValueError(f"ONDEProxy; unknown attribute {arg:s}")
            pass
        pass

    @classmethod
    def new_from_proxy(cls, parent, attr_name):
        _graph = object.__getattribute__(parent, "_graph")

        # parent_obj = object.__getattribute__(parent, "_obj")
        # _obj = parent_obj._get_attr(attr_name)
        # _obj_snap = object.__getattribute__(parent, "_obj_snap")

        _parent_path = object.__getattribute__(parent, "_path")
        path = ONDEPath(_parent_path + [attr_name])

        _trans = object.__getattribute__(parent, "_trans")

        return cls(_graph=_graph, _path=path, _trans=_trans)

    @classmethod
    def new_from_snapshot(cls, graph, snapshot):
        path = ONDEPath()
        return cls(_graph=graph, _path=path, _snap=snapshot)
    
    @classmethod
    def new_from_transaction(cls, transaction):
        _graph = transaction.graph
        _path = ONDEPath()

        return cls(_graph=_graph, _path=_path, _trans=transaction)
    
    def _get_obj(self):
        trans = object.__getattribute__(self, "_trans")

        if trans is not None:
            snap = trans.snap
            pass

        else:
            snap = trans.graph._latest_snap
            pass

        _path = object.__getattribute__(self, "_path")
        return snap._follow_path(_path)

    def __getattribute__(self, name):
        _get_attr = object.__getattribute__(self, "_get_attr")
        return _get_attr(name)

    def _get_attr(self, name):
        obj = self._get_obj()
        attr_obj = obj._get_attr(name)

        if isinstance(attr_obj, ONDEBase):
            return self.__class__.new_from_proxy(self, name)

        return attr_obj
    

    def _set_attr(self, name, value):
        _trans = object.__getattribute__(self, "_trans")

        if _trans is None:
            _graph = object.__getattribute__(self, "_graph")

            # to do: need to add include and exclude scopes
            transaction = ONDETransaction(_graph)

            with transaction as proxy:
                # to do: proxy now has a potentially updated snapshot that we
                # should  use for the transaction. Need to use our path to
                # recreate our object and then call _set_attr on that.

                pass

            pass

        else:
            # to do: create replacement node that has the desired change
            # obj = object.__getattribute__(self, "_obj")
            
            # create a new object of obj's class, passing the original that we want to copy as its first constructor parameter; the ONDE classes are built to handle this
            _get_obj = object.__getattribute__(self, "_get_obj")
            obj = _get_obj()
            scope = object.__getattribute__(self, "_scope")

            if scope is None:
                scope = _trans.scope

            # if obj._frozen:
            if obj._modification_scopes is None:
                replacement = obj.__class__(_orig=obj)
                # object.__setattr__(replacement, "_modification_scopes", set([scope]))
                replacement._modification_scopes.add(scope)
                new = True
                pass
            else:
                replacement = obj
                new = False
                pass
                
            replacement._set_attr(name, value)
            #replacement._freeze() Freezing happens at the end of the transaction
            #if new: # We could avoid the replacement for preexisting modifications if we knew that the scope of the previous modification matched our scope.
            if new or scope not in obj._modification_scopes:
                replacement._modification_scopes.add(scope)
                graph_replace_node(_trans, scope, obj, replacement)
                pass

            pass

        pass

    pass


# rough api of transactions
# with ONDETransaction(graph, include_scope, exclude_scope) as transaction:
#     transaction.obj.attr = "hello"


#class ONDEOperation(object):
#    """Represents an operation that can be part of a transaction"""
#    scope = None # ONDEOpScope reference or None representing default (local) scope
#    pass


#class ONDEAssignValue(ONDEOperation):
#    """Represents assignment of the value within an ONDEValue object"""
#    attr_name = None # Usually "value"
#    attr_value = None # String, int, float, immutable array, etc.
#    pass
