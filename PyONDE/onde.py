# Road map:
# *Need to implement _del_attr and _del_item on various classes.

import h5py
import sys
import os
import os.path
import posixpath
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
                "_list_attrs"
                ),
            "ONDEFileGraphSnapshot":(
                "_freeze",
                "_frozen",
                "_get_attr",
                "_set_attr",
                "_has_attr",
                "_list_attrs"
                )
            }

def repr_helper(indentation, classname, _extra_info = None, **attrdict):
    lines = []
    classline = " "*indentation + classname
    if _extra_info is not None:
        classline += " "+_extra_info
        pass
    lines.append(classline)
    for attrname in attrdict:
        lines.append(" "*(indentation+2) + f"{attrname:>18s}: {attrdict[attrname]:s}")
        pass
    return "\n".join(lines)

def onde_from_python(value,field):
    """field is an ONDEField or None. So far it is not used because we don't have code to parse the type specification"""
    if isinstance(value,numbers.Integral) or isinstance(value, numbers.Real) or isinstance(value,numbers.Complex) or  isinstance(value,str) or isinstance(value,np.str_):
        return ONDEValue.new(value)

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
            if name in {"_freeze", "_frozen", "_set_attr", "_get_attr", "_keys","_del_attr"}:
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

    def _del_attr(self,name):
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
            del _bystrings[name]
            pass
        pass
    
    def _get_attr(self, name):
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _bystrings = object.__getattribute__(self, "_bystrings")
        return _bystrings[name]

    def __getitem__(self,name):

        return self._get_attr(name)

    def __delitem__(self,name):
        return self._del_attr(name)
    
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
            byindex = np.empty(shape,dtype="O")
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

    @property
    def byindex(self):
        """Return safe copy of underlying array"""
        with self._lock:
            byindex = copy.copy(self._byindex)
            pass
        return byindex
    
    def __iter__(self):
        return np.nditer(self._byindex,flags=("multi_index","refs_ok")) # Just use iterator of underlying array

    def __getitem__(self, index):
        
        return self._byindex[index]

    @property
    def _shape(self):
        return self._byindex.shape

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
                self._byobjid[id(oldobj)] = self._byobjid[id(oldobj)] - frozenset({index})
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


class ONDEFileGraph(object):
    """Represents the subgraph of interconnected ONDE objects
    and attributes that are or will be contained within some particular ONDE file. It has an associated set of ONDEClassDefinitions that are used to interpret the attached objects."""
    _lock = None # threading.Lock that protects access to replace the snapshot.
    _lock_ownerthread = None # Writes protected by _lock, the threading.get_ident() of whichever thread owns the lock
    latest_snap = None # class ONDEFileGraphSnapshot
    class_defs = None # ONDEClassDefinitions, optional

    def __init__(self, class_defs = None, latest_snap = None):
        # self._lock = threading.Lock()
        object.__setattr__(self, "_lock", threading.Lock())

        if latest_snap is None:
            latest_snap = ONDEFileGraphSnapshot.new()

            pass
        
        object.__setattr__(self, "class_defs", class_defs)
        
        # self.latest_snap = snapshot
        object.__setattr__(self, "latest_snap", latest_snap)

        pass
    
    r"""
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
    """

    
    def _get_item(self, name):
        latest_snap = object.__getattribute__(self, "latest_snap")
        
        # call ONDEProxy
        
        snap_proxy = ONDEProxy.new_from_snapshot(self, latest_snap)
        obj_proxy = ONDEProxy.new_from_proxy(snap_proxy, name)

        if self.class_defs is not None:
            return ONDEClassInstanceWrapper.new_from_proxy(obj_proxy)
        return obj_proxy

    def __getitem__(self, name):
        return self._get_item(name)
    
    def _set_item(self, name, value):
        latest_snap = object.__getattribute__(self, "latest_snap")

        snap_proxy = ONDEProxy.new_from_snapshot(self, latest_snap)

        snap_proxy._set_item(name,value)

        pass

    def __setitem__(self, name, value):
        self._set_item(name,value)
        pass
    
    def keys(self):
        latest_snap = object.__getattribute__(self, "latest_snap")
        return latest_snap._list_items()

    def __iter__(self):
        return iter(self.keys())

    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        extra_info = None
        if self.class_defs is not None:
            extra_info = f"(ONDE v{self.class_defs.version:s} class definitions)"
            pass
        return repr_helper(indentation, "ONDEFileGraph", _extra_info = extra_info)+"\n"+self.latest_snap._repr(indentation+2)
        
    def __repr__(self):
        return self._repr(0)
   

    @classmethod
    def new(cls,class_defs=None,snapshot=None):
        #defs = None
        #if class_def_csv_path is not None:
        #    defs = ONDEClassDefinitions.load_from_csv(class_def_csv_path)
        #    pass
        
        return cls(class_defs = class_defs,latest_snap=snapshot)
        
    pass

class ONDEDatasetFileGraph(ONDEFileGraph):
    """Represents an ONDEFileGraph that is presumed to contain at its base level a number of ONDE_DATASET objects as per the ONDE 1.0 specification."""
    # Inherited members from ONDEFileGraph
    # _lock = None # threading.Lock that protects access to replace the snapshot.
    # _lock_ownerthread = None # Writes protected by _lock, the threading.get_ident() of whichever thread owns the lock
    # latest_snap = None # class ONDEFileGraphSnapshot
    # class_defs = None # ONDEClassDefinitions, optional

    def __init__(self, class_defs = None, latest_snap = None):
        super().__init__(self, class_defs = class_defs, latest_snap = latest_snap)
        pass
    # Various methods inherited from ONDEFileGraph
    # !!!*** should provide way to add a dataset that automatically sets the index
    pass

class ONDETransaction(object):
    """Represents a transaction in which the ONDEFileGraph is modified"""
    graph = None # ONDEFileGraph object
    scope = None
    snap = None # This is the snapshot we're modifying

    def __init__(self, graph, include_paths=None, exclude_paths=None,exclude_objects=None):
        self.graph = graph
        
        self.scope = ONDEOpScope(self,include_paths, exclude_paths,exclude_objects)

        
        pass

    def __enter__(self):
        lockowner = object.__getattribute__(self.graph, "_lock_ownerthread")
        if lockowner == threading.get_ident():
            raise RuntimeError(f"Error creating a new transaction while another transaction is already open on the file graph by the same thread. This probably means that you are attempting a change on an object not accessed via the transaction. Within a transaction, always access objects via the transaction or scope objects.")
        _lock = object.__getattribute__(self.graph, "_lock")
        _lock.acquire()

        object.__setattr__(self.graph, "_lock_ownerthread", threading.get_ident())
        
        snap = object.__getattribute__(self.graph, "latest_snap")
        self.snap = ONDEFileGraphSnapshot(_orig=snap) # Create mutable copy of most recent snapshot
        
        return self.scope

    
    def __exit__(self, exc_type, exc, tb):
        self.snap._freeze()
        object.__setattr__(self.graph, "latest_snap",self.snap)
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
    # _graph = None # ONDEFileGraph object
    _referencedby = None # set of ONDEBase objects that reference this object. The _referencedby member can still be changed even after an instance is frozen becuase new objects can reference it. Note that the _referencedby field is generally only updated to include new objects when those objects become frozen. Access is protected by _referencedby_lock.
    _referencedby_lock = None # threading.Lock object that protects _referencedby
    
    _frozen = None # True/False: has this object been finalized and therefore become immutable
    _modification_scopes = None # A set of scopes for which the ancestor nodes in the graph have been replaced for the transaction in which this node is being updated. It is only valid for use within the context of the transaction in which the node is being created and it is cleared when the node is frozen.

    _file_realizations = None # A set of ONDEFileObjects that represent realizations in hdf5 of this object. Locked by _file_realizations_lock.
    _file_realizations_lock = None # A threading.Lock object that protects _file_realizations.

    def __init__(self, _orig = None, **kwargs):
        _referencedby = None
        _file_realizations = None
        #if _orig is not None:
        #    _referencedby = object.__getattribute__(_orig, "_referencedby")
        #    pass
        if "_referencedby" in kwargs:
            _referencedby = set(kwargs["_referencedby"])
            del kwargs["_referencedby"]
            pass
        if "_file_realizations" in kwargs:
            _file_realizations = set(kwargs["_file_realizations"])
            del kwargs["_file_realizations"]
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
        if _file_realizations is None:
            _file_realizations = set()
            pass
        
        object.__setattr__(self, "_referencedby", _referencedby)
        object.__setattr__(self, "_referencedby_lock", threading.Lock())
        object.__setattr__(self, "_file_realizations", _file_realizations)
        object.__setattr__(self, "_file_realizations_lock", threading.Lock())
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
            if name in {"_freeze", "_frozen", "_add_referencedby", "__class__", "__dir__", "_get_attr","_get_attr_dataset_storage", "_set_attr","_set_dataset_attr","_get_data","_set_data","_get_item","_list_items","_set_item","_follow_path","_modification_scopes","_indices_for_object","_assign_pathel","_list_edges", "_repr", "_repr_short","_hdf5_write_group","_hdf5_write_dataset","_hdf5_write_attribute","_file_realizations","_file_realizations_lock"}:
                return object.__getattribute__(self, name)
            raise IndexError(f"ONDEBase: The attribute {name:s} has a leading underscore, which is not allowed.")
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

    def _get_attr_dataset_storage(self, name):
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

    def _set_dataset_attr(self, name, value):
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
    
    def _list_items(self,index,value):
        """List the data element indices of an ONDE object.
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

    def _hdf5_write_group(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 group
        """
        raise ValueError("ONDEBase does not have content to write")

    def _hdf5_write_dataset(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 dataset
        """
        raise ValueError("ONDEBase does not have content to write")

    def _hdf5_write_attribute(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 attribute
        """
        raise ValueError("ONDEBase does not have content to write")

        

    
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
        _referencedby_lock = object.__getattribute__(self, "_referencedby_lock")
        with _referencedby_lock: 
            _referencedby.add(obj_that_references_us)
            pass
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

    def _repr_short(self, onde_class=None):
        return type(self).__name__
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        return repr_helper(indentation, type(self).__name__, **extra_attrs)

    def __repr__(self):
        return object.__getattribute__(self, "_repr")(0)
    
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

    def _repr_short(self, onde_class=None):
        return f"ONDEValue({str(object.__getattribute__(self, 'value')):s})"
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        # return f"ONDEValue ID={id(self):x} of type {type(object.__getattribute__(self, 'value')).__name__:s} containing value: {str(object.__getattribute__(self, 'value')):s}"
        return repr_helper(indentation, "ONDEValue",
                           ID=f"{id(self):x}",
                           type=type(object.__getattribute__(self, 'value')).__name__,
                           value=str(object.__getattribute__(self, 'value')),
                           **extra_attrs)


    def _hdf5_write_attribute(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 attribute
        """
        parent.attrs[name] = self.value
        pass
    
        

    
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
    status in the parent object and whether the attribute of the parent is set to be stored as a dataset
    """
    value = None # numpy array
    #store_as_dataset = None # boolean; store as an HDF5 dataset if True, otherwise and an HDF5 attribute
    
    def __init__(self, _orig = None, **kwargs):
        #store_as_dataset = False
        value = None
        shape = None
        dtype = None
        
        if _orig is not None:
            value = _orig.value
            #store_as_dataset = _orig.store_as_dataset
            pass

        
        #if "store_as_dataset" in kwargs:
        #    store_as_dataset = bool(kwargs["store_as_dataset"])
        #    del kwargs["store_as_dataset"]
        #    pass
        if "shape" in kwargs:
            if kwargs["shape"] is not None:
                shape = tuple(kwargs["shape"])
                pass
            del kwargs["shape"]
            pass
        if "dtype" in kwargs:
            dtype = kwargs["dtype"]
            del kwargs["dtype"]
            pass
        
        if "value" in kwargs:
            if kwargs["value"] is not None:
                value = copy.copy(kwargs["value"])
                if isinstance(value, collections.abc.Sequence):
                    dtype = None
                    if len(value) > 0 and isinstance(value[0],str):
                        # For collection of strings, use h5py string datatype for numpy
                        dtype = h5py.string_dtype()
                        pass
                    value = np.array(value,dtype=dtype)
                    pass
                elif isinstance(value, np.ndarray):
                    # value.flags.writeable = False
                    pass
                else:
                    raise ValueError(f"ONDEArray: Cannot understand value type {value.__class__.__name__:s}")
                pass
            del kwargs["value"]
            pass
        if value is None:
            value = np.zeros(shape, dtype = dtype)
            pass
        
        #self.store_as_dataset = store_as_dataset
        self.value = value
        super().__init__(_orig, **kwargs)
        pass

    def __getattribute__(self,name):
        if name == "value" or name == "shape":# or name == "store_as_dataset":
           
            _get_data = object.__getattribute__(self, "_get_data")
            return _get_data(name)

        return super().__getattribute__(name)

    def __setattr__(self,name,value):
        if name == "value": # or name == "store_as_dataset":
            self._set_data(name,value)
            pass
        else:
            
            super().__setattr__(name,value)
            pass
        pass

    def _get_item(self,index):
        return self.value[index]
    
    def __getitem__(self,index):
        return self._get_item(index)

    def _set_item(self,index,el_value):
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        self.value[index] = el_value
        pass

    def __setitem__(self,index,el_value):
        self._set_item(index,el_value)
        pass

    def _get_data(self, name):
        """
        Return the named conceptual attribute of an ONDE object.
        """

        if name == "value": # or name == "store_as_dataset":
            return object.__getattribute__(self, name)
        elif name == "shape":
             return object.__getattribute__(self, "value").shape
        
        raise ValueError("ONDEArray does not have attributes other than \"value\" and \"store_as_dataset\"")
    
    def _set_data(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object.
        """
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        if name == "value": # or name == "store_as_dataset":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEArray does not have attributes other than \"value\"")
    
    def _freeze(self):
        self.value.flags.writeable = False
        super()._freeze()
        pass

    def _repr_short(self, onde_class=None):
        if len(self.shape)==1 and self.shape[0]<8:
            return f"ONDEArray([{str(list(self.value))}])"
        return f"ONDEArray(shape={str(self.shape):s},dtype={str(self.value.dtype):s})"
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        return repr_helper(indentation, "ONDEArray",
                           ID=f"{id(self):x}",
                           type=str(object.__getattribute__(self, 'value').dtype),
                           shape=str(object.__getattribute__(self, 'value').shape),
                           **extra_attrs)

    def _hdf5_write_attribute(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 attribute
        """
        parent.attrs[name] = self.value
        pass
    
    def _hdf5_write_dataset(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 dataset
        """
        ds = parent.create_dataset(name,data = self.value)

        pass
                         
    @classmethod
    def new(cls, value = None, **kwargs):
        return cls(None, value = value, **kwargs)
    
    pass


class ONDEReferenceArray(ONDEBase):
    """Represents an array of references to other ONDEObjects.

    An ONDEReferenceArray can be stored as an HDF5
    attribute"""
    refs = None # TwoWayArray of ONDEBase references
    #store_as_dataset = None # True to store as an HDF5 dataset, False to store as an HDF5 attribute
    

    def __init__(self,_orig, **kwargs):
        """Private constructor for internal use only.
        Use .new() classmethod or copy.copy()
        """
        #store_as_dataset = False
        refs = None
        if _orig is not None:
            refs = _orig.refs
            #store_as_dataset = _orig.store_as_dataset
            pass

        
        #if "store_as_dataset" in kwargs:
        #    store_as_dataset = bool(kwargs["store_as_dataset"])
        #    del kwargs["store_as_dataset"]
        #    pass
        
        shape = ()

        if "shape" in kwargs:
            if kwargs["shape"] is not None:
                shape = tuple(kwargs["shape"])
                pass
            del kwargs["shape"]
            pass
        
        if "refs" in kwargs:
            if kwargs["refs"] is not None:
                refs = TwoWayArray(byindex=kwargs["refs"])
                shape = kwargs["refs"].shape
                pass
            del kwargs["refs"]
            pass

        if refs is None:
            refs = TwoWayArray(shape=shape)
            pass
        
        #self.store_as_dataset = store_as_dataset
        object.__setattr__(self, "refs", refs)
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

        if name == "refs": # or name == "store_as_dataset":
            return object.__getattribute__(self, name)

        raise ValueError("ONDEReferenceArray does not have attributes other than \"refs\"")
    
    def _set_data(self, name, value):
        """
        Set the named conceptual data of an ONDE object.
        """

        if name == "refs": # or name == "store_as_dataset":
            return object.__setattr__(self, name, value)

        raise ValueError("ONDEReferenceArray does not have attributes other than \"refs\"")

    def _get_item(self,index):
        return self.refs[index]

    def _set_item(self,index,ref):
        if self._frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")

        if isinstance(ref, ONDEClassInstanceWrapper) or isinstance(ref, ONDEProxy):
            ref = ref._get_obj()
            pass
        
        if not isinstance(ref,ONDEBase):
            raise ValueError(f"Attempting to assign index {str(index)} of an ONDEReferenceArray to an object of class {ref.__class__.__name__} that is not an ONDEBase reference")

        self.refs[index] = ref
        pass

    def __getattribute__(self,name):
        if name == "refs":# or name == "store_as_dataset":
            _get_data = object.__getattribute__(self, "_get_data")
            return _get_data(name)

        return super().__getattribute__(name)

    def __setattr__(self,name,value):
        if name == "refs": # or name == "store_as_dataset":
            self._set_data(name,value)
            pass
        else:
            
            super().__setattr__(name,value)
            pass
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
            if self.refs[path_entry] is not None:
                return self.refs[path_entry]._follow_path(ONDEPath(path[1:]))
            return None
        else:
            raise AttributeError(f"Cannot index {self.__class__.__name__} by {path_entry}")
        
        pass

    def _assign_pathel(self, pathel, value):
        if self._frozen:
            raise RuntimeError(f"Cannot assign {str(value)} to {str(pathel)} element of frozen object")
        self.refs[pathel]=value
        pass
    
    def _list_edges(self):
        nditer = iter(self.refs) #np.nditer object
        sz = nditer.itersize
        
        edgelist= []
        for cnt in range(sz):
            next(nditer)

            if self.refs[nditer.multi_index] is not None:
                edgelist.append(nditer.multi_index)
                pass
            pass
        return edgelist

    def _indices_for_object(self,obj):
        """identify all of the indices for self that reference object obj. Returns a frozenset."""
        return self.refs(obj) # __call__ method does reverse lookup to return a set of indices 

    def _repr_short(self, onde_class=None):
        return f"ONDEReferenceArray(shape={str(object.__getattribute__(self, 'refs')._shape):s})"
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        return repr_helper(indentation, "ONDEReferenceArray",
                           ID=f"{id(self):x}",
                           shape=str(object.__getattribute__(self, 'refs')._shape),
                           **extra_attrs)

    def _hdf5_write_attribute(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 attribute
        """
        ref_dtype = h5py.special_dtype(ref = h5py.Reference)

        byindex = self.refs.byindex
        h5_byindex = np.zeros(byindex.shape,dtype = ref_dtype)
        nditer = np.nditer(byindex, flags = ("multi_index","refs_ok"))

        for objarray in nditer:
            obj = objarray[()]
            if obj is not None:
                # !!!*** This may need to be accelerated by caching the hdf5 object references per the various discussions on h5py indexing performance with Paul Wilcox, early 2026. https://github.com/COFREND/ONDE-format/issues/24
                h5_byindex[nditer.multi_index] = onde_file.fh[onde_file.file_object_dict[obj].hdf5_path].ref
                pass
            pass
        
        parent.attrs[name] = h5_byindex
        pass
    
    def _hdf5_write_dataset(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 dataset
        """
        ref_dtype = h5py.special_dtype(ref = h5py.Reference)

        byindex = self.refs.byindex
        h5_byindex = np.zeros(byindex.shape,dtype = ref_dtype)
        nditer = np.nditer(byindex, flags = ("multi_index","refs_ok"))

        for objarray in nditer:
            obj = objarray[()]
            if obj is not None:
                # !!!*** This may need to be accelerated by caching the hdf5 object references per the various discussions on h5py indexing performance with Paul Wilcox, early 2026. https://github.com/COFREND/ONDE-format/issues/24
                h5_byindex[nditer.multi_index] = onde_file.fh[onde_file.file_object_dict[obj].hdf5_path].ref
                pass
            pass
        ds = parent.create_dataset(name,data=h5_byindex)
        pass
    
    @classmethod
    def new(cls, refs = None, shape = None, **kwargs):
        return cls(None, refs = refs, shape = shape, **kwargs)

    @classmethod
    def load_from_hdf5(cls,onde_file,fileobjs_by_h5path,h5_fh,np_h5ref_array):
        refs  = np.empty(np_h5ref_array.shape,dtype = "O")
        nditer = np.nditer(np_h5ref_array, flags = ("multi_index","refs_ok"))

        for refarray in nditer:
            ref = refarray[()]
            if ref is not None:
                refs[nditer.multi_index] = ONDEObject.load_from_hdf5(onde_file,fileobjs_by_h5path,h5_fh,h5_fh[ref])
                pass
            pass
        instance = cls(None,refs = refs, shape = np_h5ref_array.shape)
        return instance
    
    pass


class ONDEObject(ONDEBase):
    """ONDEObject represents a (non-leaf) node in the graph
    that can point at other objects."""
    #ONDE_TYPE = None # List of classes starting with base class
    _ONDE_attrs = None # TwoWayDictionary by name of attributes that should be ONDEBase (or subclass) objects).
    _ONDE_dataset_attrs = None # Sub-set of ONDE_attrs that should use hdf5 dataset (as opposed to hdf5 attribute) storage.

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
        _ONDE_dataset_attrs = None
        if _orig is not None:
            _ONDE_attrs = object.__getattribute__(_orig, "_ONDE_attrs")
            _ONDE_dataset_attrs = object.__getattribute__(_orig,"_ONDE_dataset_attrs")
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

        if "_ONDE_dataset_attrs" in kwargs:
            _ONDE_dataset_attrs = kwargs["_ONDE_dataset_attrs"]
            del kwargs["_ONDE_dataset_attrs"]
            pass
        
        #object.__setattr__(self, "ONDE_TYPE", tuple(ONDE_TYPE))
        ONDE_attrs = TwoWayDictionary(_ONDE_attrs)
        if not "ONDE:TYPE" in ONDE_attrs:
            ONDE_attrs["ONDE:TYPE"] = ()
            pass
        
        object.__setattr__(self, "_ONDE_attrs", ONDE_attrs)

        if _ONDE_dataset_attrs is None :
            _ONDE_dataset_attrs = set()
            pass
        ONDE_dataset_attrs = set(_ONDE_dataset_attrs)
        object.__setattr__(self,"_ONDE_dataset_attrs",ONDE_dataset_attrs)
        
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
            if name in {"_freeze", "_frozen", "_add_referencedby", "__class__", "__dir__", "_get_attr","_get_attr_dataset_storage", "_set_attr","_set_dataset_attr","_follow_path","_modification_scopes","_indices_for_object","_assign_pathel","_list_edges","_ONDE_attrs","_ONDE_dataset_attrs", "_has_attr","_repr","_repr_short","_hdf5_write_group","_list_attrs","_hdf5_write_dataset","_hdf5_write_attribute","_file_realizations","_file_realizations_lock","_onde_class_name"}:
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

    def _get_attr_dataset_storage(self, name):
        """
        Return whether the named conceptual attribute of an ONDE object uses hdf5 dataset storage.
        """
        
        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _ONDE_dataset_attrs = object.__getattribute__(self, "_ONDE_dataset_attrs")

        return name in _ONDE_dataset_attrs

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
        Set the named conceptual attribute of an ONDE object. Use _set_dataset_attr() instead if the attribute should have hdf5 dataset storage.
        """

        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        _ONDE_dataset_attrs = object.__getattribute__(self, "_ONDE_dataset_attrs")
        
        if isinstance(value, ONDEClassInstanceWrapper) or isinstance(value, ONDEProxy):
            value = value._get_obj()
            pass

        _ONDE_dataset_attrs.discard(name)
        return _ONDE_attrs._set_attr(name, value)

    def _set_dataset_attr(self, name, value):
        """
        Set the named conceptual attribute of an ONDE object with dataset storage. Use _set_attr() instead if the attribute should have hdf5 attribute storage.
        """

        if name.startswith("_"):
            raise ValueError(f"Attributes such as \"{name:s}\" with leading underscores not allowed")

        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        _ONDE_dataset_attrs = object.__getattribute__(self, "_ONDE_dataset_attrs")
        
        if isinstance(value, ONDEClassInstanceWrapper) or isinstance(value, ONDEProxy):
            value = value._get_obj()
            pass

        _ONDE_dataset_attrs.add(name)
        return _ONDE_attrs._set_attr(name, value)

    def _list_attrs(self):
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        return [attrname for attrname in _ONDE_attrs]
    
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
            #return self._get_attr(path_entry)._follow_path(ONDEPath(path[1:]))
            # ONDEFileGraphSnapshot (our subclass) uses items not attributes. So here we explicitly use our own _get_attr() to expand out the path entry
            return ONDEObject._get_attr(self,path_entry)._follow_path(ONDEPath(path[1:]))
        else:
            raise AttributeError(f"Cannot index {self.__class__.__name__} by {path_entry}")
        
        pass

    def _assign_pathel(self, pathel, value):
        if self._frozen:
            raise RuntimeError(f"Cannot assign {str(value)} to {str(pathel)} element of frozen object")
        # ONDEFileGraphSnapshot (our subclass) uses items not attributes. So here we explicitly use our own _set_attr() to expand out the path entry
        #self._set_attr(pathel, value)
        ONDEObject._set_attr(self,pathel, value)
        pass
    
    def _list_edges(self):
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        edgelist= list(_ONDE_attrs._keys())
        return edgelist

    def _indices_for_object(self,obj):
        """identify all of the indices for self that reference object obj. Returns a frozenset."""
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        return _ONDE_attrs(obj) # __call__ method does reverse lookup to return a set of indices

    def _repr_short(self, onde_class=None):
        myclass=type(self).__name__
        if onde_class is not None:
            myclass=f"{onde_class:s}({myclass:s})"
            pass
        
        return f"{myclass:s}(ID={id(self):x})"
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        myclass=type(self).__name__
        if onde_class is not None:
            myclass=f"{onde_class:s}({myclass:s})"
            pass
        
        new_extra_attrs=collections.OrderedDict()
        if onde_class is None:
            _ONDE_attrs=object.__getattribute__(self, '_ONDE_attrs')
            _ONDE_dataset_attrs = object.__getattribute__(self, "_ONDE_dataset_attrs")
            for attrname in _ONDE_attrs._keys():
                storage_suffix = ""
                if attrname in _ONDE_dataset_attrs:
                    storage_suffix = " (hdf5 dataset storage)"
                    pass
                attrval=_ONDE_attrs[attrname]
                if attrval is not None:
                    new_extra_attrs[attrname]=object.__getattribute__(attrval, "_repr_short")() + storage_suffix
                    pass
                else:
                    new_extra_attrs[attrname]="None" + storage_suffix
                    pass
                
                pass
            pass
        new_extra_attrs.update(extra_attrs)
        return repr_helper(indentation, myclass,
                           ID=f"{id(self):x}",
                           **new_extra_attrs)

    def _onde_class_name(self):
        classname = "(None)"
        if "ONDE:TYPE" in self._ONDE_attrs:
            if isinstance(self._ONDE_attrs["ONDE:TYPE"],ONDEArray):
                if len(self._ONDE_attrs["ONDE:TYPE"].value) > 0:
                    classname = self._ONDE_attrs["ONDE:TYPE"].value[0]
                    pass
                pass
            pass
        return classname

    def _hdf5_write_group(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write this object to a new hdf5 group
        """
        gr = parent.create_group(name)
        for attrname in self._ONDE_attrs:
            value = self._ONDE_attrs[attrname]
            if attrname in self._ONDE_dataset_attrs:
                if isinstance(value,ONDEObject) or isinstance(value,ONDEValue):
                    raise ValueError(f"Error writing ONDE object of class {self._onde_class_name()}: Attribute {attrname} is marked for dataset storage, but is an {type(value).__name__} not an ONDEArray or ONDEReferenceArray")
                value._hdf5_write_dataset(onde_file,gr,gr.name,attrname,None)
                pass
            else:
                value._hdf5_write_attribute(onde_file,gr,gr.name,attrname,None)
                pass
            pass
        
        pass
    
    def _hdf5_write_attribute(self,onde_file,parent,parent_path,name,onde_fileobj):
        """Write a reference to this object to a new hdf5 attribute
        """
        parent.attrs[name] = onde_file.fh[onde_file.file_object_dict[self].hdf5_path].ref
        pass


    @classmethod
    def new(cls, file_or_graph,onde_classname, ONDE_TYPE = None, _ONDE_attrs = None,_ONDE_dataset_attrs = None, **kwargs):
        """Main constructor to call. If file_or_graph is provided, then the ONDEObject will be created but in fact the returned python object will be instead an ONDEClassInstanceWrapper with the context of that file or graph and the corresponding class definitions."""

        graph = None
        
        if isinstance(file_or_graph, ONDEFileGraph):
            graph = file_or_graph
            pass
        elif file_or_graph is not None:
            graph = file_or_graph.graph
            pass
        
        if onde_classname is not None and ONDE_TYPE is None:
            class_derivation = [ onde_classname ]
            if graph is not None and graph.class_defs is not None:
                class_defs = graph.class_defs
                if onde_classname in class_defs.classes:
                    onde_class = class_defs.classes[onde_classname]
                    class_derivation = onde_class.class_derivation
                    pass
                pass
            
            ONDE_TYPE = ONDEArray.new(class_derivation, _frozen = True)
            pass
        
        constructargs = {}
        if ONDE_TYPE is not None:
            constructargs["ONDE:TYPE"] = ONDE_TYPE
            pass
        if _ONDE_attrs is not None:
            constructargs["_ONDE_attrs"] = _ONDE_attrs
            pass
        if _ONDE_dataset_attrs is not None:
            constructargs["_ONDE_dataset_attrs"] = _ONDE_dataset_attrs
            pass
        
        constructargs.update(kwargs)
        newobj = cls(None, **constructargs)
        #for attrname in kwargs:
        #    setattr(newobj, attrname, kwargs[attrname])
        #    pass

        if file_or_graph is not None:
            return ONDEClassInstanceWrapper(_graph=graph,_obj=newobj)
        return newobj

    @classmethod
    def load_from_hdf5(cls,onde_file,fileobjs_by_h5path,h5_fh,h5_group):
        _ONDE_attrs = collections.OrderedDict()
        _ONDE_dataset_attrs = set()

        if h5_group.name in fileobjs_by_h5path:
            return fileobjs_by_h5path[h5_group.name].onde_instance
        
        for attrname in h5_group.attrs:
            h5_attr = h5_group.attrs[attrname]
            if isinstance(h5_attr,str) or isinstance(h5_attr,int) or isinstance(h5_attr,float):
                attr_obj = ONDEValue.new(h5_attr)
                _ONDE_attrs[attrname] = attr_obj
                pass

            elif isinstance(h5_attr,np.ndarray):
                string_info = h5py.check_string_dtype(h5_attr.dtype)
                if string_info is not None:
                    # array of strings
                    pass

                # Check if hdf5 reference
                ref_type = h5py.check_dtype(ref = h5_attr.dtype)
                if ref_type is not None:
                    # array of references
                    
                    attr_obj = ONDEReferenceArray.load_from_hdf5(onde_file,fileobjs_by_h5path,h5_fh,h5_attr)
                    _ONDE_attrs[attrname] = attr_obj
                    pass
                else:
                    # Array of values
                    attr_obj = ONDEArray.new(value = h5_attr)
                    _ONDE_attrs[attrname] = attr_obj
                    pass
                pass
            elif isinstance(h5_attr,h5py.Reference):
                attr_obj = ONDEObject.load_from_hdf5(onde_file, fileobjs_by_h5path, h5_fh, h5_fh[h5_attr])
                _ONDE_attrs[attrname] = attr_obj
           
                pass
            else:
                raise ValueError(f"Unknown hdf5 attribute type: {type(h5_attr).__name__:s}")
            pass
        for (subname,subobj) in h5_group.items():
            if isinstance(subobj,h5py.Dataset):
                # Check if hdf5 reference
                ref_type = h5py.check_dtype(ref = subobj.dtype)
                if ref_type is not None:
                    # array of references
                    
                    attr_obj = ONDEReferenceArray.load_from_hdf5(onde_file,fileobjs_by_h5path,h5_fh,subobj[...])
                    _ONDE_attrs[subname] = attr_obj
                    _ONDE_dataset_attrs.add(subname)
                    pass
                else:
                    # Array of values
                    attr_obj = ONDEArray.new(value = subobj[...])
                    _ONDE_attrs[subname] = attr_obj
                    _ONDE_dataset_attrs.add(subname)
                    pass
                pass
            # elif isinstance(subobj,h5py.Group): # These lines will enable support for hierarchical ONDE files
            #     attr_obj = ONDEObject.load_from_hdf5(onde_file, fileobjs_by_h5path, h5_fh, subobj)
            #     _ONDE_attrs[subname] = attr_obj
            else:
                raise ValueError(f"Unknown h5type {type(subobj).__name__:s} at hdf5 path {h5_group.name:s}")
            pass
        instance = cls(None,_ONDE_attrs = _ONDE_attrs,_ONDE_dataset_attrs = _ONDE_dataset_attrs)
        fileobj = ONDEFileObject(onde_instance = instance,hdf5_path = h5_group.name)
        fileobjs_by_h5path[h5_group.name] = fileobj
        return instance
    pass

class ONDEFileGraphSnapshot(ONDEObject):
    """ Not allowed to be referenced by any other ONDEObject.
    The ONDE:TYPE field should be absent.
    Attributes represent entry points of the graph."""
    def __init__(self, _orig = None, **kwargs):
        super().__init__(_orig, **kwargs)
        # remove the ONDE:TYPE added by the ONDEObject constructor because we are not really a proper object
        _ONDE_attrs = object.__getattribute__(self,"_ONDE_attrs")
        del _ONDE_attrs["ONDE:TYPE"]
        pass

    # Unlike ONDEObject, we index with _get_item, not with
    # _get_attr. Therefore we override the attribute methods
    # with the ones from ONDEBase.

    _get_attr=ONDEBase._get_attr
    _has_attr=ONDEBase._has_attr
    _set_attr=ONDEBase._set_attr
    # __getattribute__=ONDEBase.__getattribute__
    __getattribute__=object.__getattribute__
    __setattr__=ONDEBase.__setattr__

    def _get_item(self,index):
        return ONDEObject._get_attr(self,index)

    def _set_item(self,index,value):
        return ONDEObject._set_attr(self,index,value)

    def __getitem__(self,index):
        return self._get_item(index)

    def __setitem__(self,index,value):
        return self._set_item(index,value)
    
    def _list_items(self):
        return ONDEObject._list_attrs(self)

    def keys(self):
        return self._list_items()

    def __iter__(self):
        return iter(self.keys())

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
        newobj = cls(None)
        for attrname in kwargs:
            newobj._set_item(attrname, kwargs[attrname])
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
    _graph = None # ONDEFileGraph, used only with _obj
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

    def _get_obj(self):
        if self._obj is not None:
            return self._obj
        return self._proxy._get_obj()
        
    def _full_fieldname_from_attrname(self, _graph, obj, attrname):
        #_graph = object.__getattribute__(self,"_graph")
        if attrname in onde_basic_fields[obj.__class__.__name__]:
            return (attrname, None)
        
        if isinstance(obj,ONDEObject):
            classdefs = _graph.class_defs
            if attrname=="ONDE:TYPE":
                return (attrname, None)
            (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set) = classdefs.get_fields_dict(obj)
            if attrname in combined_fields_dict:
                field = combined_fields_dict[attrname]
                full_name = field.class_prefix + ":" + field.name
                return (full_name, field)
            else:
                # raise NameError(f"Unknown attribute {attrname:s} on ONDEObject of type {obj._ONDE_attrs['ONDE:TYPE'].value[-1]:s}.")
                return (None, None)
            pass
        return (attrname, None)
            
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
            (full_name, field) = self._full_fieldname_from_attrname(_graph, _obj, key)
            if full_name is None:
                full_name = key
                pass
            
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
                
                value_wrapper = self.__class__.new_from_obj(_graph,value)
                return value_wrapper
            else:
                
                return value
            pass
        pass

    def _get_attr(self,name):
        return self._get_attr_or_item("_get_attr",name)


    def _get_attr_dataset_storage(self,name):
        obj = self._get_obj()
        return obj._get_attr_dataset_storage(name)
    
    def _set_attr_or_item(self,set_method_name,key,value):
        our_proxy = object.__getattribute__(self,"_proxy")
        our_obj = object.__getattribute__(self,"_obj")
        _graph = object.__getattribute__(self,"_graph")

        if our_proxy is not None:
            our_obj = our_proxy._get_obj()
            _graph = our_proxy._graph
            pass
        
        full_name = key
        field = None
        if set_method_name == "_set_attr" or set_method_name == "_set_dataset_attr":
            (full_name, field) = self._full_fieldname_from_attrname(_graph, our_obj, key)       
            if full_name is None:
                full_name = key
                pass
            pass

        if field is not None and set_method_name == "_set_attr":
            # For now, if field.storage is "A or D", we always just store it as a dataset.
            if field.storage != "A":
                set_method_name = "_set_dataset_attr"
                pass
            pass
        
        if isinstance(value,ONDEClassInstanceWrapper):
            target_proxy = object.__getattribute__(value,"_proxy")
            target_obj = object.__getattribute__(value,"_obj")
            if our_proxy is not None and target_proxy is not None:
                set_method = getattr(our_proxy,set_method_name)
                set_method(full_name,target_proxy) # self._proxy._set_attr(key,target_proxy)
                pass
            elif self._proxy is not None and target_obj is not None:
                set_method = getattr(self._proxy,set_method_name)
                set_method(full_name,target_obj)
                pass
            elif self._obj is not None and target_proxy is not None:
                set_method = getattr(self._obj,set_method_name)
                set_method(full_name,target_proxy._get_obj()) # e.g. self._obj._set_attr(key,_proxy._get_obj())
                pass
            elif self._obj is not None and target_obj is not None:
                set_method = getattr(self._obj,set_method_name)
                set_method(full_name,target_obj)
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
            target_obj = onde_from_python(value, field)
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

    def _set_dataset_attr(self,name,value):
        self._set_attr_or_item("_set_dataset_attr",name,value)
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

    def _basic_field_set(self):
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            pass
        else:
            obj = self._obj
            pass

        fields = onde_basic_fields[obj.__class__.__name__]
        return frozenset(fields)

    def _class_field_set(self):
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            pass
        else:
            obj = self._obj
            pass
     
        if self._proxy is not None:
            _graph = self._proxy._graph
            pass
        else:
            _graph = self._graph
            pass
        
        classdefs = _graph.class_defs
        if classdefs is not None:

            if isinstance(obj, ONDEObject):
                (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set)=classdefs.get_fields_dict(obj)
                return frozenset(list(full_fields_dict.keys()))
            pass
        
        return frozenset()

    def _shorthand_field_set(self):
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            pass
        else:
            obj = self._obj
            pass
     
        if self._proxy is not None:
            _graph = self._proxy._graph
            pass
        else:
            _graph = self._graph
            pass
        
        classdefs = _graph.class_defs
        if classdefs is not None:

            if isinstance(obj, ONDEObject):
                (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set)=classdefs.get_fields_dict(obj)
                return frozenset(list(shorthand_fields_dict.keys()))
            pass
        
        return frozenset()

    def _assigned_attr_field_set(self):
        """Fields defined by actual assigned attributes of this object"""
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            pass
        else:
            obj = self._obj
            pass

        return frozenset(obj._list_attrs())

    def _all_field_set(self):
        return list(self._basic_field_set()|self._class_field_set()|self._shorthand_field_set()|self._assigned_attr_field_set()).sorted()
    
    def __dir__(self):
        if self._proxy is not None:
            obj = self._proxy._get_obj()
            pass
        else:
            obj = self._obj
            pass
     
        if self._proxy is not None:
            _graph = self._proxy._graph
            pass
        else:
            _graph = self._graph
            pass
        
        classdefs = _graph.class_defs
        if classdefs is not None:

            if isinstance(obj, ONDEObject):
                (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set)=classdefs.get_fields_dict(obj)
                return sorted(list(concise_set|self._basic_field_set()))
            pass
        
        return []   
      

        
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
            classdefs = _graph.class_defs
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
    def __setitem__(self,key,value):
        self._set_attr_or_item("_set_item",key,value)
        return

    def __getitem__(self,key):
        return self._get_attr_or_item("_get_item",key)
    
    
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

    def _repr_short(self, onde_class = None):
        our_proxy = object.__getattribute__(self,"_proxy")
        our_obj = object.__getattribute__(self,"_obj")
        _graph = object.__getattribute__(self,"_graph")

        if our_proxy is not None:
            our_obj = our_proxy._get_obj()
            _graph = our_proxy._graph
            pass

        return "InstanceWrapper of " + our_obj._repr_short()
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        our_proxy = object.__getattribute__(self,"_proxy")
        our_obj = object.__getattribute__(self,"_obj")
        _graph = object.__getattribute__(self,"_graph")

        if our_proxy is not None:
            our_obj = our_proxy._get_obj()
            _graph = our_proxy._graph
            pass

        classdefs = _graph.class_defs
        if classdefs is not None:

            if isinstance(our_obj, ONDEObject):
                (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set)=classdefs.get_fields_dict(our_obj)
                attrdict=collections.OrderedDict()
                for attrname in sorted(list(concise_set)):
                    attrval = self._get_attr(attrname)
                    dataset_storage = self._get_attr_dataset_storage(attrname)
                    storage_suffix = ""
                    if dataset_storage:
                        storage_suffix = " (hdf5 dataset storage)"
                        pass
                    
                    if attrval is not None:
                        attrdict[attrname] = attrval._repr_short() + storage_suffix
                        pass
                    else:
                        attrdict[attrname] = "None"
                        pass
                    pass
                return our_obj._repr(indentation,onde_class = f"InstanceWrapper({our_obj._ONDE_attrs['ONDE:TYPE'].value[-1]:s})", extra_attrs = attrdict)
            pass
        return our_obj._repr(indentation)
        
    def __repr__(self):
        return self._repr(0)
    
    @classmethod
    def new_from_proxy(cls, proxy):
        obj = proxy._get_obj()
        if not isinstance(obj,ONDEObject) and not isinstance(obj,ONDEReferenceArray):
            raise ValueError(f"ONDEClassInstanceWrapper only wraps non-leaf nodes, not {obj.__class__.__name__}")
        return cls(_proxy=proxy)

    @classmethod
    def new_obj(cls, graph, onde_classname, **kwargs):
        if graph.class_defs is None:
            raise ValueError("Graph does not have class definitions loaded")
        
        onde_class = graph.class_defs.classes[onde_classname]
        obj = ONDEObject.new(None,None,ONDE_TYPE = ONDEArray.new(onde_class.class_derivation, _frozen = True), **kwargs)
        # proxy = ONDEProxy(_path=None)

        return cls(_graph=graph,_obj=obj)

    @classmethod
    def new_from_obj(cls,graph,obj):
        if not isinstance(obj,ONDEBase):
            raise ValueError(f"Given object is of type {obj.__class__.__name__:s} and is not an ONDEBase instance")

        # onde_classname = object.__getattribute__(_orig, "ONDE:TYPE")
        if graph.class_defs is None:
            raise ValueError("Graph does not have class definitions loaded")
        return cls(_graph=graph,_obj=obj)
        
    pass

class ONDEClassDefinitions(object):
    """Represents the set of class definitions from the ONDE .csv file."""
    #NOTE: Immutable once constructed, except for field cache
    classes = None # Dictionary by name of ONDEClass
    acc_classes = None # Dictionary by name of accessory classes
    file_type = None # From the size_or_content of the blank ONDE:TYPE entry at the top of the csv file
    version = None # VERSION specification from the .csv file


    
    field_cache = None #dictionary by (tuple_of_class_derivation, frozen_set_of_accessory_classes) of a dictionary by field names and field name abbreviations of ONDEField objects
    
    def __init__(self):
        self.classes = collections.OrderedDict()
        self.acc_classes = collections.OrderedDict()
        self.field_cache = {}
        pass
    
    def get_fields_dict(self,obj):
        """returns three dictionaries by field name of ONDEField: the shorthand dictionary, the full dictionary, the combined dictionary, and the concise set. Automatically omits any shorthands that conflict with actual attributes. The concise set includes the shortest name for each field plus any fields which don't correspond to ONDEField objects""" 
        onde_type_value = obj._ONDE_attrs["ONDE:TYPE"]
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

        field_cache_key = (class_derivation, type_tags, frozenset(obj._ONDE_attrs._keys()))

        if field_cache_key in self.field_cache:
            return self.field_cache[field_cache_key]

        shorthand_fields_dict = collections.OrderedDict()
        full_fields_dict = collections.OrderedDict()
        combined_fields_dict = collections.OrderedDict()
        derivation_index=0
        mandatory_acc_classes = set()
        shorthand_blacklist = set()
        
        def add_field(fieldname,field,extra_keys):
            full_fields_dict[fieldname]=field
            combined_fields_dict[fieldname]=field
            for key in extra_keys:
                if key in shorthand_blacklist:
                    continue
                if key in obj._ONDE_attrs:
                    # Don't allow overriding an actual attribute of this object with a shorthand
                    continue
                if key in shorthand_fields_dict:
                    # key already present
                    if shorthand_fields_dict[key].class_prefix==full_fields_dict[fieldname].class_prefix and shorthand_fields_dict[key].name==full_fields_dict[fieldname].name:
                        # Override of a shorthand for the same thing already present. This is allowable.
                        shorthand_fields_dict[key]=full_fields_dict[fieldname]
                        combined_fields_dict[key]=full_fields_dict[fieldname]
                        pass
                    else:
                        # Conflicting shorthands. Remove pre-existing entry and blacklist
                        
                        del shorthand_fields_dict[key]
                        del combined_fields_dict[key]
                        shorthand_blacklist.add(key)
                        pass
                    pass
                else:
                    shorthand_fields_dict[key]=full_fields_dict[fieldname]
                    combined_fields_dict[key]=full_fields_dict[fieldname]
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

                add_field(fieldname,self.classes[classname].attributes[fieldname],extra_keys)
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
            for fieldname in acc_class.attributes:
                extra_keys=set()
                if ':' in fieldname:
                    #Shorthand for field name by admitting colon
                    extra_keys.add(fieldname[(fieldname.index(':')+1):])
                    pass

                add_field(fieldname,acc_class.attributes[fieldname],extra_keys)
                pass
            pass
        # Construct concise set
        reverse_combined = {}
        for fieldname in combined_fields_dict:
            if id(combined_fields_dict[fieldname]) in reverse_combined:
                reverse_combined[id(combined_fields_dict[fieldname])].append(fieldname)
                pass
            else:
                reverse_combined[id(combined_fields_dict[fieldname])] = [fieldname]
                pass
            pass

        concise_set=set()
        for objid in reverse_combined:
            shortest = sorted(reverse_combined[objid], key=len)[0]
            concise_set.add(shortest)
            pass

        for attrname in obj._ONDE_attrs:
            if attrname not in full_fields_dict:
                concise_set.add(attrname)
                pass
            pass

        concise_set_frozen=frozenset(concise_set)
        

        # import pdb
        # pdb.set_trace()
        
        self.field_cache[field_cache_key] = (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set_frozen)
        return (shorthand_fields_dict,full_fields_dict,combined_fields_dict,concise_set_frozen)

    
    @classmethod
    def load_from_csv(cls, filename,extra_class_defs = None):
        class_defs = ONDEClassDefinitions()

        if extra_class_defs is not None:
            raise ValueError("Extra class definitions not yet supported")
        
        with open(filename,mode="r",encoding="utf-8-sig") as csvfh:
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
                
                if name == "ONDE:VERSION":
                    class_defs.version=size_or_content
                    continue

                if name == "ONDE:FILETYPE":
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
    _graph = None # ONDEFileGraph object we started with 
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
            snap = graph.latest_snap
            pass

        _path = object.__getattribute__(self, "_path")
        return snap._follow_path(_path)

    def __getattribute__(self, name):
        if name.startswith("_"):
            if name in { "_set_attr","_set_dataset_attr", "_get_attr","_get_attr_dataset_storage","_get_item","_set_item","_get_data","_set_data","_set_attr_or_item_or_data","_get_obj","_follow_path","__class__","__dict__","_graph","_repr","_repr_short"}:
                return object.__getattribute__(self, name)
            elif  name in {"_freeze", "_frozen",}:
                obj = self._get_obj()
                return getattr(obj,name)
            raise ValueError(f"ONDEProxy: invalid underscore attribute {name}")
        obj = self._get_obj()
        if isinstance(obj,ONDEFileGraphSnapshot):
            return object.__getattribute__(obj, name) # The file graph snapshot uses items not attributes for the onde graph, so regular old attribute behavior is fine.
            
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
        
    def _get_attr_dataset_storage(self, name):
        obj = self._get_obj()
        return obj._get_attr_dataset_storage(name)

        
    def _has_attr(self, name):
        obj = self._get_obj()
        return obj._has_attr(name)

    
    def _set_attr(self, name, value):
        self._set_attr_or_item_or_data('_set_attr', name, value)
        pass

    def _set_dataset_attr(self, name, value):
        self._set_attr_or_item_or_data('_set_dataset_attr', name, value)
        pass
    

    def _get_item(self, key):
        obj = self._get_obj()
        item_obj = obj._get_item(key)

        if isinstance(item_obj, ONDEBase):
            return self.__class__.new_from_proxy(self, key)

        return item_obj
    
    def _set_item(self, index, value):
        self._set_attr_or_item_or_data('_set_item', index, value)
        pass

    def __getitem__(self,index):
        return self._get_item(index)

    def __setitem__(self,index,value):
        return self._set_item(index,value)
    
    def _get_data(self, name):
        obj = self._get_obj()
        data_obj = obj._get_data(name)

        return data_obj
    
    def _set_data(self, name, value):
        self._set_attr_or_item_or_data('_set_data', name, value)
        pass
    
    
    def _set_attr_or_item_or_data(self, set_method_name, key, value):
        ''' Use the named set method (_set_attr,_set_dataset_attr, _set_item, or  _set_data) to assign the element specified by key to the given value'''
        
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
                if len(path) > 0:
                    graph_replace_node(_trans, scope, path, obj, replacement)
                    pass
                else:
                    assert(obj is _trans.snap and replacement is _trans.snap)
                    pass
                
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

    def _repr_short(self, onde_class=None):
        return object.__getattribute__(self._get_obj(), "_repr_short")(onde_class)
    
    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        return repr_helper(indentation, f"Writable proxy of {object.__getattribute__(self._get_obj(), '_repr')(indentation+2, onde_class=onde_class, extra_attrs=extra_attrs):s}")
    
    def __repr__(self):
        return f"Writable proxy of {repr(self._get_obj()):s}"
    pass


def _traverse_snapshot_fileneeded_objs(class_defs,cur_obj,add_cur_to_needed,needed_objs):
    """Traverse the graph of ONDEBase objects depth-first starting at cur_obj, accumulating ONDEObjects that will need to be written into the file into the ordered dictionary needed_objs. It is an ordered dictionary because we will use its ordering for the object creation so that objects are created before they are used. The values stored into the ordered dictionary are all None."""
    edges = cur_obj._list_edges()

    for edge in edges:
        sub_obj = cur_obj._follow_path((edge,))
        if sub_obj in needed_objs:
            continue # sub_obj has already been processed 
        sub_is_needed = type(sub_obj) is ONDEObject
        _traverse_snapshot_fileneeded_objs(class_defs,sub_obj,sub_is_needed,needed_objs)
        pass

    if add_cur_to_needed:
        needed_objs[cur_obj] = None
        pass
    pass


def _search_h5_for_onde_datasets(h5_fh,h5_group,dataset_h5_groups,h5_groups_seen):
    """ dataset_h5_groups is a dictionary by hdf5 path of hdf5 group objects that contain an ONDE:TYPE attribute starting with ONDE_DATASET


    h5_groups_seen is a set of hdf5 group paths seen during the traversal
    """

    if "ONDE:TYPE" in h5_group.attrs and h5_group.attrs["ONDE:TYPE"][0] == "ONDE_DATASET":
        dataset_h5_groups[h5_group.name] = h5_group
        pass

    h5_groups_seen.add(h5_group.name)

    for (name,item) in h5_group.items():
        if isinstance(item,h5py.Group) and item.name not in h5_groups_seen:
            _search_h5_for_onde_datasets(h5_fh,item,dataset_h5_groups,h5_groups_seen)
            pass
        pass
    pass

class ONDEFile(object):
    """Represents an HDF5 file that may contain ONDE objects. Unlike most other data structures it is not thread safe (only one thread at a time should be manipulating an ONDEFile). However it is safe for multiple threads to simultaneously access and even modify (by the usual ONDEProxy methods) objects from a single file, so long as only a single thread attempts to write any changes to disk."""
    file_object_dict = None # Dictionary by frozen ONDEBase object of ONDEFileObject.
    class_defs = None # ONDEClassDefinitions object
    h5path = None # file path used
    mode = None # mode used to open the file
    fh = None # h5py file handle.
    graph = None # ONDEFileGraph object (or subclass)
    db_maxidx = None # integer representing the highest index used in the PyONDE_DB hdf5 group
    version = None
    filetype = None
    
    def __init__(self, class_defs = None, h5path = None, mode = None, fh = None,version = None, filetype = None):
        self.class_defs = class_defs
        self.h5path = h5path
        self.mode = mode
        self.fh = fh
        self.version = version
        self.filetype = filetype

        self.file_object_dict = {}
        self.graph = ONDEFileGraph(class_defs = self.class_defs)

        if self.mode not in {"r","r+","w","w-","x","a"}:
            raise ValueError(f"Unknown mode: {self.mode:s}")
        
        if self.mode == "r+" or self.mode == "a" or self.mode == "r":
            
            if version is not None:
                raise ValueError("Attempting to set ONDE_VERSION on existing file.")
            if filetype is not None:
                raise ValueError("Attempting to set ONDE_FILETYPE on existing file.")
            self.load() # Attempt to read in current contents.
            pass
     
        pass

    def __getitem__(self,index):
        return self.graph._get_item(index)

    def __setitem__(self,index,value):
        return self.graph._set_item(index,value)

    def keys(self):
        return self.graph.keys()

    def __iter__(self):
        return iter(self.keys())
    
    def load(self):
        self.version = self.fh.attrs["ONDE_VERSION"]
        self.filetype = self.fh.attrs["ONDE_FILETYPE"]

        # check for PyONDE_DB and db_maxidx
        self.db_maxidx = 0
        if "PyONDE_DB" in self.fh:
            db = self.fh["PyONDE_DB"]
            for db_key in db.keys():
                if db_key.isdigit():
                    db_keynum = int(db_key)
                    if db_keynum > self.db_maxidx:
                        self.db_maxidx = db_keynum
                        pass
                    pass
                pass
            pass
        #import pdb
        #pdb.set_trace()
        # Search through group structure for datasets.
        dataset_h5_groups = collections.OrderedDict() # dictionary by hdf5 path of hdf5 group objects that contain an ONDE:TYPE attribute starting with ONDE_DATASET
        h5_groups_seen = set() # set of hdf5 group paths seen during the traversal
        _search_h5_for_onde_datasets(self.fh,self.fh,dataset_h5_groups,h5_groups_seen)

        fileobjs_by_h5path = {}

        dataset_instances_by_h5path = collections.OrderedDict()
        for group_path in dataset_h5_groups:
            dataset_instances_by_h5path[group_path] = ONDEObject.load_from_hdf5(self,fileobjs_by_h5path,self.fh,dataset_h5_groups[group_path])
            pass

        # replace existing contents of self.group as an atomic transaction
        with ONDETransaction(self.graph) as tr:
            for key in list(tr.graph.keys()):
                del tr.graph[key]
                pass

            for h5path in dataset_instances_by_h5path:

                instance = dataset_instances_by_h5path[h5path]
                unique_id = id(instance) # !!!*** need a proper unique ID
                tr.graph[str(unique_id)] = instance
                pass
            pass
        pass
    
                                                            

    def flush(self):
        snap = self.graph.latest_snap

        # Ensure ONDE_FILETYPE and ONDE_VERSION are present
        if "ONDE_VERSION" not in self.fh.attrs:
            if self.version is not None:
                self.fh.attrs["ONDE_VERSION"] = self.version
                pass
            else:
                self.fh.attrs["ONDE_VERSION"] = self.class_defs.version
                pass
            pass

        if "ONDE_FILETYPE" not in self.fh.attrs:
            if self.filetype is not None:
                self.fh.attrs["ONDE_FILETYPE"] = self.filetype
                pass
            else:
                self.fh.attrs["ONDE_FILETYPE"] = "ONDE_UT"
                pass
            pass

        # Make sure PyONDE_DB HDF5 group exists.
        if not "PyONDE_DB" in self.fh:
            self.fh.create_group("PyONDE_DB")
            self.db_maxidx = 0
            pass

        db=self.fh["PyONDE_DB"]
        db_path = db.name

        present_objs = set(self.file_object_dict.keys()) # set of ONDEBase objects already present in the file
        needed_objs = collections.OrderedDict()
        _traverse_snapshot_fileneeded_objs(self.class_defs,snap,False,needed_objs) # this function will fill needed_objs with an ordered set (implemented as keys of an ordered dictionary) of ONDEBase objects that are needed in the file. The ordering is depth-first so that leaf nodes get included prior to branch nodes that reference them. The False parameter indicates that the snap itself does NOT get included.

        needed_objs_set = set(needed_objs.keys())
        # We need to remove objects that are listed in present_objs but not needed_objs
        to_remove = present_objs.difference(needed_objs_set)

        # We need to add objects that are listed in needed_objs but not present_objs
        to_add = needed_objs_set.difference(present_objs)

        # Perform the removal
        for obj in to_remove:
            fileobj = self.file_object_dict[obj]

            #if fileobj.hdf5_attrname is not None:
            #    # Object is stored as an attribute ... unnecessary becuase attributes will be written as part of their parent object.
            #    attr_parent = self.fh[fileobj.hdf5_path]
            #    del attr_parent[fileobj.hdf5_attrname]
            #    pass
            #else:
            hdf5_obj=self.fh[fileobj.hdf5_path]
            hdf5_parent = hdf5_obj.parent
            del hdf5_parent[posixpath.basename(hdf5_obj.name)]
            

            fileobj.close()
            del self.file_object_dict[obj]
            pass
        

        # add in the needed objects. Loop ordering is because needed_objs is actually an OrderedDict.
        for needed_obj in needed_objs:
            if not needed_obj in to_add:
                continue

            obj_name = f"{self.db_maxidx + 1:05d}"
            self.db_maxidx += 1

            fileobj = ONDEFileObject(onde_instance = needed_obj,hdf5_path = posixpath.join(db_path,obj_name))

            needed_obj._hdf5_write_group(onde_file = self,parent = db,parent_path = db_path,name = obj_name,onde_fileobj = fileobj)

            self.file_object_dict[needed_obj] = fileobj
        
            pass
        
                                    
        self.fh.flush()
        pass


    
    def close(self):

        if self.mode in {"r+","w","w-","x","a"}:
            self.flush()
            pass
        
        self.fh.close()
        for key in self.file_object_dict:
            self.file_object_dict[key].close()
            pass
        self.file_object_dict = None
        self.fh = None
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()
        return False

    def _repr(self, indentation, onde_class=None, extra_attrs={}):
        return repr_helper(indentation, "ONDEFile", _extra_info = f"open on \"{self.h5path:s}\"")+"\n"+self.graph._repr(indentation+2)
        
    def __repr__(self):
        return self._repr(0)
    
    @classmethod
    def new(cls, h5path, mode, class_defs_path=None, extra_class_defs = None, onde_version = None):
        fh = h5py.File(h5path, mode)
        
        class_defs = None
        if class_defs_path is None and onde_version is not None:
            class_defs_path = os.path.join(os.path.split(sys.modules[cls.__module__].__file__)[0],"onde_versions",f"ONDE_fields_v{onde_version:s}.csv")
            pass
        if class_defs_path is not None:
            class_defs = ONDEClassDefinitions.load_from_csv(class_defs_path,extra_class_defs = extra_class_defs)
            pass
        
        return cls(class_defs = class_defs, h5path = h5path, mode = mode, fh = fh)
    
    pass

class ONDEDatasetFile(ONDEFile):
    """Represents an ONDE 1.0 file that is expected to contain one or more ONDE_DATASET instances."""
    pass

class ONDEFileObject(object):
    """Represents a frozen ONDEBase subclass instance that is represented in an HDF5 file."""
    onde_instance = None # Reference to an ONDEBase subclass instance.
    hdf5_path = None # Path of the given object in the file.
    #hdf5_attrname = None # If this FileObject is stored as an attribute, then this is the attribute name. Unnecessary because attributes will be written as part of their parent object.
    # hdf5_obj = None # Actual h5py object.

    def __init__(self, onde_instance = None, hdf5_path = None): #, hdf5_obj = None):
        self.onde_instance = onde_instance
        self.hdf5_path = hdf5_path
        #self.hdf5_obj = hdf5_obj

        with self.onde_instance._file_realizations_lock:
            self.onde_instance._file_realizations.add(self)
            pass
        
        pass

    def close(self):
        self.hdf5_path = None
        #self.hdf5_obj = None

        with self.onde_instance._file_realizations_lock:
            self.onde_instance._file_realizations.remove(self)
            pass
        self.onde_instance = None
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
