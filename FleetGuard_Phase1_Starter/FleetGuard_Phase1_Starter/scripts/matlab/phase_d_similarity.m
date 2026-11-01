function phase_d_similarity(folder)
% Bounded, offline toolbox comparator. Fit data only; query prefixes only.
assert(license('test','Pred_Maintenance_Toolbox')==1,'Predictive Maintenance Toolbox unavailable');
assert(exist('pairwiseSimilarityModel','class')==8,'Pairwise estimator unavailable');
fprintf('MATLAB %s; pairwiseSimilarityModel=%s\n',version,which('pairwiseSimilarityModel'));
fitData=readtable(fullfile(folder,'fit.csv'));
query=readtable(fullfile(folder,'queries.csv'));
ids=unique(fitData.engine_id);profiles=cell(numel(ids),1);
for k=1:numel(ids)
    x=fitData(fitData.engine_id==ids(k),:);
    profiles{k}=table(x.cycle,x.hi,'VariableNames',{'Cycle','HI'});
end
timer=tic;
mdl=pairwiseSimilarityModel('Method','correlation','LifeTimeUnit','cycles');
fit(mdl,profiles,'Cycle','HI');
fitSeconds=toc(timer);
save(fullfile(folder,'pairwise_similarity.mat'),'mdl','ids','fitSeconds');
fid=fopen(fullfile(folder,'predictions.csv'),'w');
cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'engine_id,cycle,scenario,prediction,inference_seconds,status\n');
for scenario=["clean","missing"]
    for eid=unique(query.engine_id)'
        rows=query(query.engine_id==eid & string(query.scenario)==scenario,:);
        for cutoff=20:20:max(rows.cycle)
            prefix=rows(rows.cycle<=cutoff,:);
            if isempty(prefix) || ~isfinite(prefix.hi(end))
                fprintf(fid,'%d,%d,%s,,0,UNAVAILABLE\n',eid,cutoff,scenario);continue
            end
            prefix=prefix(isfinite(prefix.hi),:);
            timer=tic;
            try
                value=predictRUL(mdl,table(prefix.cycle,prefix.hi,'VariableNames',{'Cycle','HI'}));
                if isduration(value),value=hours(value);end
                assert(isscalar(value) && isfinite(value),'Invalid toolbox prediction');
                fprintf(fid,'%d,%d,%s,%.17g,%.17g,AVAILABLE\n',eid,cutoff,scenario,max(0,min(125,double(value))),toc(timer));
            catch err
                fprintf('Prediction unavailable E%d C%d: %s\n',eid,cutoff,err.message);
                fprintf(fid,'%d,%d,%s,,%.17g,ERROR\n',eid,cutoff,scenario,toc(timer));
            end
        end
    end
end
fprintf('Fit seconds %.17g\n',fitSeconds);
end
