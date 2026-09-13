"""Closed assistant output contracts. All citations bind to an immutable evidence identity."""
import json
import re
KINDS = {"ask", "error_proposal", "study_plan", "report"}
DRAFT_KEYS = {
    "error_proposal": {"hypothesis", "experiment", "success_criteria", "tradeoffs"},
    "study_plan": {"objective", "steps", "success_criteria", "experiment_budget", "stopping_conditions"},
    "report": {"title", "limitations", "recommendation"},
}

def validate_response(payload, request):
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "request_id", "snapshot_hash", "kind", "claims", "assumptions", "missing_evidence", "draft"
    }: raise ValueError("Response must use exact v1 envelope")
    if len(json.dumps(payload)) > 200000: raise ValueError("Response too large")
    if (payload["schema_version"] != 1 or payload["request_id"] != request["id"] or
        payload["snapshot_hash"] != request["snapshot"]["hash"] or payload["kind"] != request["kind"]):
        raise ValueError("Response scope or snapshot mismatch")
    evidence = {e["id"]: e for e in request["snapshot"]["evidence"]}
    if not isinstance(payload["claims"], list) or len(payload["claims"]) > 50:
        raise ValueError("Claims must be bounded list")
    for claim in payload["claims"]:
        if not isinstance(claim, dict) or set(claim) != {"text", "citations"}: raise ValueError("Invalid claim")
        if not isinstance(claim["text"], str) or not 1 <= len(claim["text"]) <= 4000: raise ValueError("Invalid text")
        if not isinstance(claim["citations"], list) or not claim["citations"]: raise ValueError("Citations required")
        if any(not isinstance(c, str) or c not in evidence for c in claim["citations"]):
            raise ValueError("Unknown evidence citation")
        # Every number must occur in the specifically cited source, not anywhere in the snapshot.
        # This checks grounding, not whether prose establishes a scientific causal conclusion.
        numbers = re.findall(r"(?<![\w-])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", claim["text"])
        cited = [evidence[c] for c in claim['citations']]
        subgroup = request['snapshot'].get('subgroup')
        numeric_sources = cited
        if subgroup:
            group_text = claim['text']
            # A narrowly recognized absence sentence is verifiable from the snapshot itself.
            # Remove it only for group attribution, never from numeric or run identity checks.
            absence_pattern = r'No [A-Za-z][A-Za-z -]{0,79} subgroup cells are recorded for ([A-Za-z0-9_-]+) in this snapshot\.'
            for absence in re.finditer(absence_pattern, claim['text'], re.IGNORECASE):
                run_id = absence.group(1)
                cited_run = any(item.get('experiment_id') == run_id for item in cited)
                has_cells = any(item.get('experiment_id') == run_id and '.error_breakdowns.' in item['path']
                                for item in request['snapshot']['evidence'])
                if cited_run and not has_cells:
                    group_text = group_text.replace(absence.group(0), '')
                else:
                    raise ValueError('Subgroup absence statement is not established for its cited run')
            mentions_group = re.search(r'(?<!\w)' + re.escape(subgroup['group']) + r'(?!\w)', group_text, re.IGNORECASE)
            mentions_group = mentions_group or any(label in group_text.casefold() for label in (
                'subgroup', 'selected group', 'this group', 'this region', 'selected region'))
            # A numeric error-proposal claim in group context needs group evidence unless it
            # explicitly identifies itself as an aggregate observation.
            if request['kind'] == 'error_proposal' and re.search(r'\d', group_text) and not any(
                label in group_text.casefold() for label in ('global', 'overall', 'aggregate')):
                mentions_group = True
            if mentions_group and not any('.error_breakdowns.' + subgroup['dimension'] + '.' in item['path'] for item in cited):
                raise ValueError('Subgroup claim must cite recorded subgroup cells, not aggregate run metrics')
            if mentions_group:
                numeric_sources = [item for item in cited if '.error_breakdowns.' + subgroup['dimension'] + '.' in item['path']]
        source_text = json.dumps([item['value'] for item in numeric_sources], sort_keys=True)
        source_numbers = set(re.findall(r"(?<![\w-])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", source_text))
        if any(number not in source_numbers for number in numbers):
            raise ValueError("Numerical claim is not grounded in its cited source; quote exact recorded values")
        # Reject explicit references to a different selected run or named metric. Natural-language
        # synonyms and causal interpretation still require review; citation checks cannot prove prose.
        for experiment_id in request['snapshot'].get('experiment_ids', []):
            if re.search(r'(?<![\w-])' + re.escape(experiment_id) + r'(?![\w-])', claim['text']):
                if not any(item['experiment_id'] == experiment_id for item in cited):
                    raise ValueError('Claim names a run absent from its citations')
        metric_aliases = {'validation_auprc': ('validation AP','validation average precision','validation_auprc'),
                          'validation_auroc': ('validation AUROC','validation_auroc'),
                          'false_negative_count': ('false_negative_count',),
                          'false_positive_count': ('false_positive_count',)}
        for metric, aliases in metric_aliases.items():
            if any(alias.casefold() in claim['text'].casefold() for alias in aliases):
                if not any(item['path'].endswith('.' + metric) or (
                    item['path'].startswith('findings.') and item['path'].endswith('.metrics') and
                    isinstance(item['value'], dict) and metric in item['value']) for item in cited):
                    raise ValueError('Claim metric does not match cited evidence')
    for key in ("assumptions", "missing_evidence"):
        if not isinstance(payload[key], list) or len(payload[key]) > 30 or any(
            not isinstance(v, str) or len(v) > 4000 for v in payload[key]): raise ValueError("Invalid " + key)
    draft = payload["draft"]
    if request["kind"] == "ask":
        if draft is not None: raise ValueError("Ask cannot create executable drafts")
    else:
        if not isinstance(draft, dict) or set(draft) != DRAFT_KEYS[request["kind"]]: raise ValueError("Invalid draft fields")
        for key, value in draft.items():
            if key in {'experiment_budget','experiment'}: continue
            if key in {'steps', 'success_criteria', 'stopping_conditions', 'tradeoffs', 'limitations'}:
                if not isinstance(value, (str, list)): raise ValueError("Invalid draft " + key)
                values = value if isinstance(value, list) else [value]
                if len(values) > 50 or any(not isinstance(v, str) or len(v) > 4000 for v in values):
                    raise ValueError("Invalid draft " + key)
            elif not isinstance(value, str) or not 1 <= len(value) <= 4000: raise ValueError("Invalid draft " + key)
        if request['kind'] == 'error_proposal':
            if not isinstance(draft['experiment'], dict) or set(draft['experiment']) != {
                'model','feature_protocol','weather_days','hyperparameters'}: raise ValueError("Invalid experiment shape")
        if request["kind"] == "study_plan":
            if type(draft["experiment_budget"]) is not int or not 1 <= draft["experiment_budget"] <= 50: raise ValueError("Invalid budget")
            if not isinstance(draft["steps"], list) or len(draft["steps"]) > draft["experiment_budget"]:
                raise ValueError("Invalid planned experiments")
    return payload
