%% MATLAB MCP Server — Plotting Examples
% Figures are auto-converted to interactive Plotly JSON + static PNG.
% Ask your AI agent to run any of these!

%% 1. Simple Line Plot
x = linspace(0, 2*pi, 100);
y = sin(x);
figure;
plot(x, y, 'b-', 'LineWidth', 2);
xlabel('x');
ylabel('sin(x)');
title('Sine Wave');
grid on;

%% 2. Multiple Lines
x = linspace(0, 2*pi, 200);
figure;
plot(x, sin(x), 'r-', 'LineWidth', 2); hold on;
plot(x, cos(x), 'b--', 'LineWidth', 2);
plot(x, sin(x) .* cos(x), 'g-.', 'LineWidth', 2);
legend('sin(x)', 'cos(x)', 'sin(x)*cos(x)');
xlabel('x'); ylabel('y');
title('Trigonometric Functions');
grid on;

%% 3. Scatter Plot
n = 500;
x = randn(n, 1);
y = 2*x + randn(n, 1) * 0.5;
figure;
scatter(x, y, 20, 'filled', 'MarkerFaceAlpha', 0.5);
xlabel('X'); ylabel('Y');
title(sprintf('Scatter Plot (n=%d, r=%.2f)', n, corr(x, y)));
grid on;

%% 4. Bar Chart
categories = {'Q1', 'Q2', 'Q3', 'Q4'};
revenue = [150 230 180 310];
figure;
bar(revenue);
set(gca, 'XTickLabel', categories);
ylabel('Revenue ($K)');
title('Quarterly Revenue');
grid on;

%% 5. Histogram
data = randn(10000, 1);
figure;
histogram(data, 50, 'FaceColor', [0.2 0.6 0.8], 'EdgeColor', 'white');
xlabel('Value');
ylabel('Count');
title('Normal Distribution (10,000 samples)');

%% 6. Surface Plot (3D)
[X, Y] = meshgrid(-3:0.1:3, -3:0.1:3);
Z = peaks(X, Y);
figure;
surf(X, Y, Z);
xlabel('X'); ylabel('Y'); zlabel('Z');
title('Peaks Function');
colorbar;
shading interp;

%% 7. Subplots
t = linspace(0, 1, 1000);
figure;
subplot(2,2,1);
plot(t, sin(2*pi*5*t)); title('5 Hz');
subplot(2,2,2);
plot(t, sin(2*pi*10*t)); title('10 Hz');
subplot(2,2,3);
plot(t, sin(2*pi*20*t)); title('20 Hz');
subplot(2,2,4);
plot(t, sin(2*pi*5*t) + sin(2*pi*20*t)); title('5 + 20 Hz');
sgtitle('Signal Frequencies');

%% 8. Heatmap / Image
data = rand(20, 20);
figure;
imagesc(data);
colorbar;
title('Random Heatmap');
xlabel('Column'); ylabel('Row');
