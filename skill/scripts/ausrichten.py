#!/usr/bin/env python3.14
"""Wortzeiten per erzwungener Ausrichtung (CTC forced alignment), statt Whisper-Zeitstempeln (15.10.2026).
Grund: Whisper legt Wortanfänge und -enden in Pausen (Abnahmen R4 v5/v6: Untertitel bis 540 ms vor dem Wort); die
Whisper-gestützte Korrektur kam bei leisen Wörtern nicht zum Ziel ("willst" als "Hörst" gehört, "Zehn" als "10").
Hier wird der bekannte Text (woerter.json, je Montage-Stück per Whisper transkribiert und geprüft) Buchstabe für Buchstabe auf
den Ton gelegt: torchaudio VOXPOPULI_ASR_BASE_10K_DE (Deutsch, mit ä ö ü ß) + torchaudio.functional.forced_align.
Zahlen werden für die Ausrichtung in Sprechform umgeschrieben, der Untertitel-Text bleibt unverändert.
Aufruf: python3.14 ausrichten.py take.mp4 take.stuecke.json woerter.json   (Sicherung: woerter.vor-ausrichtung.json)"""
import json, re, shutil, subprocess, sys
from pathlib import Path
import torch, torchaudio

take, st_p, wp = sys.argv[1], sys.argv[2], Path(sys.argv[3])
ST = json.load(open(st_p))
W = json.load(open(wp))
bak = wp.with_name('woerter.vor-ausrichtung.json')
if not bak.exists():
    shutil.copy(wp, bak)
W = json.load(open(bak))                              # immer von den Whisper-Zeiten aus (wiederholbar)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zahlwort   # spoken form of digits, any number (was a fixed table of the reference reels)
bundle = torchaudio.pipelines.VOXPOPULI_ASR_BASE_10K_DE
labels = bundle.get_labels()
LID = {c: i for i, c in enumerate(labels)}
model = bundle.get_model().eval()
SR = bundle.sample_rate


def sprechform(w):
    return zahlwort.sprechform(w)


raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', take, '-vn', '-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                     capture_output=True, check=True).stdout
audio = torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768
o = 0.0
grenzen = []
for s in ST:
    d = s['bis'] - s['von']
    grenzen.append((o, o + d)); o += d
geaendert, verschiebung = 0, []
for k, (g0, g1) in enumerate(grenzen):
    idxs = [i for i, w in enumerate(W) if g0 - 0.05 <= w['s'] < g1 - 0.01]
    if not idxs:
        continue
    teile = [(i, sprechform(W[i]['w'])) for i in idxs]
    teile = [(i, t) for i, t in teile if t]
    zeichen, wortzu = [], []
    for n_, (i, t) in enumerate(teile):
        for c in t.replace(' ', '|'):
            if c in LID:
                zeichen.append(LID[c]); wortzu.append(n_)
        if n_ < len(teile) - 1:
            zeichen.append(LID['|']); wortzu.append(-1)
    # Stille am Stückanfang nicht mitgeben (17.10.2026): CTC legte das erste Wort sonst auf den Stückanfang ("Hör" in R3 0,34 s
    # zu früh). Fenster beginnt 120 ms vor dem ersten Laut des Stücks (30 ms über Grundrauschen des Stücks p10 + 12 dB; mit + 26 dB lag
    # "Du" im lauten Interview-Einstieg 0,63 s zu spät).
    _seg = audio[int(g0 * SR):int(g1 * SR)].numpy(); _m = len(_seg) // 160
    if _m > 20:
        import numpy as _np
        _lv = 20 * _np.log10(_np.sqrt(_np.mean(_seg[:_m * 160].reshape(_m, 160) ** 2, axis=1) + 1e-12))
        _sw = float(_np.percentile(_lv, 10)) + 12   # speech threshold of this piece, must hold for 30 ms
        _on = next((x for x in range(_m - 3) if (_lv[x:x + 3] > _sw).all()), None)
        if _on is not None and _on / 100 - 0.12 > 0.05:
            g0 = g0 + _on / 100 - 0.12
    wav = audio[int(g0 * SR):int(g1 * SR)].unsqueeze(0)
    with torch.inference_mode():
        em, _ = model(wav)
        em = torch.log_softmax(em, dim=-1)
    rahmen = wav.shape[1] / em.shape[1] / SR
    ziel = torch.tensor([zeichen], dtype=torch.int32)
    ali, sc = torchaudio.functional.forced_align(em, ziel, blank=0)
    spans = torchaudio.functional.merge_tokens(ali[0], sc[0].exp())
    if len(spans) != len(zeichen):
        print(f'Stück {k}: {len(spans)} Spannen für {len(zeichen)} Zeichen, Stück übersprungen'); continue
    for n_, (i, t) in enumerate(teile):
        sp = [spans[j] for j in range(len(zeichen)) if wortzu[j] == n_]
        if not sp:
            continue
        s_neu = round(g0 + sp[0].start * rahmen - 0.03, 3)   # CTC setzt den Anfang 1 bis 2 Rahmen spät
        e_neu = round(g0 + sp[-1].end * rahmen, 3)
        verschiebung.append(s_neu - W[i]['s'])
        W[i]['s'], W[i]['e'] = s_neu, max(e_neu, s_neu + 0.05)
        geaendert += 1
# Wortanfang in Stille? (R3 15.10.2026: "Hör" auf -0,03 s gelegt, gesprochen ab 0,31 s.) Liegt im Fenster 150 ms ab dem
# Wortanfang kein Laut über Grundrauschen + 8 dB, rückt der Anfang auf den ersten deutlichen Laut (+ 22 dB) der nächsten 0,8 s,
# von dort zurück bis unter die Sprachschwelle, minus 20 ms.
import numpy as np
_a = audio.numpy(); _n = len(_a) // 160
_db = 20 * np.log10(np.sqrt(np.mean(_a[:_n * 160].reshape(_n, 160) ** 2, axis=1) + 1e-12))
_thr = float(np.percentile(_db[_db > -80], 10) + 12)
# The rule "Wortanfang aus der Stille" (move a start LATER onto the first loud sound) was removed 17.10.2026: on a take with a
# higher noise floor it pushed 10 quiet words up to 675 ms late (validation case 2), against pitfall 12. A first word glued
# onto its piece start is handled below by the per-piece rule.
verschoben, verschoben_i = [], []
# Nachausrichtung (Abnahme R3 v1 15.10.2026: nach "Hör" in der Stille lagen "mal" und "hin!" 170 bis 215 ms zu spät, die
# Ausrichtung des ganzen Stücks war am Anfang verrutscht). Für jedes aus der Stille geholte Wort wird sein Lauf (Folgewörter
# mit weniger als 0,25 s Abstand, höchstens 8) im engen Fenster ab dem neuen Anfang neu ausgerichtet. Übernommen wird nur ein
# früherer Anfang (nie später, Lehre "Kostenlos"), das geholte Wort behält den Pegelanfang, wenn der früher liegt.
nachgerichtet = []
for i in verschoben_i:
    k = i
    while k + 1 < len(W) and k - i < 7 and W[k + 1]['s'] - W[k]['e'] < 0.25:
        k += 1
    if k == i:
        continue
    lauf = [(j, sprechform(W[j]['w'])) for j in range(i, k + 1)]
    lauf = [(j, t) for j, t in lauf if t]
    a0 = max(0.0, W[i]['s'] - 0.06)
    a1 = W[k]['e'] + 0.2
    if k + 1 < len(W):
        a1 = min(a1, W[k + 1]['s'] - 0.02)
    z, wz = [], []
    for n_, (j, t) in enumerate(lauf):
        for c in t.replace(' ', '|'):
            if c in LID:
                z.append(LID[c]); wz.append(n_)
        if n_ < len(lauf) - 1:
            z.append(LID['|']); wz.append(-1)
    wav = audio[int(a0 * SR):int(a1 * SR)].unsqueeze(0)
    with torch.inference_mode():
        em, _ = model(wav)
        em = torch.log_softmax(em, dim=-1)
    rr = wav.shape[1] / em.shape[1] / SR
    ali, sc = torchaudio.functional.forced_align(em, torch.tensor([z], dtype=torch.int32), blank=0)
    spans = torchaudio.functional.merge_tokens(ali[0], sc[0].exp())
    if len(spans) != len(z):
        continue
    for n_, (j, t) in enumerate(lauf):
        sp = [spans[q] for q in range(len(z)) if wz[q] == n_]
        if not sp:
            continue
        s2 = round(a0 + sp[0].start * rr - 0.03, 3)
        e2 = round(a0 + sp[-1].end * rr, 3)
        if j == i:
            W[j]['e'] = max(W[j]['s'] + 0.08, e2)            # Ende war beim Holen künstlich verlängert
            continue
        if s2 < W[j]['s'] - 0.02:
            nachgerichtet.append(f"{W[j]['w']} {W[j]['s']:.2f}->{s2:.2f}")
            W[j]['s'] = s2
            W[j]['e'] = max(e2, s2 + 0.05)
if nachgerichtet:
    print('Nachausrichtung nach geholtem Wortanfang:', ', '.join(nachgerichtet))
# Wortanfang nach einer Pause auf den hörbaren Einsatz (Abnahme R4 v7: "Deine" 290 ms zu spät, das Modell setzt den Anfang
# nach Pausen und an Stückanfängen teils mehrere Silbenlängen daneben). Gleiche Regel wie schnitte_vorab.py B: letzte Pause
# (mind. 60 ms unter der Sprachschwelle) nach dem Vorwort, die vor dem Wortanfang beginnt; Einsatz = erster Block über
# Schwelle + 18 dB in 0,6 s, höchstens 60 ms zurück über Schwelle + 8 dB. Korrigiert ab 150 ms Abweichung.
_ruhig = _db < _thr; _laeufe, _s0 = [], None
for _x in range(_n + 1):
    _q = _x < _n and _ruhig[_x]
    if _q and _s0 is None: _s0 = _x
    if not _q and _s0 is not None:
        if _x - _s0 >= 6: _laeufe.append((_s0 / 100, _x / 100))
        _s0 = None
_gem = set()   # Runde 6: Wörter mit gemessenem Einsatz (Pause, Stückanfang, Hüllkurve, Anlaut); anlaut.verbunden lässt sie stehen
eingesetzt = []
for i, w in enumerate(W):
    lo = W[i - 1]['e'] - 0.05 if i else -1
    kand = [(r0, r1) for r0, r1 in _laeufe if r0 < w['s'] + 0.01 and r1 > lo and r1 > w['s'] - 0.6]
    if not kand:
        continue
    r1 = kand[-1][1]; q = int(round(r1 * 100))
    s_ = next((x for x in range(q, min(_n, q + 60)) if _db[x] > _thr + 18), None)
    if s_ is None:
        continue
    b_ = s_
    while b_ > max(q, s_ - 6) and _db[b_ - 1] > _thr + 8: b_ -= 1
    on = b_ / 100
    if i + 1 < len(W) and on > W[i + 1]['s'] - 0.05:
        continue
    s_neu = round(on - 0.03, 3)
    # nur nach vorn: ein behauchter Anlaut ("Kostenlos") bleibt unter Schwelle + 18 dB, der Einsatz läge sonst auf dem Vokal
    # (Abnahme R2: Untertitel 299 ms zu spät)
    if s_neu < w['s'] - 0.15:
        eingesetzt.append(f"{w['w']} {w['s']:.2f}->{s_neu:.2f}"); _gem.add(id(w))
        w['s'] = s_neu; w['e'] = max(w['e'], s_neu + 0.08)
if eingesetzt:
    print('Wortanfang auf den Einsatz nach der Pause:', ', '.join(eingesetzt))
# Erstes Wort jedes Montage-Stücks auf den Einsatz IM EIGENEN STÜCK (17.10.2026, Fehler aus R3 15.10.: "Hör" lag 0,34 s zu früh
# im Raumton des Einstiegs, weil das vorige Stück lauter rauscht und die Pausenregel oben dort keine Stille findet). Schwelle aus
# dem Grundrauschen dieses Stücks (p10 + 12 dB), Einsatz = erster Block über Schwelle + 18 dB, höchstens 60 ms zurück über
# Schwelle + 8 dB, Anfang 30 ms davor. Kein Wort beginnt vor seinem Stück.
_st_kanten = []
_o = 0.0
for _s in ST:
    _st_kanten.append((_o, _o + _s['bis'] - _s['von'])); _o += _s['bis'] - _s['von']
_stueck_neu = []
for _k, (_a, _b) in enumerate(_st_kanten):
    _iw = [i for i, w in enumerate(W) if w.get('stueck', -1) == _k] or [i for i, w in enumerate(W) if _a - 0.05 <= w['s'] < _b - 0.01]
    if not _iw or _k == 0:
        continue
    i = _iw[0]; w = W[i]
    # two symptoms only: the aligner glued the word onto the piece start (R3 "Hör" 15.10.), or put it late after the piece's
    # leading silence. A breath blip must not count as onset (17.10.2026: it moved a correct "Den" 0.75 s too early), so the
    # onset is speech of this word: 30 ms above max(piece floor + 12 dB, word peak - 20 dB).
    _geklebt = w['s'] <= _a + 0.03
    _x0, _x1 = int(round(_a * 100)), min(_n, int(round(_b * 100)))
    if _x1 - _x0 < 20:
        continue
    _bis = min(_x1, int(round((W[i + 1]['s'] if i + 1 < len(W) and W[i + 1]['s'] > _a + 0.05 else _a + 1.2) * 100)) + 30)
    _spitze = float(_db[_x0:_bis].max())
    _schw = max(float(np.percentile(_db[_x0:_x1], 10)) + 12, _spitze - 20)   # speech of this word, not a breath
    _on = next((x for x in range(_x0 + 1, _bis - 3) if (_db[x:x + 3] > _schw).all()), None)
    if _on is None:
        continue
    _k0 = _on
    while _on > max(_x0 + 1, _k0 - 6) and _db[_on - 1] > _schw - 10:   # back over the soft attack, at most 60 ms
        _on -= 1
    _s_neu = round(max(_a + 0.01, _on / 100 - 0.03), 3)
    # later only when glued to the piece start (never "correct" a start later from the envelope otherwise: pitfall 12)
    if (_geklebt and _s_neu - w['s'] > 0.05) or (not _geklebt and w['s'] - _s_neu > 0.05):
        _stueck_neu.append(f"{w['w']} {w['s']:.2f}->{_s_neu:.2f} (Stück {_k})"); _gem.add(id(w))
        w['s'] = _s_neu; w['e'] = max(w['e'], _s_neu + 0.08)
if _stueck_neu:
    print('Erstes Wort im Stück auf den eigenen Einsatz:', ', '.join(_stueck_neu))
# Runde 4 (17.10.2026): CTC zieht ein Wort manchmal über eine Pause (Prüffall mit tiefer Männerstimme: ein Wort über 1,3 s
# ausgerichtet, 0,6 s davon gesprochen, dann 0,6 s tiefes Brummen im Hook). Die Wortmaske deckte die Pause, so wurde sie weder
# geschnitten noch abgesenkt, und der Einsatz des nächsten Worts (120 ms zu spät) war gesperrt, weil er nie ins vorige Wort darf.
# einsatz.pause_im_wort im Band 1 bis 7,9 kHz; das Wort endet 30 ms nach dem Beginn der Pause. Läuft vor der Einsatzmessung,
# damit die das nächste Wort danach richtig vorziehen kann. Geprüft: Trockenlauf auf den fertigen Zeiten der 8 Referenz-Fassungen
# (kein Wort), Neubau beider Prüffälle (nur das gestreckte Wort); siehe pitfalls.md 77.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import einsatz as _ez
_hb = _ez.hochband(audio.numpy(), SR)
_hb_laut = float(np.percentile(_hb, 10)) + 12 if len(_hb) else 0.0
_gekuerzt = []
for w in W:
    _p = _ez.pause_im_wort(_hb, w['s'], w['e'], _hb_laut)
    if _p is not None:
        _gekuerzt.append(f"{w['w']} Ende {w['e']:.2f}->{_p + 0.03:.2f}")
        w['e'] = round(_p + 0.03, 3)
if _gekuerzt:
    print('Wortende vor die Pause im Wort:', ', '.join(_gekuerzt))
# Audible onset from the envelope (method of the independent inspector, einsatz.py): a word that follows a dip of at least
# 15 dB starts where the level rises again; the CTC start was up to 207 ms later ("verrate", "mir", R3 17.10.2026).
# Only earlier, never into the previous word. With the extra rules of einsatz.py (never across a piece start, the take's
# speech level held 30 ms, a dip owned by the next aligned word skipped): round 2 (deep male voice, room noise) 4 hand-
# measured starts moved from -142/-74/-100/-40 ms to -75/-12/-35/-4 ms; the reference channel R3 unchanged at the words
# the inspection had found late ("verrate", "mir").
sys.path.insert(0, str(Path(__file__).resolve().parent))
import einsatz as _ez
_r1 = _ez.huelle_1ms(audio.numpy(), SR)
_frueh, _lags, _ohne = [], [], []
for i, w in enumerate(W):
    pe = W[i - 1]['e'] if i else 0.0
    _g = max([a_ for a_, _ in _st_kanten if a_ <= w['s'] - 0.01] or [0.0])
    on = _ez.einsatz(_r1, w['s'], w['e'], pe, grenze=_g if _g > 0 else None, laut=_thr,
                     starts=[W[k]['s'] for k in range(max(0, i - 3), i)], halten_ms=30)
    if on is None:
        _ohne.append(i)
        continue
    s_neu = round(on - 0.02, 3)
    _lags.append(w['s'] - s_neu)
    if w['s'] - s_neu > 0.06 and s_neu > (W[i - 1]['s'] + 0.05 if i else 0.0):
        _frueh.append(f"{w['w']} {w['s']:.2f}->{s_neu:.2f}"); _gem.add(id(w))
        w['s'] = s_neu
        if i and W[i - 1]['e'] > s_neu:
            W[i - 1]['e'] = s_neu
if _frueh:
    print('Wortanfang auf den hörbaren Einsatz (früher):', ', '.join(_frueh))
# Runde 4 (17.10.2026): weiche Anlaute in verbundener Rede (stimmloser Reibelaut im Hochband, Nasal am Abfall des Mittelbands),
# anlaut.py. Die Abnahme maß "Morgen" 138 und 148 ms, "Ergebnis" 139 ms zu spät; nur nach vorn, 40 bis 250 ms.
import anlaut as _an
_B = _an.baender_aus(audio.numpy(), SR)
_anl = []
for i, w in enumerate(W):
    a_ = _an.anlaut(w, W[i - 1]['s'] if i else 0.0, _B, W[i - 1]['w'] if i else '')
    if a_ is None:
        continue
    s_neu = round(a_ - 0.01, 3)
    # nie über einen Stückanfang (Fall 1 Runde 4: das "st" von "kannst." vor der Naht galt als "W" von "Wochenplan")
    # das eigene Stück aus woerter_je_stueck ('stueck'); CTC setzte "Wochenplan" 27 ms vor seine Naht (16,84 statt 16,867 s)
    _g = (_st_kanten[w['stueck']][0] if isinstance(w.get('stueck'), int) and 0 <= w['stueck'] < len(_st_kanten)
          else max([a0 for a0, _ in _st_kanten if a0 <= w['s'] + 1e-6] or [0.0]))
    if 0.04 < w['s'] - s_neu <= 0.25 and s_neu > (W[i - 1]['s'] + 0.08 if i else 0.0) and s_neu >= _g:
        _anl.append(f"{w['w']} {w['s']:.2f}->{s_neu:.2f}"); _gem.add(id(w))
        w['s'] = s_neu
        if i and W[i - 1]['e'] > s_neu:
            W[i - 1]['e'] = s_neu
        if i in _ohne:
            _ohne.remove(i)
if _anl:
    print('Wortanfang auf den weichen Anlaut (früher):', ', '.join(_anl))
# connected speech has no dip to measure; the inspector estimates its onset as CTC start minus the median CTC delay of the
# measurable words. Same here (at most 100 ms, only earlier, never before the previous word's start + 50 ms).
if len(_lags) >= 5:
    _lag = min(0.10, max(0.0, float(np.median(_lags))))
    _n_lag = 0
    for i in _ohne:
        w = W[i]; s_neu = round(w['s'] - _lag, 3)
        if _lag > 0.02 and s_neu > (W[i - 1]['s'] + 0.05 if i else 0.0):
            w['s'] = s_neu; _n_lag += 1
            if i and W[i - 1]['e'] > s_neu:
                W[i - 1]['e'] = s_neu
    print(f'Verbundene Sprache: CTC-Verzug Median {_lag * 1000:.0f} ms aus {len(_lags)} messbaren Wörtern, {_n_lag} Wörter vorgezogen')
# Runde 6 (17.10.2026): verbundene Rede ohne messbaren Einsatz, anlaut.verbunden (Lücke mit Senke, stimmhafte Lücke, Spektralwechsel)
_vb = _an.verbunden(W, audio.numpy(), SR, gemessen=lambda w: id(w) in _gem, stueck_anfang=lambda w: (_st_kanten[w['stueck']][0] if isinstance(w.get('stueck'), int)
                    and 0 <= w['stueck'] < len(_st_kanten) else max([a0 for a0, _ in _st_kanten if a0 <= w['s'] + 1e-6] or [0.0])))
if _vb:
    print(f'Verbundene Rede, Wortanfang früher ({len(_vb)}):', ', '.join(_vb[:12]) + (' …' if len(_vb) > 12 else ''))
# Handkorrektur je Fassung (woerter-korrektur.json: {"Wort": "wirklich", "s": 55.09}), gemessen an der Hüllkurve und belegt durch
# eine Abnahme (R1 Runde 8: "wirklich" begann mit dem leisen w 230 ms vor dem Modellanfang)
_kp = wp.with_name('woerter-korrektur.json')
if _kp.exists():
    for _k in json.load(open(_kp)):
        _hit = [i for i, w in enumerate(W) if w['w'] == _k['wort'] and abs(w['s'] - _k['s']) < 1.5]   # 0.6 was too narrow (validation case 2)
        if _hit:
            W[_hit[0]]['s'] = _k['s']; print(f"Handkorrektur {_k['wort']} -> {_k['s']}")
            if 'e' in _k: W[_hit[0]]['e'] = _k['e']          # R4 v10: "Warum?" lag quer über der Naht, Ende ebenfalls gemessen
for i in range(1, len(W)):                            # Reihenfolge sichern
    if W[i]['s'] < W[i - 1]['s'] + 0.02:
        W[i]['s'] = round(W[i - 1]['s'] + 0.02, 3)
tmp = wp.with_suffix('.tmp')
json.dump(W, open(tmp, 'w'), ensure_ascii=False, indent=0); tmp.replace(wp)
import statistics
v = sorted(verschiebung)
print(f'{geaendert} von {len(W)} Wörtern ausgerichtet; Wortanfang gegenüber Whisper: Median {statistics.median(v) * 1000:+.0f} ms, '
      f'größte Verschiebung nach hinten {max(v) * 1000:+.0f} ms, nach vorn {min(v) * 1000:+.0f} ms')
