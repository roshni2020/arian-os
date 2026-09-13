"""Link the verified reconstruction into the organization's Registry, without test certification."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wandb
from wildfire_researcher import config, tracking

def main():
    config.load_wandb_credential();api=wandb.Api()
    path=config.ARTIFACTS_DIR/'operations'/'preserved-winner'/'publication.json'
    record=json.loads(path.read_text())
    if record['registry_status']=='linked':
        print(json.dumps(record,indent=2));return
    org='ali-amjad52114-r42-org'; name='Wildfire Research Models'
    matches=list(api.registries(organization=org,filter={'name':name}))
    registry=matches[0] if matches else api.create_registry(name=name,visibility='organization',organization=org,
        description='Research candidates with explicit validation provenance; no production or certified benchmark endorsement.',artifact_types=['model'])
    model=api.artifact(record['model_artifact'])
    if model.digest!=record['model_digest']:
        raise ValueError('Published model identity changed')
    target=f'{org}/wandb-registry-{name}/WildfireIA validation winner'
    model.link(target_path=target,aliases=['validation-winner','reconstructed'])
    linked=api.artifact(target+':validation-winner')
    if linked.digest!=model.digest:
        raise ValueError('Registry artifact verification failed')
    record.update({'registry_status':'linked','registry_artifact':linked.qualified_name,'registry_target':target})
    tracking.write_json(path,record);print(json.dumps(record,indent=2))

if __name__=='__main__':main()
