#!/usr/bin/env python3
"""Pausen im Ton eines Rohclips messen (10-ms-RMS, Schwelle = Grundrauschen + 12 dB).
Aufruf: python3 naehte.py CLIP [von bis]   listet alle Pausen >= 60 ms mit den Wörtern davor/danach."""
import json, subprocess, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal
SR, HOP = 16000, 160


def pegel(clip):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(kanal.roh(clip)), '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = len(a) // HOP
    rms = np.sqrt(np.mean(a[:n * HOP].reshape(n, HOP) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms)


def pausen(db, min_ms=60):
    rausch = np.percentile(db, 10)
    thr = rausch + 12
    still = db < thr
    out, i = [], 0
    while i < len(still):
        if still[i]:
            j = i
            while j < len(still) and still[j]: j += 1
            if (j - i) * 10 >= min_ms: out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out, rausch, thr


def letzter_laut(clip, t0, t1, P=None):
    """Last sound in [t0, t1] of the raw clip, sensitive to soft and voiceless word ends: a 10 ms block counts when its
    broadband level is 10 dB above the local floor or its first-difference level (weights the band above 2 kHz) is 10 dB
    above its local floor (the "sch" of a softly spoken word end at -45 to -50 dB in -55 dB room noise, round 3
    17.10.2026). Floors: 10th percentile of the 2 s around t1. A low hum 6 dB over the floor does not count. Returns
    seconds or None."""
    f = kanal.roh(clip, P or kanal.profil())
    a0 = max(0.0, min(t0 - 0.5, t1 - 1.0))          # the window always holds the word's start
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{a0:.3f}', '-t', f'{t1 + 1.0 - a0:.3f}', '-i', str(f), '-vn', '-ac', '1', '-ar', '16000',
                          '-f', 's16le', '-'], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if len(x) < 3200:
        return None
    hp = np.concatenate([[0.0], np.diff(x)])
    n = len(x) // 160
    lv = 20 * np.log10(np.sqrt(np.mean(x[:n * 160].reshape(n, 160) ** 2, axis=1)) + 1e-9)
    lh = 20 * np.log10(np.sqrt(np.mean(hp[:n * 160].reshape(n, 160) ** 2, axis=1)) + 1e-9)
    fb, fh = np.percentile(lv, 10), np.percentile(lh, 10)
    k0, k1 = max(0, int((t0 - a0) * 100)), min(n, int((t1 - a0) * 100))
    # only what belongs to the word: from its start on, gaps up to 120 ms (a stop closure, the "t" of "gut") stay inside it;
    # a breath after a longer silence (170 ms after "falsch", round 3) does not
    ende, luecke = None, 0
    for k in range(k0, k1):
        if lv[k] > fb + 10 or lh[k] > fh + 10:
            ende, luecke = k, 0
        elif ende is not None:
            luecke += 1
            if luecke > 12:
                break
    return a0 + (ende + 1) / 100 if ende is not None else None


if __name__ == '__main__':
    clip = sys.argv[1]
    a, b = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0, 1e9)
    db = pegel(clip); P, r, thr = pausen(db)
    W = json.load(open(kanal.transkripte() / f'{Path(clip).stem}.woerter.json'))
    print(f'Rauschen {r:.1f} dB, Schwelle {thr:.1f} dB')
    for g0, g1 in P:
        if g1 < a or g0 > b: continue
        vor = [w['w'] for w in W if w['e'] <= g0 + 0.15][-1:] ; nach = [w['w'] for w in W if w['s'] >= g1 - 0.15][:1]
        print(f'{g0:7.2f}-{g1:7.2f} ({(g1-g0)*1000:4.0f} ms)  nach "{vor[0] if vor else "-"}"  vor "{nach[0] if nach else "-"}"')
