"""
Shared geometry: the half outline, key footprints, frames/transforms and the
interface planes between each half and the centre section.

Frames
  local : one half's plate frame (left half; the right half is its mirror).
          z = 0 is the plate underside.
  P     : top-view frame with splay and tent applied. The centre section
          (bridge, cover, controller) is designed here: back face at y = 0,
          front face at y = -BRIDGE_LEN, x = 0 on the centreline.
  world : P tilted by the typing tilt; the floor is z = 0.

Interface plane: the plane through a half's inner edge, perpendicular to its
plate (local x = anchor x). Bridge sides, plate edge, frame inner face and
cover sides all lie on it (with FIT_GAP where parts must not touch). Plates
and frames are installed along their plate normal, which lies in that plane;
the cover drops straight down into a slot that widens upward. So nothing ever
needs a clearance notch.
"""
import math
import numpy as np
import cadquery as cq
from shapely.geometry import box as sbox, Polygon
from shapely.geometry.polygon import orient
from shapely.affinity import rotate as srot, translate as strans
from shapely.ops import unary_union
from compose import params as PR
from compose import layout as layouts

LAYOUT = layouts.get()
P = PR.KEY_PITCH


# ---------------------------------------------------------------- 2D footprints
def key_poly(k, size=None, grow=0.0):
    """Key footprint: size None -> full key cell (pitch); else cap size."""
    shrink = 0.0 if size is None else (P - size)
    w = P * k.w - shrink + 2 * grow
    h = P * k.h - shrink + 2 * grow
    s = sbox(-w / 2, -h / 2, w / 2, h / 2)
    return strans(srot(s, k.rot, origin=(0, 0)), k.x, k.y)


def anchor():
    """Inner-back corner of the half: the splay/tent pivot."""
    c = LAYOUT.inner_col
    return (c * P + P / 2 + PR.PLATE_MARGIN, LAYOUT.inner_col_stagger * P + P / 2 + PR.PLATE_MARGIN)


def outline():
    """Half outline: key cells + margin, rounded, inner-back corner square."""
    u = unary_union([key_poly(k) for k in LAYOUT.keys])
    o = u.buffer(PR.PLATE_MARGIN, join_style="mitre", mitre_limit=2.0)
    o = o.buffer(PR.OUTLINE_CONCAVE_R, join_style="round").buffer(-PR.OUTLINE_CONCAVE_R, join_style="round")
    o = o.buffer(-PR.OUTLINE_CONVEX_R, join_style="round").buffer(PR.OUTLINE_CONVEX_R, join_style="round")
    ax, ay = anchor()
    r = PR.OUTLINE_CONVEX_R + 2.0
    o = o.union(sbox(ax - r, ay - r, ax, ay))     # square where it meets the bridge
    return orient(o.simplify(0.02), 1.0)


OUTLINE = outline()
ANCHOR = anchor()


def ring(poly):
    return list(poly.exterior.coords)[:-1]


def miter_offset(pts, d):
    """Inward offset of a CCW polygon keeping its vertex count (edges stay
    parallel, so a ruled loft between the two gives flat side faces)."""
    A = np.array(pts)
    n = len(A)
    out = []
    for i in range(n):
        a, b, c = A[i - 1], A[i], A[(i + 1) % n]
        e1, e2 = (b - a) / np.linalg.norm(b - a), (c - b) / np.linalg.norm(c - b)
        n1, n2 = np.array([-e1[1], e1[0]]), np.array([-e2[1], e2[0]])
        m = n1 + n2
        m /= np.linalg.norm(m)
        out.append(tuple(b + m * d / max(np.dot(m, n1), 0.3)))
    return out


# ---------------------------------------------------------------- solids from 2D
def prism(pts, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(z1 - z0).val()


def poly_prism(poly, z0, z1):
    """Prism of a shapely (Multi)Polygon, holes respected."""
    out = None
    for g in getattr(poly, "geoms", [poly]):
        if g.area < 0.5:
            continue
        g = g.simplify(0.02)
        s = prism(list(g.exterior.coords)[:-1], z0, z1)
        for hole in g.interiors:
            s = s.cut(prism(list(hole.coords)[:-1], z0 - 1, z1 + 1))
        out = s if out is None else out.fuse(s)
    return out


def cyl(x, y, r, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0).val()


def big_box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0)).val()


def union(shapes):
    shapes = [s for s in shapes if s is not None]
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out.clean()


def loft(pts0, z0, pts1, z1):
    return (cq.Workplane("XY").workplane(offset=z0).polyline(pts0).close()
            .workplane(offset=z1 - z0).polyline(pts1).close().loft(ruled=True).val())


# ---------------------------------------------------------------- transforms
def T(x=0, y=0, z=0):
    m = np.eye(4); m[:3, 3] = [x, y, z]; return m


def _R(axis, d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    m[i, i], m[i, j], m[j, i], m[j, j] = c, -s, s, c
    return m


def apply(M, p):
    return (M @ np.array([p[0], p[1], p[2], 1.0]))[:3]


S_MIRROR = np.diag([-1.0, 1, 1, 1])


def _ops_local_to_P(z0):
    ax, ay = ANCHOR
    return [("t", -ax, -ay, 0), ("r", "y", -PR.TENT_DEG), ("r", "z", -PR.SPLAY_DEG), ("t", -PR.GAP_TOP / 2, 0, z0)]


def _ops_matrix(ops):
    M = np.eye(4)
    for op in ops:
        M = (T(*op[1:]) if op[0] == "t" else _R(op[1], op[2])) @ M
    return M


def solve_z0():
    """Lowest inner-edge height that keeps WIRE_DEPTH under the whole plate."""
    M = _R("x", PR.TILT_DEG) @ _ops_matrix(_ops_local_to_P(0.0))
    lo = 0.0
    for x, y in OUTLINE.exterior.coords:
        lo = max(lo, PR.FLOOR_T - apply(M, (x, y, -PR.WIRE_DEPTH))[2])
    return math.ceil(lo * 2) / 2


Z0 = solve_z0()                       # plate underside height at the inner edge (P frame)
Z_DECK = Z0 + PR.PLATE_T              # plate top at the inner edge = bridge top = cover underside
OPS_LP = _ops_local_to_P(Z0)
OPS_PW = [("r", "x", PR.TILT_DEG)]
M_LP = _ops_matrix(OPS_LP)
M_PW = _ops_matrix(OPS_PW)
M_LW = M_PW @ M_LP
M_RW = S_MIRROR @ M_LW @ S_MIRROR


def _run(shape, ops):
    for op in ops:
        if op[0] == "t":
            shape = shape.translate(cq.Vector(*op[1:]))
        else:
            ax = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[op[1]]
            shape = shape.rotate(cq.Vector(0, 0, 0), cq.Vector(*ax), op[2])
    return shape


def _inverse(ops):
    out = []
    for op in reversed(ops):
        out.append(("t", -op[1], -op[2], -op[3]) if op[0] == "t" else ("r", op[1], -op[2]))
    return out


def L2W(shape):  return _run(shape, OPS_LP + OPS_PW)          # left local -> world
def R2W(shape):  return L2W(shape).mirror("YZ")              # (mirror image) right half
def P2W(shape):  return _run(shape, OPS_PW)                  # bridge frame -> world
def P2L(shape):  return _run(shape, _inverse(OPS_LP))        # bridge frame -> left local
def W2L(shape):  return _run(shape, _inverse(OPS_LP + OPS_PW))


def plate_normal_world(side=-1):
    """Install direction of a half's plate/frame (unit vector, world)."""
    n = (M_LW[:3, :3] @ np.array([0, 0, 1.0]))
    if side == 1:
        n = n * np.array([-1, 1, 1])
    return n / np.linalg.norm(n)


def up_P_world():
    return M_PW[:3, :3] @ np.array([0, 0, 1.0])


# ---------------------------------------------------------------- interface planes
def half_space_P(side, gap=0.0, extent=600.0):
    """Solid on the HALF side of a half's interface plane, offset toward the
    bridge by `gap` (negative = into the half). In the P frame."""
    ax, ay = ANCHOR
    hs = big_box(ax + gap - 2 * extent, ax + gap, ay - extent, ay + extent, -extent, extent)
    hs = _run(hs, OPS_LP)
    return hs.mirror("YZ") if side == 1 else hs


def interface_x(y, z, side=-1):
    """x of the left (side -1) interface plane at P-frame (y, z)."""
    R = M_LP[:3, :3]
    n = R @ np.array([1.0, 0, 0])
    p0 = apply(M_LP, (ANCHOR[0], ANCHOR[1], 0.0))
    x = p0[0] - (n[1] * (y - p0[1]) + n[2] * (z - p0[2])) / n[0]
    return x if side == -1 else -x


def bridge_stretch_local():
    """Local y range of the inner edge that faces the bridge (back, front)."""
    ay = ANCHOR[1]
    return ay, ay - PR.BRIDGE_LEN / math.cos(math.radians(PR.SPLAY_DEG))


def bridge_zone_P(z0=-200.0, z1=200.0, reach=None):
    """P-frame block between the bridge's back and front faces, reaching
    `reach` mm into each half past its interface plane (default: whole
    bridge + a few mm). Used to stop the trim lip/reveal at the bridge faces."""
    reach = PR.TRIM_LIP_T + 8.0 if reach is None else reach      # the back edge meets the bridge face at a shallow angle
    yb, yf = 0.0, -PR.BRIDGE_LEN
    w = lambda y: abs(interface_x(y, Z0)) + reach
    pts = [(-w(yb), yb), (w(yb), yb), (w(yf), yf), (-w(yf), yf)]
    return prism(pts, z0, z1)


def bridge_zone_local(grow=0.0, reach=None, z0=-50.0, z1=50.0):
    """The bridge zone as seen by one half, as a prism along the LOCAL z axis
    (= the plate's install direction). Its back/front faces pass through the
    lines where the bridge's back/front faces meet the plate underside, so the
    trim lip's ends and the reveal's ends both contain the install direction
    and slide past each other. `grow` pushes both faces outward (in local y),
    used to stop the lip short of the reveal's ends."""
    reach = PR.TRIM_LIP_T + 8.0 if reach is None else reach      # the back edge meets the bridge face at a shallow angle
    ax = ANCHOR[0]
    R = M_LP[:3, :3]

    def y_local(x_l, y_P):
        # local point (x_l, y, 0) whose P-frame y equals y_P
        b = apply(M_LP, (x_l, 0.0, 0.0))[1]
        return (y_P - b) / R[1, 1]

    xa, xb = ax - reach, ax + 60.0                 # into the half .. across the bridge
    yb0, yb1 = y_local(xa, 0.0) + grow, y_local(xb, 0.0) + grow
    yf0, yf1 = y_local(xa, -PR.BRIDGE_LEN) - grow, y_local(xb, -PR.BRIDGE_LEN) - grow
    return prism([(xa, yf0), (xb, yf1), (xb, yb1), (xa, yb0)], z0, z1)


# ---------------------------------------------------------------- checks on the layout
def validate_layout():
    issues = []
    caps = [key_poly(k, PR.KEYCAP_SIZE) for k in LAYOUT.keys]
    for i in range(len(caps)):
        for j in range(i + 1, len(caps)):
            if caps[i].distance(caps[j]) < 0.5:
                issues.append(f"keycaps {LAYOUT.keys[i].label_l}/{LAYOUT.keys[j].label_l} closer than 0.5 mm")
    # inner edge must be straight along the bridge
    yb, yf = bridge_stretch_local()
    ax = ANCHOR[0]
    for t in np.linspace(0.02, 0.98, 40):
        y = yb + (yf - yb) * t
        seg = sbox(ax - 0.05, y - 0.05, ax + 0.05, y + 0.05)
        if not OUTLINE.exterior.intersects(seg):
            issues.append(f"inner edge not straight at local y={y:.1f} (bridge too long for this layout)")
            break
    for x, y in LAYOUT.screws:
        from shapely.geometry import Point
        p = Point(x, y)
        if not OUTLINE.contains(p) or OUTLINE.exterior.distance(p) < PR.SCREW_EDGE_INSET - 0.1:
            issues.append(f"screw at ({x:.1f},{y:.1f}) too close to the edge")
    return issues
