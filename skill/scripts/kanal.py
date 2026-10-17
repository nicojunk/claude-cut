#!/usr/bin/env python3
"""Channel profile (Kanal-Profil) and machine settings for SMM Clipping.

Every script that needs something channel specific (raw footage folder, transcripts, brand colours, fonts, call to action,
forbidden content) asks this module instead of hard-coding it. The engine was built on the reference creator's reels; her palette is
the BASE palette. Another channel declares its own colour for each role and the finished composition is recoloured in one
pass (`farben_umsetzen`). the reference channel's own profile maps every role onto itself, so her reels stay byte-identical.

Lookup of the profile, first hit wins:
  1. environment SMM_KANAL = profile name ("demo") or path to a profile JSON
  2. the nearest reel.json or kanal.json above the working folder (or above a given path) with a "kanal" field
Profiles live in the folder `kanaele` of the settings (default ~/.config/smm-clipping/kanaele/), then in the skill's own
`kanaele/` folder, which ships only the template.

Settings (machine specific, never in a profile): ~/.config/smm-clipping/config.json, or SMM_CONFIG=path.
Usage as a tool:  python3 kanal.py [zeigen|pruefen] [NAME]
"""
import json, os, re, shutil, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get('SMM_CONFIG', Path.home() / '.config' / 'smm-clipping' / 'config.json'))

# Base palette: the colours the engine (style.css, baue_reel.py, erklaerer.py) is written in. Role -> (hex, rgb triple).
BASIS_FARBEN = {
    'ink':          ('#1E2430', (30, 36, 48)),     # dark: text on paper and cards, dark cards, background
    'ink2':         ('#283040', (40, 48, 64)),     # second dark, gradients on dark cards
    'ink_tief':     ('#12161E', (18, 22, 30)),     # deepest dark, vignette edge
    'accent':       ('#3FB8AF', (63, 184, 175)),   # brand accent: key box, rings, lines, icons
    'accent2':      ('#52C7BE', (82, 199, 190)),   # brighter accent: highlights, bars, glow
    'accent_hell':  ('#A8E2DD', (168, 226, 221)),  # light accent: italic text on dark cards
    'accent_blass': ('#E3F5F3', (227, 245, 243)),  # palest accent: sheen, gradient middle, light tint
    'papier':       ('#F7F8F6', (247, 248, 246)),  # paper of the split screen
    'signal':       ('#3FB8B0', (63, 184, 176)),   # semantic red: blood, danger, wrong value (the reference channel: looks like the accent)
}


def _expand(p):
    return Path(os.path.expanduser(str(p))) if p else None


def einstellungen():
    """Machine settings with defaults. Keys: kanaele, renders, python_ml, ablage, credit_log."""
    e = {'kanaele': '~/.config/smm-clipping/kanaele', 'renders': '~/Renders', 'python_ml': None, 'ablage': '~/Desktop',
         'credit_log': None}
    if CONFIG.exists():
        e.update(json.loads(CONFIG.read_text()))
    if not e.get('python_ml'):
        e['python_ml'] = shutil.which('python3.14') or shutil.which('python3') or sys.executable
    return e


def _profil_datei(name):
    p = Path(os.path.expanduser(name))
    if p.suffix == '.json' and p.exists():
        return p
    for d in (_expand(einstellungen()['kanaele']), SKILL / 'kanaele'):
        if d and (d / f'{name}.json').exists():
            return d / f'{name}.json'
    raise SystemExit(f'Kanal-Profil "{name}" nicht gefunden (gesucht in {einstellungen()["kanaele"]} und {SKILL / "kanaele"}). '
                     f'Neues Profil: Vorlage {SKILL / "kanaele" / "vorlage.json"} kopieren, references/creator-profile.md lesen.')


def _name_von(start):
    if os.environ.get('SMM_KANAL'):
        return os.environ['SMM_KANAL']
    d = Path(start or os.getcwd()).resolve()
    if d.is_file():
        d = d.parent
    for x in [d, *d.parents]:
        for f in ('reel.json', 'kanal.json'):
            if (x / f).exists():
                k = json.loads((x / f).read_text()).get('kanal')
                if k:
                    return k
    raise SystemExit('Kein Kanal bekannt: SMM_KANAL setzen oder "kanal" in reel.json / kanal.json eintragen.')


_CACHE = {}


def profil(start=None):
    """The channel profile as dict, with defaults filled in and paths expanded."""
    name = _name_von(start)
    if name in _CACHE:
        return _CACHE[name]
    f = _profil_datei(name)
    P = json.loads(f.read_text())
    P.setdefault('name', f.stem)
    P['_datei'] = str(f)
    P['_ordner'] = str(f.parent)
    P.setdefault('sprache', 'de')
    farben = {k: v[0] for k, v in BASIS_FARBEN.items()}
    farben.update(P.get('farben', {}))
    P['farben'] = farben
    P.setdefault('raster', None)
    P.setdefault('css_zusatz', '')
    P.setdefault('stopp', [])
    P.setdefault('plan_standard', {})
    P.setdefault('rollen', {})
    P['rohmaterial'] = [str(_expand(x)) for x in P.get('rohmaterial', [])]
    for k in ('transkripte', 'cache', 'arbeitsordner'):
        if P.get(k):
            P[k] = str(_expand(P[k]))
    if not P.get('cache'):
        P['cache'] = str(Path.home() / '.cache' / 'smm-clipping' / P['name'])
    _CACHE[name] = P
    return P


_HDR = {}


def _ist_hdr(p):
    import subprocess
    if str(p) not in _HDR:
        r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=color_transfer,pix_fmt',
                            '-of', 'csv=p=0', str(p)], capture_output=True, text=True).stdout
        _HDR[str(p)] = 'arib-std-b67' in r or 'smpte2084' in r or '10le' in r
    return _HDR[str(p)]


def roh(clip, P=None, sdr_erlaubt=True):
    """Path of a raw clip: absolute path, or file name inside one of the profile's raw footage folders.
    iPhone HDR (HLG, 10 bit) is never used directly: ffmpeg filters give a yellow cast. The SDR copy that
    `clip.py material` made with Apple's tonemapper (cache/sdr/<name>_SDR.mp4) is returned instead."""
    p = _expand(clip)
    P = P or profil()
    if not (p.is_absolute() and p.exists()):
        p = next((Path(d) / clip for d in P['rohmaterial'] if (Path(d) / clip).exists()), None)
        if p is None:
            raise SystemExit(f'Rohclip {clip} in keinem Rohmaterial-Ordner von "{P["name"]}" gefunden: {P["rohmaterial"]}')
    if sdr_erlaubt and _ist_hdr(p):
        sdr = Path(P['cache']) / 'sdr' / f'{p.stem}_SDR.mp4'
        if not sdr.exists():
            raise SystemExit(f'{clip} ist HDR. Erst: python3 clip.py material {P["name"]} {clip}  (SDR-Kopie mit avconvert)')
        return sdr
    return p


def transkripte(P=None):
    P = P or profil()
    d = Path(P.get('transkripte') or Path(P['cache']) / 'transkripte')
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache(P=None):
    P = P or profil()
    d = Path(P['cache'])
    d.mkdir(parents=True, exist_ok=True)
    return d


def datei_schluessel(path):
    """Content key of a file (size + first and last MiB) for caches: a new take with the same name invalidates its cache,
    a copy with the same content does not (14.10.2026: take.faces.tsv and entrauschen.json were never invalidated)."""
    import hashlib
    p = Path(path); n = p.stat().st_size; h = hashlib.sha1(str(n).encode())
    with open(p, 'rb') as f:
        h.update(f.read(1 << 20))
        if n > 2 << 20:
            f.seek(-(1 << 20), 2); h.update(f.read())
    return h.hexdigest()[:16]


# ---------- colours ----------
def _rgb(hexs):
    h = hexs.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def kontrast(a, b):
    """WCAG contrast ratio of two #RRGGBB colours."""
    def L(h):
        c = [x / 255 for x in _rgb(h)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    la, lb = sorted((L(a), L(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def rgb(rolle, P=None):
    return _rgb((P or profil())['farben'][rolle])


def farben_umsetzen(text, P=None):
    """Recolour engine output from the base palette to the channel palette in one pass (no chained replacements)."""
    P = P or profil()
    karte_hex, karte_rgb = {}, {}
    for rolle, (hx, tri) in BASIS_FARBEN.items():
        ziel = P['farben'][rolle].upper()
        if ziel != hx.upper():
            karte_hex[hx.upper()] = ziel
            karte_rgb[tri] = _rgb(ziel)
    if not karte_hex:
        return text
    text = re.sub(r'#[0-9A-Fa-f]{6}\b', lambda m: karte_hex.get(m.group(0).upper(), m.group(0)), text)

    def _tri(m):
        t = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
        if t not in karte_rgb:
            return m.group(0)
        r, g, b = karte_rgb[t]
        return f'{m.group(1)}{r},{g},{b}'
    return re.sub(r'(rgba?\(\s*)(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})', _tri, text)


def farbreste(text, P=None):
    """Base colours that are still in the text although the channel maps them elsewhere (gate after every build)."""
    P = P or profil()
    rest = []
    for rolle, (hx, tri) in BASIS_FARBEN.items():
        if P['farben'][rolle].upper() == hx.upper():
            continue
        n = len(re.findall(re.escape(hx), text, re.I)) + len(re.findall(r'rgba?\(\s*%d\s*,\s*%d\s*,\s*%d\b' % tri, text))
        if n:
            rest.append(f'{rolle} {hx} ({n}x)')
    return rest


# ---------- fonts ----------
SCHRIFT_STANDARD = {
    'text':   {'datei': 'Inter[opsz,wght].ttf', 'gewicht': '100 900'},
    'hero':   {'datei': 'CormorantGaramond[wght].ttf', 'gewicht': '300 700'},
    'akzent': {'datei': 'CormorantGaramond-Italic[wght].ttf', 'gewicht': '300 700'},
}


def schriften(P=None):
    """{'text'|'hero'|'akzent': {'datei': name, 'gewicht': css range, 'pfad': source file}}"""
    P = P or profil()
    out = {}
    for rolle, std in SCHRIFT_STANDARD.items():
        s = dict(std); s.update(P.get('schriften', {}).get(rolle, {}))
        kand = [Path(P['_ordner']) / 'schriften' / s['datei'], SKILL / 'assets' / 'fonts' / s['datei']]
        if P.get('schriften_ordner'):
            kand.insert(0, _expand(P['schriften_ordner']) / s['datei'])
        s['pfad'] = next((str(k) for k in kand if k.exists()), None)
        if not s['pfad']:
            raise SystemExit(f'Schrift {s["datei"]} ({rolle}) für Kanal {P["name"]} nicht gefunden: {[str(k) for k in kand]}')
        out[rolle] = s
    return out


def stopp_treffer(texte, P=None):
    """Compliance stop words (profile 'stopp': [{"muster": regex, "grund": "..."}]) found in the given texts."""
    P = P or profil()
    hits = []
    for regel in P.get('stopp', []):
        rx = re.compile(regel['muster'], re.I)
        for t in texte:
            for m in rx.finditer(t or ''):
                hits.append((regel.get('grund', ''), m.group(0), t))
    return hits


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'zeigen'
    if len(sys.argv) > 2:
        os.environ['SMM_KANAL'] = sys.argv[2]
    P = profil()
    if cmd == 'zeigen':
        print(json.dumps({k: v for k, v in P.items()}, ensure_ascii=False, indent=1))
    elif cmd == 'pruefen':
        ok = True
        for d in P['rohmaterial']:
            print(('ok    ' if Path(d).is_dir() else 'FEHLT ') + 'Rohmaterial ' + d); ok &= Path(d).is_dir()
        for r, s in schriften(P).items():
            print(f'ok    Schrift {r}: {s["pfad"]}')
        for r, hx in P['farben'].items():
            if not re.fullmatch(r'#[0-9A-Fa-f]{6}', hx):
                print(f'FEHLER Farbe {r}={hx} (nur #RRGGBB)'); ok = False
        for regel in P['stopp']:
            re.compile(regel['muster'])
        # contrast rules of the engine: accents are drawn as lines on white cards AND on dark boxes, light accent is text on dark
        for a, b, mindest, warum in (('accent', '#FFFFFF', 2.0, 'Linien auf weißen Karten'), ('accent2', '#FFFFFF', 2.0, 'Linien auf weißen Karten'),
                                     ('accent', 'ink', 3.0, 'Rahmen auf dunklen Karten'), ('accent_hell', 'ink', 4.5, 'Schrift auf dunklen Karten'),
                                     ('ink', 'papier', 7.0, 'Schrift auf dem Papier'), ('ink', '#FFFFFF', 7.0, 'Schrift auf weißen Karten'),
                                     ('signal', '#FFFFFF', 2.0, 'Signal (Warnung, falscher Wert) auf weißen Karten')):
            k = kontrast(P['farben'].get(a, a), P['farben'].get(b, b))
            gut = k >= mindest
            print(f'{"ok    " if gut else "FEHLER"} Kontrast {a} gegen {b}: {k:.2f}:1 (mindestens {mindest}, {warum})'); ok &= gut
        print('Profil', P['name'], 'OK' if ok else 'MIT FEHLERN'); sys.exit(0 if ok else 1)


_AAC = None
def aac_kodierer():
    """ffmpeg arguments for the AAC encoder of every delivery (round 5, 17.10.2026): Apple's AudioToolbox (aac_at) when ffmpeg
    has it. ffmpeg's own encoder put a one-sided spike into the first audio block (+0.39 dBTP in the left channel at 0.010 s,
    independent inspection case 2); aac_at reproduced the master there within 0.4 dB. Fallback: ffmpeg's aac."""
    global _AAC
    if _AAC is None:
        import subprocess
        enc = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
        _AAC = ['-c:a', 'aac_at'] if ' aac_at ' in enc else ['-c:a', 'aac']
    return list(_AAC)
