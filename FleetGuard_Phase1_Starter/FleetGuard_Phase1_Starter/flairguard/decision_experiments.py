"""FD002 research policies and a fast development-only scheduling model.

Final experiments execute through WorkOrderStore. The development scheduler is
differentially checked against that store; it is not an independent cost scorer.
"""
import math
from .triage import Proposal
from .evidence import digest


def propose(row, state, policy):
    cycle=int(row['cycle']);kind=policy['kind'];point=row['prediction']
    def monitor(reason):return Proposal('NORMAL','NORMAL',False,'MONITOR',reason)
    def maintenance(value):
        priority='CRITICAL' if value<=policy['critical_threshold'] else 'HIGH'
        return Proposal(priority,priority,False,'WORK_ORDER_SCHEDULE_MAINTENANCE','Frozen development policy; proposed simulated maintenance')
    if kind=='none':return monitor('Run-to-failure comparator')
    if kind=='fixed':return maintenance(policy['threshold']) if cycle>=policy['fixed_age'] else monitor('Waiting for fixed age')
    if cycle<policy['min_history']:return monitor('Initial observation warm-up')
    available=bool(row['available']) and point is not None
    risk_key='risk_score' if kind=='learned_gate' else 'quality_score'
    invalid=not available or (kind!='point' and row[risk_key]>policy['risk_threshold'])
    if invalid:
        if kind in ('learned_gate','quality_decision') and available and point>policy['threshold']+policy['decision_buffer']:
            return monitor('Rejected prediction is far from the action threshold; no automatic early replacement')
        last=state.get('last_valid');age=cycle-last['cycle'] if last else None
        if last and age<=policy['stale_limit']:
            point=max(0,last['prediction']-age)
        else:
            urgent=point is not None and point<=policy['critical_threshold']
            return Proposal('CRITICAL' if urgent else 'ESCALATE_HUMAN','CRITICAL' if urgent else 'MEDIUM',
                            True,'ESCALATE_HUMAN_DATA_FAULT','Bounded stale evidence exhausted; uninformative inspection fallback')
    return maintenance(point) if point is not None and point<=policy['threshold'] else monitor('Action threshold not reached')


def next_state(row, state, policy):
    state=dict(state);kind=policy['kind']
    key='risk_score' if kind=='learned_gate' else 'quality_score'
    valid=row['available'] and row['prediction'] is not None
    if kind not in ('point','fixed','none'):valid=valid and row[key]<=policy['risk_threshold']
    if valid:state['last_valid']=dict(cycle=int(row['cycle']),prediction=float(row['prediction']))
    state['last_cycle']=int(row['cycle'])
    return state


def fast_schedule(rows, failure_cycle, policy):
    """Development screening only. No failure time reaches propose/next_state."""
    state={};due=review_due=None;priority=0;inspections=[];maint_action=False
    rank={'NORMAL':0,'MEDIUM':1,'HIGH':2,'CRITICAL':3}
    previous=0
    for row in rows:
        cycle=int(row['cycle'])
        if cycle<=previous:raise ValueError('Development replay requires increasing cycles')
        previous=cycle
        if cycle>=failure_cycle:return dict(outcome='FAILURE',outcome_cycle=failure_cycle,inspection_cycles=inspections)
        if review_due is not None and cycle>=review_due:
            inspections.append(cycle);review_due=None;maint_action=True;priority=max(priority,2)
            due=min(due,cycle+policy['lead_time']) if due is not None else cycle+policy['lead_time']
        if maint_action and review_due is None and cycle>=due:
            return dict(outcome='MAINTENANCE',outcome_cycle=cycle,inspection_cycles=inspections)
        proposal=propose(row,state,policy)
        if proposal.action_type!='MONITOR':
            action=proposal.action_type.startswith('WORK_ORDER_')
            higher=rank[proposal.priority]>priority
            if priority==0 or higher or (action and not maint_action):
                priority=max(priority,rank[proposal.priority])
                if action:
                    maint_action=True;review_due=None
                    due=min(due,cycle+policy['lead_time']) if due is not None else cycle+policy['lead_time']
                elif not maint_action:review_due=cycle+policy['review_delay']
        state=next_state(row,state,policy)
    raise ValueError('Incomplete episode; historical failure boundary not reached')


def schedule_cost(schedule, failure_cycle, costs):
    maintained=schedule['outcome']=='MAINTENANCE'
    if (maintained and schedule['outcome_cycle']>=failure_cycle) or any(c>=failure_cycle for c in schedule['inspection_cycles']):
        raise ValueError('Execution at/after failure cannot be scored as service')
    return (costs['planned']+costs['unused_cycle']*(failure_cycle-schedule['outcome_cycle']) if maintained else costs['failure'])+len(schedule['inspection_cycles'])*costs['inspection']


class EvidenceReplay:
    """Policy replay of previously saved causal evidence, not a serving shortcut.

    Evidence is produced without outcome labels and is immutable before policy
    evaluation. Final actions use the same transactional store as Phase A.
    """
    def __init__(self,store,policy,model_id,protocol_hash):
        self.store=store;self.policy=policy;self.model_id=model_id;self.policy_id=digest(policy)
        store.bind_context(dict(model_id=model_id,protocol_hash=protocol_hash,policy=policy,
                                mode='offline causal-evidence replay; durable at snapshot'))

    def consume(self,engine_id,row,telemetry):
        if any(key in row for key in ('true_rul','failure_cycle','T')):
            raise ValueError('Evaluator labels are forbidden in replay evidence')
        cycle=int(row['cycle']);last,state=self.store.get_checkpoint(engine_id)
        proposal=propose(row,state,self.policy)
        result=self.store.record_decision(int(engine_id),cycle,proposal.severity,proposal.action_type,
                row['prediction'],None,None,0,proposal.reason,telemetry,
                priority=proposal.priority,review_required=proposal.review_required,
                checkpoint=next_state(row,state,self.policy),prediction_evidence=row,
                model_id=self.model_id,policy_id=self.policy_id,
                input_hash=digest(dict(engine_id=engine_id,row=row,telemetry=telemetry,policy_id=self.policy_id)),
                expected_previous_cycle=last,lead_time=self.policy['lead_time'],review_delay=self.policy['review_delay'])
        return result


def execute_episode(replay,engine_id,rows,telemetry,failure_cycle):
    for row,raw in zip(rows,telemetry,strict=True):
        cycle=int(row['cycle'])
        if cycle>=failure_cycle:
            replay.store.record_failure(int(engine_id),failure_cycle);break
        replay.store.execute_due(int(engine_id),cycle,lead_time=replay.policy['lead_time'])
        with replay.store._get_connection() as c:
            ended=c.execute('SELECT 1 FROM episode_outcomes WHERE namespace=? AND asset_id=?',
                            (replay.store.namespace,str(engine_id))).fetchone()
        if ended:break
        replay.consume(engine_id,row,raw)
    with replay.store._get_connection() as c:
        outcome=c.execute('SELECT cycle,kind FROM episode_outcomes WHERE namespace=? AND asset_id=?',
                          (replay.store.namespace,str(engine_id))).fetchone()
        inspections=c.execute("SELECT cycle FROM executions WHERE namespace=? AND asset_id=? AND kind='INSPECTION' ORDER BY cycle",
                              (replay.store.namespace,str(engine_id))).fetchall()
    if outcome is None:raise ValueError('Incomplete executed episode')
    return dict(outcome=outcome['kind'],outcome_cycle=outcome['cycle'],inspection_cycles=[r[0] for r in inspections])
