"""Read-only check of remote run, artifact, and trace evidence."""
import json
from pathlib import Path
from probe import credential

credential()
import wandb
import weave

project='ali-amjad52114-r42/aria-integration-probe'
session='aria-probe-20260913'
state=json.loads((Path('artifacts')/session/'state.json').read_text())
api=wandb.Api()
runs=[]
for row in state['history']:
    run_id=row['wandb_run_url'].rsplit('/',1)[-1]
    r=api.run(f'{project}/{run_id}')
    remote=float(r.summary['validation_auprc'])
    assert abs(remote-row['result']['validation_auprc']) < 1e-12
    assert r.config['benchmark_comparable'] is False
    runs.append({'id':run_id,'state':r.state,'auprc':remote,'controller':r.config['controller']})
client=weave.init(project)
calls=list(client.get_calls(limit=100))
trace_rows=[{'id':c.id,'op':c.op_name,'run_id':getattr(c,'wb_run_id',None),
             'exception':c.exception} for c in calls]
assert trace_rows, 'No Weave traces found'
assert all(c['exception'] is None for c in trace_rows), 'A trace failed'
print(json.dumps({'session_status':state['status'],'runs':runs,'trace_count':len(trace_rows),
    'traces':trace_rows,'decisions':state['decisions']},indent=2))
