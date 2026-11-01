"""Independent event-ledger scorer. Standard library only; never calls a policy."""
import math


def score_events(events, failure_times, num_bays, duration, costs):
    requests, starts, outcomes, occupied = {}, {}, {}, {}
    wait = busy = wasted = 0.0
    previous = 0
    for event in events:
        kind, eid, t = event['kind'], event['engine_id'], event['cycle']
        if eid not in failure_times or t < previous:
            raise AssertionError('Unknown engine or nonmonotone ledger')
        previous = t
        if eid in outcomes:
            raise AssertionError('Action after terminal outcome')
        if kind == 'REQUEST':
            if eid in requests or t >= failure_times[eid]:
                raise AssertionError('Invalid request')
            requests[eid] = t
        elif kind == 'START':
            bay = event['bay_id']
            if eid not in requests or eid in starts or bay in occupied or not 1 <= bay <= num_bays:
                raise AssertionError('Invalid dispatch/capacity')
            if t >= failure_times[eid]:
                raise AssertionError('Dispatch at or after failure')
            starts[eid] = t
            occupied[bay] = eid
            wait += t - requests[eid]
        elif kind in ('COMPLETE', 'FAILURE'):
            if kind == 'COMPLETE':
                if eid not in starts or t != starts[eid]+duration or t >= failure_times[eid]:
                    raise AssertionError('Invalid completion; failure wins ties')
                wasted += failure_times[eid] - t
            elif t != math.ceil(failure_times[eid]):
                raise AssertionError('Incorrect failure clock')
            if eid in starts:
                bay = next((b for b, e in occupied.items() if e == eid), None)
                if bay is None:
                    raise AssertionError('Missing active service')
                del occupied[bay]
                busy += t - starts[eid]
            elif eid in requests:
                wait += t - requests[eid]
            outcomes[eid] = kind
        else:
            raise AssertionError('Unknown event type')
    if set(outcomes) != set(failure_times) or occupied:
        raise AssertionError('Incomplete population or unresolved service')
    serviced = sum(k == 'COMPLETE' for k in outcomes.values())
    failed = len(outcomes)-serviced
    breakdown = dict(failure_penalties=failed*costs['failure'],
        maintenance_executions=serviced*costs['service'],
        wasted_useful_life=wasted*costs['waste'], queue_delays=wait*costs['delay'])
    return dict(serviced_count=serviced, failure_count=failed,
                total_fleet_cost=sum(breakdown.values()), cost_breakdown=breakdown,
                busy_bay_cycles=busy, wasted_cycles=wasted, total_queue_wait=wait)
