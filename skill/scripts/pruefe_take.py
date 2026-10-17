#!/usr/bin/env python3
"""Entry check for a raw take before anything is cut. Stops on input that is not a raw talking-head take.
Usage: python3 pruefe_take.py TAKE      exit 0 = usable, 1 = stop (reason printed)

Checks: video stream readable, effective orientation after rotation metadata is portrait, HDR (needs avconvert),
frame rate, resolution (warn under 1080 px wide: upscaling loses sharpness), length, and burned-in text: a take
that already carries captions, an end card or a logo is a finished edit, not raw material (eval 07.10.2026)."""
import json, re, subprocess, sys, tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent / 'bin'
take = sys.argv[1]
d = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
     'stream=codec_type,width,height,r_frame_rate,color_transfer,pix_fmt:stream_side_data=rotation:format=duration',
     '-of', 'json', take], capture_output=True, text=True).stdout)
v = next((s for s in d.get('streams', []) if s['codec_type'] == 'video'), None)
if not v:
    print('STOP: no video stream'); sys.exit(1)
rot = 0
for sd in v.get('side_data_list', []) or []:
    if 'rotation' in sd: rot = int(sd['rotation'])
w, h = (v['height'], v['width']) if abs(rot) == 90 else (v['width'], v['height'])
num, den = map(int, v['r_frame_rate'].split('/')); fps = num / den
dur = float(d['format']['duration'])
hdr = v.get('color_transfer') in ('arib-std-b67', 'smpte2084') or '10' in v.get('pix_fmt', '')
res = {'width': w, 'height': h, 'rotation': rot, 'fps': round(fps, 3), 'duration': round(dur, 2), 'hdr': hdr, 'warnings': [], 'stop': []}
if h <= w: res['stop'].append(f'landscape after rotation ({w}x{h}); the style needs a portrait take')
if hdr: res['warnings'].append('HDR: convert with avconvert --preset Preset1920x1080 before anything else')
if w < 1080: res['warnings'].append(f'{w}x{h}: will be upscaled to 1080x1920, expect softer picture')
if abs(fps - 30) > 0.05: res['warnings'].append(f'{fps:.3f} fps: conform with -vf fps=30')
if dur < 15: res['stop'].append(f'only {dur:.1f} s')
# burned-in text: OCR 8 frames spread over the take
with tempfile.TemporaryDirectory() as td:
    for k in range(8):
        t = dur * (k + 0.5) / 8
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', take, '-frames:v', '1', '-vf', 'scale=-2:960', f'{td}/s{k}.jpg'])
    out = subprocess.run([str(BIN / 'ocr')] + [f'{td}/s{k}.jpg' for k in range(8)], capture_output=True, text=True).stdout
hits = {}
for line in out.splitlines():
    p = line.split('\t')
    if len(p) >= 4 and float(p[3]) >= 0.5 and len(re.sub(r'\W', '', p[1])) >= 3:
        hits.setdefault(p[0], []).append(p[1])
res['frames_with_text'] = {Path(k).name: v_[:4] for k, v_ in hits.items()}
if len(hits) >= 3:
    res['stop'].append(f'text burned in on {len(hits)} of 8 sample frames: this is an edited reel, not a raw take')
elif hits:
    res['warnings'].append(f'text on {len(hits)} sample frame(s) (signs, shirt print?): look before cutting')
print(json.dumps(res, ensure_ascii=False, indent=1))
sys.exit(1 if res['stop'] else 0)
