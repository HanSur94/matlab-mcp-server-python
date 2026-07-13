# Examples

Ready-to-run MATLAB examples and how to invoke them through the MCP tools. The full scripts live in the [`examples/`](https://github.com/HanSur94/matlab-mcp-server-python/tree/master/examples) directory:

| Script | Focus |
|---|---|
| `basic_usage.m` | Calculations, matrices, linear systems, stats, tables |
| `plotting_examples.m` | Line / scatter / bar / histogram / 3D / subplots → Plotly |
| `signal_processing.m` | FFT, Butterworth filter, spectrogram |
| `async_simulation.m` | Long-running jobs with progress reporting |

You do not run these directly — ask your AI agent to execute them. The agent calls the `execute_code` tool (or `check_code` to lint first). See the [MCP-Tools-Reference](MCP-Tools-Reference) for the full tool list.

## Basic usage

The agent runs MATLAB via `execute_code(code=...)`. The response includes captured output and a summary of workspace variables (from `whos`).

### Simple calculation

> "Calculate the eigenvalues of a 3x3 magic square"

```matlab
A = magic(3);
eigenvalues = eig(A);
disp(eigenvalues)
```

### Matrix operations

> "Create two 100x100 random matrices, multiply them, and show the trace"

```matlab
A = rand(100);
B = rand(100);
C = A * B;
fprintf('Trace: %.4f\n', trace(C));
```

### Solve a linear system

> "Solve 3x + 2y - z = 1, 2x - 2y + 4z = -2, -x + 0.5y - z = 0"

```matlab
A = [3 2 -1; 2 -2 4; -1 0.5 -1];
b = [1; -2; 0];
x = A \ b;
disp(x)
```

### Inspect the workspace

After running code, the agent can call `get_workspace()` (no arguments) to list the current session's variables with their sizes and types.

## Plotting → Plotly

When `output.plotly_conversion` is enabled (the default), every MATLAB figure is auto-converted to interactive Plotly JSON plus a static PNG. No extra tool call is needed — just create figures inside `execute_code`.

### Line plot

> "Plot sin(x) from 0 to 2π"

```matlab
x = linspace(0, 2*pi, 200);
plot(x, sin(x), 'LineWidth', 2);
xlabel('x'); ylabel('sin(x)');
title('Sine Wave');
grid on;
```

### 3D surface

> "Show me the peaks function as a 3D surface"

```matlab
[X, Y] = meshgrid(-3:0.1:3);
Z = peaks(X, Y);
surf(X, Y, Z);
colorbar; shading interp;
title('Peaks Function');
```

### Multiple subplots

> "Plot 4 different frequency sine waves in subplots"

```matlab
t = linspace(0, 1, 1000);
freqs = [5 10 20 50];
for i = 1:4
    subplot(2,2,i);
    plot(t, sin(2*pi*freqs(i)*t));
    title(sprintf('%d Hz', freqs(i)));
end
```

Static image format and resolution are controlled by `output.static_image_format` and `output.static_image_dpi` — see [Configuration](Configuration).

## Signal processing

The FFT examples work with base MATLAB. The Butterworth filter and spectrogram require the Signal Processing Toolbox.

> "Generate a noisy 440Hz signal, compute its FFT, and show both"

```matlab
fs = 8000;
t = 0:1/fs:0.1;
signal = sin(2*pi*440*t) + 0.3*randn(size(t));

N = length(signal);
Y = fft(signal);
f = (0:N-1) * fs / N;

subplot(2,1,1);
plot(t*1000, signal); title('Time Domain');
xlabel('Time (ms)');

subplot(2,1,2);
plot(f(1:N/2), abs(Y(1:N/2))/N); title('Frequency Domain');
xlabel('Frequency (Hz)');
xlim([0 2000]);
```

## Long-running jobs (async)

A job whose execution exceeds `execution.sync_timeout` (default 30s) is automatically promoted to async: `execute_code` returns a `job_id` immediately instead of blocking. Report progress from MATLAB with the bundled `mcp_progress(job_id, percentage, message)` helper, using the injected `__mcp_job_id__` variable.

> "Run a Monte Carlo simulation with 1 million trials"

```matlab
n = 1e6;
inside = 0;
for i = 1:n
    if rand()^2 + rand()^2 <= 1
        inside = inside + 1;
    end
    if mod(i, 1e5) == 0
        mcp_progress(__mcp_job_id__, i/n*100, ...
            sprintf('Trial %d/%d', i, n));
    end
end
fprintf('Pi ~= %.6f\n', 4 * inside / n);
```

The agent then polls and collects the result with the job tools:

```
get_job_status(job_id="...")   # queued / running (with % progress) / completed / failed
get_job_result(job_id="...")   # full output once completed
list_jobs()                    # all jobs for this session
cancel_job(job_id="...")       # stop a pending or running job
```

See [Async-Jobs](Async-Jobs) for the full lifecycle.

## Reading files back

The server can read files back from the session's temp directory — handy for retrieving generated scripts, data, and plots.

### Read a MATLAB script

> "Show me the script you just saved"

```
read_script(filename="analysis.m")
```

Returns the `.m` file content as inline text.

### Read a data file

> "What variables are in results.mat?"

```
read_data(filename="results.mat", format="summary")
```

For `.mat` files, `format="summary"` returns variable names, sizes, and types; `format="raw"` returns the base64-encoded file content. `read_data` also handles `.csv`, `.json`, `.txt`, and `.xlsx`.

### View a generated plot

> "Show me the plot you just created"

```
read_image(filename="result.png")
```

Returns the image as an inline content block that renders directly in Claude Desktop, Cursor, and other agent UIs. Supported: `.png`, `.jpg`, `.gif`.

## Configuration examples

Two ready-to-copy config files ship in `examples/`. Copy either to `config.yaml` in your project root.

### Minimal — single user (`config_minimal.yaml`)

```yaml
server:
  transport: "stdio"
  log_level: "info"

pool:
  min_engines: 1
  max_engines: 2
```

### Multi-user server (`config_multiuser.yaml`)

```yaml
server:
  transport: "sse"          # streamablehttp is now the recommended HTTP transport; sse is kept for back-compat
  host: "0.0.0.0"
  port: 8765
  drain_timeout_seconds: 600

pool:
  min_engines: 4
  max_engines: 16
  scale_down_idle_timeout: 1800

execution:
  sync_timeout: 60          # promote to async after 60s

security:
  require_proxy_auth: true
  max_upload_size_mb: 500

sessions:
  max_sessions: 100
  session_timeout: 7200
```

For HTTP deployments, prefer `transport: "streamablehttp"` and protect the endpoint with a bearer token (`MATLAB_MCP_AUTH_TOKEN`). See [Configuration](Configuration) and [Security](Security) for the complete schema and auth setup, and [Custom-Tools](Custom-Tools) to expose your own MATLAB functions as MCP tools.
