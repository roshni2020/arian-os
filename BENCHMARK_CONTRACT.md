# Benchmark API contract v1

Backend owns this contract and `wildfire_researcher/benchmarks/`, new scripts, and additive API mount. Frontend owns pages/components/client. Verification owns acceptance tests and checkpoint. Existing scientific modules are protected. API base is existing backend, prefix `/api`.

## Endpoints (JSON)
- GET `/benchmarks?q=&source=&domain=&task_type=&metric=&sort=readiness&limit=50&offset=0`: `{items: Benchmark[], total, stale: boolean}`; local cache only. sort supports newest, readiness, smallest, popular.
- POST `/benchmarks/sync`: `{provider:"huggingface"|"openml",query:"",limit:10}` -> `{items: Benchmark[], warnings:string[]}`. Explicit bounded network refresh.
- POST `/benchmarks/import`: `{url:string}` -> Import record `{id,status:"complete"|"partial"|"failed",benchmark:Benchmark|null,warnings:string[]}`. Structured allowed providers only.
- GET `/benchmarks/imports/{id}` -> persisted Import record.
- GET `/benchmarks/{id}` -> Benchmark; 404 unknown.
- POST `/projects`: `{benchmark_id:string,name:string,experiment_budget:1..50,overrides?:Record<string,unknown>,selected_result_id?:string,idempotency_key?:string}` -> Project. Creates saved snapshot only, never starts research. Multiple results require explicit selection.
- GET `/projects` -> `{items:Project[]}`.
- POST `/projects/from-session`: `{session_id,name}` saves an existing custom session into the same thin project model without starting or modifying it. Existing custom start UI stays intact.
- GET `/projects/{id}` -> Project.
- POST `/projects/{id}/start`: `{wait_seconds?:number}` -> `{project:Project,session_id:string,journal_url:string}`. Connected real ARIA only; idempotent for already linked project. 409 unsupported/altered protocol or active worker. Existing `/api/sessions` remains custom-session interface.

## Shapes
Benchmark has `id,slug,title,description,domain,task_type,publication_date,paper_url,repository_url,dataset_url,dataset_provider,dataset_identifier,dataset_revision,metric_name,metric_direction,published_score,published_model,sample_count,license,train_split,validation_split,test_split,evaluation_protocol,leakage_notes,source,created_at,updated_at`. Missing values are null. Strings unless score/count numeric; evaluation_protocol is object. Also `provenance:Record<string,Provenance>`, `sources:Source[]`, `results:Result[]`, `readiness:Readiness`, `compatibility:Compatibility`.

Provenance: `{value:unknown,source_provider:string|null,source_url:string|null,status:"verified"|"inferred"|"missing"|"user_edited",confidence:"high"|"medium"|"low"|null}`. User edits do not become source verification.
Source: `{provider,external_id,external_url,last_synced_at}`.
Public access evidence is explicit: `dataset_public:boolean|null`, `repository_public:boolean|null`. A URL alone does not prove public access. OpenML task identity does not collapse into its supporting dataset identity.
Result: `{id,model,metric_name,metric_direction,metric_definition,score,dataset_identifier,dataset_revision,split,source_url}`. All absent values null. No score is inferred or automatically selected among multiple results.
Readiness: `{status:"complete"|"partial",score:number,total:6,missing:string[]}` measures metadata only.
Compatibility: `{executable:boolean,executor:"wildfireia"|null,reasons:string[],comparability:string}` is independent of metadata readiness. No arbitrary dataset executor.
Project: `{id,name,benchmark_id,snapshot:Benchmark,experiment_budget,selected_result_id:string|null,session_id:string|null,created_at,compatibility:Compatibility}`. Snapshot immutable across source refresh; overrides are marked user_edited.

## Strict execution boundary
Only trusted WildfireIA import with exact pinned dataset `WildfireIA/Anonymous-WildfireIA` revision `cd1fcad871c4293ec7bf066229d8714f059d42de`, repo `https://github.com/LabRAI/WildfireIA` commit `aba9be9ef046a03e868a61c4139aa5bfcd7b5b56`, task ia_failure/tabular, official chronological split, label, prediction-time restrictions and sklearn average precision can start. Any change to execution-relevant fields blocks execution. Published 0.533 is a test reference; validation experiments cannot claim to beat it. Five published seeds are not fully disclosed. Start links to existing research journal and preserves final-evaluation gates. Live acceptance is validation only, with no official test evaluation.

Errors use existing FastAPI `{detail:string}` with 400 malformed input, 404 missing, 409 incompatible/conflict, 502 provider failure. Partial metadata is successful partial import. Provider response contents and raw secrets never appear in errors.
