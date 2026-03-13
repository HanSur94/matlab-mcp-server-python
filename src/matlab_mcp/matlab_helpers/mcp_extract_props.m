function mcp_extract_props(fig_handle, output_path)
%MCP_EXTRACT_PROPS Extract raw figure properties to JSON for Plotly conversion.
%
%   mcp_extract_props(fig_handle, output_path)
%
%   Extracts all visual properties from the MATLAB figure specified by
%   fig_handle and writes them as a JSON file to output_path.
%   If fig_handle is omitted, gcf is used.

    if nargin < 1 || isempty(fig_handle)
        fig_handle = gcf;
    end
    if nargin < 2
        error('MCP_EXTRACT_PROPS:MissingArg', 'output_path is required');
    end

    result = struct();
    result.schema_version = 1;

    % Figure background
    result.background_color = get(fig_handle, 'Color');

    % Detect layout type
    tl = findobj(fig_handle, 'Type', 'tiledlayout');
    axes_list = findobj(fig_handle, 'Type', 'axes');
    % Remove legend axes
    axes_list = axes_list(~arrayfun(@(a) isa(a, 'matlab.graphics.illustration.Legend'), axes_list));

    if ~isempty(tl)
        result.layout_type = 'tiledlayout';
        gs = tl.GridSize;
        result.grid = struct('rows', gs(1), 'cols', gs(2));
    elseif length(axes_list) > 1
        result.layout_type = 'subplot';
        result.grid = mcp_infer_grid(axes_list);
    else
        result.layout_type = 'single';
    end

    % Extract each axes
    result.axes = {};
    for ax_idx = 1:length(axes_list)
        ax = axes_list(ax_idx);
        ax_data = mcp_extract_axes_data(ax, result.layout_type, tl);
        result.axes{end+1} = ax_data;
    end

    % Write JSON
    json_str = jsonencode(result);
    fid = fopen(output_path, 'w');
    if fid == -1
        warning('MCP_EXTRACT_PROPS:WriteError', 'Cannot write to %s', output_path);
        return;
    end
    fprintf(fid, '%s', json_str);
    fclose(fid);
end


function ax_data = mcp_extract_axes_data(ax, layout_type, tl)
    ax_data = struct();

    % Position and grid index
    ax_data.position = get(ax, 'Position');
    if strcmp(layout_type, 'tiledlayout') && ~isempty(tl)
        try
            tile_info = ax.Layout;
            % Tile is a scalar linear index; convert to (row, col)
            tile_num = tile_info.Tile;
            [tile_row, tile_col] = ind2sub(tl.GridSize, tile_num);
            ax_data.grid_index = struct('row', tile_row, 'col', tile_col, ...
                'rowspan', tile_info.TileSpan(1), 'colspan', tile_info.TileSpan(2));
        catch
            ax_data.grid_index = struct('row', 1, 'col', 1, 'rowspan', 1, 'colspan', 1);
        end
    else
        ax_data.grid_index = struct('row', 1, 'col', 1, 'rowspan', 1, 'colspan', 1);
    end

    % Title
    title_obj = get(ax, 'Title');
    ax_data.title = struct('text', get(title_obj, 'String'), ...
        'font_name', get(title_obj, 'FontName'), ...
        'font_size', get(title_obj, 'FontSize'), ...
        'font_weight', get(title_obj, 'FontWeight'));

    % Labels
    xl = get(ax, 'XLabel');
    ax_data.xlabel = struct('text', get(xl, 'String'), ...
        'font_name', get(xl, 'FontName'), 'font_size', get(xl, 'FontSize'));
    yl = get(ax, 'YLabel');
    ax_data.ylabel = struct('text', get(yl, 'String'), ...
        'font_name', get(yl, 'FontName'), 'font_size', get(yl, 'FontSize'));

    % Axis ranges and ticks
    ax_data.xlim = get(ax, 'XLim');
    ax_data.ylim = get(ax, 'YLim');
    ax_data.xgrid = strcmp(get(ax, 'XGrid'), 'on');
    ax_data.ygrid = strcmp(get(ax, 'YGrid'), 'on');
    ax_data.xdir = get(ax, 'XDir');
    ax_data.ydir = get(ax, 'YDir');
    ax_data.xtick = get(ax, 'XTick');
    ax_data.ytick = get(ax, 'YTick');

    xtl = get(ax, 'XTickLabel');
    if ~isempty(xtl), ax_data.xticklabels = xtl; else, ax_data.xticklabels = []; end
    ytl = get(ax, 'YTickLabel');
    if ~isempty(ytl), ax_data.yticklabels = ytl; else, ax_data.yticklabels = []; end

    ax_data.tick_font = struct('font_name', get(ax, 'FontName'), ...
        'font_size', get(ax, 'FontSize'));

    % Colors and grid style
    ax_data.color = get(ax, 'Color');
    ax_data.grid_color = get(ax, 'GridColor');
    ax_data.grid_alpha = get(ax, 'GridAlpha');
    ax_data.grid_line_style = get(ax, 'GridLineStyle');

    % Legend (ax.Legend is available in R2020a+, fallback for older)
    try
        leg = ax.Legend;
    catch
        leg = findobj(get(ax, 'Parent'), 'Type', 'legend');
        if ~isempty(leg), leg = leg(1); end
    end
    if ~isempty(leg) && isvalid(leg)
        ax_data.legend = struct('visible', true, ...
            'entries', {get(leg, 'String')}, ...
            'location', get(leg, 'Location'));
    else
        ax_data.legend = struct('visible', false, 'entries', {{}}, 'location', 'best');
    end

    % Children — check for FastPlot first, then standard MATLAB children
    ax_data.children = {};

    fp_obj = mcp_find_fastplot(ax);
    if ~isempty(fp_obj)
        % FastPlot detected — extract raw data (full resolution) and thresholds
        ax_data.children = mcp_extract_fastplot(fp_obj, ax);
    else
        % Standard MATLAB children
        children = get(ax, 'Children');
        for ch_idx = 1:length(children)
            child = children(ch_idx);
            child_data = mcp_extract_child_data(child);
            if ~isempty(child_data)
                ax_data.children{end+1} = child_data;
            end
        end
    end
end


function child_data = mcp_extract_child_data(child)
    child_type = lower(get(child, 'Type'));
    child_data = struct();

    switch child_type
        case 'line'
            child_data.type = 'line';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.color = get(child, 'Color');
            child_data.line_style = get(child, 'LineStyle');
            child_data.line_width = get(child, 'LineWidth');
            child_data.display_name = get(child, 'DisplayName');
            child_data.marker = get(child, 'Marker');
            child_data.marker_size = get(child, 'MarkerSize');
            child_data.marker_face_color = get(child, 'MarkerFaceColor');
            child_data.marker_edge_color = get(child, 'MarkerEdgeColor');

        case 'bar'
            child_data.type = 'bar';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.face_color = get(child, 'FaceColor');
            child_data.edge_color = get(child, 'EdgeColor');
            child_data.bar_width = get(child, 'BarWidth');
            child_data.display_name = get(child, 'DisplayName');

        case 'scatter'
            child_data.type = 'scatter';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.marker = get(child, 'Marker');
            child_data.size_data = get(child, 'SizeData');
            child_data.marker_face_color = get(child, 'MarkerFaceColor');
            child_data.marker_edge_color = get(child, 'MarkerEdgeColor');
            child_data.display_name = get(child, 'DisplayName');

        case 'surface'
            child_data.type = 'surface';
            child_data.xdata = get(child, 'XData');
            child_data.ydata = get(child, 'YData');
            child_data.zdata = get(child, 'ZData');
            try
                child_data.colormap = mcp_get_colormap_name(ancestor(child, 'axes'));
            catch
                child_data.colormap = 'parula';
            end

        case 'image'
            child_data.type = 'image';
            child_data.cdata = get(child, 'CData');
            try
                child_data.colormap = mcp_get_colormap_name(ancestor(child, 'axes'));
            catch
                child_data.colormap = 'gray';
            end

        case 'histogram'
            child_data.type = 'histogram';
            child_data.data = get(child, 'Data');
            child_data.face_color = get(child, 'FaceColor');
            child_data.edge_color = get(child, 'EdgeColor');
            child_data.num_bins = get(child, 'NumBins');
            child_data.bin_edges = get(child, 'BinEdges');

        case 'patch'
            child_data.type = 'patch';
            xd = get(child, 'XData');
            yd = get(child, 'YData');
            % Flatten patch data (may be matrix for multi-face patches)
            if ~isvector(xd), xd = xd(:,1)'; end
            if ~isvector(yd), yd = yd(:,1)'; end
            child_data.xdata = xd;
            child_data.ydata = yd;
            child_data.face_color = get(child, 'FaceColor');
            child_data.face_alpha = get(child, 'FaceAlpha');
            child_data.edge_color = get(child, 'EdgeColor');
            child_data.display_name = get(child, 'DisplayName');

        otherwise
            child_data = [];
            return;
    end
end


function fp_obj = mcp_find_fastplot(ax)
%MCP_FIND_FASTPLOT Find a FastPlot object that owns the given axes.
%   Searches the base workspace for FastPlot objects whose hAxes matches ax.
    fp_obj = [];
    try
        vars = evalin('base', 'whos');
        for i = 1:length(vars)
            if strcmp(vars(i).class, 'FastPlot')
                fp = evalin('base', vars(i).name);
                if isvalid(fp) && isprop(fp, 'hAxes') && ~isempty(fp.hAxes) && fp.hAxes == ax
                    fp_obj = fp;
                    return;
                end
            end
        end
    catch
        % FastPlot not available or not found
    end
end


function children = mcp_extract_fastplot(fp, ax)
%MCP_EXTRACT_FASTPLOT Extract full-resolution data from a FastPlot object.
%   Returns a cell array of child structs with raw data, thresholds, and violations.
    children = {};

    % Extract lines at full resolution from FastPlot's internal data
    if isprop(fp, 'Lines')
        for i = 1:length(fp.Lines)
            L = fp.Lines(i);
            child = struct();
            child.type = 'line';

            % Get FULL resolution data from FastPlot's raw storage
            if isfield(L, 'X') && isfield(L, 'Y')
                xraw = L.X;
                yraw = L.Y;

                % Cap at 50,000 points for JSON size — downsample if larger
                maxpts = 50000;
                if length(xraw) > maxpts
                    step = ceil(length(xraw) / maxpts);
                    idx = 1:step:length(xraw);
                    % Always include last point
                    if idx(end) ~= length(xraw)
                        idx = [idx, length(xraw)];
                    end
                    child.xdata = xraw(idx);
                    child.ydata = yraw(idx);
                else
                    child.xdata = xraw;
                    child.ydata = yraw;
                end
            else
                % Fallback to rendered line handle
                if isfield(L, 'hLine') && ~isempty(L.hLine) && isvalid(L.hLine)
                    child.xdata = get(L.hLine, 'XData');
                    child.ydata = get(L.hLine, 'YData');
                else
                    continue;
                end
            end

            % Get line style from Options or from handle
            if isfield(L, 'Options') && isfield(L.Options, 'Color')
                child.color = L.Options.Color;
            elseif isfield(L, 'hLine') && ~isempty(L.hLine) && isvalid(L.hLine)
                child.color = get(L.hLine, 'Color');
            else
                child.color = [0 0.447 0.741];
            end

            if isfield(L, 'Options') && isfield(L.Options, 'LineWidth')
                child.line_width = L.Options.LineWidth;
            elseif isfield(L, 'hLine') && ~isempty(L.hLine) && isvalid(L.hLine)
                child.line_width = get(L.hLine, 'LineWidth');
            else
                child.line_width = 1;
            end

            if isfield(L, 'Options') && isfield(L.Options, 'LineStyle')
                child.line_style = L.Options.LineStyle;
            else
                child.line_style = '-';
            end

            if isfield(L, 'Options') && isfield(L.Options, 'DisplayName')
                child.display_name = L.Options.DisplayName;
            else
                child.display_name = '';
            end

            child.marker = 'none';
            child.marker_size = 6;
            child.marker_face_color = 'none';
            child.marker_edge_color = 'auto';

            children{end+1} = child;
        end
    end

    % Extract thresholds
    if isprop(fp, 'Thresholds')
        for i = 1:length(fp.Thresholds)
            T = fp.Thresholds(i);

            % Threshold line
            child = struct();
            child.type = 'line';
            xl = get(ax, 'XLim');
            child.xdata = xl;
            child.ydata = [T.Value, T.Value];

            if isfield(T, 'Color') && ~isempty(T.Color)
                child.color = T.Color;
            else
                child.color = [1 0 0];
            end

            if isfield(T, 'LineStyle') && ~isempty(T.LineStyle)
                child.line_style = T.LineStyle;
            else
                child.line_style = '--';
            end

            child.line_width = 1.5;

            if isfield(T, 'Label') && ~isempty(T.Label)
                child.display_name = T.Label;
            else
                child.display_name = sprintf('Threshold %.2f', T.Value);
            end

            child.marker = 'none';
            child.marker_size = 6;
            child.marker_face_color = 'none';
            child.marker_edge_color = 'auto';

            children{end+1} = child;

            % Violation markers (if ShowViolations is enabled)
            if isfield(T, 'hMarkers') && ~isempty(T.hMarkers) && isvalid(T.hMarkers)
                vm = struct();
                vm.type = 'scatter';
                vm.xdata = get(T.hMarkers, 'XData');
                vm.ydata = get(T.hMarkers, 'YData');
                vm.marker = 'o';
                vm.size_data = 36;
                if isfield(T, 'Color') && ~isempty(T.Color)
                    vm.marker_face_color = T.Color;
                    vm.marker_edge_color = T.Color;
                else
                    vm.marker_face_color = [1 0 0];
                    vm.marker_edge_color = [1 0 0];
                end
                vm.display_name = sprintf('%s Violations', child.display_name);

                if ~isempty(vm.xdata)
                    children{end+1} = vm;
                end
            end
        end
    end
end


function grid = mcp_infer_grid(axes_list)
%MCP_INFER_GRID Infer grid dimensions from axes positions.
    positions = zeros(length(axes_list), 4);
    for i = 1:length(axes_list)
        positions(i,:) = get(axes_list(i), 'Position');
    end

    % Cluster unique left values for columns, bottom values for rows
    lefts = sort(unique(round(positions(:,1), 2)));
    bottoms = sort(unique(round(positions(:,2), 2)), 'descend');

    grid = struct('rows', length(bottoms), 'cols', length(lefts));
end


function name = mcp_get_colormap_name(ax)
%MCP_GET_COLORMAP_NAME Try to determine the colormap name.
    cmap = colormap(ax);
    known = {'parula','jet','hsv','hot','cool','gray','bone','copper','turbo'};
    for i = 1:length(known)
        try
            ref = feval(known{i}, size(cmap, 1));
            if max(abs(cmap - ref), [], 'all') < 0.01
                name = known{i};
                return;
            end
        catch
        end
    end
    name = 'parula';
end
