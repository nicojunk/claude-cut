#!/usr/bin/env python3
"""Master the audio of a rendered reel: compressed speech at -14 LUFS, true peak <= -1.5 dBTP, AAC 48 kHz stereo 256 kb/s.
Usage: python3 mastern.py IN OUT.mp4   (video stream is copied)

15.10.2026 19:20 (Nico 18:15: "dieses Zischen"), gemessen an R3:
- S-Laute: Bandkompressor nur über 4,8 kHz (acrossover 8. Ordnung, Summe flach). Schwelle = 80. Perzentil des HF-Bandpegels in
  Sprachfenstern (20 ms) dieser Fassung, Verhältnis 8, Attack 0,5 ms, Release 40 ms. R3: Klarheit (HF zu Mitte, Median) 3,4 dB
  heller als vorher, S-Laute p95 2 dB und lauteste 1 % 7,5 dB unter der alten Fassung, Zischspitzen 0,8 dB darunter.
- Lautheit: feste Verstärkung auf -14 LUFS, danach Begrenzer mit 4-facher Überabtastung. loudnorm lief zuvor trotz linear=true
  dynamisch (Verstärkung hätte den True Peak über -1,5 gehoben) und hob leise Stellen an.
- asetpts=N/SR/TB am Ende, sonst 1 Paket mit 4226 Samples (66,7 ms Zeitsprung, Abnahme R2)."""
import re, subprocess, sys
import numpy as np
src, dst = sys.argv[1], sys.argv[2]
def pcm(af):
    return np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vn', '-af', af, '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'],
                                        capture_output=True, check=True).stdout, np.float32)
x, h = pcm('highpass=f=80'), pcm('highpass=f=4800:poles=2,highpass=f=4800:poles=2')
W = 960; n = min(len(x), len(h)) // W
lt = 20 * np.log10(np.sqrt((x[:n * W].reshape(n, W) ** 2).mean(1)) + 1e-9)
lh = 20 * np.log10(np.sqrt((h[:n * W].reshape(n, W) ** 2).mean(1)) + 1e-9)
T = float(np.percentile(lh[lt > np.percentile(lt, 50)], 80))
deess = (f'highpass=f=80,acrossover=split=4800:order=8th[l][h];[h]acompressor=threshold={10 ** (T / 20):.6f}:ratio=8:attack=0.5:release=40:knee=2[hc];'
         f'[l][hc]amix=inputs=2:normalize=0,acompressor=threshold=-24dB:ratio=3.5:attack=5:release=90:makeup=6dB')
lim = 'aresample=192000,alimiter=limit=0.7499:attack=1:release=60:level=disabled:asc=1,aresample=48000'   # -2,5 dBFS bei 4x
def lufs(chain):
    m = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', src, '-filter_complex', f'[0:a]{chain},ebur128=peak=true[o]', '-map', '[o]', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    s = m[m.rfind('Summary:'):]
    return float(re.search(r'I:\s+(-?[\d.]+) LUFS', s).group(1)), float(re.search(r'Peak:\s+(-?[\d.]+) dBFS', s).group(1))
I0, _ = lufs(deess)
g = -14.0 - I0
for _ in range(4):
    chain = f'{deess},volume={g:.2f}dB,{lim}'
    I1, tp = lufs(chain)
    if abs(I1 + 14) <= 0.15: break
    g += -14.0 - I1
print(f'Master: S-Laut-Schwelle {T:.1f} dBFS, Eingang {I0:.2f} LUFS, Verstärkung {g:+.2f} dB, Ausgang {I1:.2f} LUFS, True Peak {tp:.2f} dBTP')
assert tp <= -1.5 and abs(I1 + 14) <= 0.3, 'Lautheit oder True Peak außerhalb'
# Runde 5 (17.10.2026): der Master liegt zusätzlich unkomprimiert neben dst (render-ton.wav); die Lieferung kodiert ihn genau einmal.
# Vorher kodierte ffmpegs AAC hier und die Lieferung den dekodierten Ton noch einmal: +0,39 dBTP Knack im ersten Bild, nur links.
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kanal
from pathlib import Path
wav = Path(dst).with_name('render-ton.wav')
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-filter_complex', f'[0:a]{chain},asetpts=N/SR/TB[o]', '-map', '[o]',
                '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le', str(wav)], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-i', str(wav), '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                '-ar', '48000', '-ac', '2'] + kanal.aac_kodierer() + ['-b:a', '256k', '-movflags', '+faststart', dst], check=True)
print('mastered', dst)
