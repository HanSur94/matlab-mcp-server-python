# Custom Tools

Expose your own MATLAB functions as first-class MCP tools. AI agents can discover and call them directly, with full parameter validation and help text.

## How It Works

1. Write your MATLAB function (`.m` file)
2. Describe it in `custom_tools.yaml`
3. The server registers it as an MCP tool at startup
4. Agents see it alongside built-in tools

## Configuration

Point your `config.yaml` to the custom tools file:

```yaml
custom_tools:
  config_file: "./custom_tools.yaml"
```

## YAML Format

```yaml
tools:
  - name: tool_name                # MCP tool name (what agents call)
    matlab_function: pkg.func      # MATLAB function to call
    description: "What it does"    # Shown to agents
    parameters:
      - name: param_name
        type: string               # string | double | int | logical
        required: true             # or false
        description: "What this parameter does"
      - name: optional_param
        type: double
        default: 1.0               # Default value if not provided
        description: "Optional param with default"
    returns: "Description of return value"
```

## Parameter Types

| YAML Type | MATLAB Type | Python Type |
|-----------|-------------|-------------|
| `string` | `char` | `str` |
| `double` | `double` | `float` |
| `int` | `int64` | `int` |
| `logical` | `logical` | `bool` |

## Complete Example

### 1. MATLAB Function (`mylib/analyze_signal.m`)

```matlab
function result = analyze_signal(signal_path, sample_rate, window_size)
    % ANALYZE_SIGNAL  Frequency analysis of a signal file
    %
    %   result = analyze_signal(signal_path, sample_rate, window_size)
    %
    %   Returns struct with: frequencies, magnitudes, snr, peaks

    data = load(signal_path);
    signal = data.signal;

    N = length(signal);
    Y = fft(signal, window_size);
    f = (0:window_size/2-1) * sample_rate / window_size;
    mag = abs(Y(1:window_size/2)) / N;

    [peaks, locs] = findpeaks(mag, 'MinPeakHeight', max(mag)*0.1);

    result.frequencies = f;
    result.magnitudes = mag;
    result.snr = snr(signal);
    result.peaks = struct('frequencies', f(locs), 'amplitudes', peaks);
end
```

### 2. Custom Tool Definition (`custom_tools.yaml`)

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
        description: "Path to the signal data file (.mat)"
      - name: sample_rate
        type: double
        required: true
        description: "Sample rate in Hz"
      - name: window_size
        type: int
        default: 1024
        description: "FFT window size"
    returns: "Struct with fields: frequencies, magnitudes, snr, peaks"
```

### 3. Make Sure MATLAB Can Find It

Add the directory containing your `.m` files to the workspace paths in `config.yaml`:

```yaml
workspace:
  default_paths:
    - "/path/to/mylib"
```

### 4. Agent Usage

The agent now sees `analyze_signal` as a tool and can call it:

> "Analyze the signal in data/recording.mat at 44100 Hz sample rate"

The server:
1. Validates parameters against the YAML schema
2. Calls `analyze_signal('data/recording.mat', 44100, 1024)` in MATLAB
3. Returns the result to the agent

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
        default: "svm"
    returns: "Trained model and accuracy metrics"

  - name: process_image
    matlab_function: imgtools.enhance
    description: "Image enhancement pipeline"
    parameters:
      - name: image_path
        type: string
        required: true
      - name: denoise_strength
        type: double
        default: 0.5
    returns: "Enhanced image saved to temp directory"
```

## Tips

- **Function names with packages:** Use `pkg.func` notation to call functions in MATLAB packages (e.g., `+mylib/analyze_signal.m` → `mylib.analyze_signal`)
- **MEX files:** Custom tools work with `.mex` files too — just reference the function name without the extension
- **Error handling:** If the MATLAB function throws an error, the MCP server returns a structured error response to the agent
- **Testing:** Test your functions in MATLAB first before exposing them as tools
