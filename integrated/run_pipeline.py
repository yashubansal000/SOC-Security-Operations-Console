"""
End-to-end orchestrator — runs the full pipeline in order and seeds
hypotheses for every incident. Assumes Module 1's rca.db already exists
(the demo ships with it). Idempotent.

    python run_pipeline.py            # M2 -> M3 -> M4(all incidents)
    python run_pipeline.py --agent    # only re-run M4 over existing incidents
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
DB = ROOT / "data" / "processed" / "rca.db"


def sh(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def seed_all_hypotheses() -> None:
    from adapters.pipeline import generate_hypotheses_for_incident
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ids = [r["incident_id"] for r in conn.execute("SELECT incident_id FROM incidents ORDER BY incident_id")]
    print(f"\nSeeding hypotheses for {len(ids)} incidents...")
    ok = 0
    for iid in ids:
        res = generate_hypotheses_for_incident(conn, iid, actor="system")
        if res:
            ok += 1
    conn.close()
    print(f"Seeded hypotheses for {ok}/{len(ids)} incidents.")


def main() -> None:
    agent_only = "--agent" in sys.argv
    if not agent_only:
        sh([PY, "-m", "db.setup_integration"])
        sh([PY, "ml/train.py"])
        sh([PY, "ml/detect_events.py"])
        sh([PY, "correlation/evidence_engine.py"])
    seed_all_hypotheses()
    print("\nPipeline complete. Start the API with:")
    print("    uvicorn api.main:app --port 8000")


if __name__ == "__main__":
    main()
