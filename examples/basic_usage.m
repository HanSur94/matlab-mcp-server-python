%% MATLAB MCP Server — Basic Usage Examples
% These examples show what your AI agent can execute through the MCP server.
% You don't run these directly — ask your AI agent to run them!

%% 1. Simple Calculation
A = magic(3);
eigenvalues = eig(A);
disp('Eigenvalues of a 3x3 magic square:');
disp(eigenvalues);

%% 2. Matrix Operations
n = 100;
A = rand(n);
B = rand(n);
C = A * B;
fprintf('Result matrix size: %dx%d\n', size(C, 1), size(C, 2));
fprintf('Max element: %.4f\n', max(C(:)));
fprintf('Trace: %.4f\n', trace(C));

%% 3. Solving a Linear System
A = [3 2 -1; 2 -2 4; -1 0.5 -1];
b = [1; -2; 0];
x = A \ b;
disp('Solution to Ax = b:');
disp(x);

%% 4. Basic Statistics
data = randn(1, 10000);
fprintf('Mean:   %.4f\n', mean(data));
fprintf('Std:    %.4f\n', std(data));
fprintf('Median: %.4f\n', median(data));
fprintf('Min:    %.4f\n', min(data));
fprintf('Max:    %.4f\n', max(data));

%% 5. String Operations
name = 'MATLAB MCP Server';
fprintf('Upper: %s\n', upper(name));
fprintf('Length: %d\n', length(name));
fprintf('Reversed: %s\n', fliplr(name));

%% 6. Working with Tables (R2013b+)
names = {'Alice'; 'Bob'; 'Charlie'; 'Diana'};
ages = [30; 25; 35; 28];
scores = [95.5; 88.0; 92.3; 97.1];
T = table(names, ages, scores, 'VariableNames', {'Name', 'Age', 'Score'});
disp(T);
fprintf('Average score: %.1f\n', mean(T.Score));
