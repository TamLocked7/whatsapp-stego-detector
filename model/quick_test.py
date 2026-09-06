"""
quick_test.py -- sanity-check the trained model directly, no browser/WhatsApp needed.
Run from inside model/:  python quick_test.py
"""
import glob
from feature_extraction import extract_features
from joblib import load

model = load("stego_detector.pkl")

for label, folder in [("clean", "../demo_data/clean"), ("stego", "../demo_data/stego")]:
    files = sorted(glob.glob(f"{folder}/*.png"))[:10]
    correct = 0
    for f in files:
        feat = extract_features(f).reshape(1, -1)
        pred = model.predict(feat)[0]
        pred_label = "suspicious" if pred == 1 else "safe"
        expected = "suspicious" if label == "stego" else "safe"
        correct += pred_label == expected
        print(f"{f:35s} -> {pred_label:12s} (expected {expected})")
    print(f"{label}: {correct}/{len(files)} correct\n")
