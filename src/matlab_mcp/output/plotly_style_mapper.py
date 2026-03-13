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
    else:
        trace["showlegend"] = False

    return trace


# ---------------------------------------------------------------------------
# Child type dispatcher
# ---------------------------------------------------------------------------

_CHILD_CONVERTERS: dict[str, Any] = {
    "line": convert_line,
    "bar": convert_bar,
    "scatter": convert_scatter_trace,
    "surface": convert_surface,
    "image": convert_heatmap,
    "histogram": convert_histogram_trace,
    "patch": convert_patch,
}


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
    tick_font_dict: dict[str, Any] = {}
    if tick_font.get("font_name"):
        tick_font_dict["family"] = map_font(tick_font["font_name"])
    if tick_font.get("font_size"):
        tick_font_dict["size"] = tick_font["font_size"]

    def _label_dict(label_data: Optional[dict]) -> dict:
        if not label_data or not label_data.get("text"):
            return {}
        result: dict[str, Any] = {"text": label_data["text"]}
        font: dict[str, Any] = {}
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
