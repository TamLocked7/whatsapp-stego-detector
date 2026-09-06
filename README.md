# WhatsApp Steganography Detector

Detects LSB (Least-Significant-Bit) steganography in images on WhatsApp Web
and flags them **SAFE** or **SUSPICIOUS** via a Chrome extension backed by a
locally-running ML model.

Dataset target: [Stego-Images-Dataset (Kaggle)](https://www.kaggle.com/datasets/marcozuppelli/stegoimagesdataset)
— 44,000 images with malicious JS / HTML / PowerShell / URL / Ethereum-key
payloads embedded via LSB substitution.

```
whatsapp-stego-detector/
├── model/
│   ├── feature_extraction.py   # steganalysis feature engineering (Chi-Sq, RS, SPA, ...)
│   ├── make_demo_dataset.py    # generates a small synthetic clean/stego set for testing
│   ├── train_model.py          # trains + evaluates the RandomForest classifier
│   └── stego_detector.pkl      # trained model (produced by train_model.py)
├── backend/
│   └── app.py                  # Flask API the extension calls (localhost:5000)
├── extension/                  # Chrome extension (Manifest V3)
│   ├── manifest.json
│   ├── content.js              # scans images in the WhatsApp Web DOM
│   ├── popup.html / popup.js
│   └── style.css
├── demo_data/                  # synthetic clean/ and stego/ demo images
└── docs/                       # analysis report for your professor
```

## 1. Train on the REAL dataset (do this before the demo)

```bash
# 1. Download & unzip the Kaggle dataset (needs a free Kaggle account + API key)
pip install kaggle
kaggle datasets download -d marcozuppelli/stegoimagesdataset
unzip stegoimagesdataset.zip -d data/

# 2. Arrange into clean/ and stego/ folders matching the dataset's own
#    structure (check the unzipped folder names -- typically something like
#    data/clean/*.png and data/{js,html,ps,url,eth}/*.png). Merge all the
#    payload-type folders into one "stego" folder for a binary classifier,
#    e.g.:
mkdir -p data/all_stego
cp data/js/* data/html/* data/ps/* data/url/* data/eth/* data/all_stego/ 2>/dev/null

# 3. Train (uncap for the full 44k images, or set --max_per_class for a
#    quicker run while iterating)
cd model
python train_model.py --clean_dir ../data/clean --stego_dir ../data/all_stego --max_per_class 5000
```

This overwrites `model/stego_detector.pkl` and `model/metrics.json` with
real numbers you can show your professor.

## 2. Quick demo (no download needed)

Already run in this project — `demo_data/` has 120 synthetic clean + 120
synthetic stego images and `model/stego_detector.pkl` is trained on them
(96% accuracy, ROC-AUC 0.99, see `model/metrics.json`). To regenerate:

```bash
cd model
python make_demo_dataset.py
python train_model.py
```

## 3. Run the backend

```bash
cd backend
pip install flask flask-cors pillow numpy scikit-learn joblib
python app.py
# -> Running on http://127.0.0.1:5000
```

## 4a. (Recommended for demo) Standalone chat UI — no WhatsApp compression

`demo_chatbox/index.html` is a small self-contained WhatsApp-style chat mockup
that sends images to the same local backend, but — unlike real WhatsApp — it
never recompresses anything, so you see the detector's true behavior without
fighting WhatsApp's JPEG pipeline. Great for a controlled, reliable
professor demo.

With the backend running (step 3), just double-click `demo_chatbox/index.html`
to open it in your browser (or right-click → Open with → Chrome). Drag an
image from `demo_data/stego/` or `demo_data/clean/` onto the chat window, or
use the 📎 attach button — a badge appears within ~1 second.

## 4b. Load the real Chrome extension (WhatsApp Web integration)

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select the `extension/` folder
4. Open `web.whatsapp.com`, scan the QR code, open any chat with images
5. Each image gets a green **✓ Safe** or red **⚠ Suspicious** badge in its
   top-right corner within ~50ms of the model's prediction

## Notes / known limitations (read before the viva)

- **JPEG re-compression**: WhatsApp re-encodes most sent photos as JPEG,
  which destroys naive spatial-domain LSB payloads. The detector still
  works fully on: images sent as "Document" (uncompressed), PNG stickers,
  and any image the model is pointed at directly (e.g. via the training
  script) — see `docs/analysis.md` for the full discussion and how a real
  deployment would extend to JPEG-domain (DCT-coefficient) steganalysis.
- All inference happens on `localhost` — no image data leaves the machine.
- The classifier is intentionally an interpretable RandomForest over
  classical steganalysis statistics, not a black-box CNN — see
  `docs/analysis.md` for the justification, expected exam questions, and
  answers.
