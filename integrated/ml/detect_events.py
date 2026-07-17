import os
import joblib
import pandas as pd
import numpy as np
import shap
import sqlite3
import json
from typing import List, Dict


def _ensure_anomaly_scores_table(conn):
    """Create only the anomaly_scores table if absent. Deliberately does NOT
    create the downstream M3/M5 tables (those are owned by
    db/schema_downstream.sql) to avoid conflicting incidents schemas."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS anomaly_scores (
               flow_id           INTEGER PRIMARY KEY,
               attack_cat_pred   TEXT NOT NULL,
               confidence        REAL NOT NULL,
               shap_top_features TEXT
           )"""
    )
    conn.commit()

# Set up paths to model artifacts
MODULE2_DIR = os.path.dirname(os.path.abspath(__file__))
PREPROCESSOR_PATH = os.path.join(MODULE2_DIR, "preprocessor.joblib")
LABEL_ENCODER_PATH = os.path.join(MODULE2_DIR, "label_encoder.joblib")
MODEL_MULTICLASS_PATH = os.path.join(MODULE2_DIR, "model_multiclass.joblib")
MODEL_BINARY_PATH = os.path.join(MODULE2_DIR, "model_binary.joblib")
FEATURE_NAMES_PATH = os.path.join(MODULE2_DIR, "encoded_feature_names.joblib")

_preprocessor = None
_label_encoder = None
_model_multiclass = None
_model_binary = None
_encoded_feature_names = None
_explainer = None

def load_ml_artifacts():
    """
    Loads all saved model preprocessors, classifiers, and label encoders on demand.
    Initializes the SHAP TreeExplainer for feature importance mapping.
    """
    global _preprocessor, _label_encoder, _model_multiclass, _model_binary, _encoded_feature_names, _explainer
    if _preprocessor is None:
        if not os.path.exists(PREPROCESSOR_PATH):
            raise FileNotFoundError(
                f"Model artifacts not found in {MODULE2_DIR}. Please run training first."
            )
        _preprocessor = joblib.load(PREPROCESSOR_PATH)
        _label_encoder = joblib.load(LABEL_ENCODER_PATH)
        _model_multiclass = joblib.load(MODEL_MULTICLASS_PATH)
        _model_binary = joblib.load(MODEL_BINARY_PATH)
        _encoded_feature_names = joblib.load(FEATURE_NAMES_PATH)
        _explainer = shap.TreeExplainer(_model_multiclass)

def score_flow(flow_dict: dict) -> dict:
    """
    Scores a single flow record for multiclass classification and binary anomalies.

    :param flow_dict: Dictionary containing raw flow features.
    :return: Dictionary containing predicted class, confidence, and binary label.
    """
    load_ml_artifacts()

    # Preprocess feature columns
    df = pd.DataFrame([flow_dict])
    feature_cols = [
        'proto', 'service', 'state', 'sbytes', 'dbytes', 'rate', 
        'sload', 'dload', 'dur', 'sinpkt', 'dinpkt', 
        'ct_src_dport_ltm', 'ct_dst_sport_ltm'
    ]
    X = df[feature_cols]
    X_encoded = _preprocessor.transform(X)

    # Multiclass predictions
    proba_multiclass = _model_multiclass.predict_proba(X_encoded)[0]
    pred_class_idx = np.argmax(proba_multiclass)
    attack_cat_pred = _label_encoder.classes_[pred_class_idx]
    confidence = float(proba_multiclass[pred_class_idx])

    # Binary anomaly prediction (0 = normal, 1 = anomalous)
    label_pred = int(_model_binary.predict(X_encoded)[0])

    return {
        "attack_cat_pred": attack_cat_pred,
        "confidence": confidence,
        "label_pred": label_pred
    }

def explain_flow_shap(flow_dict: dict) -> List[dict]:
    """
    Computes SHAP values explaining the model prediction for a single flow.

    :param flow_dict: Dictionary containing raw flow features.
    :return: List of sorted dictionaries representing feature contributions.
    """
    load_ml_artifacts()

    # Preprocess
    df = pd.DataFrame([flow_dict])
    feature_cols = [
        'proto', 'service', 'state', 'sbytes', 'dbytes', 'rate', 
        'sload', 'dload', 'dur', 'sinpkt', 'dinpkt', 
        'ct_src_dport_ltm', 'ct_dst_sport_ltm'
    ]
    X = df[feature_cols]
    X_encoded = _preprocessor.transform(X)

    # Get predicted class index
    proba_multiclass = _model_multiclass.predict_proba(X_encoded)[0]
    pred_class_idx = np.argmax(proba_multiclass)

    # Compute SHAP values: shape is (n_samples, n_features, n_classes)
    sv = _explainer.shap_values(X_encoded)
    
    # Extract values for the predicted class
    shap_vals_class = sv[0, :, pred_class_idx]

    # Map back to feature names
    explanations = []
    for name, val in zip(_encoded_feature_names, shap_vals_class):
        explanations.append({
            "feature": name,
            "contribution": float(val)
        })

    # Sort by absolute impact descending
    explanations.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return explanations

def batch_score_test_set(db_path="data/processed/rca.db", batch_size=5000):
    """
    Batch scores the entire testing split in the database, generating
    multiclass labels, confidence scores, and SHAP top features. Writes
    all scores back into the anomaly_scores SQLite table.
    """
    load_ml_artifacts()

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    _ensure_anomaly_scores_table(conn)
    test_df = pd.read_sql_query("SELECT * FROM flows WHERE split = 'test'", conn)

    if len(test_df) == 0:
        print("No test flows to score.")
        conn.close()
        return

    print(f"Scoring {len(test_df)} test flows...")

    feature_cols = [
        'proto', 'service', 'state', 'sbytes', 'dbytes', 'rate', 
        'sload', 'dload', 'dur', 'sinpkt', 'dinpkt', 
        'ct_src_dport_ltm', 'ct_dst_sport_ltm'
    ]
    X_test = test_df[feature_cols]
    X_test_encoded = _preprocessor.transform(X_test)

    # Batch multiclass predictions
    print("Predicting multiclass categories and confidences...")
    proba_multiclass = _model_multiclass.predict_proba(X_test_encoded)
    pred_class_indices = np.argmax(proba_multiclass, axis=1)
    attack_cat_preds = _label_encoder.classes_[pred_class_indices]
    confidences = proba_multiclass[np.arange(len(proba_multiclass)), pred_class_indices]

    # Batch compute SHAP values in chunks to prevent memory limits
    print("Computing SHAP values in batches...")
    n_samples = len(test_df)
    all_top_features = []

    for start_idx in range(0, n_samples, batch_size):
        end_idx = min(start_idx + batch_size, n_samples)
        X_batch = X_test_encoded[start_idx:end_idx]
        
        # Computes TreeExplainer SHAP array: shape (batch_size, n_features, n_classes)
        sv_batch = _explainer.shap_values(X_batch)
        
        for i in range(len(X_batch)):
            global_idx = start_idx + i
            pred_idx = pred_class_indices[global_idx]
            
            # Extract features for this flow's predicted class
            flow_shap = sv_batch[i, :, pred_idx]
            
            # Get top 5 features by absolute contribution
            top_indices = np.argsort(np.abs(flow_shap))[::-1][:5]
            top_features = [
                {
                    "feature": _encoded_feature_names[idx],
                    "contribution": float(flow_shap[idx])
                }
                for idx in top_indices
            ]
            all_top_features.append(json.dumps(top_features))

    print("Writing scores to anomaly_scores table...")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM anomaly_scores")

    insert_data = []
    for idx, row in test_df.iterrows():
        insert_data.append((
            int(row['flow_id']),
            str(attack_cat_preds[idx]),
            float(confidences[idx]),
            str(all_top_features[idx])
        ))

    cursor.executemany(
        "INSERT INTO anomaly_scores (flow_id, attack_cat_pred, confidence, shap_top_features) VALUES (?, ?, ?, ?)",
        insert_data
    )
    conn.commit()
    conn.close()
    print("Batch scoring completed successfully!")

if __name__ == "__main__":
    batch_score_test_set()
