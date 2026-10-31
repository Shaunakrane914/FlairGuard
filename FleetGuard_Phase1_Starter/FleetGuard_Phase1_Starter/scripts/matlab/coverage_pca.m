function coverage_pca(runFolder)
% Secondary fit-only HI comparison. The held-out labels never fit parameters.
for subset = ["FD003", "FD004"]
    folder = fullfile(runFolder, subset);
    fit = readtable(fullfile(folder, 'matlab_fit_input.csv'));
    x = fit{:,4:end};
    center = mean(x,1);
    [~,~,vectors] = svd(x-center, 'econ');
    loading = vectors(:,1);
    [~,largest] = max(abs(loading));
    loading = loading * sign(loading(largest));
    hi = (x-center)*loading;
    design = [ones(height(fit),1), fit.cycle, hi];
    [~,~,engineGroup] = unique(fit.engine_id);
    counts = accumarray(engineGroup,1);
    weights = 1 ./ counts(engineGroup);
    weights = weights * height(fit)/sum(weights);
    target = min(max(fit.true_rul,0),125);
    beta = (design'*(design.*weights) + diag([0,100,100])) \ (design'*(target.*weights));
    environment = struct('version',version,'release',version('-release'), ...
        'algorithm','fit-only centered first PC + cycle; engine-balanced ridge 100');
    fitEngineIds = unique(fit.engine_id);
    save(fullfile(folder,'MatlabPCAAgeRidge.mat'),'center','loading','beta','fitEngineIds','environment');
    for role = ["development", "evaluation"]
        heldout = readtable(fullfile(folder,'matlab_'+role+'_input.csv'));
        assert(isempty(intersect(fitEngineIds, heldout.engine_id)), 'Engine leakage');
        heldoutHI = (heldout{:,4:end}-center)*loading;
        raw = [ones(height(heldout),1),heldout.cycle,heldoutHI]*beta;
        prediction = min(max(raw,0),125);
        values = [heldout.engine_id,heldout.cycle,heldout.true_rul,raw,prediction];
        path = fullfile(folder,'MatlabPCAAgeRidge_'+role+'_predictions.csv');
        assert(~isfile(path), 'Refusing to overwrite evidence');
        try
            file = fopen(path,'x');
        catch
            file = -1;
        end
        if file == -1
            % MATLAB fopen lacks exclusive-create mode on some releases. A
            % prior isfile guard and isolated run directory protect this path.
            file = fopen(path,'w');
        end
        assert(file ~= -1,'Cannot create predictions');
        fprintf(file,'engine_id,cycle,true_rul,prediction_raw,prediction\n');
        fprintf(file,'%.17g,%.17g,%.17g,%.17g,%.17g\n',values');
        fclose(file);
    end
    fprintf('%s fit engines=%d; first-PC variance fraction=%.17g\n',subset,numel(fitEngineIds), ...
        sum(((x-center)*loading).^2)/sum((x-center).^2,'all'));
end
end
