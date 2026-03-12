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
  store_as_dataset: True or False
}

class ONDEReferenceArray {
  refs: array of references
  store_as_dataset: True or False
}

class ONDEObject {
  _ONDE_type: list of classes
  _ONDE_type_tags: list of accessory classes
  _ONDE_attrs: dictionary of contained ONDEBase
}

class ONDEGraphSnapshot {
  _ONDE_type: empty list
  _ONDE_attrs: dictionary of graph entry points
}

class ONDEGraph {
  latest_snap: ONDESnapshot
}


ONDEBase <-- ONDEObject::_ONDE_attrs : references 
ONDEBase <|-- ONDEValue : extends
ONDEBase <|-- ONDEArray : extends
ONDEBase <|-- ONDEReferenceArray : extends
ONDEBase <|-- ONDEObject : extends
ONDEObject <|-- ONDEGraphSnapshot : extends
ONDEGraphSnapshot <-- ONDEGraph::latest_snap : references
ONDEObject <-- ONDEGraphSnapshot::_ONDE_attrs : references
ONDEObject <-- ONDEReferenceArray::refs : references
@enduml