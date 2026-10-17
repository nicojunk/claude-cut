#!/usr/bin/env python3
"""Vorab-Prüfung der Schnitte VOR dem Rendern (15.10.2026, R2: 4 angeschnittene Pausenschnitte erst nach dem Render gefunden).
Setzt den Reel-Ton aus take.mp4 und projekt/edl.json 'ranges' zusammen und misst jeden Pausenschnitt und jede Montage-Naht
wie pruefe_ms.py Abschnitt 1: Spitze im Fenster ±15 ms unter Grundrauschen (p10) + 12 dB.
Aufruf: python3 schnitte_vorab.py ORDNER   Exit 1 bei angeschnittenen Stellen."""
import json, subprocess, sys
import numpy as np
d = sys.argv[1]
E = json.load(open(f'{d}/projekt/edl.json')); ST = json.load(open(f'{d}/take.stuecke.json'))
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', f'{d}/take.mp4', '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                     capture_output=True, check=True).stdout
t_a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
R = E['ranges']
a = np.concatenate([t_a[int(round(r0 * 16000)):int(round(r1 * 16000))] for r0, r1 in R])
n = len(a) // 160
db = 20 * np.log10(np.sqrt(np.mean(a[:n * 160].reshape(n, 160) ** 2, axis=1) + 1e-12))
thr = np.percentile(db[db > -80], 10) + 12
def take2out(x):
    o = 0.0
    for r0, r1 in R:
        if x < r0: return o
        if x <= r1: return o + (x - r0)
        o += r1 - r0
    return o
schnitte, t = [], 0.0
for k, (r0, r1) in enumerate(R[:-1]):
    t += r1 - r0; schnitte.append(('Pausenschnitt', round(t, 3)))
off = 0.0
for s in ST[:-1]:
    off += s['bis'] - s['von']; schnitte.append(('Montage-Naht', round(take2out(off), 3)))
schlecht = 0
for typ, c in sorted(schnitte, key=lambda x: x[1]):
    lauf = db[max(0, int((c - 0.015) * 100)):int((c + 0.015) * 100) + 1]
    sp = float(lauf.max()) if len(lauf) else -99
    j = int(c * 100); L = j
    while L > 0 and db[L] < thr: L -= 1
    Rr = j
    while Rr < len(db) - 1 and db[Rr] < thr: Rr += 1
    ok = sp < thr - 2                     # 2 dB Sicherheitsabstand: R2 5,800 s lag im Reel 0,1 dB über der Schwelle
    schlecht += not ok
    if not ok or (c - L / 100) < 0.03 or (Rr / 100 - c) < 0.03:
        print(f'  {typ:13s} {c:7.3f} s  Stille links {(c - L / 100) * 1000:4.0f} ms, rechts {(Rr / 100 - c) * 1000:4.0f} ms, '
              f'Spitze {sp:6.1f} dB (Schwelle {thr:.1f})' + ('' if ok else '  <-- ANGESCHNITTEN'))
print(f'{d}: {len(schnitte)} Schnitte, {schlecht} angeschnitten, Dauer {len(a) / 16000:.2f} s')

# B Untertitel gegen den hörbaren Einsatz NACH EINER PAUSE (Hüllkurve, unabhängig vom Ausrichtungsmodell; Abnahme R4 v7:
# "Warum?" 393 ms und "Deine" 295 ms zu spät, 3b sah es nicht). Je Wort: die letzte Pause (mind. 60 ms unter der Sprachschwelle),
# die nach dem Ende des Vorworts liegt und vor der Einblendung beginnt. Einsatz = erster 10-ms-Block über Schwelle + 18 dB
# (über Atem) bis 0,6 s nach der Pause, davon höchstens 60 ms zurück, solange über Schwelle + 8 dB.
# Befund: Untertitel mehr als 250 ms vor oder nach dem Einsatz.
Wt = json.load(open(f'{d}/woerter.json'))
assert len(Wt) == len(E['words']), 'woerter.json und edl passen nicht'
ruhig = db < thr
laeufe, s0 = [], None
for x in range(len(db) + 1):
    q = x < len(db) and ruhig[x]
    if q and s0 is None: s0 = x
    if not q and s0 is not None:
        if x - s0 >= 6: laeufe.append((s0 / 100, x / 100))
        s0 = None
spaet = 0
for i, w in enumerate(E['words']):
    cap = w['out'] + 1 / 30
    lo = take2out(Wt[i - 1]['e']) - 0.05 if i else -1
    kand = [(r0, r1) for r0, r1 in laeufe if r0 < cap - 0.02 and r1 > lo and r1 > cap - 0.6]
    if not kand:
        continue
    r0, r1 = kand[-1]
    q = int(round(r1 * 100))
    s_ = next((x for x in range(q, min(len(db), q + 60)) if db[x] > thr + 18), None)
    if s_ is None:
        continue
    b_ = s_
    while b_ > max(q, s_ - 6) and db[b_ - 1] > thr + 8: b_ -= 1
    on = b_ / 100
    if i + 1 < len(E['words']) and abs(on - (E['words'][i + 1]['out'] + 1 / 30)) < abs(on - cap):
        continue                                   # Einsatz gehört zum nächsten Wort (leise Satzenden wie "sich." bleiben unter + 18 dB)
    dt = cap - on
    if abs(dt) > 0.25:
        spaet += 1
        print(f"  Untertitel '{w['t']}' erscheint {cap:.3f} s, Einsatz nach Pause {on:.3f} s: {'zu spät' if dt > 0 else 'zu früh'} {abs(dt) * 1000:.0f} ms")
    elif abs(dt) > 0.15:
        print(f"  (Warnung) '{w['t']}' {cap:.3f} s gegen Einsatz {on:.3f} s: {dt * 1000:+.0f} ms")
print(f'{d}: {spaet} Untertitel mehr als 250 ms neben dem Einsatz nach einer Pause')

# C Reste an Stückrändern (Berater nach Abnahme R4 v7: Gemurmel nach "Warum?" blieb im Reel). Im Take: Laut über Schwelle + 12 dB
# für mindestens 30 ms zwischen Stückanfang und erstem Wort (minus 100 ms) oder letztem Wortende (plus 250 ms, das Modell setzt
# Wortenden bis 200 ms zu früh: "Warum?" endet hörbar 3,72 s, ausgerichtet 3,50 s) und Stückende,
# soweit dieser Bereich im Reel bleibt (edl ranges).
nt = len(t_a) // 160
dbt = 20 * np.log10(np.sqrt(np.mean(t_a[:nt * 160].reshape(nt, 160) ** 2, axis=1) + 1e-12))
thr_t = np.percentile(dbt[dbt > -80], 10) + 12
def im_reel(x0, x1):
    return [(max(x0, r0), min(x1, r1)) for r0, r1 in R if min(x1, r1) - max(x0, r0) > 0.02]
reste, o = 0, 0.0
for k, s in enumerate(ST):
    g0, g1 = o, o + s['bis'] - s['von'] - float(s.get('stille_danach', 0)); o += s['bis'] - s['von']
    ws = [w for w in Wt if g0 - 0.05 <= w['s'] < g1 - 0.01]
    if not ws:
        continue
    for name, (x0, x1) in (('vor dem ersten Wort', (g0 + 0.01, ws[0]['s'] - 0.10)), ('nach dem letzten Wort', (ws[-1]['e'] + 0.25, g1 - 0.01))):
        for y0, y1 in im_reel(x0, x1):
            lauf = dbt[int(y0 * 100):int(y1 * 100)] > thr_t + 12
            best = cur = 0
            for q in lauf:
                cur = cur + 1 if q else 0; best = max(best, cur)
            if best >= 3:
                reste += 1
                print(f'  Rest {name} in Stück {k} ({s["clip"]}): Take {y0:.2f} bis {y1:.2f} s, {best * 10} ms über Sprachpegel')
print(f'{d}: {reste} Reste an Stückrändern')

# D every caption against the audible onset with the inspector's method (einsatz.py, 1 ms envelope of the assembled reel
# audio): a word after a dip of >= 15 dB is checked, connected speech is not measurable here. Finding: caption more than 120 ms
# after or more than 250 ms before the onset (limits of the independent inspection, 17.10.2026).
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import einsatz as _ez
_r = _ez.huelle_1ms(a, 16000)
WT = json.load(open(f'{d}/woerter.json'))
_n = len(t_a) // 160
_laut = float(np.percentile((_x := 20 * np.log10(np.sqrt(np.mean(t_a[:_n * 160].reshape(_n, 160) ** 2, axis=1) + 1e-12)))[_x > -80], 10) + 12)
_schnitte = sorted(x for _, x in schnitte)
EW = E['words']
d_bef, d_n = 0, 0
for i, w in enumerate(EW):
    if i >= len(WT):
        break
    s0 = w['out']; dur = max(0.05, WT[i]['e'] - WT[i]['s'])
    pe = (EW[i - 1]['out'] + max(0.03, WT[i - 1]['e'] - WT[i - 1]['s'])) if i else 0.0
    on = _ez.einsatz(_r, s0, s0 + dur, min(pe, s0), grenze=max([x for x in _schnitte if x <= s0 - 0.01] or [0.0]), laut=_laut,
                     starts=[take2out(WT[k]['s']) for k in range(max(0, i - 3), i)], halten_ms=30)
    if on is None:
        continue
    d_n += 1
    dt = s0 - on
    # late captions block (the independent inspection's finding, measured by this envelope method). An early caption is only
    # a hint here: inside a word the envelope finds consonant dips (the "v" of "Avatar", a fricative before a stop) and reads the
    # vowel after them as the onset (round 2, 17.10.2026); early captions are measured on the finished audio by pruefe_ms 3b.
    if dt > 0.12:
        d_bef += 1
        print(f"  D Untertitel '{w['t']}' {s0:.3f} s, hörbarer Einsatz {on:.3f} s, zu spät um {dt * 1000:.0f} ms")
    elif dt < -0.25:
        print(f"  (Hinweis) Untertitel '{w['t']}' {s0:.3f} s, Hüllkurve {on:.3f} s, früh um {-dt * 1000:.0f} ms: nach dem Render misst pruefe_ms 3b")
print(f'{d}: {d_bef} Untertitel mehr als 120 ms nach dem hörbaren Einsatz ({d_n} messbare Wörter)')

# Runde 5 (17.10.2026): drei Lücken, durch die Befunde der unabhängigen Abnahme Fall 2 kamen, obwohl alle eigenen Prüfungen bestanden.
import re as _re
_html = open(f'{d}/projekt/index.html').read()
# E Kartenton über einem Wortende (Abnahme: Stempel 10,133 s auf dem Ende von "Die", Pop 36,933 s auf dem Nasal von "dein").
#   Hörbar ist ein Klick dort, wo die Stimme in seinen ersten 15 ms wenig Höhen hat: Klick-Hochband (1 bis 7,9 kHz, mit seiner
#   Lautstärke im Mix) mehr als 10 dB über dem Hochband der Stimme, die Stimme klingt noch (über Schwelle + 6 dB), und ein
#   ausgerichtetes Wortende liegt 20 ms vor bis 60 ms nach dem Tonbeginn. Die freigegebenen Referenz-Töne liegen alle außerhalb
#   (nächstes Wortende 34 ms vor dem Ton, R4 24,8 s).
def _hb(x):
    if len(x) < 32:
        return -120.0
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2; f = np.fft.rfftfreq(len(x), 1 / 16000)
    return float(10 * np.log10(sp[(f >= 1000) & (f <= 7900)].sum() / len(x) + 1e-15))
_sfx_cache, ton_bef = {}, 0
_enden = [take2out(w['e']) for w in Wt]
for _name, _t, _vol in _re.findall(r'<audio id="sx\d+" src="sfx/(\w+)\.wav" data-start="([\d.]+)"[^>]*data-volume="([\d.]+)"', _html):
    _t, _vol = float(_t), float(_vol)
    if _name not in _sfx_cache:
        _sfx_cache[_name] = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', f'{d}/projekt/sfx/{_name}.wav', '-ac', '1', '-ar', '16000',
                                                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout, np.float32)
    k0, k1 = int(_t * 16000), int((_t + 0.015) * 16000)
    if k1 > len(a):
        continue
    stimme = float(20 * np.log10(np.sqrt(np.mean(a[k0:k1] ** 2)) + 1e-12))
    klick_ueber = _hb(_sfx_cache[_name][:k1 - k0] * _vol) - _hb(a[k0:k1])
    ende = [e for e in _enden if -0.02 <= e - _t <= 0.06]
    if stimme > thr + 6 and klick_ueber > 10 and ende:
        ton_bef += 1
        print(f'  E Kartenton {_name} {_t:.3f} s über einem Wortende ({(ende[0] - _t) * 1000:+.0f} ms), Klick {klick_ueber:.0f} dB über dem Hochband der Stimme')
print(f'{d}: {ton_bef} Kartentöne hörbar über einem Wortende')
# F Text, den eine Ausschnittmaske oben oder unten beschneidet (Abnahme: Unterlängen der "g" in "Trink genug" abgeschnitten): ein
#   clipPath "inset(oben rechts unten links ...)" auf einem Element mit Text braucht oben und unten negative Werte.
clip_bef = 0
for _sel, _wert in _re.findall(r'tl\.(?:set|fromTo|to)\("([^"]+)",\{[^}]*?clipPath:"inset\(([^)]*)\)"', _html):
    _teile = _wert.replace('round', ' round ').split()
    _o, _u = _teile[0], _teile[2] if len(_teile) > 2 else _teile[0]
    if not _o.startswith('-') or not _u.startswith('-'):
        # nur wenn die Schrift über ihre Zeilenbox hinausragt: Zeilenhöhe <= 1,05 der Schriftgröße (Chip: line-height 1). Eine
        # Zeile mit normaler Zeilenhöhe (the reference channel R3 Schreibzeile, freigegeben) hält ihre Unterlängen in der Box.
        _teil = _sel.split()
        def _element(start):
            """das Element ab seinem öffnenden Tag bis zum passenden schließenden Tag (Tiefe gezählt)"""
            _tm = _re.match(r'<(\w+)', _html[start:])
            if not _tm:
                return ''
            tag, tiefe, pos = _tm.group(1), 0, start
            for _t in _re.finditer(rf'<(/?){tag}\b[^>]*>', _html[start:]):
                tiefe += -1 if _t.group(1) else 1
                if tiefe == 0:
                    return _html[start:start + _t.end()]
            return _html[start:start + 600]
        _m = _re.search(rf'<\w+[^>]*id="{_re.escape(_teil[0].lstrip("#"))}"', _html)
        if not _m:
            continue
        _ab = _element(_m.start())
        if len(_teil) > 1 and _teil[1].startswith('.'):
            _k = _re.search(rf'<\w+[^>]*class="[^"]*\b{_re.escape(_teil[1][1:])}\b', _ab)
            _ab = _element(_m.start() + _k.start()) if _k else ''
        _klassen = set(c for grp in _re.findall(r'class="([^"]+)"', _ab) for c in grp.split())
        _eng = False
        for _c in _klassen:
            for _regel in _re.findall(rf'\.{_re.escape(_c)}\s*\{{([^}}]*)\}}', _html):
                _lh = _re.search(r'line-height:\s*([\d.]+)(px)?', _regel); _fs = _re.search(r'font-size:\s*([\d.]+)px', _regel)
                if _lh and ((not _lh.group(2) and float(_lh.group(1)) <= 1.05) or
                            (_lh.group(2) and _fs and float(_lh.group(1)) <= 1.05 * float(_fs.group(1)))):
                    _eng = True
        if _eng and _re.search(r'>[^<]*\w[^<]*<', _ab):
            clip_bef += 1
            print(f'  F Maske beschneidet Text oben oder unten: {_sel} inset({_wert}), Zeilenhöhe der Schrift <= 1,05')
print(f'{d}: {clip_bef} Masken, die Text oben oder unten beschneiden')
# G gezeigte statt geplanter Untertitelzeit (Abnahme: das erste Wort nach einem Blitzwechsel kam 4 bis 5 Bilder nach seiner
#   edl-Zeit, weil der Renderer weiße Untertitel bis 4 Bilder nach der Blitzspitze zurückhält; Prüfung D maß die edl-Zeit).
#   baue_reel.py schreibt projekt/untertitel-zeiten.json (Wortindex -> Zeit der Einblendung). Befund: mehr als 50 ms nach der
#   edl-Zeit (der Renderer zeigt ohnehin 1 Bild später, zusammen über der 120-ms-Grenze der Abnahme).
zeig_bef = 0
try:
    _zeig = json.load(open(f'{d}/projekt/untertitel-zeiten.json'))
except FileNotFoundError:
    _zeig = None
    print(f'  G untertitel-zeiten.json fehlt (Komposition mit altem Werkzeug gebaut)  <-- BEFUND'); zeig_bef += 1
for _k, _tz in (_zeig or {}).items():
    _w = E['words'][int(_k)]
    if _tz - _w['out'] > 0.05:
        zeig_bef += 1
        print(f"  G Untertitel '{_w['t']}' geplant {_w['out']:.3f} s, gezeigt {_tz:.3f} s: {(_tz - _w['out']) * 1000:.0f} ms verzögert")
print(f'{d}: {zeig_bef} Untertitel später gezeigt als geplant')
sys.exit(1 if (schlecht or spaet or reste or d_bef or ton_bef or clip_bef or zeig_bef) else 0)
