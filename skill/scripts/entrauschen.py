#!/usr/bin/env python3
"""Rauschminderung je Rohclip einstellen (15.10.2026 18:50, Nico 18:15: "dieses Zischen").
Befund: afftdn=nf=-30 (fest) hielt die Stimme des Referenzkanals oberhalb 1 kHz für Rauschen und senkte sie um 7 bis 13 dB (Konsonanten
dumpf), das Rauschen in den Pausen nur um denselben Betrag; nach Kompression und Lautheit trat das Rauschen relativ hervor.
Jetzt: je Clip das höchste nf (stärkste Minderung), bei dem die Stimme in den Bändern 1-3, 3-6 und 6-10 kHz höchstens 1,0 dB
und 10-16 kHz höchstens 3 dB verliert. Gemessen an den im Reel benutzten Stücken (höchstens 90 s), Sprache = obere 40 % der
85-ms-Fenster. Ergebnis wird in entrauschen.json gespeichert, damit jede Montage gleich entrauscht.
Aufruf: python3 entrauschen.py CLIP von-bis [von-bis ...]   oder als Modul: nf_fuer(clip, stuecke)"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal
SR, N = 48000, 4096
NR = 15
fq = np.fft.rfftfreq(N, 1 / SR)

def _ton(clip, stuecke, af):
    teile = []
    for von, bis in stuecke:
        # afftdn verzögert um 25,0 ms (wie in montiere_take.py): 25 ms mehr holen und vorne abschneiden, sonst vergleicht die Messung
        # verschobene Fenster (erster Lauf 15.10. 18:55: konstant -1,3 dB bei 1-3 kHz in jeder Stufe = Versatz, kein Verlust)
        dt, af2 = (0.025, af + ',atrim=start=0.025,asetpts=PTS-STARTPTS') if 'afftdn' in af else (0.0, af)
        x = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{von:.3f}', '-t', f'{bis - von + dt:.3f}', '-i', str(kanal.roh(clip)), '-vn',
                                          '-af', af2, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout, np.float32)[:int(round((bis - von) * SR))]
        teile.append(x[int(0.1 * SR):])     # afftdn-Einschwingen am Stückanfang nicht mitmessen
    return np.concatenate(teile)

def _spek(x):
    n = len(x) // N; fr = x[:n * N].reshape(n, N)
    return np.abs(np.fft.rfft(fr * np.hanning(N), axis=1)) ** 2, 10 * np.log10((fr ** 2).mean(1) + 1e-12)

def _band(A, lo, hi): return 10 * np.log10(A[(fq >= lo) & (fq < hi)].sum() + 1e-15)

def kalibrieren(clip, stuecke):
    st, tot = [], 0.0
    for von, bis in sorted(set(map(tuple, stuecke))):
        if tot >= 90: break
        st.append((von, bis)); tot += bis - von
    x0 = _ton(clip, st, 'highpass=f=70'); S0, L0 = _spek(x0)
    sp = L0 > np.percentile(L0, 60); pz = L0 < np.percentile(L0, 10)
    n5 = len(x0) // 4800
    boden = float(np.percentile(20 * np.log10(np.sqrt((x0[:n5 * 4800].reshape(n5, 4800) ** 2).mean(1)) + 1e-9), 5))
    bericht = []
    for nf in range(int(min(-20, boden + 20)), int(max(-80, boden - 10)) - 1, -2):
        x = _ton(clip, st, f'highpass=f=70,afftdn=nf={nf}:nt=w:nr={NR}'); S, L = _spek(x); m = min(len(S), len(S0))
        verl = {f'{lo}-{hi}': _band(S[:m][sp[:m]].mean(0), lo, hi) - _band(S0[:m][sp[:m]].mean(0), lo, hi) for lo, hi in ((1000, 3000), (3000, 6000), (6000, 10000), (10000, 16000))}
        pause = _band(S[:m][pz[:m]].mean(0), 1000, 10000) - _band(S0[:m][pz[:m]].mean(0), 1000, 10000)
        ok = all(v >= -1.0 for k, v in verl.items() if k != '10000-16000') and verl['10000-16000'] >= -3.0
        bericht.append((nf, ok, round(pause, 1), {k: round(v, 1) for k, v in verl.items()}))
        if ok:
            return {'nf': nf, 'nr': NR, 'boden_dbfs': round(boden, 1), 'pause_1_10k_db': round(pause, 1), 'stimme_db': {k: round(v, 1) for k, v in verl.items()},
                    'gemessen_s': round(tot, 1)}, bericht
    return {'nf': -80, 'nr': NR, 'boden_dbfs': round(boden, 1), 'hinweis': 'keine Stufe ohne Stimmverlust'}, bericht

def nf_fuer(clip, stuecke):
    # Cache je Kanal (kanal.cache()/entrauschen.json), Eintrag gilt nur für denselben Dateiinhalt (Schlüssel aus Größe und
    # Anfang/Ende der Datei): ein anderer Clip mit gleichem Namen (IMG_1234 bei zwei Kanälen) bekommt seine eigene Messung.
    # Einträge ohne Schlüssel stammen aus der Referenz-Produktion 15.10.2026 und gelten weiter.
    CACHE = kanal.cache() / 'entrauschen.json'
    cache = json.load(open(CACHE)) if CACHE.exists() else {}
    key = kanal.datei_schluessel(kanal.roh(clip))
    e = cache.get(clip)
    if e is None or e.get('schluessel', key) != key:
        e, _ = kalibrieren(clip, stuecke); e['schluessel'] = key; cache[clip] = e
        json.dump(cache, open(CACHE, 'w'), indent=1, ensure_ascii=False)
    return e['nf'], e['nr']

if __name__ == '__main__':
    clip = sys.argv[1]; st = [tuple(map(float, a.split('-'))) for a in sys.argv[2:]]
    erg, ber = kalibrieren(clip, st)
    for b in ber: print(b)
    print(json.dumps(erg, ensure_ascii=False))
