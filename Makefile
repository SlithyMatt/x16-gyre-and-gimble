# Gyre & Gimble — Commander X16
CL65    ?= cl65
X16EMU  ?= x16emu
PYTHON  ?= python3

NAME    := GYRE
BUILD   := build
PRG     := $(BUILD)/$(NAME).PRG
BOARD   := $(BUILD)/RINGS.BIN
SOURCES := $(wildcard src/*.asm src/*.inc)
GEN_INC := $(BUILD)/regions.inc $(BUILD)/level.inc

.PHONY: all run clean

all: $(PRG) $(BOARD)

$(PRG): $(SOURCES) $(GEN_INC) | $(BUILD)
	$(CL65) -t cx16 -C cx16-asm.cfg -u __EXEHDR__ \
		--asm-include-dir src --asm-include-dir $(BUILD) -o $@ \
		-l $(BUILD)/$(NAME).list -m $(BUILD)/$(NAME).map -Ln $(BUILD)/$(NAME).sym \
		src/main.asm

$(BOARD) $(BUILD)/regions.inc &: tools/genrings.py | $(BUILD)
	$(PYTHON) tools/genrings.py $(BOARD) $(BUILD)/regions.inc

$(BUILD)/level.inc: tools/level.py levels/level01.txt | $(BUILD)
	$(PYTHON) tools/level.py levels/level01.txt $@

$(BUILD):
	mkdir -p $@

# Run from the build directory so the game can load RINGS.BIN from the host FS
run: all
	cd $(BUILD) && $(X16EMU) -prg $(NAME).PRG -run -scale 2

clean:
	rm -rf $(BUILD)
