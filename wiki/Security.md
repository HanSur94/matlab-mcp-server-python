# Security

The server includes multiple security layers to prevent misuse while keeping MATLAB accessible to AI agents.

## Function Blocklist

By default, these MATLAB functions are blocked:

| Function | Risk |
|----------|------|
| `system()` | Execute arbitrary OS commands |
| `unix()` | Execute Unix commands |
| `dos()` | Execute DOS/Windows commands |
| `!` | Shell escape operator |

### Smart Scanning

The security validator strips **string literals** and **comments** before checking for blocked functions. This prevents false positives:

```matlab
% These are SAFE and will NOT trigger the blocklist:
disp('The operating system is great')    % "system" inside a string
% system('ls')                            % "system" inside a comment
msg = "unix-based systems";              % "unix" inside a string

% This WILL be blocked:
system('rm -rf /')                       % Actual system() call
```

### Customizing the Blocklist

```yaml
security:
  blocked_functions_enabled: true  # Set false to disable entirely
  blocked_functions:
    - "system"
    - "unix"
    - "dos"
    - "!"
    - "eval"        # Add more as needed
    - "feval"
    - "web"
```

## Workspace Isolation

When `workspace_isolation: true` (default), the server runs these commands between sessions:

```matlab
clear all;
clear global;
clear functions;
fclose all;
restoredefaultpath;
```

This ensures one user's variables, functions, and file handles don't leak to another user.

## Upload Protection

- **Size limit:** Configurable via `max_upload_size_mb` (default 100MB)
- **Filename sanitization:** Prevents path traversal attacks (`../../etc/passwd` → `etc_passwd`)
- **Temp directory isolation:** Files are uploaded to session-specific temp directories

## SSE Transport Security

When using SSE transport for multi-user deployments:

1. **Set `require_proxy_auth: true`** in config — this is a flag that acknowledges you've set up proper auth
2. **Put the server behind a reverse proxy** (nginx, Caddy, Traefik) with authentication
3. **Do NOT expose the SSE port directly** to the internet

```yaml
security:
  require_proxy_auth: true  # Suppresses the security warning

server:
  transport: "sse"
  host: "127.0.0.1"  # Bind to localhost only
  port: 8765
```

The server logs a warning at startup if SSE is enabled without `require_proxy_auth: true`.

## Session Cleanup

- Sessions expire after `session_timeout` seconds of inactivity (default 1 hour)
- Temp files are deleted when sessions end (`temp_cleanup_on_disconnect: true`)
- Completed job metadata is pruned after `job_retention_seconds` (default 24 hours)

## Recommendations

| Scenario | Recommendations |
|----------|----------------|
| **Personal use** | Default config is fine. stdio transport, basic blocklist |
| **Team server** | SSE + reverse proxy + auth. Consider adding `eval`/`feval` to blocklist |
| **Production** | SSE + reverse proxy + TLS + auth. `require_proxy_auth: true`. Review blocklist for your use case |
