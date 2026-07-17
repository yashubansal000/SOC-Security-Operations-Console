import os
import time
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from preprocess import DataPreprocessor
from model import IncidentDetector
from shap_explain import SHAPEvidenceGenerator
from utils import build_incident_object
from pathlib import Path

_ML_DIR = Path(__file__).resolve().parent   # combined/2/ml/
MODEL_PATH = str(_ML_DIR.parent / "models" / "xgboost_model.pkl")
ENCODERS_PATH = str(_ML_DIR.parent / "models" / "encoders.pkl")
DB_PATH = os.path.join("data", "dataset.db")


def run_batch_inference_pipeline():
    db_path = DB_PATH
    model_path = MODEL_PATH

    preprocessor = DataPreprocessor()
    df = preprocessor.load_data_from_sqlite(db_path)
    df_encoded = preprocessor.fit_transform(df)

    test_mask = df_encoded['split'].str.lower() == 'test'
    drop_cols = ['flow_id', 'ts', 'host_id', 'split', 'attack_cat', 'label']
    feature_cols = [c for c in df_encoded.columns if c not in drop_cols]

    X_test = df_encoded.loc[test_mask, feature_cols]
    y_test = df_encoded.loc[test_mask, 'label']
    raw_test_reference = df.loc[test_mask].copy()

    detector = IncidentDetector()
    detector.load_artifact(model_path)
    preds = detector.model.predict(X_test)
    probs = detector.model.predict_proba(X_test)[:, 1]

    metrics = detector.evaluate_model(X_test, y_test)
    print("Evaluation Metrics Calculated:\n", json.dumps(metrics, indent=4))

    scores_df = pd.DataFrame({'prediction': preds, 'anomaly_probability': probs})
    scores_df.to_csv(os.path.join("outputs", "anomaly_scores.csv"), index=False)

    anomalous_positions = np.where(preds == 1)[0]
    incident_objects = []

    if len(anomalous_positions) > 0:
        X_anomalous = X_test.iloc[anomalous_positions]
        evidence_engine = SHAPEvidenceGenerator(detector.model, feature_cols)
        shap_data, evidence_logs = evidence_engine.extract_incident_shap(X_anomalous)

        for i, target_idx in enumerate(anomalous_positions):
            row_raw = raw_test_reference.iloc[target_idx]
            prob_score = float(probs[target_idx])

            ticket = build_incident_object(
                orig_idx=target_idx,
                row_raw=row_raw,
                prob_score=prob_score,
                shap_data=shap_data[i],
                evidence=evidence_logs[i]
            )
            incident_objects.append(ticket)

    with open(os.path.join("outputs", "incident_objects.json"), "w") as f:
        json.dump(incident_objects, f, indent=4)

    print(f"Batch inference processing finalized. Created {len(incident_objects)} incident objects.")


# ---------------------------------------------------------------------
# NEW: single custom-record inference (no dataset.db, no retraining)
# ---------------------------------------------------------------------
_single_preprocessor: Optional[DataPreprocessor] = None
_single_detector: Optional[IncidentDetector] = None
_single_shap_engine: Optional[SHAPEvidenceGenerator] = None


def _get_single_record_pipeline():
    """Lazily loads the trained model + saved encoders once per process,
    reused across repeated predict_single() calls instead of reloading
    from disk every time."""
    global _single_preprocessor, _single_detector, _single_shap_engine

    if _single_preprocessor is None:
        if not os.path.exists(ENCODERS_PATH):
            raise FileNotFoundError(
                f"{ENCODERS_PATH} not found. Run `python3 bootstrap_encoders.py` "
                f"once first (this does NOT retrain the model, it only saves "
                f"the encoders that already existed implicitly during training)."
            )
        _single_preprocessor = DataPreprocessor()
        _single_preprocessor.load_encoders(ENCODERS_PATH)

    if _single_detector is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"{MODEL_PATH} not found. Train the model first via train.py.")
        _single_detector = IncidentDetector()
        _single_detector.load_artifact(MODEL_PATH)

    if _single_shap_engine is None:
        _single_shap_engine = SHAPEvidenceGenerator(
            _single_detector.model, _single_preprocessor.feature_cols
        )

    return _single_preprocessor, _single_detector, _single_shap_engine


def predict_single(record: Dict[str, Any], orig_idx: int = None) -> Optional[Dict[str, Any]]:
    """Scores ONE custom flow record against the already-trained model.
    Does not touch dataset.db and does not retrain anything.

    Missing numeric fields are filled with the training median (not 0.0)
    and tracked in the returned object's imputed_features list, so any
    confidence/evidence leaning on estimated data is visible, not hidden.
    """
    preprocessor, detector, shap_engine = _get_single_record_pipeline()

    X_single, imputed_features = preprocessor.transform_single(record)

    pred = int(detector.model.predict(X_single)[0])
    prob = float(detector.model.predict_proba(X_single)[:, 1][0])

    if pred != 1:
        return None

    shap_data_list, evidence_logs = shap_engine.extract_incident_shap(X_single)

    if orig_idx is None:
        orig_idx = int(time.time() * 1000) % 100000

    ticket = build_incident_object(
        orig_idx=orig_idx,
        row_raw=record,
        prob_score=prob,
        shap_data=shap_data_list[0],
        evidence=evidence_logs[0],
        imputed_features=imputed_features,
    )
    return ticket