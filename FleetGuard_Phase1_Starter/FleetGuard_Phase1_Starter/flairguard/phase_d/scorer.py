"""Independent standard-library-only action/cost reconstruction. No policy imports."""
import math


def score(events,world,condition,costs):
    commits,starts,ends,proposals,reviews={}, {}, {}, {}, {}
    occupied={};review_active=None;review_completed={};review_requested=set();last=0
    for event in events:
        eid=int(event['engine_id']);t=event['tick'];kind=event['kind']
        if eid not in world or t<last or eid in ends:raise AssertionError('Ledger order/identity/terminal violation')
        last=t
        if kind=='PROPOSE':
            if eid in proposals:raise AssertionError('Duplicate proposal')
            proposals[eid]=event
        elif kind=='COMMIT':
            if eid not in proposals or eid in commits or event['tick']!=proposals[eid]['tick']:
                raise AssertionError('Commit lacks unique proposal')
            commits[eid]=event
        elif kind=='START':
            bay=event['bay_id']
            if eid not in commits or eid in starts or event['order_id']!=commits[eid]['order_id']:
                raise AssertionError('Execution without unique committed order')
            if t<commits[eid]['tick']+condition['lead'] or t>=world[eid]:raise AssertionError('Lead/failure boundary')
            if not 1<=bay<=min(condition['bays'],condition['technicians']) or bay in occupied:
                raise AssertionError('Resource capacity violation')
            starts[eid]=event;occupied[bay]=eid
        elif kind=='REVIEW_REQUEST':
            if eid in review_requested:raise AssertionError('Duplicate review')
            review_requested.add(eid)
        elif kind=='REVIEW_START':
            if eid not in review_requested or review_active is not None:raise AssertionError('Review capacity violation')
            review_active=eid;reviews[eid]=t
        elif kind in ('REVIEW_COMPLETE','REVIEW_CANCEL'):
            if review_active!=eid:raise AssertionError('Review completion without start')
            if kind=='REVIEW_COMPLETE':
                if t!=reviews[eid]+2:raise AssertionError('Review delay mismatch')
                review_completed[eid]=t
            review_active=None
        elif kind in ('FAILURE','COMPLETE'):
            if kind=='FAILURE':
                if t!=world[eid]:raise AssertionError('Wrong failure time')
                if review_active==eid:review_active=None
            else:
                if eid not in starts or t!=starts[eid]['tick']+condition['duration'] or t>=world[eid]:
                    raise AssertionError('Wrong service completion')
                if event['order_id']!=commits[eid]['order_id']:raise AssertionError('Order identity mismatch')
            if eid in starts:
                bay=starts[eid]['bay_id']
                if occupied.get(bay)!=eid:raise AssertionError('Missing occupied bay')
                del occupied[bay]
            ends[eid]=event
        else:raise AssertionError('Unknown event')
    if set(ends)!=set(world) or occupied:raise AssertionError('Incomplete engine population')
    rows=[]
    for eid,terminal in sorted(ends.items()):
        t=terminal['tick'];requested=commits.get(eid,{}).get('tick');started=starts.get(eid,{}).get('tick')
        wait=(started if started is not None else t)-requested if requested is not None else 0
        completed=terminal['kind']=='COMPLETE';wasted=world[eid]-t if completed else 0
        busy=t-started if started is not None else 0
        downtime=t-requested if requested is not None else 0
        inspected=int(eid in review_completed)
        breakdown=dict(failure=0. if completed else costs['failure'],service=costs['service'] if completed else 0.,
            waste=costs['waste']*wasted,delay=costs['delay']*wait,
            downtime=costs['downtime']*downtime,inspection=costs['inspection']*inspected)
        rows.append(dict(engine_id=eid,outcome=terminal['kind'],outcome_tick=t,
            requested_tick=requested,started_tick=started,completed=int(completed),failures=int(not completed),
            failure_phase=terminal.get('phase'),queue_wait=wait,maintenance_delay=wait,
            wasted_cycles=wasted,downtime=downtime,busy_bay_cycles=busy,inspections=inspected,
            review_requests=int(eid in review_requested),
            decision_lateness=max(0,requested-(world[eid]-condition['lead']-condition['duration'])) if requested is not None else None,
            missed_service_opportunity=int(requested is None or requested+condition['lead']+condition['duration']>=world[eid]),
            total_cost=math.fsum(breakdown.values()),**{'cost_'+k:v for k,v in breakdown.items()}))
    return rows
