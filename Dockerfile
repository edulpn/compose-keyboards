# Compose build environment: the same stack the boards and checks were developed on.
#   Ubuntu 24.04, KiCad 7.0.11 (apt), Python 3.12 + requirements.txt, OpenJDK 21 + Freerouting 2.1.0,
#   ngspice, Node (renders).
#
#   docker build -t compose .
#   docker run --rm -it -v "$PWD":/work/compose-keyboards -w /work/compose-keyboards compose
#   (inside)  python3 -m compose --help
#
# Apple silicon: builds natively (arm64). If a Python wheel is missing for arm64, build and run with
# --platform linux/amd64 instead (slower, under emulation).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        kicad kicad-footprints kicad-symbols \
        python3 python3-pip python3-dev \
        openjdk-21-jre-headless ngspice \
        nodejs npm \
        fonts-dejavu-core git curl ca-certificates zip unzip \
    && rm -rf /var/lib/apt/lists/*

# Freerouting (the autorouter); compose/pcb/kicad.py reads FREEROUTING
ARG FREEROUTING_VERSION=2.1.0
RUN curl -fsSL -o /opt/freerouting.jar \
        "https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar"
ENV FREEROUTING=/opt/freerouting.jar

# Python packages (into the system Python, the one KiCad's pcbnew module is built for)
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt cairosvg pillow

# Render helpers (optional: only `render` / `gasket-render` / board previews need them)
COPY compose/render/web/package.json /opt/render-web/package.json
RUN cd /opt/render-web && npm install --no-audit --no-fund && npx playwright install --with-deps chromium
ENV NODE_PATH=/opt/render-web/node_modules

RUN python3 -c "import pcbnew, cadquery, trimesh, manifold3d, shapely; print('pcbnew', pcbnew.Version())"
