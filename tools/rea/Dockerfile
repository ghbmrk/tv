# Offline analysis tools only; no vendor artifact is copied into this image.
FROM rust:1.85.1-slim-bookworm@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36 AS binwalk
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libfontconfig1-dev liblzma-dev libbz2-dev zlib1g-dev ca-certificates && rm -rf /var/lib/apt/lists/*
RUN cargo install binwalk --version 3.1.0 --locked --root /opt/binwalk

FROM node:24.11.0-bookworm-slim@sha256:76d0ed0ed93bed4f4376211e9d8fddac4d8b3fbdb54cc45955696001a3c91152
RUN apt-get update && apt-get install -y --no-install-recommends procps util-linux libfontconfig1 liblzma5 libbz2-1.0 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install --prefix /opt/rea --ignore-scripts --omit=optional rea-agents@6.5.0
COPY --from=binwalk /opt/binwalk/bin/binwalk /usr/local/bin/binwalk
ENV REA_BINWALK_COMMAND=/usr/local/bin/binwalk
ENTRYPOINT ["node", "/opt/rea/node_modules/rea-agents/scripts/rea.mjs"]
