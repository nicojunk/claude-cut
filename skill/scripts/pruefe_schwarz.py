#!/usr/bin/env python3
"""Schwarzstart-/Schwarzende-Prüfung vor jeder Abgabe (Ersatz für video-kein-schwarz.py, das auf diesem Rechner fehlt).
Exit 0 = bestanden, 1 = fehlerhaft, 2 = nicht prüfbar (gilt wie fehlerhaft).
Prüft: Bildspur beginnt bei 0,000 s (erstes Video-Paket pts), Tonspur endet nicht nach dem Bild,
erstes und letztes Bild nicht schwarz (mittlere Helligkeit Y > 16) und kein Helligkeitssturz am Rand: das letzte Bild hat
mindestens 60 % der Helligkeit der 5 Bilder davor, das erste mindestens 60 % der 5 danach (15.10.2026: Fassung 6 hatte 1 Zusatzbild
mit Helligkeit 31 hinter Bildern mit 129, die Schwelle 16 ließ es durch).
Titelbild (the user 15.10.2026 18:13: Titelbild als erstes Bild für die WhatsApp-Vorschau): mit --titelbild COVER.jpg darf Bild 0 das
Titelbild sein. Bedingung: Bild 0 weicht im Mittel höchstens 6 Graustufen vom Titelbild ab, hat Helligkeit >= 60 und Inhalt
(Standardabweichung >= 30). Dann gilt der Sturz-Test am Anfang ab Bild 2 (erstes reines Videobild, Bild 1 ist die Überblendung).
Ein schwarzes oder leeres Bild 0 fällt weiterhin durch, weil es nicht dem Titelbild entspricht."""
import json, subprocess, sys
f = sys.argv[1]
titel = sys.argv[sys.argv.index('--titelbild') + 1] if '--titelbild' in sys.argv else None
def probe(sel, entries):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', sel, '-show_entries', entries, '-of', 'json', f], capture_output=True, text=True)
    return json.loads(r.stdout or '{}')
try:
    pk = probe('v:0', 'packet=pts_time')['packets'] if False else None
    v = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-read_intervals', '%+#1', '-show_entries', 'frame=pts_time,best_effort_timestamp_time', '-of', 'json', f], capture_output=True, text=True).stdout)['frames'][0]
    v0 = float(v.get('pts_time', v.get('best_effort_timestamp_time')))
    sv = probe('v:0', 'stream=start_time,duration')['streams'][0]; sa = probe('a:0', 'stream=start_time,duration')['streams']
    vend = float(sv['start_time']) + float(sv['duration'])
    aend = float(sa[0]['start_time']) + float(sa[0]['duration']) if sa else 0.0
    def luma(ss):
        r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', ss, '-i', f, '-frames:v', '1', '-vf', 'scale=64:-2,format=gray', '-f', 'rawvideo', '-'], capture_output=True)
        return sum(r.stdout) / max(1, len(r.stdout))
    l0 = luma('0'); lend = luma(f'{max(0, vend - 0.05):.3f}')
    def randbilder(args):
        r = subprocess.run(['ffmpeg', '-v', 'error'] + args + ['-i', f, '-vf', 'scale=54:96,format=gray', '-f', 'rawvideo', '-'], capture_output=True)
        n = len(r.stdout) // (54 * 96)
        return [sum(r.stdout[i * 5184:(i + 1) * 5184]) / 5184 for i in range(n)]
    anf = randbilder(['-t', '0.2'])[:6]; end = randbilder(['-sseof', '-0.3'])[-6:]
    med = lambda xs: sorted(xs)[len(xs) // 2]
    sturz_anf = len(anf) >= 6 and anf[0] < 0.6 * med(anf[1:])
    titel_ok = None
    if titel:
        import numpy as np
        g = lambda a: np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error'] + a, capture_output=True).stdout, np.uint8).astype(float)
        c = g(['-i', titel, '-vf', 'scale=1080:1920,format=gray', '-f', 'rawvideo', '-'])
        b0 = g(['-i', f, '-frames:v', '1', '-vf', 'scale=1080:1920,format=gray', '-f', 'rawvideo', '-'])
        abw, hell, std = float(np.abs(b0 - c).mean()), float(b0.mean()), float(b0.std())
        titel_ok = abw <= 6 and hell >= 60 and std >= 30
        if titel_ok:
            anf2 = randbilder(['-t', '0.35'])[2:8]
            sturz_anf = len(anf2) >= 6 and anf2[0] < 0.6 * med(anf2[1:])
            l0 = max(l0, 17)
    sturz_end = len(end) >= 6 and end[-1] < 0.6 * med(end[:-1])
    lend = end[-1] if end else lend
except Exception as e:
    print('NICHT PRÜFBAR', e); sys.exit(2)
if titel and not titel_ok:
    print(f'Bild 0 ist NICHT das Titelbild (Abweichung {abw:.1f}, Helligkeit {hell:.0f}, Streuung {std:.0f})'); sys.exit(1)
if titel_ok:
    print(f'Bild 0 = Titelbild (Abweichung {abw:.1f} Graustufen, Helligkeit {hell:.0f}, kein Schwarz), Sturz-Test ab Bild 2;', end=' ')
ok = abs(v0) < 0.0005 and aend <= vend + 0.001 and l0 > 16 and lend > 16 and not sturz_anf and not sturz_end
print(f"Bild beginnt bei {v0:.3f} s, Bild endet {vend:.3f} s, Ton endet {aend:.3f} s, Helligkeit Anfang {l0:.0f} Ende {lend:.0f}{', HELLIGKEITSSTURZ AM ENDE' if sturz_end else ''}{', HELLIGKEITSSTURZ AM ANFANG' if sturz_anf else ''}: {'Prüfung bestanden' if ok else 'FEHLERHAFT'}")
sys.exit(0 if ok else 1)
