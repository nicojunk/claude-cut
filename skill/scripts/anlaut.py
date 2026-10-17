"""Onset of words that start with a voiceless fricative or a nasal, in connected speech where the CTC start sits on the
vowel (round 4, 17.10.2026: the independent inspection measured "Morgen" 138 and 148 ms late, "Ergebnis" 139 ms;
the new starts are within 10 ms of its spectral measurements). Used by ausrichten.py; moves a start only earlier.
Usage for a check: python3 anlaut.py VERSIONSORDNER"""
import numpy as np, subprocess, json, re, sys
def baender_aus(x, sr=16000):
    x = np.asarray(x, np.float32)
    return _baender(x, sr)


def baender(path, sr=16000):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', str(sr), '-f', 's16le', '-'], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    return _baender(x, sr)


def _baender(x, sr):
    hop, win = sr // 200, sr // 100                                   # 5 ms hop, 10 ms window
    n = 1 + (len(x) - win) // hop
    fr = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n] * np.hanning(win)
    S = np.abs(np.fft.rfft(fr, axis=1)) ** 2; f = np.fft.rfftfreq(win, 1 / sr)
    db = lambda m: 10 * np.log10(S[:, m].sum(1) + 1e-12)
    return db(f > 0), db((f >= 4000)), db((f >= 1500) & (f < 4000)), db(f < 600)
def anlaut(w, prev_s, B):
    """Onset of a word that starts with a continuant, in connected speech where the CTC start sits on the vowel.
    Fricatives (f, v, w, s, z, sch): the high band (>= 4 kHz) around the aligned start; walk back from its peak near the
    start while it stays within 10 dB, stop where it falls (the vowel of the word before). Nasals (m, n): the mid band
    (1.5 to 4 kHz) drops by >= 8 dB within 10 ms while the overall level stays (no pause): the lips close."""
    ges, hoch, mitte, tief = B
    t = re.sub(r'[^a-zäöüß]', '', w['w'].lower())
    if not t: return None
    k_s = int(w['s'] / 0.005)
    k_lo = max(int((prev_s + 0.08) / 0.005), k_s - 50)          # never into the first 80 ms of the word before
    if t.startswith(('sch', 'f', 'v', 's', 'z')):          # not 'w': a voiced /v/ has no high band
        a0, a1 = max(k_lo, k_s - 30), min(len(hoch) - 1, k_s + 10)   # peak within -150/+50 ms of the aligned start
        if a1 - a0 < 4: return None
        kp = a0 + int(np.argmax(hoch[a0:a1])); pk = hoch[kp]
        k = kp
        while k > k_lo and pk - 10 <= hoch[k - 1] <= pk + 3: k -= 1     # stop at a stronger fricative of the word before
        if pk - hoch[max(k_lo, k - 6):k + 1].min() < 10: return None      # needs a clear rise out of the vowel before
        return k * 0.005
    if t.startswith(('m', 'n')):
        a0, a1 = max(k_lo, k_s - 30), min(len(ges) - 1, k_s + 6)
        d = mitte[a0 + 2:a1] - mitte[a0:a1 - 2]; g = ges[a0 + 2:a1] - ges[a0:a1 - 2]
        kand = [a0 + 2 + i for i in range(len(d)) if d[i] <= -8 and g[i] > -6]
        return kand[-1] * 0.005 if kand else None          # the drop closest to the aligned start
    return None
if __name__ == '__main__':
    D = sys.argv[1]; W = json.load(open(D + '/woerter.json')); E = json.load(open(D + '/projekt/edl.json'))
    B = baender(D + '/take.mp4')
    for i, w in enumerate(W):
        a = anlaut(w, W[i - 1]['s'] if i else 0.0, B)
        if a is not None and w['s'] - a > 0.04:
            print(f"{w['w']:16s} Take {w['s']:.3f} -> Anlaut {a:.3f} ({(a - w['s']) * 1000:+.0f} ms), Reel {E['words'][i]['out']:.3f}")
