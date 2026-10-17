#!/usr/bin/env python3
"""Setzt aus den Rohclips eines Kanals (Kanal-Profil, kanal.py) einen Take für das Schnittwerkzeug zusammen.
Aufruf: python3 montiere_take.py auswahl.json take.mp4
auswahl.json: [{"clip": "aufnahme-31.mov", "von": 19.54, "bis": 24.44, "satz": "..."}, ...] (Sekunden aus woerter.json)

Jede Grenze wird innerhalb von ±0,18 s auf das leiseste 20-ms-Fenster gelegt (kein angeschnittenes Wort).
Bild: 2160x3840 -> 1080x1920, 30 fps, jedes Stück mit setpts=PTS-STARTPTS, Ton je Stück entrauscht (afftdn, gleicher Grundpegel über alle Clips, Nico 15.10.: Ton beim Szenenwechsel), 30 ms Ein-/Ausblendung,
optional "crop" und "stil": "rueckblende" für das Querformat-Interview, Lautheit auf -18 LUFS angehoben, Ton nie länger als Bild (aresample + atrim auf Bildlänge), Kodierung ohne B-Frames (-bf 0)."""
import json, subprocess, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal
SR = 16000


def ton(clip):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(kanal.roh(clip)), '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32)


def leiseste(a, t, r=0.18, fenster=0.02):
    n = int(fenster * SR)
    best, bt = None, t
    for k in range(int(-r * 100), int(r * 100) + 1):
        tt = t + k / 100
        i = int(tt * SR)
        if i - n // 2 < 0 or i + n // 2 >= len(a):
            continue
        e = float(np.sqrt(np.mean(a[i - n // 2:i + n // 2] ** 2)))
        if best is None or e < best:
            best, bt = e, tt
    return round(bt * 30) / 30          # auf Bildgrenze runden


auswahl = json.load(open(sys.argv[1]))
ziel = sys.argv[2]
cache, stuecke = {}, []
# Nähte am Ton (Nico 15.10.2026 01:32 "da stimmt was nicht", Advisor): jede Grenze liegt in einer gemessenen Pause,
# nie in einem Wort; Pause < 200 ms = Schnitt mitten im Satz -> Warnung
sys.path.insert(0, str(Path(__file__).resolve().parent))
import naehte
pcache, warn, pegel_cache, tcache = {}, [], {}, {}
LANGE_PAUSEN = '--lange-pausen' in sys.argv
for s in auswahl:
    if s['clip'] not in pcache:
        pcache[s['clip']] = naehte.pausen(naehte.pegel(s['clip']))[0]
    P = pcache[s['clip']]
    if LANGE_PAUSEN:
        # 15.10.2026 (R2): eine 60-ms-Senke im Wort "gewinnt" gewann gegen die echte 590-ms-Pause dahinter. Jetzt: Rand in einer
        # Pause = sauber; sonst Pausen ab 150 ms im Fenster ±0,35 s bevorzugt, erst dann kürzere.
        drin_v = [(g0, g1) for g0, g1 in P if g0 <= s['von'] <= g1]
        drin_h = [(g0, g1) for g0, g1 in P if g0 <= s['bis'] <= g1]
        vorne = [(g0, g1) for g0, g1 in P if abs(g1 - s['von']) <= 0.35]
        hinten = [(g0, g1) for g0, g1 in P if abs(g0 - s['bis']) <= 0.35]
        vorne = [g for g in vorne if g[1] - g[0] >= 0.15] or vorne
        hinten = [g for g in hinten if g[1] - g[0] >= 0.15] or hinten
        if drin_v:
            g0, g1 = drin_v[0]; von = min(max(s['von'], g0 + 0.03), g1 - 0.03); gv = g1 - g0
        elif vorne:
            g0, g1 = min(vorne, key=lambda g: abs(g[1] - s['von'])); von = max(g1 - 0.10, g0 + 0.03); gv = g1 - g0
        else:
            von = s['von']; gv = 0.0
        if drin_h:
            g0, g1 = drin_h[0]; bis = max(min(s['bis'], g1 - 0.03), g0 + 0.03); gh = g1 - g0
        elif hinten:
            g0, g1 = min(hinten, key=lambda g: abs(g[0] - s['bis'])); bis = min(g0 + 0.12, g1 - 0.03); gh = g1 - g0
        else:
            bis = s['bis']; gh = 0.0
    else:
        vorne = [(g0, g1) for g0, g1 in P if s['von'] - 0.35 <= g1 <= s['von'] + 0.2]
        hinten = [(g0, g1) for g0, g1 in P if s['bis'] - 0.25 <= g0 <= s['bis'] + 0.35]
        if vorne:
            g0, g1 = min(vorne, key=lambda g: abs(g[1] - s['von']))
            von = max(g1 - 0.10, g0 + 0.03); gv = g1 - g0
        else:
            von = s['von']; gv = 0.0
        if hinten:
            g0, g1 = min(hinten, key=lambda g: abs(g[0] - s['bis']))
            bis = min(g0 + 0.12, g1 - 0.03); gh = g1 - g0
        else:
            bis = s['bis']; gh = 0.0
    # Runde 4 (17.10.2026, Abnahme Fall 1): am freien Stückende kein kurzer abgesetzter Stimmrest (34 ms, 15 dB über Grund, 330 ms nach
    # dem Wort), am freien Stückanfang kein abgesetztes Einatmen vor dem ersten Wort. Gemessen wie in der Abnahme: Grund dieser
    # Stelle + 12 dB auf 10 ms; "abgesetzt" = mindestens 100 ms (Ende) bzw. 40 ms (Anfang) Ruhe zur Sprache.
    dbc = pegel_cache.setdefault(s['clip'], naehte.pegel(s['clip']))
    def _laeufe(t0, t1):
        k0, k1 = max(0, int((t0 - 1.0) * 100)), min(len(dbc), int((t1 + 1.0) * 100))
        g_ = float(np.percentile(dbc[k0:k1], 10)) if k1 > k0 else -90.0
        out_, cur = [], None
        for k in range(max(0, int(t0 * 100)), min(len(dbc), int(t1 * 100))):
            if dbc[k] > g_ + 12:
                cur = [k, k] if cur is None else [cur[0], k]
            elif cur is not None:
                out_.append(cur); cur = None
        if cur is not None: out_.append(cur)
        return out_
    # Nur was weder Sprache ist noch im Transkript steht: Spitze unter Sprachschwelle des Clips + 10 dB und außerhalb aller Wörter.
    # Fall 1 Runde 4: ohne diese Sperre fiel das "Wo" von "Wochenplan" als "Einatmen" weg (eigener Lauf, 40 ms Lücke zu "chenplan").
    if s['clip'] not in tcache:
        _tp = kanal.transkripte() / f"{Path(s['clip']).stem}.woerter.json"
        tcache[s['clip']] = json.loads(_tp.read_text()) if _tp.exists() else None
    _TW = tcache[s['clip']]
    _sprache = float(np.percentile(dbc, 10)) + 22
    def _leise(L0):
        return max(dbc[L0[0]:L0[1] + 1]) < _sprache
    def _frei(t0, t1):
        return _TW is not None and not any(w['s'] - 0.03 < t1 and w['e'] + 0.03 > t0 for w in _TW)
    if not s.get('bis_fest'):
        L = _laeufe(bis - 0.6, bis)
        if (len(L) >= 2 and L[-1][1] - L[-1][0] <= 6 and L[-1][0] - L[-2][1] >= 10 and _leise(L[-1])
                and _frei(L[-1][0] / 100, (L[-1][1] + 1) / 100)):
            neu_bis = L[-1][0] / 100 - 0.03
            print(f"Hinweis: {s['clip']} Ende {bis:.2f} -> {neu_bis:.2f} s (kurzer Stimmrest am Stückende weggelassen)")
            bis = neu_bis
    if not s.get('von_fest') and stuecke:
        L = _laeufe(von, von + 0.6)
        if (len(L) >= 2 and L[1][0] - L[0][1] >= 4 and L[0][1] - L[0][0] <= 40 and _leise(L[0])
                and _frei(L[0][0] / 100, (L[0][1] + 1) / 100)):
            neu_von = (L[0][1] + L[1][0]) / 200
            print(f"Hinweis: {s['clip']} Anfang {von:.2f} -> {neu_von:.2f} s (Einatmen vor dem ersten Wort weggelassen)")
            von = neu_von
    if s.get('von_fest'):                        # gemessene Grenze, kein Einrasten (Abnahme R4 v6: Wortrest nach "können")
        von, gv = s['von'], 1.0
    if s.get('bis_fest'):
        bis, gh = s['bis'], 1.0
    if not stuecke and not s.get('von_fest'):     # 0,3 s Vorlauf vor dem ersten Stück: beginnt der erste Bereich bei Take 0, liegt sein
        von = max(0.0, von - 0.3)                # Ton 1 AAC-Rahmen (21,5 ms) früh, am Bereichsende entsteht ein 20-ms-Tonloch (Abnahme R4 v6)
    von, bis = round(von * 30) / 30, round(bis * 30) / 30
    stuecke.append((s['clip'], von, bis))
    for seite, g in (('Anfang', gv), ('Ende', gh)):
        if g < 0.2 and not (seite == 'Anfang' and s['von'] < 0.5):
            warn.append(f"{s['clip']} {seite} bei {s['von'] if seite == 'Anfang' else s['bis']:.2f}: Pause nur {g*1000:.0f} ms (mitten im Satz?)")
    print(f"{s['clip']:15s} {von:7.3f}-{bis:7.3f} ({bis - von:5.2f} s) Pause vorn {gv*1000:4.0f} ms, hinten {gh*1000:4.0f} ms  {s.get('satz', '')[:60]}")
for w in warn:
    print('WARNUNG', w)
if warn and '--trotzdem' not in sys.argv:
    sys.exit('Abbruch: Naht mitten im Satz. Andere Grenze wählen oder --trotzdem.')

# Rauschminderung je Clip (15.10.2026 19:00, Nico 18:15 "dieses Zischen"): nf=-30 fest hielt die Stimme über 1 kHz für Rauschen
# (-7 bis -13 dB, dumpf), jetzt je Clip kalibriert in entrauschen.py (Stimme 1-10 kHz höchstens -1 dB), gespeichert in entrauschen.json
import entrauschen
NF = {c: entrauschen.nf_fuer(c, [(v, b) for cc, v, b in stuecke if cc == c]) for c in {c for c, _, _ in stuecke}}
# Level matching per piece (independent inspection 17.10.2026: +6.2 LU at the seam between two recordings). Integrated loudness
# of every piece after the same noise reduction; each piece is brought to the median of all pieces, at most +-8 dB. An explicit
# "gain" in auswahl.json comes on top (normally not needed any more).
import re as _re
def _lufs(clip, von, bis):
    nf, nr = NF[clip]
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-ss', f'{von:.3f}', '-t', f'{max(0.5, bis - von):.3f}', '-i', str(kanal.roh(clip)),
                        '-vn', '-af', f'aresample=48000,highpass=f=70,afftdn=nf={nf}:nt=w:nr={nr},ebur128=framelog=quiet', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    m = _re.findall(r'I:\s+(-?[0-9.]+) LUFS', r)
    return float(m[-1]) if m else None
_L = [_lufs(c, v, b) for c, v, b in stuecke]
_gueltig = [x for x in _L if x is not None and x > -60]
_ziel = float(np.median(_gueltig)) if _gueltig else None
AUTO = [0.0 if (x is None or _ziel is None or x <= -60) else max(-8.0, min(8.0, round(_ziel - x, 1))) for x in _L]
print('Lautheit je Stück (LUFS):', [None if x is None else round(x, 1) for x in _L], '-> Ziel', None if _ziel is None else round(_ziel, 1),
      'Ausgleich dB:', AUTO)
NUR_TON = sys.argv[sys.argv.index('--nur-ton') + 1] if '--nur-ton' in sys.argv else None
if NUR_TON:
    # Nur den Ton neu erzeugen (Bild und Schnittplan bleiben): Stücke müssen exakt der bestehenden Montage entsprechen
    alt = json.load(open(Path(ziel).with_suffix('.stuecke.json')))
    neu = [{'clip': c, 'von': v, 'bis': b + float(auswahl[i].get('stille_danach', 0))} for i, (c, v, b) in enumerate(stuecke)]
    assert len(alt) == len(neu) and all(a['clip'] == n['clip'] and abs(a['von'] - n['von']) < 1e-3 and abs(a['bis'] - n['bis']) < 1e-3
                                        for a, n in zip(alt, neu)), 'Stücke weichen von take.stuecke.json ab, kein Tontausch'
cmd = ['ffmpeg', '-v', 'error', '-y']
for clip, _, _ in stuecke:
    cmd += ['-i', str(kanal.roh(clip))]
fil, cat = [], ''
for k, (clip, von, bis) in enumerate(stuecke):
    d = bis - von
    s = auswahl[k]
    crop = f"crop={s['crop']}," if s.get('crop') else ''
    # Rückblende (Interview Mai 2026, Querformat): fast schwarzweiß, etwas Korn, Vignette, damit der andere Raum gewollt wirkt
    stil = ',hue=s=0.18,eq=contrast=1.06:brightness=-0.02,noise=alls=9:allf=t,vignette=PI/4.2' if s.get('stil') == 'rueckblende' else ''
    nach = float(s.get('stille_danach', 0))          # Stille nach dem Stück (letztes Bild steht, Ton still), z. B. unter einer Abblende
    pad_v = f',tpad=stop_mode=clone:stop_duration={nach:.3f}' if nach else ''
    # Abnahme R4 v5 (15.10.2026): 170 ms stehendes Gesicht in der Stille. Mit 'stille_farbe' blendet das Bild in die Farbe.
    # Runde 3 (17.10.2026): die Blende beginnt erst am Stückende (vorher 120 ms davor, über dem letzten Wort) und dauert die
    # ganze Stille, so steht kein Bild still (vorher 6 gleiche nachtblaue Bilder vor dem Blitz).
    if nach and s.get('stille_farbe'):
        pad_v += f',fade=t=out:st={d:.3f}:d={nach:.3f}:color={s["stille_farbe"]}'
    fil.append(f'[{k}:v]trim=start={von:.3f}:end={bis:.3f},setpts=PTS-STARTPTS,{crop}scale=1080:1920:flags=lanczos,fps=30{stil}{pad_v},setsar=1,format=yuv420p[v{k}]')
    # afftdn verzögert den Ton um genau 25,0 ms (gemessen 15.10.2026, Kreuzkorrelation): 25 ms mehr Quelle holen und danach
    # vorne abschneiden, sonst fehlen am Stückende 25 ms Wort (Abnahme R4 v5: "können" angeschnitten) und der Ton liegt 25 ms hinter dem Bild
    # 'blende_aus': Ausblendung am Stückende in s (Standard 0,03). Abnahme R4 v7: 30 ms fraßen das Schluss-n von "können",
    # das Folgewort setzt 2 ms nach dem Schnitt ein; dort 5 ms.
    ba = float(s.get('blende_aus', 0.03))
    fil.append(f'[{k}:a]atrim=start={von:.3f}:end={bis + 0.025:.3f},asetpts=PTS-STARTPTS,aresample=48000,'
               f'highpass=f=70,afftdn=nf={NF[clip][0]}:nt=w:nr={NF[clip][1]},atrim=start=0.025,asetpts=PTS-STARTPTS,{"volume=" + str(round(AUTO[k] + float(s.get("gain", 0)), 2)) + "dB," if (AUTO[k] or s.get("gain")) else ""}'
               f'afade=t=in:d=0.03,afade=t=out:st={max(0, d - ba):.3f}:d={ba:.3f},atrim=end={d:.3f}' + (f',apad=pad_dur={nach:.3f}' if nach else '') + f'[a{k}]')
    cat += f'[v{k}][a{k}]'
if NUR_TON:
    fil = [f for f in fil if not f.startswith('[') or ':a]' in f.split(']')[0] + ']']
    fil.append(''.join(f'[a{k}]' for k in range(len(stuecke))) + f'concat=n={len(stuecke)}:v=0:a=1[aa]')
    fil.append('[aa]asetpts=PTS-STARTPTS,loudnorm=I=-18:TP=-2:LRA=11,aresample=48000,asetpts=N/SR/TB[aout]')
    subprocess.run(cmd + ['-filter_complex', ';'.join(fil), '-map', '[aout]', '-c:a', 'pcm_f32le', '-ar', '48000', '-ac', '2', NUR_TON], check=True)
    print('Ton:', NUR_TON, NF); sys.exit(0)
fil.append(f'{cat}concat=n={len(stuecke)}:v=1:a=1[vv][aa]')
fil.append('[vv]setpts=PTS-STARTPTS[vout]')
fil.append('[aa]asetpts=PTS-STARTPTS,loudnorm=I=-18:TP=-2:LRA=11,aresample=48000,asetpts=N/SR/TB[aout]')  # loudnorm setzt beim Leeren des 3-s-Puffers einen Zeitsprung von 100 ms (Abnahme R4 v5), N/SR/TB zählt die Proben durch  # der Ton des Referenzkanals liegt bei -39,5 dB im Mittel, sonst schneidet die Pausenerkennung (-35 dB) Wörter an
cmd += ['-filter_complex', ';'.join(fil), '-map', '[vout]', '-map', '[aout]',
        '-c:v', 'libx264', '-crf', '16', '-preset', 'medium', '-bf', '0', '-pix_fmt', 'yuv420p', '-r', '30',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-shortest', '-movflags', '+faststart', ziel]
subprocess.run(cmd, check=True)
json.dump([{'clip': c, 'von': v, 'bis': b + float(auswahl[i].get('stille_danach', 0)), 'stille_danach': float(auswahl[i].get('stille_danach', 0))} for i, (c, v, b) in enumerate(stuecke)], open(Path(ziel).with_suffix('.stuecke.json'), 'w'), indent=1)
print('Take:', ziel)
