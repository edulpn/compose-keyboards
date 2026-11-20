"""
Compose42: what the keyboard is called, whose key layout it is, and the values that are its own. Plain
constants and no imports: compose/params.py reads this file before it works anything else out. The keys
themselves are in layout.py.
"""
NAME = "Compose42"                       # on the boards, in the firmware and in the build's summary
CREDIT = "layout: Corne by foostan"      # printed on the half boards (see NOTICE.md)

# angles (degrees; COMPOSE_TENT and COMPOSE_TILT override them for one run)
TENT_DEG = 12.0                          # gable tent: inner edges raised
TILT_DEG = 0.0                           # typing tilt: back raised (negative = front raised)

# USB ids in the QMK keyboard definition
USB_VID = "0xFEED"
USB_PID = "0x4C42"
USB_PID_RGB = "0x4C43"                   # rev 2 with the RGB half boards: its own firmware, so its own id
