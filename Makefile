# Gyre & Gimble — Commander X16
CL65    ?= cl65
X16EMU  ?= x16emu

NAME    := GYRE
BUILD   := build
PRG     := $(BUILD)/$(NAME).PRG
SOURCES := $(wildcard src/*.asm)

.PHONY: all run clean

all: $(PRG)

$(PRG): $(SOURCES) | $(BUILD)
	$(CL65) -t cx16 -C cx16-asm.cfg -u __EXEHDR__ -o $@ \
		-l $(BUILD)/$(NAME).list -m $(BUILD)/$(NAME).map -Ln $(BUILD)/$(NAME).sym \
		src/main.asm

$(BUILD):
	mkdir -p $@

run: $(PRG)
	$(X16EMU) -prg $(PRG) -run -scale 2

clean:
	rm -rf $(BUILD)
