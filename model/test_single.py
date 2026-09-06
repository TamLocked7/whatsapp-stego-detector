"""
test_single.py -- run the trained model against ONE image file, e.g. one you
downloaded from WhatsApp, to check it survived the trip intact.

Usage:
    python test_single.py "C:\\Users\\YourName\\Downloads\\stego_0000.png"
    python test_single.py /home/you/Downloads/stego_0000.png
"""
import sys
from feature_extraction import extract_features
from joblib import load

if len(sys.argv) < 2:
    print('Usage: python test_single.py "path\\to\\image.png"')
    sys.exit(1)

path = sys.argv[1]
model = load("stego_detector.pkl")

feat = extract_features(path).reshape(1, -1)
pred = model.predict(feat)[0]
proba = model.predict_proba(feat)[0]

label = "SUSPICIOUS (hidden data likely present)" if pred == 1 else "SAFE (no hidden data detected)"
print(f"\nFile: {path}")
print(f"Verdict: {label}")
print(f"Confidence -> safe: {proba[0]:.2%}, suspicious: {proba[1]:.2%}")
