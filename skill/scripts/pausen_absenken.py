#!/usr/bin/env python3
"""Lower the room tone in word gaps of the take by 14 dB, before the render (part of the hiss fix of 15.10.2026).

Why: the voice-preserving noise reduction (entrauschen.py) leaves more noise than the old fixed setting, and the master's
compression lifts it; in the reference reels the noise in word gaps was 8 to 10 dB louder than before (measured 15.10.2026 19:10).
Speech mask per word from the aligned woerter.json: 50 ms before the start to 100 ms after the end (aligned ends tend to be early).
Gaps of 120 ms or more between masks are lowered by 14 dB with 35 ms cosine ramps inside the gap, never muted (room tone stays).
Writes take-ton.mp4: the take's video stream copied, the gated audio as AAC 320k. baue_reel.py renders this file (plan
"render_quelle") but keeps measuring silences, faces and contrast on take.mp4, so the edit is the same as without gating.
Usage: python3 pausen_absenken.py ORDNER   (needs take.mp4 and woerter.json)"""
import json, subprocess, sys
from pathlib import Path
import numpy as np

D = Path(sys.argv[1]); SR = 48000
PAUSE_DB, RAMPE = -14.0, 0.035
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(D / 'take.mp4'), '-vn', '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'],
                     capture_output=True, check=True).stdout
take = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
WT = json.loads((D / 'woerter.json').read_text())
masken = sorted((max(0.0, w['s'] - 0.05), w['e'] + 0.10) for w in WT)
zus = []
for a0, a1 in masken:
    if zus and a0 <= zus[-1][1]:
        zus[-1][1] = max(zus[-1][1], a1)
    else:
        zus.append([a0, a1])
gain = np.ones(len(take), np.float32); tief = 10 ** (PAUSE_DB / 20); luecken = []
ende = len(take) / SR
grenzen = [[0.0, 0.0]] + zus + [[ende, ende]]
def senken(l0, l1):
    i0, i1, r = int(l0 * SR), min(len(take), int(l1 * SR)), int(RAMPE * SR)
    if i1 - i0 < 2 * r:
        return False
    seg = np.full(i1 - i0, tief, np.float32)
    k = np.linspace(0, np.pi, r)
    if l0 > 0:
        seg[:r] = tief + (1 - tief) * (np.cos(k) + 1) / 2
    if l1 < ende:
        seg[-r:] = tief + (1 - tief) * (1 - np.cos(k)) / 2
    gain[i0:i1] = np.minimum(gain[i0:i1], seg)
    return True


for (_, l0), (l1, _) in zip(grenzen, grenzen[1:]):
    if l1 - l0 >= 0.12 and senken(l0, l1):
        luecken.append(round(l1 - l0, 2))
take *= gain[:, None]
wav = D / 'take-ton.wav'
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', str(wav)], input=take.tobytes(), check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(D / 'take.mp4'), '-i', str(wav), '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '320k', '-ar', str(SR), '-shortest', '-movflags', '+faststart', str(D / 'take-ton.mp4')], check=True)
wav.unlink()
print(f'Pausen abgesenkt: {len(luecken)} Lücken um {PAUSE_DB:.0f} dB, zusammen {sum(luecken):.1f} s -> {D / "take-ton.mp4"}')
