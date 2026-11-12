"""
Pointer modules (rev 2): a pointing device on a printed carrier that meets the pointer mount standard
(compose/pointer/std.py), wired to the controller by its own cable (docs/pointer-modules.md). Devices live in
pointers/<name>/. The footprint is one of the standard's: "slot" (on the plate, in place of a half's 1.5u thumb key,
which is gone) or a bay such as "bay30" (on the case, in the thumb bay the layout declares; every key stays; the bay
comes with it, compose/case/bay.py). Configured like the angles, by environment variables:

    C58_POINTER=pim447:R             device : side (L or R) [: footprint, slot (default) or e.g. bay30]. Unset = none.
    C58_POINTER_PORT=J5              the controller connector an I2C device's cable plugs into: J5 (Qwiic) or J4.
"""
import os
from dataclasses import dataclass

from compose.pointer import std as S

PORTS = ("J5", "J4")


@dataclass(frozen=True)
class PointerConfig:
    device: str
    side: str
    mount: str = "slot"
    port: str = "J5"


def parse(spec, port=None):
    """'pim447:R' or 'pim447:L:bay30' -> PointerConfig; '' or None -> None. Raises ValueError when malformed (an
    unknown device is the checks' business: compose/pointer/device.py)."""
    if not spec:
        return None
    parts = spec.split(":")
    if len(parts) not in (2, 3) or not all(parts):
        raise ValueError(f"C58_POINTER={spec!r}: expected device:side[:footprint], e.g. pim447:R or pim447:R:bay30")
    device, side = parts[:2]
    mount = parts[2] if len(parts) == 3 else "slot"
    if side not in ("L", "R"):
        raise ValueError(f"C58_POINTER={spec!r}: the side must be L or R")
    if mount not in S.FOOTPRINTS:
        raise ValueError(f"C58_POINTER={spec!r}: the footprint must be one of {', '.join(S.FOOTPRINTS)}")
    port = port or "J5"
    if port not in PORTS:
        raise ValueError(f"C58_POINTER_PORT={port!r}: must be one of {', '.join(PORTS)}")
    return PointerConfig(device, side, mount, port)


def active():
    """The configured device, or None."""
    return parse(os.environ.get("C58_POINTER", ""), os.environ.get("C58_POINTER_PORT"))
