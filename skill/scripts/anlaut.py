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
def anlaut(w, prev_s, B, prev_w=''):
    """Onset of a word that starts with a continuant, in connected speech where the CTC start sits on the vowel.
    Fricatives (f, v, w, s, z, sch): the high band (>= 4 kHz) around the aligned start; walk back from its peak near the
    start while it stays within 10 dB, stop where it falls (the vowel of the word before). Nasals (m, n): the mid band
    (1.5 to 4 kHz) drops by >= 8 dB within 10 ms while the overall level stays (no pause): the lips close."""
    ges, hoch, mitte, tief = B
    t = re.sub(r'[^a-zäöüß]', '', w['w'].lower())
    if not t: return None
    k_s = int(w['s'] / 0.005)
    k_lo = max(int((prev_s + 0.08) / 0.005), k_s - 50)          # never into the first 80 ms of the word before
    # Runde 6: endet das Wort davor selbst auf einem Reibelaut ("-sche" vor einem Wort mit V), läuft die Suche in diesen zurück
    # (230 ms zu früh); eine Reibelautkette hat keine trennbare Grenze (so auch die Abnahme): dann nichts verschieben
    if t.startswith(('sch', 'f', 'v', 's', 'z')) and re.search(r'(sch|ch|s|ß|z|x|f)$', re.sub(r'[^a-zäöüß]', '', prev_w.lower())):
        return None
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


# Runde 6 (17.10.2026): Wortanfänge in verbundener Rede, die Runde 5 noch 140 bis 230 ms zu spät zeigte (Vokal nach "-e",
# [v] nach "wir", Nasal nach "-cht", [h] nach einem Nasal). Gemessen gegen die Wortanfänge der
# unabhängigen Abnahme (regression/anlaut-fixture.json im Arbeitsordner, Rohclip-Zeit): 11 Verstöße vorher, 2 danach, keiner zu früh.
def _fluss(x, sr=16000, nb=24):
    """spectral change per 5 ms: mean absolute difference of 24 log bands (80 Hz to 7.6 kHz) 20 ms apart, in dB"""
    hop, win = sr // 200, sr // 50
    n = 1 + (len(x) - win) // hop
    fr = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n] * np.hanning(win)
    S = np.abs(np.fft.rfft(fr, axis=1)) ** 2; f = np.fft.rfftfreq(win, 1 / sr)
    kanten = np.geomspace(80, 7600, nb + 1)
    L = np.stack([10 * np.log10(S[:, (f >= a) & (f < b)].sum(1) + 1e-10) for a, b in zip(kanten[:-1], kanten[1:])], 1)
    L = np.maximum(L, L.max() - 70)
    F = np.zeros(n); F[2:-2] = np.abs(L[4:] - L[:-4]).mean(1)
    return F


def verbunden(W, x, sr=16000, stueck_anfang=lambda w: 0.0, schwelle=5.0, maxv=0.25, gemessen=lambda w: False):
    """Moves word starts in connected speech earlier (only earlier, at most 250 ms, never into the first 80 ms of the word
    before, never before the start of the word's own piece). Per word, in this order:
    1 the gap after the previous word (aligned end to aligned start) has a dip below the pause threshold (p10 + 12 dB):
      if the gap starts voiced and the word starts with a vowel, that voiced part is its first vowel (the dip is the closure
      of its next consonant): start = previous end. Otherwise start = end of the dip, or its beginning for a word with [h].
      A dip that ends more than 250 ms before the aligned start is a real pause (einsatz.py measures that onset).
    2 a voiced gap of more than 30 ms: start = previous end.
    3 else the nearest strong spectral change (>= 5 dB) 50 to 250 ms before the aligned start.
    Returns the list of moves for the log."""
    x = np.asarray(x, np.float32)
    F = _fluss(x, sr)
    n = len(x) // (sr // 200); P = 20 * np.log10(np.sqrt((x[:n * (sr // 200)].reshape(n, sr // 200) ** 2).mean(1)) + 1e-9)
    pz = float(np.percentile(P[P > -80], 10)) + 12
    _ges, _hoch, _mitte, _tief = _baender(x, sr)
    def stimmhaft(k):                                  # 20 ms ab k: Grundton und erste Formanten (< 600 Hz) über dem Hochband
        return float(np.mean(_tief[k:k + 4]) - np.mean(_hoch[k:k + 4])) >= 6.0
    neu = []
    for i in range(1, len(W)):
        w, pv = W[i], W[i - 1]
        if gemessen(w):        # schon am Einsatz gemessen (Hüllkurve gemessen; die Regel zog so ein Wort ins "-sche" davor)
            continue
        k_s = int(w['s'] / 0.005)
        k_lo = max(int((pv['s'] + 0.08) / 0.005), k_s - int(maxv / 0.005))
        if k_lo >= k_s - 10 or k_s >= len(F) - 2:
            continue
        gap = w['s'] - pv['e']
        k0 = int(pv['e'] / 0.005)
        luecke = P[k0:k_s] if gap > 0.005 else np.array([0.0])
        kand = []
        if len(luecke) and luecke.min() <= pz:
            tief = [k0 + j for j, v in enumerate(luecke) if v <= pz]
            if w['s'] - tief[-1] * 0.005 > maxv:
                continue
            # nur ein Wort mit Vokal am Anfang beginnt im stimmhaften Anfang der Lücke (Vokal nach "-e"); bei "-st, n..." war
            # dieser Anfang das "-st" des Vorworts (235 ms zu früh)
            if all(v > pz for v in luecke[:4]) and re.match(r'[aeiouäöüAEIOUÄÖÜ]', w['w']) and stimmhaft(k0):
                kand.append(k0)
            else:
                kand.append(tief[0] if re.match(r'[hH]', w['w']) else tief[-1] + 1)
            k_lo = min(k_lo, kand[-1])
        elif gap > 0.03 and stimmhaft(k0):              # stimmlos ("-sche" vor dem Wort) ist das Ende des Vorworts
            kand.append(k0)
        else:
            for k in range(k_s - 10, k_lo, -1):
                if F[k] >= schwelle and F[k] >= F[k - 1] and F[k] >= F[k + 1]:
                    kand.append(k); break
        kand = [k for k in kand if k >= k_lo]
        if not kand:
            continue
        s_neu = round(min(kand) * 0.005 - 0.01, 3)
        if 0.04 < w['s'] - s_neu <= maxv and s_neu >= stueck_anfang(w):
            neu.append(f"{w['w']} {w['s']:.2f}->{s_neu:.2f}")
            w['s'] = s_neu
            if pv['e'] > s_neu:
                pv['e'] = s_neu
    return neu
