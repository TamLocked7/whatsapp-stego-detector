"""
app.py -- Local inference server for the WhatsApp Steganography Detector.

The Chrome extension (content script running on web.whatsapp.com) POSTs each
image it sees to  http://localhost:5000/predict  and this server returns a
verdict. Runs entirely on localhost -- no image ever leaves the user's
machine, which matters both for WhatsApp's privacy and for classroom
demoing ("where does the image data go?" is a guaranteed prof question).

Run:
    python app.py
Then load the /extension folder as an unpacked Chrome extension and open
web.whatsapp.com.
"""

import base64
import io
import os
import sys
import time

from flask import Flask, request, jsonify
from flask_cors import CORS
from joblib import load
from PIL import Image
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "model"))
from feature_extraction import extract_features, FEATURE_NAMES  # noqa: E402

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model", "stego_detector.pkl")

app = Flask(__name__)
CORS(app)  # allow requests from the extension's content-script origin

_model = None


def get_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError(
                f"No trained model at {MODEL_PATH}. Run model/train_model.py first."
            )
        _model = load(MODEL_PATH)
    return _model


def decode_image(data_url_or_b64):
    """Accepts either a data: URL (data:image/png;base64,...) or raw base64."""
    if "," in data_url_or_b64 and data_url_or_b64.strip().startswith("data:"):
        data_url_or_b64 = data_url_or_b64.split(",", 1)[1]
    raw = base64.b64decode(data_url_or_b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(img)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_loaded": _model is not None})


@app.route("/predict", methods=["POST"])
def predict():
    t0 = time.time()
    payload = request.get_json(force=True, silent=True) or {}
    image_b64 = payload.get("image")
    if not image_b64:
        return jsonify({"error": "missing 'image' field (base64 or data URL)"}), 400

    try:
        arr = decode_image(image_b64)
    except Exception as e:
        return jsonify({"error": f"could not decode image: {e}"}), 400

    # WhatsApp recompresses images (JPEG) heavily on send -- this is noted
    # explicitly in the analysis doc as a known limitation, since JPEG
    # re-encoding destroys most naive LSB payloads anyway. We still run
    # detection because (a) "View Once" / document-mode images and many
    # stickers pass through less lossy paths, and (b) it's the right thing
    # to demo the detector's behaviour on whatever image the user has.
    try:
        model = get_model()
        features = extract_features(arr).reshape(1, -1)
        proba = model.predict_proba(features)[0]
        pred = int(np.argmax(proba))
        confidence = float(proba[pred])
        label = "suspicious" if pred == 1 else "safe"

        top_features = sorted(
            zip(FEATURE_NAMES, features[0].tolist()), key=lambda t: -abs(t[1])
        )[:5]

        return jsonify({
            "label": label,
            "is_suspicious": bool(pred == 1),
            "confidence": round(confidence, 4),
            "probabilities": {"safe": round(float(proba[0]), 4), "suspicious": round(float(proba[1]), 4)},
            "top_signals": [{"feature": n, "value": round(v, 4)} for n, v in top_features],
            "inference_ms": round((time.time() - t0) * 1000, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    get_model()  # fail fast if model missing
    app.run(host="127.0.0.1", port=5000, debug=False)
