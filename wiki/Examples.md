# Examples

Ready-to-run examples are in the [`examples/`](https://github.com/HanSur94/matlab-mcp-server-python/tree/master/examples) directory. You don't run these directly — ask your AI agent to execute them!

## Basic Usage

### Simple Calculation

> "Calculate the eigenvalues of a 3x3 magic square"

```matlab
A = magic(3);
eigenvalues = eig(A);
disp(eigenvalues)
```

### Matrix Operations

> "Create two 100x100 random matrices, multiply them, and show the trace"

```matlab
A = rand(100);
B = rand(100);
C = A * B;
fprintf('Trace: %.4f\n', trace(C));
```

### Solve a Linear System

> "Solve this system of equations: 3x + 2y - z = 1, 2x - 2y + 4z = -2, -x + 0.5y - z = 0"

```matlab
A = [3 2 -1; 2 -2 4; -1 0.5 -1];
b = [1; -2; 0];
x = A \ b;
disp(x)
```

## Plotting

All figures are automatically converted to interactive Plotly JSON + static PNG.

### Line Plot

> "Plot sin(x) from 0 to 2π"

```matlab
x = linspace(0, 2*pi, 200);
plot(x, sin(x), 'LineWidth', 2);
xlabel('x'); ylabel('sin(x)');
title('Sine Wave');
grid on;
```

### 3D Surface

> "Show me the peaks function as a 3D surface"

```matlab
[X, Y] = meshgrid(-3:0.1:3);
Z = peaks(X, Y);
surf(X, Y, Z);
colorbar; shading interp;
title('Peaks Function');
```

### Multiple Subplots

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

## Signal Processing

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

## Long-Running Jobs (Async)

Jobs that exceed `sync_timeout` are automatically promoted to async. Use `mcp_progress()` to report progress.

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
fprintf('Pi ≈ %.6f\n', 4 * inside / n);
```

The agent gets a job ID immediately and can poll progress:
- "Trial 100000/1000000 — 10%"
- "Trial 500000/1000000 — 50%"
- ...until complete.

## Configuration Examples

### Minimal (Single User)

```yaml
server:
  transport: "stdio"
  log_level: "info"

pool:
  min_engines: 1
  max_engines: 2
```

### Multi-User Server

```yaml
server:
  transport: "sse"
  host: "0.0.0.0"
  port: 8765

pool:
  min_engines: 4
  max_engines: 16

security:
  require_proxy_auth: true

sessions:
  max_sessions: 100
```

See the full [`examples/`](https://github.com/HanSur94/matlab-mcp-server-python/tree/master/examples) directory for more.
