#!/usr/bin/env python3
"""Cover (Titelbild) with a text hook in the upper third, in the channel's colours and fonts.

Rules (Nico 15.10.2026 17:41 and 18:13): the text is the best fitting of the 50 hook templates (references/hook-vorlagen.md),
at most 2 lines, no punctuation, upper third (inside the 4:5 profile crop y 285 to 1635). The still moves down by VERSATZ px so
card and face never overlap; above it the channel's dark colour with a soft blend into the picture. The cover becomes frame 0 of
the delivered reel (abliefern.sh), so WhatsApp and Instagram show it as preview.

Usage:  python3 titelbild.py ORDNER ZEIT "Zeile 1" "Zeile 2" [VERSATZ]
        ORDNER holds take.mp4; ZEIT = take seconds of the still (eyes open, mouth closed, face sharp).
Writes ORDNER/cover-bild.jpg (the still), cover.jpg (1080x1920) and cover-profil-4zu5.jpg."""
import math, random, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal

d0, zeit, l1, l2 = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
VERSATZ = int(sys.argv[5]) if len(sys.argv) > 5 else 430
for z in (l1, l2):
    if re.search(r'[.,;:!?–—-]', z):
        sys.exit(f'Titelbild: keine Satzzeichen im Text-Hook ("{z}"), Regel der 50 Vorlagen')
P = kanal.profil(d0)
TB = {'grund': 'ink', 'rand': 'accent', 'welle': 'accent2', 'zeile1_farbe': '#FFFFFF', 'zeile2_farbe': 'accent_hell',
      'zeile1_schrift': 'text', 'zeile2_schrift': 'akzent', 'zeile1_versal': False, 'motiv': 'welle', 'zeile1_px': 64, 'zeile2_px': 82}
TB.update(P.get('titelbild', {}))
farbe = lambda x: kanal._rgb(P['farben'].get(x, x))
GRUND, RAND, WELLE, F1, F2 = (farbe(TB[k]) for k in ('grund', 'rand', 'welle', 'zeile1_farbe', 'zeile2_farbe'))
SCH = kanal.schriften(P)
if TB['zeile1_versal']:
    l1 = l1.upper()

subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', zeit, '-i', str(d0 / 'take.mp4'), '-frames:v', '1', '-q:v', '2', str(d0 / 'cover-bild.jpg')], check=True)
foto = Image.open(d0 / 'cover-bild.jpg').convert('RGB')
W, H = foto.size
assert (W, H) == (1080, 1920), (W, H)
img = Image.new('RGB', (W, H), GRUND)
img.paste(foto.crop((0, 0, W, H - VERSATZ)), (0, VERSATZ))
m = Image.new('L', (W, H), 0); dm = ImageDraw.Draw(m)
for y in range(H):   # soft blend: dark above VERSATZ, then 260 px into the picture
    dm.line([(0, y), (W, y)], fill=255 if y < VERSATZ else max(0, int(255 * (1 - (y - VERSATZ) / 260))))
img = Image.composite(Image.new('RGB', (W, H), GRUND), img, m)


def schrift(rolle, gr, wght):
    f = ImageFont.truetype(SCH[rolle]['pfad'], gr)
    try:
        achsen = f.get_variation_axes()
        f.set_variation_by_axes([wght if a.get('name') in (b'Weight', 'Weight') else (32 if a.get('name') in (b'Optical size', 'Optical size') else a['default']) for a in achsen])
    except Exception:
        pass
    return f


d = ImageDraw.Draw(img)
g1, g2 = int(TB['zeile1_px']), int(TB['zeile2_px'])   # start sizes; a condensed uppercase font needs a bigger line 1
while True:
    s1, s2 = schrift(TB['zeile1_schrift'], g1, 700), schrift(TB['zeile2_schrift'], g2, 600)
    w1, w2 = d.textlength(l1, font=s1), d.textlength(l2, font=s2)
    if max(w1, w2) <= 920:
        break
    g1, g2 = g1 - 2, g2 - 2
welle = TB['motiv'] == 'welle'   # the sound wave suits a voice channel; other channels set "motiv": "keins"
cw = int(max(w1, w2) + 120); ch = 330 if welle else 250
y1_txt, y2_txt = (128, 210) if welle else (40, 40 + int(g1 * 1.25))
x0, y0 = (W - cw) // 2, 330
sh = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
ds.rounded_rectangle([x0, y0 + 14, x0 + cw, y0 + ch + 14], 30, fill=tuple(int(c * 0.55) for c in GRUND) + (150,))
img = Image.alpha_composite(img.convert('RGBA'), sh.filter(ImageFilter.GaussianBlur(18)))
d = ImageDraw.Draw(img)
d.rounded_rectangle([x0, y0, x0 + cw, y0 + ch], 30, fill=GRUND + (255,), outline=RAND, width=3)
rnd = random.Random(7); n = 29; step = 20; bx = (W - (n - 1) * step) // 2
for i in range(n if welle else 0):   # sound wave motif (optional per channel)
    env = 0.35 + 0.65 * math.sin(math.pi * (i + 0.5) / n)
    hh = 10 + env * rnd.uniform(0.3, 1.0) * 70
    cx, cy = bx + i * step, y0 + 70
    d.rounded_rectangle([cx - 4, cy - hh / 2, cx + 4, cy + hh / 2], 4, fill=WELLE)
d.text(((W - w1) / 2, y0 + y1_txt), l1, font=s1, fill=F1)
d.text(((W - w2) / 2, y0 + y2_txt), l2, font=s2, fill=F2)
img.convert('RGB').save(d0 / 'cover.jpg', quality=93)
img.convert('RGB').crop((0, 285, 1080, 1635)).save(d0 / 'cover-profil-4zu5.jpg', quality=88)
print('ok', d0, l1, '|', l2, 'Schrift', g1, g2, 'Kanal', P['name'])
