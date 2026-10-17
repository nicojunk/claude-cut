#!/usr/bin/env python3
"""True peak of a delivered file over its whole length, and a one-sided click at the file start (round 5, 17.10.2026).

Why: the independent inspection measured +0.39 dBTP at 0.010 to 0.015 s, left channel only, in a reel whose master had
-2.50 dBTP. ffmpeg's own AAC encoder put the spike into the first audio block; the delivery encoded the decoded master a
second time and doubled it. mastern.py measured the PCM before encoding, so no own check saw the delivered file.
Checks per file:
  1 true peak (ffmpeg ebur128, 4x oversampling) of the decoded file <= -1.5 dBTP
  2 first 60 ms in 5 ms windows: left and right sample peaks differ by more than 6 dB while the louder one is above
    -20 dBFS (a one-sided click; speech is the same on both channels)
Usage: python3 pruefe_ton_spitze.py DATEI [DATEI ...]   exit 1 on a finding"""
import re, subprocess, sys
import numpy as np

befund = 0
for f in sys.argv[1:]:
    m = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', f, '-map', '0:a', '-filter_complex', '[0:a]ebur128=peak=true[o]',
                        '-map', '[o]', '-f', 'null', '-'], capture_output=True, text=True).stderr
    s = m[m.rfind('Summary:'):]
    tp = float(re.search(r'Peak:\s+(-?[\d.]+|-inf) dBFS', s).group(1).replace('-inf', '-120'))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-t', '0.06', '-vn', '-ac', '2', '-ar', '48000', '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2)
    einseitig = []
    for ms in range(0, 60, 5):
        blk = x[ms * 48:(ms + 5) * 48]
        if not len(blk):
            break
        l, r = (20 * np.log10(np.abs(blk[:, c]).max() + 1e-9) for c in (0, 1))
        if max(l, r) > -20 and abs(l - r) > 6:
            einseitig.append(f'{ms}-{ms + 5} ms L {l:.1f} / R {r:.1f} dBFS')
    ok = tp <= -1.5 and not einseitig
    print(f'{f}: True Peak {tp:+.2f} dBTP' + (f', einseitiger Knack am Anfang: {"; ".join(einseitig)}' if einseitig else '')
          + ('' if ok else '  <-- BEFUND'))
    befund += not ok
sys.exit(1 if befund else 0)
