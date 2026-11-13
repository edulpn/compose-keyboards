"""
Pimoroni Trackball Breakout (PIM447): a 3-5 V I2C trackball with an RGBW LED, address 0x0A. Device frame: origin at
the ball centre on the board's top face, +y toward the edge away from the header tab (compose/pointer/device.py).
"""
from compose.pointer.device import Device

DEVICE = Device(
    name="pim447",
    title="Pimoroni Trackball Breakout (PIM447)",
    footprints=("slot", "bay30"),
    rects=((-12.5, -8.1, 12.5, 8.0), (-7.5, -14.0, 7.5, -8.1)),
    holes=((-9.8, 5.45), (9.8, 5.45), (-9.8, -5.45), (9.8, -5.45)),
    hole_d=2.7,
    pads=(("VCC", -5.08, -12.3), ("SDA", -2.54, -12.3), ("SCL", 0.0, -12.3), ("INT", 2.54, -12.3), ("GND", 5.08, -12.3)),
    pcb_t=1.6,
    top_rect=(-7.0, -7.0, 7.0, 7.0),
    top_h=7.9,
    back_rect=(-7.0, -7.0, 7.0, 7.0),
    back_h=1.5,
    bus="i2c",
    address=0x0A,
    driver="pimoroni_trackball",
    qmk_defines=(("PIMORONI_TRACKBALL_ADDRESS", "0x0A"),),
    measured=False,
    sources=(("outline 25 x 22, ball 8.0 from the top edge, holes 19.6 x 10.9", "github.com/Cipulot/PimoPoint, mechanical drawing"),
             ("body/tab split 16.1 / 5.9, tab 15 wide, pad row 12.3 below the ball", "scaled off the same drawing"),
             ("hole diameter 2.7 (M2.5 clearance)", "assumed"),
             ("pad order VCC SDA SCL INT GND", "datasheet mirror (elecfans); read the silkscreen"),
             ("height 9.5 overall: 1.6 board + 7.9 above; parts under the board <= 1.5 within the housing area", "retailer listings; split assumed"),
             ("I2C 0x0A, 3-5 V", "Pimoroni listing, QMK driver")),
)
