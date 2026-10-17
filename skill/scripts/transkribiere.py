#!/usr/bin/env python3.14
"""Wortzeiten (faster-whisper large-v3) für die Rohclips des Referenzkanals 14.10.2026. Lädt das Modell 1 Mal.
Aufruf: python3.14 transkribiere.py CLIP...   schreibt takes/<name>.woerter.json und takes/<name>.txt"""
import json, subprocess, sys, tempfile
from pathlib import Path
from faster_whisper import WhisperModel
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal
T = kanal.transkripte()
m = WhisperModel('large-v3', device='cpu', compute_type='int8')
for clip in sys.argv[1:]:
    name = Path(clip).stem
    out = T / f'{name}.woerter.json'
    if out.exists(): print('schon da', name, flush=True); continue
    with tempfile.TemporaryDirectory() as td:
        wav = f'{td}/a.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', clip, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
        segs, info = m.transcribe(wav, language='de', word_timestamps=True, vad_filter=False, beam_size=5)
        W = [{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3), 'p': round(w.probability, 3)} for s in segs for w in s.words]
    out.write_text(json.dumps(W, ensure_ascii=False, indent=0))
    (T / f'{name}.txt').write_text(' '.join(x['w'] for x in W))
    print(f'{name}: {len(W)} Wörter', flush=True)
print('FERTIG', flush=True)
