// Read-only /api for deploys without the Python backend: serves the recorded ARIA sessions.
// With BACKEND_URL set, next.config.ts rewrites /api to the backend before this route is reached.
import { replayView, type ReplayRecord } from "@/lib/replay";
import launch133047 from "@/data/replays/launch-20260913-133047-0467.json";
import wf104003 from "@/data/replays/wf-20260913-104003-2c71.json";
import wf123756 from "@/data/replays/wf-20260913-123756-7824.json";
import wf150158 from "@/data/replays/wf-20260913-150158-81be.json";
import wfLive1 from "@/data/replays/wf-20260913-live1.json";

const RECORDS = [wfLive1, wf104003, wf123756, wf150158, launch133047] as unknown as ReplayRecord[];
const BY_ID = new Map(RECORDS.map((r) => [r.session.id, r]));

type Ctx = { params: Promise<{ path: string[] }> };

const readOnly = () => Response.json({ detail: "Read-only demo: showing recorded ARIA sessions. Connect BACKEND_URL to run live research." }, { status: 503 });

function demo(req: Request, path: string[]) {
  if (req.method !== "GET") return readOnly();
  const [root, id, sub, eid] = path;
  if (root === "health") return Response.json({ ok: true, aria_mode_default: "replay", canonical_ready: false, wandb_project: "", credential_present: false });
  if (root !== "sessions") return readOnly();
  if (!id) return Response.json(RECORDS.map((r) => ({
    id: r.session.id, status: r.session.status, aria_mode: r.session.aria_mode, created_at: r.session.created_at,
    current_best_auprc: r.session.current_best_auprc, budget: r.session.budget, worker_alive: false,
    mode_label: "RECORDED RUN", benchmark_beaten: false,
  })));
  const record = BY_ID.get(id);
  if (!record) return Response.json({ detail: "unknown session" }, { status: 404 });
  if (!sub) return Response.json(replayView(record));
  if (sub === "replay") return Response.json(record);
  if (sub === "events") {
    const after = Number(new URL(req.url).searchParams.get("after") ?? 0);
    return Response.json(record.events.filter((e) => e.id > after));
  }
  if (sub === "experiments" && eid) {
    const exp = record.experiments.find((e) => e.id === eid);
    return exp ? Response.json(exp) : Response.json({ detail: "unknown experiment" }, { status: 404 });
  }
  return readOnly();
}

async function handle(req: Request, { params }: Ctx) {
  return demo(req, (await params).path);
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
