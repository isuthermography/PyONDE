import h5py
import sys
import os
import os.path
import threading
import copy
import numbers
import collections
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
        object.__setattr__(self, "_byobjid",{id(bystrings[s]): s for s in bystrings})
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_frozen", False)
        pass

    def __iter__(self):
        _bystrings = object.__getattribute__(self, "_bystrings")
        return _bystrings.__iter__() # Just use iterator of underlying dictionary

    def __getattribute__(self, name):
        _bystrings = object.__getattribute__(self, "_bystrings")

        if name.startswith("_"):
            if name == "_freeze" or name == "_frozen":
                return object.__getattribute__(self, name)
            raise IndexError("TwoWayDictionary: Indexes are not allowed to have leading underscores")
        return _bystrings[name]


    def __getitem__(self, obj):
        _byobjid = object.__getattribute__(self, "_byobjid")
        objidx = _byobjid[id(obj)]
        return objidx # Returns frozenset
    
    
    def __setattr__(self, name, obj):
        if name.startswith("_"):
            raise ValueError("Attributes with leading underscores not allowed")
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
            
            _bystrings[name] = obj

            nameset = frozenset({name})
            # Check if this object already has an existing set of references
            if id(obj) in _byobjid:
                nameset = _byobjid[id(obj)] | nameset
                pass
            _byobjid[id(obj)] = nameset
            pass
        pass

    def _freeze(self):
        object.__setattr__(self, "_frozen", True)
        pass
    pass


class ONDEGraph(object):
    """Represents the graph of interconnected ONDE objects
    and attributes. May relate to any number of actual files."""
    lock = None # threading.Lock that protects access to modify graph structure information.
    latest_snap = None # class ONDEGraphSnapshot

    def __init__(self, snapshot = None):
        self.lock = threading.Lock()

        if snapshot is None:
            snapshot = ONDEGraphSnapshot.new()

            pass
        self.latest_snap = snapshot
        pass
    pass


class ONDETransaction(object):
    """Represents a transaction in which the ONDEGraph is modified"""
    graph = None # ONDEGraph object
    pass


class ONDEOpScope(object):
    """Represents scope of an operation. This includes a list of paths originating at entry points that are included in the scope, and an overriding list of paths originating at entry points that are excluded from the scope"""
    include_paths = None # List of ONDEPath objects
    exclude_paths = None # List of ONDEPath objects
    exclude_objects = None #  List of objects to be excluded
    pass



class ONDEPath(list):
    """A path, essentially a list of strings, starting
    with an entry_point name and followed by attribute names
    for ONDEObjects, that leads to an ONDEBase."""
    pass

class ONDEBase(object):
    # _graph = None # ONDEGraph object
    _referencedby = None # set of ONDEBase objects that reference this object. They should all be part of the given ONDEGraph. The _referencedby member can still be changed even after an instance is frozen becuase new objects can reference it. Note that the _referencedby field is generally only updated to include new objects when those objects become frozen.
    _frozen = None # True/False: has this object been finalized and therefore become immutable

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
            _referencedby = frozenset()
            pass
        object.__setattr__(self, "_referencedby", _referencedby)
        object.__setattr__(self, "_frozen", False)
        if _frozen:
            self._freeze() # Derived class may have additional operations
            pass
        pass

    def __copy__(self):
        new = self.__class__(self)
        return new

    def __hash__(self):
        return id(self) # For now we identify ourself by our pointer. In the future perhaps we might use a content hash.
    
    def _freeze(self):
        _frozen = object.__getattribute__(self, "_frozen")
        if _frozen:
            raise RuntimeError("Attempting to freeze an object that is already frozen")
        object.__setattr__(self, "_frozen", True)
        pass

    def _add_referencedby(self, obj_that_references_us):
        _referencedby = object.__getattr__(self, "_referencedby")
        _referencedby.add(obj_that_references_us)
        pass

    @classmethod
    def new(cls):
        raise RuntimeError("ONDEBase class is not independently instantiatable")
    
    pass

class ONDEValue(ONDEBase):
    """ONDEValue represents a string, integer, float,
    small array, or other simple value. An ONDEValue
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
            elif isinstance(value, collections.Sequence):
                value = tuple(value)
                pass
            elif isinstance(value, np.ndarray):
                value.flags.writeable = False
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
    
    pass

class ONDEH5Dataset(ONDEBase):
    """Represents an HDF5 dataset"""

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
        if _ONDE_type in kwargs:
            _ONDE_type = kwargs["_ONDE_type"]
            del kwargs["_ONDE_type"]
            pass

        _ONDE_attrs = None
        if _orig is not None:
            _ONDE_attrs = object.__getattribute__(_orig, "_ONDE_attrs")
            pass
        if _ONDE_attrs in kwargs:
            #if _ONDE_attrs is not None:
            #    _ONDE_attrs.update(kwargs["_ONDE_attrs"])
            #    pass
            #else:
            _ONDE_attrs = kwargs["_ONDE_attrs"]
            #    pass
            del kwargs["_ONDE_attrs"]
            pass
        
        super().__init__(_orig, **kwargs)
        object.__setattr__(self, "_ONDE_type", list(_ONDE_type)) ######################## 'NoneType' object is not iterable
        ONDE_attrs = TwoWayDictionary(_ONDE_attrs)
        object.__setattr__(self, "_ONDE_attrs", ONDE_attrs)
        pass

    def __getattribute__(self, name):
        if name.startswith("_"):
            if name == "_freeze" or name == "_frozen" or name == "_add_referencedby":
                return object.__getattribute__(self, name)
            raise IndexError("ONDEObject: Attributes may not have leading underscores")
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        return getattr(_ONDE_attrs, name)

    def __setattr__(self, name, value):
        _frozen = object.__getattribute__(self, "_frozen")
        if _frozen:
            raise RuntimeError("Attempting to modify an object that is already frozen")
        _ONDE_attrs = object.__getattribute__(self, "_ONDE_attrs")
        setattr(_ONDE_attrs, name, value)
        pass
    
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
        return cls
    pass

class ONDEGraphSnapshot(ONDEObject):
    """ Not allowed to be referenced by any other object.
    The _ONDE_type field should be empty.
    Attributes represent entry points of the graph."""
    def __init__(self, _orig = None, **kwargs):
        super().__init__(self, _orig, **kwargs)
        pass

    #@classmethod
    #def new(cls, entry_points = None):
    #    if entry_points is None:
    #        entry_points = TwoWayDictionary()
    #        pass
    #    return cls(None, _ONDE_type = [], _ONDE_attrs = entry_points)
    @classmethod
    def new(cls, **kwargs):
        return cls(None, _ONDE_type = [],**kwargs)
    pass

class ONDEProxy(object):
    """Mutable proxy reference to a graph entry that remembers context."""
    _graph = None # ONDEGraph object we started with 
    _path = None # ONDEPath of the object we are proxying
    _obj = None # The actual object we are proxying
    _obj_snap = None # Snapshot from which we obtained _obj
    pass





#class ONDEOperation(object):
#    """Represents an operation that can be part of a transaction"""
#    scope = None # ONDEOpScope reference or None representing default (local) scope
#    pass


#class ONDEAssignValue(ONDEOperation):
#    """Represents assignment of the value within an ONDEValue object"""
#    attr_name = None # Usually "value"
#    attr_value = None # String, int, float, immutable array, etc.
#    pass
