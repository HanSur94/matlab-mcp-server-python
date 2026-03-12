function results = mcp_checkcode(file_path)
    info = checkcode(file_path, '-struct');
    issues = {};
    for i = 1:length(info)
        issue = struct();
        issue.line = info(i).line;
        issue.column = info(i).column(1);
        issue.message = info(i).message;
        issue.id = info(i).id;
        issue.severity = 'warning';
        issues{end+1} = issue;
    end
    result = struct();
    result.issues = issues;
    result.summary = struct('errors', 0, 'warnings', length(issues));
    results = jsonencode(result);
end
