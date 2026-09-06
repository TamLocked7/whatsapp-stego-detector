"""
train_model.py
---------------
Trains the WhatsApp Steganography Detector model.

USAGE (on the real Kaggle dataset):
    1. Download & unzip "Stego-Images-Dataset" from:
       https://www.kaggle.com/datasets/marcozuppelli/stegoimagesdataset
    2. Arrange (or point --clean_dir / --stego_dir at) folders of clean vs
       stego images, e.g.:
           data/clean/*.png
           data/stego/*.png
    3. Run:
           python train_model.py --clean_dir data/clean --stego_dir data/stego

USAGE (quick demo, no download needed):
    python make_demo_dataset.py        # builds ../demo_data/{clean,stego}
    python train_model.py              # uses ../demo_data by default

Outputs:
    stego_detector.pkl   -- trained sklearn Pipeline (StandardScaler + model)
    metrics.json         -- accuracy / precision / recall / F1 / ROC-AUC / confusion matrix
    feature_importance.png (if matplotlib available)
"""

import argparse
import glob
import json
import os
import time

import numpy as np
from joblib import dump
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)

from feature_extraction import extract_features, FEATURE_NAMES

HERE = os.path.dirname(os.path.abspath(__file__))


def build_dataset(clean_dir, stego_dir, max_per_class=None):
    clean_paths = sorted(glob.glob(os.path.join(clean_dir, "*")))
    stego_paths = sorted(glob.glob(os.path.join(stego_dir, "*")))
    if max_per_class:
        clean_paths = clean_paths[:max_per_class]
        stego_paths = stego_paths[:max_per_class]

    X, y = [], []
    t0 = time.time()
    for p in clean_paths:
        try:
            X.append(extract_features(p))
            y.append(0)  # 0 = clean / safe
        except Exception as e:
            print(f"skip {p}: {e}")
    for p in stego_paths:
        try:
            X.append(extract_features(p))
            y.append(1)  # 1 = stego / suspicious
        except Exception as e:
            print(f"skip {p}: {e}")
    print(f"Extracted features for {len(X)} images in {time.time()-t0:.1f}s")
    return np.array(X), np.array(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean_dir", default=os.path.join(HERE, "..", "demo_data", "clean"))
    ap.add_argument("--stego_dir", default=os.path.join(HERE, "..", "demo_data", "stego"))
    ap.add_argument("--max_per_class", type=int, default=None,
                     help="cap images per class (useful for a quick run on the full 44k dataset)")
    ap.add_argument("--out", default=os.path.join(HERE, "stego_detector.pkl"))
    args = ap.parse_args()

    X, y = build_dataset(args.clean_dir, args.stego_dir, args.max_per_class)
    if len(X) < 10:
        raise SystemExit("Not enough images found -- check --clean_dir / --stego_dir paths.")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=300,
            max_depth=None,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )),
    ])

    print("Training RandomForestClassifier on steganalysis features...")
    clf.fit(X_train, y_train)

    # 5-fold cross validation on the training split for a more robust estimate
    cv_scores = cross_val_score(clf, X_train, y_train, cv=5, scoring="f1")

    y_pred = clf.predict(X_test)
    y_proba = clf.predict_proba(X_test)[:, 1]

    metrics = {
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred)),
        "recall": float(recall_score(y_test, y_pred)),
        "f1": float(f1_score(y_test, y_pred)),
        "roc_auc": float(roc_auc_score(y_test, y_proba)),
        "cv_f1_mean": float(cv_scores.mean()),
        "cv_f1_std": float(cv_scores.std()),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }

    print(json.dumps(metrics, indent=2))
    print("\n" + classification_report(y_test, y_pred, target_names=["clean/safe", "stego/suspicious"]))

    # feature importances (from the RandomForest inside the pipeline)
    importances = clf.named_steps["rf"].feature_importances_
    ranked = sorted(zip(FEATURE_NAMES, importances), key=lambda t: -t[1])
    metrics["feature_importance"] = [(n, float(v)) for n, v in ranked]
    print("\nTop features:")
    for name, val in ranked[:8]:
        print(f"  {name:22s} {val:.4f}")

    dump(clf, args.out)
    with open(os.path.join(HERE, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nSaved model -> {args.out}")
    print("Saved metrics -> metrics.json")


if __name__ == "__main__":
    main()
