#!/usr/bin/env python3
"""Dramaturgy gate on the built composition (before the render), from the user's feedback on the reference reels 15.10.2026:
  1 hook from frame 0; between the hook's last sound (take envelope) and the first VISIBLE frame of the change (the flash shows
    about 6 frames before the cut) lie at least 300 ms (23:17 "Bei dem 3 Clip wird zu früh der Clip gewechselt"; inspection
    17.10.2026 measured 23 ms in R3 although the cut came 356 ms after the word)
  2 the viewer's benefit (reel.json "nutzen_bei") starts by second 15 of the finished reel
  3 at least 2 dopamine hits (cards marked "dopamin" in the drop-off map) are in the composition
  4 the version "mit" ends on the comment keyword card, the version "ohne" has none
  5 the first word after the hook carries a caption (R3 15.10.2026: "Hör" was missing, the aligner put it into room tone)
  6 length 20 to 90 s (warning only)
Usage: python3 pruefe_dramaturgie.py REELORDNER VARIANTE   exit 1 on a violated rule."""
import json, re, sys
from pathlib import Path

rd, var = Path(sys.argv[1]).resolve(), sys.argv[2]
D = rd / var
R = json.loads((rd / 'reel.json').read_text())
E = json.loads((D / 'projekt' / 'edl.json').read_text())
P = json.loads((D / 'plan.json').read_text())
A = json.loads((D / 'absprung-karte.json').read_text())
W = json.loads((D / 'woerter.json').read_text())
ST = json.loads((D / 'take.stuecke.json').read_text())
norm = lambda s: re.sub(r'[^\wäöüß0-9]', '', s.lower())
fehler, hinweise = [], []
hook_ende = ST[0]['bis'] - ST[0]['von'] - float(ST[0].get('stille_danach', 0))
HOOK_N = sum(1 for w in W if w.get('stueck', 0 if w['s'] < hook_ende - 0.01 else 1) == 0)
out = [w['out'] for w in E['words']]
# 1 afterglow, measured on the take's envelope: last 10-ms block above the speech threshold inside the hook piece
import subprocess, numpy as np
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(D / 'take.mp4'), '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                     capture_output=True, check=True).stdout
a_ = np.frombuffer(raw, np.int16).astype(np.float32) / 32768; n_ = len(a_) // 160
db = 20 * np.log10(np.sqrt(np.mean(a_[:n_ * 160].reshape(n_, 160) ** 2, axis=1) + 1e-12))
thr = float(np.percentile(db[db > -80], 10) + 12)
laut = [i for i in range(0, min(n_, int(hook_ende * 100))) if db[i] > thr]
def take2out(t):
    o = 0.0
    for r0, r1 in E['ranges']:
        if t < r0: return o
        if t <= r1: return o + t - r0
        o += r1 - r0
    return o
ende_out = take2out((laut[-1] + 1) / 100) if laut else out[HOOK_N - 1]
# Runde 3 (17.10.2026): the last sound is measured in the RAW clip like plan_bauen does (local floor + 10 dB, voiceless ends
# included). On the take the per-version loudness match lifted a low hum 6 dB over the room floor above the take's threshold
# ("ohne" reported -33 ms, "mit" 347 ms for the same hook piece).
import os as _os, sys as _sy
_sy.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import naehte as _nae, kanal as _kan
_hw = [w for w in W[:HOOK_N]]
if _hw:
    _P = _kan.profil(rd)
    _raw_end = ST[0]['bis'] - float(ST[0].get('stille_danach', 0) or 0)
    _von = ST[0]['von']
    _ll = _nae.letzter_laut(ST[0]['clip'], _von + _hw[-1]['s'], _raw_end, _P)
    if _ll is not None:
        ende_out = take2out(_ll - _von)
wechsel = E['segments'][1]['a'] if len(E['segments']) > 1 else E['total']
blitz = any(abs(f - wechsel) < 0.02 for f in E.get('flashes', []))
sichtbar = wechsel - (6 / 30 if blitz else 0)
nachhall = sichtbar - ende_out
print(f'1 Hook: "{" ".join(w["w"] for w in W[:HOOK_N])}" letzter Laut {ende_out:.3f} s, Wechsel {wechsel:.3f} s'
      f'{" (Blitz sichtbar ab " + format(sichtbar, ".3f") + " s)" if blitz else ""}, Nachhall {nachhall * 1000:.0f} ms')
if nachhall < 0.29:
    fehler.append(f'Nachhall nach dem Hook nur {nachhall * 1000:.0f} ms bis zum ersten sichtbaren Bild des Wechsels (mindestens 300 ms)')
# 2 benefit by second 15
nb = R.get('nutzen_bei')
idx = None
if nb:
    teile = [norm(x) for x in re.sub(r'@\d+$', '', nb).split()]
    idx = next((i for i in range(HOOK_N, len(W) - len(teile) + 1) if all(norm(W[i + j]['w']) == t for j, t in enumerate(teile))), None)
if idx is None:
    fehler.append(f'Nutzen-Wort "{nb}" nicht gefunden')
else:
    print(f'2 Nutzen ab "{W[idx]["w"]}" bei {out[idx]:.2f} s')
    if out[idx] > 15.0:
        fehler.append(f'Nutzen beginnt erst bei {out[idx]:.1f} s (spätestens 15 s)')
# 3 dopamine hits
dop = [a for a in A['eintraege'] if a.get('dopamin')]
typen = {c['type'] for c in E['cards']}
da = [a for a in dop if a.get('karte') in typen]
print(f'3 Dopamin-Treffer in der Komposition: {len(da)} ({", ".join(a.get("karte") or "?" for a in da)})')
if len(da) < 2:
    fehler.append(f'nur {len(da)} Dopamin-Treffer mit Karte, mindestens 2')
# 4 call to action
kw = [c for c in E['cards'] if c['type'] == 'keyword']
print(f'4 Aufruf-Karten: {len(kw)} (Fassung {var})')
if var == 'mit' and not kw:
    fehler.append('Fassung "mit" ohne Kommentarwort-Karte')
if var == 'mit' and kw and kw[-1]['appear'] < E['total'] - 15:
    hinweise.append(f'Kommentarwort-Karte schon bei {kw[-1]["appear"]:.1f} s von {E["total"]:.1f} s')
# 5 first word after the hook has a caption
erst = HOOK_N
gruppen_w = {i for g in P['groups'] for i in g['w']}
print(f'5 erstes Wort nach dem Hook: "{W[erst]["w"]}" bei {out[erst]:.3f} s, Untertitel {"ja" if erst in gruppen_w else "NEIN"}')
if erst not in gruppen_w:
    fehler.append(f'erstes Wort nach dem Hook "{W[erst]["w"]}" hat keinen Untertitel')
# 6b channel duty cards (profile "pflicht_karten": [{"wenn": regex on the reel's words, "text": regex on card texts, "grund"}]),
# e.g. a doctor note in health reels; validation 17.10.2026: no script read the channel rules at all
import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kanal
P = kanal.profil(rd)
alle_karten = ' '.join(json.dumps(c, ensure_ascii=False) for c in P_cards) if (P_cards := json.loads((D / 'plan.json').read_text()).get('cards')) else ''
woerter_text = ' '.join(w['w'] for w in W)
for pk in P.get('pflicht_karten', []):
    if re.search(pk['wenn'], woerter_text, re.I) and not re.search(pk['text'], alle_karten, re.I):
        fehler.append(f'Kanalregel: {pk.get("grund", "")} (Reel spricht über /{pk["wenn"]}/, keine Karte enthält /{pk["text"]}/)')
# 6 length
print(f'6 Länge {E["total"]:.1f} s')
if not 20 <= E['total'] <= 90:
    hinweise.append(f'Länge {E["total"]:.1f} s außerhalb 20 bis 90 s')
for h in hinweise:
    print('HINWEIS', h)
for f in fehler:
    print('REGEL VERLETZT', f)
print('ERGEBNIS:', 'bestanden' if not fehler else f'{len(fehler)} Regelverletzung(en)')
sys.exit(1 if fehler else 0)
