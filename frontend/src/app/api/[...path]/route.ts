// /api for the frontend. The five recorded ARIA sessions are served from bundled replays;
// everything else goes to the Python backend at BACKEND_URL. Without BACKEND_URL the site is read-only.
import { replayView, type ReplayRecord } from "@/lib/replay";
import launch133047 from "@/data/replays/launch-20260913-133047-0467.json";
import wf104003 from "@/data/replays/wf-20260913-104003-2c71.json";
import wf123756 from "@/data/replays/wf-20260913-123756-7824.json";
import wf150158 from "@/data/replays/wf-20260913-150158-81be.json";
import wfLive1 from "@/data/replays/wf-20260913-live1.json";

export const maxDuration = 60;

const BACKEND = process.env.BACKEND_URL?.replace(/\/+$/, "");
const RECORDS = [wfLive1, wf104003, wf123756, wf150158, launch133047] as unknown as ReplayRecord[];
const BY_ID = new Map(RECORDS.map((r) => [r.session.id, r]));
const SUMMARIES = RECORDS.map((r) => ({
  id: r.session.id, status: r.session.status, aria_mode: r.session.aria_mode, created_at: r.session.created_at,
  current_best_auprc: r.session.current_best_auprc, budget: r.session.budget, worker_alive: false,
  mode_label: "RECORDED RUN", benchmark_beaten: false,
}));

type Ctx = { params: Promise<{ path: string[] }> };

const readOnly = () => Response.json({ detail: "Read-only demo: showing recorded ARIA sessions. Connect BACKEND_URL to run live research." }, { status: 503 });

function replay(req: Request, record: ReplayRecord, [, , sub, eid]: string[]) {
  if (req.method !== "GET") return Response.json({ detail: "Recorded sessions are read-only." }, { status: 409 });
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
  return Response.json({ detail: "Not available for recorded sessions." }, { status: 404 });
}

async function proxy(req: Request, path: string[]) {
  const res = await fetch(`${BACKEND}/api/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`, {
    method: req.method,
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
    body: ["GET", "HEAD"].includes(req.method) ? undefined : await req.text(),
    cache: "no-store",
  });
  const headers = new Headers({ "content-type": res.headers.get("content-type") ?? "application/json" });
  const disposition = res.headers.get("content-disposition");
  if (disposition) headers.set("content-disposition", disposition);
  return new Response(res.body, { status: res.status, headers });
}

async function handle(req: Request, { params }: Ctx) {
  const path = (await params).path;
  const [root, id] = path;
  const record = root === "sessions" && id ? BY_ID.get(id) : undefined;
  if (record) return replay(req, record, path);
  if (!BACKEND) {
    if (req.method !== "GET") return readOnly();
    if (root === "health") return Response.json({ ok: true, aria_mode_default: "replay", canonical_ready: false, wandb_project: "", credential_present: false });
    if (root === "sessions" && !id) return Response.json(SUMMARIES);
    if (root === "sessions") return Response.json({ detail: "unknown session" }, { status: 404 });
    return readOnly();
  }
  try {
    if (root === "sessions" && !id && req.method === "GET") {
      const live = await fetch(`${BACKEND}/api/sessions`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : [])).catch(() => []);
      return Response.json([...live, ...SUMMARIES]);
    }
    return await proxy(req, path);
  } catch {
    return Response.json({ detail: "Backend unavailable; it may be waking up. Retry in a minute." }, { status: 502 });
  }
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
