FROM python:3.12-slim

WORKDIR /app

# Install third-party deps first for layer caching
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir \
    "fastmcp>=2.0.0,<3.0.0" "pydantic>=2.0.0" "pyyaml>=6.0" \
    "Pillow>=9.0.0" "aiosqlite>=0.19.0" "plotly>=5.9.0" \
    "psutil>=5.9.0" "uvicorn>=0.20.0"

# Copy source and install the package itself
COPY src/ ./src/
COPY examples/ ./examples/
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8765 8766

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

ENTRYPOINT ["matlab-mcp"]
CMD ["--transport", "sse"]
