#!/usr/bin/env python3
"""The hook's last word must be heard without context (round 3, 17.10.2026): an automatic trim had cut "gut" and "falsch"
to their first consonant, and every own check passed, because Whisper with the whole sentence as context writes the cut
word anyway. The independent inspection found it by transcribing only the audio up to the hook's end.

Two tests, either one fails the build (exit 1):
1 acoustic: in the RAW clip the last word's sound (from its start, gaps up to 120 ms, naehte.letzter_laut) must end
  before the hook's cut. Whisper alone was not enough: with "gar nicht ..." before it, it still wrote "gut" for a cut "g".
2 Whisper large-v3 without prompt on the montage from 0 to the hook's end (without stille_danach): the hook's last word
  among the last 3 recognised words (same word, or at most 2 letters off for words of 5+ letters; numbers as words).
Usage: python3.14 hook_ende.py VERSIONSORDNER"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
from faster_whisper import WhisperModel
sys.path.insert(0, str(Path(__file__).resolve().parent))
import zahlwort, kanal
import numpy as np

D = Path(sys.argv[1])
ST = json.load(open(D / 'take.stuecke.json'))
W = json.load(open(D / 'woerter.json'))
ende = ST[0]['bis'] - ST[0]['von'] - float(ST[0].get('stille_danach', 0) or 0)
hook = [w for w in W if w.get('stueck', 0 if w['s'] < ende - 0.01 else 1) == 0 and w['s'] < ende]
if not hook:
    sys.exit('Hook-Ende: keine Wörter im Hook')
norm = lambda t: re.sub(r'[^a-zäöüß0-9]', '', zahlwort.sprechform(t).lower() if hasattr(zahlwort, 'sprechform') else t.lower())
ziel = norm(hook[-1]['w'])
with tempfile.TemporaryDirectory() as tmp:
    wav = Path(tmp) / 'hook.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(D / 'take.mp4'), '-t', f'{ende + 0.05:.3f}', '-vn', '-ac', '1', '-ar', '16000', str(wav)], check=True)
    m = WhisperModel('large-v3', device='cpu', compute_type='int8', cpu_threads=4)
    segs, _ = m.transcribe(str(wav), language='de', beam_size=5, word_timestamps=True, condition_on_previous_text=False, vad_filter=False)
    gehoert = [w.word.strip() for s in segs for w in (s.words or [])]


def lev(a, b):
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        p, d[0] = d[:], i
        for j in range(1, len(b) + 1):
            d[j] = min(p[j] + 1, d[j - 1] + 1, p[j - 1] + (a[i - 1] != b[j - 1]))
    return d[len(b)]


# 1 acoustic: the last word's sound in the RAW clip (from its start on, gaps up to 120 ms, naehte.letzter_laut) must end
# before the hook's cut. A sound after a longer silence (a breath, the next sentence) does not count.
import naehte
P = kanal.profil()
schnitt = ST[0]['bis'] - float(ST[0].get('stille_danach', 0) or 0)        # raw seconds where the hook's picture and sound end
wort_roh = ST[0]['von'] + hook[-1]['s']
w_ende = naehte.letzter_laut(ST[0]['clip'], wort_roh, schnitt + 0.6, P)
akustisch_ok = w_ende is None or w_ende <= schnitt + 0.005
print(f'Hook-Schnitt im Rohclip {ST[0]["clip"]} {schnitt:.2f} s: letztes Wort "{hook[-1]["w"]}" klingt bis ' +
      (f'{w_ende:.2f} s' if w_ende else '?') + (', vor dem Schnitt' if akustisch_ok else ': ÜBER DEN SCHNITT HINAUS, Wort angeschnitten'))

letzte = [norm(x) for x in gehoert[-3:]]
ok = any(x == ziel or (len(ziel) >= 5 and lev(x, ziel) <= 2) for x in letzte)
print(f'Hook-Ende ohne Kontext ({ende:.2f} s): gehört "... {" ".join(gehoert[-6:])}", letztes Hook-Wort "{hook[-1]["w"]}": '
      + ('vorhanden' if ok else 'FEHLT, Wort angeschnitten oder zu leise: Hook-Ende im Rohclip prüfen'))
sys.exit(0 if (ok and akustisch_ok) else 1)
