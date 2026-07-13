# Custom Tools

Expose your own MATLAB functions as first-class MCP tools. AI agents discover and call them exactly like the built-in tools ([MCP Tools Reference](MCP-Tools-Reference)), with parameter types validated by the framework and your description shown as help text.

Defined in `src/matlab_mcp/tools/custom.py`; loaded and registered at server startup in `create_server()`.

## How It Works

1. Write your MATLAB function (`.m` file) and make sure MATLAB can find it.
2. Describe it in `custom_tools.yaml`.
3. At startup the server reads the YAML, builds a typed handler per tool, and registers it with FastMCP.
4. When an agent calls the tool, the server assembles a positional MATLAB call and runs it through the same executor (and security checks) as `execute_code`.

Registration is best-effort: a malformed tool definition is logged and skipped, and the server keeps running.

## Configuration

Point `config.yaml` at the custom tools file (this is the default):

```yaml
custom_tools:
  config_file: "./custom_tools.yaml"
```

Relative paths are resolved against the config file's directory. The shipped `custom_tools.yaml` starts empty:

```yaml
tools: []
```

## YAML Schema

The file has a single top-level `tools:` list. Each entry maps to a `CustomToolDef`:

```yaml
tools:
  - name: tool_name              # MCP tool name the agent calls (required)
    matlab_function: pkg.func    # MATLAB function invoked (required)
    description: "What it does"   # Shown to the agent; defaults to "Custom tool: <name>"
    parameters:                  # Ordered list; defaults to empty
      - name: param_name         # Parameter name / MATLAB arg (required)
        type: string             # See Parameter Types below; defaults to "str"
        required: true           # Defaults to true
      - name: optional_param
        type: float
        required: false
        default: 1.0             # Used when not supplied by the caller
    returns: "Description of the return value"   # Documentation only
```

Notes:

- `parameters` order is significant — arguments are passed to MATLAB **positionally in this order**.
- `returns` is purely descriptive text; it does not shape the result.
- An implicit `ctx` argument is injected by the framework and is **not** part of your `parameters` — the agent never sees it.

## Parameter Types

The `type` string is matched case-insensitively against this map (`_TYPE_MAP`); anything unrecognized falls back to `str`.

| YAML `type` | Aliases | Python type | MATLAB rendering |
|-------------|---------|-------------|------------------|
| `str` | `string` | `str` | single-quoted string, `'...'` |
| `int` | `integer` | `int` | numeric literal |
| `float` | `number` | `float` | numeric literal |
| `bool` | `boolean` | `bool` | `true` / `false` |
| `list` | — | `list` | `str(value)` |
| `dict` | — | `dict` | `str(value)` |
| `any` | — | `Any` | `str(value)` |

String arguments are made injection-safe by doubling any single quotes before they are wrapped in `'...'`. `list`/`dict`/`any` are rendered with plain `str()`, so they are best suited to simple scalar values.

## How the MATLAB Call Is Built

For a call the server:

1. Binds the supplied arguments to the tool signature and applies defaults, so **every** parameter (required and optional) is always passed.
2. Renders each value to a MATLAB literal per the table above, in `parameters` order.
3. Executes `matlab_function(arg1, arg2, ...)` through the executor for the current session.

Because the call is a bare expression (no assignment, no trailing semicolon), MATLAB echoes the result into the session output and `ans`, and it comes back to the agent as a normal execution result — the same status / output / variables shape as `execute_code`. Your MATLAB function must accept exactly the number of positional arguments you declare.

Custom tools are **not** exempt from security: the executor runs the assembled code through the same [Security](Security) validator, so blocked functions and other checks still apply.

## Complete Example

### 1. MATLAB function (`mylib/analyze_signal.m`)

```matlab
function result = analyze_signal(signal_path, sample_rate, window_size)
    % ANALYZE_SIGNAL  Frequency analysis of a signal file.
    %   result = analyze_signal(signal_path, sample_rate, window_size)

    data = load(signal_path);
    signal = data.signal;

    N = length(signal);
    Y = fft(signal, window_size);
    f = (0:window_size/2-1) * sample_rate / window_size;
    mag = abs(Y(1:window_size/2)) / N;

    result.frequencies = f;
    result.magnitudes  = mag;
    result.snr         = snr(signal);
end
```

### 2. Tool definition (`custom_tools.yaml`)

```yaml
tools:
  - name: analyze_signal
    matlab_function: analyze_signal
    description: >
      Analyze a signal file and return frequency components, SNR,
      and peak detection results.
    parameters:
      - name: signal_path
        type: string
        required: true
      - name: sample_rate
        type: float
        required: true
      - name: window_size
        type: int
        required: false
        default: 1024
    returns: "Struct with fields: frequencies, magnitudes, snr"
```

### 3. Make MATLAB find the function

Add the directory containing your `.m` files to `workspace.default_paths` in `config.yaml` (these paths are added to the MATLAB path when engines start; see [Configuration](Configuration)):

```yaml
workspace:
  default_paths:
    - "/path/to/mylib"
```

### 4. Agent usage

The agent now sees `analyze_signal` as a tool. Asked to "analyze the signal in `data/recording.mat` at 44100 Hz", it calls the tool, and the server runs:

```matlab
analyze_signal('data/recording.mat', 44100, 1024)
```

## Multiple Tools

```yaml
tools:
  - name: analyze_signal
    matlab_function: mylib.analyze_signal
    description: "Frequency analysis of signal files"
    parameters:
      - name: signal_path
        type: string
        required: true
    returns: "Frequency analysis struct"

  - name: train_model
    matlab_function: ml.train_classifier
    description: "Train a classification model"
    parameters:
      - name: dataset_path
        type: string
        required: true
      - name: model_type
        type: string
        required: false
        default: "svm"
    returns: "Trained model and accuracy metrics"
```

## Tips

- **Package notation:** `matlab_function` is interpolated verbatim before `(...)`, so `mylib.analyze_signal` calls a function in the `+mylib` package (`+mylib/analyze_signal.m`).
- **Type coercion:** unknown `type` values silently become `str`. Double-check spelling against the [Parameter Types](#parameter-types) table.
- **Optional means defaulted, not skipped:** every declared parameter is passed on every call. There is no way to omit a middle argument — give it a sensible `default` instead.
- **Complex inputs:** `list`/`dict`/`any` are rendered with `str()` and are not guaranteed to produce valid MATLAB. Prefer passing a file path or a simple scalar and unpacking inside the `.m` function.
- **Errors:** if the MATLAB function throws, the failure is returned as a structured execution error to the agent, like any other `execute_code` result.
- **Test in MATLAB first** before exposing a function as a tool.
