%% MATLAB MCP Server — Signal Processing Examples
% Requires: Signal Processing Toolbox (for butter, fft-based functions)
% Basic FFT works without any toolbox.

%% 1. Generate and Analyze a Signal
fs = 8000;                    % Sample rate
t = 0:1/fs:0.1;              % 100ms duration
f1 = 440;                    % A4 note
f2 = 880;                    % A5 note

signal = sin(2*pi*f1*t) + 0.5*sin(2*pi*f2*t);
noisy = signal + 0.3*randn(size(t));

% FFT Analysis
N = length(noisy);
Y = fft(noisy);
f = (0:N-1) * fs / N;

figure;
subplot(2,1,1);
plot(t*1000, noisy);
xlabel('Time (ms)'); ylabel('Amplitude');
title('Noisy Signal (440 Hz + 880 Hz)');

subplot(2,1,2);
plot(f(1:N/2), abs(Y(1:N/2))/N);
xlabel('Frequency (Hz)'); ylabel('|FFT|');
title('Frequency Spectrum');
xlim([0 2000]);

%% 2. Low-Pass Butterworth Filter (requires Signal Processing Toolbox)
fs = 8000;
t = 0:1/fs:0.1;
clean = sin(2*pi*500*t);
noisy = clean + 0.8*randn(size(t));

[b, a] = butter(6, 1000/(fs/2));  % 6th order, 1kHz cutoff
filtered = filter(b, a, noisy);

figure;
subplot(3,1,1);
plot(t*1000, clean); title('Clean Signal');
subplot(3,1,2);
plot(t*1000, noisy); title('Noisy Signal');
subplot(3,1,3);
plot(t*1000, filtered); title('Filtered Signal');
xlabel('Time (ms)');

%% 3. Spectrogram
fs = 8000;
t = 0:1/fs:1;
% Chirp signal: frequency increases from 100 Hz to 2000 Hz
f0 = 100; f1 = 2000;
signal = chirp(t, f0, 1, f1);

figure;
spectrogram(signal, 256, 200, 512, fs, 'yaxis');
title('Chirp Signal Spectrogram (100-2000 Hz)');
colorbar;
