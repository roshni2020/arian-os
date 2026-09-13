"""Add operational separation and carefully scoped benchmark interpretation panels."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import wandb_workspaces.workspaces as ws
import wandb_workspaces.reports.v2 as wr
from wildfire_researcher import config,tracking

def main():
    config.load_wandb_credential();out=config.ARTIFACTS_DIR/'operations'
    a=json.loads((out/'aria-retrospective-v1'/'analysis.json').read_text())
    record=out/'workspace-additions.json'
    if record.exists():
        controls=ws.Workspace.from_url(json.loads(record.read_text())['controller_workspace'])
    else:
        controls=ws.Workspace(entity=config.WANDB_ENTITY,project=config.WANDB_PROJECT,
            name='ARIA operations and controller runs',
            runset_settings=ws.RunsetSettings(query='operator-|aria-upload|control-r|final-decision',regex_query=True),
            sections=[ws.Section(name='Controller health',is_open=True,panels=[
                wr.MarkdownPanel(markdown='Operational/upload/Launch-controller runs. Scientific comparisons are in the focused research view.'),
                wr.BarPlot(title='Controller runtime',metrics=['_runtime']),
                wr.RunComparer()])])
        controls.save()
    url=controls.url.replace('\\','/')
    main=ws.Workspace.from_url(a['urls']['workspace'])
    if not any(s.name=='Benchmark interpretation' for s in main.sections):
        main.sections.append(ws.Section(name='Benchmark interpretation',is_open=True,panels=[
            wr.BarPlot(title='Descriptive final test delta versus 0.533',metrics=['delta_vs_published']),
            wr.MarkdownPanel(markdown='Validation AUPRC is not comparable to the published test benchmark. Final test deltas are descriptive: unpublished reference seeds and prior test disclosure prevent a certified benchmark claim. Protocol matching alone does not establish certification.')]))
    for section in main.sections:
        if section.name=='Controller noise separated':
            section.panels=[wr.MarkdownPanel(markdown=f'[Open controller and operational runs]({url}). The default research runset includes experiments and final evaluations only.')]
    main.save()
    reread=ws.Workspace.from_url(a['urls']['workspace'])
    assert any(s.name=='Benchmark interpretation' for s in reread.sections)
    tracking.write_json(record,{'research_workspace':a['urls']['workspace'],'controller_workspace':url})
    print(record.read_text())

if __name__=='__main__':main()
