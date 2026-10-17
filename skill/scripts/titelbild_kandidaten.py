#!/usr/bin/env python3
"""Candidate stills for the cover: samples the take every 0.25 s inside a window (default: the hook), ranks by face sharpness
(variance of the Laplacian in the upper middle of the frame) and writes a contact sheet of the 8 sharpest, each labelled with
its take time. Look at the sheet and pick a still with open eyes, closed or softly open mouth and a clear expression; then
python3 titelbild.py ORDNER ZEIT "Zeile 1" "Zeile 2".
Usage: python3 titelbild_kandidaten.py ORDNER [VON BIS]   writes ORDNER/titelbild-kandidaten.jpg"""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
d0 = Path(sys.argv[1]); take = d0 / 'take.mp4'
dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(take)], capture_output=True, text=True).stdout)
if len(sys.argv) > 3:
    von, bis = float(sys.argv[2]), float(sys.argv[3])
else:   # default: the hook piece (validation 17.10.2026: 0 to 8 s reached past the hook)
    import json
    st = d0 / 'take.stuecke.json'
    von, bis = 0.0, (min(dur, json.loads(st.read_text())[0]['bis'] - json.loads(st.read_text())[0]['von']) if st.exists() else min(dur, 8.0))
kand = []
for t in np.arange(von, bis, 0.25):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.2f}', '-i', str(take), '-frames:v', '1', '-vf', 'scale=270:480,format=gray',
                          '-f', 'rawvideo', '-'], capture_output=True).stdout
    if len(raw) != 270 * 480:
        continue
    a = np.frombuffer(raw, np.uint8).reshape(480, 270).astype(float)[80:300, 60:210]
    lap = a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]
    kand.append((float(lap.var()), round(float(t), 2)))
best = sorted(kand, reverse=True)[:8]
sheet = Image.new('RGB', (4 * 270, 2 * 500), (20, 20, 20)); dr = ImageDraw.Draw(sheet)
for i, (s, t) in enumerate(sorted(best, key=lambda x: x[1])):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', str(take), '-frames:v', '1', '-vf', 'scale=270:480', str(d0 / '_k.jpg')], check=True)
    sheet.paste(Image.open(d0 / '_k.jpg'), ((i % 4) * 270, (i // 4) * 500)); dr.text(((i % 4) * 270 + 8, (i // 4) * 500 + 482), f'{t:.2f} s', fill=(255, 255, 255))
(d0 / '_k.jpg').unlink(missing_ok=True)
sheet.save(d0 / 'titelbild-kandidaten.jpg', quality=88)
print('Kandidaten (Zeit, Schärfe):', [(t, round(s)) for s, t in sorted(best, key=lambda x: x[1])], '->', d0 / 'titelbild-kandidaten.jpg')
