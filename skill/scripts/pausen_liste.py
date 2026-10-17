#!/usr/bin/env python3
"""Lange Pausen im zusammengesetzten Reel-Ton (vor dem Render): Läufe unter Grundrauschen + 18 dB ab 0,4 s.
Aufruf: python3 pausen_liste.py ORDNER"""
import json, subprocess, sys
import numpy as np
d = sys.argv[1]
E = json.load(open(d + '/projekt/edl.json'))
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', d + '/take.mp4', '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True, check=True).stdout
ta = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
a = np.concatenate([ta[int(round(r0 * 16000)):int(round(r1 * 16000))] for r0, r1 in E['ranges']])
n = len(a) // 160; db = 20 * np.log10(np.sqrt(np.mean(a[:n * 160].reshape(n, 160) ** 2, axis=1) + 1e-12))
thr = np.percentile(db[db > -80], 10) + 12
runs, s = [], None
for i, x in enumerate(np.append(db < thr + 6, False)):
    if x and s is None: s = i
    if not x and s is not None:
        if i - s >= 40: runs.append((s / 100, (i - s) / 100))
        s = None
print(d, f'{E["total"]:.2f} s, Pausen ab 0,4 s: {len(runs)}, Summe {sum(r[1] for r in runs):.2f} s, längste {max([r[1] for r in runs] or [0]):.2f} s',
      ' '.join(f'{t:.1f}:{l:.2f}' for t, l in runs))
