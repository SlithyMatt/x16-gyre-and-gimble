; Commander X16 constants
; Reference: https://github.com/X16Community/x16-docs

; KERNAL
CHROUT          = $FFD2
GETIN           = $FFE4

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

; Banking
RAM_BANK        = $00
ROM_BANK        = $01
