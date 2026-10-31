% Read-only capability inspection. No project models or datasets are modified.
r = struct;
r.version = version;
r.release = version('-release');
r.computer = computer;
r.products = ver;
features = {'MATLAB','SIMULINK','Pred_Maintenance_Toolbox','Statistics_Toolbox', ...
    'Signal_Toolbox','Identification_Toolbox','Neural_Network_Toolbox', ...
    'Distrib_Computing_Toolbox','Optimization_Toolbox','Curve_Fitting_Toolbox', ...
    'Control_Toolbox','Simscape','Simscape_Fluids','Hydraulics','GADS_Toolbox','Wavelet_Toolbox','Stateflow','Simulink_Design_Optim'};
r.license_tests = struct;
for k = 1:numel(features)
    try
        r.license_tests.(features{k}) = license('test',features{k});
    catch ME
        r.license_tests.(features{k}) = ME.message;
    end
end
names = {'similarityModel','residualSimilarityModel','pairwiseSimilarityModel','hashSimilarityModel','predictRUL','linearDegradationModel','exponentialDegradationModel', ...
    'reliabilitySurvivalModel','monotonicity','trendability','prognosability', ...
    'diagnosticFeatureDesigner','pca','fitrensemble','fitrgp','kmeans', ...
    'findpeaks','lowpass','ssest','iddata','trainnet','dlnetwork','parpool', ...
    'sim','new_system','simulink','fmincon','fit','fluids_lib'};
r.functions = struct;
for k = 1:numel(names)
    n = names{k};
    r.functions.(n) = struct('exist_file',exist(n,'file'),'exist_class',exist(n,'class'),'path',which(n));
end
% Tiny independent smoke probes. This is not C-MAPSS model training.
r.smoke = struct;
constructors = {'residualSimilarityModel','pairwiseSimilarityModel','hashSimilarityModel', ...
    'linearDegradationModel','exponentialDegradationModel','reliabilitySurvivalModel'};
for k = 1:numel(constructors)
    n = constructors{k};
    try
        a = feval(n);
        r.smoke.(n) = struct('status','ok','class',class(a),'has_predictRUL',ismethod(a,'predictRUL'));
    catch ME
        r.smoke.(n) = struct('status','failed','error',ME.message);
    end
end
try
    [~,~,latent] = pca([1 2;2 2.2;3 3.1;4 3.9]);
    r.smoke.statistics = struct('status','ok','latent',latent);
catch ME
    r.smoke.statistics = struct('status','failed','error',ME.message);
end
try
    [pks,locs] = findpeaks([0 1 0 2 0]);
    r.smoke.signal = struct('status','ok','peak_count',numel(pks));
catch ME
    r.smoke.signal = struct('status','failed','error',ME.message);
end
try
    load_system('simulink');
    r.smoke.simulink = struct('status','ok','loaded',bdIsLoaded('simulink'));
    close_system('simulink',0);
catch ME
    r.smoke.simulink = struct('status','failed','error',ME.message);
end
r.licenses_in_use = license('inuse');
out = fullfile(fileparts(mfilename('fullpath')),'matlab_capabilities.json');
fid = fopen(out,'w'); fwrite(fid,jsonencode(r,PrettyPrint=true),'char'); fclose(fid);
fprintf('Capability report: %s\nRelease: %s\n',out,r.release);
disp(r.license_tests);
disp(r.smoke);
