"""Evaluator-only failure labels; never called by the operational forecast builder."""
import math
from pathlib import Path
from .data import read_test_end_rul, read_trajectories
from .fleet_scheduler import SchedulePolicy, SchedulingMetrics


def load_failure_times(data_dir, dataset, engine_ids):
    raw = read_trajectories(Path(data_dir) / f'test_{dataset}.txt')
    labels = read_test_end_rul(Path(data_dir) / f'RUL_{dataset}.txt')
    ends = raw.groupby('engine_id').cycle.max().sort_index()
    if len(ends) != len(labels):
        raise ValueError('Failure label alignment mismatch')
    world = {int(e): float(t+r) for (e,t),r in zip(ends.items(),labels)}
    return {int(e): world[int(e)] for e in engine_ids}


def summarize_trace(scheduler, trace, policy, failure_times):
    events = trace['events']
    if failure_times is not None:
        # Production accounting is separate from scheduler_scorer.py, which audits this ledger.
        completed = [e for e in events if e['kind']=='COMPLETE']
        failed = [e for e in events if e['kind']=='FAILURE']
        starts = {e['engine_id']:e['cycle'] for e in events if e['kind']=='START'}
        requests_at = {e['engine_id']:e['cycle'] for e in events if e['kind']=='REQUEST'}
        terminal = completed + failed
        wasted = sum(failure_times[e['engine_id']]-e['cycle'] for e in completed)
        busy = sum(e['cycle']-starts[e['engine_id']] for e in terminal if e['engine_id'] in starts)
        waits = sum(starts.get(eid,next((e['cycle'] for e in terminal if e['engine_id']==eid),at))-at
                    for eid,at in requests_at.items())
        breakdown = dict(failure_penalties=len(failed)*scheduler.cost_failure,
            maintenance_executions=len(completed)*scheduler.cost_service,
            wasted_useful_life=wasted*scheduler.cost_waste_per_cycle,
            queue_delays=waits*scheduler.cost_grounding_delay)
        scored = dict(serviced_count=len(completed),failure_count=len(failed),
                      total_fleet_cost=sum(breakdown.values()),cost_breakdown=breakdown,
                      busy_bay_cycles=busy,wasted_cycles=wasted)
    else:
        raise ValueError('Failure labels unavailable: policy costs cannot be scored')
    requests = {e['engine_id']:e['cycle'] for e in events if e['kind']=='REQUEST'}
    waits = [e['cycle']-requests[e['engine_id']] for e in events
             if e['kind']=='START' or (e['kind']=='FAILURE' and e['engine_id'] in requests and
                not any(s['kind']=='START' and s['engine_id']==e['engine_id'] for s in events))]
    n = scored['serviced_count']
    return SchedulingMetrics(policy=policy.value,num_bays=scheduler.num_bays,
        service_duration=scheduler.service_duration,total_engines_evaluated=len(trace['profiles']),
        serviced_count=n,failure_count=scored['failure_count'],
        mean_queue_wait_cycles=sum(waits)/len(waits) if waits else 0.,
        max_queue_wait_cycles=max(waits,default=0),
        mean_wasted_cycles=scored['wasted_cycles']/n if n else 0.,
        bay_utilization_pct=100*scored['busy_bay_cycles']/max(1,trace['cycle']*scheduler.num_bays),
        total_fleet_cost=scored['total_fleet_cost'],cost_breakdown=scored['cost_breakdown'],
        operational_recommendation='Descriptive comparison only; no scheduler promoted. Risk-aware margin is uncalibrated.',
        evaluation_scope='Uncapped evaluator-only failure times; synchronous cycle offsets=0; ageing through service' if failure_times is not None else 'Censored operational trace; costs and failure outcomes unavailable',
        censored_count=trace['censored_count'],events=events)


def evaluate_fleet(scheduler, profiles, failure_times, policy):
    if set(failure_times) != {p.engine_id for p in profiles}:
        raise ValueError('Failure population mismatch')
    horizon = math.ceil(max(failure_times.values(),default=0))
    observer = lambda t: [e for e,f in failure_times.items() if math.ceil(f)==t]
    trace = scheduler.run(profiles,policy,failure_observer=observer,horizon=horizon)
    return summarize_trace(scheduler,trace,policy,failure_times)


def compare_fleet(scheduler, profiles, failure_times):
    return sorted([evaluate_fleet(scheduler,profiles,failure_times,p) for p in SchedulePolicy],
                  key=lambda m:m.total_fleet_cost)
