#!/usr/bin/env python3
"""Flacker-Prüfung auf der Lieferdatei (15.10.2026, Berater nach Abnahme R4 v7: Aufblitzen nach der Navy-Stille, Karte 1 Bild
fertig vor ihrer Einflug-Animation, Zoomsprung 1 Bild; keine eigene Prüfung hatte das gesehen).
Mittlere Helligkeit je Bild in 4 waagrechten Streifen (Video auf 108x192 verkleinert). Befund: ein Sprung von mehr als 12
Helligkeitsstufen, nach dem der Streifen binnen 1 bis 8 Bildern wieder auf höchstens 35 % des Sprungs an den Ausgangswert
zurückkehrt (hin und zurück), außerhalb der geplanten Blitze (edl 'flashes' ±4 Bilder).
Dazu Einzelbilder: ein Bild, das sich von beiden Nachbarn stark unterscheidet, während die Nachbarn einander gleichen.
Aufruf: python3 flimmern.py liefer.mp4 projekt/edl.json"""
import json, subprocess, sys
import numpy as np
v, e = sys.argv[1], sys.argv[2]
E = json.load(open(e))
W, H = 108, 192
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', v, '-vf', f'scale={W}:{H}:flags=area,format=gray', '-f', 'rawvideo', '-'],
                     capture_output=True, check=True).stdout
F = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W).astype(np.float32)
n = len(F)
blitz = set()
for t in E.get('flashes', []):
    f0 = int(round(t * 30)); blitz.update(range(f0 - 6, f0 + 10))
# card entering on a state change: in the change frame the card stands half (baue_reel _am_wechsel, against a 1-frame jump
# back and forth to the speaker); this one transition frame is intended (R3 v3 gate-ausnahmen 15.10.2026, measured)
for c in E.get('cards', []):
    if any(abs(c['appear'] - sg['a']) < 0.5 / 30 for sg in E.get('segments', [])[1:]):
        f0 = int(round(c['appear'] * 30)); blitz.update(range(f0 - 1, f0 + 2))
for t in E.get('dips', []):
    f0 = int(round(t * 30)); blitz.update(range(f0 - 10, f0 + 12))      # geplante Navy-Abblenden
# planned fade to the channel dark after the hook ("stille_danach" in take.stuecke.json, round 2 case 2 17.10.2026:
# 18 -> 2 -> 15 at 9.00 to 9.23 s was this fade followed by the flash): skip from its start to 12 frames after the piece end
import os as _os
_st_p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(sys.argv[2]))), 'take.stuecke.json')
if _os.path.exists(_st_p):
    def _t2o(x):
        o = 0.0
        for r0, r1 in E['ranges']:
            if x < r0: return o
            if x <= r1: return o + (x - r0)
            o += r1 - r0
        return o
    _off = 0.0
    for _s in json.load(open(_st_p)):
        _len = _s['bis'] - _s['von']; _sd = float(_s.get('stille_danach', 0) or 0)
        if _sd:
            blitz.update(range(int(_t2o(_off + _len - _sd - 0.05) * 30) - 2, int(round(_t2o(_off + _len) * 30)) + 13))
        _off += _len
for c in E.get('cards', []):
    if c.get('drehung') is not None:     # planned card turn (12 frames, back.out): edge-on the card is thin for a frame
        f0 = int(round(c['drehung'] * 30)); blitz.update(range(f0 - 1, f0 + 13))
B = np.stack([F[:, q * H // 4:(q + 1) * H // 4, :].mean(axis=(1, 2)) for q in range(4)], axis=1)   # n x 4
befunde = []
for q in range(4):
    L = B[:, q]
    i = 1
    while i < n - 1:
        d = L[i] - L[i - 1]
        if abs(d) > 12 and i not in blitz:
            for j in range(i + 1, min(n, i + 9)):
                if abs(L[j] - L[i - 1]) <= 0.35 * abs(d) and np.sign(L[j - 1] - L[i - 1]) == np.sign(d):
                    befunde.append((i, j, q, float(L[i - 1]), float(L[i]), float(L[j])))
                    i = j
                    break
        i += 1
# Einzelbilder (Bilddifferenz)
D = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2))           # D[k] = |F[k+1]-F[k]|
einzel = []
for k in range(1, n - 1):
    a_, b_ = D[k - 1], D[k]                                 # zu Bild k von k-1, von k zu k+1
    rund = np.abs(F[k + 1] - F[k - 1]).mean()
    if min(a_, b_) > 18 and rund < 0.4 * min(a_, b_) and k not in blitz:
        einzel.append((k, float(a_), float(b_), float(rund)))
streifen = ['oben', 'oben-mitte', 'unten-mitte', 'unten']
for i, j, q, l0, l1, l2 in befunde:
    print(f'  Sprung hin und zurück Bild {i} bis {j} ({i / 30:.3f} bis {j / 30:.3f} s), Streifen {streifen[q]}: {l0:.0f} -> {l1:.0f} -> {l2:.0f}')
for k, a_, b_, r in einzel:
    print(f'  Einzelbild {k} ({k / 30:.3f} s): Abstand zu den Nachbarn {a_:.0f} / {b_:.0f}, Nachbarn untereinander {r:.0f}')
print(f'{v}: {n} Bilder, {len(befunde)} Hin-und-zurück-Sprünge, {len(einzel)} Einzelbilder')
# Kontaktblatt je Meldung (Bild davor, Sprung, danach, Rückkehr), zum Ansehen
from PIL import Image
if (befunde or einzel) and len(sys.argv) > 3:
    ziele = sorted({(i, j) for i, j, *_ in befunde} | {(k, k + 1) for k, *_ in einzel})
    rows = []
    for i, j in ziele[:12]:
        fr = [max(0, i - 1), i, min(n - 1, i + 1), j]
        rows.append(np.concatenate([F[x] for x in fr], axis=1))
    Image.fromarray(np.concatenate(rows, axis=0).astype(np.uint8)).resize((4 * W * 2, len(rows) * H * 2)).save(sys.argv[3])
    print('Kontaktblatt:', sys.argv[3], 'Zeilen:', ', '.join(f'{i}-{j}' for i, j in ziele[:12]))
sys.exit(1 if (befunde or einzel) else 0)
