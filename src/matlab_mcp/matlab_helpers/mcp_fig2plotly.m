function mcp_fig2plotly(fig_handle, output_path)
%MCP_FIG2PLOTLY Convert a MATLAB figure to a Plotly-compatible JSON file.
%
%   mcp_fig2plotly(fig_handle, output_path)
%
%   Converts the figure specified by fig_handle into a Plotly JSON structure
%   and writes it to output_path.  If fig_handle is omitted, gcf is used.
%   If output_path is omitted, the JSON string is printed to stdout.
%
%   Supported plot types:
%     line      -> scatter (mode='lines')
%     bar       -> bar
%     scatter   -> scatter (mode='markers')
%     surface   -> surface
%     image     -> heatmap
%     histogram -> histogram

    if nargin < 1 || isempty(fig_handle)
        fig_handle = gcf;
    end
    if nargin < 2
        output_path = '';
    end

    traces = {};
    layout = struct();

    % Iterate all axes in the figure
    axes_list = findobj(fig_handle, 'Type', 'axes');

    for ax_idx = 1:length(axes_list)
        ax = axes_list(ax_idx);
        children = get(ax, 'Children');

        % Extract layout from the first (last in array) axes
        if ax_idx == length(axes_list)
            title_obj = get(ax, 'Title');
            if ~isempty(title_obj)
                layout.title = struct('text', get(title_obj, 'String'));
            end
            xlabel_obj = get(ax, 'XLabel');
            if ~isempty(xlabel_obj)
                layout.xaxis = struct('title', struct('text', get(xlabel_obj, 'String')));
            end
            ylabel_obj = get(ax, 'YLabel');
            if ~isempty(ylabel_obj)
                layout.yaxis = struct('title', struct('text', get(ylabel_obj, 'String')));
            end
        end

        % Convert each child object to a Plotly trace
        for ch_idx = 1:length(children)
            child = children(ch_idx);
            child_type = lower(get(child, 'Type'));

            trace = struct();

            switch child_type
                case 'line'
                    trace.type = 'scatter';
                    trace.mode = 'lines';
                    xdata = get(child, 'XData');
                    ydata = get(child, 'YData');
                    if ~isempty(xdata), trace.x = xdata; end
                    if ~isempty(ydata), trace.y = ydata; end
                    line_color = get(child, 'Color');
                    if ~isempty(line_color)
                        trace.line = struct('color', _rgb_to_hex(line_color));
                    end

                case 'bar'
                    trace.type = 'bar';
                    xdata = get(child, 'XData');
                    ydata = get(child, 'YData');
                    if ~isempty(xdata), trace.x = xdata; end
                    if ~isempty(ydata), trace.y = ydata; end

                case {'scatter', 'stair', 'errorbar'}
                    trace.type = 'scatter';
                    trace.mode = 'markers';
                    xdata = get(child, 'XData');
                    ydata = get(child, 'YData');
                    if ~isempty(xdata), trace.x = xdata; end
                    if ~isempty(ydata), trace.y = ydata; end

                case 'surface'
                    trace.type = 'surface';
                    xdata = get(child, 'XData');
                    ydata = get(child, 'YData');
                    zdata = get(child, 'ZData');
                    if ~isempty(xdata), trace.x = xdata; end
                    if ~isempty(ydata), trace.y = ydata; end
                    if ~isempty(zdata), trace.z = zdata; end

                case 'image'
                    trace.type = 'heatmap';
                    cdata = get(child, 'CData');
                    if ~isempty(cdata), trace.z = cdata; end

                case 'histogram'
                    trace.type = 'histogram';
                    xdata = get(child, 'Data');
                    if ~isempty(xdata), trace.x = xdata; end

                otherwise
                    % Skip unknown types
                    continue
            end

            traces{end+1} = trace;
        end
    end

    % Assemble the Plotly figure dict
    plotly_fig = struct();
    plotly_fig.data = traces;
    plotly_fig.layout = layout;

    json_str = jsonencode(plotly_fig);

    if ~isempty(output_path)
        fid = fopen(output_path, 'w');
        if fid == -1
            warning('MCP_FIG2PLOTLY:WriteError', ...
                    'Cannot write Plotly JSON to %s', output_path);
            return;
        end
        fprintf(fid, '%s', json_str);
        fclose(fid);
    else
        disp(json_str);
    end
end


function hex = _rgb_to_hex(rgb)
%_RGB_TO_HEX Convert a [r g b] vector (0-1 range) to a CSS hex color string.
    r = round(rgb(1) * 255);
    g = round(rgb(2) * 255);
    b = round(rgb(3) * 255);
    hex = sprintf('#%02x%02x%02x', r, g, b);
end
