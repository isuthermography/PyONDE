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
from typing import Optional, Any
import numpy as np

onde_basic_fields = {
            "ONDEValue":(
                "_freeze",
                "_frozen",
                "_get_attr",
                "_get_data",
                "_set_attr",
                "_set_data",
                "_has_attr",
                "value"
                ),
            "ONDEArray":(
                "_freeze",
                "_frozen",
                "_get_attr",
                "_get_data",
                "_set_attr",
                "_set_data",
                "_has_attr",
                "value"
                ),
            "ONDEReferenceArray":(
                "_freeze",
                "_frozen",
                "_get_attr",
                "_get_data",
                "_get_item",
                "_set_attr",
                "_set_data",
                "_set_item",
                "_has_attr",
                "refs"
                ),
            "ONDEObject":(
                "_freeze",
                "_frozen",
                "_get_attr",
                "_set_attr",
                "_has_attr",
                ),
            "ONDEGraphSnapshot":(
                "_freeze",
                "_frozen",
                "_get_attr",
                "_set_attr",
                "_has_attr",
                )
            }

def onde_from_python(value):
    if isinstance(value,numbers.Integral) or isinstance(value, numbers.Real) or isinstance(value,numbers.Complex) or  isinstance(value,str) or isinstance(value,np.str_):
        return onde.ONDEValue.new(value)

    if isinstance(value,collections.abc.Sequence):
        subvalues = []
        all_string = True
        all_numeric = True
        any_complex = False
        all_object = True
        for subvalue in value:
            if isinstance(value,str) or isinstance(value,np.str_):
                all_numeric = False
                all_object = False
                pass
            elif isinstance(value,numbers.Real):
                all_string = False
                all_object = False
                pass
            elif isinstance(value,numbers.Complex):
                all_string = False
                any_complex = True
                all_object = False
                pass
            elif isinstance(value,collections.abc.Sequence):
                all_string = False
                all_numeric = False
                value = onde_from_python(value)
                pass
            else:
                raise ValueError(f"Could not convert object of type {value.__class__.__name__:s} into an ONDE object")
            
            subvalues.append(value)
            pass

        if all_string and not(all_numeric) and not(all_object):
            dtype = np.StringDType()
            return ONDEArray.new(value = np.array(subvalues,dtype = dtype))
        elif all_numeric and not(all_string) and not(all_object):
            if any_complex:
                dtype = "D"
                pass
            else:
                dtype = "d"
                pass
            return ONDEArray.new(value = np.array(subvalues,dtype = dtype))
            
        elif all_object and not(all_string) and not(all_numeric):
            return ONDEReferenceArray.new(refs = np.array(subvalues,dtype = "O"))
        else:
            raise ValueError(f"Could not identify unique type for converting python object {str(value):s} into an ONDE object")
        pass
    
        
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
                if id(obj) in byobjid:
                    idx_set = byobjid[id(obj)]
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
            if name in {"_freeze", "_frozen", "_set_attr", "_get_attr", "_keys"}:
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

    def __setitem__(self,name,value):
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

    def __getitem__(self,name):

        return self._get_attr(name)
    
    def _freeze(self):
        object.__setattr__(self, "_frozen", True)
        pass

    def _keys(self):
        _bystrings = object.__getattribute__(self, "_bystrings")
        return _bystrings.keys()

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
    _lock_ownerthread = None # Writes protected by _lock, the threading.get_ident() of whichever thread owns the lock
    _latest_snap = None # class ONDEGraphSnapshot
    _class_defs = None # ONDEClassDefinitions, optional

    def __init__(self, _class_defs = None, _latest_snap = None):
        # self._lock = threading.Lock()
        object.__setattr__(self, "_lock", threading.Lock())

        if _latest_snap is None:
            _latest_snap = ONDEGraphSnapshot.new()

            pass
        
        object.__setattr__(self, "_class_defs", _class_defs)
        
        # self._latest_snap = snapshot
        object.__setattr__(self, "_latest_snap", _latest_snap)

        pass
    
    def __getattribute__(self, name):
        if name.startswith("_"):
            
            if name in {"_set_attr", "_get_attr","__dict__","__dir__","_latest_snap","_lock", "_class_defs"}:
                return object.__getattribute__(self, name)
            pass
        
        _latest_snap = object.__getattribute__(self, "_latest_snap")
        
        # call ONDEProxy
        
        snap_proxy = ONDEProxy.new_from_snapshot(self, _latest_snap)
        obj_proxy = ONDEProxy.new_from_proxy(snap_proxy, name)

        if self._class_defs is not None:
            return ONDEClassInstanceWrapper.new_from_proxy(obj_proxy)
        return obj_proxy
    
    def __setattr__(self, name, value):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")
        
        _latest_snap = object.__getattribute__(self, "_latest_snap")

        snap_proxy = ONDEProxy.new_from_snapshot(self, _latest_snap)

        snap_proxy._set_attr(name,value)

        pass

    def _get_attr(self, name):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")
        
        _latest_snap = object.__getattribute__(self, "_latest_snap")
        
        # call ONDEProxy
        
        snap_proxy = ONDEProxy.new_from_snapshot(self, _latest_snap)
        obj_proxy = ONDEProxy.new_from_proxy(snap_proxy, name)
        if self._class_defs is not None:
            return ONDEClassInstanceWrapper.new(obj_proxy)

        return obj_proxy # _latest_snap._get_attr(name)
    
    def _set_attr(self, name, value):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _latest_snap = object.__getattribute__(self, "_latest_snap")
        snap_proxy._set_attr(name,value)

        pass

    def _get_item(self, index):
        # Strictly shouldn't be necessary unless we shift to indexing the snapshot with numbers rather than strings
        _latest_snap = object.__getattribute__(self, "_latest_snap")
        
        # call ONDEProxy
        
        snap_proxy = ONDEProxy.new_from_snapshot(self, _latest_snap)
        obj_proxy = ONDEProxy.new_from_proxy(snap_proxy, index)
        if self._class_defs is not None:
            return ONDEClassInstanceWrapper.new(obj_proxy)

        return obj_proxy # _latest_snap._get_attr(name)
    
    def _set_item(self, index, value):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _latest_snap = object.__getattribute__(self, "_latest_snap")
        
        _latest_snap._set_item(index,value)
        pass

   
    def new_obj(self,onde_classname,**kwargs):
        if self._class_defs is not None:
            return ONDEClassInstanceWrapper.new_obj(self,onde_classname,**kwargs)
        return ONDEObject.new(ONDE_TYPE = onde_classname,_ONDE_attrs=None,**kwargs)

    @classmethod
    def new(cls,class_def_csv_path=None,snapshot=None):
        defs = None
        if class_def_csv_path is not None:
            defs = ONDEClassDefinitions.load_from_csv(class_def_csv_path)
            pass
        
        return cls(_class_defs = defs,_latest_snap=snapshot)
        
    pass


class ONDETransaction(object):
    """Represents a transaction in which the ONDEGraph is modified"""
    graph = None # ONDEGraph object
    scope = None
    snap = None # This is the snapshot we're modifying

    def __init__(self, graph, include_paths=None, exclude_paths=None,exclude_objects=None):
        self.graph = graph
        
        self.scope = ONDEOpScope(self,include_paths, exclude_paths,exclude_objects)

        
        pass

    def __enter__(self):
        lockowner = object.__getattribute__(self.graph, "_lock_ownerthread")
        if lockowner == threading.get_ident():
            raise RuntimeError(f"Error creating a new transaction while another transaction is already open on the graph by the same thread. This probably means that you are attempting a change on an object not accessed via the transaction. Within a transaction, always access objects via the transaction or scope objects.")
        _lock = object.__getattribute__(self.graph, "_lock")
        _lock.acquire()

        object.__setattr__(self.graph, "_lock_ownerthread", threading.get_ident())
        
        snap = object.__getattribute__(self.graph, "_latest_snap")
        self.snap = ONDEGraphSnapshot(_orig=snap) # Create mutable copy of most recent snapshot
        
        return self.scope

    
    def __exit__(self, exc_type, exc, tb):
        self.snap._freeze()
        object.__setattr__(self.graph, "_latest_snap",self.snap)
        object.__setattr__(self.graph, "_lock_ownerthread", None)
        _lock = object.__getattribute__(self.graph, "_lock")
        _lock.release()

        pass

    pass


class ONDEOpScope(object):
    """Represents scope of an operation. This includes a list of paths originating at entry points that are included in the scope, and an overriding list of paths originating at entry points that are excluded from the scope"""
    include_paths = None # List of ONDEPath objects, or None representing no scope specified
    exclude_paths = None # frozenset of ONDEPath objects
    exclude_objects = None #  frozenset of objects to be excluded
    trans = None # Transaction for this scope (warning: creates reference loop)
    
    def __init__(self, trans,include_paths=None, exclude_paths = None, exclude_objects = None):
        self.trans=trans
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

    def __enter__(self):

        return self

    def __exit__(self, exc_type, exc, tb):
        pass
        
    @property
    def graph(self):
        return ONDEProxy.new_from_scope(self)

    def rescope(self,include_paths=None, exclude_paths = None, exclude_objects = None):
        return type(self)(include_paths, exclude_paths, exclude_objects)
    
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

    def __getattribute__(self,name):
        if name.startswith("_"):
            if name in {"_freeze", "_frozen", "_add_referencedby", "__class__", "__dir__", "_get_attr", "_set_attr","_get_data","_set_data","_get_item","_set_item","_follow_path","_modification_scopes","_indices_for_object","_assign_pathel","_list_edges"}:
                return object.__getattribute__(self, name)
            raise IndexError("ONDEBase: Attributes may not have leading underscores")
        raise IndexError(f"ONDEBase: Unknown attribute {name:s}")

    def __setattr__(self, name, value):
        _frozen = object.__getattribute__(self, "_frozen")
        if _frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")
        # object.__setattr__(self,name,value)
        raise ValueError(f"ONDEBase is not mutable")
    
    # Attributes are other ONDEBase objects
    def _get_attr(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        raise ValueError("ONDEBase does not have attributes")

    def _has_attr(self, name):
        """
        Return whether the named conceptual attribute of an ONDE object exists.
        """

        return False
    
    def _set_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """

        raise ValueError("ONDEBase does not have attributes")

    # Items are indexed ONDEBase that we can access
    def _get_item(self,index):
        """Return the indexed data element of an ONDE object.
        """
        raise ValueError("ONDEBase does not have items")
    
    def _set_item(self,index,value):
        """Set the indexed data element of an ONDE object.
        """
        raise ValueError("ONDEBase does not have items")

    # Data are lower level objects such as arrays of numbers, integers, strings, etc.
    def _get_data(self,name):
        """Return the named data element of an ONDE object.
        """
        raise ValueError("ONDEBase does not have data")
    
    def _set_data(self,name,value):
        """Set the named data element of an ONDE object.
        """
        raise ValueError("ONDEBase does not have data")

   
        

    
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

    def _assign_pathel(self, pathel, value):
        raise AttributeError(f"{self.__class__.__name__} is a leaf node and does not support element assignment of {str(pathel)} to {str(value)}")
    
    def _list_edges(self):
        return []

    def _indices_for_object(self,obj):
        """identify all of the indices for self that reference object obj. Returns a frozenset."""
        return frozenset()
    
    
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
            elif isinstance(value, str) or isinstance(value,np.str_):
                value = str(value)
                pass
            else:
                raise ValueError(f"ONDEValue: Cannot understand value type {value.__class__.__name__:s}")
            self.value=value
            del kwargs["value"]
            pass
        super().__init__(_orig, **kwargs)
        pass

    def __getattribute__(self,name):
        if name == "value":
           
            _get_data = object.__getattribute__(self, "_get_data")
            return _get_data(name)

        return super().__getattribute__(name)

    def __setattr__(self,name,value):
        if name == "value":
            self._set_data(name,value)
            pass
        else:
            
            super().__setattr__(name,value)
            pass
        pass

    
    def _get_data(self, name):
        """
        Return the named conceptual data of an ONDE object.
        """

        if name == "value":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEValue does not have data other than \"value\"")
    
    def _set_data(self, name, value):
        """
        Set the named conceptual data of an ONDE object.
        """

        if name == "value":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEValue does not have data other than \"value\"")

    @classmethod
    def new(cls, value = None, **kwargs):
        return cls(None, value = value, **kwargs)
    
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

    def __getattribute__(self,name):
        if name == "value" or name == "store_as_dataset":
           
            _get_data = object.__getattribute__(self, "_get_data")
            return _get_data(name)

        return super().__getattribute__(name)

    def __setattr__(self,name,value):
        if name == "value" or name == "store_as_dataset":
            self._set_data(name,value)
            pass
        else:
            
            super().__setattr__(name,value)
            pass
        pass
   
    def __getitem__(self,index):
        return self.value[index]

    def __setitem__(self,index,el_value):
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        self.value[index] = el_value
        pass

    def _get_data(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        if name == "value" or name == "store_as_dataset":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEArray does not have attributes other than \"value\" and \"store_as_dataset\"")
    
    def _set_data(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

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
        return self._get_item(index)

    def __setitem__(self,index,ref):
        self._set_item(index,ref)
        pass

    def _get_data(self, name):
        """
        Return the named conceptual data of an ONDE object.
        """

        if name == "refs" or name == "store_as_dataset":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEReferenceArray does not have attributes other than \"refs\" and \"store_as_dataset\"")
    
    def _set_data(self, name, value):
        """
        Set the named conceptual data of an ONDE object.
        """

        if name == "refs" or name == "store_as_dataset":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEReferenceArray does not have attributes other than \"refs\" and \"store_as_dataset\"")

    def _get_item(self,index):
        return self.refs[index]

    def _set_item(self,index,ref):
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        if not isinstance(ref,ONDEBase):
            raise ValueError(f"Attempting to assign index {str(index)} of an ONDEReferenceArray to an object of class {ref.__class__.__name__} that is not an ONDEBase reference")

        self.refs[index] = ref
        pass


    
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

    def _assign_pathel(self, pathel, value):
        if self._frozen:
            raise RuntimeError(f"Cannot assign {str(value)} to {str(pathel)} element of frozen object")
        self.refs[pathel]=value
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

    def _indices_for_object(self,obj):
        """identify all of the indices for self that reference object obj. Returns a frozenset."""
        return self.refs(obj) # __call__ method does reverse lookup to return a set of indices 
    
    @classmethod
    def new(cls, refs = None, shape = None, **kwargs):
        return cls(None, refs = refs, shape = shape, **kwargs)
    
    pass


class ONDEObject(ONDEBase):
    """ONDEObject represents a (non-leaf) node in the graph
    that can point at other objects."""
    #ONDE_TYPE = None # List of classes starting with base class
    _ONDE_attrs = None # TwoWayDictionary by name of attributes that should be ONDEBase (or subclass) objects

    def __init__(self, _orig, **kwargs):
        """Private constructor for internal use only.
        Use .new() classmethod or copy.copy()
        """
        
        #ONDE_TYPE = None
        #if _orig is not None:
        #    ONDE_TYPE = object.__getattribute__(_orig, "ONDE_TYPE")
        #    pass
        #if "ONDE_TYPE" in kwargs:
        #    ONDE_TYPE = kwargs["ONDE_TYPE"]
        #    del kwargs["ONDE_TYPE"]
        #    pass

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
        
        
        #object.__setattr__(self, "ONDE_TYPE", tuple(ONDE_TYPE))
        ONDE_attrs = TwoWayDictionary(_ONDE_attrs)
        if not "ONDE_TYPE" in ONDE_attrs:
            ONDE_attrs["ONDE_TYPE"] = ()
            pass
        
        object.__setattr__(self, "_ONDE_attrs", ONDE_attrs)

        base_kwargs = {}
        for kwarg in kwargs:
            if kwarg.startswith("_"):
                base_kwargs[kwarg] = kwargs[kwarg]
                pass
            else:
                ONDE_attrs._set_attr(kwarg,kwargs[kwarg])
                pass
            pass
        super().__init__(_orig, **base_kwargs)
        pass

    def __getattribute__(self, name):
        if name.startswith("_"):
            if name in {"_freeze", "_frozen", "_add_referencedby", "__class__", "__dir__", "_get_attr", "_set_attr","_follow_path","_modification_scopes","_indices_for_object","_assign_pathel","_list_edges","_ONDE_attrs", "_has_attr"}:
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

    def _has_attr(self, name):
        """
        Return whether the named conceptual attribute of an ONDE object exists.
        """
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        if name in _ONDE_attrs:
            return True
        return False
    
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

    def _assign_pathel(self, pathel, value):
        if self._frozen:
            raise RuntimeError(f"Cannot assign {str(value)} to {str(pathel)} element of frozen object")
        self._set_attr(pathel, value)
        pass
    
    def _list_edges(self):
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        edgelist= list(_ONDE_attrs._keys())
        return edgelist

    def _indices_for_object(self,obj):
        """identify all of the indices for self that reference object obj. Returns a frozenset."""
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        return _ONDE_attrs(obj) # __call__ method does reverse lookup to return a set of indices
    
    @classmethod
    def new(cls, ONDE_TYPE = None, _ONDE_attrs = None, **kwargs):
        """Main constructor to call"""
        constructargs = {}
        if ONDE_TYPE is not None:
            constructargs["ONDE_TYPE"] = ONDE_TYPE
            pass
        if _ONDE_attrs is not None:
            constructargs["_ONDE_attrs"] = _ONDE_attrs
            pass
        constructargs.update(kwargs)
        newobj = cls(None, **constructargs)
        #for attrname in kwargs:
        #    setattr(newobj, attrname, kwargs[attrname])
        #    pass
        return newobj
    pass

class ONDEGraphSnapshot(ONDEObject):
    """ Not allowed to be referenced by any other ONDEObject.
    The ONDE_TYPE field should be empty.
    Attributes represent entry points of the graph."""
    def __init__(self, _orig = None, **kwargs):
        super().__init__(_orig, **kwargs)
        pass

    #@classmethod
    #def new(cls, entry_points = None):
    #    if entry_points is None:
    #        entry_points = TwoWayDictionary()
    #        pass
    #    return cls(None, ONDE_TYPE = [], _ONDE_attrs = entry_points)
    @classmethod
    def new(cls, **kwargs):
        _frozen = False
        if "_frozen" in kwargs:
            _frozen = kwargs["_frozen"]
            del kwargs["_frozen"]
            pass
        newobj = cls(None, ONDE_TYPE = ONDEArray.new([],_frozen = True))
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
    storage = None # "D" for dataset storage, "A" for attribute storage, "A or D" for either
    content_class_string = None # Referenced type
    dimensionality_string = None # Dimensionality field from .csv
    size_or_content_string = None # Value field from .csv
    min_val_string = None # Min field from .csv
    max_val_string = None # Max field from .csv

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
        (classname, name, comments, mandatory_optional, dataset_attribute, content_class, dims, size_or_content, min_val, max_val, accessory_class) = row

        name_split = name.split(":")
        class_prefix = name_split[0]
        class_derivation = (classname,) if class_derivation is None else class_derivation

        if len(name_split) != 2:
            raise ValueError(f"Field name {name:s} should have one colon")

        if class_prefix not in class_derivation and not (class_prefix == "ONDE" and name in ["ONDE:LABEL", "ONDE:TYPE_TAGS"]):
            raise ValueError(f"Mismatch between class name or super classes and prefix defining {name:s}")
        
        if mandatory_optional not in ["M", "O"]:
            raise ValueError(f"Mandatory/Optional field is not either O or M defining {name:s}")
        
        if dataset_attribute not in ["A", "D","A or D"]:
            raise ValueError(f"Dataset/Attribute field is not either D or A defining {name:s}")
        
        name_only = name_split[1]
        mandatory = mandatory_optional == "M"
        storage = dataset_attribute

        return cls(
            defining_class=classname,
            class_prefix=class_prefix,
            name=name_only,
            comments=comments,
            mandatory=mandatory,
            storage=storage,
            content_class_string=content_class,
            dimensionality_string=dims,
            size_or_content_string=size_or_content,
            min_val_string = min_val,
            max_val_string = max_val
        )
    pass
    

class ONDEAccessoryClass(object):
    """Represents an accessory class defined in the ONDE .csv spec."""

    classname = None # Name of the accessory class
    attributes = None # Dictionary by name of ONDEField references
    comments = None # Comments about this class (sourced from the .csv file)

    def __init__(self):
        self.attributes = collections.OrderedDict()
        pass
    pass

class ONDEClass(object):
    """Represents a class defined in the ONDE .csv spec."""
    classname = None
    class_derivation = None # tuple of strings starting with base class and ending with this current class
    superclass = None # Reference the ONDEClass object for our superclass, or None
    type_tags = None # Dictionary by name of truth value for mandatory
    attributes = None # Dictionary by name of ONDEField references
    comments = None # Comments about thhis class (sourced from the .csv file)

    def __init__(self):
        self.attributes = collections.OrderedDict()
        self.type_tags = collections.OrderedDict()
        pass
    pass

class ONDEClassInstanceWrapper(object):
    """Represents an ONDEObject that is an instance of a known class. References the proxy to the underlying ONDEObject and the class definition."""

    # only _proxy OR _obj can ever be set
    _proxy = None # an ONDEProxy for the ONDEObject instance
    _obj = None # an ONDEObject instance
    _graph = None # ONDEGraph, used only with _obj
    # _our_class = None # the ONDEClass instance
    
    def __init__(self, **kwargs):
        # _dict = object.__getattribute__(self, "__dict__")

        for arg in kwargs:
            if arg in type(self).__dict__:
                # setattr(self, arg, kwargs[arg])
                object.__setattr__(self, arg, kwargs[arg])

                pass
            else:
                raise ValueError(f"ONDEClassInstanceWrapper; unknown attribute {arg:s}")
            pass
        pass

    def _full_fieldname_from_attrname(self, _graph, obj, attrname):
        #_graph = object.__getattribute__(self,"_graph")
        if attrname in onde_basic_fields[obj.__class__.__name__]:
            return attrname
        
        if isinstance(obj,ONDEObject):
            classdefs = _graph._class_defs
            field_dict = classdefs.get_fields_dict(obj)
            if attrname in field_dict:
                field = field_dict[attrname]
                full_name = field.class_prefix + ":" + field.name
                return full_name
            else:
                raise NameError(f"Unknown attribute {attrname:s} on ONDEObject of type {obj._ONDE_attrs['ONDE_TYPE'].value[-1]:s}.")
            pass
        return attrname
            
    def _get_attr_or_item(self,get_method_name,key):

        _proxy = object.__getattribute__(self,"_proxy")
        _obj = object.__getattribute__(self,"_obj")
        _graph = object.__getattribute__(self,"_graph")

        if _proxy is not None:
            _obj = _proxy._get_obj()
            _graph = _proxy._graph
            pass
        
        full_name = key
        if get_method_name == "_get_attr":
            full_name = self._full_fieldname_from_attrname(_graph, _obj, key)
            if not _obj._has_attr(full_name):
                return None
            
            pass
        
        if _proxy is not None:
            get_method = getattr(_proxy,get_method_name)
            value = get_method(full_name) # e.g. _proxy._get_attr(key)
            if isinstance(value,ONDEProxy):
                value_obj = value._get_obj()
                if isinstance(value_obj,ONDEObject) or isinstance(value_obj,ONDEReferenceArray):
                    return self.__class__.new_from_proxy(value)
                return value
            return value
        else:
          
            get_method = getattr(_obj,get_method_name)
            value = get_method(full_name) # e.g. _obj._get_attr(name)

            if isinstance(value,ONDEObject) or isinstance(value,ONDEReferenceArray):
                
                value_wrapper = self.__class__.new_from_obj(cls,_graph,value)
                return value_wrapper
            else:
                
                return value
            pass
        pass

    def _get_attr(self,name):
        return self._get_attr_or_item("_get_attr",name)
            
    def _set_attr_or_item(self,set_method_name,key,value):
        our_proxy = object.__getattribute__(self,"_proxy")
        our_obj = object.__getattribute__(self,"_obj")
        _graph = object.__getattribute__(self,"_graph")

        if our_proxy is not None:
            our_obj = our_proxy._get_obj()
            _graph = our_proxy._graph
            pass
        
        full_name = key
        if set_method_name == "_set_attr":
            full_name = self._full_fieldname_from_attrname(_graph, our_obj, key)       
            pass
        
        if isinstance(value,ONDEClassInstanceWrapper):
            target_proxy = object.__getattribute__(value,"_proxy")
            target_obj = object.__getattribute__(value,"_obj")
            if our_proxy is not None and target_proxy is not None:
                set_method = getattr(our_proxy,set_method_name)
                set_method(full_name,_proxy) # self._proxy._set_attr(key,_proxy)
                pass
            elif self._proxy is not None and _obj is not None:
                set_method = getattr(self._proxy,set_method_name)
                set_method(full_name,_obj)
                pass
            elif self._obj is not None and _proxy is not None:
                set_method = getattr(self._obj,set_method_name)
                set_method(full_name,_proxy._get_obj()) # e.g. self._obj._set_attr(key,_proxy._get_obj())
                pass
            elif self._obj is not None and _obj is not None:
                set_method = getattr(self._obj,set_method_name)
                set_method(full_name,_obj)
                pass
            else:
                assert(False) # Exactly one of _obj and _proxy should be valid
                pass
            pass
        elif isinstance(value,ONDEProxy):
            if our_proxy is not None:
                set_method = getattr(our_proxy,set_method_name)
                set_method(full_name,value)
                pass
            elif our_obj is not None:
                set_method = getattr(our_obj,set_method_name)
                set_method(full_name,value._get_obj())
                pass
            else:
                assert(False)
                pass
            pass
        elif isinstance(value,ONDEBase):
            if our_proxy is not None:
                set_method = getattr(our_proxy,set_method_name)
                set_method(full_name,value)
                pass
            elif our_obj is not None:
                set_method = getattr(our_obj,set_method_name)
                set_method(full_name,value)
                pass
            else:
                assert(False)
                pass
            pass
        else:
            #raise ValueError(f"Attribute values should be ONDEBase or ONDEProxy or ONDEClassInstanceWrapper")
            #build an object from python structures
            target_obj = onde_from_python(value)
            if our_proxy is not None:
                set_method = getattr(our_proxy,set_method_name)
                set_method(full_name,target_obj)
                pass
            elif our_obj is not None:
                set_method = getattr(our_obj,set_method_name)
                set_method(full_name,target_obj)
                pass
            else:
                assert(False)
                pass
            pass
        pass

   
    
    def _set_attr(self,name,value):
        self._set_attr_or_item("_set_attr",name,value)
        pass

    def _get_item(self,index):
        return self._get_attr_or_item("_get_item",index)

    def _set_item(self,index,value):
        self._set_attr_or_item("_set_item",index,value)
        pass
    
    def _get_data(self,name):
        _proxy = object.__getattribute__(self,"_proxy")
        _obj = object.__getattribute__(self,"_obj")

        if _proxy is not None:
            value = _proxy._get_data(self,name)
            
            return value
        else:
            _graph = object.__getattribute__(self,"_graph")
            value = _obj._get_data(self,name)
            return value
        pass
    
    def _set_data(self,name,value):
        if isinstance(value,ONDEClassInstanceWrapper) or isinstance(value,ONDEBase) or isinstance(value,ONDEProxy):
            raise ValueError(f"_set_data(): value must not be an ONDEClassInstanceWrapper, a ONDEProxy, or an ONDEBase subclass")
        if self._proxy is not None:
            self._proxy._set_data(name,value)
            pass
        elif self._obj is not None:
            self._obj._set_data(name,value)
            pass
        else:
            assert(False)
            pass
        pass


    def __dir__(self):
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            pass
        else:
            obj = self._obj
            pass
     
        fields = onde_basic_fields[obj.__class__.__name__]
        if self._proxy is not None:
            _graph = self._proxy._graph
            pass
        else:
            _graph = self._graph
            pass
        
        classdefs = _graph._class_defs
        if classdefs is not None:

            if isinstance(obj, ONDEObject):
                fields +=  tuple(classdefs.get_fields_dict(obj).keys())
                pass
            pass
        
                
        return list(fields)
    
    def __getattribute__(self,name):
        if name.startswith('_'):
            return object.__getattribute__(self,name)
        
        return self._get_attr_or_item("_get_attr",name)
    obsolete = r"""
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            _graph = self._proxy._graph
            pass
        else:
            obj = self._obj
            _graph = self._graph
            pass

        field_dict = {}
        if isinstance(obj,ONDEObject):
            classdefs = _graph._class_defs
            field_dict = classdefs.get_fields_dict(obj)
            if name in field_dict:
                field = field_dict[name]
                full_name = field.class_prefix + ":" + field.name
                value = obj._ONDE_attrs[full_name]
                if self._proxy is not None:
                    valueproxy = _proxy._get_attr(full_name)
                    if isinstance(value,ONDEObject) or isinstance(value,ONDEReferenceArray):
                        return self.__class__.new_from_proxy(valueproxy)
                    else:
                        return valueproxy
                    pass
                else:
                    if isinstance(value,ONDEObject) or isinstance(value,ONDEReferenceArray):
                        return self.__class__.new_from_obj(self._graph, value)
                    else:
                        return value
                    pass
                pass
            pass
        else:
            assert(isinstance(obj, ONDEReferenceArray))
            value = obj._get_attr(name)
            
            if self._proxy is not None:
                valueproxy = _proxy._get_attr(name)
                if isinstance(value,ONDEObject) or isinstance(value,ONDEReferenceArray):
                    return self.__class__.new_from_proxy(valueproxy)
                else:
                    return valueproxy
                pass
            else:
                if isinstance(value,ONDEObject) or isinstance(value,ONDEReferenceArray):
                    return self.__class__.new_from_obj(self._graph, value)
                else:
                    return value
                pass
            pass
        assert(False)
        pass
"""
    def __setattr__(self,name,value):
        if name.startswith('_'):
            raise ValueError('Cannot assign attribute with leading underscore')
        self._set_attr_or_item("_set_attr",name,value)
        return
    obsolete = r"""
        if self._proxy is not None:
            if isinstance(value, ONDEClassInstanceWrapper):
                _proxy = value._proxy
                _obj = value._obj
                if _proxy is not None:
                    setattr(self._proxy, _proxy)
                    pass
                elif _obj is not None:
                    setattr(self._proxy, _obj)
                    pass
                else:
                    assert(False)
                    pass
                pass
            else:
                setattr(self._proxy, value)
                pass
            pass
        elif self._obj is not None:
            if isinstance(value, ONDEClassInstanceWrapper):
                _proxy = value._proxy
                _obj = value._obj
                if _proxy is not None:
                    setattr(self._obj, _proxy._get_obj())
                    pass
                elif _obj is not None:
                    setattr(self._obj, _obj)
                    pass
                else:
                    assert(False)
                    pass
                pass
            else:
                if isinstance(value, ONDEProxy):
                    setattr(self._obj, value._get_obj())
                    pass
                else:
                    setattr(self._obj, value)
                    pass
                pass
            pass
        else:
            assert(False)
            pass
        pass
                
"""                
        
            
            
    
    @classmethod
    def new_from_proxy(cls, proxy):
        obj = proxy._get_obj()
        if not isinstance(obj,ONDEObject) and not isinstance(obj,ONDEReferenceArray):
            raise ValueError(f"ONDEClassInstanceWrapper only wraps non-leaf nodes, not {obj.__class__.__name__}")
        return cls(_proxy=proxy)

    @classmethod
    def new_obj(cls, graph, onde_classname, **kwargs):
        if graph._class_defs is None:
            raise ValueError("Graph does not have class definitions loaded")
        
        onde_class = graph._class_defs.classes[onde_classname]
        obj = ONDEObject.new(ONDE_TYPE=onde_class.class_derivation, **kwargs)
        # proxy = ONDEProxy(_path=None)

        return cls(_graph=graph,_obj=obj)

    @classmethod
    def new_from_obj(cls,graph,obj):
        if not isinstance(obj,ONDEBase):
            raise ValueError(f"Given object is of type {obj.__class__.__name__:s} and is not an ONDEBase instance")

        # onde_classname = object.__getattribute__(_orig, "ONDE_TYPE")
        if graph._class_defs is None:
            raise ValueError("Graph does not have class definitions loaded")
        return cls(_graph=graph,_obj=obj)
        
    pass

class ONDEClassDefinitions(object):
    """Represents the set of class definitions from the ONDE .csv file."""
    #NOTE: Immutable once constructed, except for field cache
    classes = None # Dictionary by name of ONDEClass
    acc_classes = None # Dictionary by name of accessory classes
    file_type = None # From the size_or_content of the blank ONDE:TYPE entry at the top of the csv file

    field_cache = None #dictionary by (tuple_of_class_derivation, frozen_set_of_accessory_classes) of a dictionary by field names and field name abbreviations of ONDEField objects
    
    def __init__(self):
        self.classes = collections.OrderedDict()
        self.acc_classes = collections.OrderedDict()
        self.field_cache = {}
        pass
    
    def get_fields_dict(self,obj):
        onde_type_value = obj._ONDE_attrs["ONDE_TYPE"]
        assert(isinstance(onde_type_value,ONDEArray))
        
        class_derivation = tuple([str(classname) for classname in onde_type_value.value])
        
        if "ONDE:TYPE_TAGS" in obj._ONDE_attrs:
            acc_class_value = obj._ONDE_attrs["ONDE:TYPE_TAGS"]
            assert(isinstance(acc_class_value,ONDEArray))
            type_tags = frozenset([str(type_tag) for typ_tag in acc_class_value.value])
            pass
        else:
            type_tags = frozenset()
            pass

        field_cache_key = (class_derivation, type_tags)

        if field_cache_key in self.field_cache:
            return self.field_cache[field_cache_key]

        fields_dict = {}
        derivation_index=0
        mandatory_acc_classes = set()

        
        def add_field(fieldname,field,extra_keys):
            fields_dict[fieldname]=field.attributes[fieldname]
            for key in extra_keys:
                if key in fields_dict:
                    # key already present
                    if fields_dict[key].class_prefix==fields_dict[fieldname].class_prefix and fields_dict[key].name==fields_dict[fieldname].key:
                        # Override of a shorthand for the same thing already present. This is allowable.
                        fields_dict[key]=fields_dict[fieldname]
                        pass
                    else:
                        # Conflicting shorthands. Remove pre-existing entry.
                        del fields_dict[key]
                        pass
                    pass
                pass
            pass

        for classname in ("ONDE",)+class_derivation:
            # from base class to most derived
            derivation_index+=1
            
            if not classname in self.classes:
                continue

            if class_derivation[:(derivation_index-1)] != self.classes[classname].class_derivation:
                print(f"Object class derivation mismatch: {class_derivation[:(derivation_index-1)]}  from object definition versus {self.classes[classname].class_derivation}  from class definition.",file=sys.stderr)
                break
                

            # Gather fields from this class
            for fieldname in self.classes[classname].attributes:
                extra_keys=set()
                if ':' in fieldname:
                    #Shorthand for field name by admitting colon
                    extra_keys.add(fieldname[(fieldname.index(':')+1):])
                    pass

                add_field(fieldname,self.classes[classname],extra_keys)
                pass

            # Gather mandatory accessory classes
            for acc_class_name in self.classes[classname].type_tags:
                if self.classes[classname].type_tags[acc_class_name]:
                    # This accessory class is mandatory
                    mandatory_acc_classes.add(acc_class_name)
                    pass
                pass
            pass

        acc_classes = type_tags | mandatory_acc_classes # Set union
        
        for acc_class_name in acc_classes:
            
            # Gather fields from accessory classes
            acc_class = self.acc_classes[acc_class_name]

            # Gather fields from this accessory class
            for fieldname in self.classes[classname].attributes:
                extra_keys=set()
                if ':' in fieldname:
                    #Shorthand for field name by admitting colon
                    extra_keys.add(fieldname[(fieldname.index(':')+1):])
                    pass

                add_field(fieldname,acc_class.attributes[fieldname],extra_keys)
                pass
            pass
        

        
        self.field_cache[field_cache_key] = fields_dict
        return fields_dict

    
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
                (classname, name, comments, mandatory_optional, dataset_attribute, content_class, dims, size_or_content, min_val, max_val, accessory_class) = stripped_row
                
                if classname == "Class":
                    # header csv line
                    continue

                if classname == "" and name == "ONDE:VERSION":
                    # to do: store version
                    continue

                if classname == "" and name == "ONDE:FILETYPE":
                    # ignore filetype definition in .csv
                    continue
                
                if accessory_class == "True":
                    accessory_class = True
                    pass
                elif accessory_class == "False" or accessory_class == "":
                    accessory_class = False
                    pass
                else:
                    raise ValueError(f"unknown accessory_class value in .csv: {accessory_class:s}")
                
                if name == "ONDE:TYPE" and not accessory_class:
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

                elif name == "ONDE:TYPE" and accessory_class:
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

                elif name == "ONDE:TYPE_TAGS":
                    # specification for a class having a particular accessory class

                    type_tags = ast.literal_eval(size_or_content)

                    for type_tag in type_tags:
                        class_defs.classes[classname].type_tags[type_tag] = mandatory_optional == "M"

                        pass

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

            if current_obj in scope.exclude_objects:
                continue
        
            graph_replace_node__walk(current_path, current_obj, starting_obj,scope, scope_nodes, trans)
        
            pass
        pass
    pass


@dataclass
class ReplacedNode(object):
    replacement: Optional[ONDEBase]=None
    refersto: Optional[set[ONDEBase]]=field(default_factory=set) # Set of objects this node refers to that we might want to replace.
    
    pass


def graph_replace_node__reversewalk(current_node,refersto,scope_nodes,changed_nodes):
    if current_node not in changed_nodes:
        new = True
        changed_nodes[current_node] = ReplacedNode()
        pass
    else:
        new = False
        pass
    
    changed_nodes[current_node].refersto.update(refersto)
    
    if new: 
        referrers = scope_nodes[current_node].referrers
        
        for referrer in referrers:
            if referrer in changed_nodes:
                continue

            graph_replace_node__reversewalk(referrer,set([current_node]),scope_nodes,changed_nodes)
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
        current_path = ONDEPath(())
        pending_path = starting_path
        current_scope_set = scope_nodes[snap].edges
        
        # Follow the starting path, element by element, because we need to accumulate all referrers into the scope dictionary.
        while len(current_path) < len(starting_path)-1:
            current_scope_set.add(pending_path[0])
            current_path = ONDEPath(current_path + (pending_path[0],))

            current_parent_parent=current_parent
            current_parent = current_parent._follow_path(ONDEPath((pending_path[0],)))
            #print("current_parent=",str(current_path))
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
            current_scope_node.referrers.add(current_parent_parent)
            pass
        
        if current_scope_set is not None:
            current_scope_set.add(pending_path[0])
            pass
        
        

        assert(starting_path[-1] == pending_path[0])
        starting_parent = current_parent
        starting_obj = starting_parent._follow_path(ONDEPath((starting_path[-1],)))
        if starting_obj in scope.exclude_objects:
            continue
        
        graph_replace_node__walk(starting_path, starting_obj, starting_parent, scope, scope_nodes, trans)
        pass

    # print("scope_nodes=",scope_nodes)

        
    #
    # step 2: identify the node to be changed within the set (if it's not included, the new node is not referenced)
    #
    if orig_node not in scope_nodes:
        return
    # step 3: reverse walk the set of nodes, starting at the node to be changed, identifying these nodes into a new (and probably smaller) dict called changed_nodes, the keys of which are a set of nodes through which the change will propagate while the values are ReplacedNode objects with the replacement set to None
    #
    changed_nodes = collections.OrderedDict()

    current_node = orig_node

    graph_replace_node__reversewalk(current_node,set([]),scope_nodes,changed_nodes)

    
    #print("changed_nodes=",changed_nodes)
    
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
        changed_nodes[changed_node].replacement = replacement
        pass
        

    
    #print("changed_nodes=",changed_nodes)
    

    
    # step 5: iterate through the replacements, identifying every "fair game" reference to changed_nodes, and re-pointing that to the replacements
    #

    for replaced_node in changed_nodes:
        replacement = changed_nodes[replaced_node].replacement
        scope_node = scope_nodes[replaced_node]
        fair_game_edges = scope_node.edges
        refersto = changed_nodes[replaced_node].refersto
        # refersto is a set of ONDEBase that includes all of the outgoing-referenced-objects referred to by replacement that may need to be repointed at a newly created copy that is findable by changed_nodes
        # Only those edges listed in fair_game_edges (or all edges if fair_game_edges is None) need to be swapped out.
        for dest in refersto:
            dest_indices = replaced_node._indices_for_object(dest)
            if fair_game_edges is not None:
                dest_indices = dest_indices.intersection(fair_game_edges)
                pass
            for dest_index in dest_indices:
                replacement._assign_pathel(dest_index, changed_nodes[dest].replacement)
                pass
            pass
        pass
    
        
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
        # _dict = object.__getattribute__(self, "__dict__")

        for arg in kwargs:
            if arg in type(self).__dict__:
                # setattr(self, arg, kwargs[arg])
                object.__setattr__(self, arg, kwargs[arg])

                pass
            else:
                raise ValueError(f"ONDEProxy; unknown attribute {arg:s}")
            pass
        pass

    @classmethod
    def new_from_proxy(cls, parent, subpath):
        _graph = object.__getattribute__(parent, "_graph")

        # parent_obj = object.__getattribute__(parent, "_obj")
        # _obj = parent_obj._get_attr(attr_name)
        # _obj_snap = object.__getattribute__(parent, "_obj_snap")

        _parent_path = object.__getattribute__(parent, "_path")
        path = ONDEPath(_parent_path + (subpath,))

        _trans = object.__getattribute__(parent, "_trans")

        return cls(_graph=_graph, _path=path, _trans=_trans)

    @classmethod
    def new_from_snapshot(cls, graph, snapshot):
        path = ONDEPath()
        return cls(_graph=graph, _path=path, _snap=snapshot)
    
    @classmethod
    def new_from_scope(cls, scope):
        _trans = scope.trans
        _graph = _trans.graph
        _path = ONDEPath()

        return cls(_graph=_graph, _path=_path, _trans=_trans,_scope=scope)
    
    def _get_obj(self):
        trans = object.__getattribute__(self, "_trans")

        if trans is not None:
            snap = trans.snap
            pass

        else:
            graph = object.__getattribute__(self, "_graph")
            snap = graph._latest_snap
            pass

        _path = object.__getattribute__(self, "_path")
        return snap._follow_path(_path)

    def __getattribute__(self, name):
        if name.startswith("_"):
            if name in { "_set_attr", "_get_attr","_get_item","_set_item","_get_data","_set_data","_set_attr_or_item_or_data","_get_obj","_follow_path","__class__","__dict__","_graph"}:
                return object.__getattribute__(self, name)
            elif  name in {"_freeze", "_frozen",}:
                obj = self._get_obj()
                return getattr(obj,name)
            raise ValueError(f"ONDEProxy: invalid underscore attribute {name}")
        obj = self._get_obj()
        if isinstance(obj,ONDEObject):
            _get_attr = object.__getattribute__(self, "_get_attr")
            return _get_attr(name)

        #elif isinstance(obj,ONDEReferenceArray):
        #    self._set_item(name,value)
        #    pass
        else:
            assert(isinstance(obj,ONDEBase))
            _get_data = object.__getattribute__(self, "_get_data")
            return _get_data(name)
          
        pass
    
    def __setattr__(self,name,value):
        _set_attr = object.__getattribute__(self, "_set_attr")
        obj = self._get_obj()
        if isinstance(obj,ONDEObject):
            self._set_attr(name,value)
            pass
        #elif isinstance(obj,ONDEReferenceArray):
        #    self._set_item(name,value)
        #    pass
        else:
            assert(isinstance(obj,ONDEBase))
            self._set_data(name,value)
            pass
        pass
    
    def _get_attr(self, name):
        obj = self._get_obj()
        attr_obj = obj._get_attr(name)

        assert(isinstance(attr_obj, ONDEBase))
        return self.__class__.new_from_proxy(self, name)

        #return attr_obj
        
    def _has_attr(self, name):
        obj = self._get_obj()
        return obj._has_attr(name)

    
    def _set_attr(self, name, value):
        self._set_attr_or_item_or_data('_set_attr', name, value)
        pass

    def _get_item(self, key):
        obj = self._get_obj()
        item_obj = obj._get_item(name)

        if isinstance(item_obj, ONDEBase):
            return self.__class__.new_from_proxy(self, key)

        return item_obj
    
    def _set_item(self, index, value):
        self._set_attr_or_item_or_data('_set_item', index, value)
        pass

    def _get_data(self, name):
        obj = self._get_obj()
        data_obj = obj._get_data(name)

        return data_obj
    
    def _set_data(self, name, value):
        self._set_attr_or_item_or_data('_set_data', name, value)
        pass
    
    
    def _set_attr_or_item_or_data(self, set_method_name, key, value):
        ''' Use the named set method (_set_attr, _set_item, or  _set_data) to assign the element specified by key to the given value'''
        
        _trans = object.__getattribute__(self, "_trans")
        #import pdb
        #pdb.set_trace()

        if _trans is None:
            _graph = object.__getattribute__(self, "_graph")

            transaction = ONDETransaction(_graph)

            with transaction as scope:
                proxy=scope.graph
                # proxy now has a potentially updated snapshot that we
                
                # should  use for the transaction. Need to use our path to
                # recreate our object and then call _set_attr on that.
                path = object.__getattribute__(self,"_path")
                newproxy = proxy._follow_path(path)
                set_method = getattr(newproxy, set_method_name) # extract the bound method e.g. newproxy._set_attr
                set_method(key, value)
                pass

            pass

        else:
            # create replacement node that has the desired change
            # obj = object.__getattribute__(self, "_obj")
            
            # create a new object of obj's class, passing the original that we want to copy as its first constructor parameter; the ONDE classes are built to handle this
            _get_obj = object.__getattribute__(self, "_get_obj")
            obj = _get_obj()
            scope = object.__getattribute__(self, "_scope")
            path = object.__getattribute__(self, "_path")

            if scope is None:
                scope = _trans.scope
                pass

            if scope.include_paths is None:
                # Null scope: use most constrained scope for each op
                scope = ONDEOpScope(_trans,[path])
                pass

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

            set_method = getattr(replacement, set_method_name) # e.g. replacement._set_attr
            set_method(key, value)
            #replacement._freeze() Freezing happens at the end of the transaction
            #if new: # We could avoid the replacement for preexisting modifications if we knew that the scope of the previous modification matched our scope.
            if new or scope not in obj._modification_scopes:
                replacement._modification_scopes.add(scope)
                graph_replace_node(_trans, scope,path, obj, replacement)
                pass

            pass

        pass

    def _follow_path(self,path):
        obj = self._get_obj()
        dest=obj._follow_path(path)


        _graph = object.__getattribute__(self, "_graph")

        _our_path = object.__getattribute__(self, "_path")
        full_path = ONDEPath(_our_path + path)

        _trans = object.__getattribute__(self, "_trans")

        return self.__class__(_graph=_graph, _path=full_path, _trans=_trans)
        
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
