#!/usr/bin/env python3
"""Audible word onset from the level envelope, the method of the independent inspector of 17.10.2026 (it found captions
167 to 207 ms late that every own check passed, because those checks used the same CTC model that placed the words).

1 ms RMS envelope (5 ms window). For a word that the aligner starts at s: in the window s - 250 ms .. s + 30 ms (not into
the previous word) find the deepest point. If it lies at least 15 dB below the word's peak, the word follows a dip and its
onset is the first point after the dip where the level reaches max(dip + 15 dB, peak - 30 dB). Otherwise (connected speech)
no onset is measured and the aligner's start stands.

Used by ausrichten.py (moves a start only EARLIER, never later: pitfall 12) and by schnitte_vorab.py (caption against
the audible onset in the assembled reel audio, before the render).

Round 2 validation 17.10.2026 (male voice, room noise around -40 dB): the plain method reported 5 late or early captions
that were all wrong (measured by level curve and spectrum). schnitte_vorab.py therefore passes 4 extra rules; with the
defaults the function behaves exactly as before (ausrichten.py):
  grenze     the last cut before the word: never search across it (the sound on the other side belongs to another range)
  laut       speech level of the recording (take p10 + 12 dB): the onset must reach it, room noise never does
  starts     aligned starts of the previous words: if one begins after the dip (or less than 50 ms before it), the sound
             after the dip is that word's (a short deep word before the next one), not measurable
  halten_ms  the onset must hold (level >= threshold - 6 dB for this long): a noise burst does not
Checked against the late captions the independent inspection found (still found) and the 5 wrong ones (gone)."""
import numpy as np


def huelle_1ms(x, sr):
    """x: mono float samples. Returns dB per ms (window 5 ms centred on each ms)."""
    hop, win = sr // 1000, 5 * sr // 1000
    pad = np.concatenate([np.zeros(win // 2), x.astype(np.float64), np.zeros(win // 2)])
    n = 1 + (len(pad) - win) // hop
    c = np.concatenate([[0.0], np.cumsum(pad * pad)])
    st = np.arange(n) * hop
    return 10 * np.log10((c[st + win] - c[st]) / win + 1e-12)


def einsatz(rms, s, e, prev_e=0.0, grenze=None, laut=None, starts=(), halten_ms=0):
    """Onset in s of a word aligned at [s, e] (seconds), or None in connected speech."""
    a = max(0, int((s - 0.25) * 1000), int(prev_e * 1000) - 20)
    if grenze is not None:
        a = max(a, int(grenze * 1000) + 5)
    b = int((s + 0.03) * 1000)
    seg = rms[a:b]
    w = rms[int(s * 1000):int(e * 1000) + 1]
    if len(seg) <= 5 or len(w) == 0:
        return None
    peak = float(w.max())
    j = int(np.argmin(seg)); lmin = float(seg[j])
    if lmin > peak - 15:
        return None
    tdip = (a + j) / 1000
    if any(tdip - 0.05 <= x < s - 0.01 for x in starts):
        return None
    thr = max(lmin + 15, peak - 30) if laut is None else max(lmin + 15, peak - 30, laut)
    after = rms[a + j:int(e * 1000) + 1]
    if halten_ms:
        for k in range(len(after) - halten_ms):
            if after[k] >= thr and (after[k:k + halten_ms] >= thr - 6).all():
                return (a + j + k) / 1000
        return None
    idx = np.where(after >= thr)[0]
    return (a + j + int(idx[0])) / 1000 if len(idx) else None


def hochband(x, sr=16000):
    """10 ms steps, 20 ms window: level of 1 to 7.9 kHz in dB. Hum and its overtones below 1 kHz do not count as speech,
    vowels' upper formants and fricatives do. Used by pause_im_wort (round 4, 17.10.2026)."""
    x = np.asarray(x, np.float32); hop, win = sr // 100, sr // 50
    n = max(0, (len(x) - win) // hop)
    out = np.full(n, -120.0, np.float32)
    if not n:
        return out
    f = np.fft.rfftfreq(win, 1 / sr); bd = (f >= 1000) & (f <= 7900); fen = np.hanning(win)
    for j0 in range(0, n, 4096):
        j1 = min(n, j0 + 4096)
        fr = x[np.arange(win)[None, :] + hop * np.arange(j0, j1)[:, None]] * fen
        out[j0:j1] = 10 * np.log10((np.abs(np.fft.rfft(fr, axis=1)) ** 2)[:, bd].sum(1) + 1e-12)
    return out


def pause_im_wort(hb, s, e, laut, luecke=0.25, rest=0.30):
    """A pause inside an aligned word span (CTC stretched the word over it): after the word's first frame at laut + 6 dB,
    the first stretch of at least `luecke` s where every frame stays below laut + 6 dB (sporadic room noise up to there is
    allowed), if the aligned end lies at least `rest` s after its start. laut = take p10 of hb + 12 dB. Returns the
    stretch's start in seconds or None. Round 4: a word aligned over 1.3 s in a validation case, spoken for 0.6 s, then
    0.6 s of low hum; a soft word end ("-keit" 18 dB under the word's peak) stays above laut + 6 in this band and is never
    taken for a pause."""
    k0, k1 = int(s * 100), min(len(hb), int(e * 100) + 1)
    schw = laut + 6; k = k0
    while k < k1 and hb[k] < schw:
        k += 1
    while k < k1:
        if hb[k] >= schw:
            k += 1; continue
        j = k
        while j < k1 and hb[j] < schw:
            j += 1
        if (j - k) / 100 >= luecke and e - k / 100 >= rest:
            return k / 100
        if j >= k1:
            return None
        k = j
    return None
