"""
Module 7 — API Layer & Audit Trail (FastAPI, single service).

Serves the Incident Command Center dashboard over Module 1's real database
and the Module 4 agent. Every mutating action writes an audit_log row
(spec §7.14, structurally enforced here).

Run from the integrated/ project root:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `uvicorn api.main:app` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.db import get_conn, write_audit
from adapters.pipeline import generate_hypotheses_for_incident
from agent.topology import get_impact_path, full_graph_json
from correlation.timeline import generate_incident_timeline

app = FastAPI(title="Network Anomaly Root-Cause Assistant — API (M7)")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /incidents  — list, filterable
# ---------------------------------------------------------------------------
@app.get("/incidents")
def list_incidents(attack_cat: str | None = None, severity: str | None = None):
    conn = get_conn()
    try:
        q = ("SELECT incident_id, node_id, attack_cat, start_ts, end_ts, "
             "flow_count, severity FROM incidents WHERE 1=1")
        params: list = []
        if attack_cat:
            q += " AND attack_cat = ?"; params.append(attack_cat)
        if severity:
            q += " AND severity = ?"; params.append(severity)
        q += " ORDER BY flow_count DESC"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /incidents/{id}  — full detail: evidence + timeline + hypotheses
# ---------------------------------------------------------------------------
@app.get("/incidents/{incident_id}")
def incident_detail(incident_id: int):
    conn = get_conn()
    try:
        inc = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        if inc is None:
            raise HTTPException(404, f"Incident {incident_id} not found")

        evidence = [dict(r) for r in conn.execute(
            "SELECT evidence_id, bucket, evidence_type, node_id, ref_id, description, "
            "confidence_weight FROM evidence WHERE incident_id = ? ORDER BY "
            "CASE bucket WHEN 'confirmed' THEN 0 WHEN 'correlated' THEN 1 ELSE 2 END",
            (incident_id,),
        ).fetchall()]

        buckets = {"confirmed": [], "correlated": [], "missing": []}
        for e in evidence:
            buckets.setdefault(e["bucket"], []).append(e)

        hyps = [dict(r) for r in conn.execute(
            "SELECT * FROM hypotheses WHERE incident_id = ? ORDER BY rank", (incident_id,)
        ).fetchall()]
        for h in hyps:
            h["evidence_refs"] = json.loads(h["evidence_refs"] or "[]")
            h["next_steps"] = json.loads(h["next_steps"] or "[]")

        return {
            "incident": dict(inc),
            "evidence": evidence,
            "evidence_by_bucket": buckets,
            "timeline": generate_incident_timeline(incident_id),
            "hypotheses": hyps,
            "impact_path": get_impact_path(inc["node_id"]),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /incidents/{id}/hypotheses/regenerate  — re-run M4 (mutating -> audit)
# ---------------------------------------------------------------------------
@app.post("/incidents/{incident_id}/hypotheses/regenerate")
def regenerate(incident_id: int):
    conn = get_conn()
    try:
        result = generate_hypotheses_for_incident(conn, incident_id, actor="system")
        if result is None:
            raise HTTPException(404, f"Incident {incident_id} not found")
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /incidents/{id}/timeline
# ---------------------------------------------------------------------------
@app.get("/incidents/{incident_id}/timeline")
def timeline(incident_id: int):
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM incidents WHERE incident_id=?", (incident_id,)).fetchone() is None:
            raise HTTPException(404, f"Incident {incident_id} not found")
    finally:
        conn.close()
    return generate_incident_timeline(incident_id)


# ---------------------------------------------------------------------------
# GET /incidents/{id}/topology  — impact-path subgraph
# ---------------------------------------------------------------------------
@app.get("/incidents/{incident_id}/topology")
def incident_topology(incident_id: int):
    conn = get_conn()
    try:
        inc = conn.execute("SELECT node_id FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
        if inc is None:
            raise HTTPException(404, f"Incident {incident_id} not found")
        return get_impact_path(inc["node_id"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /incidents/{id}/review  — human approve/reject (mutating -> audit)
# ---------------------------------------------------------------------------
class ReviewInput(BaseModel):
    decision: str          # "approve" | "reject"
    reviewer: str = "reviewer"
    note: str = ""


@app.post("/incidents/{incident_id}/review")
def review(incident_id: int, body: ReviewInput):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be 'approve' or 'reject'")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM incidents WHERE incident_id=?", (incident_id,)).fetchone() is None:
            raise HTTPException(404, f"Incident {incident_id} not found")
        action = "reviewer_approved" if body.decision == "approve" else "reviewer_rejected"
        write_audit(conn, actor=f"reviewer:{body.reviewer}", action=action,
                    incident_id=incident_id, details=body.note)
        return {"status": "ok", "incident_id": incident_id, "action": action}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /audit-log/{incident_id}
# ---------------------------------------------------------------------------
@app.get("/audit-log/{incident_id}")
def audit_log(incident_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT audit_id, ts, actor, action, incident_id, details FROM audit_log "
            "WHERE incident_id = ? ORDER BY audit_id DESC", (incident_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /score  — live single-flow scoring (demo lever, calls M2)
# ---------------------------------------------------------------------------
class FlowInput(BaseModel):
    proto: str = "tcp"
    service: str = "-"
    state: str = "FIN"
    sbytes: int = 0
    dbytes: int = 0
    rate: float = 0.0
    sload: float = 0.0
    dload: float = 0.0
    dur: float = 0.0
    sinpkt: float = 0.0
    dinpkt: float = 0.0
    ct_src_dport_ltm: int = 0
    ct_dst_sport_ltm: int = 0


@app.post("/score")
def score(flow: FlowInput):
    from ml.detect_events import score_flow, explain_flow_shap  # lazy: loads joblibs
    payload = flow.model_dump()
    result = score_flow(payload)
    result["shap"] = explain_flow_shap(payload)[:5]
    conn = get_conn()
    try:
        write_audit(conn, actor="system", action="live_score",
                    details=f"pred={result['attack_cat_pred']} conf={round(result['confidence'],3)}")
    finally:
        conn.close()
    return result


# ---------------------------------------------------------------------------
# GET /stats  — dashboard summary counts
# ---------------------------------------------------------------------------
@app.get("/stats")
def stats():
    conn = get_conn()
    try:
        def one(sql, *a):
            r = conn.execute(sql, a).fetchone()
            return r[0] if r else 0
        return {
            "total_incidents": one("SELECT COUNT(*) FROM incidents"),
            "flows_scored": one("SELECT COUNT(*) FROM anomaly_scores"),
            "anomalous_flows": one("SELECT COUNT(*) FROM anomaly_scores WHERE attack_cat_pred!='Normal'"),
            "evidence_confirmed": one("SELECT COUNT(*) FROM evidence WHERE bucket='confirmed'"),
            "evidence_correlated": one("SELECT COUNT(*) FROM evidence WHERE bucket='correlated'"),
            "evidence_missing": one("SELECT COUNT(*) FROM evidence WHERE bucket='missing'"),
            "hypotheses_generated": one("SELECT COUNT(*) FROM hypotheses"),
            "audit_entries": one("SELECT COUNT(*) FROM audit_log"),
            "by_severity": {r[0]: r[1] for r in conn.execute(
                "SELECT severity, COUNT(*) FROM incidents GROUP BY severity")},
            "by_attack_cat": {r[0]: r[1] for r in conn.execute(
                "SELECT attack_cat, COUNT(*) FROM incidents GROUP BY attack_cat")},
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /audit-log  — global feed (read-only; surfaces existing audit_log rows)
# ---------------------------------------------------------------------------
@app.get("/audit-log")
def audit_log_global(limit: int = 200):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT audit_id, ts, actor, action, incident_id, details FROM audit_log "
            "ORDER BY audit_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /analytics  — read-only aggregations over EXISTING tables only.
# No ML/agent/schema/pipeline change; pure SELECTs surfacing data already in
# rca.db so the dashboard can render real charts instead of fabricated ones.
# ---------------------------------------------------------------------------
@app.get("/analytics")
def analytics():
    conn = get_conn()
    try:
        def dist(sql, *a):
            return {("" if r[0] is None else str(r[0])): r[1] for r in conn.execute(sql, a)}

        # SHAP top-feature frequency via JSON1 (fast; no Python parse of 82k rows)
        try:
            shap_freq = dist(
                "SELECT json_extract(shap_top_features,'$[0].feature') f, COUNT(*) "
                "FROM anomaly_scores WHERE shap_top_features IS NOT NULL GROUP BY f ORDER BY 2 DESC")
        except sqlite3.OperationalError:
            shap_freq = {}  # JSON1 unavailable — chart hidden client-side

        return {
            # --- flow-level (Module 1/2) ---
            "proto_distribution": dist("SELECT proto, COUNT(*) FROM flows GROUP BY proto ORDER BY 2 DESC LIMIT 12"),
            "service_distribution": dist("SELECT service, COUNT(*) FROM flows GROUP BY service ORDER BY 2 DESC LIMIT 12"),
            "state_distribution": dist("SELECT state, COUNT(*) FROM flows GROUP BY state ORDER BY 2 DESC LIMIT 10"),
            "split_distribution": dist("SELECT split, COUNT(*) FROM flows GROUP BY split"),
            "binary_label_distribution": dist(
                "SELECT CASE label WHEN 1 THEN 'Attack' ELSE 'Normal' END, COUNT(*) FROM flows GROUP BY label"),
            # --- ML predictions (Module 2) ---
            "predicted_attack_distribution": dist(
                "SELECT attack_cat_pred, COUNT(*) FROM anomaly_scores GROUP BY attack_cat_pred ORDER BY 2 DESC"),
            "confidence_histogram": dist(
                "SELECT CAST(confidence*10 AS INT)*10 || '%', COUNT(*) FROM anomaly_scores GROUP BY 1 ORDER BY 1"),
            "shap_top_feature_frequency": shap_freq,
            "avg_bytes_by_attack": {r[0]: {"sbytes": round(r[1] or 0), "dbytes": round(r[2] or 0)} for r in conn.execute(
                "SELECT attack_cat, AVG(sbytes), AVG(dbytes) FROM flows WHERE attack_cat!='Normal' GROUP BY attack_cat ORDER BY 2 DESC LIMIT 10")},
            # --- correlation / evidence (Module 3) ---
            "evidence_bucket_distribution": dist("SELECT bucket, COUNT(*) FROM evidence GROUP BY bucket"),
            "evidence_type_distribution": dist("SELECT evidence_type, COUNT(*) FROM evidence GROUP BY evidence_type ORDER BY 2 DESC"),
            "incidents_by_severity": dist("SELECT severity, COUNT(*) FROM incidents GROUP BY severity"),
            "incidents_by_attack": dist("SELECT attack_cat, COUNT(*) FROM incidents GROUP BY attack_cat ORDER BY 2 DESC"),
            "incidents_over_time": dist(
                "SELECT substr(start_ts,12,2)||':00', COUNT(*) FROM incidents GROUP BY 1 ORDER BY 1"),
            "top_affected_hosts": dist("SELECT node_id, COUNT(*) FROM incidents GROUP BY node_id ORDER BY 2 DESC LIMIT 10"),
            "host_severity_breakdown": [
                {"host": r[0], "severity": r[1], "count": r[2]} for r in conn.execute(
                    "SELECT node_id, severity, COUNT(*) FROM incidents GROUP BY node_id, severity ORDER BY node_id")],
            "config_changes_by_severity": dist("SELECT severity, COUNT(*) FROM synthetic_config_changes GROUP BY severity"),
            "config_changes_by_host": dist("SELECT host_id, COUNT(*) FROM synthetic_config_changes GROUP BY host_id ORDER BY 2 DESC LIMIT 10"),
            # --- agent (Module 4) ---
            "root_cause_frequency": dist("SELECT root_cause_node, COUNT(*) FROM hypotheses WHERE confidence_pct>5 GROUP BY root_cause_node ORDER BY 2 DESC LIMIT 10"),
            "hypothesis_confidence_histogram": dist(
                "SELECT CAST(confidence_pct/10 AS INT)*10 || '%', COUNT(*) FROM hypotheses GROUP BY 1 ORDER BY 1"),
            # --- audit (Module 7) ---
            "audit_action_distribution": dist("SELECT action, COUNT(*) FROM audit_log GROUP BY action ORDER BY 2 DESC"),
            "reviewer_actions": dist("SELECT action, COUNT(*) FROM audit_log WHERE actor LIKE 'reviewer%' GROUP BY action"),
            # --- topology (Module 1) ---
            "topology_summary": {
                "nodes": conn.execute("SELECT COUNT(*) FROM synthetic_topology").fetchone()[0],
                "edges": conn.execute("SELECT COUNT(*) FROM topology").fetchone()[0],
            },
        }
    finally:
        conn.close()


# --- Serve the dashboard ----------------------------------------------------
frontend_dir = PROJECT_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(str(frontend_dir / "index.html"))


# """
# Module 7 — API Layer & Audit Trail (FastAPI, single service).

# Serves the Incident Command Center dashboard over Module 1's real database
# and the Module 4 agent. Every mutating action writes an audit_log row
# (spec §7.14, structurally enforced here).

# Run from the integrated/ project root:
#     uvicorn api.main:app --reload --port 8000
# """

# from __future__ import annotations

# import json
# import sys
# from pathlib import Path

# # Allow `uvicorn api.main:app` from the project root.
# PROJECT_ROOT = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(PROJECT_ROOT))

# from dotenv import load_dotenv
# load_dotenv(PROJECT_ROOT / ".env")

# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import FileResponse
# from pydantic import BaseModel

# from api.db import get_conn, write_audit
# from adapters.pipeline import generate_hypotheses_for_incident
# from agent.topology import get_impact_path, full_graph_json
# from correlation.timeline import generate_incident_timeline

# app = FastAPI(title="Network Anomaly Root-Cause Assistant — API (M7)")
# app.add_middleware(
#     CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
# )


# # ---------------------------------------------------------------------------
# # GET /health - API health check
# # ---------------------------------------------------------------------------
# @app.get("/health")
# def health_check():
#     return {"status": "ok"}

# # ---------------------------------------------------------------------------
# # GET /incidents  — list, filterable
# # ---------------------------------------------------------------------------
# @app.get("/incidents")
# def list_incidents(attack_cat: str | None = None, severity: str | None = None):
#     conn = get_conn()
#     try:
#         q = ("SELECT incident_id, node_id, attack_cat, start_ts, end_ts, "
#              "flow_count, severity FROM incidents WHERE 1=1")
#         params: list = []
#         if attack_cat:
#             q += " AND attack_cat = ?"; params.append(attack_cat)
#         if severity:
#             q += " AND severity = ?"; params.append(severity)
#         q += " ORDER BY flow_count DESC"
#         rows = conn.execute(q, params).fetchall()
#         return [dict(r) for r in rows]
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # GET /incidents/{id}  — full detail: evidence + timeline + hypotheses
# # ---------------------------------------------------------------------------
# @app.get("/incidents/{incident_id}")
# def incident_detail(incident_id: int):
#     conn = get_conn()
#     try:
#         inc = conn.execute(
#             "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
#         ).fetchone()
#         if inc is None:
#             raise HTTPException(404, f"Incident {incident_id} not found")

#         evidence = [dict(r) for r in conn.execute(
#             "SELECT evidence_id, bucket, evidence_type, node_id, ref_id, description, "
#             "confidence_weight FROM evidence WHERE incident_id = ? ORDER BY "
#             "CASE bucket WHEN 'confirmed' THEN 0 WHEN 'correlated' THEN 1 ELSE 2 END",
#             (incident_id,),
#         ).fetchall()]

#         buckets = {"confirmed": [], "correlated": [], "missing": []}
#         for e in evidence:
#             buckets.setdefault(e["bucket"], []).append(e)

#         hyps = [dict(r) for r in conn.execute(
#             "SELECT * FROM hypotheses WHERE incident_id = ? ORDER BY rank", (incident_id,)
#         ).fetchall()]
#         for h in hyps:
#             h["evidence_refs"] = json.loads(h["evidence_refs"] or "[]")
#             h["next_steps"] = json.loads(h["next_steps"] or "[]")

#         return {
#             "incident": dict(inc),
#             "evidence": evidence,
#             "evidence_by_bucket": buckets,
#             "timeline": generate_incident_timeline(incident_id),
#             "hypotheses": hyps,
#             "impact_path": get_impact_path(inc["node_id"]),
#         }
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # POST /incidents/{id}/hypotheses/regenerate  — re-run M4 (mutating -> audit)
# # ---------------------------------------------------------------------------
# @app.post("/incidents/{incident_id}/hypotheses/regenerate")
# def regenerate(incident_id: int):
#     conn = get_conn()
#     try:
#         result = generate_hypotheses_for_incident(conn, incident_id, actor="system")
#         if result is None:
#             raise HTTPException(404, f"Incident {incident_id} not found")
#         return result
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # GET /incidents/{id}/timeline
# # ---------------------------------------------------------------------------
# @app.get("/incidents/{incident_id}/timeline")
# def timeline(incident_id: int):
#     conn = get_conn()
#     try:
#         if conn.execute("SELECT 1 FROM incidents WHERE incident_id=?", (incident_id,)).fetchone() is None:
#             raise HTTPException(404, f"Incident {incident_id} not found")
#     finally:
#         conn.close()
#     return generate_incident_timeline(incident_id)


# # ---------------------------------------------------------------------------
# # GET /incidents/{id}/topology  — impact-path subgraph
# # ---------------------------------------------------------------------------
# @app.get("/incidents/{incident_id}/topology")
# def incident_topology(incident_id: int):
#     conn = get_conn()
#     try:
#         inc = conn.execute("SELECT node_id FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
#         if inc is None:
#             raise HTTPException(404, f"Incident {incident_id} not found")
#         return get_impact_path(inc["node_id"])
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # POST /incidents/{id}/review  — human approve/reject (mutating -> audit)
# # ---------------------------------------------------------------------------
# class ReviewInput(BaseModel):
#     decision: str          # "approve" | "reject"
#     reviewer: str = "reviewer"
#     note: str = ""


# @app.post("/incidents/{incident_id}/review")
# def review(incident_id: int, body: ReviewInput):
#     if body.decision not in ("approve", "reject"):
#         raise HTTPException(422, "decision must be 'approve' or 'reject'")
#     conn = get_conn()
#     try:
#         if conn.execute("SELECT 1 FROM incidents WHERE incident_id=?", (incident_id,)).fetchone() is None:
#             raise HTTPException(404, f"Incident {incident_id} not found")
#         action = "reviewer_approved" if body.decision == "approve" else "reviewer_rejected"
#         write_audit(conn, actor=f"reviewer:{body.reviewer}", action=action,
#                     incident_id=incident_id, details=body.note)
#         return {"status": "ok", "incident_id": incident_id, "action": action}
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # GET /audit-log/{incident_id}
# # ---------------------------------------------------------------------------
# @app.get("/audit-log/{incident_id}")
# def audit_log(incident_id: int):
#     conn = get_conn()
#     try:
#         rows = conn.execute(
#             "SELECT audit_id, ts, actor, action, incident_id, details FROM audit_log "
#             "WHERE incident_id = ? ORDER BY audit_id DESC", (incident_id,)
#         ).fetchall()
#         return [dict(r) for r in rows]
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # POST /score  — live single-flow scoring (demo lever, calls M2)
# # ---------------------------------------------------------------------------
# class FlowInput(BaseModel):
#     proto: str = "tcp"
#     service: str = "-"
#     state: str = "FIN"
#     sbytes: int = 0
#     dbytes: int = 0
#     rate: float = 0.0
#     sload: float = 0.0
#     dload: float = 0.0
#     dur: float = 0.0
#     sinpkt: float = 0.0
#     dinpkt: float = 0.0
#     ct_src_dport_ltm: int = 0
#     ct_dst_sport_ltm: int = 0


# @app.post("/score")
# def score(flow: FlowInput):
#     from ml.detect_events import score_flow, explain_flow_shap  # lazy: loads joblibs
#     payload = flow.model_dump()
#     result = score_flow(payload)
#     result["shap"] = explain_flow_shap(payload)[:5]
#     conn = get_conn()
#     try:
#         write_audit(conn, actor="system", action="live_score",
#                     details=f"pred={result['attack_cat_pred']} conf={round(result['confidence'],3)}")
#     finally:
#         conn.close()
#     return result


# # ---------------------------------------------------------------------------
# # GET /stats  — dashboard summary counts
# # ---------------------------------------------------------------------------
# @app.get("/stats")
# def stats():
#     conn = get_conn()
#     try:
#         def one(sql, *a):
#             r = conn.execute(sql, a).fetchone()
#             return r[0] if r else 0
#         return {
#             "total_incidents": one("SELECT COUNT(*) FROM incidents"),
#             "flows_scored": one("SELECT COUNT(*) FROM anomaly_scores"),
#             "anomalous_flows": one("SELECT COUNT(*) FROM anomaly_scores WHERE attack_cat_pred!='Normal'"),
#             "evidence_confirmed": one("SELECT COUNT(*) FROM evidence WHERE bucket='confirmed'"),
#             "evidence_correlated": one("SELECT COUNT(*) FROM evidence WHERE bucket='correlated'"),
#             "evidence_missing": one("SELECT COUNT(*) FROM evidence WHERE bucket='missing'"),
#             "hypotheses_generated": one("SELECT COUNT(*) FROM hypotheses"),
#             "audit_entries": one("SELECT COUNT(*) FROM audit_log"),
#             "by_severity": {r[0]: r[1] for r in conn.execute(
#                 "SELECT severity, COUNT(*) FROM incidents GROUP BY severity")},
#             "by_attack_cat": {r[0]: r[1] for r in conn.execute(
#                 "SELECT attack_cat, COUNT(*) FROM incidents GROUP BY attack_cat")},
#         }
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # GET /audit-log  — global feed (read-only; surfaces existing audit_log rows)
# # ---------------------------------------------------------------------------
# @app.get("/audit-log")
# def audit_log_global(limit: int = 200):
#     conn = get_conn()
#     try:
#         rows = conn.execute(
#             "SELECT audit_id, ts, actor, action, incident_id, details FROM audit_log "
#             "ORDER BY audit_id DESC LIMIT ?", (limit,)
#         ).fetchall()
#         return [dict(r) for r in rows]
#     finally:
#         conn.close()


# # ---------------------------------------------------------------------------
# # GET /analytics  — read-only aggregations over EXISTING tables only.
# # No ML/agent/schema/pipeline change; pure SELECTs surfacing data already in
# # rca.db so the dashboard can render real charts instead of fabricated ones.
# # ---------------------------------------------------------------------------
# @app.get("/analytics")
# def analytics():
#     conn = get_conn()
#     try:
#         def dist(sql, *a):
#             return {("" if r[0] is None else str(r[0])): r[1] for r in conn.execute(sql, a)}

#         # SHAP top-feature frequency via JSON1 (fast; no Python parse of 82k rows)
#         try:
#             shap_freq = dist(
#                 "SELECT json_extract(shap_top_features,'$[0].feature') f, COUNT(*) "
#                 "FROM anomaly_scores WHERE shap_top_features IS NOT NULL GROUP BY f ORDER BY 2 DESC")
#         except sqlite3.OperationalError:
#             shap_freq = {}  # JSON1 unavailable — chart hidden client-side

#         return {
#             # --- flow-level (Module 1/2) ---
#             "proto_distribution": dist("SELECT proto, COUNT(*) FROM flows GROUP BY proto ORDER BY 2 DESC LIMIT 12"),
#             "service_distribution": dist("SELECT service, COUNT(*) FROM flows GROUP BY service ORDER BY 2 DESC LIMIT 12"),
#             "state_distribution": dist("SELECT state, COUNT(*) FROM flows GROUP BY state ORDER BY 2 DESC LIMIT 10"),
#             "split_distribution": dist("SELECT split, COUNT(*) FROM flows GROUP BY split"),
#             "binary_label_distribution": dist(
#                 "SELECT CASE label WHEN 1 THEN 'Attack' ELSE 'Normal' END, COUNT(*) FROM flows GROUP BY label"),
#             # --- ML predictions (Module 2) ---
#             "predicted_attack_distribution": dist(
#                 "SELECT attack_cat_pred, COUNT(*) FROM anomaly_scores GROUP BY attack_cat_pred ORDER BY 2 DESC"),
#             "confidence_histogram": dist(
#                 "SELECT CAST(confidence*10 AS INT)*10 || '%', COUNT(*) FROM anomaly_scores GROUP BY 1 ORDER BY 1"),
#             "shap_top_feature_frequency": shap_freq,
#             "avg_bytes_by_attack": {r[0]: {"sbytes": round(r[1] or 0), "dbytes": round(r[2] or 0)} for r in conn.execute(
#                 "SELECT attack_cat, AVG(sbytes), AVG(dbytes) FROM flows WHERE attack_cat!='Normal' GROUP BY attack_cat ORDER BY 2 DESC LIMIT 10")},
#             # --- correlation / evidence (Module 3) ---
#             "evidence_bucket_distribution": dist("SELECT bucket, COUNT(*) FROM evidence GROUP BY bucket"),
#             "evidence_type_distribution": dist("SELECT evidence_type, COUNT(*) FROM evidence GROUP BY evidence_type ORDER BY 2 DESC"),
#             "incidents_by_severity": dist("SELECT severity, COUNT(*) FROM incidents GROUP BY severity"),
#             "incidents_by_attack": dist("SELECT attack_cat, COUNT(*) FROM incidents GROUP BY attack_cat ORDER BY 2 DESC"),
#             "incidents_over_time": dist(
#                 "SELECT substr(start_ts,12,2)||':00', COUNT(*) FROM incidents GROUP BY 1 ORDER BY 1"),
#             "top_affected_hosts": dist("SELECT node_id, COUNT(*) FROM incidents GROUP BY node_id ORDER BY 2 DESC LIMIT 10"),
#             "host_severity_breakdown": [
#                 {"host": r[0], "severity": r[1], "count": r[2]} for r in conn.execute(
#                     "SELECT node_id, severity, COUNT(*) FROM incidents GROUP BY node_id, severity ORDER BY node_id")],
#             "config_changes_by_severity": dist("SELECT severity, COUNT(*) FROM synthetic_config_changes GROUP BY severity"),
#             "config_changes_by_host": dist("SELECT host_id, COUNT(*) FROM synthetic_config_changes GROUP BY host_id ORDER BY 2 DESC LIMIT 10"),
#             # --- agent (Module 4) ---
#             "root_cause_frequency": dist("SELECT root_cause_node, COUNT(*) FROM hypotheses WHERE confidence_pct>5 GROUP BY root_cause_node ORDER BY 2 DESC LIMIT 10"),
#             "hypothesis_confidence_histogram": dist(
#                 "SELECT CAST(confidence_pct/10 AS INT)*10 || '%', COUNT(*) FROM hypotheses GROUP BY 1 ORDER BY 1"),
#             # --- audit (Module 7) ---
#             "audit_action_distribution": dist("SELECT action, COUNT(*) FROM audit_log GROUP BY action ORDER BY 2 DESC"),
#             "reviewer_actions": dist("SELECT action, COUNT(*) FROM audit_log WHERE actor LIKE 'reviewer%' GROUP BY action"),
#             # --- topology (Module 1) ---
#             "topology_summary": {
#                 "nodes": conn.execute("SELECT COUNT(*) FROM synthetic_topology").fetchone()[0],
#                 "edges": conn.execute("SELECT COUNT(*) FROM topology").fetchone()[0],
#             },
#         }
#     finally:
#         conn.close()


# # --- Serve the dashboard ----------------------------------------------------
# frontend_dir = PROJECT_ROOT / "frontend" / "dist"
# app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

# @app.get("/")
# def index():
#     return FileResponse(str(frontend_dir / "index.html"))