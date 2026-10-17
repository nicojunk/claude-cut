#!/usr/bin/env python3
"""Build a HyperFrames composition that edits a talking-head take in the SMM Clipping style (measured on the reference reels of 14 to 16.10.2026, engine first built on a measured cutter reference in October 2026). Input: a plan JSON (references/plan-schema.md).
Channel specifics (colours, fonts, grid, extra CSS, compliance stop words) come from the channel profile (kanal.py).

Usage:  python3 baue_reel.py plan.json PROJECT_DIR
Writes PROJECT_DIR/index.html, copies fonts/sfx/media into the project, writes edl.json.

Every number below comes from references/style-spec.md (measured frame by frame on the
reference reel). Change a value only together with the spec and a re-measurement.
"""
import json, os, re, shutil, subprocess, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erklaerer, kanal
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FPS = 30
W, H = 1080, 1920

# ---------- measured style tokens (style-spec.md §2-§6) ----------
PAPER = '#F7F8F6'; GRID = 'transparent'; GRID_PERIOD = 60; GRID_X0 = 30; GRID_Y0 = 18
INK = '#1E2430'; RED = '#3FB8AF'; CARD = '#FFFFFF'
SIGNAL = '#3FB8B0'   # base of the 'signal' role (blood, danger); the reference channel: same look as the accent, other channels map it to red
SEAM_SOLID = 900; SEAM_FADE = 56                   # paper opaque to y=900, fades over 56 px
FACE_FULL_Y = 0.415; FACE_SPLIT_Y = 0.693          # face centre, share of frame height
CAP_FULL_TOP = 1035; CAP_SPLIT_CY = 833            # caption block top (full) / line centre (split)
FLASH_RISE, FLASH_FALL = 8, 10                     # frames before / after the peak frame
MINI_RISE, MINI_FALL = 3, 5
CAP_FADE = 2; CAP_DELAY = 0                        # caption word: fade starts on the word start (Abnahme R3 v1 15.10.: 1 Bild Verzug zu viel), 2-frame fade
PUNCH_FROM, PUNCH_TO, PUNCH_FR = 1.20, 1.04, 24    # after a flash
HERO_PUNCH_FROM, HERO_PUNCH_FR = 1.13, 20
PUNCH_SNAP = 0.4    # s: a hero punch this close after a cut moves onto the cut frame
BROLL_PUSH = 1.08
WHOOSH_LEAD = 0.27                                 # s, whoosh starts before a layout cut
SIL_DB, SIL_MIN, SIL_KEEP_PRE, SIL_KEEP_POST = -35, 0.12, 0.05, 0.05

def ds(t):  # Clip-Start bildgenau: 4 Nachkommastellen runden 7.56667 auf 7.5667 auf, der Clip kam 1 Bild zu spät (Abnahme R4 v6)
    return max(0.0, round(t * FPS) / FPS - 0.0005)


def dd(a, b):  # Clip-Dauer bildgenau, Ende knapp vor dem Bild round(b*FPS)
    return max(1, round(b * FPS) - round(a * FPS)) / FPS


def bildgenau(js_text):
    """Alle GSAP-Positionen, die auf ein Bild fallen (n/30), auf n/30 - 0,0005 setzen. Mit 4 Stellen gedruckt rundet jede dritte
    Bildzeit nach oben (1304/30 -> 43.4667) und feuert 1 Bild zu spät (Abnahme R3 v1 Runde 7b: Punch-in 43,467 s; Gedächtnis
    Punkt 3). Seit dem Einrasten auf Schnitte liegen fast alle Wechsel genau auf Bildern."""
    import re as _re
    def _p(m):
        t = float(m.group(1)); f = t * FPS; n = round(f)
        if t > 0 and -1e-9 <= f - n < 0.01:
            return '},' + f'{max(0.0, n / FPS - 0.0005):.4f}' + ')'
        return m.group(0)
    return _re.sub(r'\},(\d+\.\d+)\)', _p, js_text)

def fs(t):  # GSAP-Zeitpunkt knapp vor dem Bild: 7.6667 > 230/30 feuert sonst 1 Bild zu spät (Abnahme R4 v5: kopflose Bilder)
    return max(0.0, round(t * FPS) / FPS - 0.0005)


def fr(t):  # snap seconds to frame grid
    return round(round(t * FPS) / FPS, 4)

def esc(s):
    return html.escape(s, quote=True)

# ---------- 1 pause removal: keep ranges from audio silence ----------
def silences(src):
    # threshold follows the take's noise floor (validation 17.10.2026: floor -43.9 dB, peaks to -24 dB in pauses, the fixed
    # -35 dB found no pause longer than 0.45 s, the pause cap shortened nothing). the reference channel's takes (floor about -65 dB) keep -35.
    _db, _thr = huelle(src)
    sil_db = max(SIL_DB, round(_thr - 12 + 15, 1))
    out = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', src, '-af',
                          f'silencedetect=noise={sil_db}dB:d={SIL_MIN}', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r'silence_start: ([0-9.]+)', out)]
    en = [float(x) for x in re.findall(r'silence_end: ([0-9.]+)', out)]
    return list(zip(st, en))

PAUSE_CAP = None
NAEHTE = []      # Montage-Nähte im Take (plan 'naehte'); Abnahme R4 v5 15.10.2026: 1 Einzelbild zwischen Pausenschnitt und Naht

def huelle(src):
    """10-ms-Pegel des Takes und Sprachschwelle wie pruefe_ms.py (Grundrauschen p10 + 12 dB). R2 15.10.2026: silencedetect
    mit fester Schwelle -35 dB liegt ~30 dB über dem Grundrauschen, leise Wortenden ("besitzen.", "Kamera.") galten als Stille
    und wurden angeschnitten."""
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = len(a) // 160
    db = 20 * np.log10(np.sqrt(np.mean(a[:n * 160].reshape(n, 160) ** 2, axis=1) + 1e-12))
    return db, float(np.percentile(db[db > -80], 10) + 12)

def stimmhaft(src):
    """10-ms-Raster: True, wo die Stimme schwingt (normierte Autokorrelation > 0,45 bei 80 bis 400 Hz, Pegel > Schwelle + 6 dB).
    Abnahme R3 v1 Runde 7b: das Wortende aus der Ausrichtung schloss das Ausatmen nach "hinein" ein (200 ms), der Pop lag
    dadurch auf dem echten Wortende."""
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    db, thr = huelle(src)
    n = len(db); v = np.zeros(n, bool)
    for i in range(n):
        x = a[i * 160:i * 160 + 480]
        if len(x) < 480 or db[i] < thr + 6:
            continue
        x = x - x.mean(); e = float((x * x).sum())
        if e <= 0:
            continue
        r = max(float((x[:-L] * x[L:]).sum()) / e for L in range(40, 201, 2))
        v[i] = r > 0.45
    return v

LOKAL_DB = float(os.environ.get('SMM_LOKAL_DB', 99))   # aus (Runde 3: veränderte die freigegebenen Schnitte des Referenzkanals schon ab 18 dB); Pausengrund so viel unter dem der Aufnahme: dann gilt er am Schnitt
AUSKLANG = os.environ.get('SMM_AUSKLANG', '1') == '1'   # leisen Wortausklang vor einem Pausenschnitt behalten (Runde 3)
LV = LH = None
RUHE_RAND = 0.04   # Abstand eines Pausenschnitts zum letzten Sprachpegel davor und danach (pruefe_ms prüft ±15 ms)

def keep_ranges(src, dur, t0, t1, protect=(), vorlauf=()):
    """protect: [[s, e], ...] source seconds that are never cut (plan "keep_pauses"): quiet speech that silencedetect
    takes for a pause. Eval 08.10.2026: 0.17 s cut out of two quietly spoken words turned them into other words; only a
    transcript of the finished reel showed it."""
    cut = []
    db, thr = huelle(src)
    global LV, LH
    if AUSKLANG:
        import numpy as _np0
        _raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True, check=True).stdout
        _x = _np0.frombuffer(_raw, _np0.int16).astype(_np0.float32) / 32768; _n = len(_x) // 160; _hp = _np0.concatenate([[0.0], _np0.diff(_x)])
        LV = 20 * _np0.log10(_np0.sqrt(_np0.mean(_x[:_n * 160].reshape(_n, 160) ** 2, axis=1)) + 1e-9)
        LH = 20 * _np0.log10(_np0.sqrt(_np0.mean(_hp[:_n * 160].reshape(_n, 160) ** 2, axis=1)) + 1e-9)
    for a, b in silences(src):
        if PAUSE_CAP:
            if b - a <= PAUSE_CAP[0]:
                continue
            a2, b2 = a + PAUSE_CAP[1] / 2, b - PAUSE_CAP[1] / 2
        else:
            a2, b2 = a + SIL_KEEP_POST, b - SIL_KEEP_PRE
        # Schnittkanten nur dort, wo RUHE_RAND vor dem Schnittanfang und RUHE_RAND nach dem Schnittende ruhig sind
        # (unter Grundrauschen + 12 dB - 2 dB, wie schnitte_vorab.py). Kurze Geräuschspitzen mitten in der Pause bleiben
        # im behaltenen Teil oder fallen weg, sie verhindern den Schnitt nicht (R3: 3,2 s Pause nach "Hör mal hin!").
        # Runde 3 (17.10.2026): ein leiser Wortausklang bei -49 dB galt als Stille (Pausengrund dort -65 dB, Schwelle der ganzen
        # Aufnahme viel höher), 45 ms fielen weg (unabhängige Abnahme Fall 2).
        # Nur in den 15 ms direkt am Schnitt (dem Fenster der Abnahme) gilt zusätzlich der Grund dieser Pause + 12 dB; über die
        # 40 ms RUHE_RAND bleibt die Schwelle der ganzen Aufnahme (sonst wurden die freigegebenen Pausen des Referenzkanals länger).
        import numpy as _np
        _seg = db[max(0, int(a * 100)):int(b * 100) + 1]
        _lf = float(_np.percentile(_seg, 10)) if len(_seg) >= 5 else 0.0
        _thr_l = _lf + 12 if len(_seg) >= 5 and _lf < thr - 12 - LOKAL_DB else thr
        ruhig = lambda x0, x1, _t=thr: bool((db[max(0, int(round(x0 * 100))):int(round(x1 * 100)) + 1] < _t - 2).all())
        while a2 < b2 and not (ruhig(a2 - RUHE_RAND, a2 + 0.01) and ruhig(a2 - 0.015, a2 + 0.01, _thr_l)):
            a2 = round(a2 + 0.01, 3)
        if AUSKLANG:
            # Runde 3 (17.10.2026): der leise Ausklang eines Worts bleibt ganz drin. Vom letzten deutlichen Laut vor dem Schnitt
            # (über der Sprachschwelle) läuft der Ausklang weiter, solange Pegel oder Hochband 10 dB über dem Grund der 2 s um
            # die Stelle liegen (Lücken bis 30 ms); der Schnitt beginnt höchstens 100 ms später, 20 ms nach dem Ausklang.
            _k = int(round(a2 * 100))
            _e = next((i for i in range(_k, max(0, _k - 60), -1) if i < len(db) and db[i] > thr), None)
            if _e is not None:
                _k0, _k1 = max(0, _e - 100), min(len(LV), _e + 100)
                _fb, _fh = float(_np.percentile(LV[_k0:_k1], 10)), float(_np.percentile(LH[_k0:_k1], 10))
                _i, _luecke, _ende = _e, 0, _e
                while _i < min(len(LV), _e + 30) and _luecke < 3:
                    if LV[_i] > _fb + 10 or LH[_i] > _fh + 10:
                        _ende, _luecke = _i, 0
                    else:
                        _luecke += 1
                    _i += 1
                _neu = min(a2 + 0.1, (_ende + 1) / 100 + 0.02)
                if _neu > a2 and _neu < b2 - 2 / FPS:
                    a2 = round(_neu, 3)
        while b2 > a2 and not (ruhig(b2 - 0.01, b2 + RUHE_RAND) and ruhig(b2 - 0.01, b2 + 0.015, _thr_l)):
            b2 = round(b2 - 0.01, 3)
        # Runde 4 (17.10.2026): vor dem ersten Wort eines Abschnitts mit Blitz bleiben 220 ms. Der Blitz liegt auf diesem Schnitt;
        # Untertitel warten seine hellen Bilder ab (4 Bilder nach der Spitze), sonst kam das Wort 145 bis 229 ms zu spät (Abnahme Fall 2)
        for v_ in vorlauf:
            if a2 < v_ <= b2 + 0.25:
                b2 = min(b2, round(v_ - 0.22, 3))
        for s_ in NAEHTE:                          # Schnitt auf eine nahe Naht ziehen, sonst bleibt 1 Bild des Vorstücks stehen
            if b2 < s_ <= b2 + 0.12 and s_ < b:
                b2 = s_
            if a2 - 0.12 <= s_ < a2 and s_ > a:
                a2 = s_
        if any(a2 < pe and b2 > ps for ps, pe in protect):
            continue
        if b2 - a2 >= 2 / FPS:
            cut.append((a2, b2))
    ranges, cur = [], t0
    for a, b in cut:
        if b <= t0 or a >= t1:
            continue
        a, b = max(a, t0), min(b, t1)
        if a > cur:
            ranges.append((cur, a))
        cur = max(cur, b)
    if cur < t1:
        ranges.append((cur, t1))
    # frame-snap and drop slivers shorter than 3 frames
    out = []
    for a, b in ranges:
        a, b = fr(a), fr(b)
        if b - a >= 3 / FPS:
            out.append((a, b))
    return out

def schnitt_blenden(datei, table):
    """Each <video> plays its range of the take with its sound; at a pause cut two ranges meet without a crossfade. In a quiet
    room that is inaudible; in room noise of -40 dB it clicks (round 2 case 2: 11 and 15 dB high-pass spikes at 37.833 and
    51.467 s). The render's copy of the take gets a 8 ms ramp to zero before every range end and after every range start,
    with 2 to 3 ms of zero around the edge; the ramps lie inside the 40 ms of quiet every cut keeps (RUHE_RAND). The video
    stream is copied unchanged; the measurements of the build keep using the original take."""
    import numpy as np
    if len(table) < 2:
        return
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(datei), '-vn', '-f', 'f32le', '-ac', '2', '-ar', '48000', '-'],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    sr, g = 48000, np.ones(len(a), np.float32)
    ramp = lambda n: (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))).astype(np.float32)   # 0 -> 1
    for k, (fa, fb, _) in enumerate(table):
        s0, e0 = fa / FPS, fb / FPS
        if k > 0:                                     # range start: zero 3 ms before to 2 ms after, ramp up over 8 ms
            i0, i1, i2 = int((s0 - 0.003) * sr), int((s0 + 0.002) * sr), int((s0 + 0.010) * sr)
            g[max(0, i0):i1] = 0; g[i1:i2] = np.minimum(g[i1:i2], ramp(i2 - i1)[:len(g[i1:i2])])
        if k < len(table) - 1:                        # range end: ramp down over 8 ms, zero 2 ms before to 3 ms after
            j0, j1, j2 = int((e0 - 0.010) * sr), int((e0 - 0.002) * sr), int((e0 + 0.003) * sr)
            g[j0:j1] = np.minimum(g[j0:j1], ramp(j1 - j0)[::-1][:len(g[j0:j1])]); g[j1:min(len(g), j2)] = 0
    a *= g[:, None]
    tmp = Path(datei).with_suffix('.blend.wav'); neu = Path(datei).with_suffix('.blend.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(sr), '-ac', '2', '-i', '-', str(tmp)], input=a.tobytes(), check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(datei), '-i', str(tmp), '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '256k', '-ar', str(sr), '-movflags', '+faststart', str(neu)], check=True)
    tmp.unlink(); neu.replace(datei)


def mapper(ranges):
    # integer frames end to end, so consecutive clips touch exactly (no 1-frame gaps from rounding)
    acc, table = 0, []
    for a, b in ranges:
        fa, fb = round(a * FPS), round(b * FPS)
        table.append((fa, fb, acc)); acc += fb - fa
    def m(t):
        f = round(t * FPS)
        for fa, fb, o in table:
            if f < fa:
                return o / FPS
            if f <= fb:
                return (o + f - fa) / FPS
        return acc / FPS
    return m, acc / FPS, table

# ---------- 2 speaker placement from face boxes ----------
def face_y(src):
    tsv = Path(src).with_suffix('.faces.tsv'); key = Path(src).with_suffix('.faces.key')
    # cache only for the same take content (14.10.2026: a re-cut take kept the face track of the old montage)
    if tsv.exists() and (not key.exists() or key.read_text().strip() != kanal.datei_schluessel(src)):
        tsv.unlink()
    if not tsv.exists():
        tmp = Path(src).with_suffix('.facesamples'); tmp.mkdir(exist_ok=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-vf', "select='not(mod(n\\,10))',scale=540:960",
                        '-fps_mode', 'vfr', '-q:v', '3', str(tmp / 'a%03d.jpg')], check=True)
        res = subprocess.run([str(SKILL / 'scripts' / 'bin' / 'gesicht')] + sorted(str(p) for p in tmp.glob('*.jpg')),
                             capture_output=True, text=True).stdout
        tsv.write_text(res); key.write_text(kanal.datei_schluessel(src))
    ys, ws = [], []
    for line in tsv.read_text().splitlines():
        p = line.split('\t')
        if len(p) < 2 or p[1] == 'none':
            continue
        x, y, w, h = map(float, p[1].split())
        ys.append(1 - (y + h / 2)); ws.append(w)
    hs = []
    for line in tsv.read_text().splitlines():
        p = line.split('\t')
        if len(p) >= 2 and p[1] != 'none':
            hs.append(float(p[1].split()[3]))
    ys.sort(); ws.sort(); hs.sort()
    return ys[len(ys) // 2], ws[len(ws) // 2], hs[len(hs) // 2]

def face_track(src):
    """source time in s -> (centre y, height) of the face, from the samples every 10 frames written by face_y()"""
    tr = {}
    for line in Path(src).with_suffix('.faces.tsv').read_text().splitlines():
        p = line.split('\t')
        if len(p) < 2 or p[1] == 'none': continue
        k = int(re.search(r'a(\d+)\.jpg', p[0]).group(1)) - 1
        x, y, w, h = map(float, p[1].split()); tr[k * 10 / FPS] = (1 - (y + h / 2), h)
    return tr

_frame_cache = {}
def contrast_at(src, t, top, full_dy, scale0, height=190):
    """WCAG contrast of white text against the take in the caption block (x 200..880, top..top+height in output px)."""
    key = round(t, 1)
    if key not in _frame_cache:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{key:.2f}', '-i', src, '-frames:v', '1', '-vf', 'scale=270:480',
                              '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
        import numpy as np
        _frame_cache[key] = np.frombuffer(raw, np.uint8).reshape(480, 270, 3).astype(float) / 255 if len(raw) == 480 * 270 * 3 else None
    A = _frame_cache[key]
    if A is None: return 9.9
    import numpy as np
    oy = FACE_FULL_Y * H
    ys = [(y - full_dy - oy) / scale0 + oy for y in (top, top + height)]
    xs = [540 + (x - 540) / scale0 for x in (300, 780)]
    r0, r1 = [int(max(0, min(479, y / 4))) for y in ys]; c0, c1 = [int(max(0, min(269, x / 4))) for x in xs]
    B = A[r0:r1 + 1, c0:c1 + 1].reshape(-1, 3)
    if len(B) == 0: return 9.9
    lin = np.where(B <= 0.04045, B / 12.92, ((B + 0.055) / 1.055) ** 2.4) @ np.array([0.2126, 0.7152, 0.0722])
    return 1.05 / (float(np.median(lin)) + 0.05)

# ---------- 3 caption rendering ----------
def cap_html(group, words, mode, cid):
    """group: {"w":[i..], "roles":[...]} roles: base|hero|accent|key. Returns html and list of (span_id, word_index)."""
    spans, items = [], []
    for k, (wi, role) in enumerate(zip(group['w'], group['roles'])):
        sid = f'{cid}w{k}'
        items.append((sid, wi, role))
    def span(sid, wi, role):
        t = words[wi]['t']; st = ''
        if role in ('hero', 'key'):   # long words shrink to fit 960 px (Montserrat 800 ~0.62 em per glyph)
            mx, k = {('full', 'hero'): (112, .62), ('full', 'key'): (92, .64), ('split', 'hero'): (76, .62), ('split', 'key'): (70, .64)}[(mode, role)]
            fs = min(mx, int(900 / (k * max(1, len(t)))))
            if fs < mx: st = f' style="font-size:{fs}px"'
        return f'<span id="{sid}" class="w {role}"{st}>{esc(t)}</span>'
    if mode == 'split':
        inner = ' '.join(span(*it) for it in items)
        return f'<div class="cap split"><div class="line">{inner}</div></div>', items
    hero_k = next((k for k, it in enumerate(items) if it[2] in ('hero', 'key')), None)
    if hero_k is None:
        # no hero: up to 2 lines, split before the first accent run if any
        acc_k = next((k for k, it in enumerate(items) if it[2] == 'accent' and k > 0), None)
        l1 = items[:acc_k] if acc_k else items
        l2 = items[acc_k:] if acc_k else []
        lines = [' '.join(span(*it) for it in l1)] + ([' '.join(span(*it) for it in l2)] if l2 else [])
        return '<div class="cap full">' + ''.join(f'<div class="line">{l}</div>' for l in lines) + '</div>', items
    before, hero, after = items[:hero_k], items[hero_k], items[hero_k + 1:]
    out = '<div class="cap full">'
    if before:
        out += '<div class="line pre">' + ' '.join(span(*it) for it in before) + '</div>'
    out += '<div class="line herol">' + span(*hero) + '</div>'
    if after:
        out += '<div class="line post">' + ' '.join(span(*it) for it in after) + '</div>'
    return out + '</div>', items

# ---------- 4 card components (each returns html, list of timeline js lines) ----------
ICONS = {
    'warn': f'<svg viewBox="0 0 24 24" class="ico"><path d="M12 2 1 21h22L12 2z" fill="{RED}"/><rect x="11" y="8" width="2" height="7" fill="#fff"/><rect x="11" y="16.5" width="2" height="2" fill="#fff"/></svg>',
    'check': f'<svg viewBox="0 0 24 24" class="ico"><circle cx="12" cy="12" r="11" fill="{RED}"/><path d="M6.5 12.5l3.5 3.5 7.5-8" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round"/></svg>',
    'up': f'<svg viewBox="0 0 24 24" class="ico"><rect x="1" y="1" width="22" height="22" rx="6" fill="{RED}"/><path d="M12 18V7M7 11l5-5 5 5" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round"/></svg>',
    'cross': f'<svg viewBox="0 0 24 24" class="ico"><circle cx="12" cy="12" r="11" fill="{RED}"/><rect x="10" y="5.5" width="4" height="13" rx="1" fill="#fff"/><rect x="5.5" y="10" width="13" height="4" rx="1" fill="#fff"/></svg>',
    'dot': f'<svg viewBox="0 0 24 24" class="ico"><circle cx="12" cy="12" r="6" fill="{INK}"/></svg>',
    'heart': f'<svg viewBox="0 0 24 24" class="ico"><path d="M12 21s-8-5.2-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.8-8 11-8 11z" fill="{RED}"/></svg>',
    'germ': f'<svg viewBox="0 0 24 24" class="ico"><circle cx="12" cy="12" r="6" fill="{RED}"/><g stroke="{RED}" stroke-width="2"><path d="M12 2v4M12 18v4M2 12h4M18 12h4M5 5l3 3M16 16l3 3M19 5l-3 3M8 16l-3 3"/></g></svg>',
    'pore': f'<svg viewBox="0 0 24 24" class="ico"><circle cx="12" cy="12" r="9" fill="none" stroke="{INK}" stroke-width="2.4"/><circle cx="12" cy="12" r="3.6" fill="{INK}"/></svg>',
    'drop': f'<svg viewBox="0 0 24 24" class="ico"><path d="M12 2C9 7 5 10.5 5 15a7 7 0 0 0 14 0c0-4.5-4-8-7-13z" fill="{RED}"/></svg>',
}

def ecg_path():
    """PQRST trace in a 430 x 300 box, baseline y 200, R spike to y 60, S dip to y 238 (reference monitor, frame 690)."""
    d, x = ['M 0 200'], 0
    for _ in range(3):
        d += [f'L {x+40} 200', f'Q {x+52} 186 {x+64} 200', f'L {x+74} 200', f'L {x+80} 214', f'L {x+88} 60',
              f'L {x+96} 238', f'L {x+104} 200', f'L {x+120} 200', f'Q {x+136} 166 {x+152} 200', f'L {x+170} 200']
        x += 170
    return ' '.join(d)

def mix_tone(f):
    """number colour during a rise, measured frames 630-650: green, yellow-green, yellow, orange, red."""
    stops = [(0, (68, 231, 134)), (.3, (123, 237, 69)), (.5, (244, 242, 69)), (.7, (250, 123, 69)), (1, (254, 82, 72))]
    for (fa, ca), (fb, cb) in zip(stops, stops[1:]):
        if f <= fb:
            k = (f - fa) / (fb - fa); return '#%02X%02X%02X' % tuple(round(a + (b - a) * k) for a, b in zip(ca, cb))
    return '#FE5248'

# glossy heart of the counter card: 135 x 116 px at (232, 216) in the reference (frame 1020)
HEART_BIG = (f'<svg viewBox="0 0 24 24" preserveAspectRatio="none"><path d="M12 21s-8-5.2-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.8-8 11-8 11z" fill="{RED}"/>'
             '<ellipse cx="7.6" cy="8.6" rx="1.5" ry="1" fill="#fff" opacity=".55" transform="rotate(-30 7.6 8.6)"/></svg>')

def pop6(sel, t):
    # measured: frame0 opacity ~.4 scale ~1.0 -> frame2 scale 1.037 -> settle 1.0 at frame 6
    # reference scale per frame (template match, hook + counter card): 1.0125, 1.035, 1.0375 (peak), 1.03, 1.02, 1.0025, 1.0 (settled after 5-6 frames)
    # hidden from time 0 until its entrance, so the first frame of the clip never shows the card at rest
    return (f'tl.set("{sel}",{{scale:0.97,opacity:0}},0);'
            f'tl.fromTo("{sel}",{{opacity:0}},{{opacity:1,duration:{2/FPS:.4f},ease:"power1.out",immediateRender:false}},{t:.4f});'
            f'tl.fromTo("{sel}",{{scale:0.97}},{{scale:1.0375,duration:{3/FPS:.4f},ease:"power2.out",immediateRender:false}},{t:.4f});'
            f'tl.to("{sel}",{{scale:1,duration:{4/FPS:.4f},ease:"sine.inOut"}},{t+3/FPS:.4f});')

def pop2(sel, t):
    return (f'tl.set("{sel}",{{scale:0.9,opacity:0}},0);'
            f'tl.fromTo("{sel}",{{scale:0.9,opacity:0}},{{scale:1,opacity:1,duration:{2/FPS:.4f},ease:"back.out(2)",immediateRender:false}},{t:.4f});')

SFX_EVENTS = []   # (name, time, volume) collected from explainers; very soft (the user 08.10.2026: "der Ton ist zu viel")

def card(c, cid, T):
    """c: card dict from plan; T(word_index) -> output seconds. Returns (html, js)."""
    typ, js = c['type'], []
    t0 = T(c['at']) + CAP_DELAY / FPS
    zone = c.get('zone', 'top')           # top (on video, full mode) | paper (split mode)
    cls = f'card-wrap z-{zone}'
    if c.get('top') is not None and zone == 'top':   # top-zone cards may sit 150 to 170 px from the top (reference range)
        cls += f'" style="top:{max(150, min(170, int(c["top"])))}px'
    if typ == 'title':                     # hook card: icon + bold line, italic sub line
        h = (f'<div class="{cls}"><div id="{cid}" class="card title"><div class="t1">{ICONS[c.get("icon","warn")]}'
             f'<b class="num">{esc(c.get("num",""))}</b><b>{esc(c["text"])}</b></div>'
             + (f'<div class="t2">{esc(c["sub"])}</div>' if c.get('sub') else '') + '</div></div>')
        js.append(pop6(f'#{cid}', t0))
        if c.get('sub') and c.get('sub_at') is not None:
            js.append(f'tl.set("#{cid} .t2",{{opacity:0}},0);')
            js.append(f'tl.fromTo("#{cid} .t2",{{opacity:0}},{{opacity:1,duration:{3/FPS:.4f}}},{T(c["sub_at"]):.4f});')
        return h, js
    if typ == 'chip':                      # section chip: red number circle, pill grows over 8 frames
        h = (f'<div class="{cls}"><div id="{cid}" class="chip"><span class="ring" id="{cid}g"></span><span class="n">{esc(str(c["num"]))}</span>'
             f'<span class="pill"><span class="txt">{esc(c["text"])}</span></span></div></div>')
        js.append(f'tl.set("#{cid} .n",{{scale:0,opacity:0}},0);tl.set("#{cid} .pill",{{clipPath:"inset(-40px 60% -40px 0 round 40px)"}},0);')
        js.append(f'tl.fromTo("#{cid} .n",{{scale:0,opacity:0}},{{scale:1,opacity:1,duration:{3/FPS:.4f},ease:"back.out(2)"}},{t0:.4f});')
        js.append(f'tl.fromTo("#{cid}g",{{scale:1,opacity:0.5}},{{scale:1.32,opacity:0,duration:{18/FPS:.4f},ease:"power1.out",immediateRender:false}},{t0+3/FPS:.4f});')
        js.append(f'tl.fromTo("#{cid} .pill",{{clipPath:"inset(-40px 60% -40px 0 round 40px)"}},{{clipPath:"inset(-40px 0% -40px 0 round 40px)",duration:{8/FPS:.4f},ease:"power1.out"}},{t0+6/FPS:.4f});')
        return h, js
    if typ == 'list':                      # header + rows that pop in at their anchor words
        rows = ''.join(f'<div class="row" id="{cid}r{k}"><span class="ib">{ICONS.get(r.get("icon","dot"),"")}</span><span>{esc(r["text"])}</span>'
                       + (f'<em class="lab" id="{cid}l{k}">{esc(r["label"])}</em>' if r.get('label') else '') + '</div>'
                       for k, r in enumerate(c['rows']))
        foot = f'<em class="lab foot" id="{cid}f">{esc(c["foot"])}</em>' if c.get('foot') else ''
        dense = ' dense' if len(c['rows']) >= 4 else ''
        h = (f'<div class="{cls}"><div id="{cid}" class="card list{dense}"><div class="hd">{ICONS.get(c.get("icon","warn"),"")}'
             f'<b>{esc(c["title"])}</b></div>{rows}{foot}</div></div>')
        if c.get('foot'):
            js.append(f'tl.set("#{cid}f",{{opacity:0}},0);'); js.append(pop2(f'#{cid}f', T(c['foot_at']) + CAP_DELAY / FPS))
        js.append(pop6(f'#{cid}', t0))
        for k, r in enumerate(c['rows']):
            # the card grows with every row (reference frames 790 to 880): a row takes no space until its word
            tr_ = T(r['at']) + CAP_DELAY / FPS
            js.append(f'tl.set("#{cid}r{k}",{{opacity:0,display:"none"}},0);tl.set("#{cid}r{k}",{{display:"flex"}},{tr_:.4f});')
            js.append(pop2(f'#{cid}r{k}', tr_))
            if r.get('label'):
                js.append(f'tl.set("#{cid}l{k}",{{opacity:0}},0);')
                js.append(pop2(f'#{cid}l{k}', T(r.get('label_at', r['at'])) + CAP_DELAY / FPS))
        return h, js
    if typ == 'flow':                      # nodes connected by arrows, each node at its anchor word
        parts = []
        for k, n in enumerate(c['nodes']):
            if k:
                parts.append(f'<div class="arrow" id="{cid}a{k}"><span>&#8595;</span><em>{esc(n.get("verb",""))}</em></div>')
            cl = 'dark' if n.get('dark') else ('hot' if n.get('hot') else '')
            badge = f'<span class="badge">{ICONS["up"]}</span>' if n.get('hot') else ''
            icon = '' if n.get('hot') else ICONS.get(n.get('icon', ''), '')
            parts.append(f'<div class="node {cl}" id="{cid}n{k}">{icon}<b>{esc(n["text"])}</b>{badge}</div>')
        h = f'<div class="{cls}"><div id="{cid}" class="flow">{"".join(parts)}</div></div>'
        for k, n in enumerate(c['nodes']):
            js.append(f'tl.set("#{cid}n{k}",{{opacity:0}},0);')
            js.append(pop2(f'#{cid}n{k}', T(n['at']) + CAP_DELAY / FPS))
            if k:
                js.append(f'tl.set("#{cid}a{k}",{{opacity:0}},0);')
                js.append(f'tl.fromTo("#{cid}a{k}",{{opacity:0,y:-10}},{{opacity:1,y:0,duration:{4/FPS:.4f}}},{T(n["at"]) - 4/FPS:.4f});')
        return h, js
    if typ == 'image':                     # rounded image card with a red label
        src = c['src']
        sz = f' style="width:{c["img_w"]}px;height:{c["img_h"]}px"' if c.get('img_w') else ''
        h = (f'<div class="{cls}"><div id="{cid}" class="card image"><img src="{esc(src)}" alt=""{sz}>'
             + (f'<em class="lab top" id="{cid}l">{esc(c["label"])}</em>' if c.get('label') else '') + '</div></div>')
        js.append(pop6(f'#{cid}', t0))
        if c.get('label'):
            js.append(f'tl.set("#{cid}l",{{opacity:0}},0);')
            js.append(pop2(f'#{cid}l', T(c.get('label_at', c['at'])) + CAP_DELAY / FPS))
        return h, js
    if typ == 'pills':                     # row of pills + optional italic sub pill
        ps = ''.join(f'<span class="p" id="{cid}p{k}"><i></i>{esc(p["text"])}</span>' for k, p in enumerate(c['pills']))
        sub = f'<div class="sub" id="{cid}s">{esc(c["sub"])}</div>' if c.get('sub') else ''
        h = f'<div class="{cls}"><div id="{cid}" class="pills"><div class="pr">{ps}</div>{sub}</div></div>'
        for k, p in enumerate(c['pills']):
            js.append(f'tl.set("#{cid}p{k}",{{opacity:0}},0);'); js.append(pop2(f'#{cid}p{k}', T(p['at']) + CAP_DELAY / FPS))
        if c.get('sub'):
            js.append(f'tl.set("#{cid}s",{{opacity:0}},0);'); js.append(pop2(f'#{cid}s', T(c['sub_at']) + CAP_DELAY / FPS))
        return h, js
    if typ in erklaerer.TYPES:             # explainers at drop-off moments (references/erklaerer.md)
        if not c.get('satz'):
            raise SystemExit(f'plan error: explainer {cid} ({typ}) needs "satz": the take sentence it shows (and "quelle" for any mechanism the speaker does not say there)')
        return erklaerer.TYPES[typ](c, cid, T, {'RED': RED, 'SIGNAL': SIGNAL, 'INK': INK, 'CAP_DELAY': CAP_DELAY, 'pop6': pop6, 'pop2': pop2,
                                                'sfx': None if c.get('ton') is False else SFX_EVENTS, 'icons': ICONS})   # 'ton': False im Plan: Karte ohne Ton (R1 Runde 8: Pop überdeckte "Auge")
    if typ == 'bars':                      # heading on the paper + bar chart card (reference frames 1423-1632)
        vals = [b['value'] for b in c['bars']]; mx = max(vals)
        n = len(c['bars']); x0 = 440 - (n * 168 + (n - 1) * 102) // 2      # group centred in the card (card x 100..980)
        bars, labs = [], []
        for k, b in enumerate(c['bars']):
            x = x0 + k * 270; hgt = round(240 * b['value'] / mx)
            tone = b.get('tone', 'ink' if k else 'grey')
            pill = (f'<em class="bpill" id="{cid}p{k}" style="left:{x-58}px;top:{360-hgt-26-61}px">{esc(b["pill"])}</em>' if b.get('pill') else '')
            bars.append(f'<div class="bar {tone}" id="{cid}b{k}" style="left:{x}px;height:{hgt}px"></div>{pill}')
            labs.append(f'<b class="blab" id="{cid}t{k}" style="left:{x-51}px">{esc(b["text"])}</b>')
        hd = c.get('heading', ['', c.get('title', '')])
        h = (f'<div class="card-wrap z-abs"><div id="{cid}" class="barsw"><div class="bhead"><span class="r">{esc(hd[0])}</span>{esc(hd[1])}</div>'
             f'<div class="card bcard"><div class="bline"></div>{"".join(bars)}{"".join(labs)}</div></div></div>')
        js.append(pop6(f'#{cid}', t0))
        for k, b in enumerate(c['bars']):
            tb = T(b['at']) + CAP_DELAY / FPS
            # measured: 0 -> 105.4 % in 9 frames (ease out), settle to 100 % in 6 frames, grows from the baseline
            js.append(f'tl.set("#{cid}b{k}",{{scaleY:0,transformOrigin:"50% 100%"}},0);tl.set("#{cid}t{k}",{{opacity:0}},0);')
            js.append(f'tl.to("#{cid}b{k}",{{scaleY:1.054,duration:{9/FPS:.4f},ease:"power2.out"}},{tb:.4f});'
                      f'tl.to("#{cid}b{k}",{{scaleY:1,duration:{6/FPS:.4f},ease:"sine.inOut"}},{tb+9/FPS:.4f});')
            js.append(pop2(f'#{cid}t{k}', tb))
            if b.get('pill'):
                js.append(pop2(f'#{cid}p{k}', T(b.get('pill_at', b['at'])) + CAP_DELAY / FPS))
        return h, js
    if typ == 'monitor':                   # dark vital-sign monitor in a white bezel (reference frames 586-726)
        tones = {'green': ('#62CC90', '#44E786', '#77A88C'), 'red': ('#E25E57', '#FE5248', '#E19690')}
        tone0 = c.get('tone', 'green')
        ecg = ecg_path()
        v0 = int(c['value']); rise = c.get('rise')
        nums = [f'<b class="mnum" id="{cid}v{v0}" style="color:{tones[tone0][1]}">{v0}</b>']
        seq = []
        if rise:
            v1 = int(rise['to']); nfr = rise.get('frames', 20); tr = T(rise['at']) + CAP_DELAY / FPS
            steps = list(range(v0 + 1, v1 + 1)) if v1 > v0 else list(range(v0 - 1, v1 - 1, -1))
            for i, v in enumerate(steps):
                f = (i + 1) / len(steps)
                col = mix_tone(f)          # measured: green -> yellow (40 %) -> orange -> red over the rise
                nums.append(f'<b class="mnum" id="{cid}v{v}" style="color:{col}">{v}</b>')
                seq.append((v, tr + (i + 1) * nfr / len(steps) / FPS))
        unit = c.get('unit', 'BPM'); icon = ICONS.get(c.get('icon', 'heart'), '')
        tab = f'<em class="mtab" id="{cid}tab">{esc(c["tab"])}</em>' if c.get('tab') else ''
        lab = f'<em class="lab mlab" id="{cid}lab">{esc(c["label"])}</em>' if c.get('label') else ''
        h = (f'<div class="card-wrap z-abs"><div id="{cid}" class="card mon">{tab}<div class="mpanel">'
             f'<svg class="ecg" viewBox="0 0 430 300"><path id="{cid}eg" d="{ecg}" pathLength="1000" style="stroke:{tones[tone0][0]};color:{tones[tone0][0]}"/>'
             f'<path id="{cid}er" d="{ecg}" pathLength="1000" style="stroke:{tones["red"][0]};color:{tones["red"][0]};opacity:0"/></svg><i class="mdiv"></i>'
             f'<div class="mhead">{icon}<span id="{cid}u" style="color:{tones[tone0][2]}">{esc(unit)}</span><i class="mdot"></i></div>'
             f'<div class="mnums">{"".join(nums)}</div><svg class="marrow" id="{cid}ar" viewBox="0 0 50 56"><path d="M25 52V8M8 24 25 6l17 18" /></svg>'
             f'</div>{lab}</div></div>')
        js.append(pop6(f'#{cid}', t0))
        js.append(f'tl.set("#{cid} .mnum",{{opacity:0}},0);tl.set("#{cid}v{v0}",{{opacity:1}},0);tl.set("#{cid}ar",{{opacity:0}},0);')
        # the trace sweeps left to right once per 0.9 s while the card is on screen
        dur = 12.0
        for pid in ('eg', 'er'):
            js.append(f'tl.fromTo("#{cid}{pid}",{{strokeDashoffset:1000}},{{strokeDashoffset:0,duration:0.9,ease:"none",repeat:{int(dur/0.9)}}},{t0:.4f});')
        prev = v0
        for v, tv in seq:
            js.append(f'tl.set("#{cid}v{prev}",{{opacity:0}},{tv:.4f});tl.set("#{cid}v{v}",{{opacity:1}},{tv:.4f});'); prev = v
        if rise:
            t_mid = seq[len(seq) // 2][1]
            js.append(f'tl.to("#{cid}eg",{{opacity:0,duration:{6/FPS:.4f}}},{t_mid:.4f});tl.to("#{cid}er",{{opacity:1,duration:{6/FPS:.4f}}},{t_mid:.4f});')
            js.append(f'tl.to("#{cid}u",{{color:"{tones["red"][2]}",duration:{6/FPS:.4f}}},{t_mid:.4f});')
            if v1 > v0:
                js.append(f'tl.set("#{cid}ar",{{opacity:1}},{seq[0][1]:.4f});')
        if c.get('tab'):   # measured: small grey tab at +0, full dark tab 15 frames later
            ta = T(c.get('tab_at', c['at'])) + CAP_DELAY / FPS
            js.append(f'tl.set("#{cid}tab",{{opacity:0,scale:0.6}},0);tl.to("#{cid}tab",{{opacity:1,scale:1,duration:{4/FPS:.4f},ease:"back.out(2)"}},{ta:.4f});')
        if c.get('label'):
            js.append(f'tl.set("#{cid}lab",{{opacity:0}},0);'); js.append(pop2(f'#{cid}lab', T(c['label_at']) + CAP_DELAY / FPS))
        return h, js
    if typ == 'counter':                   # white card on the video: icon, grey label, big counter that steps up (reference 940-1026)
        icon = HEART_BIG if c.get('icon', 'heart') == 'heart' else ICONS.get(c['icon'], '')
        steps = c['steps']
        fit = lambda t: '' if len(t) <= 5 else f' style="font-size:{int(470 / (0.68 * len(t)))}px;top:{int((150 - 470 / (0.68 * len(t))) * 0.75)}px"'
        vals = ''.join(f'<b class="cval {s_.get("tone","red")}" id="{cid}s{k}"{fit(s_["text"])}>{esc(s_["text"])}</b>' for k, s_ in enumerate(steps))
        h = (f'<div class="card-wrap z-abs"><div id="{cid}" class="card cnt"><div class="cico">{icon}<span class="ring" id="{cid}g"></span></div>'
             f'<span class="clab">{esc(c["label"])}</span><div class="cvals">{vals}</div></div></div>')
        js.append(pop6(f'#{cid}', t0))
        js.append(f'tl.set("#{cid} .cval",{{opacity:0,yPercent:60}},0);tl.set("#{cid}s0",{{opacity:1,yPercent:0}},0);')
        for k, s_ in enumerate(steps[1:], 1):
            ts = T(s_['at']) + CAP_DELAY / FPS
            # measured: new value rolls in from below inside the line (4 frames), a ring pulses around the icon
            js.append(f'tl.to("#{cid}s{k-1}",{{opacity:0,yPercent:-60,duration:{3/FPS:.4f}}},{ts:.4f});'
                      f'tl.to("#{cid}s{k}",{{opacity:1,yPercent:0,duration:{4/FPS:.4f},ease:"power2.out"}},{ts:.4f});')
            js.append(f'tl.fromTo("#{cid}g",{{scale:1,opacity:0.6}},{{scale:1.35,opacity:0,duration:{18/FPS:.4f},ease:"power1.out",immediateRender:false}},{ts:.4f});')
        js.append(f'tl.set("#{cid}g",{{opacity:0}},0);')
        return h, js
    if typ == 'keyword':                   # CTA: "Kommentiere" + keyword in red box
        sub = c.get('sub')   # Datumszeile unter dem Aufruf (Kallaway-10 Maßnahme 2, 15.10.2026)
        if sub:
            h = (f'<div class="{cls}"><div id="{cid}" class="card kw kwm"><div class="kwrow"><span>{esc(c.get("lead","Kommentiere"))}</span>'
                 f'<b class="key">{esc(c["keyword"])}</b></div><div class="kwsub">{esc(sub)}</div></div></div>')
        else:
            h = (f'<div class="{cls}"><div id="{cid}" class="card kw"><span>{esc(c.get("lead","Kommentiere"))}</span>'
                 f'<b class="key">{esc(c["keyword"])}</b></div></div>')
        # auf einem Zustandswechsel beginnt die Einblendung 1 Bild vorher wie bei den Erklärkarten: im Wechselbild steht die Karte
        # halb, danach ganz (Runde 7b R1: 1 Bild Sprecherin ohne Karte zwischen Splitscreen und Karte, Hin-und-zurück-Sprung)
        js.append(pop6(f'#{cid}', max(0.0, t0 - 1 / FPS) if c.get('_am_wechsel') else t0)); return h, js
    raise ValueError(f'unknown card type {typ}')

NICHT_ANZEIGE = {'type', 'zone', 'src', 'quelle', 'satz', 'icon', 'tone', 'live', 'frames', 'img_w', 'img_h', 'zoom_box', 'zoom_glass',
                 'zoom_src', 'top', 'cap_top', 'ton', 'ab_null', 'until', 'at', 'dopamin', 'absprung', 'land_delay', 'hinweis_delay'}


def anzeige_texte(c, tief=0):
    """Every text a card can show (all string and number fields except timing, layout and source fields), for the number
    gate and the channel stop words. Nested 'value' fields are bar heights (0 to 1), never printed. A chip's 'num' is the
    section index, not a claim."""
    out = []
    for k, v in c.items():
        if k in NICHT_ANZEIGE or k.endswith('_at') or k.endswith('_bis') or k.startswith('_') or (k == 'value' and tief):
            continue
        if k == 'num' and c.get('type') == 'chip':
            continue
        if isinstance(v, dict):
            out += anzeige_texte(v, tief + 1)
        elif isinstance(v, list):
            for x in v:
                out += anzeige_texte(x, tief + 1) if isinstance(x, dict) else ([str(x)] if isinstance(x, (str, int, float)) and not isinstance(x, bool) else [])
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            out.append(str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
    return out


# ---------- 5 main ----------
def main(plan_path, proj):
    plan = json.load(open(plan_path)); base = Path(plan_path).parent
    proj = Path(proj); proj.mkdir(parents=True, exist_ok=True)
    for d in ('fonts', 'media', 'sfx'):
        (proj / d).mkdir(exist_ok=True)
    P = kanal.profil(plan_path)
    for f in (SKILL / 'assets' / 'fonts').glob('*.ttf'):
        shutil.copy(f, proj / 'fonts' / f.name)
    SCH = kanal.schriften(P)
    for s_ in SCH.values():
        shutil.copy(s_['pfad'], proj / 'fonts' / s_['datei'])
    shutil.copy(SKILL / 'assets' / 'vendor' / 'gsap.min.js', proj / 'gsap.min.js')   # local copy: renders offline, same version as the CDN 3.14.2
    global GRID
    GRID = P.get('raster') or 'transparent'
    for f in (SKILL / 'assets' / 'sfx').glob('*.wav'):
        shutil.copy(f, proj / 'sfx' / f.name)
    src = str((base / plan['source']).resolve())
    # the render plays the take with gated word gaps (pausen_absenken.py) when the plan names it; every measurement below
    # (silences, faces, contrast, voiced word ends) still runs on the original take, so the edit does not change
    shutil.copy((base / plan['render_quelle']) if plan.get('render_quelle') else src, proj / 'media' / 'take.mp4')
    for a in plan.get('assets', []):   # images used by cards / b-roll, copied to media/<name>
        shutil.copy(base / a, proj / 'media' / Path(a).name)
    global PAUSE_CAP
    PAUSE_CAP = plan.get('pause_cap')
    global NAEHTE
    NAEHTE = list(plan.get('naehte', []))
    words_raw = json.load(open(base / plan['words']))
    fix = plan.get('fix', {})
    # Datum behält den Schlusspunkt ("26.10.", "26."), sonst Satzzeichen weg (Abnahme R4 v7-ohne G9: "26.10" ohne Punkt)
    _rein = lambda x: x.strip(' ,') if re.fullmatch(r'\d{1,2}\.(\d{1,2}\.)?', x.strip(' ,')) else x.strip(' ,.')
    words = [{'t': _rein(fix.get(str(i), w['w'])), 's': w['s'], 'e': w['e']} for i, w in enumerate(words_raw)]
    dur_src = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', src],
                                   capture_output=True, text=True).stdout)
    # Anfang in der Ruhe VOR dem ersten Laut: der ausgerichtete Wortanfang liegt bei Reibelauten zu spät (Abnahme R4 v7:
    # Reel begann mitten im "Z" von "Zehn"). Erster deutlicher Laut (Grundrauschen + 22 dB), davon zurück bis unter die
    # Sprachschwelle, 40 ms Abstand; nie ab Take 0: dort lag der Ton 1 AAC-Rahmen früh (Abnahme R4 v6).
    db0, thr0 = huelle(src)
    i_on = next((i for i in range(5, min(len(db0), int((words[0]['s'] + 0.3) * 100))) if db0[i] > thr0 + 10), None)
    if i_on is not None:
        while i_on > 3 and db0[i_on - 1] > thr0: i_on -= 1
    t0 = max(1 / FPS, min(words[0]['s'] - 0.1, (i_on / 100 - 0.08) if i_on is not None else 9e9))   # 80 ms: bei 40 ms fehlte der /t/-Verschluss von "Zehn" (Abnahme R4 v8-ohne)
    t1 = min(dur_src, words[-1]['e'] + plan.get('tail', 0.6))
    _vorlauf = [words[sg['from']]['s'] for sg in plan.get('segments', [])[1:] if sg.get('flash') and sg.get('from') is not None]
    ranges = keep_ranges(src, dur_src, t0, t1, plan.get('keep_pauses', []), _vorlauf)
    # plan 'weg': [[s, e], ...] Take-Sekunden, die immer herausfallen (Abnahme R4 Runde 8: stimmhaftes Ausatmen "Ja." vor einer Naht)
    for wa, wb in plan.get('weg', []):
        _neu = []
        for a_, b_ in ranges:
            if wb <= a_ or wa >= b_:
                _neu.append((a_, b_)); continue
            if fr(wa) - a_ >= 3 / FPS: _neu.append((a_, fr(wa)))
            if b_ - fr(wb) >= 3 / FPS: _neu.append((fr(wb), b_))
        ranges = _neu
    M, total, table = mapper(ranges)
    T = lambda wi: M(words[wi]['s'])
    schnitt_blenden(proj / 'media' / 'take.mp4', table)

    # segments: list of {"state": speaker|split|broll, "from": word index}; each runs until the next
    segs = plan['segments']
    seg_t = [0.0 if k == 0 else T(s['from']) for k, s in enumerate(segs)] + [total]
    # Segmente mit Abblende beginnen am Bildwechsel (Montage-Naht bis 0,5 s vor dem Wort): sonst laufen Rückblenden-Filter,
    # Zoom und der letzte Untertitel über das neue Bild bis zum ersten Wort (Fassung 8: Farbsprung 39,27 s, "können" über dem neuen Bild)
    # Allgemein (Abnahme R3-ohne 15.10.): liegt eine Montage-Naht bis 0,3 s vor einem Zustandswechsel (bei Abblende 0,5 s), rückt
    # der Wechsel samt Blitz auf die Naht. Sonst sah man den Bildsprung 133 ms vor der Blitzspitze oder 1 Bild neues Stück im
    # alten Splitscreen. Karten mit Anker auf dem Segmentwort rücken mit (Tc).
    # Runde 7 (Abnahme R2-ohne): auch Pausenschnitte zählen (Blitz 7 Bilder nach einem Sprungschnitt), Fenster 0,5 s
    # (Naht 0,43 s vor dem Wechsel: 13 Bilder neues Stück im alten Splitscreen)
    _kanten = [M(x) for x in NAEHTE] + [o / FPS for _, _, o in table][1:]
    snap_from = {}
    for k, s in enumerate(segs):
        if k:
            fenster = 0.5
            nz = [x for x in _kanten if seg_t[k] - fenster <= x <= seg_t[k] + 0.02 and x > seg_t[k - 1] + 0.2]
            if not nz:
                # Schnitt bis 0,3 s NACH dem Wechsel: Wechsel rückt auf den Schnitt (Abnahme R1 Runde 8: Sprungschnitt 267 ms
                # nach dem Wechsel bei 23,333 s, sichtbarer Kopfsprung)
                nach_ = [x for x in _kanten if seg_t[k] + 0.001 < x <= seg_t[k] + 0.3 and x < seg_t[k + 1] - 0.2]
                if nach_:
                    nz = [min(nach_)]
            if nz:
                neu = round((max(nz) if max(nz) <= seg_t[k] + 0.02 else min(nz)) * FPS) / FPS
                if abs(neu - seg_t[k]) > 0.001:
                    print(f'note: Zustandswechsel {k} von {seg_t[k]:.3f} auf Naht/Schnitt {neu:.3f} s')
                seg_t[k] = neu; snap_from[s['from']] = neu
    # Runde 5 (17.10.2026): ein Blitzwechsel genau auf dem ersten Wort eines Abschnitts mit weißen Untertiteln (Sprecher, B-Roll)
    # hielt dieses Wort bis 4 Bilder nach der Blitzspitze zurück (Lesbarkeit weiß auf weiß), die Abnahme Fall 2 maß +139 bis +201 ms.
    # Liegt davor eine Pause (Vorwort endet mindestens 2 Bilder vorher), rückt der Wechsel samt Blitz 5 Bilder vor das Wort.
    # Sonst bleibt er, schnitte_vorab G meldet die Verzögerung.
    for k, s in enumerate(segs):
        if not k or not s.get('flash') or s['state'] == 'split' or s['from'] in snap_from:
            continue
        w0 = T(s['from'])
        if w0 - seg_t[k] >= 4 / FPS - 0.001:
            continue
        # gleicher Zustand davor und danach (Betonungsblitz Sprecher -> Sprecher, Fall 1 Runde 5 "Unterschied"): kein Bildwechsel,
        # der Blitz darf ins Vorwort rücken, 4 Bilder genügen; bei einem Bildwechsel braucht es die Pause (5 Bilder)
        gleich = segs[k - 1]['state'] == s['state']
        vor_ende = M(words[s['from'] - 1]['e']) if s['from'] > 0 else 0.0
        # Runde 6 (17.10.2026, Fall 2: erstes Wort nach einem Satzende, 210 ms Pause): passen 5 Bilder nicht, dann 4 (das Wort erscheint
        # pünktlich, die Haltezeit endet auf ihm) oder 3 (33 ms später, unter der Grenze von G); vorher blieb der Wechsel auf dem
        # Wort und hielt es 133 ms zurück
        for n_ in ((4, 3) if gleich else (5, 4, 3)):
            neu = round((w0 - n_ / FPS) * FPS) / FPS
            if not ((not gleich and neu - vor_ende < 2 / FPS) or neu <= seg_t[k - 1] + 0.2
                    or any(neu - 0.02 < x < seg_t[k] + 0.02 for x in _kanten)):
                break
        else:
            print(f'note: Blitzwechsel {k} bleibt auf dem ersten Wort {w0:.3f} s (keine Pause davor)')
            continue
        print(f'note: Blitzwechsel {k} von {seg_t[k]:.3f} auf {neu:.3f} s, {round((w0 - neu) * FPS)} Bilder vor das erste Wort')
        seg_t[k] = neu
    Tc = lambda wi: snap_from.get(wi, T(wi))
    def state_at(t):
        for k, s in enumerate(segs):
            if seg_t[k] <= t < seg_t[k + 1]:
                return s['state'], k
        return segs[-1]['state'], len(segs) - 1

    fy, fw, fh = face_y(src)
    # full mode: move face toward FACE_FULL_Y as far as the frame allows without exposing edges
    scale0 = max(1.0, plan.get('scale', 1.0))
    # Vergrößert wird um die Gesichtshöhe FACE_FULL_Y, nicht um die Bildmitte: oben ragen FACE_FULL_Y*(scale0-1)*H Pixel über,
    # unten (1-FACE_FULL_Y)*(scale0-1)*H. Die alte Grenze (scale0-1)*H/2 ließ bei scale 1,12 oben 20 px Nachtblau frei (R4 v7, 15.10.2026).
    full_dy = max(-(1 - FACE_FULL_Y) * (scale0 - 1) * H, min(FACE_FULL_Y * (scale0 - 1) * H, (FACE_FULL_Y - fy) * H * scale0))
    split_dy = (FACE_SPLIT_Y - fy) * H * scale0           # downward shift always possible (top is paper)
    # caption block in full mode: 38 px below the chin, as in the reference (face centre 797 px, chin ~997, captions 1035)
    chin = (fy * H + full_dy) + fh * H * scale0 / 2
    # 38 px below the chin as measured; the reference's 1035 px is only where its chin happened to be (997 px).
    # A take with the face high (car: chin at ~900) gets its captions higher, on the chest instead of the car door.
    cap_top = int(min(1380, max(700, chin + 38)))
    track = face_track(src)

    body, js, audio, flashes_out, cards_out = [], [], [], [], []
    dips_out = []          # geplante Abblenden (für flimmern.py)
    # speaker videos
    vids = []
    for k, (fa, fb, o) in enumerate(table):
        vids.append(f'<video id="v{k}" src="media/take.mp4" data-start="{max(0.0, o/FPS - 0.0005):.6f}" data-duration="{(fb-fa)/FPS:.6f}" '
                    f'data-media-start="{fa/FPS:.6f}" data-track-index="{k % 2}" playsinline data-has-audio="true"></video>')
    body.append(f'<div id="spk"><div id="spkz">{"".join(vids)}</div></div>')

    # states: transforms + paper + broll + whoosh
    for k, s in enumerate(segs):
        a, b = seg_t[k], seg_t[k + 1]
        if b - a <= 0:
            continue
        st = s['state']
        dy = split_dy if st == 'split' else full_dy
        oy = FACE_SPLIT_Y if st == 'split' else FACE_FULL_Y
        # 17.10.2026 (independent inspection of the R3 rebuild): a speaker -> speaker change without flash, dip, punch or drama
        # is no visible cut; resetting the zoom there after a punch-in (1.04) jumped the picture by 3.8 % in one frame.
        # Keep the current zoom and position in that case.
        unsichtbar = (k > 0 and st == segs[k - 1]['state'] and not any(s.get(x) for x in ('flash', 'dip', 'punch', 'drama'))
                      and not segs[k - 1].get('drama'))
        if not unsichtbar:
            js.append(f'tl.set("#spk",{{y:{dy:.1f}}},{fs(a):.4f});')
            js.append(f'tl.set("#spkz",{{transformOrigin:"50% {oy*100:.1f}%",scale:{scale0:.3f}}},{fs(a):.4f});')
        if st == 'split':
            body.append(f'<div class="clip paper" data-start="{ds(a):.6f}" data-duration="{dd(a, b):.6f}" data-track-index="2"></div>')
        if st == 'broll':
            bid = f'br{k}'
            live = ''
            if s.get('live'):
                # living still: highlights flow through a mask of the water stream / bubbles (no video model on the free plan)
                live = (f'<div class="live" id="{bid}lv" style="-webkit-mask-image:url({esc(s["live"])});mask-image:url({esc(s["live"])});'
                        f'-webkit-mask-size:100% 100%;mask-size:100% 100%"></div>')
            if str(s["src"]).endswith('.mp4'):
                body.append(f'<div class="brollv" id="{bid}w"><div class="brz" id="{bid}z"><video id="{bid}" src="{esc(s["src"])}" '
                            f'data-start="{ds(a):.6f}" data-duration="{dd(a, b):.6f}" data-media-start="0" data-track-index="4" muted playsinline '
                            f'data-has-audio="false"></video></div></div>')
            else:
                body.append(f'<div class="clip broll" data-start="{ds(a):.6f}" data-duration="{dd(a, b):.6f}" data-track-index="3">'
                            f'<div class="brz" id="{bid}z"><img id="{bid}" src="{esc(s["src"])}" alt="">{live}</div></div>')
            js.append(f'tl.fromTo("#{bid}z",{{scale:1}},{{scale:{BROLL_PUSH},duration:{fr(b-a):.4f},ease:"none"}},{a:.4f});')
            if s.get('live'):
                js.append(f'tl.fromTo("#{bid}lv",{{backgroundPositionY:"0px"}},{{backgroundPositionY:"480px",duration:{fr(b-a):.4f},ease:"none",immediateRender:false}},{a:.4f});')
        if k > 0 and not s.get('flash') and segs[k - 1]['state'] != st:
            ws = max(0.0, a - WHOOSH_LEAD)
            audio.append(f'<audio id="wh{k}" src="sfx/whoosh.wav" data-start="{fr(ws):.4f}" data-duration="0.5500" data-track-index="9" data-volume="0.35"></audio>')
        if s.get('punch'):
            js.append(f'tl.fromTo("#spkz",{{scale:{scale0*PUNCH_FROM:.3f}}},{{scale:{scale0*PUNCH_TO:.3f},duration:{PUNCH_FR/FPS:.4f},ease:"power2.out"}},{fs(a):.4f});')   # fs: auf 4 Stellen gerundet feuerte der Punch 1 Bild zu spät (Abnahme R3 v1 Runde 7b: 43,467 s)
        if s.get('dip') and k > 0:
            # Abblende auf den Bildwechsel zentrieren: liegt eine Montage-Naht bis 0,5 s vor dem Segmentanfang (Einatmen vor
            # dem ersten Wort), wechselt das Bild dort. Abnahme R4 v7: Abblende auf "Und" zentriert, Naht 240 ms davor, beim
            # Wechsel erst 22 % deckend, Gesicht blitzte auf. Jetzt voll deckend ab 1 Bild vor dem Wechsel bis 1 Bild danach.
            nz = [M(x) for x in NAEHTE if a - 0.5 <= M(x) <= a + 0.02]
            c_ = round((max(nz) if nz else a) * FPS) / FPS
            dips_out.append(round(c_, 4))
            body.append(f'<div class="clip dipc" data-start="{max(0, c_ - 0.3):.4f}" data-duration="0.6667" data-track-index="8"><div id="dp{k}" class="dip"></div></div>')
            js.append(f'tl.set("#dp{k}",{{opacity:0}},0);tl.to("#dp{k}",{{opacity:1,duration:{0.3 - 1 / FPS:.4f},ease:"sine.in"}},{max(0, c_ - 0.3):.4f});'
                      f'tl.to("#dp{k}",{{opacity:0,duration:0.3,ease:"sine.out"}},{c_ + 1 / FPS:.4f});')
        if s.get('drama'):
            dz = float(s.get('drama_zoom', 1.16))
            # Zoomfahrt und Filter enden 1 ms VOR dem Zustandswechsel (fs(b)); fr(b-a) rundete bis zu 1/2 Bild darüber hinaus,
            # die laufende Fahrt überschrieb dann das tl.set des Splitscreens für 1 Bild (Abnahme R4 v7-ohne: Zoomsprung Bild 940).
            dzd = max(1 / FPS, fs(b) - a - 0.001)
            js.append(f'tl.fromTo("#spkz",{{scale:{scale0:.3f}}},{{scale:{scale0*dz:.3f},duration:{dzd:.4f},ease:"sine.inOut",immediateRender:false}},{fs(a):.4f});')
            js.append(f'tl.fromTo("#spk",{{filter:"saturate(1) brightness(1) contrast(1)"}},{{filter:"{s.get('drama_filter', 'saturate(0.45) brightness(0.8) contrast(1.08)')}",duration:{min(1.2, dzd):.4f},ease:"sine.inOut",immediateRender:false}},{fs(a):.4f});')
            js.append(f'tl.set("#spk",{{filter:"none"}},{fs(b):.4f});')
            body.append(f'<div class="clip dramav" data-start="{ds(a):.6f}" data-duration="{dd(a, b):.6f}" data-track-index="7"><div id="dv{k}" class="vign"></div></div>')
            js.append(f'tl.fromTo("#dv{k}",{{opacity:0}},{{opacity:1,duration:1.0,ease:"sine.inOut",immediateRender:false}},{fs(a):.4f});')
        if s.get('flash'):
            fid = f'fl{k}'
            fa = fr(a - FLASH_RISE / FPS)
            body.append(f'<div class="clip flashc" data-start="{max(0,fa):.4f}" data-duration="{(FLASH_RISE+FLASH_FALL+1)/FPS:.4f}" data-track-index="8"><div id="{fid}" class="flash"></div></div>')
            # 1 peak frame exactly on the cut (reference), then the fall starts immediately
            js.append(f'tl.fromTo("#{fid}",{{opacity:0}},{{opacity:1,duration:{FLASH_RISE/FPS:.4f},ease:"power2.in",immediateRender:false}},{max(0,fa):.4f});'
                      f'tl.to("#{fid}",{{opacity:0,duration:{FLASH_FALL/FPS:.4f},ease:"sine.out"}},{max(0,fa)+FLASH_RISE/FPS:.4f});')
            # fall ease sine.out (was power2.out): power2 measured a 6-frame fall on two dark takes and 5 on a bright take,
            # the reference falls in 8 (10 % rule); sine.out measured 7 to 8 (eval 08.10.2026)
            flashes_out.append(round(a, 4))
            audio.append(f'<audio id="wf{k}" src="sfx/whoosh.wav" data-start="{max(0,fr(a-WHOOSH_LEAD)):.4f}" data-duration="0.5500" data-track-index="9" data-volume="0.35"></audio>')
    # opening flash decay (reference F0-F10). Off by default since 10.10.2026: the creator read it as a glitch
    # ("ja am anfang ist ein kleiner fehler? kann das sein", WhatsApp 08.10.2026 09:14). "open_flash": true brings it back.
    if plan.get('open_flash', False):
        body.append(f'<div class="clip flashc" data-start="0" data-duration="{11/FPS:.4f}" data-track-index="8"><div id="fl_open" class="flash"></div></div>')
        js.append(f'tl.fromTo("#fl_open",{{opacity:0.55}},{{opacity:0,duration:{10/FPS:.4f},ease:"power2.out"}},0);')
    # numbers on cards must be spoken in the take (no invented health values, § 3 HWG / source rule); `quelle` overrides
    ZAHLW = {'null': '0', 'eins': '1', 'ein': '1', 'eine': '1', 'zwei': '2', 'drei': '3', 'vier': '4', 'fünf': '5', 'sechs': '6',
             'sieben': '7', 'acht': '8', 'neun': '9', 'zehn': '10', 'elf': '11', 'zwölf': '12', 'zwanzig': '20', 'dreißig': '30', 'hundert': '100'}
    spoken = set()
    for w in words:
        t_ = w['t'].lower().strip(' ,.!?')
        spoken.update(re.findall(r'\d+', t_))
        if t_ in ZAHLW: spoken.add(ZAHLW[t_])
    def card_texts(c):
        return ' '.join(anzeige_texte(c))
    for k, c in enumerate(plan.get('cards', [])):
        if c.get('type') == 'keyword' or c.get('quelle'): continue
        missing = [d_ for d_ in re.findall(r'\d+', card_texts(c)) if d_ not in spoken]
        if missing:
            raise SystemExit(f'plan error: card {k} ({c["type"]}) shows {missing}, which the take never says. Use what the speaker says, '
                             f'show the direction without a number, or add "quelle" with the source for the user to decide')
    # compliance stop words of the channel (profile "stopp"): on every visible card text and every caption word
    _stopp = kanal.stopp_treffer([card_texts(c) for c in plan.get('cards', [])] + [' '.join(w['t'] for w in words)], P)
    if _stopp:
        raise SystemExit('STOPP Kanalregel: ' + '; '.join(f'"{m}" ({g})' for g, m, _ in _stopp[:8]) +
                         '. Nicht selbst herausschneiden: Wortlaut mit Zeitcode an the user melden (references/creator-profile.md).')

    # hero punch-ins (never within 6 frames of a card entrance: the mini flash would wash the card out)
    card_t = [Tc(c['at']) + CAP_DELAY / FPS for c in plan.get('cards', [])]
    # a hero punch snaps back onto a cut that lies up to PUNCH_SNAP s before its word, so the zoom hides the jump cut
    # (08.10.2026: a cut at 1.07 s between two words, eyes closed before, open after, the punch came 0.24 s late)
    cut_t = [o / FPS for (_fa, _fb, o) in table[1:]]
    for hp in plan.get('hero_punch', []):
        t = T(hp)
        prev = [c for c in cut_t if 0 < t - c <= PUNCH_SNAP]
        if prev:
            print(f'hero_punch word {hp}: snapped from {t:.3f} s to the cut at {prev[-1]:.3f} s')
            t = prev[-1]
        clash = [ct for ct in card_t if abs(ct - t) < 6 / FPS + MINI_RISE / FPS]
        if clash:
            raise SystemExit(f'plan error: hero_punch at word {hp} ({t:.2f} s) collides with a card entrance at {clash[0]:.2f} s; move one of them')
        js.append(f'tl.fromTo("#spkz",{{scale:{scale0*HERO_PUNCH_FROM:.3f}}},{{scale:{scale0*PUNCH_TO:.3f},duration:{HERO_PUNCH_FR/FPS:.4f},ease:"power2.out"}},{fs(t):.4f});')
        body.append(f'<div class="clip flashc" data-start="{max(0,t-MINI_RISE/FPS):.4f}" data-duration="{(MINI_RISE+MINI_FALL+1)/FPS:.4f}" data-track-index="8"><div id="mf{hp}" class="flash mini"></div></div>')
        js.append(f'tl.fromTo("#mf{hp}",{{opacity:0}},{{opacity:0.35,duration:{MINI_RISE/FPS:.4f},immediateRender:false}},{max(0,t-MINI_RISE/FPS):.4f});'
                  f'tl.to("#mf{hp}",{{opacity:0,duration:{MINI_FALL/FPS:.4f}}},{max(0,t-MINI_RISE/FPS)+MINI_RISE/FPS:.4f});')

    _drama0 = any(sg.get('drama') and sg.get('from') == 0 for sg in plan.get('segments', []))
    # 15.10.2026 21:25: beginnt das Reel mit Dramatik, macht deren Zoomfahrt den Einstiegs-Zoom; beide zusammen auf #spkz ergaben
    # beim Ende der 1,5-s-Startfahrt einen Sprung um 8 % (Eigenmessung R1/R2 v2 Bild 45 -> 46)
    if plan.get('start_zoom') and not _drama0:   # Kallaway [WluuZB_ck9Q 29:55] "Right away, there's a slight zoom in."
        z = float(plan['start_zoom'])
        js.append(f'tl.fromTo("#spkz",{{scale:{scale0:.3f}}},{{scale:{scale0*z:.3f},duration:1.5,ease:"sine.out",immediateRender:false}},0);')

    # cards
    for k, c in enumerate(plan.get('cards', [])):
        a = 0.0 if c.get('ab_null') else Tc(c['at']); b = Tc(c['until']) if c.get('until') is not None else None   # Tc: endet mit dem eingerasteten Wechsel (Abnahme R2 Runde 7b: Hook-Karte 6 Bilder über dem neuen Bild)
        if b is None:   # until the end of the segment that contains it
            _, si = state_at(a + 0.001); b = seg_t[si + 1]
        Tk, _kw = Tc, False
        if c.get('type') == 'keyword' and not c.get('ab_null'):
            _cv = [x for x in [o / FPS for _, _, o in table][1:] + [M(x) for x in NAEHTE] if a - 0.25 <= x < a - 0.001 and not any(x < y <= a for y in seg_t[1:-1])]
            if _cv:   # Karte tritt mit dem Sprungschnitt ein statt 4 Bilder danach (Abnahme R3 v1 Runde 7b, H1)
                a = round(max(_cv) * FPS) / FPS; _kw = True
                Tk = lambda wi, _a=a, _w=c['at']: _a if wi == _w else Tc(wi)
                print(f'note: Keyword-Karte {k} auf Schnitt {a:.3f} s')
        h, j = card(dict(c, _am_wechsel=_kw or any(abs(a - x) < 0.5 / FPS for x in seg_t[1:-1]), _ende=b), f'c{k}', Tk)
        cards_out.append({'id': f'c{k}', 'type': c['type'], 'zone': c.get('zone', 'top'), 'appear': round(a + CAP_DELAY / FPS, 4), 'end': round(b, 4),
                          **({'zoom': True} if c.get('zoom_src') else {}),
                          # planned turn of a card (karte_flip, start as in erklaerer: tf = T(flip_at) + D - 3 frames): edge-on the
                          # dark card shows the paper behind it for a frame; flimmern.py leaves these frames out (round 2, 17.10.2026)
                          **({'drehung': round(Tk(c['flip_at']) + CAP_DELAY / FPS - 3 / FPS, 4)} if c.get('flip_at') is not None else {}),
                          **({'sub_appear': round(T(c['sub_at']), 4)} if c.get('sub_at') is not None and c['type'] == 'title' else {})})
        # Runde 5 (17.10.2026): eine Karte oben darf Augen und Brauen nicht bedecken (Abnahme Fall 2: Kommentarwort-Karte bis 367 px,
        # Pupille bei 375 px; das Gesicht steht hoch im Bild). Brauenlinie aus der Gesichtsspur über die Standzeit der Karte (Oberkante
        # des Gesichtsrahmens, im fertigen Bild nachgemessen: Modell 381 px, Vision 378 bis 385 px samt Zoomstoß), 20 % der Rahmenhöhe
        # und 8 px darüber (die Prüfung eigenpruefung 4 sperrt erst ab 18 % ohne Zuschlag). Liegt sie höher als jede Kartenhöhe (427 px), passt beim Laden ein Skript die Karte an: erst
        # auf 150 px (unterer Rand der Referenz), dann verkleinert (höchstens auf 70 %). Kartenhöhen kennt erst der Browser.
        if c.get('zone', 'top') == 'top' and track and state_at(a + 0.001)[0] != 'split':
            _tk = []
            for fa_, fb_, o_ in table:
                t0_, t1_ = o_ / FPS, (o_ + fb_ - fa_) / FPS
                if t1_ > a and t0_ < b:
                    _tk.append((fa_ / FPS + max(0.0, a - t0_), fa_ / FPS + min(b, t1_) - t0_))
            _brauen = []
            for sec, (cy, fh_) in track.items():
                if any(x0 - 0.2 <= sec <= x1 + 0.2 for x0, x1 in _tk):
                    _top = (cy * H + full_dy) - fh_ * H * scale0 / 2
                    _brauen.append(_top - 0.20 * fh_ * H * scale0 - 8)
            if _brauen and min(_brauen) < 427:
                _mx = int(min(_brauen))
                h = h.replace('<div class="card-wrap z-top"', f'<div class="card-wrap z-top" data-max-unten="{_mx}"', 1)
                print(f'note: Karte {k} ({c["type"]}) muss über {_mx} px enden (Augen und Brauen frei)')
        body.append(f'<div class="clip cardc" data-start="{ds(a):.6f}" data-duration="{dd(a, b):.6f}" data-track-index="5">{h}</div>')
        js += j

    if not plan.get('whoosh', True):
        audio[:] = [x for x in audio if 'sfx/whoosh.wav' not in x]
    # explainer sound effects: soft, never louder than 0.15 (whoosh 0.35)
    # Töne nie über einem Wortende und nie näher als 100 ms an einem Schnitt (Abnahme R1 15.10.: Pop 12,43 s auf "-ge" von
    # "Auge", 70 ms vor dem Pausenschnitt, Whisper hörte "auf"): liegt der Ton in einem Wort, rückt er auf dessen Anfang;
    # reicht er dann bis 100 ms an den nächsten Schnitt, rückt er vor (höchstens 150 ms vor den Wortanfang).
    # sounds keep 100 ms from pause cuts AND montage seams (validation 17.10.2026: a stamp landed exactly on a seam and
    # pruefe_ms read it as a clipped word)
    schnitte = sorted([o / FPS for _, _, o in table][1:] + [M(x) for x in NAEHTE])
    _sv = stimmhaft(src)
    def _ende(w):   # letztes stimmhaftes 10-ms-Stück im Wort (Mitte des 30-ms-Fensters), sonst das Wortende der Ausrichtung
        i0, i1 = int(w['s'] * 100), min(len(_sv), int((w['e'] + 0.03) * 100))
        pk = max([db0[i] for i in range(i0, i1)] or [-99])
        hit = [i for i in range(i0, i1) if _sv[i] and db0[i] >= pk - 14]   # Ausatmen nach dem Wort liegt 15 bis 20 dB tiefer
        return min(w['e'], hit[-1] / 100 + 0.02) if hit else w['e']
    # Runde 3 (17.10.2026): ein stimmloser Auslaut zählt zum Wort (Pop über einem stimmlosen Auslaut, Reibelaut 100 ms lang, unabhängige
    # Abnahme Fall 2). Ende = letzter 10-ms-Block bis 200 ms nach dem stimmhaften Ende, dessen Pegel oder Hochbandpegel 10 dB über
    # dem Grund der 2 s um das Wort liegt, ohne Lücke über 40 ms.
    import numpy as _np
    _raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', src, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], capture_output=True, check=True).stdout
    _x = _np.frombuffer(_raw, _np.int16).astype(_np.float32) / 32768
    _n = len(_x) // 160; _hp = _np.concatenate([[0.0], _np.diff(_x)])
    _lv = 20 * _np.log10(_np.sqrt(_np.mean(_x[:_n * 160].reshape(_n, 160) ** 2, axis=1)) + 1e-9)
    _lh = 20 * _np.log10(_np.sqrt(_np.mean(_hp[:_n * 160].reshape(_n, 160) ** 2, axis=1)) + 1e-9)
    def _ende_energie(w, e_v, nxt=1e9):
        k0, k1 = max(0, int((w['s'] - 1.0) * 100)), min(_n, int((w['e'] + 1.0) * 100))
        fb, fh = float(_np.percentile(_lv[k0:k1], 10)), float(_np.percentile(_lh[k0:k1], 10))
        k, luecke, ende = int(e_v * 100), 0, e_v
        # in verbundener Rede endet ein Wort spätestens am Anfang des nächsten (Runde 4: "nur" lief sonst in "einem" hinein)
        while k < min(_n, int((e_v + 0.2) * 100), int(max(e_v, nxt - 0.01) * 100)) and luecke < 4:
            if _lv[k] > fb + 10 or _lh[k] > fh + 10:
                ende, luecke = (k + 1) / 100, 0
            else:
                luecke += 1
            k += 1
        return ende
    w_out = [(M(w['s']), M(_ende_energie(w, _ende(w), words[i_ + 1]['s'] if i_ + 1 < len(words) else 1e9))) for i_, w in enumerate(words)]
    dauer = {'sfx_pop': 0.12, 'sfx_stempel': 0.35}
    for n_, (name, t_, vol) in enumerate(list(SFX_EVENTS)):
        d_ = dauer.get(name, 0.2)
        t0_ = t_
        for ws, we in w_out:                     # Ton überdeckt die letzten 120 ms eines Worts: davor ziehen, höchstens bis Wortanfang - 50 ms
            if t_ < we and t_ + d_ > we - 0.12 and t_ >= ws - 0.05:
                vor = max(ws - 0.05, we - 0.12 - d_)
                if d_ <= 0.15 and (vor + d_ > we - 0.12 or vor < t0_ - 0.2):
                    # kurzes Wort ("hinein" 142 ms): davor passt der Ton nicht, also 40 ms hinter das stimmhafte Ende,
                    # wenn bis zum nächsten Wort und zum nächsten Schnitt Platz ist
                    nach_ = we + 0.04
                    nxt = min([s2 for s2, _ in w_out if s2 > we], default=1e9)
                    if nach_ - t0_ <= 0.15 and nach_ + d_ <= nxt and not any(nach_ - 0.1 < c < nach_ + d_ + 0.1 for c in schnitte):
                        t_ = nach_; break
                t_ = vor
        nach = [c for c in schnitte if t_ - 0.1 < c < t_ + d_ + 0.1]
        if nach:
            t_ = min(nach) - d_ - 0.1
        t_ = max(t_, t0_ - 0.2) if t_ <= t0_ else t_   # höchstens 200 ms vor die Kartenbewegung
        # the 200 ms cap can put the sound back onto the cut it was moved away from (round 2 case 2, 17.10.2026: stamps on
        # the cuts at 37.833 and 51.467 s, read as clipped words): then the card's own time if that is clear of every cut,
        # else 100 ms behind the cut
        _nah = lambda x: [c for c in schnitte if x - 0.1 < c < x + d_ + 0.1]
        if _nah(t_):
            t_ = t0_ if not _nah(t0_) else max(_nah(t0_)) + 0.1
        # Runde 4 (17.10.2026): die Kappung kann den Ton auch zurück auf ein Wortende legen (Pop über "-sten", Abnahme Fall 1 ohne).
        # Liegt er danach noch über den letzten 120 ms eines Worts, rückt er 40 ms hinter das Wortende (höchstens 350 ms nach der
        # Kartenbewegung, frei von Schnitten und vom nächsten Wort) oder vor das Wort (höchstens 400 ms vor der Bewegung); gibt es
        # beides nicht, bleibt er und bau.txt meldet es (freigegebene Referenz-Reels behalten so ihre Töne).
        _dk = {'sfx_pop': 0.10, 'sfx_stempel': 0.15}.get(name, d_)     # hörbar prägender Teil (Anschlag), der Rest klingt leise aus
        _ueber = [(ws, we) for ws, we in w_out if t_ < we and t_ + _dk > we - 0.12 and t_ + _dk > ws]
        if _ueber:
            _we = max(we for _, we in _ueber); _nach = _we + 0.04
            _nxt = min([s2 for s2, _ in w_out if s2 > _we - 0.001], default=1e9)
            _ws0 = min(ws for ws, _ in _ueber); _vor = _ws0 - 0.05 - _dk
            _frei = lambda x: not any(x < we and x + _dk > we - 0.12 and x + _dk > ws for ws, we in w_out) and not _nah(x)
            if _nach - t0_ <= 0.35 and _nach + _dk <= _nxt and not _nah(_nach):
                t_ = _nach
            elif t0_ - _vor <= 0.40 and _vor >= 0 and _frei(_vor):     # vor dem Wort, höchstens 400 ms vor der Kartenbewegung
                t_ = _vor
            else:
                print(f'HINWEIS: Ton {name} bei {t_:.3f} s liegt über einem Wortende, kein freier Platz in der Nähe der Kartenbewegung')
        if t_ is not None and abs(t_ - t0_) > 0.001:
            print(f'note: Ton {name} von {t0_:.3f} auf {t_:.3f} s (Wortanfang/Schnittabstand)')
        SFX_EVENTS[n_] = (name, t_, vol)
    SFX_EVENTS[:] = [e_ for e_ in SFX_EVENTS if e_[1] is not None]
    # Runde 5 (17.10.2026): Klick auf einem ausklingenden Wortende (Abnahme Fall 2: Stempel 10,133 s auf "Die", Pop 36,933 s auf dem
    # Nasal von "dein", tiefe Stimme ohne Höhen). Beginnt ein Ton 20 ms nach bis 60 ms vor einem ausgerichteten Wortende, rückt er
    # 25 ms hinter dieses Ende (auf den Anlaut des nächsten Worts, das hält die Abnahme für unhörbar), also höchstens 85 ms später,
    # und nur ohne Schnitt in der Nähe. Ins Bildraster wird nie nach vorn gerundet: 10,150 s wurde sonst 10,133 s.
    import math as _math
    fr_ton = lambda x: round(_math.ceil(x * FPS - 0.05) / FPS, 4)
    _enden = [M(w['e']) for w in words]
    # dieselbe Bedingung wie schnitte_vorab E: die Stimme klingt in den ersten 15 ms noch (über Schwelle + 6 dB) und der Klick liegt
    # im Hochband 1 bis 7,9 kHz mehr als 10 dB über ihr. In einer Pause bleibt der Ton (R1 7,500 s, freigegeben).
    _xo = _np.concatenate([_x[int(round(r0 * 16000)):int(round(r1 * 16000))] for r0, r1 in ranges])
    _no = len(_xo) // 160
    _lvo = 20 * _np.log10(_np.sqrt(_np.mean(_xo[:_no * 160].reshape(_no, 160) ** 2, axis=1)) + 1e-12)
    _thr_o = float(_np.percentile(_lvo[_lvo > -80], 10)) + 12
    def _hb(x):
        if len(x) < 32:
            return -120.0
        sp = _np.abs(_np.fft.rfft(x * _np.hanning(len(x)))) ** 2; f = _np.fft.rfftfreq(len(x), 1 / 16000)
        return float(10 * _np.log10(sp[(f >= 1000) & (f <= 7900)].sum() / len(x) + 1e-15))
    _sfx_roh = {}
    def _hoerbar(name, t, vol):
        if name not in _sfx_roh:
            _sfx_roh[name] = _np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(SKILL / 'assets' / 'sfx' / f'{name}.wav'), '-ac', '1',
                                                           '-ar', '16000', '-f', 'f32le', '-'], capture_output=True, check=True).stdout, _np.float32)
        k0, k1 = int(t * 16000), int((t + 0.015) * 16000)
        if k1 > len(_xo):
            return False
        stimme = float(20 * _np.log10(_np.sqrt(_np.mean(_xo[k0:k1] ** 2)) + 1e-12))
        return stimme > _thr_o + 6 and _hb(_sfx_roh[name][:k1 - k0] * min(0.15, vol)) - _hb(_xo[k0:k1]) > 10
    for n_, (name, t_, vol) in enumerate(SFX_EVENTS):
        _nahe = [e for e in _enden if -0.02 <= e - t_ <= 0.06]
        if _nahe and _hoerbar(name, fr_ton(max(0, t_)), vol):
            _neu = max(_nahe) + 0.025
            _cut = [c for c in schnitte if _neu - 0.1 < c < _neu + 0.25]
            if not _cut:
                print(f'note: Ton {name} von {t_:.3f} auf {_neu:.3f} s hinter das Wortende {max(_nahe):.3f} s')
                SFX_EVENTS[n_] = (name, _neu, vol)
            else:
                print(f'HINWEIS: Ton {name} bei {t_:.3f} s beginnt am Wortende {max(_nahe):.3f} s, dahinter liegt ein Schnitt')
    for n_, (name, t_, vol) in enumerate(SFX_EVENTS):
        if plan.get('sfx', True):
            audio.append(f'<audio id="sx{n_}" src="sfx/{name}.wav" data-start="{fr_ton(max(0, t_)):.4f}" data-duration="0.4000" '
                         f'data-track-index="{10 + n_ % 2}" data-volume="{min(0.15, vol):.2f}"></audio>')

    # captions
    # Gruppen am Zustandswechsel teilen (Abnahme R4 Runde 8: Gruppe "bin und" endete am vorgezogenen Wechsel, "und" fehlte)
    groups = []
    for g in plan['groups']:
        ws_, rs_ = list(g['w']), list(g.get('roles', ['base'] * len(g['w'])))
        k0 = 0
        for j in range(1, len(ws_)):
            if any(T(ws_[k0]) < s_ <= T(ws_[j]) for s_ in seg_t[1:-1]):
                groups.append(dict(g, w=ws_[k0:j], roles=rs_[k0:j])); k0 = j
        groups.append(dict(g, w=ws_[k0:], roles=rs_[k0:]))
    low_contrast = []
    zeigt = {}            # Runde 5: Wortindex -> Zeit der Einblendung (schnitte_vorab G misst gezeigte statt geplanter Zeit)
    for g_i, g in enumerate(groups):
        a = T(g['w'][0])
        b = T(groups[g_i + 1]['w'][0]) if g_i + 1 < len(groups) else total
        st, si = state_at(a + 0.001)
        b = min(b, seg_t[si + 1]) if g.get('clip_at_segment', True) else b
        # Untertitel enden an der ersten Montage-Naht nach ihrem letzten Wort (Abnahme R3-ohne: 7 Bilder über dem nächsten Clip)
        _ns = [M(x) for x in NAEHTE if M(words[g['w'][-1]]['s']) + 0.05 < M(x) < b]
        if _ns:
            b = min(_ns)
        mode = 'split' if st == 'split' else 'full'
        cid = f'g{g_i}'
        h, items = cap_html(g, words, mode, cid)
        if mode == 'full' and st == 'speaker' and track:
            # lowest chin while this group is on screen (face sampled every 10 frames, ±0.5 s), 38 px gap as in the reference
            s0 = words[g['w'][0]]['s'] - 0.5; s1 = words[g['w'][-1]]['e'] + 0.5
            chins = [(cy * H + full_dy) + fh_ * H * scale0 / 2 for sec, (cy, fh_) in track.items() if s0 <= sec <= s1]
            top_g = int(min(1500, max(700, max(chins) + 38))) if chins else cap_top
            if g.get('cap_top'):
                top_g = int(g['cap_top'])
            else:
                # readability: white captions need a dark background (reference: always on the dark shirt, contrast
                # 10th percentile 4.4:1). Try up to 300 px further down the torso in 20 px steps; move only if a position
                # reaches 3.0:1. Otherwise the caption stays at the cutter's position and is reported: a stronger
                # shadow would change the style, that is the user's decision (08.10.2026).
                mid = (words[g['w'][0]]['s'] + words[g['w'][-1]]['e']) / 2
                c0 = contrast_at(src, mid, top_g, full_dy, scale0)
                if c0 < 3.0:
                    hit = next((y for y in range(top_g + 20, min(1560, top_g + 300) + 1, 20) if contrast_at(src, mid, y, full_dy, scale0) >= 3.0), None)
                    if hit:
                        print(f'note: caption group {g_i} moved {top_g} -> {hit} px for contrast >= 3.0:1 (was {c0:.1f}:1)'); top_g = hit
                    else:
                        low_contrast.append(g_i)
            if top_g != cap_top:
                h = h.replace('<div class="cap full">', f'<div class="cap full" style="top:{top_g}px">', 1)
        if mode == 'full' and st != 'speaker' and g.get('cap_top'):
            h = h.replace('<div class="cap full">', f'<div class="cap full" style="top:{int(g["cap_top"])}px">', 1)
        # weiße Untertitel, die schon stehen, wenn ein Blitz kommt, verschwinden 2 Bilder vor der Spitze und kommen 4 Bilder
        # danach wieder (Abnahme R2 Runde 2: "aufzunehmen?" voll weiß auf dem hellen Blitz, Kontrast 2,15:1)
        pausen = [fp for fp in flashes_out if mode == 'full' and a < fp - 2 / FPS < b] if mode == 'full' else []
        if pausen:
            h = h.replace('<div class="cap full"', f'<div id="{cid}w" class="cap full"', 1)
            for fp in pausen:
                js.append(f'tl.set("#{cid}w",{{opacity:0}},{fp - 2 / FPS:.4f});')
                if b > fp + 4 / FPS:
                    js.append(f'tl.set("#{cid}w",{{opacity:1}},{fp + 4 / FPS:.4f});')
                print(f'note: weißer Untertitel {g_i} pausiert im Blitz {fp:.3f} s')
        body.append(f'<div class="clip capc" data-start="{ds(a):.6f}" data-duration="{dd(a, b):.6f}" data-track-index="6">{h}</div>')
        for sid, wi, role in items:
            tw = max(a, T(wi) + CAP_DELAY / FPS) if wi != g['w'][0] else a
            if mode == 'full':     # weiße Untertitel nicht im Blitzabklingen beginnen (weiß auf weiß, R3 15.10.): ab 4 Bilder nach der Spitze
                for fp in flashes_out:
                    if fp - 2 / FPS <= tw < fp + 4 / FPS:
                        tw = fp + 4 / FPS
            # word pop (the user 08.10.2026: "Untertitel lebendiger", taken from the edit he preferred): hero and key jump in at
            # 128 % and spring back over 5 frames (back.out 1.4), small words grow from 86 %; all rise 14 px; 3-frame fade
            # im Splitscreen stehen Hauptwörter in der Zeile mit ihren Nachbarn: 128 % überdeckten im 1. Bild den Wortabstand
            # ("Undsobald", Abnahme R2 G7), dort 108 %; Deckkraft in 2 Bildern (Regel des Referenzkanals: höchstens 1 Übergangsbild)
            s0 = (1.28 if mode == 'full' else 1.08) if role in ('hero', 'key') else 0.86
            ez = 'back.out(1.4)' if role in ('hero', 'key') else 'power3.out'
            zeigt[wi] = round(tw, 4)
            js.append(f'tl.set("#{sid}",{{transformOrigin:"50% 80%"}},0);'
                      f'tl.fromTo("#{sid}",{{opacity:0}},{{opacity:1,duration:{2/FPS:.4f},ease:"power1.out",immediateRender:false}},{tw:.4f});'
                      f'tl.fromTo("#{sid}",{{scale:{s0},y:14}},{{scale:1,y:0,duration:{5/FPS:.4f},ease:"{ez}",immediateRender:false}},{tw:.4f});')

    # plans written by plan_bauen.py carry "kartentext_streng": defaults are refused for every channel then (validation 17.10.:
    # texts of other reference reels showed up unnoticed); the 8 delivered reference plans do not have the field
    if erklaerer.VORGABE_GENUTZT and (plan.get('kartentext_streng') or not P.get('kartentext_vorgabe_erlaubt')):
        raise SystemExit('plan error: Karten zeigen Beispieltexte aus den Referenz-Reels: ' +
                         '; '.join(f'{t}.{f}="{v}"' for t, f, v in erklaerer.VORGABE_GENUTZT[:10]) +
                         '. Jedes sichtbare Feld braucht den eigenen Satz des Kanals (references/card-catalog.md).')
    _ff = ''.join(f'@font-face {{ font-family: "{fam}"; src: url("fonts/{SCH[r]["datei"]}") format("{"woff2" if SCH[r]["datei"].endswith(".woff2") else "truetype"}"); '
                  f'font-weight: {SCH[r]["gewicht"]}; font-style: {sty}; }}\n'
                  for fam, r, sty in (('CormorantHF', 'hero', 'normal'), ('MontserratHF', 'text', 'normal'), ('PlayfairHF', 'akzent', 'italic')))
    css = ((SKILL / 'assets' / 'style.css').read_text().replace('%FONTFACES%\n', _ff) + erklaerer.CSS + (P.get('css_zusatz') or '')).replace('%PAPER%', PAPER).replace('%GRID%', GRID) \
        .replace('%INK%', INK).replace('%RED%', RED).replace('%SIGNAL%', SIGNAL).replace('%CARD%', CARD).replace('%SEAM_SOLID%', str(SEAM_SOLID)) \
        .replace('%SEAM_END%', str(SEAM_SOLID + SEAM_FADE)).replace('%CAP_FULL_TOP%', str(cap_top)) \
        .replace('%CAP_SPLIT_CY%', str(CAP_SPLIT_CY)).replace('%GRID_X0%', str(GRID_X0)).replace('%GRID_Y0%', str(GRID_Y0))
    # Runde 5: Anpassung der Karten mit data-max-unten (siehe Karten oben); nur wenn eine Karte sie braucht, sonst bleibt index.html gleich
    passung = ("document.querySelectorAll('.card-wrap[data-max-unten]').forEach(function(el){var m=+el.dataset.maxUnten,"
               "t=el.offsetTop,h=el.offsetHeight;if(t+h<=m)return;var t2=Math.min(t,150),s=Math.max(0.7,(m-t2)/h);"
               "el.style.top=t2+'px';el.style.transformOrigin='50% 0';el.style.transform='scale('+s.toFixed(3)+')';});\n"
               if any('data-max-unten=' in x for x in body) else '')
    doc = f'''<!doctype html>
<html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H}">
<title>{esc(plan.get("title","Reel"))}</title>
<script src="gsap.min.js"></script>
<style>{css}</style></head>
<body>
<div id="root" data-composition-id="reel" data-start="0" data-width="{W}" data-height="{H}" data-duration="{total:.4f}">
{chr(10).join(body)}
{chr(10).join(audio)}
</div>
<script>
{passung}const tl = gsap.timeline({{ paused: true }});
{bildgenau(chr(10).join(js))}
window.__timelines["reel"] = tl;
</script>
</body></html>'''
    doc = kanal.farben_umsetzen(doc, P)
    _rest = kanal.farbreste(doc, P)
    if _rest:
        raise SystemExit(f'build error: Grundfarben stehen noch in der Komposition, Kanal {P["name"]} färbt sie um: {_rest}')
    (proj / 'index.html').write_text(doc, encoding='utf-8')
    edl = {'source': src, 'ranges': ranges, 'total': total, 'face_y': fy, 'face_w': fw, 'full_dy': full_dy,
           'split_dy': split_dy, 'dips': dips_out, 'segments': [{'state': s['state'], 'a': seg_t[k], 'b': seg_t[k + 1]} for k, s in enumerate(segs)],
           'words': [{'t': w['t'], 'raw': words_raw[i]['w'], 'out': T(i)} for i, w in enumerate(words)], 'flashes': flashes_out, 'cards': cards_out}
    (proj / 'edl.json').write_text(json.dumps(edl, ensure_ascii=False, indent=1))
    (proj / 'untertitel-zeiten.json').write_text(json.dumps({str(k): v for k, v in sorted(zeigt.items())}))
    if low_contrast:
        print(f'WARN: white captions on a bright background in groups {low_contrast} (below 3.0:1 even 300 px lower). '
              f'Options for the user: stronger shadow, show these phrases on the paper, or keep them as they are.')
    print(f'ok: {len(ranges)} keep ranges, {total:.2f} s (source {t1-t0:.2f} s), {len(groups)} caption groups, '
          f'{len(plan.get("cards", []))} cards, face_y {fy:.3f} -> full_dy {full_dy:.0f}px split_dy {split_dy:.0f}px, captions full at y={cap_top}')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
