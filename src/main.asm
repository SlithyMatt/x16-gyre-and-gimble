; Gyre & Gimble — prototype
;
; Rotate the rings until a tunnel runs from the entry gap at the top of the
; outer ring to the burrow in the middle. Each screen cell is redrawn from
; pre-shaded pieces when it changes, in its color class's palette row; the
; palette comes from the level's theme (see DESIGN.md).

.include "x16.inc"
.include "board.inc"

; Tove sprite
TOVE_SPRITE     = 1             ; sprite 0 is the KERNAL mouse pointer
TOVE_VRAM       = $13000        ; KERNAL's sprite image area in this mode
TOVE_PAL        = ROW_TOVE      ; palette offset: indices 224-239
TOVE_Z          = 2 << 2        ; Z-depth 2: over the board, under the HUD text
WALK_STEPS      = 8             ; frames per waypoint segment (make_step assumes 8)
VRAM_SPRITES    = $1FC00

; Garden critters: borogoves and mome raths (see assets/critters.txt)
CRITTER_SPRITE  = 2             ; sprites 2-5, under the tove
NCRITTERS       = 4
CRITTER_VRAM    = TOVE_VRAM + TOVE_FRAMES * 128
CRITTER_PAL     = ROW_CRITTER
BOROGOVE        = 0             ; first frame of each kind
RATH            = 4
POSE_WALK       = 0             ; walk A, then walk B
POSE_IDLE       = 2             ; peck or sniff
POSE_CHEER      = 3             ; fluff or outgrabe

; Cell bits (match tools/level.py)
IN              = $01
OUT             = $02
CW              = $04
TUN             = $80

RINGS           = 4
CELLS           = 12
NCELLS          = RINGS * CELLS
ENTRY_K         = (RINGS - 1) * CELLS   ; outer ring, position 0 (top)

CCW             = $08           ; drawn-cell key: opens counter-clockwise
KEY_CLASS       = $70           ; drawn-cell key: class palette row << 4

; Zero page (ZP_PTR is the general pointer)
ZP_THEME        = $24           ; the level's theme palette data
ZP_CLASS        = $26           ; class row << 4 for draw_piece

PALETTE_ROW     = 32            ; bytes per palette row

; CRT title-safe text area (10% margins on 40x30); keep all text inside it
SAFE_L          = 4
SAFE_R          = 35
SAFE_T          = 3
SAFE_B          = 26

KEY_UP          = $91
KEY_DOWN        = $11
KEY_LEFT        = $9d
KEY_RIGHT       = $1d
KEY_DEL         = $14
KEY_RETURN      = $0d

; Star ratings: 3 at par, 2 within par + par/2, else 1
STAR_PETSCII    = $b0           ; CHROUT codes for the star glyphs ...
STAR_SCREEN     = $70           ; ... and the screen codes they print as
CLR_LIT         = $9e           ; yellow: earned
CLR_DIM         = $98           ; gray: not earned (luma differs, not just hue)
CLR_TEXT        = $05           ; white

; SNES pads: frames before a held D-pad direction repeats, then between repeats
JOY_DELAY       = 18
JOY_RATE        = 8
JOY_DPAD        = $0f           ; byte 0: UP DN LT RT

.assert ROW_TUNNEL = ROW_STONE + RINGS, error, "class rows must be contiguous"
.assert ROW_LIT = ROW_TUNNEL + 1, error, "class rows must be contiguous"
.assert ROW_WALL = ROW_LIT + 1, error, "class rows must be contiguous"
.assert (IN | OUT | CW | CCW) & KEY_CLASS = 0, error, "drawn-cell key bits overlap"

.macro print_at row, col, str
    ldx #row
    ldy #col
    clc
    jsr PLOT
    lda #<str
    sta ZP_PTR
    lda #>str
    sta ZP_PTR+1
    jsr print_str
.endmacro

.segment "RODATA"

.include "level.inc"
.include "waypoints.inc"
.include "tove.inc"
.include "themes.inc"
.include "pieces.inc"
.include "stars.inc"
.include "critters.inc"

.import __BSS_RUN__, __BSS_SIZE__

.segment "CODE"

start:
    jsr clear_bss               ; RUN again without LOAD must start fresh too
    sec
    jsr SCREEN_MODE
    sta saved_mode
    lda #$80                    ; 320x240 256-color bitmap + 40x30 text
    clc
    jsr SCREEN_MODE
    ldx #0
@init:
    lda init_text,x
    beq @loaded
    jsr CHROUT
    inx
    bra @init
@loaded:
    jsr init_stars              ; after the charset switch, which reloads it
    jsr load_board
    bcs @failed
    jsr load_cells
    bcc @go
@failed:
    print_at SAFE_T, SAFE_L, s_load_failed
:   jsr GETIN
    cmp #0
    beq :-
    jmp quit
@go:
    jsr init_tove               ; all other state starts at zero (clear_bss)
    jsr init_critters
    jsr reset_level
    ; fall through

main_loop:
    jsr GETIN
    cmp #0
    beq @frame
    cmp #$c1                    ; fold shifted letters (caps lock) to unshifted
    bcc :+
    cmp #$db
    bcs :+
    and #$7f
:   jsr handle_key
    bcs quit
@frame:
    jsr RDTIM                   ; poll the pads once per jiffy (frame)
    cmp last_jiffy
    beq main_loop
    sta last_jiffy
    jsr poll_joy
    jsr tick_tove
    jsr tick_critters
    bra main_loop

quit:
    stz tove_z                  ; hide the sprites before handing back to BASIC
    jsr set_tove
    stz critter_z
    ldx #NCRITTERS-1
:   lda #0
    jsr set_critter
    dex
    bpl :-
    lda saved_mode
    clc
    jsr SCREEN_MODE
    lda #$8e                    ; back to upper/graphics charset
    jsr CHROUT
    lda #$93
    jmp CHROUT

; Act on key A. Carry set to quit.
handle_key:
    cmp #KEY_UP
    beq @up
    cmp #'w'
    bne :+
@up:
    lda sel
    cmp #RINGS-1
    beq @ignore
    inc sel
    bra @redraw
:   cmp #KEY_DOWN
    beq @down
    cmp #'s'
    bne :+
@down:
    lda sel
    beq @ignore
    dec sel
    bra @redraw
:   cmp #KEY_LEFT
    beq @left
    cmp #'a'
    bne :+
@left:
    lda #$ff
    bra @turn
:   cmp #KEY_RIGHT
    beq @right
    cmp #'d'
    bne :+
@right:
    lda #1
    bra @turn
:   cmp #'u'
    beq @undo
    cmp #KEY_DEL
    beq @undo
    cmp #'r'
    beq @reset
    cmp #KEY_RETURN
    beq @advance
    cmp #'n'
    beq @next
    cmp #'p'
    beq @prev
    cmp #'q'
    beq @quit
@ignore:
    clc
    rts
@quit:
    sec
    rts
@turn:
    ldx won
    bne @ignore
    jsr do_move
@redraw:
    jsr refresh
    clc
    rts
@undo:
    jsr undo_move
    bra @redraw
@advance:
    lda won
    beq @ignore
    lda arrived
    bne @next
    jsr arrive                  ; still walking: skip to the end
    clc
    rts
@next:
    lda level
    inc a
    cmp #NLEVELS
    bcs @ignore
    bra @goto
@prev:
    lda level
    beq @ignore
    dec a
@goto:
    sta level
@reset:
    jsr reset_level
    clc
    rts

;
; SNES controllers
;
; Pads 1-4 are merged and their new presses translated into the same key
; codes as the keyboard, so handle_key is the only place game input is
; handled. Pad 0 (the keyboard joystick) is skipped: GETIN already sees
; those keys. A held D-pad direction repeats.

poll_joy:
    stz joy0                    ; pressed buttons, 1 = down
    stz joy1
    lda #1
    sta joy_pad
@pad:
    lda joy_pad
.ifdef JOY_SCRIPT
    jsr script_joy
.else
    jsr JOYSTICK_GET
.endif
    cpy #0
    bne @absent
    eor #$ff
    ora joy0
    sta joy0
    txa
    eor #$ff
    and #$f0                    ; low nibble of byte 1 is always 1
    ora joy1
    sta joy1
@absent:
    inc joy_pad
    lda joy_pad
    cmp #5
    bne @pad

    lda joy0                    ; new presses = down now, not last frame
    eor joy0_prev
    and joy0
    sta joy_new0
    lda joy1
    eor joy1_prev
    and joy1
    sta joy_new1
    lda joy0
    sta joy0_prev
    lda joy1
    sta joy1_prev

    lda joy_new0                ; D-pad repeat
    and #JOY_DPAD
    beq @held
    lda #JOY_DELAY
    sta joy_timer
    bra @fire
@held:
    lda joy0
    and #JOY_DPAD
    beq @fire
    dec joy_timer
    bne @fire
    lda #JOY_RATE
    sta joy_timer
    lda joy0
    and #JOY_DPAD
    ora joy_new0
    sta joy_new0

@fire:
    ldx #0
:   asl joy_new0
    bcc @next0
    lda joy_keys0,x
    jsr joy_key
@next0:
    inx
    cpx #8
    bne :-
    ldx #0
:   asl joy_new1
    bcc @next1
    lda joy_keys1,x
    jsr joy_key
@next1:
    inx
    cpx #4
    bne :-
    rts

; Feed key A (if any) to handle_key. Preserves X.
joy_key:
    beq :+
    phx
    jsr handle_key
    plx
:   rts

.ifdef JOY_SCRIPT
; Test build: pad 1 replays build/joyscript.inc, one frame per call.
; Returns like JOYSTICK_GET.
script_joy:
    cmp #1
    bne @none
    lda joy_script_ptr+1
    bne :+
    lda #<joy_script            ; first call
    sta joy_script_ptr
    lda #>joy_script
    sta joy_script_ptr+1
:   lda joy_script_ptr
    sta ZP_PTR
    lda joy_script_ptr+1
    sta ZP_PTR+1
    ldy #1
    lda (ZP_PTR),y
    tax
    beq @none                   ; byte 1 = 0 marks the end: pad unplugged
    lda (ZP_PTR)
    pha
    clc
    lda joy_script_ptr
    adc #2
    sta joy_script_ptr
    bcc :+
    inc joy_script_ptr+1
:   pla
    ldy #0
    rts
@none:
    ldy #$ff
    rts
.endif

;
; The tove
;
; It idles at the entry gap. When the board is solved it walks the BFS path
; from flood through gates and cell centers (tables from tools/genrings.py)
; to the burrow, then vanishes into it.

; Copy the tove's frames and palette to VRAM and enable sprites
init_tove:
    stz VERA_CTRL
    lda #<TOVE_VRAM
    sta VERA_ADDR_L
    lda #>TOVE_VRAM
    sta VERA_ADDR_M
    lda #^TOVE_VRAM | VERA_INC_1
    sta VERA_ADDR_H
    lda #<tove_frames
    sta ZP_PTR
    lda #>tove_frames
    sta ZP_PTR+1
    ldx #TOVE_FRAMES / 2        ; 128 bytes per frame: 256 per pass
    ldy #0
:   lda (ZP_PTR),y
    sta VERA_DATA0
    iny
    bne :-
    inc ZP_PTR+1
    dex
    bne :-
    lda #<(VRAM_PALETTE + (TOVE_PAL * 16 + 1) * 2)
    sta VERA_ADDR_L
    lda #>(VRAM_PALETTE + (TOVE_PAL * 16 + 1) * 2)
    sta VERA_ADDR_M
    lda #^(VRAM_PALETTE + (TOVE_PAL * 16 + 1) * 2) | VERA_INC_1
    sta VERA_ADDR_H
    ldx #0
:   lda tove_pal,x
    sta VERA_DATA0
    inx
    cpx #tove_frames - tove_pal
    bne :-
    lda VERA_DC_VIDEO
    ora #$40                    ; sprites on
    sta VERA_DC_VIDEO
    rts

; Stand the tove at the entry gap
tove_idle:
    lda #ENTRY_X - 8
    sta tove_x
    lda #ENTRY_Y - 8
    sta tove_y
    stz tove_flip
    lda #TOVE_Z
    sta tove_z
    jmp set_tove

; Write the tove's sprite attributes from tove_x/y/frame/flip/z
set_tove:
    stz VERA_CTRL
    lda #<(VRAM_SPRITES + TOVE_SPRITE * 8)
    sta VERA_ADDR_L
    lda #>(VRAM_SPRITES + TOVE_SPRITE * 8)
    sta VERA_ADDR_M
    lda #^(VRAM_SPRITES + TOVE_SPRITE * 8) | VERA_INC_1
    sta VERA_ADDR_H
    lda tove_frame              ; 128-byte frames = 4 address units of 32
    asl a
    asl a
    clc
    adc #<(TOVE_VRAM >> 5)
    sta VERA_DATA0
    lda #>(TOVE_VRAM >> 5)      ; address bits 16:13, mode 0 = 4bpp
    sta VERA_DATA0
    lda tove_x
    sta VERA_DATA0
    stz VERA_DATA0
    lda tove_y
    sta VERA_DATA0
    stz VERA_DATA0
    lda tove_z
    ora tove_flip
    sta VERA_DATA0
    lda #%01010000 | TOVE_PAL   ; 16x16
    sta VERA_DATA0
    rts

; Once per frame: move and animate the tove
tick_tove:
    inc anim
    lda walking
    beq @idle
    clc
    lda posx
    adc stepx
    sta posx
    lda posx+1
    adc stepx+1
    sta posx+1
    clc
    lda posy
    adc stepy
    sta posy
    lda posy+1
    adc stepy+1
    sta posy+1
    dec seg_count
    bne :+
    jsr next_segment
    lda walking
    beq @done                   ; arrived
:   lda anim                    ; walk cycle: frames 0-3, 4 jiffies each
    lsr a
    lsr a
    and #3
    sta tove_frame
    lda posx+1
    sec
    sbc #8
    sta tove_x
    lda posy+1
    sec
    sbc #8
    sta tove_y
    jmp set_tove
@idle:
    lda arrived
    bne @done
    lda anim                    ; idle: tail turns every 16 jiffies (frames 0, 2)
    and #$10
    lsr a
    lsr a
    lsr a
    sta tove_frame
    jmp set_tove
@done:
    rts

; Build the waypoint list for the path ending at goal and start walking
start_walk:
    ldx goal                    ; path cells, goal back to the entry
    ldy #0
:   txa
    sta path,y
    iny
    cpx #ENTRY_K
    beq :+
    lda parent,x
    tax
    bra :-
:   sty path_n
    stz wp_n
    lda #ENTRY_X
    ldy #ENTRY_Y
    jsr add_wp
    ldy path_n
    dey                         ; the entry cell
    ldx path,y
    phy
    jsr add_center
    ply
@cell:
    dey
    bmi @last
    stx prev_k
    ldx path,y
    phy
    jsr add_gate
    jsr add_center
    ply
    bra @cell
@last:
    ldx goal                    ; through the burrow gate, into the burrow
    lda wp_rx,x
    ldy wp_ry,x
    jsr add_wp
    lda #BURROW_X
    ldy #BURROW_Y
    jsr add_wp
    lda #1
    sta walking
    stz arrived
    stz wp_i
    jmp start_segment

; Append waypoint (A, Y). Preserves X.
add_wp:
    phx
    ldx wp_n
    sta wp_x,x
    tya
    sta wp_y,x
    inc wp_n
    plx
    rts

add_center:
    lda wp_cx,x
    ldy wp_cy,x
    jmp add_wp

; Append the gate between cells prev_k and X. Preserves X.
add_gate:
    txa
    sec
    sbc prev_k
    cmp #CELLS
    beq @radial                 ; X is the outer cell: its inner gate
    cmp #<-CELLS
    beq @radial_prev
    cmp #1
    beq @arc_prev               ; X is clockwise of prev_k: prev_k's arc gate
    cmp #<-(CELLS-1)
    beq @arc_prev
    lda wp_ax,x                 ; X is counter-clockwise: X's arc gate
    ldy wp_ay,x
    jmp add_wp
@radial:
    lda wp_rx,x
    ldy wp_ry,x
    jmp add_wp
@radial_prev:
    phx
    ldx prev_k
    lda wp_rx,x
    ldy wp_ry,x
    bra @prev
@arc_prev:
    phx
    ldx prev_k
    lda wp_ax,x
    ldy wp_ay,x
@prev:
    jsr add_wp
    plx
    rts

; Advance to the next waypoint segment, or arrive after the last one
next_segment:
    inc wp_i
    ; fall through

; Start walking from waypoint wp_i to wp_i + 1
start_segment:
    ldx wp_i
    inx
    cpx wp_n
    bcc :+
    jmp arrive
:   lda wp_x-1,x
    sta posx+1
    stz posx
    lda wp_y-1,x
    sta posy+1
    stz posy
    lda wp_x,x
    sec
    sbc wp_x-1,x
    beq :+                      ; straight up/down: keep facing
    pha
    asl a                       ; sign to carry: moving left = flip
    lda #0
    rol a
    sta tove_flip
    pla
:   jsr make_step
    sta stepx
    sty stepx+1
    ldx wp_i
    lda wp_y+1,x
    sec
    sbc wp_y,x
    jsr make_step
    sta stepy
    sty stepy+1
    lda #WALK_STEPS
    sta seg_count
    rts

; A = signed pixel distance -> A/Y = 8.8 step per frame (distance * 256 / 8)
make_step:
    ldy #0
    cmp #$80
    bcc :+
    dey
:   sty step_hi
    ldy #5
:   asl a
    rol step_hi
    dey
    bne :-
    ldy step_hi
    rts

; The tove is home: hide it, light the burrow, show the message
arrive:
    stz walking
    lda #1
    sta arrived
    jsr rate
    sta stars
    ldx level
    cmp best,x
    bcc :+
    sta best,x
:    stz tove_z
    jsr set_tove
    jsr update_palette
    jmp draw_status

;
; The critters
;
; Borogoves and mome raths wander the lawns either side of the board. Each
; walks to a random waypoint in its band (tables from tools/genrings.py),
; pauses there to peck or sniff, then picks another. When the wabe is clear
; (the tove is home) they turn to the board and celebrate.

; Copy the critters' frames and palette to VRAM and place them
init_critters:
    stz VERA_CTRL
    lda #<CRITTER_VRAM
    sta VERA_ADDR_L
    lda #>CRITTER_VRAM
    sta VERA_ADDR_M
    lda #^CRITTER_VRAM | VERA_INC_1
    sta VERA_ADDR_H
    lda #<critters_frames
    sta ZP_PTR
    lda #>critters_frames
    sta ZP_PTR+1
    ldx #CRITTERS_FRAMES / 2    ; 128 bytes per frame: 256 per pass
    ldy #0
:   lda (ZP_PTR),y
    sta VERA_DATA0
    iny
    bne :-
    inc ZP_PTR+1
    dex
    bne :-
    lda #<(VRAM_PALETTE + (CRITTER_PAL * 16 + 1) * 2)
    sta VERA_ADDR_L
    lda #>(VRAM_PALETTE + (CRITTER_PAL * 16 + 1) * 2)
    sta VERA_ADDR_M
    lda #^(VRAM_PALETTE + (CRITTER_PAL * 16 + 1) * 2) | VERA_INC_1
    sta VERA_ADDR_H
    ldx #0
:   lda critters_pal,x
    sta VERA_DATA0
    inx
    cpx #critters_frames - critters_pal
    bne :-
    jsr RDTIM                   ; seed the wandering (never zero)
    ora #1
    sta seed
    lda #TOVE_Z
    sta critter_z
    ldx #NCRITTERS-1
:   lda cr_start,x              ; start paused at a waypoint
    jsr waypoint
    lda cr_x,x
    sta cr_tx,x
    lda cr_y,x
    sta cr_ty,x
    lda cr_start,x
    asl a
    asl a
    asl a
    sta cr_timer,x              ; staggered
    stz cr_walk,x
    dex
    bpl :-
    rts

; Once per frame: move, animate and draw every critter
tick_critters:
    ldx #NCRITTERS-1
@each:
    lda arrived
    beq @live
    lda cr_band,x               ; cheer, facing the board
    sta cr_flip,x
    lda anim
    and #$10
    beq @pose
    lda #POSE_CHEER
    bra @pose
@live:
    lda cr_walk,x
    beq @pause
    lda anim
    and cr_pace,x
    bne @walk_pose
    lda cr_x,x                  ; a step toward the waypoint
    cmp cr_tx,x
    beq @y
    bcc @right
    dec cr_x,x
    lda #1
    sta cr_flip,x
    bra @y
@right:
    inc cr_x,x
    stz cr_flip,x
@y:
    lda cr_y,x
    cmp cr_ty,x
    beq @arrived
    bcc @down
    dec cr_y,x
    bra @walk_pose
@down:
    inc cr_y,x
    bra @walk_pose
@arrived:
    lda cr_x,x
    cmp cr_tx,x
    bne @walk_pose
    stz cr_walk,x               ; there: pause for 40-167 frames
    jsr random
    and #$7f
    clc
    adc #40
    sta cr_timer,x
@walk_pose:
    lda anim                    ; walk cycle: 8 jiffies a step
    lsr a
    lsr a
    lsr a
    and #1
    bra @pose
@pause:
    dec cr_timer,x
    bne @idle
    jsr random                  ; off to another waypoint
    and #CRITTER_TARGETS-1
    jsr target
    lda #1
    sta cr_walk,x
    lda #POSE_WALK
    bra @pose
@idle:
    lda cr_timer,x              ; peck or sniff now and then
    and #$20
    beq @pose
    lda #POSE_IDLE
@pose:
    clc
    adc cr_kind,x
    jsr set_critter
    dex
    bmi :+
    jmp @each
:   rts

; Put critter X at waypoint A of its band
waypoint:
    jsr band_target
    lda band_tx,y
    sta cr_x,x
    lda band_ty,y
    sta cr_y,x
    rts

; Head critter X for waypoint A of its band
target:
    jsr band_target
    lda band_tx,y
    sta cr_tx,x
    lda band_ty,y
    sta cr_ty,x
    rts

; Y = index of waypoint A in critter X's band
band_target:
    sta tmp_n
    lda cr_band,x
.repeat 4
    asl a
.endrepeat
    ora tmp_n
    tay
    rts

.assert CRITTER_TARGETS = 16, error, "band_target assumes 16 waypoints"

; Write critter X's sprite attributes, showing frame A. Preserves X.
set_critter:
    asl a                       ; 128-byte frames = 4 address units of 32
    asl a
    clc
    adc #<(CRITTER_VRAM >> 5)
    pha
    stz VERA_CTRL
    txa
    asl a
    asl a
    asl a
    adc #<(VRAM_SPRITES + CRITTER_SPRITE * 8)
    sta VERA_ADDR_L
    lda #>(VRAM_SPRITES + CRITTER_SPRITE * 8)
    sta VERA_ADDR_M
    lda #^(VRAM_SPRITES + CRITTER_SPRITE * 8) | VERA_INC_1
    sta VERA_ADDR_H
    pla
    sta VERA_DATA0
    lda #>(CRITTER_VRAM >> 5)   ; address bits 16:13, mode 0 = 4bpp
    sta VERA_DATA0
    lda cr_band,x               ; the band's screen x, plus the critter's
    asl a
    tay
    lda cr_x,x
    clc
    adc band_x,y
    sta VERA_DATA0
    lda band_x+1,y
    adc #0
    sta VERA_DATA0
    lda cr_y,x
    sta VERA_DATA0
    stz VERA_DATA0
    lda critter_z
    ora cr_flip,x
    sta VERA_DATA0
    lda #%01010000 | CRITTER_PAL ; 16x16
    sta VERA_DATA0
    rts

.assert <(CRITTER_VRAM >> 5) + (CRITTERS_FRAMES - 1) * 4 < 256, error, "critter frames cross a page"
.assert <(VRAM_SPRITES + (CRITTER_SPRITE + NCRITTERS) * 8) > <(VRAM_SPRITES + CRITTER_SPRITE * 8), error, "critter sprites cross a page"

; A = a pseudo-random byte (16-bit Galois LFSR). Preserves X.
random:
    ldy #8
    lda seed
:   asl a
    rol seed+1
    bcc :+
    eor #$39
:   dey
    bne :--
    sta seed
    rts

; Load the level theme's garden colors into the palette rows from ROW_GARDEN
load_garden:
    ldx lvl+LV_THEME
    lda garden_lo,x
    sta ZP_PTR
    lda garden_hi,x
    sta ZP_PTR+1
    stz VERA_CTRL
    lda #<(VRAM_PALETTE + ROW_GARDEN * PALETTE_ROW)
    sta VERA_ADDR_L
    lda #>(VRAM_PALETTE + ROW_GARDEN * PALETTE_ROW)
    sta VERA_ADDR_M
    lda #^(VRAM_PALETTE + ROW_GARDEN * PALETTE_ROW) | VERA_INC_1
    sta VERA_ADDR_H
    ldy #0
:   lda (ZP_PTR),y
    sta VERA_DATA0
    iny
    cpy #GARDEN_SIZE
    bne :-
    rts

; A = stars (1-3) earned by solving the level in `moves`
rate:
    lda lvl+LV_PAR
    cmp moves
    bcs @three
    lsr a
    clc
    adc lvl+LV_PAR
    bcs @two                    ; limit is past 255
    cmp moves
    bcs @two
    lda #1
    rts
@two:
    lda #2
    rts
@three:
    lda #3
    rts

; Zero every variable in BSS. Nothing here may rely on the state a previous
; run (or power-on) left in RAM.
clear_bss:
    lda #<__BSS_RUN__
    sta ZP_PTR
    lda #>__BSS_RUN__
    sta ZP_PTR+1
    ldx #>__BSS_SIZE__          ; whole pages
    ldy #0
    tya
    cpx #0
    beq @tail
:   sta (ZP_PTR),y
    iny
    bne :-
    inc ZP_PTR+1
    dex
    bne :-
@tail:
    ldy #<__BSS_SIZE__          ; then the rest
    beq @done
:   dey
    sta (ZP_PTR),y
    bne :-
@done:
    rts

; Load the cell pieces into high RAM from bank CELLS_BANK. Carry set on error.
load_cells:
    lda #1
    ldx #8
    ldy #2                      ; headerless
    jsr SETLFS
    lda #cells_name_end - cells_name
    ldx #<cells_name
    ldy #>cells_name
    jsr SETNAM
    lda RAM_BANK
    pha
    lda #CELLS_BANK             ; LOAD carries on into the following banks
    sta RAM_BANK
    lda #0
    ldx #<$a000
    ldy #>$a000
    jsr LOAD
    pla
    sta RAM_BANK
    rts

; Load the board bitmap into VRAM $00000. Carry set on error.
load_board:
    lda #1
    ldx #8
    ldy #2                      ; headerless
    jsr SETLFS
    lda #board_name_end - board_name
    ldx #<board_name
    ldy #>board_name
    jsr SETNAM
    lda #2                      ; VRAM bank 0
    ldx #0
    ldy #0
    jmp LOAD

; Copy the current level's record into lvl and start it
reset_level:
    ldx level
    lda level_lo,x
    sta ZP_PTR
    lda level_hi,x
    sta ZP_PTR+1
    ldy #LEVEL_SIZE-1
:   lda (ZP_PTR),y
    sta lvl,y
    dey
    bpl :-
    ldx #RINGS-1
:   lda lvl+LV_START,x
    sta off,x
    dex
    bpl :-
    stz moves
    stz hist_n
    lda #RINGS-1
    sta sel
    ldx lvl+LV_THEME
    lda theme_lo,x
    sta ZP_THEME
    lda theme_hi,x
    sta ZP_THEME+1
    jsr load_garden
    lda #$ff                    ; nothing drawn yet: draw every cell
    ldx #NCELLS-1
:   sta drawn,x
    dex
    bpl :-
    jsr draw_hud
    ; fall through

refresh:
    jsr compute_scr
    jsr flood
    lda won
    bne :+
    stz walking                 ; not (or no longer) solved: tove waits at the entry
    stz arrived
    jsr tove_idle
    bra @draw
:   lda walking
    ora arrived
    bne @draw
    jsr start_walk              ; just solved: walk home
@draw:
    jsr update_palette
    jsr draw_cells
    jmp draw_status

; Rotate ring X by A (+1 clockwise, -1 counter-clockwise)
rotate:
    clc
    adc off,x
    bpl :+
    lda #CELLS-1
:   cmp #CELLS
    bne :+
    lda #0
:   sta off,x
    rts

; Turn the selected ring (and its gimbal followers) by A, recording the move
do_move:
    sta move_dir
    jsr turn_sel
    lda move_dir
    and #$80                    ; history: ring | $80 if counter-clockwise
    ora sel
    ldy hist_n
    cpy #$ff
    beq :+
    sta hist,y
    inc hist_n
:   lda moves
    cmp #$ff
    beq :+
    inc moves
:   rts

undo_move:
    ldy hist_n
    beq @done
    dey
    sty hist_n
    lda hist,y
    and #RINGS-1
    tax
    stx sel
    lda hist,y
    bmi :+
    lda #$ff
    bra :++
:   lda #1
:   sta move_dir
    jsr turn_sel
    lda moves
    beq @done
    dec moves
@done:
    rts

; Turn ring sel by move_dir, along with every ring its gimbals drag.
; Must match Level.turn in tools/level.py.
turn_sel:
    ldx sel
    lda lvl+LV_SAME,x
    sta tmp_same
    lda lvl+LV_OPP,x
    sta tmp_opp
    ldx #0
@ring:
    lsr tmp_same
    bcc :+
    lda move_dir
    jsr rotate
:   lsr tmp_opp
    bcc :+
    lda move_dir
    eor #$ff
    inc a
    jsr rotate
:   inx
    cpx #RINGS
    bne @ring
    rts

; scr[r*12+p] = cell shown at screen position p of ring r
compute_scr:
    ldx #0
    ldy #0
@ring:
    stx tmp_r
    lda #CELLS                  ; first cell shown = (-off) mod 12
    sec
    sbc off,x
    cmp #CELLS
    bne :+
    lda #0
:   sta tmp_i
    lda ring_base,x
    sta tmp_b
    lda #CELLS
    sta tmp_n
@cell:
    lda tmp_b
    clc
    adc tmp_i
    tax
    lda lvl+LV_CELLS,x
    sta scr,y
    iny
    inc tmp_i
    lda tmp_i
    cmp #CELLS
    bne :+
    stz tmp_i
:   dec tmp_n
    bne @cell
    ldx tmp_r
    inx
    cpx #RINGS
    bne @ring
    rts

; Breadth-first search from the entry: mark every reachable screen cell in
; vis with its parent in parent, and set won/goal at the first ring 0 cell
; that opens into the burrow (so goal ends a shortest path). Must match
; Level.solved() in tools/level.py.
flood:
    ldx #NCELLS-1
:   stz vis,x
    dex
    bpl :-
    stz won
    lda scr+ENTRY_K
    and #OUT
    bne :+
    rts                         ; entry closed: nothing reachable
:   lda #1
    sta vis+ENTRY_K
    lda #ENTRY_K
    sta parent+ENTRY_K
    sta queue
    stz q_head
    lda #1
    sta q_tail
@next:
    ldy q_head
    cpy q_tail
    bne :+
    rts
:   lda queue,y
    inc q_head
    tax                         ; X = current cell
    cpx #CELLS                  ; ring 0 opening inward: the burrow
    bcs @cw
    lda scr,x
    and #IN
    beq @cw
    lda won
    bne @cw
    inc won
    stx goal
@cw:
    lda scr,x                   ; clockwise neighbor
    and #CW
    beq @ccw
    lda pos_of,x
    cmp #CELLS-1
    txa
    bcc :+
    sbc #CELLS                  ; carry set: wrap from position 11 to 0
:   inc a
    jsr enqueue
@ccw:
    lda pos_of,x                ; counter-clockwise neighbor, if it opens to us
    cmp #1
    txa
    bcs :+
    adc #CELLS                  ; carry clear: wrap from position 0 to 11
:   dec a
    tay
    lda scr,y
    and #CW
    beq @in
    tya
    jsr enqueue
@in:
    cpx #CELLS
    bcc @out
    lda scr,x
    and #IN
    beq @out
    lda scr-CELLS,x
    and #OUT
    beq @out
    txa
    sec
    sbc #CELLS
    jsr enqueue
@out:
    cpx #NCELLS-CELLS
    bcs @done
    lda scr,x
    and #OUT
    beq @done
    lda scr+CELLS,x
    and #IN
    beq @done
    txa
    clc
    adc #CELLS
    jsr enqueue
@done:
    jmp @next

; Queue cell A with parent X if it hasn't been seen. Preserves X.
enqueue:
    tay
    lda vis,y
    bne :+
    lda #1
    sta vis,y
    txa
    sta parent,y
    tya
    ldy q_tail
    sta queue,y
    inc q_tail
:   rts

; Write the board's palette rows from the level's theme: each ring's stone
; (selected, dragged by a gimbal, or plain), tunnel, lit tunnel and wall,
; then the fixed row's burrow (home once the tove is in) and entry.
update_palette:
    ldx sel
    lda lvl+LV_SAME,x
    sta tmp_same
    lda lvl+LV_OPP,x
    sta tmp_opp
    ldx #0
@ring:
    lda #TH_STONE
    lsr tmp_opp
    bcc :+
    lda #TH_COUNTER
:   lsr tmp_same
    bcc :+
    lda #TH_FOLLOW
:   sta ring_stone,x
    inx
    cpx #RINGS
    bne @ring
    ldx sel
    lda #TH_SEL
    sta ring_stone,x

    stz VERA_CTRL
    lda #<(VRAM_PALETTE + ROW_STONE * PALETTE_ROW)
    sta VERA_ADDR_L
    lda #>(VRAM_PALETTE + ROW_STONE * PALETTE_ROW)
    sta VERA_ADDR_M
    lda #^(VRAM_PALETTE + ROW_STONE * PALETTE_ROW) | VERA_INC_1
    sta VERA_ADDR_H
    ldx #0
:   lda ring_stone,x
    tay
    lda #PALETTE_ROW
    jsr put_theme
    inx
    cpx #RINGS
    bne :-
    ldy #TH_TUNNEL              ; rows 5-7 follow on
    lda #PALETTE_ROW
    jsr put_theme
    ldy #TH_LIT
    lda #PALETTE_ROW
    jsr put_theme
    ldy #TH_WALL
    lda #TH_BURROW - TH_WALL
    jsr put_theme

    lda #<(VRAM_PALETTE + ROW_FIXED * PALETTE_ROW)
    sta VERA_ADDR_L
    lda #>(VRAM_PALETTE + ROW_FIXED * PALETTE_ROW)
    sta VERA_ADDR_M
    ldy #TH_BURROW
    lda arrived
    beq :+
    ldy #TH_HOME
:   lda #TH_HOME - TH_BURROW
    jsr put_theme
    ldy #TH_ENTRY
    lda #TH_SIZE - TH_ENTRY
    jmp put_theme

.assert ENTRY_SLOT = BURROW_SLOT + BURROW_SLOTS, error, "fixed row layout"
.assert TH_HOME - TH_BURROW = BURROW_SLOTS * 2, error, "fixed row layout"

; Copy A bytes of the theme from offset Y to VERA_DATA0. Preserves X.
put_theme:
    sta tmp_n
:   lda (ZP_THEME),y
    sta VERA_DATA0
    iny
    dec tmp_n
    bne :-
    rts

; Redraw every screen cell whose contents or color class changed. A cell's
; key is its class row << 4 plus its openings (IN, OUT, CW, and CCW when its
; counter-clockwise neighbor opens clockwise into it).
draw_cells:
    lda RAM_BANK
    pha
    ldx #0
@cell:
    lda scr,x
    bmi @tunnel
    ldy ring_of,x               ; stone: its ring's row, no openings
    lda ring_class,y
    bra @key
@tunnel:
    and #IN | OUT | CW
    sta tmp_b
    ldy ccw_of,x
    lda scr,y
    and #CW
    beq :+
    lda #CCW
    tsb tmp_b
:   lda #ROW_TUNNEL << 4
    ldy vis,x
    beq :+
    lda #ROW_LIT << 4
:   ora tmp_b
@key:
    cmp drawn,x
    beq @next
    sta drawn,x
    jsr draw_cell
@next:
    inx
    cpx #NCELLS
    bne @cell
    pla
    sta RAM_BANK
    rts

; Draw screen cell X with key A: its base piece, its gear teeth where a
; gimbal links its ring across a gap, then a piece per opening. Preserves X.
draw_cell:
    sta tmp_b
    and #KEY_CLASS
    sta ZP_CLASS
    stx tmp_i
    txa                         ; piece index: kind * NCELLS + cell
    jsr draw_piece

    lda ZP_CLASS                ; teeth are the ring's, in its stone color
    pha
    ldy ring_of,x
    lda ring_class,y
    sta ZP_CLASS
    tya
    beq :+                      ; ring 0 has no gap inside it
    lda lvl+LV_TEETH-1,y        ; gimbal across the gap inside this ring
    beq :+
    txa
    jsr draw_teeth
:   ldy ring_of,x
    cpy #RINGS-1
    beq :+
    lda lvl+LV_TEETH,y          ; ... and across the gap outside it
    beq :+
    txa
    clc
    adc #NCELLS
    jsr draw_teeth
:   pla
    sta ZP_CLASS
@kind:
    lda tmp_i
    clc
    adc #NCELLS
    sta tmp_i
    lsr tmp_b                   ; IN, OUT, CW, CCW in kind order
    bcc :+
    jsr draw_piece
:   lda tmp_i
    cmp #NCELLS * 5 - NCELLS
    bcc @kind
    sec
    sbc #NCELLS * 4
    tax
    rts

; Copy teeth piece A (kind * NCELLS + cell, kinds tin, tout) like draw_piece
draw_teeth:
    tay
    lda teeth_bank,y
    sta RAM_BANK
    lda teeth_lo,y
    sta ZP_PTR
    lda teeth_hi,y
    sta ZP_PTR+1
    bra draw_spans

; Copy piece A to VRAM, ORing ZP_CLASS into each pixel. Preserves X.
draw_piece:
    tay
    lda piece_bank,y
    sta RAM_BANK
    lda piece_lo,y
    sta ZP_PTR
    lda piece_hi,y
    sta ZP_PTR+1
draw_spans:
@span:
    lda (ZP_PTR)                ; length; 0 ends the piece
    beq @done
    sta span_len
    ldy #1
    lda (ZP_PTR),y
    sta VERA_ADDR_L
    iny
    lda (ZP_PTR),y
    sta VERA_ADDR_M
    iny
    lda (ZP_PTR),y
    ora #VERA_INC_1
    sta VERA_ADDR_H
    lda ZP_PTR
    clc
    adc #4
    sta ZP_PTR
    bcc :+
    inc ZP_PTR+1
:   ldy #0
:   lda (ZP_PTR),y
    ora ZP_CLASS                ; no effect on the literal wall rows
    sta VERA_DATA0
    iny
    cpy span_len
    bne :-
    tya
    clc
    adc ZP_PTR
    sta ZP_PTR
    bcc @span
    inc ZP_PTR+1
    bra @span
@done:
    rts

draw_hud:
    lda #$93
    jsr CHROUT
    print_at SAFE_T, SAFE_L, s_title1
    print_at SAFE_T+1, SAFE_L, s_title2
    print_at SAFE_T, SAFE_R-8, s_moves
    print_at SAFE_T+1, SAFE_R-8, s_par
    lda lvl+LV_PAR
    jsr print_dec3
    print_at SAFE_T+3, SAFE_L, s_level
    lda level
    inc a
    jsr print_dec2
    print_at SAFE_T+4, SAFE_L, s_best
    print_at SAFE_B-3, SAFE_L, s_help1
    print_at SAFE_B-2, SAFE_L, s_help2
    print_at SAFE_B-1, SAFE_L, s_help3
    print_at SAFE_B, SAFE_L, s_help4
    print_at SAFE_B, SAFE_R-5, s_help5
    rts

draw_status:
    ldx #SAFE_T
    ldy #SAFE_R-2
    clc
    jsr PLOT
    lda moves
    jsr print_dec3
    ldx level                   ; best so far, small, under the level number
    lda best,x
    ldx #SAFE_T+5
    ldy #SAFE_L
    stz star_big
    jsr draw_stars
    lda arrived
    bne :+
    jmp @unsolved
:   print_at SAFE_T+2, SAFE_R-7, s_home1
    print_at SAFE_T+3, SAFE_R-7, s_home2
    lda stars                   ; this solve, big, under the message
    ldx #SAFE_T+4
    ldy #SAFE_R-5
    sta star_big
    jsr draw_stars
    lda level
    cmp #NLEVELS-1
    bcs @last
    print_at SAFE_B-2, SAFE_R-7, s_next1
    print_at SAFE_B-1, SAFE_R-7, s_next2
    rts
@last:
    print_at SAFE_B-2, SAFE_R-7, s_end1
    print_at SAFE_B-1, SAFE_R-7, s_end2
    rts
@unsolved:
    print_at SAFE_T+2, SAFE_R-7, s_blank
    print_at SAFE_T+3, SAFE_R-7, s_blank
    print_at SAFE_T+4, SAFE_R-7, s_blank
    print_at SAFE_T+5, SAFE_R-7, s_blank
    print_at SAFE_B-2, SAFE_R-7, s_blank
    print_at SAFE_B-1, SAFE_R-7, s_blank
    rts

; Draw three stars at row X, column Y, the first A of them lit: 2x2
; characters each if star_big is nonzero, else one character every other column
draw_stars:
    sta star_lit
    stx star_row
    sty star_col
    lda #3
    sta star_n
@star:
    ldx star_row
    ldy star_col
    clc
    jsr PLOT
    lda #CLR_DIM
    ldx star_lit
    beq :+
    dec star_lit
    lda #CLR_LIT
:   jsr CHROUT
    lda star_big
    bne @big
    lda #STAR_PETSCII+STAR_SMALL
    jsr CHROUT
    bra @next
@big:
    lda #STAR_PETSCII+STAR_BIG
    jsr CHROUT
    lda #STAR_PETSCII+STAR_BIG+1
    jsr CHROUT
    ldx star_row
    inx
    ldy star_col
    clc
    jsr PLOT
    lda #STAR_PETSCII+STAR_BIG+2
    jsr CHROUT
    lda #STAR_PETSCII+STAR_BIG+3
    jsr CHROUT
@next:
    inc star_col
    inc star_col
    dec star_n
    bne @star
    lda #CLR_TEXT
    jmp CHROUT

; Copy the star glyphs over unused graphics characters of layer 1's charset
init_stars:
    stz VERA_CTRL
    lda VERA_L1_TILEBASE        ; bits 7:2 = tile base address bits 16:11
    asl a
    and #$f8
    ora #>(STAR_SCREEN * 8)
    sta VERA_ADDR_M
    lda #<(STAR_SCREEN * 8)
    sta VERA_ADDR_L
    lda VERA_L1_TILEBASE
    rol a                       ; bit 7 -> address bit 16
    rol a
    and #1
    ora #VERA_INC_1
    sta VERA_ADDR_H
    ldx #0
:   lda star_chars,x
    sta VERA_DATA0
    inx
    cpx #STAR_CHARS * 8
    bne :-
    rts

; Print the zero-terminated string at (ZP_PTR)
print_str:
    ldy #0
:   lda (ZP_PTR),y
    beq :+
    jsr CHROUT
    iny
    bne :-
:   rts

; Print A as three decimal digits at the cursor
print_dec3:
    ldx #0
:   cmp #100
    bcc :+
    sbc #100
    inx
    bra :-
:   pha
    txa
    ora #'0'
    jsr CHROUT
    pla
    ; fall through

; Print A (0-99) as two decimal digits at the cursor
print_dec2:
    ldx #0
:   cmp #10
    bcc :+
    sbc #10
    inx
    bra :-
:   pha
    txa
    ora #'0'
    jsr CHROUT
    pla
    ora #'0'
    jmp CHROUT

.segment "RODATA"

; Key code for each pad button, in bit order from bit 7 down (0 = unused)
joy_keys0:      ; B, Y, Select, Start, Up, Down, Left, Right
    .byte KEY_DEL, 0, 'r', KEY_RETURN, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT
joy_keys1:      ; A, X, L, R
    .byte KEY_RETURN, 0, 0, 0

.ifdef JOY_SCRIPT
.include "joyscript.inc"
.endif

ring_base:
    .byte 0, CELLS, 2*CELLS, 3*CELLS

; Each critter: its kind, band (0 left, 1 right), frames per step - 1
; (a mask of anim) and starting waypoint
cr_kind:        .byte BOROGOVE, RATH, RATH, BOROGOVE
cr_band:        .byte 0, 0, 1, 1
cr_pace:        .byte 1, 3, 3, 1
cr_start:       .byte 3, 9, 5, 12

ring_of:
.repeat NCELLS, i
    .byte i / CELLS
.endrepeat

pos_of:
.repeat NCELLS, i
    .byte i .mod CELLS
.endrepeat

ccw_of:                         ; the counter-clockwise neighbor of each cell
.repeat NCELLS, i
    .byte i / CELLS * CELLS + (i + CELLS - 1) .mod CELLS
.endrepeat

ring_class:                     ; each ring's stone row << 4
.repeat RINGS, r
    .byte (ROW_STONE + r) << 4
.endrepeat

init_text:
    .byte $0e                   ; upper/lowercase charset
    .byte $90, $01, $05         ; black, swap (black background), white text
    .byte 0

board_name:
    .byte "rings.bin"
board_name_end:
cells_name:
    .byte "cells.bin"
cells_name_end:

s_title1:       .byte "Gyre &", 0
s_title2:       .byte "Gimble", 0
s_moves:        .byte "Moves", 0
s_par:          .byte "Par   ", 0
s_help1:        .byte "W/S ring", 0
s_help2:        .byte "A/D turn", 0
s_help3:        .byte "U undo", 0
s_help4:        .byte "R reset", 0
s_help5:        .byte "Q quit", 0
s_home1:        .byte "The tove", 0
s_home2:        .byte "is home!", 0
s_next1:        .byte "  Return", 0
s_next2:        .byte "for next", 0
s_end1:         .byte "The wabe", 0
s_end2:         .byte "is clear", 0
s_level:        .byte "Level ", 0
s_best:         .byte "Best", 0
s_blank:        .byte "        ", 0
s_load_failed:  .byte "Can't load RINGS.BIN or CELLS.BIN", 0

.segment "BSS"

saved_mode:     .res 1
seed:           .res 2
critter_z:      .res 1
cr_x:           .res NCRITTERS      ; sprite corner, x relative to the band
cr_y:           .res NCRITTERS
cr_tx:          .res NCRITTERS      ; waypoint
cr_ty:          .res NCRITTERS
cr_walk:        .res NCRITTERS      ; walking (else paused)
cr_timer:       .res NCRITTERS
cr_flip:        .res NCRITTERS
parent:         .res NCELLS
queue:          .res NCELLS
q_head:         .res 1
q_tail:         .res 1
goal:           .res 1
path:           .res NCELLS     ; goal first, entry last
path_n:         .res 1
prev_k:         .res 1
wp_x:           .res 2 * NCELLS + 4
wp_y:           .res 2 * NCELLS + 4
wp_n:           .res 1
wp_i:           .res 1
walking:        .res 1
arrived:        .res 1
posx:           .res 2          ; 8.8 fixed point
posy:           .res 2
stepx:          .res 2
stepy:          .res 2
step_hi:        .res 1
seg_count:      .res 1
anim:           .res 1
tove_x:         .res 1          ; sprite top-left
tove_y:         .res 1
tove_frame:     .res 1
tove_flip:      .res 1
tove_z:         .res 1
last_jiffy:     .res 1
joy_pad:        .res 1
joy0:           .res 1
joy1:           .res 1
joy0_prev:      .res 1
joy1_prev:      .res 1
joy_new0:       .res 1
joy_new1:       .res 1
joy_timer:      .res 1
.ifdef JOY_SCRIPT
joy_script_ptr: .res 2
.endif
level:          .res 1
lvl:            .res LEVEL_SIZE     ; current level record (see tools/level.py)
move_dir:       .res 1
tmp_same:       .res 1
tmp_opp:        .res 1
ring_stone:     .res RINGS      ; TH_ offset of each ring's stone ramp
drawn:          .res NCELLS     ; key of each screen cell as drawn ($ff: redraw)
span_len:       .res 1
off:            .res RINGS
scr:            .res NCELLS
vis:            .res NCELLS
sel:            .res 1
moves:          .res 1
won:            .res 1
stars:          .res 1          ; rating of the last solve
best:           .res NLEVELS    ; best rating per level this session (0 = none)
star_big:       .res 1
star_lit:       .res 1
star_row:       .res 1
star_col:       .res 1
star_n:         .res 1
hist_n:         .res 1
hist:           .res 256
tmp_r:          .res 1
tmp_i:          .res 1
tmp_b:          .res 1
tmp_n:          .res 1
