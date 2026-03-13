"""Integration tests for figure extraction — requires live MATLAB engine.

Run with: pytest tests/test_integration_figures.py -v -m matlab
"""
import pytest

pytestmark = pytest.mark.matlab


@pytest.fixture
def execute_and_get_figures():
    """Helper to execute MATLAB code via MCP and return figures."""
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
