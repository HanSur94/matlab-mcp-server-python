# Plotly Visual Fidelity Conversion Layer — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert MATLAB figures to Plotly JSON with full visual fidelity — matching colors, fonts, line styles, markers, grids, legends, and subplot layouts.

**Architecture:** MATLAB-side property extractor (`mcp_extract_props.m`) dumps raw figure properties to JSON. Python-side style mapper (`plotly_style_mapper.py`) converts that JSON to Plotly figure dicts. The executor wires these together in `_build_result()`.

**Tech Stack:** Python 3.9+, MATLAB R2019b+, Plotly.js (client-side rendering), pytest

**Spec:** `docs/superpowers/specs/2026-03-13-plotly-visual-fidelity-design.md`

---

## Chunk 1: Foundation — Utilities, Loader Update, and Dependency

### Task 1: Add `plotly` dependency to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml:12-18`

- [ ] **Step 1: Add plotly to dependencies**

In `pyproject.toml`, add `"plotly>=5.9.0"` to the `dependencies` list:

```python
dependencies = [
    "fastmcp>=2.0.0,<3.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "aiosqlite>=0.19.0",
    "plotly>=5.9.0",
]
```

- [ ] **Step 2: Verify install**

Run: `pip install -e . 2>&1 | tail -5`
Expected: successful install with plotly

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add plotly>=5.9.0 dependency"
```

---

### Task 2: Update `plotly_convert.py` with schema_version validation

**Files:**
- Modify: `src/matlab_mcp/output/plotly_convert.py`
- Modify: `tests/test_output.py:481-510`

- [ ] **Step 1: Write the failing tests**

In `tests/test_output.py`, update the existing `TestLoadPlotlyJson` class. Replace the `test_load_valid_json` test and add new tests:

```python
class TestLoadPlotlyJson:
    def test_load_valid_json_with_schema_version(self, tmp_path):
        """load_plotly_json should parse a valid JSON file with schema_version 1."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        data = {"schema_version": 1, "layout_type": "single", "axes": []}
        json_file = tmp_path / "fig.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_plotly_json(str(json_file))

        assert result is not None
        assert result["schema_version"] == 1

    def test_load_missing_schema_version_returns_none(self, tmp_path):
        """load_plotly_json should return None when schema_version is absent."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        data = {"data": [{"type": "scatter"}], "layout": {}}
        json_file = tmp_path / "fig.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_plotly_json(str(json_file))
        assert result is None

    def test_load_future_schema_version_returns_none(self, tmp_path):
        """load_plotly_json should return None for unsupported schema_version."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        data = {"schema_version": 99, "layout_type": "single", "axes": []}
        json_file = tmp_path / "fig.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_plotly_json(str(json_file))
        assert result is None

    def test_load_missing_file_returns_none(self, tmp_path):
        """load_plotly_json should return None for a non-existent file."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        result = load_plotly_json(str(tmp_path / "missing.json"))
        assert result is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        """load_plotly_json should return None for invalid JSON."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")

        result = load_plotly_json(str(bad_file))
        assert result is None

    def test_load_empty_dict_returns_none(self, tmp_path):
        """load_plotly_json should return None for {} (no schema_version)."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}", encoding="utf-8")

        result = load_plotly_json(str(empty_file))
        assert result is None

    def test_load_non_dict_json_returns_none(self, tmp_path):
        """load_plotly_json should return None for a JSON list."""
        from matlab_mcp.output.plotly_convert import load_plotly_json

        list_file = tmp_path / "list.json"
        list_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        result = load_plotly_json(str(list_file))
        assert result is None
```

**Note:** This replacement replaces the ENTIRE existing `TestLoadPlotlyJson` class. Remove the old `test_load_valid_json`, `test_load_empty_dict` (which would now fail), and `test_load_non_dict_json_returns_none` tests.

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_output.py::TestLoadPlotlyJson -v`
Expected: `test_load_valid_json_with_schema_version` PASSES (existing loader accepts any dict), `test_load_missing_schema_version_returns_none` FAILS (currently returns the dict), `test_load_future_schema_version_returns_none` FAILS

- [ ] **Step 3: Implement schema_version validation**

Update `src/matlab_mcp/output/plotly_convert.py`:

```python
"""Figure property JSON loader for MATLAB MCP Server.

Provides ``load_plotly_json`` which reads a JSON file written by the
MATLAB helper ``mcp_extract_props.m``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSION = 1


def load_plotly_json(json_path: str) -> Optional[dict]:
    """Load a figure property JSON file produced by ``mcp_extract_props``.

    Parameters
    ----------
    json_path:
        Path to the JSON file to load.

    Returns
    -------
    Optional[dict]
        Parsed figure dict, or ``None`` if the file does not exist,
        cannot be parsed, or has an unsupported schema_version.
    """
    path = Path(json_path)
    if not path.exists():
        logger.debug("Figure JSON file not found: %s", json_path)
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            logger.warning("Figure JSON at %s is not a dict: %r", json_path, type(data))
            return None
        version = data.get("schema_version")
        if version is None:
            logger.warning("Figure JSON at %s missing schema_version", json_path)
            return None
        if version > SUPPORTED_SCHEMA_VERSION:
            logger.warning(
                "Figure JSON at %s has unsupported schema_version %s (max %s)",
                json_path, version, SUPPORTED_SCHEMA_VERSION,
            )
            return None
        return data
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse figure JSON from %s: %s", json_path, exc)
        return None
    except Exception as exc:
        logger.warning("Failed to load figure JSON from %s: %s", json_path, exc)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_output.py::TestLoadPlotlyJson -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_convert.py tests/test_output.py
git commit -m "feat: add schema_version validation to figure JSON loader"
```

---

### Task 3: Create utility functions — `rgb_to_css`, `resolve_color`, `map_font`

**Files:**
- Create: `src/matlab_mcp/output/plotly_style_mapper.py`
- Create: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plotly_style_mapper.py`:

```python
"""Tests for the MATLAB-to-Plotly style mapper."""
import math
import pytest


class TestRgbToCss:
    def test_matlab_blue(self):
        from matlab_mcp.output.plotly_style_mapper import rgb_to_css
        assert rgb_to_css([0, 0.447, 0.741]) == "rgb(0, 114, 189)"

    def test_black(self):
        from matlab_mcp.output.plotly_style_mapper import rgb_to_css
        assert rgb_to_css([0, 0, 0]) == "rgb(0, 0, 0)"

    def test_white(self):
        from matlab_mcp.output.plotly_style_mapper import rgb_to_css
        assert rgb_to_css([1, 1, 1]) == "rgb(255, 255, 255)"

    def test_rounding(self):
        from matlab_mcp.output.plotly_style_mapper import rgb_to_css
        assert rgb_to_css([0.5, 0.5, 0.5]) == "rgb(128, 128, 128)"


class TestResolveColor:
    def test_rgb_array(self):
        from matlab_mcp.output.plotly_style_mapper import resolve_color
        assert resolve_color([1, 0, 0], None) == "rgb(255, 0, 0)"

    def test_none_string(self):
        from matlab_mcp.output.plotly_style_mapper import resolve_color
        assert resolve_color("none", None) == "rgba(0,0,0,0)"

    def test_auto_returns_fallback(self):
        from matlab_mcp.output.plotly_style_mapper import resolve_color
        assert resolve_color("auto", "rgb(255, 0, 0)") == "rgb(255, 0, 0)"

    def test_auto_with_none_fallback(self):
        from matlab_mcp.output.plotly_style_mapper import resolve_color
        assert resolve_color("auto", None) is None


class TestMapFont:
    def test_simple_name(self):
        from matlab_mcp.output.plotly_style_mapper import map_font
        assert map_font("Helvetica") == "Helvetica, Arial, sans-serif"

    def test_name_with_spaces(self):
        from matlab_mcp.output.plotly_style_mapper import map_font
        assert map_font("Times New Roman") == '"Times New Roman", Arial, sans-serif'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plotly_style_mapper.py::TestRgbToCss -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the utility functions**

Create `src/matlab_mcp/output/plotly_style_mapper.py`:

```python
"""MATLAB figure property to Plotly JSON mapper.

Converts raw MATLAB figure property dicts (from ``mcp_extract_props.m``)
into Plotly figure dicts suitable for ``Plotly.newPlot()``.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

LINE_STYLE_MAP: dict[str, str] = {
    "-": "solid",
    "--": "dash",
    ":": "dot",
    "-.": "dashdot",
}

MARKER_MAP: dict[str, Optional[str]] = {
    "o": "circle",
    "+": "cross",
    "*": "star",
    ".": "circle",
    "x": "x",
    "s": "square",
    "d": "diamond",
    "^": "triangle-up",
    "v": "triangle-down",
    "<": "triangle-left",
    ">": "triangle-right",
    "p": "pentagon",
    "h": "hexagon",
    "none": None,
}

LEGEND_LOCATION_MAP: dict[str, dict] = {
    "northeast": {"x": 1, "y": 1, "xanchor": "right", "yanchor": "top"},
    "northwest": {"x": 0, "y": 1, "xanchor": "left", "yanchor": "top"},
    "southeast": {"x": 1, "y": 0, "xanchor": "right", "yanchor": "bottom"},
    "southwest": {"x": 0, "y": 0, "xanchor": "left", "yanchor": "bottom"},
    "north": {"x": 0.5, "y": 1, "xanchor": "center", "yanchor": "top"},
    "south": {"x": 0.5, "y": 0, "xanchor": "center", "yanchor": "bottom"},
    "east": {"x": 1, "y": 0.5, "xanchor": "right", "yanchor": "middle"},
    "west": {"x": 0, "y": 0.5, "xanchor": "left", "yanchor": "middle"},
    "best": {},
    "bestoutside": {"x": 1.05, "y": 1, "xanchor": "left", "yanchor": "top"},
    "northoutside": {"x": 0.5, "y": 1.05, "xanchor": "center", "yanchor": "bottom"},
    "southoutside": {"x": 0.5, "y": -0.1, "xanchor": "center", "yanchor": "top"},
    "eastoutside": {"x": 1.05, "y": 0.5, "xanchor": "left", "yanchor": "middle"},
    "westoutside": {"x": -0.15, "y": 0.5, "xanchor": "right", "yanchor": "middle"},
}

COLORMAP_MAP: dict[str, str] = {
    "parula": "Viridis",
    "jet": "Jet",
    "hsv": "HSV",
    "hot": "Hot",
    "cool": "Bluered",
    "gray": "Greys",
    "bone": "Greys",
    "copper": "Copper",
    "turbo": "Turbo",
}

GRID_STYLE_MAP: dict[str, Optional[str]] = {
    "-": "solid",
    "--": "dash",
    ":": "dot",
    "-.": "dashdot",
    "none": None,
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def rgb_to_css(rgb: list[float]) -> str:
    """Convert MATLAB [r, g, b] (0-1 range) to CSS ``rgb(R, G, B)``."""
    r = round(rgb[0] * 255)
    g = round(rgb[1] * 255)
    b = round(rgb[2] * 255)
    return f"rgb({r}, {g}, {b})"


def resolve_color(value: Any, fallback: Optional[str]) -> Optional[str]:
    """Resolve a MATLAB color value to a CSS color string.

    - list/tuple of floats -> rgb_to_css
    - ``"auto"`` -> *fallback*
    - ``"none"`` -> ``"rgba(0,0,0,0)"``
    """
    if isinstance(value, (list, tuple)):
        return rgb_to_css(value)
    if isinstance(value, str):
        low = value.lower()
        if low == "none":
            return "rgba(0,0,0,0)"
        if low == "auto":
            return fallback
    return fallback


def map_font(font_name: str) -> str:
    """Build a CSS font-family stack from a MATLAB font name."""
    if " " in font_name:
        font_name = f'"{font_name}"'
    return f"{font_name}, Arial, sans-serif"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plotly_style_mapper.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add plotly style mapper with utility functions and mapping tables"
```

---

## Chunk 2: Trace Converters — Line, Bar, Scatter

### Task 4: `convert_line` — MATLAB line to Plotly scatter trace

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plotly_style_mapper.py`:

```python
class TestConvertLine:
    def test_basic_line(self):
        from matlab_mcp.output.plotly_style_mapper import convert_line

        child = {
            "type": "line",
            "xdata": [1, 2, 3],
            "ydata": [4, 5, 6],
            "color": [0, 0.447, 0.741],
            "line_style": "-",
            "line_width": 2,
            "display_name": "sin(x)",
            "marker": "none",
            "marker_size": 6,
            "marker_face_color": "none",
            "marker_edge_color": "auto",
        }
        result = convert_line(child, "")

        assert result["type"] == "scatter"
        assert result["mode"] == "lines"
        assert result["x"] == [1, 2, 3]
        assert result["y"] == [4, 5, 6]
        assert result["line"]["color"] == "rgb(0, 114, 189)"
        assert result["line"]["width"] == 2
        assert result["line"]["dash"] == "solid"
        assert result["name"] == "sin(x)"
        assert result["xaxis"] == "x"
        assert result["yaxis"] == "y"

    def test_line_with_markers(self):
        from matlab_mcp.output.plotly_style_mapper import convert_line

        child = {
            "type": "line",
            "xdata": [1, 2],
            "ydata": [3, 4],
            "color": [1, 0, 0],
            "line_style": "--",
            "line_width": 1,
            "display_name": "",
            "marker": "o",
            "marker_size": 8,
            "marker_face_color": [0, 1, 0],
            "marker_edge_color": [0, 0, 0],
        }
        result = convert_line(child, "2")

        assert result["mode"] == "lines+markers"
        assert result["line"]["dash"] == "dash"
        assert result["marker"]["symbol"] == "circle"
        assert result["marker"]["size"] == 8
        assert result["marker"]["color"] == "rgb(0, 255, 0)"
        assert result["marker"]["line"]["color"] == "rgb(0, 0, 0)"
        assert result["xaxis"] == "x2"
        assert result["yaxis"] == "y2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertLine -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement convert_line**

Append to `src/matlab_mcp/output/plotly_style_mapper.py`:

```python
# ---------------------------------------------------------------------------
# Trace converters
# ---------------------------------------------------------------------------

def convert_line(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB line child to a Plotly scatter trace."""
    marker_symbol = MARKER_MAP.get(child.get("marker", "none"))
    mode = "lines+markers" if marker_symbol else "lines"

    line_color = resolve_color(child.get("color"), None)

    trace: dict[str, Any] = {
        "type": "scatter",
        "mode": mode,
        "x": child.get("xdata", []),
        "y": child.get("ydata", []),
        "line": {
            "color": line_color,
            "width": child.get("line_width", 1),
            "dash": LINE_STYLE_MAP.get(child.get("line_style", "-"), "solid"),
        },
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }

    name = child.get("display_name", "")
    if name:
        trace["name"] = name
    else:
        trace["showlegend"] = False

    if marker_symbol:
        face_color = resolve_color(
            child.get("marker_face_color"), line_color
        )
        edge_color = resolve_color(
            child.get("marker_edge_color"), line_color
        )
        trace["marker"] = {
            "symbol": marker_symbol,
            "size": child.get("marker_size", 6),
            "color": face_color,
            "line": {"color": edge_color, "width": 1},
        }

    return trace
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertLine -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_line trace converter"
```

---

### Task 5: `convert_bar` — MATLAB bar to Plotly bar trace

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertBar:
    def test_basic_bar(self):
        from matlab_mcp.output.plotly_style_mapper import convert_bar

        child = {
            "type": "bar",
            "xdata": [1, 2, 3],
            "ydata": [10, 20, 30],
            "face_color": [0, 0.447, 0.741],
            "edge_color": [0, 0, 0],
            "bar_width": 0.8,
            "display_name": "Sales",
        }
        result = convert_bar(child, "")

        assert result["type"] == "bar"
        assert result["x"] == [1, 2, 3]
        assert result["y"] == [10, 20, 30]
        assert result["marker"]["color"] == "rgb(0, 114, 189)"
        assert result["marker"]["line"]["color"] == "rgb(0, 0, 0)"
        assert result["name"] == "Sales"
        assert result["xaxis"] == "x"

    def test_bar_auto_edge_color(self):
        from matlab_mcp.output.plotly_style_mapper import convert_bar

        child = {
            "type": "bar",
            "xdata": [1],
            "ydata": [5],
            "face_color": [1, 0, 0],
            "edge_color": "auto",
            "bar_width": 0.8,
            "display_name": "",
        }
        result = convert_bar(child, "")
        # auto edge_color should inherit face_color
        assert result["marker"]["line"]["color"] == "rgb(255, 0, 0)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertBar -v`
Expected: FAIL

- [ ] **Step 3: Implement convert_bar**

Append to `src/matlab_mcp/output/plotly_style_mapper.py`:

```python
def convert_bar(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB bar child to a Plotly bar trace."""
    face_color = resolve_color(child.get("face_color"), None)
    edge_color = resolve_color(child.get("edge_color"), face_color)

    trace: dict[str, Any] = {
        "type": "bar",
        "x": child.get("xdata", []),
        "y": child.get("ydata", []),
        "width": child.get("bar_width", 0.8),
        "marker": {
            "color": face_color,
            "line": {"color": edge_color, "width": 1},
        },
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }

    name = child.get("display_name", "")
    if name:
        trace["name"] = name
    else:
        trace["showlegend"] = False

    return trace
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertBar -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_bar trace converter"
```

---

### Task 6: `convert_scatter_trace` — MATLAB scatter to Plotly scatter

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertScatterTrace:
    def test_basic_scatter(self):
        from matlab_mcp.output.plotly_style_mapper import convert_scatter_trace

        child = {
            "type": "scatter",
            "xdata": [1, 2, 3],
            "ydata": [4, 5, 6],
            "marker": "o",
            "size_data": 36,
            "marker_face_color": [0.85, 0.33, 0.1],
            "marker_edge_color": [0, 0, 0],
            "display_name": "Points",
        }
        result = convert_scatter_trace(child, "")

        assert result["type"] == "scatter"
        assert result["mode"] == "markers"
        assert result["x"] == [1, 2, 3]
        assert result["marker"]["symbol"] == "circle"
        # size_data is area in pt^2, Plotly uses diameter -> sqrt(36) = 6
        assert result["marker"]["size"] == 6
        assert result["marker"]["color"] == "rgb(217, 84, 26)"
        assert result["name"] == "Points"

    def test_scatter_default_size(self):
        from matlab_mcp.output.plotly_style_mapper import convert_scatter_trace

        child = {
            "type": "scatter",
            "xdata": [1],
            "ydata": [2],
            "marker": "x",
            "marker_face_color": [0, 0, 1],
            "marker_edge_color": "auto",
            "display_name": "",
        }
        result = convert_scatter_trace(child, "")
        assert result["marker"]["symbol"] == "x"
        # No size_data -> default 36 -> sqrt = 6
        assert result["marker"]["size"] == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertScatterTrace -v`
Expected: FAIL

- [ ] **Step 3: Implement convert_scatter_trace**

```python
def convert_scatter_trace(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB scatter child to a Plotly scatter trace."""
    face_color = resolve_color(child.get("marker_face_color"), None)
    edge_color = resolve_color(child.get("marker_edge_color"), face_color)
    marker_symbol = MARKER_MAP.get(child.get("marker", "o"), "circle")

    # MATLAB SizeData is area in pt^2; Plotly marker.size is diameter
    size_data = child.get("size_data", 36)
    plotly_size = round(math.sqrt(size_data))

    trace: dict[str, Any] = {
        "type": "scatter",
        "mode": "markers",
        "x": child.get("xdata", []),
        "y": child.get("ydata", []),
        "marker": {
            "symbol": marker_symbol,
            "size": plotly_size,
            "color": face_color,
            "line": {"color": edge_color, "width": 1},
        },
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }

    name = child.get("display_name", "")
    if name:
        trace["name"] = name
    else:
        trace["showlegend"] = False

    return trace
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertScatterTrace -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_scatter_trace converter with SizeData->diameter"
```

---

## Chunk 3: Trace Converters — Surface, Heatmap, Histogram, Patch

### Task 7: `convert_surface`

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertSurface:
    def test_basic_surface(self):
        from matlab_mcp.output.plotly_style_mapper import convert_surface

        child = {
            "type": "surface",
            "xdata": [[0, 1], [0, 1]],
            "ydata": [[0, 0], [1, 1]],
            "zdata": [[0, 1], [1, 0]],
            "colormap": "parula",
        }
        result = convert_surface(child, "")

        assert result["type"] == "surface"
        assert result["x"] == [[0, 1], [0, 1]]
        assert result["z"] == [[0, 1], [1, 0]]
        assert result["colorscale"] == "Viridis"

    def test_unknown_colormap_passthrough(self):
        from matlab_mcp.output.plotly_style_mapper import convert_surface

        child = {
            "type": "surface",
            "xdata": [[0]], "ydata": [[0]], "zdata": [[0]],
            "colormap": "unknown_map",
        }
        result = convert_surface(child, "")
        assert result["colorscale"] == "Viridis"  # fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertSurface -v`

- [ ] **Step 3: Implement**

```python
def convert_surface(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB surface child to a Plotly surface trace."""
    colormap = child.get("colormap", "parula")
    colorscale = COLORMAP_MAP.get(colormap, "Viridis")

    return {
        "type": "surface",
        "x": child.get("xdata", []),
        "y": child.get("ydata", []),
        "z": child.get("zdata", []),
        "colorscale": colorscale,
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertSurface -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_surface trace converter"
```

---

### Task 8: `convert_heatmap`

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertHeatmap:
    def test_basic_heatmap(self):
        from matlab_mcp.output.plotly_style_mapper import convert_heatmap

        child = {
            "type": "image",
            "cdata": [[0, 1], [1, 0]],
            "colormap": "gray",
        }
        result = convert_heatmap(child, "")

        assert result["type"] == "heatmap"
        assert result["z"] == [[0, 1], [1, 0]]
        assert result["colorscale"] == "Greys"
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertHeatmap -v`

- [ ] **Step 3: Implement**

```python
def convert_heatmap(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB image child to a Plotly heatmap trace."""
    colormap = child.get("colormap", "gray")
    colorscale = COLORMAP_MAP.get(colormap, "Greys")

    trace: dict[str, Any] = {
        "type": "heatmap",
        "z": child.get("cdata", []),
        "colorscale": colorscale,
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }
    return trace
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_heatmap trace converter"
```

---

### Task 9: `convert_histogram_trace`

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertHistogramTrace:
    def test_basic_histogram(self):
        from matlab_mcp.output.plotly_style_mapper import convert_histogram_trace

        child = {
            "type": "histogram",
            "data": [1, 2, 2, 3, 3, 3],
            "face_color": [0, 0.447, 0.741],
            "edge_color": [1, 1, 1],
            "num_bins": None,
            "bin_edges": None,
        }
        result = convert_histogram_trace(child, "")

        assert result["type"] == "histogram"
        assert result["x"] == [1, 2, 2, 3, 3, 3]
        assert result["marker"]["color"] == "rgb(0, 114, 189)"
        assert result["marker"]["line"]["color"] == "rgb(255, 255, 255)"

    def test_histogram_with_bin_edges(self):
        from matlab_mcp.output.plotly_style_mapper import convert_histogram_trace

        child = {
            "type": "histogram",
            "data": [1, 2, 3],
            "face_color": [1, 0, 0],
            "edge_color": [0, 0, 0],
            "num_bins": None,
            "bin_edges": [0.5, 1.5, 2.5, 3.5],
        }
        result = convert_histogram_trace(child, "")
        assert result["xbins"]["start"] == 0.5
        assert result["xbins"]["end"] == 3.5
        assert result["xbins"]["size"] == 1.0
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
def convert_histogram_trace(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB histogram child to a Plotly histogram trace."""
    face_color = resolve_color(child.get("face_color"), None)
    edge_color = resolve_color(child.get("edge_color"), face_color)

    trace: dict[str, Any] = {
        "type": "histogram",
        "x": child.get("data", []),
        "marker": {
            "color": face_color,
            "line": {"color": edge_color, "width": 1},
        },
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }

    bin_edges = child.get("bin_edges")
    if bin_edges and len(bin_edges) >= 2:
        trace["xbins"] = {
            "start": bin_edges[0],
            "end": bin_edges[-1],
            "size": bin_edges[1] - bin_edges[0],
        }

    return trace
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_histogram_trace converter"
```

---

### Task 10: `convert_patch` — bands/shadings to Plotly fill

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertPatch:
    def test_basic_patch(self):
        from matlab_mcp.output.plotly_style_mapper import convert_patch

        child = {
            "type": "patch",
            "xdata": [0, 1, 1, 0],
            "ydata": [0, 0, 1, 1],
            "face_color": [0.8, 0.9, 1.0],
            "face_alpha": 0.3,
            "edge_color": "none",
            "display_name": "Band",
        }
        result = convert_patch(child, "")

        assert result["type"] == "scatter"
        assert result["fill"] == "toself"
        # x/y should close the polygon
        assert result["x"] == [0, 1, 1, 0, 0]
        assert result["y"] == [0, 0, 1, 1, 0]
        assert "rgba" in result["fillcolor"]  # includes alpha
        assert result["name"] == "Band"
        # edge_color "none" -> transparent line
        assert result["line"]["color"] == "rgba(0,0,0,0)"
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
def convert_patch(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB patch child to a Plotly scatter trace with fill."""
    face_color_raw = child.get("face_color", [0.8, 0.8, 0.8])
    face_alpha = child.get("face_alpha", 1.0)
    edge_color = resolve_color(child.get("edge_color"), None)

    # Build fillcolor with alpha
    if isinstance(face_color_raw, (list, tuple)):
        r = round(face_color_raw[0] * 255)
        g = round(face_color_raw[1] * 255)
        b = round(face_color_raw[2] * 255)
        fillcolor = f"rgba({r},{g},{b},{face_alpha})"
    else:
        fillcolor = resolve_color(face_color_raw, "rgba(128,128,128,0.5)")

    # Close the polygon by repeating the first point
    xdata = list(child.get("xdata", []))
    ydata = list(child.get("ydata", []))
    if xdata and ydata and (xdata[0] != xdata[-1] or ydata[0] != ydata[-1]):
        xdata.append(xdata[0])
        ydata.append(ydata[0])

    trace: dict[str, Any] = {
        "type": "scatter",
        "mode": "lines",
        "fill": "toself",
        "fillcolor": fillcolor,
        "x": xdata,
        "y": ydata,
        "line": {"color": edge_color or "rgba(0,0,0,0)", "width": 1},
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }

    name = child.get("display_name", "")
    if name:
        trace["name"] = name

    return trace
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_patch for bands/shadings"
```

---

## Chunk 4: Layout, Subplots, and Figure Assembly

### Task 11: `compute_domains` — subplot domain computation

**Files:**
- Create: `tests/test_subplot_layout.py`
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_subplot_layout.py`:

```python
"""Tests for subplot layout domain computation."""
import pytest


class TestComputeDomains:
    def test_single_axes_no_grid(self):
        from matlab_mcp.output.plotly_style_mapper import compute_domains

        result = compute_domains(None, [{}])
        assert result == [{"x": [0, 1], "y": [0, 1]}]

    def test_2x2_grid(self):
        from matlab_mcp.output.plotly_style_mapper import compute_domains

        grid = {"rows": 2, "cols": 2}
        axes = [
            {"grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1}},
            {"grid_index": {"row": 1, "col": 2, "rowspan": 1, "colspan": 1}},
            {"grid_index": {"row": 2, "col": 1, "rowspan": 1, "colspan": 1}},
            {"grid_index": {"row": 2, "col": 2, "rowspan": 1, "colspan": 1}},
        ]
        result = compute_domains(grid, axes)

        assert len(result) == 4
        # Top-left: x starts near 0, y near 0.5
        assert result[0]["x"][0] < 0.1
        assert result[0]["y"][0] > 0.4
        # Bottom-right: x ends near 1, y near 0
        assert result[3]["x"][1] > 0.9
        assert result[3]["y"][0] < 0.1

    def test_spanning_tile(self):
        from matlab_mcp.output.plotly_style_mapper import compute_domains

        grid = {"rows": 2, "cols": 3}
        axes = [
            {"grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 2}},
        ]
        result = compute_domains(grid, axes)

        # colspan=2 in a 3-col grid -> x domain should span ~0 to ~0.67
        assert result[0]["x"][1] > 0.6
        assert result[0]["x"][1] < 0.7

    def test_domains_clamped_to_unit(self):
        from matlab_mcp.output.plotly_style_mapper import compute_domains

        grid = {"rows": 1, "cols": 1}
        axes = [
            {"grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1}},
        ]
        result = compute_domains(grid, axes)

        assert result[0]["x"][0] >= 0
        assert result[0]["x"][1] <= 1
        assert result[0]["y"][0] >= 0
        assert result[0]["y"][1] <= 1
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_subplot_layout.py -v`

- [ ] **Step 3: Implement compute_domains**

Append to `src/matlab_mcp/output/plotly_style_mapper.py`:

```python
# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def compute_domains(
    grid: Optional[dict], axes_list: list[dict]
) -> list[dict[str, list[float]]]:
    """Compute Plotly xaxis/yaxis domain pairs from grid positions.

    Returns a list parallel to *axes_list*.
    """
    if grid is None:
        return [{"x": [0, 1], "y": [0, 1]}]

    rows = grid["rows"]
    cols = grid["cols"]
    gap_x, gap_y = 0.04, 0.06

    domains: list[dict[str, list[float]]] = []
    for ax in axes_list:
        gi = ax["grid_index"]
        col_start = (gi["col"] - 1) / cols
        col_end = (gi["col"] - 1 + gi["colspan"]) / cols
        row_start = (gi["row"] - 1) / rows
        row_end = (gi["row"] - 1 + gi["rowspan"]) / rows

        x_domain = [max(0, col_start + gap_x / 2), min(1, col_end - gap_x / 2)]
        y_domain = [max(0, 1 - row_end + gap_y / 2), min(1, 1 - row_start - gap_y / 2)]
        domains.append({"x": x_domain, "y": y_domain})

    return domains
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_subplot_layout.py -v`
Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_subplot_layout.py
git commit -m "feat: add compute_domains for subplot layout"
```

---

### Task 12: `convert_axes` and `convert_layout` — axes to layout fragments

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing tests**

```python
class TestConvertAxes:
    def test_single_axes_with_line(self):
        from matlab_mcp.output.plotly_style_mapper import convert_axes

        axes_data = {
            "grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1},
            "position": [0.13, 0.11, 0.775, 0.815],
            "title": {"text": "Test", "font_name": "Helvetica", "font_size": 14, "font_weight": "bold"},
            "xlabel": {"text": "X", "font_name": "Helvetica", "font_size": 12},
            "ylabel": {"text": "Y", "font_name": "Helvetica", "font_size": 12},
            "xlim": [0, 10],
            "ylim": [-1, 1],
            "xgrid": True,
            "ygrid": True,
            "xdir": "normal",
            "ydir": "normal",
            "xtick": [0, 5, 10],
            "ytick": [-1, 0, 1],
            "xticklabels": None,
            "yticklabels": None,
            "tick_font": {"font_name": "Helvetica", "font_size": 10},
            "color": [1, 1, 1],
            "grid_color": [0.15, 0.15, 0.15],
            "grid_alpha": 0.15,
            "grid_line_style": "-",
            "legend": {"visible": True, "entries": ["sin(x)"], "location": "northeast"},
            "children": [
                {
                    "type": "line",
                    "xdata": [0, 5, 10],
                    "ydata": [0, 1, 0],
                    "color": [0, 0.447, 0.741],
                    "line_style": "-",
                    "line_width": 2,
                    "display_name": "sin(x)",
                    "marker": "none",
                    "marker_size": 6,
                    "marker_face_color": "none",
                    "marker_edge_color": "auto",
                },
            ],
        }
        traces, layout_frag = convert_axes(axes_data, 0)

        assert len(traces) == 1
        assert traces[0]["type"] == "scatter"
        assert "xaxis" in layout_frag
        assert layout_frag["xaxis"]["title"]["text"] == "X"
        assert layout_frag["xaxis"]["range"] == [0, 10]
        assert layout_frag["xaxis"]["showgrid"] is True
        assert layout_frag["yaxis"]["range"] == [-1, 1]
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertAxes -v`

- [ ] **Step 3: Implement convert_axes**

```python
def _axis_suffix(index: int) -> str:
    """Return '' for index 0, '2' for 1, '3' for 2, etc."""
    return "" if index == 0 else str(index + 1)


def _build_axis_layout(axes_data: dict, suffix: str) -> dict:
    """Build xaxis/yaxis layout dicts from MATLAB axes properties."""
    grid_color_rgb = axes_data.get("grid_color", [0.15, 0.15, 0.15])
    grid_alpha = axes_data.get("grid_alpha", 0.15)
    r, g, b = [round(c * 255) for c in grid_color_rgb]
    grid_color = f"rgba({r},{g},{b},{grid_alpha})"
    grid_dash = GRID_STYLE_MAP.get(axes_data.get("grid_line_style", "-"), "solid")

    tick_font = axes_data.get("tick_font", {})
    tick_font_dict = {}
    if tick_font.get("font_name"):
        tick_font_dict["family"] = map_font(tick_font["font_name"])
    if tick_font.get("font_size"):
        tick_font_dict["size"] = tick_font["font_size"]

    def _label_dict(label_data: Optional[dict]) -> dict:
        if not label_data or not label_data.get("text"):
            return {}
        result = {"text": label_data["text"]}
        font = {}
        if label_data.get("font_name"):
            font["family"] = map_font(label_data["font_name"])
        if label_data.get("font_size"):
            font["size"] = label_data["font_size"]
        if font:
            result["font"] = font
        return result

    x_key = f"xaxis{suffix}"
    y_key = f"yaxis{suffix}"

    xlim = axes_data.get("xlim")
    ylim = axes_data.get("ylim")

    layout: dict[str, Any] = {}

    layout[x_key] = {
        "showgrid": axes_data.get("xgrid", False),
        "gridcolor": grid_color,
        "griddash": grid_dash,
    }
    x_title = _label_dict(axes_data.get("xlabel"))
    if x_title:
        layout[x_key]["title"] = x_title
    if xlim:
        layout[x_key]["range"] = xlim
    xtick = axes_data.get("xtick")
    if xtick:
        layout[x_key]["tickvals"] = xtick
    xticklabels = axes_data.get("xticklabels")
    if xticklabels:
        layout[x_key]["ticktext"] = xticklabels
    if tick_font_dict:
        layout[x_key]["tickfont"] = tick_font_dict
    if axes_data.get("xdir") == "reverse":
        layout[x_key]["autorange"] = "reversed"

    layout[y_key] = {
        "showgrid": axes_data.get("ygrid", False),
        "gridcolor": grid_color,
        "griddash": grid_dash,
    }
    y_title = _label_dict(axes_data.get("ylabel"))
    if y_title:
        layout[y_key]["title"] = y_title
    if ylim:
        layout[y_key]["range"] = ylim
    ytick = axes_data.get("ytick")
    if ytick:
        layout[y_key]["tickvals"] = ytick
    yticklabels = axes_data.get("yticklabels")
    if yticklabels:
        layout[y_key]["ticktext"] = yticklabels
    if tick_font_dict:
        layout[y_key]["tickfont"] = tick_font_dict
    if axes_data.get("ydir") == "reverse":
        layout[y_key]["autorange"] = "reversed"

    # Link y-axis to its x-axis for multi-axis subplots
    if suffix:
        layout[y_key]["anchor"] = f"x{suffix}"

    return layout


_CHILD_CONVERTERS: dict[str, Any] = {}  # populated after all converters defined


def convert_axes(axes_data: dict, axis_index: int) -> tuple[list[dict], dict]:
    """Convert a single MATLAB axes dict to Plotly traces + layout fragment."""
    suffix = _axis_suffix(axis_index)
    traces: list[dict] = []

    for child in axes_data.get("children", []):
        child_type = child.get("type", "")
        converter = _CHILD_CONVERTERS.get(child_type)
        if converter:
            traces.append(converter(child, suffix))
        else:
            logger.warning("Unknown child type %r — skipping", child_type)

    layout_frag = _build_axis_layout(axes_data, suffix)

    return traces, layout_frag
```

After all converter functions are defined, add the dispatcher registration:

```python
_CHILD_CONVERTERS.update({
    "line": convert_line,
    "bar": convert_bar,
    "scatter": convert_scatter_trace,
    "surface": convert_surface,
    "image": convert_heatmap,
    "histogram": convert_histogram_trace,
    "patch": convert_patch,
})
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertAxes -v`

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_axes with axis layout builder and child dispatch"
```

---

### Task 13: `convert_figure` — top-level orchestrator

**Files:**
- Modify: `src/matlab_mcp/output/plotly_style_mapper.py`
- Modify: `tests/test_plotly_style_mapper.py`

- [ ] **Step 1: Write the failing test**

```python
class TestConvertFigure:
    def test_single_line_figure(self):
        from matlab_mcp.output.plotly_style_mapper import convert_figure

        matlab_fig = {
            "schema_version": 1,
            "layout_type": "single",
            "background_color": [0.94, 0.94, 0.94],
            "axes": [
                {
                    "grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1},
                    "position": [0.13, 0.11, 0.775, 0.815],
                    "title": {"text": "Test", "font_name": "Helvetica", "font_size": 14, "font_weight": "bold"},
                    "xlabel": {"text": "X", "font_name": "Helvetica", "font_size": 12},
                    "ylabel": {"text": "Y", "font_name": "Helvetica", "font_size": 12},
                    "xlim": [0, 10], "ylim": [-1, 1],
                    "xgrid": True, "ygrid": True,
                    "xdir": "normal", "ydir": "normal",
                    "xtick": None, "ytick": None,
                    "xticklabels": None, "yticklabels": None,
                    "tick_font": {"font_name": "Helvetica", "font_size": 10},
                    "color": [1, 1, 1],
                    "grid_color": [0.15, 0.15, 0.15],
                    "grid_alpha": 0.15,
                    "grid_line_style": "-",
                    "legend": {"visible": False, "entries": [], "location": "best"},
                    "children": [
                        {
                            "type": "line",
                            "xdata": [0, 5, 10],
                            "ydata": [0, 1, 0],
                            "color": [0, 0.447, 0.741],
                            "line_style": "-",
                            "line_width": 2,
                            "display_name": "",
                            "marker": "none",
                            "marker_size": 6,
                            "marker_face_color": "none",
                            "marker_edge_color": "auto",
                        },
                    ],
                },
            ],
        }
        result = convert_figure(matlab_fig)

        assert "data" in result
        assert "layout" in result
        assert len(result["data"]) == 1
        assert result["data"][0]["type"] == "scatter"
        assert result["layout"]["paper_bgcolor"] == "rgb(240, 240, 240)"
        assert result["layout"]["plot_bgcolor"] == "rgb(255, 255, 255)"
        assert result["layout"]["title"]["text"] == "Test"

    def test_subplot_figure(self):
        from matlab_mcp.output.plotly_style_mapper import convert_figure

        matlab_fig = {
            "schema_version": 1,
            "layout_type": "subplot",
            "background_color": [1, 1, 1],
            "grid": {"rows": 1, "cols": 2},
            "axes": [
                {
                    "grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1},
                    "position": [0.05, 0.1, 0.4, 0.8],
                    "title": {"text": "Left", "font_name": "Helvetica", "font_size": 12, "font_weight": "normal"},
                    "xlabel": {}, "ylabel": {},
                    "xlim": None, "ylim": None,
                    "xgrid": False, "ygrid": False,
                    "xdir": "normal", "ydir": "normal",
                    "xtick": None, "ytick": None,
                    "xticklabels": None, "yticklabels": None,
                    "tick_font": {},
                    "color": [1, 1, 1],
                    "grid_color": [0.15, 0.15, 0.15], "grid_alpha": 0.15,
                    "grid_line_style": "-",
                    "legend": {"visible": False, "entries": [], "location": "best"},
                    "children": [],
                },
                {
                    "grid_index": {"row": 1, "col": 2, "rowspan": 1, "colspan": 1},
                    "position": [0.55, 0.1, 0.4, 0.8],
                    "title": {"text": "Right", "font_name": "Helvetica", "font_size": 12, "font_weight": "normal"},
                    "xlabel": {}, "ylabel": {},
                    "xlim": None, "ylim": None,
                    "xgrid": False, "ygrid": False,
                    "xdir": "normal", "ydir": "normal",
                    "xtick": None, "ytick": None,
                    "xticklabels": None, "yticklabels": None,
                    "tick_font": {},
                    "color": [1, 1, 1],
                    "grid_color": [0.15, 0.15, 0.15], "grid_alpha": 0.15,
                    "grid_line_style": "-",
                    "legend": {"visible": False, "entries": [], "location": "best"},
                    "children": [],
                },
            ],
        }
        result = convert_figure(matlab_fig)

        assert "xaxis" in result["layout"]
        assert "xaxis2" in result["layout"]
        assert "yaxis" in result["layout"]
        assert "yaxis2" in result["layout"]
        assert "domain" in result["layout"]["xaxis"]
        assert "domain" in result["layout"]["xaxis2"]
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertFigure -v`

- [ ] **Step 3: Implement convert_figure**

```python
def convert_figure(matlab_fig: dict) -> dict:
    """Convert a full MATLAB figure property dict to a Plotly figure dict."""
    axes_list = matlab_fig.get("axes", [])
    layout_type = matlab_fig.get("layout_type", "single")
    grid = matlab_fig.get("grid") if layout_type != "single" else None

    all_traces: list[dict] = []
    merged_layout: dict[str, Any] = {}

    # Background colors
    bg = matlab_fig.get("background_color", [0.94, 0.94, 0.94])
    merged_layout["paper_bgcolor"] = rgb_to_css(bg)

    # Compute subplot domains
    domains = compute_domains(grid, axes_list)

    show_legend = False

    for i, axes_data in enumerate(axes_list):
        traces, layout_frag = convert_axes(axes_data, i)
        all_traces.extend(traces)
        merged_layout.update(layout_frag)

        suffix = _axis_suffix(i)
        x_key = f"xaxis{suffix}"
        y_key = f"yaxis{suffix}"

        # Apply domains for multi-axes
        if len(axes_list) > 1:
            if x_key in merged_layout:
                merged_layout[x_key]["domain"] = domains[i]["x"]
            if y_key in merged_layout:
                merged_layout[y_key]["domain"] = domains[i]["y"]

        # Axes background
        axes_bg = axes_data.get("color", [1, 1, 1])
        if i == 0:
            merged_layout["plot_bgcolor"] = rgb_to_css(axes_bg)

        # Title from first axes
        title_data = axes_data.get("title", {})
        if i == 0 and title_data.get("text"):
            title_dict: dict[str, Any] = {"text": title_data["text"]}
            font: dict[str, Any] = {}
            if title_data.get("font_name"):
                font["family"] = map_font(title_data["font_name"])
            if title_data.get("font_size"):
                font["size"] = title_data["font_size"]
            if font:
                title_dict["font"] = font
            merged_layout["title"] = title_dict

        # Legend
        legend_data = axes_data.get("legend", {})
        if legend_data.get("visible"):
            show_legend = True
            location = legend_data.get("location", "best")
            legend_pos = LEGEND_LOCATION_MAP.get(location, {})
            merged_layout["legend"] = legend_pos

    merged_layout["showlegend"] = show_legend

    return {"data": all_traces, "layout": merged_layout}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_plotly_style_mapper.py::TestConvertFigure -v`

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/plotly_style_mapper.py tests/test_plotly_style_mapper.py
git commit -m "feat: add convert_figure orchestrator with subplot support"
```

---

## Chunk 5: MATLAB Extractor and Executor Integration

### Task 14: Rewrite MATLAB property extractor

**Files:**
- Remove: `src/matlab_mcp/matlab_helpers/mcp_fig2plotly.m`
- Create: `src/matlab_mcp/matlab_helpers/mcp_extract_props.m`

- [ ] **Step 1: Write `mcp_extract_props.m`**

Create `src/matlab_mcp/matlab_helpers/mcp_extract_props.m`:

```matlab
function mcp_extract_props(fig_handle, output_path)
%MCP_EXTRACT_PROPS Extract raw figure properties to JSON for Plotly conversion.
%
%   mcp_extract_props(fig_handle, output_path)
%
%   Extracts all visual properties from the MATLAB figure specified by
%   fig_handle and writes them as a JSON file to output_path.
%   If fig_handle is omitted, gcf is used.

    if nargin < 1 || isempty(fig_handle)
        fig_handle = gcf;
    end
    if nargin < 2
        error('MCP_EXTRACT_PROPS:MissingArg', 'output_path is required');
    end

    result = struct();
    result.schema_version = 1;

    % Figure background
    result.background_color = get(fig_handle, 'Color');

    % Detect layout type
    tl = findobj(fig_handle, 'Type', 'tiledlayout');
    axes_list = findobj(fig_handle, 'Type', 'axes');
    % Remove legend axes
    axes_list = axes_list(~arrayfun(@(a) isa(a, 'matlab.graphics.illustration.Legend'), axes_list));

    if ~isempty(tl)
        result.layout_type = 'tiledlayout';
        gs = tl.GridSize;
        result.grid = struct('rows', gs(1), 'cols', gs(2));
    elseif length(axes_list) > 1
        result.layout_type = 'subplot';
        result.grid = infer_grid(axes_list);
    else
        result.layout_type = 'single';
    end

    % Extract each axes
    result.axes = {};
    for ax_idx = 1:length(axes_list)
        ax = axes_list(ax_idx);
        ax_data = extract_axes_data(ax, result.layout_type, tl);
        result.axes{end+1} = ax_data;
    end

    % Write JSON
    json_str = jsonencode(result);
    fid = fopen(output_path, 'w');
    if fid == -1
        warning('MCP_EXTRACT_PROPS:WriteError', 'Cannot write to %s', output_path);
        return;
    end
    fprintf(fid, '%s', json_str);
    fclose(fid);
end


function ax_data = extract_axes_data(ax, layout_type, tl)
    ax_data = struct();

    % Position and grid index
    ax_data.position = get(ax, 'Position');
    if strcmp(layout_type, 'tiledlayout') && ~isempty(tl)
        try
            tile_info = ax.Layout;
            ax_data.grid_index = struct('row', tile_info.Tile(1), 'col', tile_info.Tile(2), ...
                'rowspan', tile_info.TileSpan(1), 'colspan', tile_info.TileSpan(2));
        catch
            ax_data.grid_index = struct('row', 1, 'col', 1, 'rowspan', 1, 'colspan', 1);
        end
    else
        ax_data.grid_index = struct('row', 1, 'col', 1, 'rowspan', 1, 'colspan', 1);
    end

    % Title
    title_obj = get(ax, 'Title');
    ax_data.title = struct('text', get(title_obj, 'String'), ...
        'font_name', get(title_obj, 'FontName'), ...
        'font_size', get(title_obj, 'FontSize'), ...
        'font_weight', get(title_obj, 'FontWeight'));

    % Labels
    xl = get(ax, 'XLabel');
    ax_data.xlabel = struct('text', get(xl, 'String'), ...
        'font_name', get(xl, 'FontName'), 'font_size', get(xl, 'FontSize'));
    yl = get(ax, 'YLabel');
    ax_data.ylabel = struct('text', get(yl, 'String'), ...
        'font_name', get(yl, 'FontName'), 'font_size', get(yl, 'FontSize'));

    % Axis ranges and ticks
    ax_data.xlim = get(ax, 'XLim');
    ax_data.ylim = get(ax, 'YLim');
    ax_data.xgrid = strcmp(get(ax, 'XGrid'), 'on');
    ax_data.ygrid = strcmp(get(ax, 'YGrid'), 'on');
    ax_data.xdir = get(ax, 'XDir');
    ax_data.ydir = get(ax, 'YDir');
    ax_data.xtick = get(ax, 'XTick');
    ax_data.ytick = get(ax, 'YTick');

    xtl = get(ax, 'XTickLabel');
    if ~isempty(xtl), ax_data.xticklabels = xtl; else, ax_data.xticklabels = []; end
    ytl = get(ax, 'YTickLabel');
    if ~isempty(ytl), ax_data.yticklabels = ytl; else, ax_data.yticklabels = []; end

    ax_data.tick_font = struct('font_name', get(ax, 'FontName'), ...
        'font_size', get(ax, 'FontSize'));

    % Colors and grid style
    ax_data.color = get(ax, 'Color');
    ax_data.grid_color = get(ax, 'GridColor');
    ax_data.grid_alpha = get(ax, 'GridAlpha');
    ax_data.grid_line_style = get(ax, 'GridLineStyle');

    % Legend (ax.Legend is available in R2020a+, fallback for older)
    try
        leg = ax.Legend;
    catch
        leg = findobj(get(ax, 'Parent'), 'Type', 'legend');
        if ~isempty(leg), leg = leg(1); end
    end
    if ~isempty(leg) && isvalid(leg)
        ax_data.legend = struct('visible', true, ...
            'entries', {get(leg, 'String')}, ...
            'location', get(leg, 'Location'));
    else
        ax_data.legend = struct('visible', false, 'entries', {{}}, 'location', 'best');
    end

    % Children
    ax_data.children = {};
    children = get(ax, 'Children');
    for ch_idx = 1:length(children)
        child = children(ch_idx);
        child_data = extract_child_data(child);
        if ~isempty(child_data)
            ax_data.children{end+1} = child_data;
        end
    end
end


function child_data = extract_child_data(child)
    child_type = lower(get(child, 'Type'));
    child_data = struct();

    switch child_type
        case 'line'
            child_data.type = 'line';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.color = get(child, 'Color');
            child_data.line_style = get(child, 'LineStyle');
            child_data.line_width = get(child, 'LineWidth');
            child_data.display_name = get(child, 'DisplayName');
            child_data.marker = get(child, 'Marker');
            child_data.marker_size = get(child, 'MarkerSize');
            child_data.marker_face_color = get(child, 'MarkerFaceColor');
            child_data.marker_edge_color = get(child, 'MarkerEdgeColor');

        case 'bar'
            child_data.type = 'bar';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.face_color = get(child, 'FaceColor');
            child_data.edge_color = get(child, 'EdgeColor');
            child_data.bar_width = get(child, 'BarWidth');
            child_data.display_name = get(child, 'DisplayName');

        case 'scatter'
            child_data.type = 'scatter';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.marker = get(child, 'Marker');
            child_data.size_data = get(child, 'SizeData');
            child_data.marker_face_color = get(child, 'MarkerFaceColor');
            child_data.marker_edge_color = get(child, 'MarkerEdgeColor');
            child_data.display_name = get(child, 'DisplayName');

        case 'surface'
            child_data.type = 'surface';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.zdata = get(child, 'ZData');
            try
                child_data.colormap = get_colormap_name(ancestor(child, 'axes'));
            catch
                child_data.colormap = 'parula';
            end

        case 'image'
            child_data.type = 'image';
            child_data.cdata = get(child, 'CData');
            try
                child_data.colormap = get_colormap_name(ancestor(child, 'axes'));
            catch
                child_data.colormap = 'gray';
            end

        case 'histogram'
            child_data.type = 'histogram';
            child_data.data = get(child, 'Data');
            child_data.face_color = get(child, 'FaceColor');
            child_data.edge_color = get(child, 'EdgeColor');
            child_data.num_bins = get(child, 'NumBins');
            child_data.bin_edges = get(child, 'BinEdges');

        case 'patch'
            child_data.type = 'patch';
            xd = get(child, 'XData');
            yd = get(child, 'YData');
            % Flatten patch data (may be matrix for multi-face patches)
            if ~isvector(xd), xd = xd(:,1)'; end
            if ~isvector(yd), yd = yd(:,1)'; end
            child_data.xdata = xd;
            child_data.ydata = yd;
            child_data.face_color = get(child, 'FaceColor');
            child_data.face_alpha = get(child, 'FaceAlpha');
            child_data.edge_color = get(child, 'EdgeColor');
            child_data.display_name = get(child, 'DisplayName');

        otherwise
            child_data = [];
            return;
    end
end


function grid = infer_grid(axes_list)
%_INFER_GRID Infer grid dimensions from axes positions.
    positions = zeros(length(axes_list), 4);
    for i = 1:length(axes_list)
        positions(i,:) = get(axes_list(i), 'Position');
    end

    % Cluster unique left values for columns, bottom values for rows
    lefts = sort(unique(round(positions(:,1), 2)));
    bottoms = sort(unique(round(positions(:,2), 2)), 'descend');

    grid = struct('rows', length(bottoms), 'cols', length(lefts));
end


function name = get_colormap_name(ax)
%_GET_COLORMAP_NAME Try to determine the colormap name.
    cmap = colormap(ax);
    % Compare with known colormaps
    known = {'parula','jet','hsv','hot','cool','gray','bone','copper','turbo'};
    for i = 1:length(known)
        try
            ref = feval(known{i}, size(cmap, 1));
            if max(abs(cmap - ref), [], 'all') < 0.01
                name = known{i};
                return;
            end
        catch
        end
    end
    name = 'parula';
end
```

- [ ] **Step 2: Remove old file**

```bash
git rm src/matlab_mcp/matlab_helpers/mcp_fig2plotly.m
```

- [ ] **Step 3: Commit**

```bash
git add src/matlab_mcp/matlab_helpers/mcp_extract_props.m
git commit -m "feat: rewrite MATLAB figure extractor as mcp_extract_props.m"
```

---

### Task 15: Wire `temp_dir` through `execute_code_impl`

**Files:**
- Modify: `src/matlab_mcp/tools/core.py:22-62`
- Modify: `src/matlab_mcp/server.py:368-373`

- [ ] **Step 1: Update `execute_code_impl` to accept `temp_dir`**

In `src/matlab_mcp/tools/core.py`, change the function signature and the executor call:

```python
async def execute_code_impl(
    code: str,
    session_id: str,
    executor: Any,
    security: Any,
    temp_dir: Optional[str] = None,
) -> dict:
```

And change line 62 from:
```python
    return await executor.execute(session_id=session_id, code=code)
```
to:
```python
    return await executor.execute(session_id=session_id, code=code, temp_dir=temp_dir)
```

- [ ] **Step 2: Update `server.py` to pass `temp_dir`**

In `src/matlab_mcp/server.py`, change the `execute_code` tool handler (around line 368):

```python
        result = await execute_code_impl(
            code=code,
            session_id=session_id,
            executor=state.executor,
            security=state.security,
            temp_dir=temp_dir,
        )
```

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `pytest tests/ -v --ignore=tests/test_integration_figures.py -x`
Expected: all existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/matlab_mcp/tools/core.py src/matlab_mcp/server.py
git commit -m "feat: wire temp_dir through execute_code_impl to executor"
```

---

### Task 16: Implement figure pipeline in `executor._build_result`

**Files:**
- Modify: `src/matlab_mcp/jobs/executor.py:271-275`

- [ ] **Step 1: Replace the placeholder in `_build_result`**

Replace the figure placeholder block (lines 271-275) with:

```python
        # Figures — extract properties and convert to Plotly
        figures: list = []
        if self._config.output.plotly_conversion and temp_dir is not None:
            try:
                import glob as glob_mod
                from matlab_mcp.output.plotly_convert import load_plotly_json
                from matlab_mcp.output.plotly_style_mapper import convert_figure

                # Run MATLAB-side figure extraction
                extract_code = (
                    f"__mcp_figs = findobj(0, 'Type', 'figure');\n"
                    f"for __mcp_i = 1:length(__mcp_figs)\n"
                    f"    mcp_extract_props(__mcp_figs(__mcp_i), "
                    f"fullfile('{temp_dir}', sprintf('{job.job_id}_fig%d.json', __mcp_i)));\n"
                    f"    close(__mcp_figs(__mcp_i));\n"
                    f"end\n"
                    f"clear __mcp_figs __mcp_i;\n"
                )
                try:
                    engine.execute(extract_code, background=False)
                except Exception as exc:
                    logger.warning("Figure extraction failed: %s", exc)

                # Load and convert each figure JSON
                fig_pattern = os.path.join(temp_dir, f"{job.job_id}_fig*.json")
                for fig_file in sorted(glob_mod.glob(fig_pattern)):
                    matlab_data = load_plotly_json(fig_file)
                    if matlab_data:
                        plotly_fig = convert_figure(matlab_data)
                        figures.append(plotly_fig)
                    try:
                        os.remove(fig_file)
                    except OSError:
                        pass
            except Exception as exc:
                logger.warning("Figure conversion pipeline failed: %s", exc)
```

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/ -v --ignore=tests/test_integration_figures.py -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/matlab_mcp/jobs/executor.py
git commit -m "feat: implement figure extraction pipeline in executor._build_result"
```

---

## Chunk 6: Fixture Tests and Integration Tests

### Task 17: Create fixture-based tests

**Files:**
- Create: `tests/fixtures/matlab_figures/single_line.json`
- Create: `tests/fixtures/matlab_figures/subplot_2x1.json`
- Create: `tests/test_plotly_conversion_fixtures.py`

- [ ] **Step 1: Create fixture JSON files**

Create `tests/fixtures/matlab_figures/single_line.json`:

```json
{
  "schema_version": 1,
  "layout_type": "single",
  "background_color": [0.94, 0.94, 0.94],
  "axes": [
    {
      "grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1},
      "position": [0.13, 0.11, 0.775, 0.815],
      "title": {"text": "Sine Wave", "font_name": "Helvetica", "font_size": 14, "font_weight": "bold"},
      "xlabel": {"text": "x", "font_name": "Helvetica", "font_size": 12},
      "ylabel": {"text": "sin(x)", "font_name": "Helvetica", "font_size": 12},
      "xlim": [0, 6.28], "ylim": [-1, 1],
      "xgrid": true, "ygrid": true,
      "xdir": "normal", "ydir": "normal",
      "xtick": [0, 1.57, 3.14, 4.71, 6.28],
      "ytick": [-1, -0.5, 0, 0.5, 1],
      "xticklabels": null, "yticklabels": null,
      "tick_font": {"font_name": "Helvetica", "font_size": 10},
      "color": [1, 1, 1],
      "grid_color": [0.15, 0.15, 0.15], "grid_alpha": 0.15, "grid_line_style": "-",
      "legend": {"visible": false, "entries": [], "location": "best"},
      "children": [
        {
          "type": "line",
          "xdata": [0, 1.57, 3.14, 4.71, 6.28],
          "ydata": [0, 1, 0, -1, 0],
          "color": [0, 0.447, 0.741],
          "line_style": "-", "line_width": 2,
          "display_name": "sin(x)",
          "marker": "none", "marker_size": 6,
          "marker_face_color": "none", "marker_edge_color": "auto"
        }
      ]
    }
  ]
}
```

Create `tests/fixtures/matlab_figures/subplot_2x1.json`:

```json
{
  "schema_version": 1,
  "layout_type": "subplot",
  "background_color": [1, 1, 1],
  "grid": {"rows": 2, "cols": 1},
  "axes": [
    {
      "grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1},
      "position": [0.13, 0.58, 0.775, 0.34],
      "title": {"text": "Top", "font_name": "Helvetica", "font_size": 12, "font_weight": "normal"},
      "xlabel": {}, "ylabel": {},
      "xlim": [0, 10], "ylim": [0, 100],
      "xgrid": false, "ygrid": false,
      "xdir": "normal", "ydir": "normal",
      "xtick": null, "ytick": null,
      "xticklabels": null, "yticklabels": null,
      "tick_font": {"font_name": "Helvetica", "font_size": 10},
      "color": [1, 1, 1],
      "grid_color": [0.15, 0.15, 0.15], "grid_alpha": 0.15, "grid_line_style": "-",
      "legend": {"visible": false, "entries": [], "location": "best"},
      "children": [
        {
          "type": "bar",
          "xdata": [1, 2, 3, 4, 5],
          "ydata": [20, 40, 60, 80, 100],
          "face_color": [0, 0.447, 0.741],
          "edge_color": [0, 0, 0],
          "bar_width": 0.8,
          "display_name": "data"
        }
      ]
    },
    {
      "grid_index": {"row": 2, "col": 1, "rowspan": 1, "colspan": 1},
      "position": [0.13, 0.11, 0.775, 0.34],
      "title": {"text": "Bottom", "font_name": "Helvetica", "font_size": 12, "font_weight": "normal"},
      "xlabel": {}, "ylabel": {},
      "xlim": [0, 10], "ylim": [-1, 1],
      "xgrid": true, "ygrid": true,
      "xdir": "normal", "ydir": "normal",
      "xtick": null, "ytick": null,
      "xticklabels": null, "yticklabels": null,
      "tick_font": {"font_name": "Helvetica", "font_size": 10},
      "color": [1, 1, 1],
      "grid_color": [0.15, 0.15, 0.15], "grid_alpha": 0.15, "grid_line_style": "-",
      "legend": {"visible": false, "entries": [], "location": "best"},
      "children": [
        {
          "type": "line",
          "xdata": [0, 5, 10],
          "ydata": [0, 1, -1],
          "color": [0.85, 0.33, 0.1],
          "line_style": "--", "line_width": 1,
          "display_name": "",
          "marker": "none", "marker_size": 6,
          "marker_face_color": "none", "marker_edge_color": "auto"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Write fixture tests**

Create `tests/test_plotly_conversion_fixtures.py`:

```python
"""Fixture-based tests for the full MATLAB->Plotly conversion pipeline."""
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "matlab_figures"


def _load_and_convert(fixture_name: str) -> dict:
    from matlab_mcp.output.plotly_convert import load_plotly_json
    from matlab_mcp.output.plotly_style_mapper import convert_figure

    path = FIXTURES_DIR / fixture_name
    matlab_data = load_plotly_json(str(path))
    assert matlab_data is not None, f"Failed to load fixture {fixture_name}"
    return convert_figure(matlab_data)


class TestSingleLineFigure:
    def test_has_one_trace(self):
        result = _load_and_convert("single_line.json")
        assert len(result["data"]) == 1

    def test_trace_is_scatter_lines(self):
        result = _load_and_convert("single_line.json")
        trace = result["data"][0]
        assert trace["type"] == "scatter"
        assert trace["mode"] == "lines"

    def test_line_color_is_matlab_blue(self):
        result = _load_and_convert("single_line.json")
        assert result["data"][0]["line"]["color"] == "rgb(0, 114, 189)"

    def test_layout_has_title(self):
        result = _load_and_convert("single_line.json")
        assert result["layout"]["title"]["text"] == "Sine Wave"

    def test_layout_has_grid(self):
        result = _load_and_convert("single_line.json")
        assert result["layout"]["xaxis"]["showgrid"] is True

    def test_axis_range(self):
        result = _load_and_convert("single_line.json")
        assert result["layout"]["xaxis"]["range"] == [0, 6.28]
        assert result["layout"]["yaxis"]["range"] == [-1, 1]


class TestSubplotFigure:
    def test_has_two_traces(self):
        result = _load_and_convert("subplot_2x1.json")
        assert len(result["data"]) == 2

    def test_first_trace_is_bar(self):
        result = _load_and_convert("subplot_2x1.json")
        assert result["data"][0]["type"] == "bar"

    def test_second_trace_is_scatter(self):
        result = _load_and_convert("subplot_2x1.json")
        assert result["data"][1]["type"] == "scatter"

    def test_has_two_x_axes(self):
        result = _load_and_convert("subplot_2x1.json")
        assert "xaxis" in result["layout"]
        assert "xaxis2" in result["layout"]

    def test_axes_have_domains(self):
        result = _load_and_convert("subplot_2x1.json")
        assert "domain" in result["layout"]["xaxis"]
        assert "domain" in result["layout"]["xaxis2"]

    def test_second_trace_uses_axis2(self):
        result = _load_and_convert("subplot_2x1.json")
        assert result["data"][1]["xaxis"] == "x2"
        assert result["data"][1]["yaxis"] == "y2"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_plotly_conversion_fixtures.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/ tests/test_plotly_conversion_fixtures.py
git commit -m "test: add fixture-based plotly conversion tests"
```

---

### Task 18: Create integration test skeleton

**Files:**
- Create: `tests/test_integration_figures.py`

- [ ] **Step 1: Write integration tests (marked with @pytest.mark.matlab)**

Create `tests/test_integration_figures.py`:

```python
"""Integration tests for figure extraction — requires live MATLAB engine.

Run with: pytest tests/test_integration_figures.py -v -m matlab
"""
import pytest

pytestmark = pytest.mark.matlab


@pytest.fixture
def execute_and_get_figures():
    """Helper to execute MATLAB code via MCP and return figures."""
    # This fixture would be implemented when the MCP test harness is available
    pytest.skip("Requires live MATLAB MCP server")


class TestLineplotExtraction:
    def test_simple_line(self, execute_and_get_figures):
        figures = execute_and_get_figures(
            "x = 0:0.1:2*pi; plot(x, sin(x), 'r--', 'LineWidth', 2); title('Sine');"
        )
        assert len(figures) >= 1
        trace = figures[0]["data"][0]
        assert trace["type"] == "scatter"
        assert trace["line"]["dash"] == "dash"
        assert figures[0]["layout"]["title"]["text"] == "Sine"


class TestSubplotExtraction:
    def test_2x1_subplot(self, execute_and_get_figures):
        code = """
        subplot(2,1,1); plot(1:10); title('Top');
        subplot(2,1,2); bar(1:5); title('Bottom');
        """
        figures = execute_and_get_figures(code)
        assert len(figures) >= 1
        assert len(figures[0]["data"]) == 2
        assert "xaxis2" in figures[0]["layout"]
```

- [ ] **Step 2: Verify tests are skipped in normal runs**

Run: `pytest tests/test_integration_figures.py -v`
Expected: all tests SKIPPED

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_figures.py
git commit -m "test: add integration test skeleton for figure extraction (requires MATLAB)"
```

---

### Task 19: Register `conftest.py` marker

**Files:**
- Modify: `conftest.py` or `pyproject.toml`

- [ ] **Step 1: Register the `matlab` marker**

Check if there's a `conftest.py` at the project root or a `[tool.pytest.ini_options]` in `pyproject.toml`. Add:

```ini
[tool.pytest.ini_options]
markers = [
    "matlab: tests requiring a live MATLAB engine",
]
```

- [ ] **Step 2: Verify no warnings**

Run: `pytest tests/test_integration_figures.py -v`
Expected: no "PytestUnknownMarkWarning"

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "config: register pytest matlab marker"
```

---

### Task 20: Final verification — run all tests

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v --ignore=tests/test_integration_figures.py`
Expected: all tests PASS

- [ ] **Step 2: Run a quick smoke test with the live server (if available)**

Run the MATLAB MCP `execute_code` tool with a plot command and check if `figures` is populated in the response.

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: final cleanup for plotly visual fidelity feature"
```
