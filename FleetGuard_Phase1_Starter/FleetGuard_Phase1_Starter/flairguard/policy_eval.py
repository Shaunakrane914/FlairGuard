"""Read executed ledger outcomes; never infer service from proposed severity."""

def score_ledger(store, failure_cycles, costs):
    rows = []
    with store._get_connection() as c:
        outcomes = c.execute("SELECT * FROM episode_outcomes WHERE namespace=? ORDER BY engine_id", (store.namespace,)).fetchall()
        for result in outcomes:
            engine = result['engine_id']
            actual_failure = failure_cycles[engine]
            executions = c.execute("SELECT * FROM executions WHERE namespace=? AND asset_id=?", (store.namespace,result['asset_id'])).fetchall()
            service = [x for x in executions if x['kind']=='MAINTENANCE']
            inspections = sum(x['kind']=='INSPECTION' for x in executions)
            if len(service) > 1 or any(x['cycle'] >= actual_failure for x in executions):
                raise ValueError('Invalid execution/failure boundary')
            maintained = result['kind']=='MAINTENANCE'
            if maintained != bool(service):
                raise ValueError('Outcome does not agree with executed maintenance')
            waste = actual_failure-result['cycle'] if maintained else 0
            planned_cost = costs['planned'] if maintained else 0.0
            failure_cost = 0.0 if maintained else costs['failure']
            unused_cost = waste*costs['unused_cycle']
            inspection_cost = inspections*costs['inspection']
            rows.append(dict(engine_id=engine,outcome=result['kind'],outcome_cycle=result['cycle'],
                             planned=int(maintained),failures=int(not maintained),inspections=inspections,
                             wasted_cycles=waste,planned_cost=planned_cost,failure_cost=failure_cost,
                             unused_cost=unused_cost,inspection_cost=inspection_cost,
                             total_cost=planned_cost+failure_cost+unused_cost+inspection_cost))
    return rows
