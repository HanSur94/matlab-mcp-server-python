function mcp_progress(job_id, percentage, message)
    if nargin < 3, message = ''; end
    percentage = max(0, min(100, percentage));
    progress = struct();
    progress.percentage = percentage;
    progress.message = message;
    progress.timestamp = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    json_str = jsonencode(progress);
    temp_dir = getenv('MCP_TEMP_DIR');
    if isempty(temp_dir), warning('MCP_PROGRESS:NoTempDir', 'MCP_TEMP_DIR not set'); return; end
    filepath = fullfile(temp_dir, [job_id '.progress']);
    fid = fopen(filepath, 'w');
    if fid == -1, warning('MCP_PROGRESS:WriteError', 'Cannot write progress file'); return; end
    fprintf(fid, '%s', json_str);
    fclose(fid);
end
