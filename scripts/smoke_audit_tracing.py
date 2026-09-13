"""Bounded live trace-link test; no ARIA request, training, or benchmark metrics."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import config,tracking

class Smoke:
    tracking_enabled=True
    @tracking.op('audit_trace_link')
    def receipt(self, source):
        return {'source':source,'synthetic_fixture':True,'not_an_aria_response':True}

if __name__ == '__main__':
    sid='audit-fixes-20260913'
    with tracking.ExperimentRun(entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT,
      session_id=sid,experiment_id='smoke',iteration=-1,run_kind='verification',
      exp_config={'purpose':'Verify external trace association only','benchmark_comparable':False}) as run:
        run_id=run.id
        url=run.url
    with tracking.research_context(config.WANDB_ENTITY,config.WANDB_PROJECT,sid,run_id,1):
        Smoke().receipt('explicit test fixture; no ARIA invocation')
    import weave
    weave.finish()
    client=weave.init(f'{config.WANDB_ENTITY}/{config.WANDB_PROJECT}')
    calls=[c for c in client.get_calls(limit=1000) if (getattr(c,'wb_run_id','') or '').endswith('/'+run_id)]
    assert len(calls)==1 and calls[0].exception is None
    assert calls[0].attributes['research_session_id']==sid
    print(json.dumps({'run_url':url,'call_id':calls[0].id,'run_id':calls[0].wb_run_id,'attributes':calls[0].attributes},indent=2))
