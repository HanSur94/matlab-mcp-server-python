%% MATLAB MCP Server — Async / Long-Running Job Examples
% Jobs that exceed sync_timeout (default 30s) are auto-promoted to async.
% The agent gets a job_id and can poll progress while MATLAB computes.

%% 1. Monte Carlo Pi Estimation (with progress reporting)
n = 1e6;
inside = 0;
for i = 1:n
    x = rand();
    y = rand();
    if x^2 + y^2 <= 1
        inside = inside + 1;
    end
    % Report progress every 10%
    if mod(i, n/10) == 0
        mcp_progress(__mcp_job_id__, i/n*100, ...
            sprintf('Processed %d/%d trials', i, n));
    end
end
pi_estimate = 4 * inside / n;
fprintf('Pi estimate: %.6f (error: %.6f)\n', pi_estimate, abs(pi - pi_estimate));

%% 2. Large Matrix Computation (auto-promotes to async if slow)
n = 5000;
fprintf('Creating %dx%d random matrix...\n', n, n);
A = rand(n);
fprintf('Computing SVD...\n');
[U, S, V] = svd(A);
fprintf('Top 5 singular values: ');
disp(diag(S(1:5, 1:5))');
fprintf('Condition number: %.2e\n', cond(A));

%% 3. Iterative Solver with Progress
n = 1000;
A = rand(n) + n*eye(n);  % diagonally dominant
b = rand(n, 1);
x = zeros(n, 1);
max_iter = 500;
tol = 1e-10;

for iter = 1:max_iter
    x_new = (b - (A - diag(diag(A))) * x) ./ diag(A);
    err = norm(x_new - x) / norm(x_new);
    x = x_new;

    if mod(iter, 50) == 0
        mcp_progress(__mcp_job_id__, iter/max_iter*100, ...
            sprintf('Iteration %d/%d, error=%.2e', iter, max_iter, err));
    end

    if err < tol
        fprintf('Converged at iteration %d (error=%.2e)\n', iter, err);
        break;
    end
end
fprintf('Residual norm: %.2e\n', norm(A*x - b));
