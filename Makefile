all: LowLevel_Class_Structure.png



%.png: %.md
	plantuml $<
