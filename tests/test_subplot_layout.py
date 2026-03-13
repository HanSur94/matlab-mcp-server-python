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
        assert result[0]["x"][0] < 0.1
        assert result[0]["y"][0] > 0.4
        assert result[3]["x"][1] > 0.9
        assert result[3]["y"][0] < 0.1

    def test_spanning_tile(self):
        from matlab_mcp.output.plotly_style_mapper import compute_domains
        grid = {"rows": 2, "cols": 3}
        axes = [{"grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 2}}]
        result = compute_domains(grid, axes)
        assert result[0]["x"][1] > 0.6
        assert result[0]["x"][1] < 0.7

    def test_domains_clamped(self):
        from matlab_mcp.output.plotly_style_mapper import compute_domains
        grid = {"rows": 1, "cols": 1}
        axes = [{"grid_index": {"row": 1, "col": 1, "rowspan": 1, "colspan": 1}}]
        result = compute_domains(grid, axes)
        assert all(0 <= v <= 1 for v in result[0]["x"])
        assert all(0 <= v <= 1 for v in result[0]["y"])
