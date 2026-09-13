"""Explicit assistant operator CLI. Never launches training or final evaluation.

python scripts/assistant_worker.py setup
python scripts/assistant_worker.py probe REQUEST_ID
python scripts/assistant_worker.py poll REQUEST_ID
python scripts/assistant_worker.py verify REQUEST_ID
python scripts/assistant_worker.py recover --watch
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher import config
from wildfire_researcher.state import Store
from wildfire_researcher.assistant.requests import AssistantService
from wildfire_researcher.assistant.transport import WandbAssistantTransport

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=config.DB_PATH)
    parser.add_argument('--entity', default=config.WANDB_ENTITY)
    parser.add_argument('--project', default=config.WANDB_PROJECT)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('setup', help='Print automation configuration; performs no remote writes')
    commands.add_parser('pending', help='Read durable request recovery inventory')
    imported = commands.add_parser('import', help='Import response JSON for review only; does not establish ARIA provenance')
    imported.add_argument('request_id')
    imported.add_argument('path', type=Path)
    for name in ('probe', 'poll', 'verify', 'reconcile', 'timeout'):
        child = commands.add_parser(name)
        child.add_argument('request_id')
    recover = commands.add_parser('recover', help='Process existing requests using verified transport')
    recover.add_argument('--watch', action='store_true')
    recover.add_argument('--interval', type=float, default=15)
    args = parser.parse_args(argv)
    transport = WandbAssistantTransport(args.entity, args.project)
    if args.command == 'setup':
        print(json.dumps({'run_name_regex':'^aria-assistant-[a-f0-9]{32}$', 'trigger':'run finished',
                          'prompt':transport.automation_prompt()}, indent=2))
        return 0
    service = AssistantService(Store(args.database), transport=transport)
    if args.command == 'pending': result = service.pending()
    elif args.command == 'import':
        if args.path.stat().st_size > 200000: parser.error('Response file exceeds 200000 bytes')
        result = service.import_response(args.request_id, json.loads(args.path.read_text(encoding='utf-8-sig')))
    elif args.command == 'probe': result = service.dispatch(args.request_id, probe=True)
    elif args.command == 'verify': result = service.verify_transport(args.request_id)
    elif args.command == 'recover':
        if args.interval < 1: parser.error('interval must be at least one second')
        while True:
            print(json.dumps(service.recover_once()), flush=True)
            if not args.watch: return 0
            time.sleep(args.interval)
    else: result = getattr(service, args.command)(args.request_id)
    print(json.dumps(result, indent=2))
    return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt: raise SystemExit(130)
