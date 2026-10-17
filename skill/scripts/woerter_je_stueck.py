#!/usr/bin/env python3.14
"""Wortzeiten für den montierten Take: jedes Stück wird einzeln aus take.mp4 transkribiert (faster-whisper large-v3,
vad_filter, ohne Vortext), dann auf die Stückposition verschoben. Jedes Wort muss im Original-Transkript des Clips
vorkommen, sonst Abbruch (Schutz gegen erfundene Wörter wie "Bis zum nächsten Mal", 15.10.2026).
Aufruf: python3.14 woerter_je_stueck.py take.mp4 take.stuecke.json woerter.json"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
from faster_whisper import WhisperModel
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal
T = kanal.transkripte()
take, st = sys.argv[1], json.load(open(sys.argv[2]))
norm = lambda s: re.sub(r'[^\wäöüß]', '', s.lower())
m = WhisperModel('large-v3', device='cpu', compute_type='int8')
out, off, fehler = [], 0.0, []
for k, s in enumerate(st):
    d = s['bis'] - s['von']
    orig = {norm(w['w']) for w in json.load(open(T / f"{Path(s['clip']).stem}.woerter.json"))}
    with tempfile.TemporaryDirectory() as td:
        wav = f'{td}/s.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{off:.3f}', '-t', f'{d:.3f}', '-i', take, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
        segs, _ = m.transcribe(wav, language='de', word_timestamps=True, vad_filter=True, beam_size=8, condition_on_previous_text=False)
        ws = [w for sg in segs for w in sg.words]
    for w in ws:
        t = w.word.strip()
        if norm(t) and norm(t) not in orig:
            fehler.append(f"Stück {k} ({s['clip']}): '{t}' bei {off + w.start:.2f} s nicht im Original-Transkript")
        out.append({'w': t, 's': round(off + w.start, 3), 'e': round(off + w.end, 3), 'p': round(w.probability, 3), 'stueck': k})
    print(f"Stück {k:2d} {s['clip']:15s} {d:5.2f} s: " + ' '.join(w.word.strip() for w in ws), flush=True)
    off += d
json.dump(out, open(sys.argv[3], 'w'), ensure_ascii=False, indent=0)
for f in fehler: print('PRÜFEN', f)
print(len(out), 'Wörter,', len(fehler), 'Wörter nicht im Original')
