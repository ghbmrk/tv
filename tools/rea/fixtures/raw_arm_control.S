.syntax unified
.arm
.text
.global raw_probe
raw_probe:
 cmp r0, #4
 blo valid
 mvn r0, #0
 bx lr
valid:
 add r0, r0, r0, lsl #1
 add r0, r0, #7
 bx lr
