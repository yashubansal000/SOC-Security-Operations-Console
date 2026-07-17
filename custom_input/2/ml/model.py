import logging
import xgboost as xgb
from typing import Dict, Any
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
import joblib
import pandas as pd

logger = logging.getLogger(__name__)


class IncidentDetector:
    """Manages training runtime parameters and mathematical scoring metrics using XGBoost."""
    
    def __init__(self):
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            eval_metric='logloss',
            use_label_encoder=False
        )

    def train_model(self, X_train: pd.DataFrame, y_train: pd.Series) -> None:
        logger.info("Initializing XGBoost classifier execution...")
        self.model.fit(X_train, y_train.astype(int))
        logger.info("Model optimization baseline reached.")

    def evaluate_model(self, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, Any]:
        preds = self.model.predict(X_test)
        y_test_int = y_test.astype(int)
        
        return {
            "accuracy": float(accuracy_score(y_test_int, preds)),
            "precision": float(precision_score(y_test_int, preds, zero_division=0)),
            "recall": float(recall_score(y_test_int, preds, zero_division=0)),
            "f1": float(f1_score(y_test_int, preds, zero_division=0)),
            "confusion_matrix": confusion_matrix(y_test_int, preds).tolist()
        }

    def save_artifact(self, path: str) -> None:
        joblib.dump(self.model, path)
        logger.info(f"Model brain signatures saved to {path}")

    def load_artifact(self, path: str) -> None:
        self.model = joblib.load(path)
        logger.info(f"Model brain loaded successfully from {path}")