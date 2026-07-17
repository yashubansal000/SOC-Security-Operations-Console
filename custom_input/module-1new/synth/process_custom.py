"""
Module 1 (Custom Extension) — LLM-Powered ETL
Reads unstructured text (simulating uploaded PDFs/TXTs), uses Groq to extract
topology, flows, AND config-change events, and formats them into the exact
Pandas DataFrames required by the original generate_multisource.py pipeline.

CHANGE: config changes described in the source text (e.g. "a firewall rule
was modified shortly before the spike") are now actually extracted and
written to synthetic_config_changes, instead of relying on M1's random
35%-injection logic (which is a synthetic-UNSW-only mechanism and never
fires for custom uploads describing a specific, real scenario).

Extracted config changes use a RELATIVE lead time (minutes before the
incident), not an absolute clock time - because flows get a synthetic
timestamp inside a fixed fake demo day (assign_timestamps), which has no
relationship to any literal time mentioned in the uploaded text. The
config change's timestamp is computed relative to the flow's actual
assigned synthetic timestamp, so the lookback-window check in
evidence_engine.py can actually match them.
"""

import os
import sys
import json
import uuid
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq

_THIS_DIR = Path(__file__).resolve().parent.parent
_CANDIDATE_ENV_PATHS = [
    _THIS_DIR.parent / ".env",
    _THIS_DIR / ".env",
]
for _env_path in _CANDIDATE_ENV_PATHS:
    if _env_path.exists():
        load_dotenv(_env_path)
        print(f"[process_custom] Loaded environment from {_env_path}")
        break
else:
    print(f"[process_custom] No .env found at {[str(p) for p in _CANDIDATE_ENV_PATHS]} "
          f"- relying on already-exported environment variables instead.")

from synth.generate_multisource import (
    topology_to_networkx,
    topology_to_dataframe,
    assign_timestamps,
    assign_hosts_bulk,
    identify_attack_clusters,
    generate_config_changes,
    generate_logs_bulk,
    write_to_sqlite,
    PROCESSED_DATA_DIR,
    SEED
)

M2_ML_PATH = os.environ.get(
    "M2_ML_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "2" / "ml"),
)
if M2_ML_PATH not in sys.path:
    sys.path.insert(0, M2_ML_PATH)

try:
    from predict import predict_single
except ImportError as e:
    raise ImportError(
        f"Could not import predict_single from '{M2_ML_PATH}'. "
        f"Set the M2_ML_PATH environment variable to the correct absolute "
        f"path of Module 2's ml/ folder, e.g.:\n"
        f"  export M2_ML_PATH=/full/path/to/combined/2/ml"
    ) from e

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

NUMERIC_FEATURE_COLS = [
    "sbytes", "dbytes", "rate", "sload", "dload",
    "dur", "sinpkt", "dinpkt", "ct_src_dport_ltm", "ct_dst_sport_ltm",
]

EXTRACTION_PROMPT = """You are a highly precise data extraction agent.
I will provide you with raw text extracted from IT documentation (network diagrams, logs, incident notes).
Extract this information into a structured JSON format containing a topology, network flows, and
any described configuration-change events.

CRITICAL RULES:
- "attack_cat" must be "Normal" unless the text implies a specific attack (e.g., "DoS", "Reconnaissance").
- If the text is missing specific categorical fields (proto/service/state), infer safe defaults (e.g., proto="tcp", state="CON", service="-").
- For the numeric fields (sbytes, dbytes, rate, sload, dload, dur, sinpkt, dinpkt, ct_src_dport_ltm, ct_dst_sport_ltm): ONLY fill these in if the source text actually states or clearly implies a real number. If the text gives no basis for a numeric field, set it to null - do NOT guess or invent a plausible-sounding number.
- "tier" should be things like "web", "db", "firewall", "app".
- For config_changes: only include an entry if the text explicitly describes a configuration/infrastructure change event (e.g. "a firewall rule was modified", "SSH config changed", "TLS cert rotated"). "node" must exactly match one of the topology node names you extracted. "lead_minutes_before_incident" is a ROUGH RELATIVE estimate of how many minutes before the anomalous traffic this change happened, based on phrasing in the text (e.g. "shortly after" -> a small number like 2-5, "an hour before" -> 60). If the text gives no timing cue at all, use 5 as a default. Do NOT try to extract or use absolute clock times (like "09:12") - only the relative gap matters.

Respond ONLY with a JSON object in exactly this structure:
{
  "topology": {
    "node_name_1": {"tier": "string", "services": ["string"], "upstream": ["string"]},
    "node_name_2": {"tier": "string", "services": ["string"], "upstream": ["string"]}
  },
  "flows": [
    {
      "proto": "string", "service": "string", "state": "string", "attack_cat": "string",
      "sbytes": null, "dbytes": null, "rate": null, "sload": null, "dload": null,
      "dur": null, "sinpkt": null, "dinpkt": null, "ct_src_dport_ltm": null, "ct_dst_sport_ltm": null
    }
  ],
  "config_changes": [
    {"node": "string", "description": "string", "lead_minutes_before_incident": 5, "severity": "INFO"}
  ]
}
"""


def extract_with_groq(raw_text: str) -> dict:
    """Sends raw text to Groq and returns structured JSON."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable missing.")

    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You output strict JSON. No markdown fences."},
            {"role": "user", "content": f"{EXTRACTION_PROMPT}\n\nRAW TEXT:\n{raw_text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    return json.loads(response.choices[0].message.content)


def _build_config_changes_df(
    config_changes_list: list,
    topology_dict: dict,
    flows_df: pd.DataFrame,
) -> pd.DataFrame:
    """Builds the config_changes DataFrame matching M1's real schema
    (change_id, ts, host_id, event_description, severity), using a
    RELATIVE lead time computed against each affected node's earliest
    assigned synthetic flow timestamp - not an absolute clock time from
    the source text, which has no relationship to the fake demo-day
    timestamps assign_timestamps() produces."""
    records = []
    change_id = 1

    # earliest synthetic ts per host, to anchor "N minutes before" against
    earliest_ts_by_host = (
        flows_df.groupby("host_id")["ts"]
        .min()
        .to_dict()
    )

    for cc in config_changes_list:
        node = cc.get("node")
        if node not in topology_dict:
            print(f"[process_custom_upload] Skipping config_change on unknown node '{node}' "
                  f"(not in extracted topology).")
            continue

        anchor_ts_str = earliest_ts_by_host.get(node)
        if anchor_ts_str is None:
            # no flow landed on this exact node - anchor against the
            # earliest flow overall instead, so we still get a plausible
            # ordering rather than dropping the config change entirely
            if flows_df.empty:
                continue
            anchor_ts_str = flows_df["ts"].min()

        anchor_dt = datetime.fromisoformat(anchor_ts_str)
        lead_minutes = cc.get("lead_minutes_before_incident")
        try:
            lead_minutes = float(lead_minutes) if lead_minutes is not None else 5.0
        except (TypeError, ValueError):
            lead_minutes = 5.0

        change_ts = anchor_dt - timedelta(minutes=lead_minutes)

        records.append({
            "change_id": change_id,
            "ts": change_ts.isoformat(timespec="seconds"),
            "host_id": node,
            "event_description": cc.get("description", "Configuration change (details unspecified)."),
            "severity": cc.get("severity", "INFO"),
        })
        change_id += 1

    if not records:
        return pd.DataFrame({
            "change_id": pd.Series(dtype="int64"),
            "ts": pd.Series(dtype="object"),
            "host_id": pd.Series(dtype="object"),
            "event_description": pd.Series(dtype="object"),
            "severity": pd.Series(dtype="object"),
        })

    return pd.DataFrame.from_records(records)


def process_custom_upload(raw_text: str):
    """
    Processes custom upload, scores each flow against the trained M2 model,
    extracts REAL config-change events described in the text, creates a
    unique database file for this session (for M3's correlation engine),
    and returns the session details plus any anomalous incidents.
    """
    session_id = str(uuid.uuid4())[:8]
    unique_db_path = PROCESSED_DATA_DIR / f"rca_{session_id}.db"

    extracted_data = extract_with_groq(raw_text)

    topology_dict = extracted_data.get("topology", {})
    flows_list = extracted_data.get("flows", [])
    config_changes_list = extracted_data.get("config_changes", [])

    if not topology_dict or not flows_list:
        raise ValueError("Upload rejected: Could not extract both topology and flow logs.")

    for node, meta in topology_dict.items():
        upstream = meta.get("upstream", [])
        valid_upstream = [u for u in upstream if u in topology_dict]
        meta["upstream"] = valid_upstream

    graph = topology_to_networkx(topology_dict)
    topology_df = topology_to_dataframe(topology_dict, graph)

    df = pd.DataFrame(flows_list)

    for col in NUMERIC_FEATURE_COLS:
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")

    n_estimated = int(df[NUMERIC_FEATURE_COLS].isna().any(axis=1).sum())
    if n_estimated:
        print(f"[process_custom_upload] {n_estimated}/{len(df)} flow(s) have at least "
              f"one numeric feature Groq could not extract - predict_single() will "
              f"fill those with the training median and log a warning per field.")

    df["split"] = "custom"
    df["label"] = df["attack_cat"].apply(lambda x: 0 if str(x).lower() == "normal" else 1)

    df["ts"] = assign_timestamps(df)
    df["host_id"] = assign_hosts_bulk(df, topology_dict)

    df = df.reset_index(drop=True)
    df["flow_id"] = df.index.astype("int64")

    incident_objects = []
    for _, row in df.iterrows():
        record = row.where(pd.notnull(row), None).to_dict()
        try:
            ticket = predict_single(record, orig_idx=int(row["flow_id"]))
        except Exception as e:
            print(f"[process_custom_upload] predict_single failed for flow_id="
                  f"{row['flow_id']}: {e}")
            continue
        if ticket is not None:
            ticket["incident_id"] = f"{session_id}-{ticket['incident_id']}"
            ticket["host_id"] = row["host_id"]
            incident_objects.append(ticket)

    df[NUMERIC_FEATURE_COLS] = df[NUMERIC_FEATURE_COLS].fillna(0.0)

    # NEW: real config-change extraction, replacing the random-injection
    # generate_config_changes() call for custom uploads specifically.
    config_changes_df = _build_config_changes_df(config_changes_list, topology_dict, df)
    n_config_changes = len(config_changes_df)
    print(f"[process_custom_upload] Extracted {n_config_changes} real config-change "
          f"event(s) from the uploaded text.")

    clusters_df = identify_attack_clusters(df)   # kept for log-generation compatibility
    logs_df = generate_logs_bulk(df)

    write_to_sqlite(unique_db_path, df, topology_df, config_changes_df, logs_df)

    return {
        "status": "success",
        "session_id": session_id,
        "db_path": str(unique_db_path),
        "nodes_extracted": len(topology_dict),
        "flows_extracted": len(flows_list),
        "flows_with_estimated_numerics": n_estimated,
        "config_changes_extracted": n_config_changes,
        "anomalous_incidents": incident_objects,
    }