"""ARIA Research Analyst: a tool-using agent over the live app, traced to the Weave Agents tab.

An LLM served by W&B Inference answers questions about the recorded research by calling the app's
read-only API as tools. Every conversation, LLM call and tool call is logged with Weave's agent
tracing API, so it appears under Weave -> Agents / Conversations.

    pip install weave openai
    WANDB_API_KEY=... python scripts/research_agent.py                 # runs the demo questions
    WANDB_API_KEY=... python scripts/research_agent.py "your question"
"""
import json
import os
import sys
import urllib.request
from urllib.parse import quote

import weave
from openai import OpenAI
from weave.conversation import Message, Usage

APP = os.environ.get("APP_URL", "https://arian-os.vercel.app")
ENTITY = os.environ.get("WANDB_ENTITY", "roshnikobular02-bu")
PROJECT = os.environ.get("WANDB_PROJECT", "arian-os")
MODEL = os.environ.get("AGENT_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507")
AGENT = "ARIA Research Analyst"
SYSTEM = ("You analyse an autonomous ML research study in which W&B's ARIA agent tried to beat the WildfireIA "
          "benchmark (0.533 published TEST AUPRC). Session scores are VALIDATION AUPRC on 2019 and are not comparable "
          "to the test benchmark. Use the tools to look up facts; never invent numbers. Answer concisely.")

llm = OpenAI(base_url="https://api.inference.wandb.ai/v1", api_key=os.environ["WANDB_API_KEY"], project=f"{ENTITY}/{PROJECT}")


def _get(path):
    with urllib.request.urlopen(APP + path, timeout=90) as r:
        return json.load(r)


def list_sessions():
    return [{k: s[k] for k in ("id", "status", "current_best_auprc", "budget")} for s in _get("/api/sessions")]


def get_session(session_id):
    v = _get("/api/sessions/" + quote(session_id))
    return {"session": session_id, "final_decision": v["session"].get("final_decision"),
            "experiments": [{k: e.get(k) for k in ("id", "change_summary", "score", "delta", "decision", "decision_reason")}
                            for e in v["experiments"]]}


def get_experiment(session_id, experiment_id):
    e = _get(f"/api/sessions/{quote(session_id)}/experiments/{quote(experiment_id)}")
    p, r = e.get("proposal") or {}, e.get("result") or {}
    return {"experiment": e["experiment"], "hypothesis": p.get("hypothesis"), "observation": p.get("observation"),
            "decision": e.get("decision"), "reason": e.get("decision_reason"), "learning": e.get("decision_learning"),
            "validation_auprc": r.get("validation_auprc"), "train_auprc": r.get("train_auprc"),
            "false_negatives": r.get("false_negative_count"), "false_positives": r.get("false_positive_count")}


def list_benchmarks():
    items = _get("/api/benchmarks").get("items", [])
    return [{"title": b.get("title"), "id": b.get("id"), "executable": (b.get("compatibility") or {}).get("executable")} for b in items]


TOOLS = {f.__name__: f for f in (list_sessions, get_session, get_experiment, list_benchmarks)}
SID = {"session_id": {"type": "string"}}
SCHEMAS = [
    {"type": "function", "function": {"name": "list_sessions", "description": "List recorded research sessions with best validation AUPRC.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_session", "description": "Experiments in a session with scores and ARIA's KEEP/REJECT decisions.", "parameters": {"type": "object", "properties": SID, "required": ["session_id"]}}},
    {"type": "function", "function": {"name": "get_experiment", "description": "One experiment: ARIA's hypothesis, config, metrics and decision.", "parameters": {"type": "object", "properties": SID | {"experiment_id": {"type": "string"}}, "required": ["session_id", "experiment_id"]}}},
    {"type": "function", "function": {"name": "list_benchmarks", "description": "Benchmarks in the library and whether research can run on them.", "parameters": {"type": "object", "properties": {}}}},
]


def ask(question, max_steps=8):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    with weave.start_conversation(agent_name=AGENT, model=MODEL, conversation_name=question[:80]) as convo:
        with convo.start_turn(user_message=question, agent_name=AGENT, model=MODEL, system_instructions=[SYSTEM]) as turn:
            for _ in range(max_steps):
                with turn.start_llm(model=MODEL, provider_name="wandb-inference") as span:
                    resp = llm.chat.completions.create(model=MODEL, messages=messages, tools=SCHEMAS)
                    msg = resp.choices[0].message
                    calls = msg.tool_calls or []
                    span.record(input_messages=[Message.user(question)],
                                output_messages=[Message.assistant(msg.content or ", ".join(f"{c.function.name}({c.function.arguments})" for c in calls))],
                                usage=Usage(input_tokens=resp.usage.prompt_tokens, output_tokens=resp.usage.completion_tokens),
                                finish_reasons=[resp.choices[0].finish_reason])
                messages.append(msg.model_dump(exclude_none=True))
                if not calls:
                    turn.record(output_messages=[Message.assistant(msg.content or "")])
                    return msg.content
                for c in calls:
                    with turn.start_tool(name=c.function.name, arguments=c.function.arguments, tool_call_id=c.id) as tool:
                        try:
                            out = json.dumps(TOOLS[c.function.name](**json.loads(c.function.arguments or "{}")), default=str)[:12000]
                        except Exception as exc:  # the model sees tool errors and can recover
                            out = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
                        tool.result = out
                    messages.append({"role": "tool", "tool_call_id": c.id, "content": out})
            return "Stopped: step limit reached."


DEMO = [
    "Which research session reached the best validation AUPRC, and what configuration did ARIA recommend there?",
    "In session wf-20260913-live1, what did ARIA try at each step and why did it keep or reject it?",
    "Which benchmarks in the library can run research right now, and why?",
]

if __name__ == "__main__":
    weave.init(f"{ENTITY}/{PROJECT}")
    for q in sys.argv[1:] or DEMO:
        print(f"\nQ: {q}\nA: {ask(q)}")
