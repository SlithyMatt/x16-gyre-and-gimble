; Commander X16 constants
; Reference: https://github.com/X16Community/x16-docs

; KERNAL
SETLFS          = $FFBA
SETNAM          = $FFBD
LOAD            = $FFD5
CHROUT          = $FFD2
GETIN           = $FFE4
PLOT            = $FFF0
SCREEN_MODE     = $FF5F
JOYSTICK_GET    = $FF56
RDTIM           = $FFDE

; VERA registers
VERA_ADDR_L     = $9F20
VERA_ADDR_M     = $9F21
VERA_ADDR_H     = $9F22
VERA_DATA0      = $9F23
VERA_DATA1      = $9F24
VERA_CTRL       = $9F25
VERA_IEN        = $9F26
VERA_ISR        = $9F27
VERA_DC_VIDEO   = $9F29
VERA_DC_HSCALE  = $9F2A
VERA_DC_VSCALE  = $9F2B
VERA_L1_TILEBASE = $9F36
VERA_AUDIO_CTRL = $9F3B
VERA_AUDIO_RATE = $9F3C
VERA_AUDIO_DATA = $9F3D

VRAM_PALETTE    = $1FA00
VERA_INC_1      = $10           ; ADDR_H auto-increment of 1

; Banking
RAM_BANK        = $00
ROM_BANK        = $01

; Free zero page for user programs: $22-$7F
ZP_PTR          = $22
