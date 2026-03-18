"""Tests for custom tool loading and handler generation."""
from __future__ import annotations

import inspect
from typing import Any

import pytest

from matlab_mcp.tools.custom import (
    CustomToolDef,
    CustomToolParam,
    _TYPE_MAP,
    load_custom_tools,
    make_custom_tool_handler,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class MockExecutor:
    """Captures the most recent ``execute`` call for assertions."""

    def __init__(self) -> None:
        self.last_code: str | None = None
        self.last_session_id: str | None = None

    async def execute(self, session_id: str, code: str) -> dict[str, str]:
        self.last_code = code
        self.last_session_id = session_id
        return {"status": "completed"}


class MockServerState:
    """Minimal stand-in for the real server state object."""

    def __init__(self) -> None:
        self.session_id = "test-session"
        self.executor = MockExecutor()


# Sentinel used where a real ``Context`` would be passed by FastMCP.
_FAKE_CTX = object()


# ---------------------------------------------------------------------------
# _TYPE_MAP
# ---------------------------------------------------------------------------

class TestTypeMap:
    """Verify the string → Python type mapping table."""

    @pytest.mark.parametrize(
        "key, expected",
        [
            ("str", str),
            ("string", str),
            ("int", int),
            ("integer", int),
            ("float", float),
            ("number", float),
            ("bool", bool),
            ("boolean", bool),
            ("list", list),
            ("dict", dict),
            ("any", Any),
        ],
    )
    def test_type_map_entries(self, key: str, expected: type) -> None:
        assert _TYPE_MAP[key] is expected

    def test_type_map_length(self) -> None:
        assert len(_TYPE_MAP) == 11


# ---------------------------------------------------------------------------
# CustomToolParam model
# ---------------------------------------------------------------------------

class TestCustomToolParam:
    def test_defaults(self) -> None:
        p = CustomToolParam(name="x")
        assert p.name == "x"
        assert p.type == "str"
        assert p.required is True
        assert p.default is None

    def test_explicit_values(self) -> None:
        p = CustomToolParam(name="n", type="int", required=False, default=42)
        assert p.name == "n"
        assert p.type == "int"
        assert p.required is False
        assert p.default == 42


# ---------------------------------------------------------------------------
# CustomToolDef model
# ---------------------------------------------------------------------------

class TestCustomToolDef:
    def test_defaults(self) -> None:
        t = CustomToolDef(name="my_tool", matlab_function="myFunc")
        assert t.name == "my_tool"
        assert t.matlab_function == "myFunc"
        assert t.description == ""
        assert t.parameters == []
        assert t.returns == ""

    def test_with_parameters(self) -> None:
        t = CustomToolDef(
            name="add",
            matlab_function="add_numbers",
            description="Add two numbers",
            parameters=[
                CustomToolParam(name="a", type="float"),
                CustomToolParam(name="b", type="float"),
            ],
            returns="sum of a and b",
        )
        assert len(t.parameters) == 2
        assert t.parameters[0].name == "a"
        assert t.returns == "sum of a and b"


# ---------------------------------------------------------------------------
# load_custom_tools
# ---------------------------------------------------------------------------

class TestLoadCustomTools:
    def test_missing_file_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        result = load_custom_tools(str(tmp_path / "nonexistent.yaml"))
        assert result == []

    def test_valid_config(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "tools.yaml"
        config.write_text(
            "tools:\n"
            "  - name: greet\n"
            "    matlab_function: greet\n"
            "    description: Say hello\n"
            "    parameters:\n"
            "      - name: who\n"
            "        type: str\n"
            "        required: true\n"
            "    returns: greeting string\n"
        )
        tools = load_custom_tools(str(config))
        assert len(tools) == 1
        assert tools[0].name == "greet"
        assert tools[0].matlab_function == "greet"
        assert tools[0].description == "Say hello"
        assert len(tools[0].parameters) == 1
        assert tools[0].parameters[0].name == "who"
        assert tools[0].returns == "greeting string"

    def test_multiple_tools(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "tools.yaml"
        config.write_text(
            "tools:\n"
            "  - name: tool_a\n"
            "    matlab_function: funcA\n"
            "  - name: tool_b\n"
            "    matlab_function: funcB\n"
        )
        tools = load_custom_tools(str(config))
        assert len(tools) == 2
        assert tools[0].name == "tool_a"
        assert tools[1].name == "tool_b"

    def test_invalid_yaml_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "bad.yaml"
        config.write_text(":\n  - :\n  bad: [unclosed")
        tools = load_custom_tools(str(config))
        assert tools == []

    def test_no_tools_key_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "empty.yaml"
        config.write_text("other_key: value\n")
        tools = load_custom_tools(str(config))
        assert tools == []

    def test_empty_tools_key_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "empty_tools.yaml"
        config.write_text("tools:\n")
        tools = load_custom_tools(str(config))
        assert tools == []

    def test_skips_invalid_keeps_valid(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "mixed.yaml"
        config.write_text(
            "tools:\n"
            "  - name: good_tool\n"
            "    matlab_function: goodFunc\n"
            "  - invalid_field_only: true\n"  # missing required 'name' and 'matlab_function'
            "  - name: another_good\n"
            "    matlab_function: anotherFunc\n"
        )
        tools = load_custom_tools(str(config))
        assert len(tools) == 2
        assert tools[0].name == "good_tool"
        assert tools[1].name == "another_good"

    def test_empty_file_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        config = tmp_path / "empty.yaml"
        config.write_text("")
        tools = load_custom_tools(str(config))
        assert tools == []


# ---------------------------------------------------------------------------
# make_custom_tool_handler – metadata
# ---------------------------------------------------------------------------

class TestMakeCustomToolHandlerMetadata:
    def test_handler_name(self) -> None:
        tool_def = CustomToolDef(name="my_tool", matlab_function="myFunc")
        handler = make_custom_tool_handler(tool_def, MockServerState())
        assert handler.__name__ == "my_tool"

    def test_handler_doc_from_description(self) -> None:
        tool_def = CustomToolDef(
            name="my_tool",
            matlab_function="myFunc",
            description="Does something useful",
        )
        handler = make_custom_tool_handler(tool_def, MockServerState())
        assert handler.__doc__ == "Does something useful"

    def test_handler_doc_fallback(self) -> None:
        tool_def = CustomToolDef(name="my_tool", matlab_function="myFunc")
        handler = make_custom_tool_handler(tool_def, MockServerState())
        assert handler.__doc__ == "Custom tool: my_tool"

    def test_handler_is_coroutine(self) -> None:
        tool_def = CustomToolDef(name="my_tool", matlab_function="myFunc")
        handler = make_custom_tool_handler(tool_def, MockServerState())
        assert inspect.iscoroutinefunction(handler)

    def test_handler_signature_ctx_only(self) -> None:
        tool_def = CustomToolDef(name="my_tool", matlab_function="myFunc")
        handler = make_custom_tool_handler(tool_def, MockServerState())
        sig = inspect.signature(handler)
        param_names = list(sig.parameters.keys())
        assert param_names == ["ctx"]
        assert sig.return_annotation is dict

    def test_handler_signature_with_params(self) -> None:
        tool_def = CustomToolDef(
            name="calc",
            matlab_function="calculate",
            parameters=[
                CustomToolParam(name="x", type="float"),
                CustomToolParam(name="label", type="str", required=False, default="result"),
            ],
        )
        handler = make_custom_tool_handler(tool_def, MockServerState())
        sig = inspect.signature(handler)
        param_names = list(sig.parameters.keys())
        assert param_names == ["ctx", "x", "label"]

        # Required param has no default
        assert sig.parameters["x"].default is inspect.Parameter.empty
        assert sig.parameters["x"].annotation is float

        # Optional param carries its default
        assert sig.parameters["label"].default == "result"
        assert sig.parameters["label"].annotation is str

    def test_handler_signature_bool_param(self) -> None:
        tool_def = CustomToolDef(
            name="toggle",
            matlab_function="setFlag",
            parameters=[
                CustomToolParam(name="flag", type="boolean"),
            ],
        )
        handler = make_custom_tool_handler(tool_def, MockServerState())
        sig = inspect.signature(handler)
        assert sig.parameters["flag"].annotation is bool


# ---------------------------------------------------------------------------
# make_custom_tool_handler – MATLAB code generation
# ---------------------------------------------------------------------------

class TestMakeCustomToolHandlerExecution:
    @pytest.mark.asyncio
    async def test_no_args(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(name="ping", matlab_function="pingServer")
        handler = make_custom_tool_handler(tool_def, state)

        result = await handler(_FAKE_CTX)

        assert result == {"status": "completed"}
        assert state.executor.last_code == "pingServer()"
        assert state.executor.last_session_id == "test-session"

    @pytest.mark.asyncio
    async def test_string_arg(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="greet",
            matlab_function="greet",
            parameters=[CustomToolParam(name="who", type="str")],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, who="world")

        assert state.executor.last_code == "greet('world')"

    @pytest.mark.asyncio
    async def test_string_arg_escapes_single_quotes(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="greet",
            matlab_function="greet",
            parameters=[CustomToolParam(name="who", type="str")],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, who="it's a test")

        assert state.executor.last_code == "greet('it''s a test')"

    @pytest.mark.asyncio
    async def test_numeric_int_arg(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="square",
            matlab_function="square",
            parameters=[CustomToolParam(name="n", type="int")],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, n=7)

        assert state.executor.last_code == "square(7)"

    @pytest.mark.asyncio
    async def test_numeric_float_arg(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="scale",
            matlab_function="scaleValue",
            parameters=[CustomToolParam(name="factor", type="float")],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, factor=3.14)

        assert state.executor.last_code == "scaleValue(3.14)"

    @pytest.mark.asyncio
    async def test_bool_true_arg(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="toggle",
            matlab_function="setFlag",
            parameters=[CustomToolParam(name="flag", type="bool")],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, flag=True)

        assert state.executor.last_code == "setFlag(true)"

    @pytest.mark.asyncio
    async def test_bool_false_arg(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="toggle",
            matlab_function="setFlag",
            parameters=[CustomToolParam(name="flag", type="bool")],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, flag=False)

        assert state.executor.last_code == "setFlag(false)"

    @pytest.mark.asyncio
    async def test_multiple_mixed_args(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="create",
            matlab_function="createObject",
            parameters=[
                CustomToolParam(name="name", type="string"),
                CustomToolParam(name="count", type="integer"),
                CustomToolParam(name="verbose", type="boolean"),
            ],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, name="widget", count=5, verbose=True)

        assert state.executor.last_code == "createObject('widget', 5, true)"

    @pytest.mark.asyncio
    async def test_optional_param_uses_default(self) -> None:
        state = MockServerState()
        tool_def = CustomToolDef(
            name="fetch",
            matlab_function="fetchData",
            parameters=[
                CustomToolParam(name="url", type="str"),
                CustomToolParam(name="timeout", type="int", required=False, default=30),
            ],
        )
        handler = make_custom_tool_handler(tool_def, state)

        # Call without providing the optional 'timeout'
        await handler(_FAKE_CTX, url="http://example.com")

        assert state.executor.last_code == "fetchData('http://example.com', 30)"

    @pytest.mark.asyncio
    async def test_session_id_fallback(self) -> None:
        """When server_state has no session_id attribute, falls back to 'default'."""
        state = MockServerState()
        del state.session_id  # remove the attribute

        tool_def = CustomToolDef(name="ping", matlab_function="pingServer")
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX)

        assert state.executor.last_session_id == "default"

    @pytest.mark.asyncio
    async def test_positional_args(self) -> None:
        """Handler accepts tool parameters as positional arguments too."""
        state = MockServerState()
        tool_def = CustomToolDef(
            name="add",
            matlab_function="addNums",
            parameters=[
                CustomToolParam(name="a", type="number"),
                CustomToolParam(name="b", type="number"),
            ],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, 1.5, 2.5)

        assert state.executor.last_code == "addNums(1.5, 2.5)"

    @pytest.mark.asyncio
    async def test_unknown_type_treated_as_string(self) -> None:
        """A parameter type not in _TYPE_MAP falls back to str (quoted)."""
        state = MockServerState()
        tool_def = CustomToolDef(
            name="custom",
            matlab_function="doSomething",
            parameters=[
                CustomToolParam(name="data", type="unknowntype"),
            ],
        )
        handler = make_custom_tool_handler(tool_def, state)

        await handler(_FAKE_CTX, data="hello")

        # Unknown type resolves to str in _TYPE_MAP.get(..., str), so the value
        # goes through the string branch and gets quoted.
        assert state.executor.last_code == "doSomething('hello')"

    @pytest.mark.asyncio
    async def test_return_value_from_executor(self) -> None:
        """Handler returns whatever the executor returns."""
        state = MockServerState()
        tool_def = CustomToolDef(name="ping", matlab_function="pingServer")
        handler = make_custom_tool_handler(tool_def, state)

        result = await handler(_FAKE_CTX)

        assert result == {"status": "completed"}
