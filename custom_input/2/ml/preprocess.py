"""
preprocess.py — Module 2 data preprocessing.

Encoders AND per-feature medians are persisted together, so a custom
record's missing numeric fields get filled with a value the model has
actually seen a lot of (the training median), not 0.0 - which read as an
extreme, attack-like value to the model and inflated confidence/SHAP
artificially. transform_single() also now reports which features were
imputed, so downstream code can flag predictions/evidence that lean on
estimated rather than real data.

fit_and_save_encoders() only re-derives things that already existed
implicitly in the original training data - it never touches or retrains
the XGBoost model.
"""

import logging
import sqlite3
import joblib
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from sklearn.preprocessing import LabelEncoder

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DROP_COLS = ['flow_id', 'ts', 'host_id', 'split', 'attack_cat', 'label']


class DataPreprocessor:
    """Handles raw data extraction from corrupted/healthy SQLite schemas and column encoding."""

    def __init__(self):
        self.categorical_cols = ['proto', 'service', 'state']
        self.encoders: Dict[str, LabelEncoder] = {col: LabelEncoder() for col in self.categorical_cols}
        self.feature_cols: Optional[List[str]] = None
        self.medians: Dict[str, float] = {}   # NEW: numeric_feature -> training median
        self._is_fitted = False

    def load_data_from_sqlite(self, db_path: str) -> pd.DataFrame:
        """Extracts data safely bypassing potentially malformed database indexes."""
        try:
            logger.info(f"Connecting to SQLite database at: {db_path}")
            conn = sqlite3.connect(db_path, isolation_level=None)
            cursor = conn.cursor()

            cursor.execute("PRAGMA writable_schema = ON;")
            cursor.execute("SELECT * FROM flows")
            rows = cursor.fetchall()

            cursor.execute("PRAGMA table_info(flows);")
            columns = [col[1] for col in cursor.fetchall()]
            conn.close()

            df = pd.DataFrame(rows, columns=columns)
            if df.empty:
                raise ValueError("Extracted database table contains 0 rows.")

            logger.info(f"Successfully recovered {len(df)} lines from target matrix table.")
            return df
        except Exception as e:
            logger.error(f"Failed parsing binary database stream: {str(e)}")
            raise

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Encodes categorical fields deterministically. Unchanged behavior -
        used by the existing batch train/predict pipeline."""
        df_encoded = df.copy()
        for col in self.categorical_cols:
            if col in df_encoded.columns:
                df_encoded[col] = df_encoded[col].astype(str).fillna('unknown')
                df_encoded[col] = self.encoders[col].fit_transform(df_encoded[col])
        self._is_fitted = True
        return df_encoded

    # ------------------------------------------------------------------
    # Persistence: encoders + feature_cols + medians, all in one file
    # ------------------------------------------------------------------
    def fit_and_save_encoders(self, db_path: str, out_path: str) -> List[str]:
        """One-time bootstrap: fits encoders AND computes per-numeric-feature
        medians on the full dataset.db vocabulary/distribution, saves both to
        disk. Does NOT train or touch the XGBoost model - only re-derives
        statistics that already existed implicitly in the training data.
        """
        df = self.load_data_from_sqlite(db_path)
        self.fit_transform(df)   # fits self.encoders in place

        self.feature_cols = [c for c in df.columns if c not in DROP_COLS]
        numeric_cols = [c for c in self.feature_cols if c not in self.categorical_cols]

        self.medians = {
            col: float(pd.to_numeric(df[col], errors="coerce").median())
            for col in numeric_cols
        }

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "encoders": self.encoders,
                "feature_cols": self.feature_cols,
                "medians": self.medians,
            },
            out_path,
        )
        logger.info(
            f"Saved fitted encoders + feature_cols ({len(self.feature_cols)} cols) "
            f"+ medians ({len(self.medians)} numeric cols) to {out_path}"
        )
        logger.info(f"Medians: {self.medians}")
        return self.feature_cols

    def load_encoders(self, encoders_path: str) -> None:
        """Loads previously-fitted encoders + feature_cols + medians from disk.
        Required before calling transform_single()."""
        bundle = joblib.load(encoders_path)
        self.encoders = bundle["encoders"]
        self.feature_cols = bundle["feature_cols"]
        self.medians = bundle.get("medians", {})   # backward-compatible if old pkl lacks it
        self._is_fitted = True
        logger.info(
            f"Loaded encoders + {len(self.feature_cols)} feature_cols + "
            f"{len(self.medians)} medians from {encoders_path}"
        )

    # ------------------------------------------------------------------
    # Single-record transform for custom/live input
    # ------------------------------------------------------------------
    def transform_single(self, record: Dict) -> Tuple[pd.DataFrame, List[str]]:
        """Transforms ONE raw record into the exact encoded, ordered feature
        row the trained model expects.

        Returns (encoded_dataframe, imputed_features) - imputed_features
        lists which numeric columns had no real value and were filled with
        the training median (NOT 0.0), so callers can flag predictions/SHAP
        entries that lean on estimated rather than observed data.

        Unseen categorical values fall back to a known class (logged as a
        warning) instead of sklearn's default hard crash.
        """
        if not self._is_fitted or self.feature_cols is None:
            raise RuntimeError(
                "Encoders not loaded. Call load_encoders(path) first "
                "(run bootstrap_encoders.py once if models/encoders.pkl "
                "doesn't exist yet - this does not retrain the model)."
            )

        row = {}
        imputed_features: List[str] = []

        for col in self.feature_cols:
            if col in self.categorical_cols:
                raw_val = str(record.get(col, "unknown"))
                row[col] = self._safe_encode(col, raw_val)
            else:
                if col not in record or record[col] is None:
                    fallback = self.medians.get(col, 0.0)
                    logger.warning(
                        f"transform_single: missing numeric feature '{col}', "
                        f"filling with training median ({fallback:.4f}) instead of 0.0"
                    )
                    row[col] = fallback
                    imputed_features.append(col)
                else:
                    row[col] = float(record[col])

        df = pd.DataFrame([row], columns=self.feature_cols)
        return df, imputed_features

    def _safe_encode(self, col: str, value: str) -> int:
        """LabelEncoder.transform but falls back instead of raising on unseen labels."""
        encoder = self.encoders[col]
        if value in encoder.classes_:
            return int(encoder.transform([value])[0])
        logger.warning(
            f"transform_single: unseen value '{value}' for column '{col}' "
            f"(not in training vocabulary) - falling back to '{encoder.classes_[0]}'."
        )
        return int(encoder.transform([encoder.classes_[0]])[0])