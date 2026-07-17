"""Module 3 — Correlation & Evidence Engine.

Clusters M2's anomalous flows into incidents, buckets evidence into
confirmed / correlated / missing, applies the ct_*_ltm repeat-connection
causation signal, and walks Module 1's real topology for impact paths.

Reads Module 1's genuine schema (host_id / ts / event_description) via
SELECT aliases, and the directed `topology` edge table built by
db/setup_integration.py.
"""
import sqlite3
import json
import networkx as nx
from datetime import datetime, timedelta

DB_PATH = "data/processed/rca.db"

def get_db_connection():
    """Establish a database connection yielding row objects."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def build_topology_graph(cursor):
    """
    Pulls the blueprint from the 'topology' table, which is 
    populated dynamically by inject_topology.py.
    """
    G = nx.DiGraph()
    
    # CHANGED: Query the 'topology' table, not 'synthetic_topology'
    cursor.execute("SELECT source_node, target_node FROM topology")
    rows = cursor.fetchall()
    
    for source, target in rows:
        G.add_edge(source, target)
        
    return G

def get_adjacent_nodes(G, node_id):
    """
    Bidirectional adjacency: nodes this node depends on, AND nodes that
    depend on this node. A config change on either side is a valid
    'topology-adjacent' correlation — a change to something you depend
    on is just as causally relevant as a change to something downstream
    of you.
    """
    if node_id not in G:
        return set()
    return set(G.predecessors(node_id)) | set(G.successors(node_id))

def cluster_incidents(time_window_minutes=10, min_anomalies=3):
    """
    Groups anomalous flows into unified incidents using a time-window + shared-node approach.
    Populates both 'incidents' and 'incident_flows' tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Maintain idempotency by clearing tables for clean demo execution
    cursor.execute("DELETE FROM incident_flows")
    cursor.execute("DELETE FROM incidents")

    # Fetch predicted anomalies from the joined flows and anomaly_scores tables
    cursor.execute("""
        SELECT f.flow_id, f.host_id AS node_id, f.ts AS synthetic_ts,
               a.attack_cat_pred, a.confidence
        FROM flows f
        JOIN anomaly_scores a ON f.flow_id = a.flow_id
        WHERE a.attack_cat_pred != 'Normal'
        ORDER BY f.host_id, f.ts
    """)
    anomalies = cursor.fetchall()

    if not anomalies:
        print("No predicted anomalies found in the database to cluster.")
        conn.close()
        return

    current_node = None
    current_cluster = []

    def save_cluster(node_id, cluster_flows):
        categories = [f['attack_cat_pred'] for f in cluster_flows]
        dominant_cat = max(set(categories), key=categories.count)

        flow_count = len(cluster_flows)
        if flow_count >= 15:
            severity = 'critical'
        elif flow_count >= 8:
            severity = 'high'
        else:
            severity = 'medium'

        start_ts = cluster_flows[0]['synthetic_ts']
        end_ts = cluster_flows[-1]['synthetic_ts']

        cursor.execute("""
            INSERT INTO incidents (node_id, attack_cat, start_ts, end_ts, flow_count, severity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (node_id, dominant_cat, start_ts, end_ts, flow_count, severity))

        incident_id = cursor.lastrowid

        for f in cluster_flows:
            cursor.execute("""
                INSERT INTO incident_flows (incident_id, flow_id)
                VALUES (?, ?)
            """, (incident_id, f['flow_id']))

    for row in anomalies:
        node_id = row['node_id']
        ts = datetime.fromisoformat(row['synthetic_ts'])

        if node_id != current_node or (
            current_cluster and
            (ts - datetime.fromisoformat(current_cluster[-1]['synthetic_ts'])).total_seconds() > (time_window_minutes * 60)
        ):
            if len(current_cluster) >= min_anomalies:
                save_cluster(current_node, current_cluster)
            current_node = node_id
            current_cluster = []

        current_cluster.append(row)

    if len(current_cluster) >= min_anomalies:
        save_cluster(current_node, current_cluster)

    conn.commit()
    conn.close()
    print("Successfully clustered anomalies into incidents.")

def classify_evidence(lookback_minutes=30):
    """
    Evaluates incidents against configuration state modifications and routing patterns.
    Populates the contract 'evidence' schema table.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM evidence")

    # build the topology graph ONCE, reused for every incident below
    topo_graph = build_topology_graph(cursor)

    cursor.execute("SELECT incident_id, node_id, start_ts FROM incidents")
    incidents = cursor.fetchall()

    for inc in incidents:
        inc_id = inc['incident_id']
        node_id = inc['node_id']
        start_ts = datetime.fromisoformat(inc['start_ts'])
        lookback_ts = (start_ts - timedelta(minutes=lookback_minutes)).isoformat()

        evidence_found = False

        # 1. Look for Confirmed Evidence: Direct host matching config records
        cursor.execute("""
            SELECT change_id, event_description AS description, ts AS change_ts
            FROM synthetic_config_changes
            WHERE host_id = ? AND ts BETWEEN ? AND ?
        """, (node_id, lookback_ts, inc['start_ts']))
        direct_changes = cursor.fetchall()

        if direct_changes:
            for change in direct_changes:
                cursor.execute("""
                    INSERT INTO evidence (incident_id, bucket, evidence_type, node_id, ref_id, description, confidence_weight)
                    VALUES (?, 'confirmed', 'config_change', ?, ?, ?, 0.95)
                """, (inc_id, node_id, change['change_id'], f"Direct config change on host {node_id}: {change['description']}"))
            evidence_found = True

        # 2. Look for Correlated Evidence: config changes on ANY topology-
        #    adjacent node — nodes this node depends on, OR nodes that
        #    depend on this node. (Bidirectional — a change to a
        #    dependency is just as relevant as a change downstream.)
        if not evidence_found:
            adjacent_nodes = get_adjacent_nodes(topo_graph, node_id)

            for adj_node in adjacent_nodes:
                cursor.execute("""
                    SELECT change_id, event_description AS description
                    FROM synthetic_config_changes
                    WHERE host_id = ? AND ts BETWEEN ? AND ?
                """, (adj_node, lookback_ts, inc['start_ts']))
                adj_changes = cursor.fetchall()

                for change in adj_changes:
                    cursor.execute("""
                        INSERT INTO evidence (incident_id, bucket, evidence_type, node_id, ref_id, description, confidence_weight)
                        VALUES (?, 'correlated', 'topology_adjacency', ?, ?, ?, 0.65)
                    """, (inc_id, adj_node, change['change_id'], f"Topology-adjacent node ({adj_node}) underwent config change: {change['description']}"))
                    evidence_found = True

        # 3. Handle Explicit Missing State Verification
        if not evidence_found:
            cursor.execute("""
                INSERT INTO evidence (incident_id, bucket, evidence_type, node_id, ref_id, description, confidence_weight)
                VALUES (?, 'missing', 'no_config_change_found', ?, NULL, 'No config structural variance located on host or network perimeter topology.', 0.0)
            """, (inc_id, node_id))

        # 4. Extract Causation strengthening metric signals from connection tracking
        cursor.execute("""
            SELECT MAX(f.ct_src_dport_ltm) as max_src, MAX(f.ct_dst_sport_ltm) as max_dst
            FROM flows f
            JOIN incident_flows inf ON f.flow_id = inf.flow_id
            WHERE inf.incident_id = ?
        """, (inc_id,))
        counters = cursor.fetchone()

        if counters and (
            (counters['max_src'] and counters['max_src'] > 12) or
            (counters['max_dst'] and counters['max_dst'] > 12)
        ):
            cursor.execute("""
                INSERT INTO evidence (incident_id, bucket, evidence_type, node_id, ref_id, description, confidence_weight)
                VALUES (?, 'correlated', 'repeat_connection', ?, NULL, ?, 0.75)
            """, (inc_id, node_id, f"Aggressive high repeat network traffic detected (src_dport count: {counters['max_src']}, dst_sport count: {counters['max_dst']})."))

    conn.commit()
    conn.close()
    print("Successfully structured and written classified evidence logs.")

def build_impact_path(node_id):
    """
    Constructs a NetworkX graph structure using comma-separated adjacency attributes.
    Returns dependency mappings matching frontend visual components.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    G = build_topology_graph(cursor)
    conn.close()

    if node_id not in G:
        return {"root_node": node_id, "downstream_nodes": [], "edges": []}

    # Get all nodes that rely directly or indirectly on our compromised node
    descendants = list(nx.descendants(G, node_id))
    subgraph = G.subgraph([node_id] + descendants)

    return {
        "root_node": node_id,
        "downstream_nodes": descendants,
        "edges": [{"source": u, "target": v} for u, v in subgraph.edges()]
    }

if __name__ == "__main__":
    print("Running Correlation & Evidence Engine Modules...")
    
    # 1. Group anomalies into incidents
    cluster_incidents()
    
    # 2. Find and bucket evidence
    classify_evidence()
    
    # 3. AUTOMATIC BATCH PROCESSING
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Find all unique nodes that were involved in an incident
    cursor.execute("SELECT DISTINCT node_id FROM incidents")
    incident_nodes = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    print(f"\nFound {len(incident_nodes)} incidents to analyze. Processing...")
    
    all_impact_paths = {}
    for node in incident_nodes:
        impact = build_impact_path(node)
        all_impact_paths[node] = impact
        # Save or print the path
        print(f"\n--- Impact Path for {node} ---")
        print(json.dumps(impact, indent=2))
        
    # Optional: Save all to a JSON file for your Agent to pick up
    with open('data/processed/all_impact_paths.json', 'w') as f:
        json.dump(all_impact_paths, f, indent=2)
        
    print("\nBatch analysis complete. Results saved to data/processed/all_impact_paths.json")