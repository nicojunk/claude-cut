#!/usr/bin/env python3
"""Reel description (reel.json) -> montage list, build plan and drop-off map for one version ("mit" or "ohne" comment keyword).

Replaces the hand-written baue_plan.py of every reference reel (16.10.2026: word indices found by regex in Python, the hook
patched in afterwards by hook_vorne.py). Here the hook is its own field, every anchor is a word of the speaker, and the
dramaturgy rules are checked before anything is built. Format: references/reel-spec.md.

Two stages, because word indices exist only after montage and transcription:
  python3 plan_bauen.py auswahl REELORDNER VARIANTE   -> REELORDNER/VARIANTE/auswahl.json   (before montiere_take.py)
  python3 plan_bauen.py plan    REELORDNER VARIANTE   -> plan.json, absprung-karte.json     (after woerter.json exists)
Exit 2 = rule violated (message says which), exit 3 = channel compliance stop (STOPP.md written, nothing is built).
"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal

norm = lambda s: re.sub(r'[^\wäöüß0-9]', '', s.lower())
DRAMA_FILTER = 'saturate(0.35) brightness(0.7) contrast(1.12)'   # the reference channel R1 to R4, Nico 15.10.2026 18:15 "die Hook muss krass sein"
NACHHALL = 0.30          # s of silence after the last hook sound before the flash becomes visible (Nico 15.10.2026 23:17 "zu früh gewechselt")
BASE = {'und', 'ich', 'du', 'dir', 'dich', 'mir', 'die', 'der', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'einer', 'zu',
        'in', 'im', 'mit', 'für', 'von', 'vom', 'sie', 'wir', 'es', 'er', 'dass', 'wie', 'wenn', 'als', 'hat', 'habe', 'hast', 'haben',
        'bin', 'bist', 'sind', 'sich', 'mein', 'meine', 'meines', 'meinen', 'deine', 'deiner', 'dein', 'deinen', 'deinem', 'über', 'sei',
        'auf', 'an', 'am', 'nicht', 'was', 'so', 'ist', 'ja', 'auch', 'weil', 'oder', 'denn', 'wird', 'werden', 'kann', 'kannst', 'zum',
        'zur', 'bei', 'aus', 'nach', 'noch', 'nur', 'man', 'aber', 'dann', 'da', 'hier', 'sehr', 'mal', 'eben', 'halt', 'doch'}


def fehler(msg, code=2):
    print('REGEL:', msg, file=sys.stderr); sys.exit(code)


def lade(reel_dir):
    R = json.loads((reel_dir / 'reel.json').read_text())
    for k in ('kanal', 'hook', 'stuecke', 'takte', 'varianten'):
        if k not in R:
            fehler(f'reel.json braucht "{k}" (references/reel-spec.md)')
    return R


def transkript(clip):
    return json.loads((kanal.transkripte() / f'{Path(clip).stem}.woerter.json').read_text())


# ---------- stage 1: montage list ----------
STOPP_KOPF = ('# STOPP: Kanalregel verletzt\n\nNichts gebaut. Nicht selbst herausschneiden und nicht um die Stelle herum schneiden: '
              'ein Schnitt ändert, was die Person unter ihrem Namen sagt. Entscheidung bei Nico, eine von drei Möglichkeiten:\n'
              '1. Die Person nimmt den Satz neu auf (Satzspanne unten).\n2. Eine andere Aufnahme ohne diese Stelle wird gewählt.\n'
              '3. Rechtliche Freigabe: dann trägt Nico sie in reel.json unter "stopp_freigabe" ein (Wort, Clip, Sekunde, von, Datum, Beleg).\n\n')
BLITZ_SICHTBAR = 6 / 30   # the light flash becomes visible about 6 frames before the cut (power2.in over 8 frames, inspection 17.10.)


def satzspanne(Wc, i):
    """Raw-clip span of the sentence around word i (to re-record it)."""
    a = i
    while a > 0 and not re.search(r'[.?!]$', Wc[a - 1]['w']):
        a -= 1
    b = i
    while b < len(Wc) - 1 and not re.search(r'[.?!]$', Wc[b]['w']):
        b += 1
    return Wc[a]['s'], Wc[b]['e']


def freigegeben(R, clip, wort, sek):
    return any(f.get('clip') == clip and norm(f.get('wort', '')) == norm(wort) and abs(float(f.get('sekunde', -99)) - sek) < 1.0
               for f in R.get('stopp_freigabe', []))


def compliance_quelle(R, P, stuecke, out):
    """A stop word anywhere between the first and the last used second of a clip stops the reel, also when the chosen pieces
    skip it: skipping the forbidden sentence is cutting it out, and that is Nico's decision. Runs before every other rule."""
    zeilen = []
    for clip in dict.fromkeys(s['clip'] for s in stuecke):
        lo = min(s['von'] for s in stuecke if s['clip'] == clip); hi = max(s['bis'] for s in stuecke if s['clip'] == clip)
        Wa = transkript(clip)
        Wc = [w for w in Wa if lo - 0.05 <= w['s'] <= hi + 0.05]
        for grund, wort, _ in kanal.stopp_treffer([' '.join(w['w'] for w in Wc)], P):
            for i, w in enumerate(Wc):
                if norm(w['w']).startswith(norm(wort.split()[0])):
                    if freigegeben(R, clip, w['w'], w['s']):
                        print(f'Hinweis: Stopp-Treffer "{w["w"]}" {clip} {w["s"]:.2f} s ist rechtlich freigegeben (stopp_freigabe)')
                        continue
                    genutzt = any(s['clip'] == clip and s['von'] <= w['s'] <= s['bis'] for s in stuecke)
                    j = Wa.index(w); a, b = satzspanne(Wa, j)
                    zeilen.append(f'- {clip} {w["s"]:.2f} s: "{" ".join(x["w"] for x in Wc[max(0, i - 8):i + 8])}" | Regel: {grund} | '
                                  f'Satz zum Neuaufnehmen {a:.2f} bis {b:.2f} s | '
                                  f'{"in einem gewählten Stück" if genutzt else "zwischen den gewählten Stücken (übersprungen wäre herausgeschnitten)"}')
    if zeilen:
        (out / 'STOPP.md').write_text(STOPP_KOPF + '\n'.join(dict.fromkeys(zeilen)) + '\n', encoding='utf-8')
        print((out / 'STOPP.md').read_text()); sys.exit(3)


def huelle(clip):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import naehte
    db = naehte.pegel(clip)
    _, rausch, thr = naehte.pausen(db)
    return db, thr


def laut(db, thr, t0, t1):
    """10-ms blocks above the speech threshold in [t0, t1) (indices)."""
    return [i for i in range(max(0, int(round(t0 * 100))), min(len(db), int(round(t1 * 100)))) if db[i] > thr]


def letzter_laut(clip, t0, t1, P):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import naehte
    return naehte.letzter_laut(clip, t0, t1, P)


def hook_pruefen(h, P):
    """Afterglow: at least 300 ms between the last sound of the hook and the first visible frame of the flash (about 200 ms
    before the cut). Never destructive (round 3, 17.10.2026): the round-2 automatic trim read the closure inside the last word
    as "word over, then residue" and cut "gut" and "falsch" (both independent inspections). The tool never moves 'bis'
    earlier. A sound in the last 20 ms before 'bis' stops the build. Missing afterglow is taken from the raw clip after 'bis'
    (real picture, real room tone) as long as no speech comes; only what the clip cannot give becomes stille_danach."""
    db, thr = huelle(h['clip'])
    if h['von'] <= 0.05 and laut(db, thr, 0.0, 0.02):
        print(f'HINWEIS Material: {h["clip"]} beginnt mitten im ersten Wort (Laut ab der ersten Probe). Die Lieferung blendet '
              f'10 ms ein (kein Knacken); die fehlenden Millisekunden des Anlauts gibt es im Material nicht. Nico entscheidet, '
              f'ob dieser Hook bleibt.')
    elif h['von'] > 0.05 and laut(db, thr, h['von'], h['von'] + 0.02):   # sound in the first 20 ms: the fade-in eats the onset
        fehler(f'Hook-Anfang {h["von"]:.2f} s liegt in einem Laut ({h["clip"]}): Anfang in die Stille davor legen '
               f'(SMM_KANAL=<kanal> python3 scripts/naehte.py {h["clip"]} {h["von"] - 1:.1f} {h["von"] + 1:.1f})')
    _alle = transkript(h['clip'])
    W = [w for w in _alle if w['e'] > h['von'] + 0.05 and w['s'] < h['bis']]   # Whisper-Anfänge bis 270 ms zu früh ("Zehn")
    if not W:
        fehler(f'Hook {h["clip"]} {h["von"]}-{h["bis"]}: keine Wörter im Transkript')
    # Runde 5 (17.10.2026, Nico: "Warum fängst du so an, dass Menschen miteinander reden? Das ist ja kein richtiges Deutsch."): der
    # Hook beginnt an einem Satzanfang. Steht vor seinem ersten Wort ein Wort ohne Satzzeichen am Ende (". ? !"), beginnt er mitten
    # im Satz, oft mit einem Nebensatz ("dass ...", "weil ..."). Ausnahme nur mit "mitten_im_satz": true im Hook (bewusst entschieden).
    # erstes Wort = das erste, dessen Ende hinter dem Hook-Anfang liegt (Whisper setzt Anfänge bis 270 ms zu früh: "Zehn" 14,68 s,
    # hörbar ab 14,95 s)
    _i0 = next((i for i, w in enumerate(_alle) if w['e'] > h['von'] + 0.05), None)
    _vor = [_alle[_i0 - 1]] if _i0 else []
    _erstes = _alle[_i0]['w'] if _i0 is not None else ''
    if _vor and not re.search(r'[.?!…]["“”»]?$', _vor[0]['w']) and not h.get('mitten_im_satz'):
        fehler(f'Hook beginnt mitten im Satz: vor "{_erstes}" steht "{_vor[0]["w"]}" ({_vor[0]["e"]:.2f} s). Einen Hook wählen, der mit '
               f'einem Satzanfang beginnt, oder im Hook "mitten_im_satz": true setzen, wenn das bewusst so sein soll')
    if laut(db, thr, h['bis'] - 0.02, h['bis']):
        fehler(f'Hook-Ende {h["bis"]:.2f} s liegt in einem Laut ({h["clip"]}): Ende hinter das letzte Wort in die Stille legen '
               f'(SMM_KANAL=<kanal> python3 scripts/naehte.py {h["clip"]} {h["bis"] - 1:.1f} {h["bis"] + 1:.1f})')
    wort_ende = letzter_laut(h['clip'], W[-1]['s'], h['bis'], P) or h['bis']
    noetig = NACHHALL + BLITZ_SICHTBAR
    ziel = round(wort_ende + noetig + 0.06, 3)          # where the cut must lie (+60 ms: the change snaps to a frame, up to 33 ms earlier)
    h2 = dict(h)
    if ziel > h['bis'] + 0.005:
        nxt = laut(db, thr, h['bis'], ziel + 0.05)       # speech after 'bis' in the raw clip
        frei = min(ziel, nxt[0] / 100 - 0.05) if nxt else ziel
        if frei > h['bis'] + 0.005:
            h2['bis'] = round(frei, 3)
            print(f'Hinweis: Nachhall aus dem Rohclip: Hook endet {h2["bis"]:.2f} s statt {h["bis"]:.2f} s (echtes Bild, Raumton; '
                  f'letzter Laut {wort_ende:.2f} s)')
        fehlt = round(ziel - h2['bis'], 3)
        if fehlt > 0.005 and not h.get('stille_danach'):
            h2['stille_danach'] = fehlt
            h2.setdefault('stille_farbe', P['farben']['ink'])
            print(f'Hinweis: der Rohclip gibt nach dem Hook nur {(h2["bis"] - wort_ende) * 1000:.0f} ms Stille her, '
                  f'{fehlt * 1000:.0f} ms Abblende nach dem Hook ergänzt')
    return h2, W, wort_ende


def raender_pruefen(stuecke):
    """Fixed edges (von_fest / bis_fest) must lie in silence: inspection 17.10.2026 found a word end cut at a fixed seam."""
    cache = {}
    for s in stuecke:
        if s.get('rolle') == 'hook':
            continue
        for feld, t in (('von_fest', s['von']), ('bis_fest', s['bis'])):
            if not s.get(feld):
                continue
            if s['clip'] not in cache:
                cache[s['clip']] = huelle(s['clip'])
            db, thr = cache[s['clip']]
            # start: no sound in the first 20 ms (the fade-in would eat a word onset); end: no sound in the last 20 ms (word end cut).
            # Sound beyond the edge is cut away anyway. A start at the clip start (t <= 50 ms) has no silence to move into.
            fenster = (t, t + 0.02) if feld == 'von_fest' else (t - 0.02, t)
            if not (feld == 'von_fest' and t <= 0.05) and laut(db, thr, *fenster):
                fehler(f'{s["clip"]} {feld.split("_")[0]} {t:.3f} s liegt in einem Laut: festen Rand in die gemessene Stille legen '
                       f'(SMM_KANAL=<kanal> python3 scripts/naehte.py {s["clip"]} {t - 1:.1f} {t + 1:.1f})')
            # Runde 4 (17.10.2026): auch ein Einatmen oder ein kurzer Stimmrest zählt, gemessen wie in der Abnahme (Grund dieser Stelle
            # + 12 dB auf 10 ms): Fall 1 begann mitten im Einatmen vor "Und" (15 dB über Grund), unter der Sprachschwelle der Aufnahme
            import numpy as _np
            k0, k1 = max(0, int((t - 1.0) * 100)), min(len(db), int((t + 1.0) * 100))
            grund = float(_np.percentile(db[k0:k1], 3)) if k1 > k0 else -90.0     # p3: im 2-s-Fenster steckt viel Sprache
            # nur ein Laut, der über den Rand hinweg läuft (20 ms davor UND 20 ms danach), ist angeschnitten. Ein Wort, das 40 ms
            # nach einem Stückanfang einsetzt, ist der eigene Anfang des Stücks (Fall 1 Runde 4: 125,67 s vor dem Einsatz bei 125,71 s)
            _k = int(round(t * 100))
            _vor = [i for i in range(max(0, _k - 2), min(len(db), _k)) if db[i] > grund + 12]
            _nach = [i for i in range(max(0, _k), min(len(db), _k + 2)) if db[i] > grund + 12]
            blk = (_vor + _nach) if (_vor and _nach) else []
            if blk and not (feld == 'von_fest' and t <= 0.05):
                ruhig = [i for i in range(k0, k1) if db[i] <= grund + 12]
                if feld == 'von_fest':
                    # hinter den Atem: erste ruhige Stelle nach dem Lauf, die vor dem nächsten Laut liegt
                    k = _k
                    while k < k1 - 3 and not all(db[j] <= grund + 12 for j in range(k, k + 3)): k += 1   # 30 ms Ruhe
                    tipp = f'hinter den Atem: {k / 100 + 0.01:.2f} s (danach Laut ab ' + next((f'{j / 100:.2f} s' for j in range(k, k1) if db[j] > grund + 12), '?') + ')'
                else:
                    tipp = 'erste ruhige Stelle danach ' + next((f'{i / 100:.2f} s' for i in ruhig if i / 100 > t), '?')
                fehler(f'{s["clip"]} {feld.split("_")[0]} {t:.3f} s liegt in einem Atem oder Laut ({db[blk[0]] - grund:.0f} dB über dem Grund '
                       f'dieser Stelle): den Rand vor oder hinter ihn legen, {tipp} '
                       f'(SMM_KANAL=<kanal> python3 scripts/naehte.py {s["clip"]} {t - 1:.1f} {t + 1:.1f})')


def auswahl(reel_dir, var):
    R = lade(reel_dir); V = R['varianten'][var]
    P = kanal.profil(reel_dir)
    out = reel_dir / var
    out.mkdir(exist_ok=True)
    roh = [dict(R['hook'], von_fest=True, bis_fest=True, rolle='hook')] + [dict(s) for s in R['stuecke'] + V.get('stuecke', [])]
    compliance_quelle(R, P, roh, out)
    h, W, wort_ende = hook_pruefen(dict(R['hook']), P)
    stuecke = [dict(h, von_fest=True, bis_fest=True, rolle='hook')] + roh[1:]
    # a hook lengthened into the raw clip must not overlap the next piece of the same clip: that piece starts after it
    if len(stuecke) > 1 and stuecke[1]['clip'] == h['clip'] and stuecke[1]['von'] < h['bis'] <= stuecke[1]['bis'] - 0.5:
        print(f'Hinweis: Stück 1 beginnt jetzt {h["bis"]:.2f} s statt {stuecke[1]["von"]:.2f} s (Nachhall des Hooks)')
        stuecke[1] = dict(stuecke[1], von=h['bis'], von_fest=True)
    import hook_vorlage                   # Runde 5: auch der gesprochene Hook wird über die 50 Vorlagen gewählt
    try:
        _nr, _muster = hook_vorlage.pruefe(R['hook'].get('vorlage'), 'Hook')
        print(f'Hook nach Vorlage {_nr} "{_muster}"')
    except ValueError as e:
        fehler(str(e))
    raender_pruefen(stuecke)
    (out / 'auswahl.json').write_text(json.dumps(stuecke, ensure_ascii=False, indent=1))
    print(f'auswahl {var}: {len(stuecke)} Stücke, Hook "{" ".join(w["w"] for w in W)}", Laut endet {wort_ende:.2f} s, '
          f'Stille im Clip {(h["bis"] - wort_ende) * 1000:.0f} ms + Standbild {h.get("stille_danach", 0) * 1000:.0f} ms')


# ---------- stage 2: plan ----------
def _lev(a, b):
    if a == b:
        return 0
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        p, d[0] = d[:], i
        for j in range(1, len(b) + 1):
            d[j] = min(p[j] + 1, d[j - 1] + 1, p[j - 1] + (a[i - 1] != b[j - 1]))
    return d[len(b)]


class Woerter:
    def __init__(self, W, start):
        self.W, self.N, self.start = W, len(W), start

    def finde(self, anker, ab, bis=None, was='Anker'):
        """anker: word index (int), "Wort", "Wort@2" (2nd occurrence from ab) or "mehrere Wörter" (phrase, index of its first
        word). Searched in [ab, bis). Exact match first; then an edit distance of at most 2 per word (words of 5+ letters), with a
        note: the per-piece transcription may write "schreiben" where the material transcript had "schreibe" (validation 17.10.)."""
        if isinstance(anker, int):
            return anker
        m = re.fullmatch(r'(.+?)@(\d+)', anker.strip())
        text, nr = (m.group(1), int(m.group(2))) if m else (anker, 1)
        teile = [norm(x) for x in text.split() if norm(x)]
        if not teile:
            fehler(f'leerer Anker "{anker}"')
        ende = min(self.N, bis if bis is not None else self.N)
        for unscharf in (False, True):
            treffer = 0
            for i in range(max(0, ab), ende - len(teile) + 1):
                ok = all((norm(self.W[i + j]['w']) == t) if not unscharf else
                         (norm(self.W[i + j]['w']) == t or (len(t) >= 5 and _lev(norm(self.W[i + j]['w']), t) <= 2)) for j, t in enumerate(teile))
                if ok:
                    treffer += 1
                    if treffer == nr:
                        if unscharf:
                            print(f'Hinweis: {was} "{anker}" trifft unscharf "{" ".join(self.W[i + j]["w"] for j in range(len(teile)))}" (Wort {i})')
                        return i
        fehler(f'{was} "{anker}" zwischen Wort {ab} und {ende} nicht gefunden'
               + (' (Kartenanker suchen nur bis zum nächsten Takt)' if bis is not None else '')
               + f'. Text dort: {" ".join(w["w"] for w in self.W[ab:min(ende, ab + 30)])}')


ANKER_FELD = lambda k: k in ('at', 'until') or k.endswith('_at') or k.endswith('_bis')


def karte_aufloesen(karte, idx0, Wf, bis=None, tief=0):
    """Resolve every anchor field of a card, also inside lists of dicts (bars, rows, nodes, pills, steps) and dicts (rise).
    Anchors are searched from the beat's word up to the next beat (validation 17.10.2026: unbounded search silently bound a
    missing word to a later occurrence 30 s away)."""
    out, cur = {}, idx0
    for k, v in karte.items():
        if ANKER_FELD(k) and isinstance(v, (str, int)):
            out[k] = Wf.finde(v, idx0, bis, was=f'Kartenanker {k}')
        elif ANKER_FELD(k) and isinstance(v, list):
            lst, c2 = [], idx0
            for a in v:
                i = Wf.finde(a, c2, bis, was=f'Kartenanker {k}'); lst.append(i); c2 = i + 1
            out[k] = lst
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            lst = []
            for x in v:           # list items in order: each searched after the previous item's anchor
                r = karte_aufloesen(x, cur, Wf, bis, tief + 1)
                lst.append(r)
                cur = max([cur] + [r[f] for f in r if ANKER_FELD(f) and isinstance(r[f], int)])
            out[k] = lst
        elif isinstance(v, dict):
            out[k] = karte_aufloesen(v, idx0, Wf, bis, tief + 1)
        else:
            out[k] = v
    if tief == 0:
        out.setdefault('at', idx0)
    return out


def fix_karte(W, R):
    """Caption fixes. 1. Whisper fragments are joined automatically: a token starting with "-" or "." belongs to the word
    before ("7 -Tage -Challenge" -> "7-Tage-Challenge", "26 .10." -> "26.10.", inspection 17.10.2026). 2. reel.json "fix":
    the same number of words on both sides replaces word by word ("schreiben wir" -> "schreibe mir" keeps 2 captions with
    their own times); a different number joins into one caption on the first word's time."""
    fix, N, i = {}, len(W), 0
    while i < N - 1:
        j = i
        while j + 1 < N and re.match(r'^[-.]\S', W[j + 1]['w']) and not re.search(r'[?!]$', W[j]['w']):
            j += 1
        if j > i:
            fix[str(i)] = ''.join(W[k]['w'] for k in range(i, j + 1))
            for k in range(i + 1, j + 1):
                fix[str(k)] = ''
        i = j + 1
    for alt, neu in R.get('fix', {}).items():
        a, b = alt.split(), neu.split()
        for i in range(N - len(a) + 1):
            if all(norm(W[i + j]['w']) == norm(t) for j, t in enumerate(a)):
                if len(a) == len(b):
                    for j, t in enumerate(b):
                        fix[str(i + j)] = t
                else:
                    fix[str(i)] = neu
                    for j in range(1, len(a)):
                        fix[str(i + j)] = ''
    return fix


def plan(reel_dir, var):
    R = lade(reel_dir); V = R['varianten'][var]; D = reel_dir / var
    P = kanal.profil(reel_dir)
    W = json.loads((D / 'woerter.json').read_text())
    ST = json.loads((D / 'take.stuecke.json').read_text())
    N = len(W)
    hook_ende = ST[0]['bis'] - ST[0]['von']
    HOOK_N = sum(1 for w in W if w.get('stueck', 0 if w['s'] < hook_ende - 0.01 else 1) == 0)
    if HOOK_N == 0:
        fehler('kein Wort im Hook-Stück')
    # compliance: the reel's own words against the channel stop list, before anything is built
    treffer = kanal.stopp_treffer([' '.join(w['w'] for w in W)], P)
    if treffer:
        zeilen = []
        for grund, wort, _ in treffer:
            for i, w in enumerate(W):
                if norm(wort.split()[0]) and norm(w['w']).startswith(norm(wort.split()[0])):
                    o, acc = w['s'], 0.0
                    for s in ST:
                        d = s['bis'] - s['von']
                        if o < acc + d:
                            zeilen.append(f'- "{" ".join(x["w"] for x in W[max(0, i - 6):i + 6])}" | Regel: {grund} | '
                                          f'Take {w["s"]:.2f} s = {s["clip"]} {s["von"] + o - acc:.2f} s'); break
                        acc += d
        (D / 'STOPP.md').write_text(STOPP_KOPF + '\n'.join(dict.fromkeys(zeilen)) + '\n', encoding='utf-8')
        print((D / 'STOPP.md').read_text()); sys.exit(3)
    Wf = Woerter(W, HOOK_N)
    std = {'tail': 0.6, 'whoosh': False, 'pause_cap': [0.45, 0.3], 'start_zoom': 1.04, 'scale': 1.12}
    std.update(P.get('plan_standard', {})); std.update(R.get('plan', {}))

    segments = [{'state': 'speaker', 'from': 0, 'drama': True, 'drama_zoom': float(R['hook'].get('drama_zoom', 1.15)),
                 'drama_filter': R['hook'].get('drama_filter', DRAMA_FILTER)}]
    if R['hook'].get('drama') is False:
        segments = [{'state': 'speaker', 'from': 0}]
    cards, absprung, cur = [], [], HOOK_N
    absprung.append({'stelle': 'Sekunde 0', 'zitat': ' '.join(w['w'] for w in W[:HOOK_N]), 'absprung': 'Hook, Daumen muss stoppen',
                     'regel': 'stärkster emotionaler Satz aus der eigenen Aufnahme ab Bild 0, Nachhall >= 300 ms, dann Lock-in (Nico 15.10.2026)',
                     'animation': 'Dramatik ab Bild 0' if segments[0].get('drama') else 'ohne Dramatik'})
    takte = R['takte'] + V.get('takte', [])
    idx = []
    for n, t in enumerate(takte):
        i = Wf.finde(t['bei'], cur if n else HOOK_N, was=f'Takt {n}')
        if i < cur:
            fehler(f'Takt {n} "{t["bei"]}" liegt vor dem vorigen Takt')
        if n == 0 and i != HOOK_N:
            print(f'Hinweis: erster Takt beginnt bei Wort {i} "{W[i]["w"]}", nicht direkt nach dem Hook (Wort {HOOK_N} "{W[HOOK_N]["w"]}")')
        cur = i + 1 if t.get('zustand') or t.get('karte') else i
        idx.append(i)
    for n, t in enumerate(takte):
        i = idx[n]
        naechster = next((idx[m] for m in range(n + 1, len(idx)) if idx[m] > i), N)
        if t.get('zustand'):
            seg = {'state': t['zustand'], 'from': i}
            for k in ('flash', 'punch', 'drama', 'drama_zoom', 'drama_filter', 'dip', 'src', 'live'):
                if k in t:
                    seg[k] = t[k]
            if t.get('blitz'):
                seg['flash'] = True
            if n == 0 and 'flash' not in seg and 'blitz' not in t:
                seg['flash'] = True      # lock-in starts with a flash after the dark hook (R1 to R4)
            segments.append(seg)
        if t.get('karte'):
            cards.append(karte_aufloesen(t['karte'], i, Wf, naechster))
        if t.get('absprung'):
            a = dict(t['absprung'])
            a.setdefault('zitat', ' '.join(w['w'] for w in W[i:i + 14]))
            a['wort'] = W[i]['w']; a['karte'] = t.get('karte', {}).get('type')
            absprung.append(a)
    # call to action of this version
    auf = dict(P.get('aufruf', {}).get(var, {})); auf.update(V.get('aufruf', {}))
    if auf.get('bei'):
        i = Wf.finde(auf['bei'], HOOK_N)
        cards.append({'type': 'keyword', 'at': i, 'zone': auf.get('zone', 'top'), 'lead': auf.get('lead', 'Kommentiere'),
                      'keyword': auf['keyword'], **({'sub': auf['sub']} if auf.get('sub') else {})})
    elif var == 'mit':
        fehler('Fassung "mit" braucht varianten.mit.aufruf.bei (Wort, auf dem die Kommentarwort-Karte erscheint)')
    # dramaturgy rules that can be checked on the plan (the rest after the build: pruefe_dramaturgie.py)
    dop = [a for a in absprung if a.get('dopamin')]
    if len(dop) < 2:
        fehler(f'nur {len(dop)} Dopamin-Treffer markiert, mindestens 2 (Kallaway Dopamin-Leiter, references/story-rules.md)')
    for c in cards:
        if c['type'] != 'keyword' and not any(a.get('karte') == c['type'] for a in absprung):
            fehler(f'Karte {c["type"]} ohne Eintrag in der Absprung-Karte: Animationen nur an Absprungstellen (Nico 15.10.2026)')
    if not R.get('nutzen_bei'):
        fehler('"nutzen_bei" fehlt: das Wort, ab dem die Zuschauerin ihren Nutzen hört (muss bis Sekunde 15 kommen)')
    Wf.finde(R['nutzen_bei'], HOOK_N)

    starts = sorted(s['from'] for s in segments)
    rl = dict(P.get('rollen', {})); [rl.setdefault(k, []).extend(v) for k, v in R.get('rollen', {}).items()]
    KEY = {norm(x) for x in rl.get('key', [])}; ACC = {norm(x) for x in rl.get('accent', [])}

    def rollen(g):
        ws = [norm(W[i]['w']) for i in g]
        r = ['accent' if w in ACC else 'base' for w in ws]
        k = [j for j, w in enumerate(ws) if w in KEY]
        if k:
            r[k[0]] = 'key'; return r
        kand = [j for j, w in enumerate(ws) if w not in BASE and w not in ACC]
        if kand:
            j = max(kand, key=lambda j: (W[g[j]]['w'][:1].isupper() and j > 0, len(ws[j])))
            r[j] = 'hero'
        return r

    groups, g = [], []
    for i in range(N):
        if g and (i in starts or len(g) >= 4 or len(' '.join(W[j]['w'] for j in g + [i])) > 24):
            groups.append(g); g = []
        g.append(i)
        if re.search(r'[.?!]$', W[i]['w']) or (W[i]['w'].endswith(',') and len(g) >= 2):
            groups.append(g); g = []
    if g:
        groups.append(g)
    acc, naehte = 0.0, []
    for s in ST[:-1]:
        acc += s['bis'] - s['von']; naehte.append(round(acc, 4))
    fix = fix_karte(W, R)
    G = []
    for gr in groups:
        w = [i for i in gr if fix.get(str(i), None) != '']
        if w:
            G.append({'w': w, 'roles': rollen(w)})
    plan = {'title': f'{R.get("titel", reel_dir.name)} {var}', 'source': 'take.mp4', 'words': 'woerter.json',
            'assets': [a if a.startswith('../') or a.startswith('/') else '../' + a for a in R.get('assets', [])],   # reel.json: relative to the reel folder
            'kartentext_streng': True, 'fix': {k: v for k, v in fix.items() if v}, 'naehte': naehte,
            # the whole hook piece incl. its afterglow and added still stays uncut (the pause cap would shorten the afterglow)
            'keep_pauses': [[max(0.0, W[0]['s'] - 0.3), max(W[HOOK_N - 1]['e'] + 0.45, hook_ende + 0.02)], [W[-1]['e'], W[-1]['e'] + 0.6]] + R.get('keep_pauses', []),
            'segments': segments, 'hero_punch': R.get('hero_punch', []), 'cards': cards, 'groups': G}
    for k, v in std.items():
        plan.setdefault(k, v)
    if R.get('weg'):
        plan['weg'] = R['weg']
    if (D / 'take-ton.mp4').exists():
        plan['render_quelle'] = 'take-ton.mp4'   # gated word gaps (pausen_absenken.py)
    (D / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=1))
    (D / 'absprung-karte.json').write_text(json.dumps({'hinweis': 'Modell, keine gemessenen Absprünge (Kallaway-Regeln, references/kallaway-rules.md).',
                                                       'eintraege': absprung}, ensure_ascii=False, indent=1))
    print(f'plan {var}: Hook {HOOK_N} Wörter, {len(segments)} Segmente, {len(cards)} Karten, {len(G)} Gruppen, {len(dop)} Dopamin-Treffer')


if __name__ == '__main__':
    stufe, rd, var = sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3]
    {'auswahl': auswahl, 'plan': plan}[stufe](rd, var)
