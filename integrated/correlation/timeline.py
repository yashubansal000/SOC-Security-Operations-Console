"""Module 5 — Incident Timeline Builder.

Merges an incident's flows, logs, and evidence-linked config changes into
one chronological timeline. Reads Module 1's real schema via SELECT aliases.
"""
import sqlite3
import json

DB_PATH = "data/processed/rca.db"

def get_db_connection():
    """Establish a database connection yielding row objects."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_incident_timeline(incident_id):
    """
    Merges flows, logs, and relevant config changes for a given incident 
    into a single chronological timeline formatted for the UI.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    timeline_events = []
    
    # 1. Fetch anomalous flows linked to this incident
    cursor.execute("""
        SELECT f.flow_id, f.ts as ts, f.host_id as node_id, f.proto, f.service, f.state, f.attack_cat, f.ct_src_dport_ltm
        FROM flows f
        JOIN incident_flows inf ON f.flow_id = inf.flow_id
        WHERE inf.incident_id = ?
    """, (incident_id,))
    flows = cursor.fetchall()
    
    for f in flows:
        timeline_events.append({
            "timestamp": f['ts'],
            "source_type": "flow",
            "node_id": f['node_id'],
            "details": f"Attack Cat: {f['attack_cat']} | Proto: {f['proto']} | Service: {f['service']} | State: {f['state']} | Repeat Src: {f['ct_src_dport_ltm']}",
            "raw_id": f['flow_id']
        })
        
    # 2. Fetch logs tied to those specific flows
    cursor.execute("""
        SELECT l.log_id, l.ts as ts, l.host_id as node_id, l.log_message as log_line
        FROM synthetic_logs l
        JOIN incident_flows inf ON l.log_id = inf.flow_id
        WHERE inf.incident_id = ?
    """, (incident_id,))
    logs = cursor.fetchall()
    
    for l in logs:
        timeline_events.append({
            "timestamp": l['ts'],
            "source_type": "log",
            "node_id": l['node_id'],
            "details": l['log_line'],
            "raw_id": l['log_id']
        })
        
    # 3. Fetch config changes explicitly flagged as evidence (confirmed or correlated)
    cursor.execute("""
        SELECT c.change_id, c.ts as ts, c.host_id as node_id, c.event_description as description
        FROM synthetic_config_changes c
        JOIN evidence e ON c.change_id = e.ref_id
        WHERE e.incident_id = ? AND e.evidence_type IN ('config_change', 'topology_adjacency')
    """, (incident_id,))
    config_changes = cursor.fetchall()
    
    for c in config_changes:
        timeline_events.append({
            "timestamp": c['ts'],
            "source_type": "config_change",
            "node_id": c['node_id'],
            "details": c['description'],
            "raw_id": c['change_id']
        })
        
    conn.close()
    
    # 4. Sort everything chronologically 
    # (ISO8601 strings safely sort alphabetically)
    timeline_events.sort(key=lambda x: x['timestamp'])
    
    return timeline_events

if __name__ == "__main__":
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT incident_id FROM incidents")
    all_incidents = [r['incident_id'] for r in cursor.fetchall()]
    conn.close()

    for inc_id in all_incidents:
        timeline = generate_incident_timeline(inc_id)
        print(f"\n--- Timeline for Incident {inc_id} ---")
        print(json.dumps(timeline, indent=2))