"""Fixture-based tests for the full MATLAB->Plotly conversion pipeline."""
from pathlib import Path


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
