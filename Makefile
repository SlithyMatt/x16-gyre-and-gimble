# Gyre & Gimble — Commander X16
CL65    ?= cl65
X16EMU  ?= x16emu
PYTHON  ?= python3

NAME    := GYRE
BUILD   := build
PRG     := $(BUILD)/$(NAME).PRG
BOARD   := $(BUILD)/RINGS.BIN
SOURCES := $(wildcard src/*.asm src/*.inc)
GEN_INC := $(BUILD)/regions.inc $(BUILD)/waypoints.inc $(BUILD)/level.inc $(BUILD)/tove.inc

.PHONY: all run clean joytest

all: $(PRG) $(BOARD)

$(PRG): $(SOURCES) $(GEN_INC) | $(BUILD)
	$(CL65) -t cx16 -C cx16-asm.cfg -u __EXEHDR__ \
		--asm-include-dir src --asm-include-dir $(BUILD) -o $@ \
		-l $(BUILD)/$(NAME).list -m $(BUILD)/$(NAME).map -Ln $(BUILD)/$(NAME).sym \
		src/main.asm

$(BOARD) $(BUILD)/regions.inc $(BUILD)/waypoints.inc &: tools/genrings.py | $(BUILD)
	$(PYTHON) tools/genrings.py $(BOARD) $(BUILD)/regions.inc $(BUILD)/waypoints.inc

$(BUILD)/tove.inc: tools/gensprites.py assets/tove.txt | $(BUILD)
	$(PYTHON) tools/gensprites.py assets/tove.txt tove $@

LEVELS  := $(sort $(wildcard levels/*.txt))

$(BUILD)/level.inc: tools/level.py $(LEVELS) | $(BUILD)
	$(PYTHON) tools/level.py build $@ $(LEVELS)

$(BUILD):
	mkdir -p $@

# Test build: pad 1 replays a scripted solve of every level (see tools/joyscript.py)
joytest: $(BUILD)/JOYTEST.PRG $(BOARD)
	cd $(BUILD) && $(X16EMU) -prg JOYTEST.PRG -run -scale 2

$(BUILD)/JOYTEST.PRG: $(SOURCES) $(GEN_INC) $(BUILD)/joyscript.inc
	$(CL65) -t cx16 -C cx16-asm.cfg -u __EXEHDR__ --asm-define JOY_SCRIPT \
		--asm-include-dir src --asm-include-dir $(BUILD) -o $@ src/main.asm

$(BUILD)/joyscript.inc: tools/joyscript.py tools/level.py $(LEVELS) | $(BUILD)
	$(PYTHON) tools/joyscript.py $@ $(LEVELS)

# Run from the build directory so the game can load RINGS.BIN from the host FS
run: all
	cd $(BUILD) && $(X16EMU) -prg $(NAME).PRG -run -scale 2

clean:
	rm -rf $(BUILD)
