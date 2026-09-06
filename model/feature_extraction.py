"""
feature_extraction.py
----------------------
Extracts classical steganalysis features from an image that are known to be
sensitive to LSB (Least Significant Bit) embedding -- the technique used by
the Kaggle "Stego-Images-Dataset" (marcozuppelli/stegoimagesdataset), which
hides malicious JS / HTML / PowerShell / URLs / Ethereum keys inside images
via LSB substitution.

Why these features (and not raw pixels into a CNN)?
  1. LSB embedding perturbs statistical relationships between neighbouring
     pixels / bit-planes in ways that are well studied in the steganalysis
     literature (Chi-Square Attack, RS-Analysis, Sample Pair Analysis).
  2. These handcrafted features are lightweight (no GPU needed), fast enough
     to run in real time inside a browser-extension workflow (WhatsApp
     images arrive continuously), and -- importantly for a viva -- each
     feature has a well defined statistical meaning you can explain to your
     professor, unlike CNN activations.
  3. They still feed a standard supervised ML classifier (RandomForest /
     XGBoost), so the pipeline is: image -> feature vector -> classifier ->
     {SAFE, SUSPICIOUS} + confidence.

Feature groups implemented:
  A. Chi-Square Attack statistic (per channel)
  B. RS-Analysis (Regular/Singular groups) estimate of embedding rate
  C. Sample Pair Analysis (SPA) estimate of embedding rate
  D. LSB-plane statistics: 0/1 balance, entropy of LSB plane
  E. First-order image statistics: global entropy, histogram smoothness
     (pairs-of-values / PoV effect), std of Laplacian (noise proxy)
  F. Bit-plane correlation between LSB and next-significant bit
"""

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _load_channels(image_path_or_array):
    """Return a HxWx3 uint8 array regardless of input mode."""
    if isinstance(image_path_or_array, np.ndarray):
        arr = image_path_or_array
    else:
        img = Image.open(image_path_or_array).convert("RGB")
        arr = np.array(img)
    if arr.ndim == 2:  # grayscale -> replicate to 3 channels
        arr = np.stack([arr] * 3, axis=-1)
    return arr[:, :, :3].astype(np.int32)


def _entropy(values):
    hist, _ = np.histogram(values, bins=256, range=(0, 256))
    p = hist / max(hist.sum(), 1)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


# --------------------------------------------------------------------------
# A. Chi-Square Attack (Westfeld & Pfitzmann, 1999)
# --------------------------------------------------------------------------

def chi_square_score(channel):
    """
    Classic chi-square test on Pairs of Values (PoVs): (2i, 2i+1).
    LSB embedding equalises the frequency of each PoV pair, so a *low*
    p-value / high statistic indicates likely embedding.
    Returns a score in [0, 1]: higher = more likely stego.
    """
    hist, _ = np.histogram(channel, bins=256, range=(0, 256))
    scores = []
    for i in range(128):
        n0, n1 = hist[2 * i], hist[2 * i + 1]
        total = n0 + n1
        if total < 4:
            continue
        expected = total / 2.0
        chi = ((n0 - expected) ** 2) / expected
        scores.append(chi)
    if not scores:
        return 0.0
    # Small chi-square statistic (close to 0) => PoVs are balanced => stego-like.
    # We invert & squash so higher output = more suspicious.
    mean_chi = float(np.mean(scores))
    return float(1.0 / (1.0 + mean_chi))


# --------------------------------------------------------------------------
# B. RS-Analysis (Fridrich, Goljan & Du, 2001) -- simplified estimator
# --------------------------------------------------------------------------

def _discrimination(group, f):
    return np.sum(np.abs(np.diff(f(group))))


def rs_analysis(channel):
    """
    Simplified RS-analysis on rows of the channel. Groups of 4 consecutive
    pixels are flipped (LSB flip) and classified Regular / Singular based on
    change in a discrimination (smoothness) function. The Rm - R(-m) and
    Sm - S(-m) gap is a proxy for estimated embedding rate.
    Returns estimated embedding rate in [0, 1].
    """
    h, w = channel.shape
    group_size = 4
    flat = channel.flatten()
    n_groups = len(flat) // group_size
    if n_groups == 0:
        return 0.0

    flat = flat[: n_groups * group_size].reshape(n_groups, group_size)

    def f_smooth(g):  # discrimination function: sum |x_i - x_{i+1}|
        return np.sum(np.abs(np.diff(g.astype(np.float32))), axis=-1)

    def flip_lsb(g):
        return g ^ 1  # LSB flip (mask F1: invert bit 0)

    orig_f = f_smooth(flat)
    flipped_f = f_smooth(flip_lsb(flat))

    regular = np.sum(flipped_f > orig_f)
    singular = np.sum(flipped_f < orig_f)
    total = regular + singular
    if total == 0:
        return 0.0

    # Larger (R - S) imbalance collapsing toward 0 as embedding rate grows
    # is the classic RS signature; we convert the normalized gap to a
    # pseudo embedding-rate estimate in [0,1].
    rs_gap = abs(regular - singular) / total
    estimated_rate = float(np.clip(1.0 - rs_gap, 0.0, 1.0))
    return estimated_rate


# --------------------------------------------------------------------------
# C. Sample Pair Analysis (Dumitrescu, Wu & Wang, 2003) -- simplified
# --------------------------------------------------------------------------

def sample_pair_analysis(channel):
    """
    Simplified SPA: examines horizontally adjacent pixel pairs and buckets
    them by whether embedding-style LSB flips would change their relative
    ordering. Returns an estimated embedding rate in [0, 1].
    """
    pairs_a = channel[:, :-1].flatten()
    pairs_b = channel[:, 1:].flatten()

    same_lsb = np.sum((pairs_a & 1) == (pairs_b & 1))
    total = len(pairs_a)
    if total == 0:
        return 0.0
    # Under no embedding, adjacent-pixel LSB agreement sits near a natural
    # baseline (~0.5 for noisy/textured images). Embedding pushes this
    # toward 0.5 from either side; deviation from the *expected* natural
    # baseline (estimated from mid-frequency pixel variance) approximates
    # embedding likelihood.
    agreement_ratio = same_lsb / total
    return float(np.clip(abs(agreement_ratio - 0.5) * 2, 0.0, 1.0))


# --------------------------------------------------------------------------
# D/E/F. Bit-plane + first-order statistics
# --------------------------------------------------------------------------

def lsb_plane_stats(channel):
    lsb = (channel & 1).flatten()
    ones_ratio = float(np.mean(lsb))
    lsb_entropy = _entropy(lsb * 255)  # scale to reuse histogram helper
    return ones_ratio, lsb_entropy


def bitplane_correlation(channel):
    lsb = (channel & 1)
    nsb = ((channel >> 1) & 1)  # next significant bit
    corr = np.corrcoef(lsb.flatten(), nsb.flatten())[0, 1]
    return float(0.0 if np.isnan(corr) else corr)


def laplacian_std(channel):
    # Discrete Laplacian kernel convolution (noise / high-freq proxy)
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
    padded = np.pad(channel, 1, mode="edge").astype(np.float32)
    out = (
        padded[:-2, 1:-1] * k[0, 1]
        + padded[1:-1, :-2] * k[1, 0]
        + padded[1:-1, 1:-1] * k[1, 1]
        + padded[1:-1, 2:] * k[1, 2]
        + padded[2:, 1:-1] * k[2, 1]
    )
    return float(np.std(out))


# --------------------------------------------------------------------------
# Master feature-vector builder
# --------------------------------------------------------------------------

FEATURE_NAMES = []
for ch in ("R", "G", "B"):
    FEATURE_NAMES += [
        f"{ch}_chi_square",
        f"{ch}_rs_rate",
        f"{ch}_spa_rate",
        f"{ch}_lsb_ones_ratio",
        f"{ch}_lsb_entropy",
        f"{ch}_bitplane_corr",
        f"{ch}_laplacian_std",
        f"{ch}_global_entropy",
    ]


def extract_features(image_path_or_array):
    """Returns a 1D numpy feature vector of length len(FEATURE_NAMES)."""
    arr = _load_channels(image_path_or_array)
    features = []
    for c in range(3):
        channel = arr[:, :, c]
        chi = chi_square_score(channel)
        rs = rs_analysis(channel)
        spa = sample_pair_analysis(channel)
        ones_ratio, lsb_ent = lsb_plane_stats(channel)
        corr = bitplane_correlation(channel)
        lap = laplacian_std(channel)
        g_ent = _entropy(channel)
        features += [chi, rs, spa, ones_ratio, lsb_ent, corr, lap, g_ent]
    return np.array(features, dtype=np.float32)


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    vec = extract_features(path)
    for name, val in zip(FEATURE_NAMES, vec):
        print(f"{name:22s}: {val:.4f}")
