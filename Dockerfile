ARG MATLAB_RELEASE=r2025a
FROM mathworks/matlab:${MATLAB_RELEASE}

USER root
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# matlabengine version MUST match the MATLAB_RELEASE image above:
#   r2022b->9.13.* r2023a->9.14.* r2023b->9.15.*
#   r2024a->24.1.* r2024b->24.2.* r2025a->25.1.* r2025b->25.2.* r2026a->26.1.*
RUN pip3 install --no-cache-dir "matlabengine==25.1.*"

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
