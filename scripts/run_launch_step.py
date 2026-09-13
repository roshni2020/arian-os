import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wildfire_researcher.launch_step import execute_request
from wildfire_researcher.state import Store

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--output',required=True)
    args=p.parse_args()
    request=json.loads(Path(args.request).read_text())
    try:
        result=execute_request(request)
    except Exception as exc:
        # Keep a failed Launch step visible in the app, instead of leaving a stale training state.
        store=Store()
        if request.get('session_id'):
            session=store.get_session(request['session_id'])
            if session['protocol'].get('execution_backend')=='wandb-launch' and session['status'] not in ('complete','cancelled'):
                store.update_session(session['id'],error=f'{type(exc).__name__}: {exc}')
                store.set_status(session['id'],'error','Launch job failed; see queued-run logs')
        raise
    Path(args.output).write_text(json.dumps(result,indent=2))
