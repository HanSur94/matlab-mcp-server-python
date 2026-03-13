# Plotly Visual Fidelity Conversion Layer

**Date:** 2026-03-13
**Status:** Draft (rev 4)

## Problem

The MATLAB MCP server converts MATLAB figures to Plotly JSON for client-side rendering, but the current conversion is minimal — only basic data and line color are extracted. The resulting Plotly charts look nothing like the original MATLAB figures. FastPlot figures (with themes, bands, thresholds, tiled dashboards) lose all styling.

## Goal

Full visual fidelity: Plotly charts should look as close as possible to the original MATLAB figures, including FastPlot-styled figures. Subplot and tiled layouts must be reconstructable.

## Architecture

Split responsibility between MATLAB (raw property extraction) and Python (Plotly mapping):

```
MATLAB code executes
  -> figures exist in workspace
  -> executor calls mcp_extract_props() per figure
  -> raw JSON (MATLAB properties, no Plotly keys) written to temp dir
  -> Python loads JSON (plotly_convert.py)
  -> Python maps to Plotly (plotly_style_mapper.py)
  -> Plotly JSON attached to response.figures[]
  -> client renders with Plotly.newPlot()
```

### Why split?

- MATLAB is best at extracting its own figure properties via handle graphics API
- Python is better for Plotly-specific mapping logic — easier to test, iterate, and maintain
- Updating mappings doesn't require touching MATLAB code

## MATLAB Property Extractor (`mcp_extract_props.m`)

Replaces the current `mcp_fig2plotly.m`. Outputs raw MATLAB properties with no Plotly-specific formatting.

### Layout Detection

Auto-detects three layout types:

1. **`tiledlayout`** (R2019b+) — reads `GridSize`, `TileSpan`, `Layout.Tile` from the tiledlayout object
2. **`subplot`** — multiple axes without tiledlayout; grid inferred by clustering axes `Position` values
3. **`single`** — one axes

### Output JSON Structure

```json
{
  "schema_version": 1,
  "layout_type": "subplot | tiledlayout | single",
  "background_color": [0.94, 0.94, 0.94],
  "grid": {
    "rows": 2,
    "cols": 3,
    "row_heights": [0.5, 0.5],
    "col_widths": [0.33, 0.33, 0.33]
  },
  "axes": [
    {
      "grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 2},
      "position": [0.05, 0.55, 0.62, 0.4],
      "title": {
        "text": "My Plot",
        "font_name": "Helvetica",
        "font_size": 14,
        "font_weight": "bold"
      },
      "xlabel": {"text": "Time", "font_name": "Helvetica", "font_size": 12},
      "ylabel": {"text": "Amplitude", "font_name": "Helvetica", "font_size": 12},
      "xlim": [0, 10],
      "ylim": [-1, 1],
      "xgrid": true,
      "ygrid": true,
      "xdir": "normal",
      "ydir": "normal",
      "xtick": [0, 2, 4, 6, 8, 10],
      "ytick": [-1, -0.5, 0, 0.5, 1],
      "xticklabels": null,
      "yticklabels": null,
      "tick_font": {"font_name": "Helvetica", "font_size": 10},
      "color": [1, 1, 1],
      "grid_color": [0.15, 0.15, 0.15],
      "grid_alpha": 0.15,
      "grid_line_style": "-",
      "legend": {
        "visible": true,
        "entries": ["sin(x)", "cos(x)"],
        "location": "northeast"
      },
      "children": [
        {
          "type": "line",
          "xdata": [0, 1, 2],
          "ydata": [0, 0.84, 0.91],
          "color": [0, 0.447, 0.741],
          "line_style": "-",
          "line_width": 2,
          "display_name": "sin(x)",
          "marker": "none",
          "marker_size": 6,
          "marker_face_color": "none",
          "marker_edge_color": "auto"
        },
        {
          "type": "bar",
          "xdata": [1, 2, 3],
          "ydata": [10, 20, 30],
          "face_color": [0, 0.447, 0.741],
          "edge_color": [0, 0, 0],
          "bar_width": 0.8,
          "display_name": "Sales"
        },
        {
          "type": "scatter",
          "xdata": [1, 2, 3],
          "ydata": [4, 5, 6],
          "marker": "o",
          "size_data": 36,
          "marker_face_color": [0.85, 0.33, 0.1],
          "marker_edge_color": [0, 0, 0],
          "display_name": "Points"
        },
        {
          "type": "surface",
          "xdata": [[0, 1], [0, 1]],
          "ydata": [[0, 0], [1, 1]],
          "zdata": [[0, 1], [1, 0]],
          "colormap": "parula"
        },
        {
          "type": "image",
          "cdata": [[0, 1], [1, 0]],
          "colormap": "gray"
        },
        {
          "type": "histogram",
          "data": [1, 2, 2, 3, 3, 3],
          "face_color": [0, 0.447, 0.741],
          "edge_color": [1, 1, 1],
          "num_bins": null,
          "bin_edges": null
        },
        {
          "type": "patch",
          "xdata": [0, 1, 1, 0],
          "ydata": [0, 0, 1, 1],
          "face_color": [0.8, 0.9, 1.0],
          "face_alpha": 0.3,
          "edge_color": "none",
          "display_name": "Band"
        }
      ]
    }
  ]
}
```

### Extracted Properties Per Type

| Type | Properties |
|---|---|
| **line** | xdata, ydata, color, line_style, line_width, display_name, marker, marker_size, marker_face_color, marker_edge_color |
| **bar** | xdata, ydata, face_color, edge_color, bar_width, display_name |
| **scatter** | xdata, ydata, marker, size_data (MATLAB `SizeData`, area in pt^2), marker_face_color, marker_edge_color, display_name |
| **surface** | xdata, ydata, zdata, colormap |
| **image** | cdata, colormap |
| **histogram** | data, face_color, edge_color, num_bins, bin_edges |
| **patch** | xdata, ydata, face_color, face_alpha, edge_color, display_name |

### Axes Properties

title, xlabel, ylabel, xlim, ylim, xgrid, ygrid, xdir, ydir, xtick, ytick, xticklabels, yticklabels, tick_font, color (background), grid_color, grid_alpha, grid_line_style (MATLAB `GridLineStyle`), legend, position, grid_index.

**Note on size properties:** MATLAB `scatter()` objects use `SizeData` (area in points-squared), while `line` objects use `MarkerSize` (diameter in points). The extractor must use the correct property for each type. The Python mapper converts `size_data` to Plotly marker size via `sqrt(size_data)` to approximate diameter.

## Python Style Mapper (`plotly_style_mapper.py`)

New module in `src/matlab_mcp/output/`. Converts raw MATLAB JSON to Plotly figure dicts.

### Mapping Tables

```python
LINE_STYLE_MAP = {
    "-": "solid",
    "--": "dash",
    ":": "dot",
    "-.": "dashdot",
}

MARKER_MAP = {
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

LEGEND_LOCATION_MAP = {
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
# Fallback: unmapped locations default to {} (Plotly auto-placement).
# Note: MATLAB's "best" places the legend in the least cluttered corner.
# Plotly has no equivalent algorithm — "best" maps to Plotly's default
# (top-right inside plot area).

COLORMAP_MAP = {
    "parula": "Viridis",   # approximation — parula is perceptually uniform like Viridis
    "jet": "Jet",
    "hsv": "HSV",
    "hot": "Hot",
    "cool": "Bluered",     # approximation — cool is cyan-to-magenta, Bluered is blue-to-red
    "gray": "Greys",
    "bone": "Greys",       # approximation — bone has a blue tint that Greys lacks
    "copper": "Copper",
    "turbo": "Turbo",
}
# Note: some mappings are approximations. For exact fidelity, a future
# enhancement could extract the full Nx3 colormap matrix from MATLAB
# and emit a custom Plotly colorscale.

GRID_STYLE_MAP = {
    "-": "solid",
    "--": "dash",
    ":": "dot",
    "-.": "dashdot",
    "none": None,
}
```

### Converter Functions

| Function | Input | Output |
|---|---|---|
| `convert_figure(matlab_fig)` | Full extracted JSON | Complete Plotly figure dict |
| `convert_axes(matlab_axes, axis_index)` | Single axes dict | `(list[trace], layout_fragment)` |
| `convert_line(child, axis_suffix)` | Line child dict | Plotly scatter trace |
| `convert_bar(child, axis_suffix)` | Bar child dict | Plotly bar trace |
| `convert_scatter_trace(child, axis_suffix)` | Scatter child dict | Plotly scatter trace |
| `convert_surface(child, axis_suffix)` | Surface child dict | Plotly surface trace |
| `convert_heatmap(child, axis_suffix)` | Image child dict | Plotly heatmap trace |
| `convert_histogram_trace(child, axis_suffix)` | Histogram child dict | Plotly histogram trace |
| `convert_patch(child, axis_suffix)` | Patch child dict | Plotly scatter trace with fill |
| `convert_layout(matlab_fig)` | Full extracted JSON | Plotly layout dict |
| `compute_domains(grid, axes_list)` | Grid info + axes | Per-axis domain pairs |
| `rgb_to_css(rgb_array)` | `[0, 0.447, 0.741]` | `"rgb(0, 114, 189)"` |
| `resolve_color(value, fallback)` | `"auto"` / `"none"` / RGB | CSS color string or None. `"auto"` returns `fallback` (caller passes the contextually correct color, e.g. `face_color` for bar edges). `"none"` returns `"rgba(0,0,0,0)"`. |

### Subplot Domain Computation

For each axes, domains are computed from grid position:

For `layout_type == "single"`, domain computation is skipped — no `domain` keys are emitted, and Plotly uses its full-area default.

```python
def compute_domains(grid, axes_list):
    if grid is None:  # single-axes case
        return [{"x": [0, 1], "y": [0, 1]}]
    rows, cols = grid["rows"], grid["cols"]
    gap_x, gap_y = 0.04, 0.06  # inter-subplot padding

    for ax in axes_list:
        gi = ax["grid_index"]
        col_start = (gi["col"] - 1) / cols
        col_end = (gi["col"] - 1 + gi["colspan"]) / cols
        row_start = (gi["row"] - 1) / rows
        row_end = (gi["row"] - 1 + gi["rowspan"]) / rows

        x_domain = [max(0, col_start + gap_x/2), min(1, col_end - gap_x/2)]
        y_domain = [max(0, 1 - row_end + gap_y/2), min(1, 1 - row_start - gap_y/2)]
        # Clamp to [0, 1] to handle spanning tiles that exceed grid bounds
        domains.append({"x": x_domain, "y": y_domain})
    return domains  # list parallel to axes_list, used to set xaxis<n>/yaxis<n> domain
```

### Font Mapping

MATLAB font names map directly with a web-safe fallback stack:

```python
def map_font(font_name):
    # Quote names containing spaces (e.g. "Times New Roman" -> '"Times New Roman"')
    if " " in font_name:
        font_name = f'"{font_name}"'
    return f"{font_name}, Arial, sans-serif"
```

## Integration with Executor (`executor.py`) and Tool Layer (`tools/core.py`)

### Where the Pipeline Lives: `executor._build_result`

The figure extraction pipeline belongs in `executor._build_result()`, which already has a placeholder (`figures: list = []` with a `plotly_conversion` config guard).

### Wiring `temp_dir` Through the Call Chain

Currently `temp_dir` is retrieved in `server.py` (`state._get_temp_dir(session_id)`) but never passed forward. Three files need changes:

1. **`server.py`** — pass `temp_dir=temp_dir` to `execute_code_impl()` (the variable is already in scope)
2. **`tools/core.py`** — add `temp_dir: Optional[str] = None` parameter to `execute_code_impl`, forward it to `executor.execute(session_id=session_id, code=code, temp_dir=temp_dir)`
3. **`executor.py`** — `execute()` already accepts `temp_dir: Optional[str] = None`; no signature change needed, but `_build_result` uses it for the figure pipeline

### `plotly_convert.py` Role

`plotly_convert.py` remains a **generic JSON file loader** — it reads any JSON dict from disk. It does NOT do Plotly-specific transformations. The function `load_plotly_json` is kept as-is (name unchanged for backward compatibility, docstring updated to reference `mcp_extract_props.m`). All Plotly-specific mapping is in `plotly_style_mapper.py`.

The loader validates `schema_version`: if `schema_version` is absent or greater than `SUPPORTED_SCHEMA_VERSION = 1`, `load_plotly_json` returns `None` and logs a warning (consistent with existing error handling pattern).

### Figure Detection & Extraction

After MATLAB code execution completes, the executor runs:

```matlab
figs = findobj(0, 'Type', 'figure');
for i = 1:length(figs)
    mcp_extract_props(figs(i), '<temp_dir>/<job_id>_fig<i>.json');
    close(figs(i));
end
```

### Python Pipeline

```python
# In executor, after code execution:
import glob
from matlab_mcp.output.plotly_convert import load_plotly_json
from matlab_mcp.output.plotly_style_mapper import convert_figure

fig_files = sorted(glob.glob(f"{temp_dir}/{job_id}_fig*.json"))
figures = []
for fig_file in fig_files:
    matlab_data = load_plotly_json(fig_file)
    if matlab_data:
        plotly_fig = convert_figure(matlab_data)
        figures.append(plotly_fig)
    os.remove(fig_file)
```

### Response Format

```json
{
  "status": "completed",
  "job_id": "j-abc123",
  "text": "...",
  "figures": [
    {
      "data": [
        {"type": "scatter", "mode": "lines", "x": [], "y": [],
         "line": {"color": "rgb(0,114,189)", "width": 2, "dash": "solid"},
         "marker": {"symbol": "circle", "size": 6},
         "name": "sin(x)", "xaxis": "x", "yaxis": "y"}
      ],
      "layout": {
        "title": {"text": "My Plot", "font": {"family": "Helvetica, Arial, sans-serif", "size": 14}},
        "xaxis": {"title": {"text": "Time"}, "range": [0, 10], "showgrid": true,
                  "gridcolor": "rgba(38,38,38,0.15)", "griddash": "solid",
                  "domain": [0.0, 0.48]},
        "xaxis2": {"domain": [0.52, 1.0]},
        "yaxis": {"domain": [0.0, 1.0]},
        "yaxis2": {"domain": [0.0, 1.0], "anchor": "x2"},
        "plot_bgcolor": "rgb(255,255,255)",
        "paper_bgcolor": "rgb(240,240,240)",
        "legend": {"x": 1, "y": 1, "xanchor": "right", "yanchor": "top"},
        "showlegend": true
      }
    }
  ]
}
```

## FastPlot-Specific Elements

| FastPlot Element | MATLAB Object | Plotly Mapping |
|---|---|---|
| Bands/shadings | `patch` | `scatter` trace with `fill: "toself"`, `fillcolor` with alpha |
| Threshold lines | `line` (constant value) | Converted as regular `scatter` traces (mode=`lines`). Post-render, threshold lines are indistinguishable from data lines in MATLAB's handle graphics — no reliable detection heuristic exists. They will look correct visually. |
| Violation markers | `scatter` | `scatter` trace with `mode: "markers"` |
| Tiled dashboard | Multiple axes with grid positions | Plotly subplots via `domain` |
| Theme colors | Applied to axes/line properties | Captured as raw property values |
| Linked zoom/pan | Runtime XLim listener | Out of scope (runtime behavior) |

FastPlot figures are standard MATLAB figures after `render()`, so the extractor captures theme-applied properties automatically.

**Note on FastPlotFigure:** FastPlotFigure does NOT use MATLAB's `tiledlayout`. It computes axes positions manually via `computeTilePosition()`. These figures will always be detected as `subplot` layout type, with the grid inferred from the axes `Position` values. The position-clustering algorithm must handle FastPlot's uniform grids with configurable gaps and spans.

## Testing

### Unit Tests (`test_plotly_style_mapper.py`)

- Mapping tables: line styles, markers, legend locations, colormaps, grid styles
- `rgb_to_css`: known conversions, edge cases (0, 1, out-of-range)
- `resolve_color`: `"auto"`, `"none"`, RGB arrays
- Each `convert_*` function with representative MATLAB input
- `compute_domains`: single axes, 2x2 grid, spanning tiles
- Edge cases: empty axes, missing properties, unknown types

### Layout Tests (`test_subplot_layout.py`)

- Single axes -> no subplot logic
- 2x2 grid -> 4 domain pairs
- Spanning tile (colspan=2) -> wider domain
- Irregular grid inferred from positions

### Integration Tests (`test_integration_figures.py`)

These tests require a live MATLAB engine and are marked with `@pytest.mark.matlab` — excluded from standard CI runs.

- Execute styled MATLAB plot -> verify Plotly JSON has correct styles
- Each plot type: line, bar, scatter, surface, heatmap, histogram
- Patch/band extraction
- Multi-subplot figure
- Figure with legend and custom fonts

### Existing Tests (`test_output.py`) — Required Updates

The existing `test_load_valid_json` test passes a dict without `schema_version`. After the `plotly_convert.py` change, this would return `None` and fail. Required changes:
- Update `test_load_valid_json` fixture to include `"schema_version": 1`
- Add `test_load_missing_schema_version` — verify returns `None` with warning log
- Add `test_load_future_schema_version` — verify `schema_version: 99` returns `None` with warning log
- Add `test_load_schema_version_1` — verify valid v1 JSON loads successfully

### Fixture-Based Tests (`test_plotly_conversion_fixtures.py`)

Pre-recorded MATLAB JSON fixtures in `tests/fixtures/matlab_figures/` enable CI testing without MATLAB:

- One fixture per plot type with known expected Plotly output
- Subplot/tiled layout fixtures
- Tests verify the full `load_plotly_json` -> `convert_figure` pipeline against expected output

## Scope

### In Scope

- All 7 plot types: line, bar, scatter, surface, image/heatmap, histogram, patch
- All style properties: colors, fonts, line styles, markers, widths, opacity
- Layout: subplots, tiledlayout, FastPlotFigure grids
- Axes: ranges, grid, ticks, labels, direction, background
- Legend: entries, position
- Figure background color
- Colormap mapping

### Out of Scope

- Runtime behaviors (linked zoom/pan, live polling, downsampling)
- FastPlot's pyramid cache and data store
- Interactive callbacks and animations
- 3D camera angles (surface plots use Plotly defaults)
- Custom MATLAB UI components (uicontrol, uipanel)

## Files Changed

| File | Action |
|---|---|
| `src/matlab_mcp/matlab_helpers/mcp_fig2plotly.m` | Rewrite -> rename to `mcp_extract_props.m` |
| `src/matlab_mcp/output/plotly_style_mapper.py` | New |
| `pyproject.toml` | Modify (add `plotly>=5.9.0` to dependencies) |
| `src/matlab_mcp/output/plotly_convert.py` | Modify (add schema_version validation, update docstring) |
| `src/matlab_mcp/jobs/executor.py` | Modify (implement figure extraction + conversion in `_build_result`) |
| `src/matlab_mcp/tools/core.py` | Modify (add `temp_dir` param to `execute_code_impl`, forward to executor) |
| `src/matlab_mcp/server.py` | Modify (pass `temp_dir` to `execute_code_impl`) |
| `tests/test_output.py` | Modify (update for new JSON schema) |
| `tests/test_plotly_style_mapper.py` | New |
| `tests/test_subplot_layout.py` | New |
| `tests/test_plotly_conversion_fixtures.py` | New (fixture-based CI tests) |
| `tests/test_integration_figures.py` | New (requires MATLAB, `@pytest.mark.matlab`) |
| `tests/fixtures/matlab_figures/` | New (pre-recorded MATLAB JSON fixtures) |
