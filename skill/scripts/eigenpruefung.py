#!/usr/bin/env python3.14
"""Eigene Messung nach den Kriterien der unabhängigen Prüfer, vor jeder Übergabe (15.10.2026, Runde 8).
Aufruf: python3.14 eigenpruefung.py ORDNER   (liest ORDNER/liefer.mp4 und ORDNER/projekt/edl.json)
1 Zoomsprung: ORB-Registrierung aufeinanderfolgender Bilder (540x960), Skalierung außerhalb 0,97 bis 1,03 bei >= 40 Inliern.
  Jede Meldung wird nachgemessen: im Gesichtsband (ruhig = Untertitel/Blitz, Hinweis) und im Take (gleicher Sprung = Rohmaterial, Hinweis).
2 Blitz: Bilder Spitze -2 bis +3, Anteil Pixel in der Kanal-Dunkelfarbe (Untertitelschatten) im Untertitelband y 900 bis 1750, nur bei Bildhelligkeit > 225.
3 Karten 0,35 s nach Eintritt: Karte als größte gleichfarbige Fläche (Kanal-Dunkelfarbe oder Weiß) oben, Anteil abweichender Pixel im Inneren.
Exit 1 bei Befund."""
import json, subprocess, sys
import numpy as np, cv2, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kanal
INK = np.array(kanal.rgb('ink', kanal.profil(sys.argv[1])))   # channel dark (the reference channel: ink 30,36,48)
D = sys.argv[1]; V = f'{D}/liefer.mp4'; E = json.load(open(f'{D}/projekt/edl.json'))
FPS = 30
def bilder(a, n, w=540, h=960):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0, a) / FPS:.4f}', '-i', V, '-frames:v', str(n), '-vf', f'scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    k = len(r) // (w * h * 3); return np.frombuffer(r, np.uint8)[:k * w * h * 3].reshape(k, h, w, 3)
befund = 0
NUR = sys.argv[2] if len(sys.argv) > 2 else ''
def take_faktor(i):
    """ORB scale between the take frames that output frames i and i+1 show (None if a cut lies between them)."""
    t0, t1 = i / FPS, (i + 1) / FPS; acc = 0.0; src = []
    for ra, rb in E['ranges']:
        d = rb - ra
        for t in (t0, t1):
            if acc <= t < acc + d: src.append((len(src), ra + t - acc, (ra, rb)))
        acc += d
    if len(src) != 2 or src[0][2] != src[1][2]:
        return None
    fr = []
    for _, ts, _ in src:
        r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{ts:.4f}', '-i', f'{D}/take.mp4', '-frames:v', '1', '-vf', 'scale=540:960', '-f', 'rawvideo',
                            '-pix_fmt', 'gray', '-'], capture_output=True).stdout
        if len(r) != 540 * 960: return None
        fr.append(np.frombuffer(r, np.uint8).reshape(960, 540))
    (a1, b1), (a2, b2) = [orb.detectAndCompute(f, None) for f in fr]
    if b1 is None or b2 is None: return None
    m = bf.match(b1, b2)
    if len(m) < 40: return None
    A_, inl_ = cv2.estimateAffinePartial2D(np.float32([a1[x.queryIdx].pt for x in m]), np.float32([a2[x.trainIdx].pt for x in m]), method=cv2.RANSAC, ransacReprojThreshold=2.0)
    return None if A_ is None else float(np.hypot(A_[0, 0], A_[1, 0]))


def gesicht_faktor(i):
    """ORB scale between output frames i and i+1 on the face band only (full screen rows 300-1300, split 900-1900 of 1920),
    histogram-equalised. None when too few matches."""
    t = (i + 0.5) / FPS
    st = next((sg['state'] for sg in E['segments'] if sg['a'] <= t < sg['b']), 'speaker')
    y0, y1 = (450, 950) if st == 'split' else (150, 650)
    f2 = [cv2.equalizeHist(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)[y0:y1]) for f in bilder(i, 2)]
    if len(f2) < 2: return None
    (a1, b1), (a2, b2) = [orb.detectAndCompute(f, None) for f in f2]
    if b1 is None or b2 is None: return None
    m = bf.match(b1, b2)
    if len(m) < 30: return None
    A_, inl_ = cv2.estimateAffinePartial2D(np.float32([a1[x.queryIdx].pt for x in m]), np.float32([a2[x.trainIdx].pt for x in m]), method=cv2.RANSAC, ransacReprojThreshold=2.0)
    return None if A_ is None or inl_ is None or inl_.sum() < 30 else float(np.hypot(A_[0, 0], A_[1, 0]))


def ohne_untertitel_faktor(i):
    """ORB scale between output frames i and i+1 without the caption band (rows 440-690 of 960), histogram-equalised, only for
    full-frame pictures (speaker, broll). Round 2 validation 17.10.2026: on a dark B-roll still fading out of a flash, the
    caption "Wochenplan" popping in gave 0.920 on the whole frame and the face band (it lies in it); without the band 1.001.
    Synthetic jumps of 4 and 6 % still measure 1.04 and 1.06. Not for split (the paper outweighs the speaker there)."""
    t = (i + 0.5) / FPS
    st = next((sg['state'] for sg in E['segments'] if sg['a'] <= t < sg['b']), 'speaker')
    if st not in ('speaker', 'broll') or i + 1 >= len(alle):
        return None
    g = [cv2.equalizeHist(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)) for f in (alle[i], alle[i + 1])]
    m = np.full(g[0].shape, 255, np.uint8); m[440:690] = 0
    (a1, b1), (a2, b2) = [orb.detectAndCompute(f, m) for f in g]
    if b1 is None or b2 is None: return None
    mm = bf.match(b1, b2)
    if len(mm) < 30: return None
    A_, inl_ = cv2.estimateAffinePartial2D(np.float32([a1[x.queryIdx].pt for x in mm]), np.float32([a2[x.trainIdx].pt for x in mm]), method=cv2.RANSAC, ransacReprojThreshold=2.0)
    return None if A_ is None or inl_ is None or inl_.sum() < 30 else float(np.hypot(A_[0, 0], A_[1, 0]))


# 1 Zoom
print('1 ZOOMSPRUNG (ORB, Inlier >= 40, Schritt > 3 %)')
alle = bilder(0, 10 ** 6) if NUR != 'karten' else []; orb = cv2.ORB_create(1500); bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
kp = [orb.detectAndCompute(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), None) for f in alle]
for i in range(len(alle) - 1):
    (k1, d1), (k2, d2) = kp[i], kp[i + 1]
    if d1 is None or d2 is None or len(k1) < 40 or len(k2) < 40: continue
    m = bf.match(d1, d2)
    if len(m) < 40: continue
    p1 = np.float32([k1[x.queryIdx].pt for x in m]); p2 = np.float32([k2[x.trainIdx].pt for x in m])
    A, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if A is None or inl is None or inl.sum() < 40: continue
    s = float(np.hypot(A[0, 0], A[1, 0]))
    if not 0.97 <= s <= 1.03:
        # a change counts as intended only if it is visible: another state, or a flash/dip on it (inspection 17.10.2026: a
        # speaker -> speaker change without flash reset the zoom by 3.8 % and was waved through as "Zustandswechsel")
        _segs = E['segments']
        wechsel = any(abs(seg['a'] * FPS - (i + 1)) < 0.5 and (seg['state'] != _segs[k_ - 1]['state']
                      or any(abs(f - seg['a']) < 0.02 for f in E.get('flashes', []) + E.get('dips', [])))
                      for k_, seg in enumerate(_segs) if k_ > 0)
        kartenzoom = any(c.get('zoom') and c['appear'] <= (i + 1) / FPS <= c['end'] for c in E.get('cards', []))
        quelle = None if wechsel else take_faktor(i)
        gesicht = None if wechsel else gesicht_faktor(i)
        band = None if wechsel else ohne_untertitel_faktor(i)
        # 17.10.2026: a jump that the take itself shows at the same place is a camera cut or zoom in the raw footage (the reference channel's
        # interview interview.mp4 at 2.73 s: 0.921 in take and reel), not an edit defect: hint, Nico decides
        aus_take = quelle is not None and abs(quelle - s) < 0.02
        # the whole-frame estimate also reacts to a big caption word popping in or a flash; measured again only on the face band
        # (contrast-equalised against the drama darkening), as the manual check of 16.10.2026 did (R3 2.700 s: caption artefact)
        ruhig_band = band is not None and 0.985 <= band <= 1.015
        ruhig = (gesicht is not None and 0.985 <= gesicht <= 1.015) or kartenzoom or ruhig_band   # kartenzoom: a card with zoom_src
        tag = ('  (Zustandswechsel, gewollt)' if wechsel else
               f'  HINWEIS: steht schon im Take (Faktor {quelle:.3f}), Kameraschnitt im Rohmaterial' if aus_take else
               f'  HINWEIS: Gesicht ruhig (Faktor {gesicht:.3f}), Untertitel oder Blitz bewegt das Bild, kein Zoomsprung'
               if ruhig and gesicht is not None and 0.985 <= gesicht <= 1.015 else
               f'  HINWEIS: ohne Untertitelband ruhig (Faktor {band:.3f}), Untertitel oder Blende bewegt das Bild, kein Zoomsprung'
               if ruhig_band else
               '  HINWEIS: geplanter Zoom in eine Karte' if ruhig else
               f'  BEFUND (Gesicht {gesicht if gesicht is None else round(gesicht, 3)})')
        print(f'  Bild {i} -> {i + 1} ({(i + 1) / FPS:.3f} s): Faktor {s:.3f}, {int(inl.sum())} Inlier{tag}'); befund += not (wechsel or aus_take or ruhig)
# 2 Blitz
print('2 WEISSE UNTERTITEL IM BLITZ (Navy-Anteil im Untertitelband bei Bildhelligkeit > 225)')
for fp in E.get('flashes', []):
    n0 = round(fp * FPS)
    for j, f in enumerate(bilder(n0 - 2, 6, 1080, 1920)):
        y = f.astype(int); lum = (0.299 * y[..., 0] + 0.587 * y[..., 1] + 0.114 * y[..., 2])
        if lum.mean() <= 225: continue
        band = y[900:1750]; navy = ((np.abs(band - INK).sum(2) < 75) & (lum[900:1750] < 110)).mean()   # caption shadow in the channel dark
        flag = navy > 0.002
        print(f'  Blitz {fp:.3f} s Bild {n0 - 2 + j}: Helligkeit {lum.mean():.0f}, Navy-Anteil {navy * 100:.2f} %{"  BEFUND" if flag else ""}'); befund += flag
# 3 Karten
print('3 KARTENINHALT 0,35 s NACH EINTRITT (Anteil abweichender Pixel im Karteninneren)')
for c in E.get('cards', []):
    if c['type'] == 'keyword': continue
    # Runde 5 (17.10.2026): leer heißt 15 Bilder ohne Inhalt (Prüferregel). Gemessen werden 4 Bilder ab 0,35 s nach dem Eintritt,
    # es zählt das vollste: die Datumskarte zeigte im 1. Bild nur die durchrollenden Ziffern "1 1" (1,8 %), 13 Bilder später "26".
    _anteile = []
    for _off in (0, 5, 10, 15):
      n = round((c['appear'] + 0.35) * FPS) + _off; f = bilder(n, 1, 1080, 1920)[0].astype(int)
      oben = f[:900]
      best = None
      for name, col, tol in (('dunkel', tuple(int(x) for x in INK), 60), ('weiß', (253, 253, 253), 6)):   # Papier (251, 249, 245) ist nicht Kartenweiß
          m = (np.abs(oben - np.array(col)).sum(2) < tol).astype(np.uint8)
          k, lab, st, _ = cv2.connectedComponentsWithStats(m)
          if k > 1:
              i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); x, y_, w, h, a = st[i]
              if best is None or a > best[0]: best = (a, name, x, y_, w, h, col)
      a, name, x, y_, w, h, col = best
      inn = oben[y_ + 30:y_ + h - 30, x + 30:x + w - 30]
      _anteile.append(((np.abs(inn - np.array(col)).sum(2) > 80).mean() if inn.size else 0, n, name, x, y_, w, h))
    anteil, n, name, x, y_, w, h = max(_anteile)
    flag = anteil < 0.02
    print(f'  {c["id"]} {c["type"][:20]:20} Bild {n}: Karte {name} {w}x{h} bei ({x},{y_}), Inhalt {anteil * 100:.1f} %{"  BEFUND (leer)" if flag else ""}'); befund += flag
# 4 Karte über Augen oder Brauen (Runde 5, 17.10.2026: die Kommentarwort-Karte endete bei 364 bis 368 px, Braue, Brillenrand und
#   Oberlid lagen darunter; das Gesicht stand hoch im Bild). Gemessen im fertigen Bild: Karte = größte kartenweiße Fläche oben
#   (wie 3), Augen und Brauen mit den Vision-Landmarken (bin/augen). Der Gesichtsrahmen allein taugt nicht: verdeckt die Karte die
#   Stirn, rutscht er 27 px nach unten (385 statt 358 px), die Landmarken nicht (Augenoberkante 374 und 375 px).
#   Befund: Kartenunterkante tiefer als die Brauen oder weniger als 25 px über der Augenoberkante, waagerecht überlappend.
print('4 KARTE ÜBER AUGEN ODER BRAUEN (Kartenunterkante gegen Augen- und Brauen-Landmarken)')
import tempfile
_augen = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'augen')
with tempfile.TemporaryDirectory() as _tmp:
    for c in E.get('cards', []):
        if c.get('zone', 'top') != 'top':
            continue
        n0, n1 = round((c['appear'] + 0.35) * FPS), round((c['end'] - 0.1) * FPS)
        if n1 <= n0:
            continue
        schritt = max(3, (n1 - n0) // 20)
        nummern = list(range(n0, n1, schritt))
        fr_ = [bilder(n, 1, 1080, 1920)[0] for n in nummern]
        pfade = []
        for n, f in zip(nummern, fr_):
            pf = os.path.join(_tmp, f'{c["id"]}_{n}.png'); cv2.imwrite(pf, cv2.cvtColor(f, cv2.COLOR_RGB2BGR)); pfade.append(pf)
        aus = subprocess.run([_augen] + pfade, capture_output=True, text=True).stdout.splitlines()
        lm = {}
        for z in aus:
            p_ = z.split('\t')
            if len(p_) == 2 and p_[1] != 'none':
                lm[p_[0]] = tuple(map(float, p_[1].split()))
        schlimm = None
        for n, f, pf in zip(nummern, fr_, pfade):
            if pf not in lm:
                continue
            auge_oben, braue_oben, _pup = lm[pf]
            m = (np.abs(f[:900].astype(int) - np.array((253, 253, 253))).sum(2) < 18).astype(np.uint8)
            k, lab, st, _ = cv2.connectedComponentsWithStats(m)
            if k <= 1:
                continue
            i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); x, y_, w, h, a = st[i]
            if a < 20000 or y_ + h <= 0:
                continue
            grenze = min(braue_oben, auge_oben - 25)
            abstand = grenze - (y_ + h)
            if schlimm is None or abstand < schlimm[0]:
                schlimm = (abstand, n, y_ + h, auge_oben, braue_oben)
        if schlimm:
            ab, n, unten, ao, bo = schlimm
            flag = ab < 0
            print(f'  {c["id"]} {c["type"][:20]:20} engstes Bild {n}: Kartenunterkante {unten} px, Brauen ab {bo:.0f} px, Augen ab {ao:.0f} px, '
                  f'Abstand {ab:+.0f} px{"  BEFUND (Karte über Augen oder Brauen)" if flag else ""}')
            befund += flag
print(f'ERGEBNIS: {befund} BEFUNDE'); sys.exit(1 if befund else 0)
