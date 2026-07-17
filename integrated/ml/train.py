import sqlite3
import os
import joblib
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight

# Save artifacts next to this module (integrated/ml/) by default.
_DEFAULT_OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def train_anomaly_models(db_path="data/processed/rca.db", output_dir=_DEFAULT_OUTPUT_DIR):
    """
    Loads UNSW-NB15 flow data from SQLite, preprocesses it,
    trains multiclass and binary XGBoost models, and evaluates them.
    Saves models and preprocessors to the output_dir.
    """
    print(f"Loading data from {db_path}...")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    # Establish connection
    conn = sqlite3.connect(db_path)

    # Load train and test splits
    print("Reading flows table...")
    train_df = pd.read_sql_query("SELECT * FROM flows WHERE split = 'train'", conn)
    test_df = pd.read_sql_query("SELECT * FROM flows WHERE split = 'test'", conn)
    conn.close()

    print(f"Loaded {len(train_df)} training rows, {len(test_df)} testing rows.")

    # Define features and target
    feature_cols = [
        'proto', 'service', 'state', 'sbytes', 'dbytes', 'rate', 
        'sload', 'dload', 'dur', 'sinpkt', 'dinpkt', 
        'ct_src_dport_ltm', 'ct_dst_sport_ltm'
    ]
    categorical_cols = ['proto', 'service', 'state']
    numeric_cols = [c for c in feature_cols if c not in categorical_cols]

    X_train = train_df[feature_cols]
    y_train_multiclass_raw = train_df['attack_cat']
    y_train_binary = train_df['label']

    X_test = test_df[feature_cols]
    y_test_multiclass_raw = test_df['attack_cat']
    y_test_binary = test_df['label']

    # Preprocessing pipelines
    print("Fitting ColumnTransformer preprocessor...")
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_cols),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_cols)
        ]
    )

    X_train_encoded = preprocessor.fit_transform(X_train)
    X_test_encoded = preprocessor.transform(X_test)

    # Get the feature names after transformation
    num_features = numeric_cols
    cat_features = preprocessor.named_transformers_['cat'].get_feature_names_out(categorical_cols).tolist()
    encoded_feature_names = num_features + cat_features

    # Label encode the target variable for multiclass
    print("Fitting LabelEncoder on attack_cat...")
    le = LabelEncoder()
    y_train_multiclass = le.fit_transform(y_train_multiclass_raw)
    y_test_multiclass = le.transform(y_test_multiclass_raw)

    # 1. Train Multiclass XGBoost Model
    print("Training Multiclass XGBoost Model (10 classes)...")
    clf_multiclass = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        eval_metric='mlogloss',
        n_jobs=-1
    )
    # Balanced sample weights so rare classes (Worms ~174 rows, Shellcode,
    # Backdoor) are not drowned out by Normal/Generic — lifts macro-F1.
    sample_weight_mc = compute_sample_weight(class_weight="balanced", y=y_train_multiclass)
    clf_multiclass.fit(X_train_encoded, y_train_multiclass, sample_weight=sample_weight_mc)

    # Evaluate Multiclass Model
    print("Evaluating Multiclass Model...")
    y_pred_multiclass = clf_multiclass.predict(X_test_encoded)
    acc_m = accuracy_score(y_test_multiclass, y_pred_multiclass)
    f1_m_weighted = f1_score(y_test_multiclass, y_pred_multiclass, average='weighted')
    f1_m_macro = f1_score(y_test_multiclass, y_pred_multiclass, average='macro')
    
    print("\n=== MULTICLASS MODEL PERFORMANCE ===")
    print(f"Accuracy: {acc_m:.4f}")
    print(f"Weighted F1: {f1_m_weighted:.4f}")
    print(f"Macro F1: {f1_m_macro:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test_multiclass, y_pred_multiclass, target_names=le.classes_))

    # 2. Train Binary XGBoost Model
    print("Training Binary XGBoost Model (normal vs anomalous)...")
    clf_binary = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        eval_metric='logloss',
        n_jobs=-1
    )
    sample_weight_bin = compute_sample_weight(class_weight="balanced", y=y_train_binary)
    clf_binary.fit(X_train_encoded, y_train_binary, sample_weight=sample_weight_bin)

    # Evaluate Binary Model
    print("Evaluating Binary Model...")
    y_pred_binary = clf_binary.predict(X_test_encoded)
    acc_b = accuracy_score(y_test_binary, y_pred_binary)
    f1_b_weighted = f1_score(y_test_binary, y_pred_binary, average='weighted')
    
    print("\n=== BINARY MODEL PERFORMANCE ===")
    print(f"Accuracy: {acc_b:.4f}")
    print(f"Weighted F1: {f1_b_weighted:.4f}")

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Save artifacts using joblib
    print(f"\nSaving artifacts to {output_dir}...")
    joblib.dump(preprocessor, os.path.join(output_dir, "preprocessor.joblib"))
    joblib.dump(le, os.path.join(output_dir, "label_encoder.joblib"))
    joblib.dump(clf_multiclass, os.path.join(output_dir, "model_multiclass.joblib"))
    joblib.dump(clf_binary, os.path.join(output_dir, "model_binary.joblib"))
    joblib.dump(encoded_feature_names, os.path.join(output_dir, "encoded_feature_names.joblib"))

    print("Model training pipeline completed successfully!")

if __name__ == "__main__":
    train_anomaly_models()
