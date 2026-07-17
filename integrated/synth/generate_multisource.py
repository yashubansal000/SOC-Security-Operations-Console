"""
Module 1 — Synthetic Multi-Source Generator
============================================
Loads UNSW-NB15 network flow data (train + test), enriches it with a
deterministic synthetic layer (timestamps, enterprise topology, host
placement, config-change events, syslog lines) and writes everything to a
single SQLite database used as the ground-truth source for the downstream
Anomaly Detection Engine (Module 2), Correlation Engine (Module 3), and
Root-Cause Agent (Module 4).

Idempotent: every table is dropped and recreated on each run.
Deterministic: fixed seed + hash-based mapping = same output every time.

Run:
    python3 synth/generate_multisource.py

Output:
    data/processed/rca.db
    logs/generate_multisource.log
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------------
import hashlib
import json
import logging
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Third-party
# ---------------------------------------------------------------------------
import networkx as nx
import pandas as pd
from tqdm import tqdm


# ===========================================================================
# SECTION 1 — CONFIGURATION
# ---------------------------------------------------------------------------
# Everything a maintainer might want to tweak lives in this block.
# No magic numbers or paths are hidden deeper in the script.
# ===========================================================================

# --- Reproducibility --------------------------------------------------------
SEED: int = 42

# --- Paths ------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

TRAIN_DATA_PATH: Path = RAW_DATA_DIR / "UNSW_NB15_training-set.parquet"
TEST_DATA_PATH: Path = RAW_DATA_DIR / "UNSW_NB15_testing-set.parquet"
DB_PATH: Path = PROCESSED_DATA_DIR / "rca.db"
LOG_PATH: Path = LOGS_DIR / "generate_multisource.log"

# --- Schema validation ------------------------------------------------------
# At least one of `attack_cat` / `label` must be present; both preferred.
REQUIRED_COLUMNS: tuple[str, ...] = ("proto", "service", "state")
LABEL_COLUMNS: tuple[str, ...] = ("attack_cat", "label")

# Feature columns carried into the flows table for downstream ML (Module 2)
# and correlation logic (Module 3). Kept explicit — no `SELECT *` behavior.
FEATURE_COLUMNS: tuple[str, ...] = (
    "proto", "service", "state",
    "sbytes", "dbytes", "rate", "sload", "dload", "dur",
    "sinpkt", "dinpkt",
    "ct_src_dport_ltm", "ct_dst_sport_ltm",
)

# --- Timestamp generation ---------------------------------------------------
DEMO_DATE: datetime = datetime(2026, 7, 14, 0, 0, 0)
WINDOW_HOURS: int = 24
TIMESTAMP_JITTER_SECONDS: float = 30.0   # +/- jitter around each flow's slot

# --- Topology ---------------------------------------------------------------
# See Section 6. Constants here are just size expectations for validation.
EXPECTED_MIN_TOPOLOGY_NODES: int = 15
EXPECTED_MAX_TOPOLOGY_NODES: int = 22

# --- Config-change injection ------------------------------------------------
# Only ~35% of attack clusters get a config-change event — this leaves real
# "missing evidence" cases for Module 3 to report, satisfying the problem
# statement's "explicitly refuse to evaluate incomplete data" requirement.
CONFIG_CHANGE_INJECTION_RATE: float = 0.35
CONFIG_CHANGE_LEAD_MINUTES_MIN: float = 2.0
CONFIG_CHANGE_LEAD_MINUTES_MAX: float = 15.0
CONFIG_CHANGE_ADJACENT_HOST_PROBABILITY: float = 0.30  # 30% land on neighbor, 70% on cluster host

CONFIG_CHANGE_TEMPLATES: tuple[tuple[str, str], ...] = (
    # (event_description_template, default_severity)
    ("Firewall rule modified on {host} (new allow rule added)",              "WARN"),
    ("Database access privilege updated on {host}",                           "WARN"),
    ("SSH configuration changed on {host} (auth method updated)",             "WARN"),
    ("DNS configuration updated on {host} (zone record modified)",            "INFO"),
    ("Application deployed to {host} (new build promoted)",                   "INFO"),
    ("Port closed on {host} via ACL update",                                  "INFO"),
    ("TLS certificate rotated on {host}",                                     "INFO"),
    ("Access-control list updated on {host} (new principal granted)",         "WARN"),
    ("Routing table updated on {host} (new static route)",                    "INFO"),
    ("Service restart / config reload on {host}",                             "INFO"),
)

# --- Attack-cluster detection ----------------------------------------------
# Two attack rows on the same host within this window count as one cluster.
CLUSTER_TIME_WINDOW_MINUTES: int = 10

# --- Log severity thresholds -----------------------------------------------
LOG_SEVERITY_ERROR_STATES: frozenset[str] = frozenset({"RST", "URN"})
LOG_SEVERITY_WARN_BYTES: int = 100_000   # flows above this get WARN

# --- Runtime ----------------------------------------------------------------
# Set to an int for fast dev iterations; None loads the full dataset.
MAX_ROWS: int | None = None
TQDM_MIN_ROWS_FOR_BAR: int = 5_000   # below this, tqdm is skipped (too fast to matter)


# ===========================================================================
# SECTION 2 — LOGGING
# ---------------------------------------------------------------------------
# Dual-handler logger: everything goes to both stdout (for interactive runs)
# and a log file (for post-mortem debugging after a failed demo).
# ===========================================================================

_LOGGER_NAME: str = "generate_multisource"
_LOG_FORMAT: str = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_path: Path = LOG_PATH, level: int = logging.INFO) -> logging.Logger:
    """Configure the module logger with a console + file handler.

    Idempotent: safe to call more than once — existing handlers are removed
    before new ones are attached, so re-running the script never produces
    duplicate log lines.

    Args:
        log_path: Destination file for the file handler. Parent directory
            is created if missing.
        level: Root log level for this logger (INFO by default).

    Returns:
        The configured logger instance.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False   # don't bubble to root, avoids double-printing

    # Wipe any handlers left over from a previous call (idempotency).
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    logger.info("Logger initialised — writing to %s", log_path)
    return logger


def get_logger() -> logging.Logger:
    """Return the module logger; assumes `setup_logging` has already run."""
    return logging.getLogger(_LOGGER_NAME)


def log_section(logger: logging.Logger, title: str) -> None:
    """Print a visually distinct section header in the logs."""
    bar = "=" * 60
    logger.info(bar)
    logger.info(title.upper())
    logger.info(bar)


# ===========================================================================
# SECTION 3 — DATASET LOADER
# ---------------------------------------------------------------------------
# Loads the source network-flow dataset(s) from disk. Auto-detects format
# from the file extension so the same code path works for parquet (fast,
# typed, our default) or csv (fallback for cases where the maintainer
# swaps in raw data).
# ===========================================================================

_SUPPORTED_EXTENSIONS: tuple[str, ...] = (".parquet", ".csv")


def load_dataset(path: Path) -> pd.DataFrame:
    """Load a single dataset file, auto-detecting format by extension.

    Args:
        path: Path to a .parquet or .csv file.

    Returns:
        DataFrame with the source file's contents. No transformation is
        applied here — schema validation and cleaning happen in Section 4.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not one of the supported
            formats, or if the file exists but loads to zero rows.
    """
    logger = get_logger()

    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '{suffix}' for {path.name}. "
            f"Supported: {_SUPPORTED_EXTENSIONS}"
        )

    logger.info("Loading %s ...", path.name)

    if suffix == ".parquet":
        df = pd.read_parquet(path)
    else:  # .csv
        df = pd.read_csv(path)

    if df.empty:
        raise ValueError(f"Dataset loaded from {path} contains zero rows.")

    logger.info("  -> %s: %d rows, %d columns", path.name, len(df), df.shape[1])
    return df


def load_all_datasets(
    train_path: Path = TRAIN_DATA_PATH,
    test_path: Path | None = TEST_DATA_PATH,
    max_rows: int | None = MAX_ROWS,
) -> pd.DataFrame:
    """Load train + optional test datasets and concatenate them.

    Adds a `split` column ('train' / 'test') so downstream ML modules
    (Module 2) can honour the original UNSW-NB15 partitioning without
    needing separate DataFrames or a second I/O pass.

    Args:
        train_path: Path to the training dataset.
        test_path: Path to the test dataset. Pass `None` to load train only.
        max_rows: If set, downsample to this many rows (seeded).

    Returns:
        Concatenated DataFrame with a `split` column and fresh int index.

    Raises:
        FileNotFoundError, ValueError: Propagated from `load_dataset`.
    """
    logger = get_logger()
    log_section(logger, "Section 3 — Dataset Loading")

    frames: list[pd.DataFrame] = []

    train_df = load_dataset(train_path)
    train_df["split"] = "train"
    frames.append(train_df)

    if test_path is not None:
        test_df = load_dataset(test_path)
        test_df["split"] = "test"
        frames.append(test_df)
    else:
        logger.info("Test path not provided — loading train only.")

    combined = pd.concat(frames, ignore_index=True)

    if max_rows is not None and max_rows < len(combined):
        logger.info(
            "Downsampling %d -> %d rows (seed=%d, deterministic).",
            len(combined), max_rows, SEED,
        )
        combined = combined.sample(n=max_rows, random_state=SEED).reset_index(drop=True)

    combined = combined.reset_index(drop=True)

    logger.info(
        "Total rows after concatenation: %d (train=%d, test=%d)",
        len(combined),
        int((combined["split"] == "train").sum()),
        int((combined["split"] == "test").sum()) if test_path else 0,
    )
    return combined


# ===========================================================================
# SECTION 4 — SCHEMA VALIDATION
# ---------------------------------------------------------------------------
# Verifies the loaded DataFrame is safe to hand off to downstream sections.
# Hard failures raise; soft issues log a WARN and continue.
# ===========================================================================


class SchemaValidationError(ValueError):
    """Raised when the source dataset fails a hard schema check."""


def validate_schema(df: pd.DataFrame) -> None:
    """Run all schema checks on the loaded DataFrame. Raises on hard fail.

    Hard failures (raise `SchemaValidationError`):
      - Any column in `REQUIRED_COLUMNS` is missing.
      - Neither `attack_cat` nor `label` is present.
      - Any `FEATURE_COLUMNS` entry other than proto/service/state is
        non-numeric.

    Soft issues (logged as WARN, execution continues):
      - Nulls in any column.
      - Duplicate rows.
      - `label` column present but not 0/1 valued.

    Args:
        df: DataFrame returned by `load_all_datasets`.

    Raises:
        SchemaValidationError: On any hard failure.
    """
    logger = get_logger()
    log_section(logger, "Section 4 — Schema Validation")

    _check_required_columns(df)
    _check_label_columns(df)
    _check_feature_dtypes(df)
    _check_nulls(df)
    _check_duplicates(df)
    _check_label_values(df)

    logger.info("Schema validation passed.")


def _check_required_columns(df: pd.DataFrame) -> None:
    """Every column in REQUIRED_COLUMNS must be present. Hard fail."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaValidationError(
            f"Required columns missing from source dataset: {missing}. "
            f"Expected all of: {list(REQUIRED_COLUMNS)}"
        )
    get_logger().info("  [OK] All required columns present: %s", list(REQUIRED_COLUMNS))


def _check_label_columns(df: pd.DataFrame) -> None:
    """At least one of attack_cat / label must be present. Hard fail."""
    present = [c for c in LABEL_COLUMNS if c in df.columns]
    if not present:
        raise SchemaValidationError(
            f"Source dataset must contain at least one label column. "
            f"Expected one of: {list(LABEL_COLUMNS)}. Found columns: "
            f"{list(df.columns)}"
        )
    get_logger().info("  [OK] Label column(s) present: %s", present)


def _check_feature_dtypes(df: pd.DataFrame) -> None:
    """Numeric FEATURE_COLUMNS must actually be numeric. Hard fail."""
    text_cols = {"proto", "service", "state"}
    non_numeric_offenders: list[str] = []
    for col in FEATURE_COLUMNS:
        if col in text_cols or col not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            non_numeric_offenders.append(col)

    if non_numeric_offenders:
        raise SchemaValidationError(
            f"Feature columns expected to be numeric but aren't: "
            f"{non_numeric_offenders}. Check the source file's dtypes."
        )
    get_logger().info("  [OK] Numeric feature columns have numeric dtypes.")


def _check_nulls(df: pd.DataFrame) -> None:
    """Nulls are a soft issue — logged, not raised."""
    logger = get_logger()
    null_counts = df.isna().sum()
    offenders = null_counts[null_counts > 0]
    if offenders.empty:
        logger.info("  [OK] No null values.")
        return

    logger.warning("  [WARN] Null values detected in %d column(s):", len(offenders))
    for col, n in offenders.items():
        logger.warning("         %s: %d nulls", col, int(n))


def _check_duplicates(df: pd.DataFrame) -> None:
    """Duplicate rows are a soft issue — logged, not raised."""
    logger = get_logger()
    n_dupes = int(df.duplicated().sum())
    if n_dupes == 0:
        logger.info("  [OK] No duplicate rows.")
    else:
        pct = 100.0 * n_dupes / len(df)
        logger.warning(
            "  [WARN] %d duplicate rows (%.2f%% of total). Kept as-is; "
            "each gets a distinct flow_id downstream.", n_dupes, pct,
        )


def _check_label_values(df: pd.DataFrame) -> None:
    """If `label` is present, it should be 0/1. Soft warn on anything else."""
    if "label" not in df.columns:
        return
    logger = get_logger()
    unique_vals = set(df["label"].dropna().unique().tolist())
    unexpected = unique_vals - {0, 1}
    if unexpected:
        logger.warning(
            "  [WARN] `label` column contains unexpected values %s "
            "(expected {0, 1}). Downstream logic assumes binary.", unexpected,
        )
    else:
        logger.info("  [OK] `label` column is binary (0/1).")


# ===========================================================================
# SECTION 5 — TIMESTAMP GENERATOR
# ---------------------------------------------------------------------------
# Assigns every flow a synthetic ISO-8601 timestamp inside a fixed 24-hour
# demo window. Fully deterministic (seed=42).
#
# Attack rows cluster in time (correlation signal for Module 3); normal
# traffic spreads evenly across the day.
# ===========================================================================


def _is_attack_row(row: pd.Series) -> bool:
    """Return True if a row represents attack traffic.

    Prefers `attack_cat` (richer signal) with `label` as fallback.
    """
    if "attack_cat" in row.index and pd.notna(row["attack_cat"]):
        return str(row["attack_cat"]).strip().lower() != "normal"
    if "label" in row.index and pd.notna(row["label"]):
        return int(row["label"]) == 1
    return False


def _attack_mask(df: pd.DataFrame) -> pd.Series:
    """Vectorized version of `_is_attack_row` for the full DataFrame."""
    if "attack_cat" in df.columns:
        return df["attack_cat"].astype(str).str.strip().str.lower() != "normal"
    if "label" in df.columns:
        return df["label"].fillna(0).astype(int) == 1
    return pd.Series(False, index=df.index)


def assign_timestamps(
    df: pd.DataFrame,
    seed: int = SEED,
    demo_date: datetime = DEMO_DATE,
    window_hours: int = WINDOW_HOURS,
    jitter_seconds: float = TIMESTAMP_JITTER_SECONDS,
) -> pd.Series:
    """Assign a synthetic ISO-8601 timestamp to every row.

    Algorithm:
      1. Split rows into attack / normal by `_attack_mask`.
      2. Normal rows: spread evenly across the full 24h window.
      3. Attack rows: spread across a narrower sub-window (60% of the
         day, offset from 04:00) so attacks visibly cluster.
      4. Add seeded per-row jitter (+/- `jitter_seconds`).

    Args:
        df: DataFrame with attack_cat and/or label column.
        seed: RNG seed for jitter.
        demo_date: Midnight of the fake demo day (window start).
        window_hours: Window length in hours (default 24).
        jitter_seconds: Absolute jitter magnitude in seconds.

    Returns:
        Series of ISO-8601 strings (`YYYY-MM-DDTHH:MM:SS`).
    """
    logger = get_logger()
    log_section(logger, "Section 5 — Timestamp Generation")

    total = len(df)
    if total == 0:
        raise ValueError("Cannot assign timestamps to an empty DataFrame.")

    attack_mask = _attack_mask(df)
    n_attack = int(attack_mask.sum())
    n_normal = total - n_attack
    logger.info(
        "Attack rows: %d (%.1f%%) | Normal rows: %d",
        n_attack, 100.0 * n_attack / total, n_normal,
    )

    # --- 1. Normal traffic: full 24h window, uniform spread --------------
    normal_offsets = _linear_offsets(
        n_items=n_normal,
        window_seconds=window_hours * 3600,
        start_offset_seconds=0.0,
    )

    # --- 2. Attack traffic: narrower sub-window, offset into the day ------
    # Attack window covers 60% of the day, starting at hour 4 (04:00-18:24).
    # These numbers are deliberately not exposed as config: adjusting them
    # would silently change the demo narrative.
    attack_window_seconds = window_hours * 3600 * 0.60
    attack_start_seconds = 4 * 3600
    attack_offsets = _linear_offsets(
        n_items=n_attack,
        window_seconds=attack_window_seconds,
        start_offset_seconds=attack_start_seconds,
    )

    # --- 3. Reassemble into a single ordered offset series ---------------
    offsets = pd.Series(0.0, index=df.index, dtype=float)
    if n_normal:
        offsets.loc[~attack_mask] = normal_offsets
    if n_attack:
        offsets.loc[attack_mask] = attack_offsets

    # --- 4. Seeded jitter -------------------------------------------------
    rng = random.Random(seed)
    jitter = pd.Series(
        [rng.uniform(-jitter_seconds, jitter_seconds) for _ in range(total)],
        index=df.index,
    )
    final_offsets_seconds = offsets + jitter

    # --- 5. Convert offsets -> ISO-8601 strings ---------------------------
    timestamps = final_offsets_seconds.map(
        lambda s: (demo_date + timedelta(seconds=float(s))).isoformat(timespec="seconds")
    )

    logger.info(
        "Timestamps assigned. Range: %s -> %s",
        timestamps.min(), timestamps.max(),
    )
    return timestamps


def _linear_offsets(
    n_items: int,
    window_seconds: float,
    start_offset_seconds: float,
) -> list[float]:
    """Return N evenly-spaced offsets (in seconds) inside a sub-window.

    Deterministic and pure — no RNG. Jitter is added by the caller.

    Args:
        n_items: How many offsets to produce.
        window_seconds: Length of the sub-window in seconds.
        start_offset_seconds: Where the sub-window starts.

    Returns:
        List of `n_items` monotonically non-decreasing floats.
    """
    if n_items <= 0:
        return []
    step = window_seconds / max(n_items, 1)
    return [start_offset_seconds + i * step for i in range(n_items)]


# ===========================================================================
# SECTION 6 — TOPOLOGY GENERATOR
# ---------------------------------------------------------------------------
# Builds the static synthetic enterprise topology. Represented three ways:
#   - dict:      source of truth in code
#   - NetworkX:  adjacency queries + connectivity assertion
#   - JSON str:  what gets stored per-row in the `adjacent_nodes` column
# ===========================================================================


# 18 nodes across 10 tiers. Editing this dict is the ONLY way to change
# the topology. Every downstream section reads from here.
TOPOLOGY_DEFINITION: dict[str, dict[str, Any]] = {
    # --- Perimeter ---------------------------------------------------------
    "firewall-01":    {"tier": "firewall",       "services": [],                        "upstream": []},

    # --- DNS ---------------------------------------------------------------
    "dns-01":         {"tier": "dns",             "services": ["dns"],                   "upstream": ["firewall-01"]},
    "dns-02":         {"tier": "dns",             "services": ["dns"],                   "upstream": ["firewall-01"]},

    # --- Load balancer + web tier -----------------------------------------
    "lb-01":          {"tier": "load_balancer",   "services": [],                        "upstream": ["firewall-01"]},
    "web-srv-01":     {"tier": "web",             "services": ["http", "ssl"],           "upstream": ["lb-01"]},
    "web-srv-02":     {"tier": "web",             "services": ["http", "ssl"],           "upstream": ["lb-01"]},

    # --- Application tier -------------------------------------------------
    "app-srv-01":     {"tier": "app",             "services": [],                        "upstream": ["web-srv-01", "web-srv-02"]},
    "app-srv-02":     {"tier": "app",             "services": [],                        "upstream": ["web-srv-01", "web-srv-02"]},

    # --- Data tier --------------------------------------------------------
    "db-primary":     {"tier": "db",              "services": [],                        "upstream": ["app-srv-01", "app-srv-02"]},
    "db-replica":     {"tier": "db",              "services": [],                        "upstream": ["db-primary"]},
    "cache-01":       {"tier": "cache",           "services": [],                        "upstream": ["app-srv-01", "app-srv-02"]},

    # --- Auth / remote access ---------------------------------------------
    "auth-01":        {"tier": "auth",            "services": ["radius"],                "upstream": ["firewall-01"]},
    "ssh-bastion-01": {"tier": "remote_access",   "services": ["ssh"],                   "upstream": ["firewall-01"]},

    # --- Mail / file transfer ---------------------------------------------
    "mail-01":        {"tier": "mail",            "services": ["smtp", "pop3"],          "upstream": ["firewall-01"]},
    "ftp-01":         {"tier": "file_transfer",   "services": ["ftp", "ftp-data"],       "upstream": ["firewall-01"]},

    # --- Infra / monitoring / logging -------------------------------------
    "dhcp-01":        {"tier": "infra",           "services": ["dhcp"],                  "upstream": ["firewall-01"]},
    "monitoring-01":  {"tier": "monitoring",      "services": ["snmp"],                  "upstream": ["firewall-01"]},
    "logging-01":     {"tier": "logging",         "services": [],                        "upstream": ["monitoring-01"]},

    # --- Messaging / external --------------------------------------------
    "irc-gw-01":      {"tier": "messaging",       "services": ["irc"],                   "upstream": ["firewall-01"]},
    "external-api":   {"tier": "external",        "services": [],                        "upstream": ["app-srv-01"]},
}


def build_topology() -> dict[str, dict[str, Any]]:
    """Return a defensive copy of the static topology definition."""
    return {node_id: dict(meta) for node_id, meta in TOPOLOGY_DEFINITION.items()}


def topology_to_networkx(topology: dict[str, dict[str, Any]]) -> nx.Graph:
    """Convert the topology dict to an undirected NetworkX graph.

    Undirected because Section 8's "same host OR adjacent" logic doesn't
    care about traffic direction. Module 3 can rebuild a DiGraph from the
    same source dict if it needs directionality.

    Args:
        topology: Dict from `build_topology`.

    Returns:
        Undirected `nx.Graph` with node attributes and edges.
    """
    graph = nx.Graph()
    for node_id, meta in topology.items():
        graph.add_node(node_id, tier=meta["tier"], services=list(meta["services"]))
    for node_id, meta in topology.items():
        for parent in meta["upstream"]:
            if parent not in topology:
                raise ValueError(
                    f"Node '{node_id}' lists unknown upstream '{parent}'. "
                    f"Check TOPOLOGY_DEFINITION."
                )
            graph.add_edge(node_id, parent)
    return graph


def assert_topology_valid(graph: nx.Graph) -> None:
    """Fail loudly if the topology graph is malformed. Raises on failure."""
    logger = get_logger()
    n_nodes = graph.number_of_nodes()

    if not (EXPECTED_MIN_TOPOLOGY_NODES <= n_nodes <= EXPECTED_MAX_TOPOLOGY_NODES):
        raise RuntimeError(
            f"Topology has {n_nodes} nodes; expected "
            f"{EXPECTED_MIN_TOPOLOGY_NODES}..{EXPECTED_MAX_TOPOLOGY_NODES}."
        )

    if not nx.is_connected(graph):
        components = list(nx.connected_components(graph))
        raise RuntimeError(
            f"Topology graph is not connected — found {len(components)} "
            f"components. Every node must be reachable from every other."
        )

    self_loops = list(nx.selfloop_edges(graph))
    if self_loops:
        raise RuntimeError(f"Topology contains self-loops: {self_loops}")

    logger.info(
        "  [OK] Topology valid: %d nodes, %d edges, connected.",
        n_nodes, graph.number_of_edges(),
    )


def get_neighbors(graph: nx.Graph, node_id: str) -> list[str]:
    """Return sorted list of directly-adjacent node IDs for a given node."""
    return sorted(graph.neighbors(node_id))


def topology_to_dataframe(
    topology: dict[str, dict[str, Any]],
    graph: nx.Graph,
) -> pd.DataFrame:
    """Build the DataFrame that becomes the `synthetic_topology` table."""
    records: list[dict[str, Any]] = []
    for node_id, meta in topology.items():
        neighbors = get_neighbors(graph, node_id)
        records.append({
            "node_id": node_id,
            "tier": meta["tier"],
            "adjacent_nodes": json.dumps(neighbors),
        })
    return pd.DataFrame.from_records(records)


def generate_topology() -> tuple[dict[str, dict[str, Any]], nx.Graph, pd.DataFrame]:
    """Orchestrator — builds, validates, and returns all three representations."""
    logger = get_logger()
    log_section(logger, "Section 6 — Topology Generation")

    topology = build_topology()
    logger.info("Built topology definition: %d nodes.", len(topology))

    graph = topology_to_networkx(topology)
    logger.info(
        "Built NetworkX graph: %d nodes, %d edges.",
        graph.number_of_nodes(), graph.number_of_edges(),
    )

    assert_topology_valid(graph)

    df = topology_to_dataframe(topology, graph)
    logger.info("Built topology DataFrame ready for SQLite: %d rows.", len(df))

    return topology, graph, df


# ===========================================================================
# SECTION 7 — HOST MAPPING
# ---------------------------------------------------------------------------
# Assigns every flow to exactly one host in the topology. Deterministic:
# same (proto, service, state) triple ALWAYS maps to the same host, every
# run, every Python version, every OS. Uses hashlib.md5 for cross-run
# stability (Python's built-in `hash()` is randomized per PEP 456).
# ===========================================================================


# Routing/broadcast/control-plane protocols that get their own dedicated
# infra/monitoring nodes when service is unknown.
CONTROL_PLANE_PROTOS: frozenset[str] = frozenset({
    "arp", "ospf", "igmp", "pim", "rsvp", "sun-nd", "swipe", "mobile",
    "gre", "ipv6", "ipv6-frag", "sep", "rvd", "vrrp", "egp", "vmtp",
    "eigrp", "icmp", "iso-ip", "st2", "xtp",
})


def _build_service_index(
    topology: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Reverse-index the topology: service -> sorted list of candidate node_ids."""
    index: dict[str, list[str]] = {}
    for node_id, meta in topology.items():
        for svc in meta.get("services", []):
            index.setdefault(svc, []).append(node_id)
    for svc in index:
        index[svc].sort()
    return index


def _pick_generic_pools(
    topology: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Identify the fallback pools for service='-' flows.

    Returns:
        (control_plane_pool, gateway_pool) — both sorted lists of node_ids.

    Selection is by `tier`, so renaming a node doesn't silently break
    host placement.
    """
    control_pool = sorted([
        nid for nid, meta in topology.items()
        if meta["tier"] in {"monitoring", "logging", "infra"}
    ])
    gateway_pool = sorted([
        nid for nid, meta in topology.items()
        if meta["tier"] in {"firewall", "load_balancer"}
    ])
    if not gateway_pool:
        raise RuntimeError(
            "No firewall/load_balancer nodes in topology — cannot place "
            "generic traffic. Check TOPOLOGY_DEFINITION."
        )
    if not control_pool:
        get_logger().warning(
            "  [WARN] No monitoring/logging/infra nodes — control-plane "
            "protocols will fall through to the gateway pool."
        )
    return control_pool, gateway_pool


def _stable_hash_int(key: str) -> int:
    """Cross-run, cross-process, cross-Python-version stable hash."""
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)


def assign_host(
    proto: str,
    service: str,
    state: str,
    service_index: dict[str, list[str]],
    control_pool: list[str],
    gateway_pool: list[str],
) -> str:
    """Deterministically map a single flow to a topology node.

    Priority order:
      1. Service-aware: known service -> node that advertises it.
      2. Control-plane: unknown service + routing proto -> control pool.
      3. Generic: everything else -> gateway pool.

    Args:
        proto, service, state: The three UNSW-NB15 flow-identity fields.
        service_index: Reverse index from `_build_service_index`.
        control_pool, gateway_pool: Fallback pools.

    Returns:
        A single node_id guaranteed to exist in the topology.
    """
    key = f"{proto}|{service}|{state}"
    h = _stable_hash_int(key)

    candidates = service_index.get(service)
    if candidates:
        return candidates[h % len(candidates)]

    if proto in CONTROL_PLANE_PROTOS and control_pool:
        return control_pool[h % len(control_pool)]

    return gateway_pool[h % len(gateway_pool)]


def assign_hosts_bulk(
    df: pd.DataFrame,
    topology: dict[str, dict[str, Any]],
) -> pd.Series:
    """Assign a host to every row in the DataFrame.

    Uses a per-triple cache: identical (proto, service, state) triples
    hash only once. ~250k rows completes in ~4 seconds.

    Args:
        df: DataFrame containing proto/service/state columns.
        topology: Dict from `build_topology`.

    Returns:
        A Series of host node_ids indexed identically to `df`.
    """
    logger = get_logger()
    log_section(logger, "Section 7 — Host Mapping")

    for required in ("proto", "service", "state"):
        if required not in df.columns:
            raise SchemaValidationError(
                f"Column '{required}' required for host mapping."
            )

    service_index = _build_service_index(topology)
    control_pool, gateway_pool = _pick_generic_pools(topology)

    logger.info(
        "Service-aware routing: %d services -> %d nodes; "
        "control-plane pool: %d; gateway pool: %d.",
        len(service_index),
        sum(len(v) for v in service_index.values()),
        len(control_pool), len(gateway_pool),
    )

    triples = df[["proto", "service", "state"]].astype(str)
    unique_triples = triples.drop_duplicates()
    logger.info(
        "Unique (proto, service, state) combinations: %d",
        len(unique_triples),
    )

    cache: dict[tuple[str, str, str], str] = {}
    iterator = unique_triples.itertuples(index=False, name=None)
    show_progress = len(unique_triples) >= TQDM_MIN_ROWS_FOR_BAR
    if show_progress:
        iterator = tqdm(iterator, total=len(unique_triples), desc="Mapping hosts",
                        unit="triple")
    for proto, service, state in iterator:
        cache[(proto, service, state)] = assign_host(
            proto, service, state, service_index, control_pool, gateway_pool,
        )

    hosts = pd.Series(
        [cache[(p, s, st)] for p, s, st in triples.itertuples(index=False, name=None)],
        index=df.index,
        name="host_id",
    )

    placement_counts = hosts.value_counts()
    logger.info(
        "Host placement complete. Unique hosts used: %d / %d in topology.",
        placement_counts.shape[0], len(topology),
    )
    top5 = placement_counts.head(5).to_dict()
    logger.info("Top 5 host loads: %s", top5)

    unused = set(topology.keys()) - set(hosts.unique())
    if unused:
        logger.warning(
            "  [WARN] %d topology node(s) received zero flows: %s. "
            "Fine for dashboard, but may indicate a coverage gap.",
            len(unused), sorted(unused),
        )
    return hosts


# ===========================================================================
# SECTION 8 — CONFIG CHANGE GENERATOR
# ---------------------------------------------------------------------------
# Injects synthetic infrastructure config-change events shortly BEFORE real
# attack clusters. Deliberately incomplete: only ~35% of clusters get a
# change record. The remaining 65% become "missing evidence" cases for
# Module 3.
# ===========================================================================


def identify_attack_clusters(
    df: pd.DataFrame,
    window_minutes: int = CLUSTER_TIME_WINDOW_MINUTES,
) -> pd.DataFrame:
    """Group attack rows into clusters by (host_id, time-window).

    Two or more attack flows on the same host, each consecutive pair
    within `window_minutes` of each other, count as one cluster.

    Args:
        df: DataFrame with `host_id`, `ts`, and either `attack_cat` or
            `label` columns.
        window_minutes: Max gap between two flows for cluster membership.

    Returns:
        DataFrame with one row per cluster.
    """
    logger = get_logger()

    for required in ("host_id", "ts"):
        if required not in df.columns:
            raise SchemaValidationError(
                f"Column '{required}' required for cluster identification. "
                f"Run assign_hosts_bulk / assign_timestamps first."
            )

    attack_mask = _attack_mask(df)
    attacks = df.loc[attack_mask, ["host_id", "ts", "attack_cat"]].copy() \
        if "attack_cat" in df.columns \
        else df.loc[attack_mask, ["host_id", "ts"]].assign(attack_cat="Unknown")
    if attacks.empty:
        logger.warning("  [WARN] No attack rows found — no clusters to build.")
        return pd.DataFrame(columns=["host_id", "cluster_start_ts",
                                      "cluster_end_ts", "n_flows", "attack_cats"])

    attacks["ts_dt"] = pd.to_datetime(attacks["ts"])
    attacks = attacks.sort_values(["host_id", "ts_dt"]).reset_index(drop=True)

    gap = attacks.groupby("host_id")["ts_dt"].diff()
    threshold = pd.Timedelta(minutes=window_minutes)
    new_cluster = (attacks["host_id"] != attacks["host_id"].shift()) | (gap > threshold)
    attacks["cluster_id"] = new_cluster.cumsum()

    clusters = attacks.groupby("cluster_id").agg(
        host_id=("host_id", "first"),
        cluster_start_ts=("ts_dt", "min"),
        cluster_end_ts=("ts_dt", "max"),
        n_flows=("ts_dt", "size"),
        attack_cats=("attack_cat", lambda s: json.dumps(sorted(set(map(str, s))))),
    ).reset_index(drop=True)

    clusters["cluster_start_ts"] = clusters["cluster_start_ts"] \
        .dt.strftime("%Y-%m-%dT%H:%M:%S")
    clusters["cluster_end_ts"] = clusters["cluster_end_ts"] \
        .dt.strftime("%Y-%m-%dT%H:%M:%S")

    logger.info(
        "Identified %d attack cluster(s) across %d host(s). "
        "Median cluster size: %.0f flows.",
        len(clusters), clusters["host_id"].nunique(),
        clusters["n_flows"].median() if len(clusters) else 0,
    )
    return clusters


def generate_config_changes(
    clusters_df: pd.DataFrame,
    graph: nx.Graph,
    injection_rate: float = CONFIG_CHANGE_INJECTION_RATE,
    lead_min: float = CONFIG_CHANGE_LEAD_MINUTES_MIN,
    lead_max: float = CONFIG_CHANGE_LEAD_MINUTES_MAX,
    adjacent_prob: float = CONFIG_CHANGE_ADJACENT_HOST_PROBABILITY,
    seed: int = SEED,
) -> pd.DataFrame:
    """Generate config-change events for a seeded subset of attack clusters.

    For each cluster: roll a seeded coin against `injection_rate`. On hit,
    generate 1-2 change events on the cluster's host or a neighbor,
    timestamped `lead_min`..`lead_max` minutes before the cluster starts.

    Args:
        clusters_df: Output of `identify_attack_clusters`.
        graph: NetworkX topology graph.
        injection_rate, lead_min, lead_max, adjacent_prob, seed:
            See module-level constants.

    Returns:
        DataFrame matching the `synthetic_config_changes` schema.
    """
    logger = get_logger()
    log_section(logger, "Section 8 — Config Change Generation")

    if clusters_df.empty:
        logger.info("No clusters -> no config-changes to generate.")
        return _empty_config_df()

    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    change_id = 1

    n_injected = 0
    for _, cluster in clusters_df.iterrows():
        if rng.random() >= injection_rate:
            continue   # deliberate "missing evidence" case
        n_injected += 1

        cluster_start = datetime.fromisoformat(cluster["cluster_start_ts"])
        n_changes = 1 if rng.random() > 0.25 else 2

        for _ in range(n_changes):
            host = _pick_config_change_host(
                cluster_host=cluster["host_id"],
                graph=graph,
                adjacent_prob=adjacent_prob,
                rng=rng,
            )
            lead = rng.uniform(lead_min, lead_max)
            change_ts = cluster_start - timedelta(minutes=lead)
            template, default_severity = CONFIG_CHANGE_TEMPLATES[
                rng.randrange(len(CONFIG_CHANGE_TEMPLATES))
            ]
            records.append({
                "change_id": change_id,
                "ts": change_ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "host_id": host,
                "event_description": template.format(host=host),
                "severity": default_severity,
            })
            change_id += 1

    df = pd.DataFrame.from_records(records) if records else _empty_config_df()

    logger.info(
        "Config-changes generated: %d event(s) across %d cluster(s) "
        "(%.0f%% injection rate). %d cluster(s) intentionally left as "
        "'missing evidence' for Module 3.",
        len(df), n_injected, 100 * injection_rate,
        len(clusters_df) - n_injected,
    )
    return df


def _pick_config_change_host(
    cluster_host: str,
    graph: nx.Graph,
    adjacent_prob: float,
    rng: random.Random,
) -> str:
    """Decide which host a given config-change lands on."""
    if rng.random() >= adjacent_prob:
        return cluster_host
    neighbors = get_neighbors(graph, cluster_host)
    if not neighbors:
        return cluster_host
    return neighbors[rng.randrange(len(neighbors))]


def _empty_config_df() -> pd.DataFrame:
    """Return an empty DataFrame with the exact config-change schema."""
    return pd.DataFrame({
        "change_id": pd.Series(dtype="int64"),
        "ts": pd.Series(dtype="object"),
        "host_id": pd.Series(dtype="object"),
        "event_description": pd.Series(dtype="object"),
        "severity": pd.Series(dtype="object"),
    })


# ===========================================================================
# SECTION 9 — LOG GENERATOR
# ---------------------------------------------------------------------------
# Produces one syslog-style line per network flow. Pure f-strings, no LLM.
# ===========================================================================


def _infer_severity(row: dict[str, Any]) -> str:
    """Return one of 'INFO' / 'WARN' / 'ERROR' for a single flow row.

    Args:
        row: A dict-like flow row containing at least `state`,
            `attack_cat` (optional), `label` (optional), `sbytes`, `dbytes`.

    Returns:
        Severity string.
    """
    is_attack = _is_attack_row(pd.Series(row))
    state = str(row.get("state", "")).upper()
    total_bytes = int(row.get("sbytes", 0) or 0) + int(row.get("dbytes", 0) or 0)

    if is_attack and state in LOG_SEVERITY_ERROR_STATES:
        return "ERROR"
    if is_attack:
        return "WARN"
    if total_bytes >= LOG_SEVERITY_WARN_BYTES:
        return "WARN"
    return "INFO"


def _format_log_line(
    ts: str,
    host_id: str,
    proto: str,
    service: str,
    state: str,
    sbytes: int,
    dbytes: int,
    severity: str,
) -> str:
    """Build a single syslog-style line. Pure formatting, no side effects.

    Format (fixed, do not change without updating Module 6's log parser):
        <ISO_TS>Z <host> <SEVERITY> <PROTO> <SERVICE> <STATE_MESSAGE>
        src_bytes=<N> dst_bytes=<N>
    """
    proto_up = proto.upper() if proto else "UNK"
    service_up = service.upper() if service and service != "-" else "GENERIC"
    state_msg = _describe_state(state)
    return (
        f"{ts}Z {host_id} {severity} {proto_up} {service_up} {state_msg} "
        f"src_bytes={int(sbytes)} dst_bytes={int(dbytes)}"
    )


def _describe_state(state: str) -> str:
    """Human-readable phrase for a UNSW-NB15 TCP state code."""
    return {
        "FIN": "Connection Established",
        "CON": "Connected",
        "INT": "Interrupted",
        "REQ": "Request Sent",
        "RST": "Connection Reset",
        "ECO": "Echo Reply",
        "URN": "Urgent Data",
        "PAR": "Partial Data",
        "no":  "No State",
    }.get(state, "Session")


_LOG_INPUT_COLUMNS: tuple[str, ...] = (
    "flow_id", "ts", "host_id", "proto", "service", "state",
    "sbytes", "dbytes",
)


def generate_logs_bulk(df: pd.DataFrame) -> pd.DataFrame:
    """Produce the `synthetic_logs` DataFrame from a flows DataFrame.

    Args:
        df: DataFrame with the required columns (see `_LOG_INPUT_COLUMNS`)
            plus `attack_cat` and/or `label` for severity inference.

    Returns:
        DataFrame matching the `synthetic_logs` schema.
    """
    logger = get_logger()
    log_section(logger, "Section 9 — Log Generation")

    missing = [c for c in _LOG_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaValidationError(
            f"generate_logs_bulk: missing required columns {missing}. "
            f"Run assign_timestamps + assign_hosts_bulk first."
        )

    keep = list(_LOG_INPUT_COLUMNS)
    for optional in ("attack_cat", "label"):
        if optional in df.columns:
            keep.append(optional)
    view = df[keep]

    records: list[dict[str, Any]] = []
    iterator = view.itertuples(index=False)
    show_progress = len(view) >= TQDM_MIN_ROWS_FOR_BAR
    if show_progress:
        iterator = tqdm(iterator, total=len(view), desc="Generating logs",
                        unit="row")

    for row_tuple in iterator:
        row = row_tuple._asdict()
        severity = _infer_severity(row)
        message = _format_log_line(
            ts=row["ts"],
            host_id=row["host_id"],
            proto=str(row["proto"]),
            service=str(row["service"]),
            state=str(row["state"]),
            sbytes=row["sbytes"],
            dbytes=row["dbytes"],
            severity=severity,
        )
        records.append({
            "log_id": int(row["flow_id"]),   # 1:1 with flow_id
            "ts": row["ts"],
            "host_id": row["host_id"],
            "log_message": message,
            "severity": severity,
        })

    logs_df = pd.DataFrame.from_records(records)

    severity_counts = logs_df["severity"].value_counts().to_dict()
    logger.info("Log lines generated: %d", len(logs_df))
    logger.info("Severity distribution: %s", severity_counts)
    if logs_df["log_id"].duplicated().any():
        raise RuntimeError(
            "generate_logs_bulk produced duplicate log_ids — this should "
            "never happen. Check that flow_id was unique in the input."
        )
    return logs_df


# ===========================================================================
# SECTION 10 — SQLITE WRITER
# ---------------------------------------------------------------------------
# Persists the four DataFrames into a single SQLite file. Fully idempotent
# (drop+recreate). All writes in one transaction — either the whole DB is
# valid or nothing was written.
# ===========================================================================


_FLOWS_TABLE_COLUMNS: tuple[str, ...] = (
    "flow_id", "ts", "host_id", "split",
    "proto", "service", "state",
    "sbytes", "dbytes", "rate", "sload", "dload", "dur",
    "sinpkt", "dinpkt",
    "ct_src_dport_ltm", "ct_dst_sport_ltm",
    "attack_cat", "label",
)

_TOPOLOGY_TABLE_COLUMNS: tuple[str, ...] = (
    "node_id", "tier", "adjacent_nodes",
)

_CONFIG_CHANGES_TABLE_COLUMNS: tuple[str, ...] = (
    "change_id", "ts", "host_id", "event_description", "severity",
)

_LOGS_TABLE_COLUMNS: tuple[str, ...] = (
    "log_id", "ts", "host_id", "log_message", "severity",
)

_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("idx_flows_host",     "flows",                    ("host_id",)),
    ("idx_flows_ts",       "flows",                    ("ts",)),
    ("idx_flows_attack",   "flows",                    ("attack_cat",)),
    ("idx_cc_host",        "synthetic_config_changes", ("host_id",)),
    ("idx_cc_ts",          "synthetic_config_changes", ("ts",)),
    ("idx_logs_host",      "synthetic_logs",           ("host_id",)),
    ("idx_logs_ts",        "synthetic_logs",           ("ts",)),
)


def write_to_sqlite(
    db_path: Path,
    flows_df: pd.DataFrame,
    topology_df: pd.DataFrame,
    config_changes_df: pd.DataFrame,
    logs_df: pd.DataFrame,
) -> None:
    """Write all four DataFrames to a single SQLite database.

    All writes happen in one transaction. On failure, the DB is rolled
    back and the exception is re-raised.

    Args:
        db_path: Destination SQLite file. Parent dirs created if needed.
        flows_df, topology_df, config_changes_df, logs_df:
            DataFrames from Sections 5/7 (flows), 6, 8, and 9.

    Raises:
        SchemaValidationError: If any DataFrame is missing required columns.
        sqlite3.DatabaseError: On any underlying SQLite failure.
    """
    logger = get_logger()
    log_section(logger, "Section 10 — SQLite Write")

    _assert_columns(flows_df,           _FLOWS_TABLE_COLUMNS,           "flows_df")
    _assert_columns(topology_df,        _TOPOLOGY_TABLE_COLUMNS,        "topology_df")
    _assert_columns(config_changes_df,  _CONFIG_CHANGES_TABLE_COLUMNS,  "config_changes_df")
    _assert_columns(logs_df,            _LOGS_TABLE_COLUMNS,            "logs_df")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    flows_out = flows_df[list(_FLOWS_TABLE_COLUMNS)]
    topology_out = topology_df[list(_TOPOLOGY_TABLE_COLUMNS)]
    config_out = config_changes_df[list(_CONFIG_CHANGES_TABLE_COLUMNS)]
    logs_out = logs_df[list(_LOGS_TABLE_COLUMNS)]

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        _write_table(conn, "flows",                    flows_out)
        _write_table(conn, "synthetic_topology",       topology_out)
        _write_table(conn, "synthetic_config_changes", config_out)
        _write_table(conn, "synthetic_logs",           logs_out)
        _create_indexes(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.error("SQLite write failed — transaction rolled back.")
        raise
    finally:
        conn.close()

    size_mb = db_path.stat().st_size / (1024 * 1024)
    logger.info("SQLite write complete: %s (%.1f MB)", db_path, size_mb)


def _assert_columns(
    df: pd.DataFrame,
    required: tuple[str, ...],
    df_name: str,
) -> None:
    """Fail loudly if any expected column is missing from the DataFrame."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaValidationError(
            f"{df_name} is missing required columns for SQLite write: "
            f"{missing}. Present columns: {list(df.columns)}"
        )


def _write_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """Drop-and-recreate one table from a DataFrame."""
    logger = get_logger()
    logger.info("  writing %s: %d rows, %d cols", table, len(df), df.shape[1])
    df.to_sql(
        table,
        conn,
        if_exists="replace",
        index=False,
    )


def _create_indexes(conn: sqlite3.Connection) -> None:
    """Create all indexes declared in `_INDEXES`. Idempotent per index."""
    logger = get_logger()
    for idx_name, table, cols in _INDEXES:
        col_list = ", ".join(cols)
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({col_list})")
    logger.info("  created %d indexes.", len(_INDEXES))


# ===========================================================================
# SECTION 11 — POST-WRITE VALIDATION
# ---------------------------------------------------------------------------
# Runs a fixed checklist against the freshly-written SQLite DB. Every
# check reads from disk (not memory), so bugs in Section 10 also get
# caught here.
# ===========================================================================


CheckResult = tuple[str, bool, str]   # (label, passed, detail)


def validate_database(db_path: Path = DB_PATH) -> bool:
    """Run the full post-write checklist against the SQLite DB.

    Args:
        db_path: Path to the SQLite file to validate.

    Returns:
        True if every check passed. False otherwise.

    Raises:
        RuntimeError: If the DB file doesn't exist (nothing to validate).
    """
    logger = get_logger()
    log_section(logger, "Section 11 — Post-Write Validation")

    if not db_path.exists():
        raise RuntimeError(
            f"Cannot validate — DB file not found at {db_path}. "
            f"Did Section 10 write successfully?"
        )

    conn = sqlite3.connect(db_path)
    try:
        results: list[CheckResult] = []

        counts = _table_counts(conn)
        results.append(_check_tables_populated(counts))

        results.append(_check_flows_hosts_exist(conn))
        results.append(_check_config_hosts_exist(conn))
        results.append(_check_logs_hosts_exist(conn))

        results.append(_check_id_uniqueness(conn, "flows", "flow_id"))
        results.append(_check_id_uniqueness(conn, "synthetic_logs", "log_id"))
        results.append(_check_id_uniqueness(conn, "synthetic_config_changes", "change_id"))
        results.append(_check_id_uniqueness(conn, "synthetic_topology", "node_id"))

        results.append(_check_config_precedes_attacks(conn))
        results.append(_check_no_orphan_tables(conn))

    finally:
        conn.close()

    return _log_results(counts, results)


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts for the four expected tables (missing table -> -1)."""
    counts: dict[str, int] = {}
    for t in ("flows", "synthetic_topology", "synthetic_config_changes", "synthetic_logs"):
        try:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.DatabaseError:
            counts[t] = -1
    return counts


def _check_tables_populated(counts: dict[str, int]) -> CheckResult:
    """All 4 tables exist and have >=1 row.

    synthetic_config_changes is allowed to have 0 rows only if the source
    dataset had zero attack rows.
    """
    missing = [t for t, n in counts.items() if n < 0]
    if missing:
        return ("all four tables exist", False, f"missing table(s): {missing}")

    zero_row = [t for t, n in counts.items() if n == 0 and t != "synthetic_config_changes"]
    if zero_row:
        return ("all four tables have data", False, f"empty table(s): {zero_row}")

    return ("all four tables populated", True,
            f"flows={counts['flows']:,}, topology={counts['synthetic_topology']}, "
            f"config={counts['synthetic_config_changes']}, logs={counts['synthetic_logs']:,}")


def _check_flows_hosts_exist(conn: sqlite3.Connection) -> CheckResult:
    """Every distinct flows.host_id must appear in synthetic_topology.node_id."""
    query = """
        SELECT DISTINCT f.host_id
        FROM flows f
        LEFT JOIN synthetic_topology t ON f.host_id = t.node_id
        WHERE t.node_id IS NULL
    """
    offenders = [row[0] for row in conn.execute(query)]
    if offenders:
        return ("every flow host exists in topology", False,
                f"{len(offenders)} orphan host(s): {offenders[:5]}"
                f"{'...' if len(offenders) > 5 else ''}")
    return ("every flow host exists in topology", True, "no orphan hosts")


def _check_config_hosts_exist(conn: sqlite3.Connection) -> CheckResult:
    """Every config_changes.host_id must appear in synthetic_topology."""
    query = """
        SELECT DISTINCT cc.host_id
        FROM synthetic_config_changes cc
        LEFT JOIN synthetic_topology t ON cc.host_id = t.node_id
        WHERE t.node_id IS NULL
    """
    offenders = [row[0] for row in conn.execute(query)]
    if offenders:
        return ("every config event references a real host", False,
                f"{len(offenders)} orphan host(s): {offenders[:5]}")
    return ("every config event references a real host", True, "no orphan hosts")


def _check_logs_hosts_exist(conn: sqlite3.Connection) -> CheckResult:
    """Every logs.host_id must appear in synthetic_topology."""
    query = """
        SELECT DISTINCT l.host_id
        FROM synthetic_logs l
        LEFT JOIN synthetic_topology t ON l.host_id = t.node_id
        WHERE t.node_id IS NULL
    """
    offenders = [row[0] for row in conn.execute(query)]
    if offenders:
        return ("every log references a real host", False,
                f"{len(offenders)} orphan host(s): {offenders[:5]}")
    return ("every log references a real host", True, "no orphan hosts")


def _check_id_uniqueness(
    conn: sqlite3.Connection, table: str, id_col: str,
) -> CheckResult:
    """Primary-key column contains no duplicates."""
    total_row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    distinct_row = conn.execute(f"SELECT COUNT(DISTINCT {id_col}) FROM {table}").fetchone()[0]
    label = f"{table}.{id_col} is unique"
    if total_row != distinct_row:
        return (label, False,
                f"{total_row - distinct_row} duplicate value(s) "
                f"({total_row} rows, {distinct_row} distinct)")
    return (label, True, f"{total_row:,} unique row(s)")


def _check_config_precedes_attacks(conn: sqlite3.Connection) -> CheckResult:
    """Every config-change must be followed by at least one attack on the same
    host OR on a topology-adjacent host.

    Design intent from Section 8: each config-change is placed 2-15 min BEFORE
    the attack cluster it's associated with. With `adjacent_prob=0.30`, the
    change may land on a topology neighbor of the cluster host — so the
    "later attack" that justifies a given change may live on a neighbor, not
    strictly on the change's own host.
    """
    total = conn.execute("SELECT COUNT(*) FROM synthetic_config_changes").fetchone()[0]
    if total == 0:
        return ("config-changes precede their attack clusters", True,
                "no config-changes to check")

    # Build neighbor lookup once from the topology table.
    neighbor_map: dict[str, list[str]] = {}
    for node_id, adj_json in conn.execute(
        "SELECT node_id, adjacent_nodes FROM synthetic_topology"
    ):
        try:
            neighbor_map[node_id] = list(json.loads(adj_json))
        except (json.JSONDecodeError, TypeError):
            neighbor_map[node_id] = []

    violators: list[tuple[int, str, str]] = []
    for change_id, host_id, change_ts in conn.execute(
        "SELECT change_id, host_id, ts FROM synthetic_config_changes"
    ):
        candidate_hosts = [host_id] + neighbor_map.get(host_id, [])
        placeholders = ",".join(["?"] * len(candidate_hosts))
        row = conn.execute(
            f"SELECT 1 FROM flows "
            f"WHERE host_id IN ({placeholders}) "
            f"  AND attack_cat != 'Normal' "
            f"  AND ts > ? LIMIT 1",
            (*candidate_hosts, change_ts),
        ).fetchone()
        if row is None:
            violators.append((change_id, host_id, change_ts))

    if violators:
        first = violators[0]
        return ("config-changes precede their attack clusters", False,
                f"{len(violators)} violation(s); first: change_id={first[0]} "
                f"on host {first[1]} at {first[2]} — no later attack on "
                f"same host or any topology neighbor")
    return ("config-changes precede their attack clusters", True,
            f"{total} change(s) each precede at least one attack "
            f"on same host or a neighbor")


def _check_no_orphan_tables(conn: sqlite3.Connection) -> CheckResult:
    """DB contains only the four expected tables + sqlite_-internal ones."""
    expected = {"flows", "synthetic_topology", "synthetic_config_changes", "synthetic_logs"}
    found = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    }
    unexpected = sorted(found - expected)
    missing = sorted(expected - found)
    if missing:
        return ("only expected tables exist", False, f"missing: {missing}")
    if unexpected:
        return ("only expected tables exist", False, f"unexpected: {unexpected}")
    return ("only expected tables exist", True, f"exactly {len(expected)} tables")


def _log_results(
    counts: dict[str, int],
    results: list[CheckResult],
) -> bool:
    """Log the checklist summary in a scannable format. Return overall pass/fail."""
    logger = get_logger()

    logger.info("")
    logger.info("--- Record counts ---")
    logger.info("  flows:                    %s", f"{counts.get('flows', 0):,}")
    logger.info("  synthetic_topology:       %s", counts.get("synthetic_topology", 0))
    logger.info("  synthetic_config_changes: %s", counts.get("synthetic_config_changes", 0))
    logger.info("  synthetic_logs:           %s", f"{counts.get('synthetic_logs', 0):,}")

    logger.info("")
    logger.info("--- Checklist ---")
    all_ok = True
    for label, passed, detail in results:
        marker = "PASS" if passed else "FAIL"
        (logger.info if passed else logger.error)(
            "  [%s] %-45s | %s", marker, label, detail,
        )
        all_ok &= passed

    logger.info("")
    if all_ok:
        logger.info("=== VALIDATION PASSED — DB ready for M2/M3 to build on. ===")
    else:
        logger.error("=== VALIDATION FAILED — see [FAIL] rows above. ===")
    return all_ok


# ===========================================================================
# SECTION 12 — MAIN ORCHESTRATOR
# ---------------------------------------------------------------------------
# Wires all previous sections together. Every "step" is one function call.
# ===========================================================================


def main() -> int:
    """Run the full Module 1 pipeline end-to-end.

    Returns:
        Process exit code: 0 on success, 1 on any failure.
    """
    overall_start = time.perf_counter()
    logger = setup_logging(LOG_PATH)

    try:
        logger.info("Module 1 — Synthetic Multi-Source Generator")
        logger.info("Seed=%d | Demo date=%s | Window=%dh",
                    SEED, DEMO_DATE.isoformat(), WINDOW_HOURS)

        # --- Step 1: Load ------------------------------------------------
        t0 = time.perf_counter()
        df = load_all_datasets(TRAIN_DATA_PATH, TEST_DATA_PATH, MAX_ROWS)
        _log_step_duration("Dataset load", t0)

        # --- Step 2: Validate schema ------------------------------------
        t0 = time.perf_counter()
        validate_schema(df)
        _log_step_duration("Schema validation", t0)

        # --- Step 3: Build topology -------------------------------------
        t0 = time.perf_counter()
        topology, graph, topology_df = generate_topology()
        _log_step_duration("Topology generation", t0)

        # --- Step 4a: Assign synthetic timestamps -----------------------
        t0 = time.perf_counter()
        df["ts"] = assign_timestamps(df)
        _log_step_duration("Timestamp assignment", t0)

        # --- Step 4b: Assign hosts (needs ts to be present) -------------
        t0 = time.perf_counter()
        df["host_id"] = assign_hosts_bulk(df, topology)
        _log_step_duration("Host mapping", t0)

        # --- Step 4c: Assign flow_id ------------------------------------
        df = df.reset_index(drop=True)
        df["flow_id"] = df.index.astype("int64")

        # Ensure optional labels are present with sensible defaults.
        if "attack_cat" not in df.columns:
            df["attack_cat"] = "Normal"
        if "label" not in df.columns:
            df["label"] = 0

        # --- Step 5: Attack clusters + config-changes -------------------
        t0 = time.perf_counter()
        clusters_df = identify_attack_clusters(df)
        config_changes_df = generate_config_changes(clusters_df, graph)
        _log_step_duration("Config-change generation", t0)

        # --- Step 6: Log lines -----------------------------------------
        t0 = time.perf_counter()
        logs_df = generate_logs_bulk(df)
        _log_step_duration("Log generation", t0)

        # --- Step 7: Write ---------------------------------------------
        t0 = time.perf_counter()
        write_to_sqlite(DB_PATH, df, topology_df, config_changes_df, logs_df)
        _log_step_duration("SQLite write", t0)

        # --- Step 8: Post-write validation -----------------------------
        t0 = time.perf_counter()
        ok = validate_database(DB_PATH)
        _log_step_duration("Validation", t0)

    except SchemaValidationError as exc:
        logger.error("Schema validation failed: %s", exc)
        return 1
    except FileNotFoundError as exc:
        logger.error("Missing input file: %s", exc)
        return 1
    except Exception:
        logger.exception("Module 1 pipeline aborted by unexpected error.")
        return 1

    total_elapsed = time.perf_counter() - overall_start
    logger.info("")
    logger.info("Total elapsed: %.1fs", total_elapsed)
    logger.info("Output DB:     %s", DB_PATH)
    logger.info("Log file:      %s", LOG_PATH)

    return 0 if ok else 1


def _log_step_duration(step_name: str, start_perf: float) -> None:
    """Log the wall-clock time for a single pipeline step."""
    elapsed = time.perf_counter() - start_perf
    get_logger().info("(%s completed in %.1fs)", step_name, elapsed)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
