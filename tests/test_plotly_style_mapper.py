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
        assert result["showlegend"] is False

    def test_line_empty_name_hides_legend(self):
        from matlab_mcp.output.plotly_style_mapper import convert_line
        child = {"xdata": [1], "ydata": [2], "color": [0,0,0], "display_name": "", "marker": "none"}
        result = convert_line(child, "")
        assert result["showlegend"] is False


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
        assert result["width"] == 0.8
        assert result["marker"]["color"] == "rgb(0, 114, 189)"
        assert result["marker"]["line"]["color"] == "rgb(0, 0, 0)"
        assert result["name"] == "Sales"

    def test_bar_auto_edge_color(self):
        from matlab_mcp.output.plotly_style_mapper import convert_bar

        child = {
            "xdata": [1], "ydata": [5],
            "face_color": [1, 0, 0], "edge_color": "auto",
            "bar_width": 0.8, "display_name": "",
        }
        result = convert_bar(child, "")
        assert result["marker"]["line"]["color"] == "rgb(255, 0, 0)"
        assert result["showlegend"] is False


class TestConvertScatterTrace:
    def test_basic_scatter(self):
        from matlab_mcp.output.plotly_style_mapper import convert_scatter_trace

        child = {
            "xdata": [1, 2, 3], "ydata": [4, 5, 6],
            "marker": "o", "size_data": 36,
            "marker_face_color": [0.85, 0.33, 0.1],
            "marker_edge_color": [0, 0, 0],
            "display_name": "Points",
        }
        result = convert_scatter_trace(child, "")

        assert result["type"] == "scatter"
        assert result["mode"] == "markers"
        assert result["marker"]["symbol"] == "circle"
        assert result["marker"]["size"] == 6  # sqrt(36)
        assert result["marker"]["color"] == "rgb(217, 84, 26)"
        assert result["name"] == "Points"

    def test_scatter_default_size(self):
        from matlab_mcp.output.plotly_style_mapper import convert_scatter_trace

        child = {"xdata": [1], "ydata": [2], "marker": "x",
                 "marker_face_color": [0,0,1], "marker_edge_color": "auto", "display_name": ""}
        result = convert_scatter_trace(child, "")
        assert result["marker"]["symbol"] == "x"
        assert result["marker"]["size"] == 6  # sqrt(36) default


class TestConvertSurface:
    def test_basic_surface(self):
        from matlab_mcp.output.plotly_style_mapper import convert_surface

        child = {
            "xdata": [[0, 1], [0, 1]], "ydata": [[0, 0], [1, 1]],
            "zdata": [[0, 1], [1, 0]], "colormap": "parula",
        }
        result = convert_surface(child, "")
        assert result["type"] == "surface"
        assert result["colorscale"] == "Viridis"

    def test_unknown_colormap_fallback(self):
        from matlab_mcp.output.plotly_style_mapper import convert_surface

        child = {"xdata": [[0]], "ydata": [[0]], "zdata": [[0]], "colormap": "unknown"}
        result = convert_surface(child, "")
        assert result["colorscale"] == "Viridis"


class TestConvertHeatmap:
    def test_basic_heatmap(self):
        from matlab_mcp.output.plotly_style_mapper import convert_heatmap

        child = {"cdata": [[0, 1], [1, 0]], "colormap": "gray"}
        result = convert_heatmap(child, "")
        assert result["type"] == "heatmap"
        assert result["z"] == [[0, 1], [1, 0]]
        assert result["colorscale"] == "Greys"


class TestConvertHistogramTrace:
    def test_basic_histogram(self):
        from matlab_mcp.output.plotly_style_mapper import convert_histogram_trace

        child = {
            "data": [1, 2, 2, 3, 3, 3],
            "face_color": [0, 0.447, 0.741], "edge_color": [1, 1, 1],
            "num_bins": None, "bin_edges": None,
        }
        result = convert_histogram_trace(child, "")
        assert result["type"] == "histogram"
        assert result["x"] == [1, 2, 2, 3, 3, 3]
        assert result["marker"]["color"] == "rgb(0, 114, 189)"

    def test_histogram_with_bin_edges(self):
        from matlab_mcp.output.plotly_style_mapper import convert_histogram_trace

        child = {"data": [1,2,3], "face_color": [1,0,0], "edge_color": [0,0,0],
                 "bin_edges": [0.5, 1.5, 2.5, 3.5]}
        result = convert_histogram_trace(child, "")
        assert result["xbins"]["start"] == 0.5
        assert result["xbins"]["end"] == 3.5
        assert result["xbins"]["size"] == 1.0


class TestConvertPatch:
    def test_basic_patch(self):
        from matlab_mcp.output.plotly_style_mapper import convert_patch

        child = {
            "xdata": [0, 1, 1, 0], "ydata": [0, 0, 1, 1],
            "face_color": [0.8, 0.9, 1.0], "face_alpha": 0.3,
            "edge_color": "none", "display_name": "Band",
        }
        result = convert_patch(child, "")

        assert result["type"] == "scatter"
        assert result["fill"] == "toself"
        assert result["x"] == [0, 1, 1, 0, 0]  # closed polygon
        assert result["y"] == [0, 0, 1, 1, 0]
        assert "rgba" in result["fillcolor"]
        assert result["name"] == "Band"
        assert result["line"]["color"] == "rgba(0,0,0,0)"
