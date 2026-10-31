; Gyre & Gimble — entry point
.include "x16.inc"

.segment "CODE"

start:
    ldx #0
@loop:
    lda title,x
    beq @done
    jsr CHROUT
    inx
    bne @loop
@done:
    rts

.segment "RODATA"

title:
    .byte $0e                   ; switch to upper/lowercase charset
    .byte $93                   ; clear screen
    .byte "Gyre & Gimble", $0d
    .byte "(provisional title)", $0d, 0
