@startuml
' Process with PlantUML https://www.plantuml.com
title "PyONDE Low Level Class Structure"
skinparam dpi 300

class ONDEBase {
  
}

class ONDEValue {
  value: string, integer, float, etc.
}

class ONDEArray {
  value: numpy array
}

class ONDEReferenceArray {
  refs: array of references
}

class ONDEObject {
  _ONDE_attrs: dictionary of contained ONDEBase
  _ONDE_dataset_attrs: set of field names for fields which should be stored as HDF5 datasets, not HDF5 attributes
}

class ONDEFileGraphSnapshot {
  _ONDE_attrs: dictionary of graph entry points
}

class ONDEFileGraph {
  latest_snap: ONDEFileGraphSnapshot
}


ONDEBase <-- ONDEObject::_ONDE_attrs : references 
ONDEBase <|-- ONDEValue : extends
ONDEBase <|-- ONDEArray : extends
ONDEBase <|-- ONDEReferenceArray : extends
ONDEBase <|-- ONDEObject : extends
ONDEObject <|-- ONDEFileGraphSnapshot : extends
ONDEFileGraphSnapshot <-- ONDEFileGraph::latest_snap : references
ONDEObject <-- ONDEFileGraphSnapshot::_ONDE_attrs : references
ONDEObject <-- ONDEReferenceArray::refs : references
@enduml