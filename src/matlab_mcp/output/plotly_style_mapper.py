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
        face_color = resolve_color(child.get("marker_face_color"), line_color)
        edge_color = resolve_color(child.get("marker_edge_color"), line_color)
        trace["marker"] = {
            "symbol": marker_symbol,
            "size": child.get("marker_size", 6),
            "color": face_color,
            "line": {"color": edge_color, "width": 1},
        }

    return trace


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


def convert_heatmap(child: dict, axis_suffix: str) -> dict:
    """Convert a MATLAB image child to a Plotly heatmap trace."""
    colormap = child.get("colormap", "gray")
    colorscale = COLORMAP_MAP.get(colormap, "Greys")

    return {
        "type": "heatmap",
        "z": child.get("cdata", []),
        "colorscale": colorscale,
        "xaxis": f"x{axis_suffix}",
        "yaxis": f"y{axis_suffix}",
    }


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
