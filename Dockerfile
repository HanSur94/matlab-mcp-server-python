ARG MATLAB_RELEASE=r2025a
FROM mathworks/matlab:${MATLAB_RELEASE}

USER root
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# matlabengine version MUST match the MATLAB_RELEASE image above. Map the
# release token to its matching matlabengine <major>.<minor> pin so that
# `--build-arg MATLAB_RELEASE=r2024b` installs the correct engine instead of
# a hardcoded one. Redeclare the ARG inside the build stage — an ARG declared
# before FROM is only in scope for the FROM line, not for later RUNs; a bare
# `ARG MATLAB_RELEASE` here inherits the pre-FROM default (r2025a) or the
# --build-arg override.
ARG MATLAB_RELEASE
RUN case "$MATLAB_RELEASE" in \
        r2022b) ENGINE_VER="9.13.*" ;; \
        r2023a) ENGINE_VER="9.14.*" ;; \
        r2023b) ENGINE_VER="9.15.*" ;; \
        r2024a) ENGINE_VER="24.1.*" ;; \
        r2024b) ENGINE_VER="24.2.*" ;; \
        r2025a) ENGINE_VER="25.1.*" ;; \
        r2025b) ENGINE_VER="25.2.*" ;; \
        r2026a) ENGINE_VER="26.1.*" ;; \
        *) echo "Unsupported MATLAB_RELEASE: $MATLAB_RELEASE" >&2; exit 1 ;; \
    esac && \
    pip3 install --no-cache-dir "matlabengine==${ENGINE_VER}"

# Install the project via pyproject — single source of truth for fastmcp/deps
# (no hardcoded fastmcp/plotly pins here).
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY examples/ ./examples/
RUN pip3 install --no-cache-dir ".[monitoring]"

USER matlab

EXPOSE 8765

# /health is served on the MAIN MCP app port (8765) for streamablehttp/sse
# transports via register_monitoring_routes — the stdio-only 8766 monitoring
# server does not run under streamablehttp, so the healthcheck must NOT
# target 8766.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

ENTRYPOINT ["matlab-mcp"]
CMD ["--transport", "streamablehttp"]
