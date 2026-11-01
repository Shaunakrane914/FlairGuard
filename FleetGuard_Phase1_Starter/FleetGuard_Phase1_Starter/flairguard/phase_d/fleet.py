"""Operational controller sees current observations and failure notifications only."""
import copy
import hashlib
import heapq
import itertools
import json
import math


def stable_id(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:24]


class FleetController:
    def __init__(self,engine_ids,policy,condition,threshold=20.,fixed_age=140,risk_threshold=.5,
                 recovery='abstain',namespace='study'):
        self.config=dict(engine_ids=list(map(int,engine_ids)),policy=policy,condition=condition,
            threshold=threshold,fixed_age=fixed_age,risk_threshold=risk_threshold,recovery=recovery,namespace=namespace)
        self.state=dict(t=0,done={},orders={},latest={},reviews={},events=[],bays={},review_active=None)
    def checkpoint(self):return copy.deepcopy(dict(config=self.config,state=self.state))
    @classmethod
    def restore(cls,checkpoint):
        obj=cls(**checkpoint['config']);obj.state=copy.deepcopy(checkpoint['state'])
        # JSON keys must not change engine identity after a real serialized checkpoint.
        for k in ('done','orders','latest','reviews','bays'):
            obj.state[k]={int(e):v for e,v in obj.state[k].items()}
        return obj
    def emit(self,kind,eid,t,**extra):
        event=dict(kind=kind,engine_id=int(eid),tick=t,**extra)
        self.state['events'].append(event)
    def _order(self,eid,t,row,reason):
        if eid in self.state['orders']:return
        self.state['reviews'].pop(eid,None)
        active=self.state['review_active']
        if active and active['engine_id']==eid:
            self.emit('REVIEW_CANCEL',eid,t)
            self.state['review_active']=None
        local=row['cycle'];order=stable_id([self.config['namespace'],eid,local,self.config['policy']])
        deadline=t+row['prediction'] if row.get('prediction') is not None else t
        self.emit('PROPOSE',eid,t,cycle=local,reason=reason,model_id=row.get('model_id'),
                  model_sha256=row.get('model_sha256'),prediction=row.get('prediction'))
        self.emit('COMMIT',eid,t,order_id=order,cycle=local,reason=reason,prediction=row.get('prediction'))
        self.state['orders'][eid]=dict(order_id=order,requested=t,ready=t+self.config['condition']['lead'],
                                      deadline=deadline,status='QUEUED',cycle=local)
    def _choose(self,eligible,t,free):
        policy=self.config['policy'];orders=self.state['orders'];latest=self.state['latest']
        def key(eid):
            row=latest[eid];order=orders[eid];point=row.get('prediction')
            point=point if point is not None else 0.
            if policy=='FCFS':return (order['requested'],eid)
            if policy=='EDF':return (order['deadline'],eid)
            if policy in ('risk_logistic','risk_boosted','risk_residual'):
                return (-row.get(policy,0.),point,eid)
            # margin is retained as the existing uncalibrated zero-margin comparator.
            return (point,eid)
        ranked=sorted(eligible,key=key)
        if policy!='lookahead' or len(ranked)<2:return ranked
        # Bounded rolling optimization over six urgent jobs. No truth/cost outcomes.
        shortlist=ranked[:6];capacity=max(1,free)
        best=None
        for permutation in itertools.permutations(shortlist):
            slots=[t]*capacity;score=0.
            for eid in permutation:
                start=max(heapq.heappop(slots),orders[eid]['ready'])
                finish=start+self.config['condition']['duration']
                point=latest[eid].get('prediction')
                deadline=t+(point if point is not None else 0.)
                score+=max(0.,finish-deadline)**2 + .01*(start-orders[eid]['requested'])
                heapq.heappush(slots,finish)
            candidate=(score,permutation)
            if best is None or candidate<best:best=candidate
        return list(best[1])+ranked[6:]
    def step(self,t,observations,failed_now=()):
        if t<=self.state['t']:raise ValueError('Increasing global tick required')
        for row in observations:
            if {'true_rul','failure_cycle','outcome','T'} & set(row):
                raise ValueError('Evaluator labels forbidden in operational observations')
        state=self.state;condition=self.config['condition'];state['t']=t
        for eid in sorted(failed_now):
            eid=int(eid)
            if eid in state['done']:continue
            phase=state['orders'].get(eid,{}).get('status','UNREQUESTED')
            self.emit('FAILURE',eid,t,phase=phase)
            state['done'][eid]='FAILURE'
            for bay,service in list(state['bays'].items()):
                if service['engine_id']==eid:del state['bays'][bay]
            state['reviews'].pop(eid,None)
            if state['review_active'] and state['review_active']['engine_id']==eid:state['review_active']=None
        for bay,service in sorted(list(state['bays'].items())):
            if t>=service['due']:
                eid=service['engine_id'];order=state['orders'][eid]
                self.emit('COMPLETE',eid,t,order_id=order['order_id'],bay_id=bay)
                state['done'][eid]='COMPLETE';order['status']='COMPLETE';del state['bays'][bay]
        active=state['review_active']
        if active and t>=active['due']:
            eid=active['engine_id'];self.emit('REVIEW_COMPLETE',eid,t)
            state['review_active']=None
            if eid not in state['done']:self._order(eid,t,state['latest'][eid],'Uninformative review; conservative replacement')
            state['review_active']=None;state['reviews'].pop(eid,None)
        for supplied in observations:
            row=dict(supplied);eid=int(row['engine_id'])
            if eid in state['done'] or state['orders'].get(eid,{}).get('status')=='IN_SERVICE':continue
            point=row.get('prediction')
            if point is not None and not math.isfinite(point):raise ValueError('Nonfinite prediction must be explicitly unavailable')
            state['latest'][eid]=row
            if row['cycle']<20 or eid in state['orders']:continue
            policy=self.config['policy']
            if policy=='none':continue
            request=policy=='fixed' and row['cycle']>=self.config['fixed_age']
            if policy!='fixed' and point is not None:request=point<=self.config['threshold']
            if policy.startswith('risk_'):
                request=request or row.get(policy,0.)>=self.config['risk_threshold']
            if request:self._order(eid,t,row,'Frozen '+policy+' decision')
            elif point is None and self.config['recovery']=='decision_fallback' and row.get('stale_age',0)>=5:
                # Causal deadline-aware fallback: inspect only when last forecast or age suggests urgency.
                if row.get('last_valid_prediction',125.)<=40 or row.get('stale_age',0)>=20:
                    if eid not in state['reviews']:
                        state['reviews'][eid]=t;self.emit('REVIEW_REQUEST',eid,t)
        if state['review_active'] is None and state['reviews']:
            eid=min(state['reviews'],key=lambda e:(state['reviews'][e],e))
            state['review_active']=dict(engine_id=eid,due=t+2)
            self.emit('REVIEW_START',eid,t)
        capacity=min(condition['bays'],condition['technicians'])
        free=[b for b in range(1,capacity+1) if b not in state['bays']]
        eligible=[eid for eid,o in state['orders'].items() if eid not in state['done'] and o['status']=='QUEUED' and o['ready']<=t]
        ranked=self._choose(eligible,t,len(free))
        for bay,eid in zip(free,ranked):
            order=state['orders'][eid];order['status']='IN_SERVICE'
            state['bays'][bay]=dict(engine_id=eid,due=t+condition['duration'])
            self.emit('START',eid,t,order_id=order['order_id'],bay_id=bay,request_tick=order['requested'])


def evaluate_controller(stream,failure_cycles,condition,policy,threshold=20.,fixed_age=140,
                        risk_threshold=.5,recovery='abstain',namespace='study',restart=False):
    """World/evaluator boundary: only current failure notifications enter controller.step."""
    ids=sorted(map(int,stream.engine_id.unique()))
    if set(ids)!=set(failure_cycles):raise ValueError('Evaluation population mismatch')
    offsets={eid:(eid*7)%condition['offset'] if condition['offset'] else 0 for eid in ids}
    calendar={}
    for row in stream.to_dict('records'):
        clean={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in row.items()}
        calendar.setdefault(int(row['cycle'])+offsets[int(row['engine_id'])],[]).append(clean)
    world={eid:int(failure_cycles[eid])+offsets[eid] for eid in ids}
    controller=FleetController(ids,policy,condition,threshold,fixed_age,risk_threshold,recovery,namespace)
    for t in range(1,max(world.values())+1):
        # The terminal failure row is never presented as a usable observation.
        observations=[r for r in calendar.get(t,[]) if t<world[int(r['engine_id'])]]
        controller.step(t,observations,[eid for eid,death in world.items() if death==t])
        if restart and t%31==0:controller=FleetController.restore(json.loads(json.dumps(controller.checkpoint())))
    if set(controller.state['done'])!=set(ids):raise AssertionError('Unresolved engine')
    return controller.state['events'],world
