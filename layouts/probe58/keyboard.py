"""
A PROBE, NOT A KEYBOARD: Compose58 under a second name, to run CI with two layouts once. Not to be merged.

Compose58: what the keyboard is called, whose key layout it is, which revs of the platform it is built in, and
the values that are its own. Plain constants and no imports: compose/params.py reads this file before it works
anything else out. The keys themselves are in layout.py.
"""
NAME = "Compose58"                       # on the boards, in the firmware and in the build's summary
CREDIT = "layout: Lily58 by kata0510"    # printed on the half boards (see NOTICE.md)
REVS = (2,)                              # new layouts are built in rev 2 only

# angles, per rev (degrees; COMPOSE_TENT and COMPOSE_TILT override them for one run)
TENT_DEG = {2: 12.0}                     # gable tent: inner edges raised
TILT_DEG = {2: 0.0}                     # typing tilt: back raised (negative = front raised)

# USB ids in the QMK keyboard definition
USB_VID = "0xFEED"
USB_PID = "0x4C58"
USB_PID_RGB = "0x4C59"                   # rev 2 with the RGB half boards: its own firmware, so its own id
