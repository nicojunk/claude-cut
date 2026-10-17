#!/usr/bin/env python3
"""SMM Clipping pipeline: one entry point for every phase, in a fixed order and with fixed load limits.

  python3 clip.py umgebung                       check tools, models, settings (run once per machine)
  python3 clip.py material KANAL CLIP [CLIP...]  HDR -> SDR (Apple tonemapper), transcribe (Whisper), compliance scan
  python3 clip.py bauen REELORDNER [mit|ohne] [--ab plan]   reel.json -> montage -> word times -> plan -> composition -> pre-checks
  python3 clip.py rendern REELORDNER [mit|ohne]  render (outside iCloud) -> master -> delivery encode -> all checks
  python3 clip.py pruefen REELORDNER [mit|ohne]  all checks again on the existing liefer.mp4 (no render)
  python3 clip.py abliefern REELORDNER           cover as frame 0, both versions to the desktop root, phone preview, report
  python3 clip.py alles REELORDNER               bauen + rendern (+ abliefern when reel.json has "titelbild")
  python3 clip.py stapel REELORDNER [...]        several reels overnight: builds one after another, 2 render lanes

Why fixed limits (reference production 15.10.2026): 9 parallel chains drove the load to 90 to 117, builds failed for no reason
and Whisper crawled. Now: builds run one after another, at most 2 renders and 1 Whisper/alignment job at a time (file locks in
~/.cache/smm-clipping/locks, shared by every Claude session on this machine). Renders go to the settings' renders folder
(default ~/Renders), never into iCloud (the user 16.10.2026: 101.5 s iCloud CPU per render inside the Desktop, 3.4 s outside).
Every step writes into the version folder (REELORDNER/mit, REELORDNER/ohne): bau.txt, pruefung.txt, pruefung.json.
"""
import fcntl, json, os, shutil, subprocess, sys, time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal

S = Path(__file__).resolve().parent
SKILL = S.parent
E = kanal.einstellungen()
PY = sys.executable
PY_ML = E['python_ml']
HF = os.environ.get('SMM_HYPERFRAMES', '0.8.166')   # pinned: the timing fixes were measured on 0.8.164 to 0.8.166
ML = {'ausrichten.py', 'hook_ende.py', 'pruefe_ms.py', 'transkribiere.py', 'woerter_je_stueck.py', 'untertitel_einsatz.py', 'eigenpruefung.py', 'ton_mischen.py'}
LOCKS = Path.home() / '.cache' / 'smm-clipping' / 'locks'


@contextmanager
def slot(art, n):
    """Wait for one of n machine-wide slots of a kind ('render' 2, 'ml' 1, 'bau' 1)."""
    LOCKS.mkdir(parents=True, exist_ok=True)
    while True:
        for k in range(n):
            f = open(LOCKS / f'{art}-{k}.lock', 'w')
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close(); continue
            try:
                yield k
            finally:
                fcntl.flock(f, fcntl.LOCK_UN); f.close()
            return
        time.sleep(5)


def py(script, *args, cwd=None, log=None, check=True, env=None):
    exe = PY_ML if script in ML else PY
    cmd = [exe, str(S / script), *map(str, args)]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    out = r.stdout + r.stderr
    if log:
        with open(log, 'a') as f:
            f.write(f'== {script} {" ".join(map(str, args))} (exit {r.returncode})\n{out}\n')
    if check and r.returncode:
        raise Fehler(f'{script} exit {r.returncode}: {out.strip().splitlines()[-1] if out.strip() else ""}', r.returncode)
    return r.returncode, out


class Fehler(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg); self.code = code


def zeit(rd, v, phase, sek):
    """Machine time per phase, measured (the user's benchmark: <= 60 min per reel pair)."""
    f = rd / 'zeiten.json'
    z = json.loads(f.read_text()) if f.exists() else {}
    z.setdefault(v, {})[phase] = round(z.get(v, {}).get(phase, 0) + sek, 1)
    z['summe_min'] = round(sum(x for vv in z.values() if isinstance(vv, dict) for x in vv.values()) / 60, 1)
    f.write_text(json.dumps(z, indent=1))


def werkzeugstand():
    """Fingerprint of the tool (scripts + style): a round is only comparable with the same tool (pitfall 37)."""
    import hashlib
    h = hashlib.sha1()
    for f in sorted(list(S.glob('*.py')) + list(S.glob('*.sh')) + [SKILL / 'assets' / 'style.css']):
        h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:12]


def zeiten_zuruecksetzen(rd, v, ab=None):
    f = rd / 'zeiten.json'
    if not f.exists():
        return
    z = json.loads(f.read_text())
    if v in z:
        alt = z[v]
        z.setdefault('fruehere_runden', []).append({v: alt})
        z[v] = {k: x for k, x in alt.items() if ab == 'plan' and k in ('montage', 'woerter')}
    z['summe_min'] = round(sum(x for vv in z.values() if isinstance(vv, dict) for x in vv.values()) / 60, 1)
    f.write_text(json.dumps(z, indent=1))


def varianten(rd, nur=None):
    R = json.loads((rd / 'reel.json').read_text())
    vs = [v for v in ('mit', 'ohne') if v in R['varianten']]
    return [nur] if nur else vs


def env_kanal(rd):
    env = dict(os.environ); env['SMM_KANAL'] = json.loads((rd / 'reel.json').read_text())['kanal']
    env['SMM_RENDERS'] = os.path.expanduser(E['renders']); return env


# ---------- material ----------
def ist_hdr(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=color_transfer,pix_fmt',
                        '-of', 'json', str(p)], capture_output=True, text=True)
    s = json.loads(r.stdout or '{}').get('streams', [{}])[0]
    return s.get('color_transfer') in ('arib-std-b67', 'smpte2084') or '10' in s.get('pix_fmt', '')


def material(name, clips):
    t_start = time.time()
    os.environ['SMM_KANAL'] = name
    P = kanal.profil()
    sdr = kanal.cache(P) / 'sdr'; sdr.mkdir(exist_ok=True)
    fertig, eingang = [], {}
    for c in clips:
        quelle = kanal.roh(c, P, sdr_erlaubt=False)
        ziel = quelle
        if ist_hdr(quelle):
            ziel = sdr / f'{quelle.stem}_SDR.mp4'
            if not ziel.exists() or ziel.stat().st_mtime < quelle.stat().st_mtime:
                print(f'HDR -> SDR (avconvert, Apples Tonemapper; ffmpeg-Filter ergeben Gelbstich): {quelle.name}', flush=True)
                subprocess.run(['avconvert', '--source', str(quelle), '--preset', 'Preset1920x1080', '--output', str(ziel), '--replace'],
                               check=True, capture_output=True)
        r = subprocess.run([PY, str(S / 'pruefe_take.py'), str(quelle)], capture_output=True, text=True)
        try:
            e = json.loads(r.stdout)
        except ValueError:
            e = {'stop': ['Eingangsprüfung nicht lesbar'], 'warnings': []}
        eingang[c] = e
        fertig.append((c, ziel))
    T = kanal.transkripte(P)
    offen = [(c, z) for c, z in fertig if not (T / f'{Path(c).stem}.woerter.json').exists()]
    if offen:
        tmp = kanal.cache(P) / 'transkription'; tmp.mkdir(exist_ok=True)
        links = []
        for c, z in offen:   # the transcript is named after the raw clip, the audio comes from the SDR copy
            l = tmp / f'{Path(c).stem}{z.suffix}'
            l.unlink(missing_ok=True); l.symlink_to(z); links.append(l)
        with slot('ml', 1):
            rc, out = py('transkribiere.py', *links, check=False, env=dict(os.environ))
            print(out[-2000:])
    DE = {'landscape after rotation': 'Querformat nach Drehung (nur mit "crop" im Stück nutzbar)', 'only ': 'nur ',
          'text burned in on': 'eingebrannter Text auf', 'sample frames: this is an edited reel, not a raw take':
          'Stichbildern: das ist ein geschnittenes Reel, kein Rohmaterial', 'will be upscaled to 1080x1920, expect softer picture':
          'wird auf 1080x1920 hochgerechnet, Bild wird weicher', 'fps: conform with -vf fps=30': 'fps, wird auf 30 fps gebracht',
          'sample frame(s) (signs, shirt print?): look before cutting': 'Stichbild(ern) (Schild, Shirt-Aufdruck?): vor dem Schnitt ansehen',
          'text on': 'Text auf'}
    def de(x):
        for k, v in DE.items():
            x = x.replace(k, v)
        return x
    mordner = Path(P.get('arbeitsordner') or kanal.cache(P)) / 'material'
    mordner.mkdir(parents=True, exist_ok=True)
    for c, z in fertig:
        W = json.loads((T / f'{Path(c).stem}.woerter.json').read_text())
        text = ' '.join(w['w'] for w in W)
        hits = kanal.stopp_treffer([text], P)
        b = [f'# Material {P["name"]}: {c} ({W[-1]["e"]:.1f} s, {len(W)} Wörter, {date.today().isoformat()})', '']
        e = eingang.get(c, {})
        for x in e.get('stop', []):
            b.append(f'- EINGANG: {de(x)}')
        for x in e.get('warnings', []):
            if x.startswith('HDR') and z != kanal.roh(c, P, sdr_erlaubt=False):
                b.append(f'- HDR-Aufnahme, SDR-Kopie mit avconvert erstellt: {z.name}')
            elif not x.startswith('HDR'):
                b.append(f'- Hinweis: {de(x)}')
        for g, m, _ in hits:
            w = next((x for x in W if kanal.re.sub(r'\W', '', x['w'].lower()).startswith(kanal.re.sub(r'\W', '', m.split()[0].lower()))), None)
            b.append(f'- STOPP {g}: "{m}"' + (f' bei {w["s"]:.2f} s' if w else '') + ' (diese Spanne nicht verwenden oder the user fragen)')
        b += ['', 'Prüfe Fachwörter und Namen im Text: Whisper verhört sie (ein Fachwort wird als ähnlich klingendes Wort geschrieben); Korrektur in reel.json "fix".', '', text, '']
        (mordner / f'{Path(c).stem}.md').write_text('\n'.join(b), encoding='utf-8')
        print(f'Material: {mordner / (Path(c).stem + ".md")}' + ('  STOPP-TREFFER' if hits else ''))
    print(f'Material fertig in {time.time() - t_start:.0f} s Maschinenzeit (Wartezeit auf Whisper eingeschlossen)')


# ---------- build ----------
def kanalregeln(rd):
    """The channel's rules as a file in the reel folder: the inspector checks them (validation 17.10.2026: nobody read them)."""
    P = kanal.profil(rd)
    z = [f'# Kanalregeln {P.get("anzeige", P["name"])}', '']
    z += [f'- {r}' for r in P.get('regeln', [])]
    z += [f'- Sperrwort /{r["muster"]}/: {r.get("grund", "")}' for r in P.get('stopp', [])]
    z += [f'- Pflichtkarte: spricht das Reel über /{r["wenn"]}/, braucht eine Karte /{r["text"]}/ ({r.get("grund", "")})' for r in P.get('pflicht_karten', [])]
    (rd / 'kanalregeln.md').write_text('\n'.join(z) + '\n', encoding='utf-8')


def bauen(rd, nur=None, ab=None):
    """ab='plan': keep montage and word times (fix rounds after a correction in reel.json or woerter-korrektur.json)."""
    env = env_kanal(rd)
    kanalregeln(rd)
    for v in varianten(rd, nur):
        D = rd / v; D.mkdir(exist_ok=True); log = D / 'bau.txt'; log.write_text('')
        (D / 'STOPP.md').unlink(missing_ok=True)
        zeiten_zuruecksetzen(rd, v, ab)
        if ab == 'plan' and (D / 'woerter.json').exists():
            if (D / 'woerter-korrektur.json').exists():
                with slot('ml', 1):
                    py('ausrichten.py', 'take.mp4', 'take.stuecke.json', 'woerter.json', cwd=D, log=log, env=env)
            pruefen = []
        else:
          with slot('bau', 1):
            t0 = time.time()
            rc, out = py('plan_bauen.py', 'auswahl', rd, v, log=log, check=False, env=env)
            if rc == 3:
                raise Fehler(f'{v}: STOPP Kanalregel im Rohmaterial, Bericht {D / "STOPP.md"}', 3)
            if rc:
                raise Fehler(f'{v}: Auswahl: {out.strip().splitlines()[-1]}', rc)
            rc, out = py('montiere_take.py', 'auswahl.json', 'take.mp4', '--lange-pausen', cwd=D, log=log, check=False, env=env)
            if rc:
                raise Fehler(f'{v}: Montage abgebrochen (Naht mitten im Satz?), siehe {log}: ' + out.strip().splitlines()[-1])
            zeit(rd, v, 'montage', time.time() - t0)
          with slot('ml', 1):
            t0 = time.time()
            (D / 'woerter.vor-ausrichtung.json').unlink(missing_ok=True)   # alignment always starts from this montage's Whisper times
            rc, out = py('woerter_je_stueck.py', 'take.mp4', 'take.stuecke.json', 'woerter.json', cwd=D, log=log, env=env)
            pruefen = [l for l in out.splitlines() if l.startswith('PRÜFEN')]
            py('ausrichten.py', 'take.mp4', 'take.stuecke.json', 'woerter.json', cwd=D, log=log, env=env)
            # the hook's last word complete: raw clip quiet right after the cut, and heard without context (round 3)
            rc, out = py('hook_ende.py', D, cwd=D, log=log, check=False, env=env)
            if rc:
                raise Fehler(f'{v}: Hook-Ende: ' + ' | '.join(l for l in out.strip().splitlines()[-2:]), rc)
            zeit(rd, v, 'woerter', time.time() - t0)
        t0 = time.time()
        py('pausen_absenken.py', D, log=log, env=env)
        zeit(rd, v, 'pausen_plan', time.time() - t0)
        rc, out = py('plan_bauen.py', 'plan', rd, v, log=log, check=False, env=env)
        if rc == 3:
            raise Fehler(f'{v}: STOPP Kanalregel, Bericht {D / "STOPP.md"}', 3)
        if rc:
            raise Fehler(f'{v}: Plan: {out.strip().splitlines()[-1]}', rc)
        with slot('bau', 1):
            t0 = time.time()
            for versuch in range(3):
                rc, out = py('baue_reel.py', 'plan.json', 'projekt', cwd=D, log=log, check=False, env=env)
                if rc and ('plan error' in out or 'build error' in out or 'STOPP' in out or 'Traceback' in out):
                    raise Fehler(f'{v}: ' + out.strip().splitlines()[-1], rc)   # a script error does not get better by retrying
                if rc:
                    continue
                c = subprocess.run(['npx', '--yes', 'hyperframes@' + HF, 'check'], cwd=D / 'projekt', capture_output=True, text=True)
                with open(log, 'a') as f:
                    f.write('== hyperframes check\n' + c.stdout[-3000:] + c.stderr[-1000:] + '\n')
                if 'Check passed' in c.stdout + c.stderr:
                    break
            else:
                raise Fehler(f'{v}: Bau oder hyperframes check 3 Mal fehlgeschlagen, siehe {log}')
        zeit(rd, v, 'bau', time.time() - t0)
        t0 = time.time()
        rc, out = py('schnitte_vorab.py', D, log=log, check=False, env=env)
        if rc:
            raise Fehler(f'{v}: angeschnittene Schnitte vor dem Render, siehe {log}', rc)
        rc, out = py('pruefe_dramaturgie.py', rd, v, log=log, check=False, env=env)
        print(out.strip())
        if rc:
            raise Fehler(f'{v}: Dramaturgie-Regel verletzt', rc)
        subprocess.run(['zsh', str(S / 'snap.sh'), str(D)], capture_output=True, text=True)
        # hyperframes splits the sheet into pages of 9 stills: copy every page of the newest snapshot run
        snaps = sorted((D / 'projekt' / '.hyperframes' / 'artifacts' / 'snapshots').glob('*/'), key=lambda p: p.stat().st_mtime)
        for alt in D.glob('kontaktbogen*.jpg'):
            alt.unlink()
        seiten = sorted(snaps[-1].glob('contact-sheet*.jpg')) if snaps else []
        for n_, sb in enumerate(seiten, 1):
            shutil.copy(sb, D / f'kontaktbogen-{n_}.jpg')
        zeit(rd, v, 'vorpruefung', time.time() - t0)
        print(f'{v}: gebaut. Kontaktbogen {len(seiten)} Seiten: {D}/kontaktbogen-1.jpg ...' + (f' | Whisper-Wörter prüfen: {len(pruefen)}' if pruefen else ''))


# ---------- render and check ----------
def rendern_eine(rd, v):
    env = env_kanal(rd)
    D = rd / v; log = D / 'pruefung.txt'; log.write_text('')
    with slot('render', 2):
        t0 = time.time()
        r = subprocess.run(['zsh', str(S / 'render_ausserhalb.sh'), '../render-roh.mp4', '--quality', 'looks', '--fps', '30'],
                           cwd=D / 'projekt', capture_output=True, text=True, env=env)
        (D / 'render.log').write_text(r.stdout[-5000:] + r.stderr[-5000:])
        if r.returncode:
            raise Fehler(f'{v}: Render fehlgeschlagen, siehe {D / "render.log"}')
        zeit(rd, v, 'render', time.time() - t0)
    t0 = time.time()
    py('mastern.py', 'render-roh.mp4', 'render.mp4', cwd=D, log=log, env=env)
    edl = json.loads((D / 'projekt' / 'edl.json').read_text())
    n = round(edl['total'] * 30); dauer = n / 30
    # delivery: exactly round(total*30) frames (the renderer appends 1 extra frame), no B-frames, audio ends 40 ms before the
    # picture with a 200 ms fade, every chain ends with setpts=PTS-STARTPTS (no black start, house rule since 09.10.2026)
    # Runde 5 (17.10.2026): Ton aus dem unkomprimierten Master (render-ton.wav), genau 1 AAC-Kodierung, Apple-Kodierer wenn vorhanden,
    # 20 ms Einblendung (Knack +0,39 dBTP im ersten Bild, unabhängige Abnahme Fall 2)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'render.mp4', '-i', 'render-ton.wav', '-map', '0:v', '-map', '1:a',
                    '-vf', 'setpts=PTS-STARTPTS', '-frames:v', str(n),
                    '-af', f'asetpts=PTS-STARTPTS,atrim=end={dauer - 0.04:.3f},afade=t=in:d=0.02,afade=t=out:st={dauer - 0.25:.3f}:d=0.2',
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-maxrate', '8M', '-bufsize', '16M', '-bf', '0', '-pix_fmt', 'yuv420p',
                    '-r', '30'] + kanal.aac_kodierer() + ['-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', 'liefer.mp4'], cwd=D, check=True)
    zeit(rd, v, 'mastern_liefern', time.time() - t0)
    return pruefen_eine(rd, v, log_neu=False)


def pruefen_eine(rd, v, log_neu=True):
    """All checks on the existing liefer.mp4 (also after a tool update, without a new render)."""
    env = env_kanal(rd); D = rd / v; log = D / 'pruefung.txt'
    if log_neu:
        log.write_text('')
    n = round(json.loads((D / 'projekt' / 'edl.json').read_text())['total'] * 30)
    nb = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                         '-of', 'csv=p=0', str(D / 'liefer.mp4')], capture_output=True, text=True).stdout.strip()
    erg = {'bilder_soll': n, 'bilder_ist': int(nb or 0), 'werkzeug': werkzeugstand()}
    dauer = 0.0
    for name, script, args, ml in (('ton_pakete', 'ton_pakete.py', ['liefer.mp4'], False),
                                   ('tonspitze', 'pruefe_ton_spitze.py', ['liefer.mp4'], False),
                                   ('schwarz', 'pruefe_schwarz.py', ['liefer.mp4'], False),
                                   ('flimmern', 'flimmern.py', ['liefer.mp4', 'projekt/edl.json', 'flimmern.png'], False),
                                   ('eigenpruefung', 'eigenpruefung.py', [D], True),
                                   ('ms', 'pruefe_ms.py', ['liefer.mp4', 'projekt/edl.json', 'take.stuecke.json', 'woerter.json'], True)):
        if ml:
            with slot('ml', 1):
                t1 = time.time(); rc, _ = py(script, *args, cwd=D, log=log, check=False, env=env); dauer += time.time() - t1
        else:
            t1 = time.time(); rc, _ = py(script, *args, cwd=D, log=log, check=False, env=env); dauer += time.time() - t1
        erg[name] = rc
    erg['bestanden'] = erg['bilder_soll'] == erg['bilder_ist'] and all(erg[k] == 0 for k in ('ton_pakete', 'tonspitze', 'schwarz', 'flimmern', 'eigenpruefung', 'ms'))
    (D / 'pruefung.json').write_text(json.dumps(erg, indent=1))
    zeit(rd, v, 'pruefen', dauer)
    print(f'{v}: {"alle Prüfungen bestanden" if erg["bestanden"] else "BEFUNDE, pruefung.txt lesen und nach references/quality-gates.md einordnen"} {erg}')
    return erg


def rendern(rd, nur=None):
    import threading
    fehler = []
    def lauf(v):
        try:
            rendern_eine(rd, v)
        except Exception as e:
            fehler.append(f'{v}: {e}')
    th = [threading.Thread(target=lauf, args=(v,)) for v in varianten(rd, nur)]
    [t.start() for t in th]; [t.join() for t in th]
    if fehler:
        raise Fehler('; '.join(fehler))


# ---------- delivery ----------
def abliefern(rd):
    R = json.loads((rd / 'reel.json').read_text())
    P = kanal.profil(rd) if not os.environ.get('SMM_KANAL') else kanal.profil()
    t0 = time.time()
    tb = R.get('titelbild')
    if not tb:
        raise Fehler('reel.json braucht "titelbild": {"zeit": s, "zeile1": "...", "zeile2": "...", "vorlage": "Nr aus references/hook-vorlagen.md"}')
    import hook_vorlage                    # Runde 5: der Text-Hook stammt aus einer der 50 Vorlagen, sonst keine Abgabe
    try:
        _nr, _muster = hook_vorlage.pruefe(tb.get('vorlage'), 'Titelbild')
    except ValueError as e:
        raise Fehler(str(e))
    print(f'Text-Hook nach Vorlage {_nr} "{_muster}": {tb["zeile1"]} / {tb["zeile2"]}')
    vs = varianten(rd)
    mit = rd / ('mit' if 'mit' in vs else vs[0]); ohne = rd / ('ohne' if 'ohne' in vs else vs[0])
    py('titelbild.py', mit, tb['zeit'], tb['zeile1'], tb['zeile2'], *([tb['versatz']] if tb.get('versatz') else []), env=env_kanal(rd))
    ziel = Path(os.path.expanduser(E['ablage'])) / f'{date.today().isoformat()}-{P.get("ablage_praefix", P["name"])}-reel{R.get("nummer", "")}-{R.get("thema", rd.name)}'
    r = subprocess.run(['zsh', str(S / 'abliefern.sh'), str(mit), str(ohne), str(ziel), str(mit / 'cover.jpg')], capture_output=True, text=True,
                       env=env_kanal(rd))
    (rd / 'abgabe.txt').write_text(r.stdout + r.stderr)
    zeit(rd, 'paar', 'abgabe', time.time() - t0)
    print(r.stdout[-3000:], r.stderr[-2000:])
    if r.returncode:
        raise Fehler(f'Abgabe fehlgeschlagen, siehe {rd / "abgabe.txt"}')


def alles(rd):
    bauen(rd); rendern(rd)
    if json.loads((rd / 'reel.json').read_text()).get('titelbild'):
        abliefern(rd)


def stapel(rds):
    """Builds strictly one after another; each finished build starts its render in the background (2 lanes via the lock)."""
    import threading
    th, bericht = [], {}
    for rd in rds:
        try:
            bauen(rd)
        except Fehler as e:
            bericht[rd.name] = f'BAU: {e}'; print(rd.name, 'BAU:', e); continue
        def lauf(rd=rd):
            try:
                rendern(rd)
                if json.loads((rd / 'reel.json').read_text()).get('titelbild'):
                    abliefern(rd)
                bericht[rd.name] = 'fertig'
            except Exception as e:
                bericht[rd.name] = f'RENDER/ABGABE: {e}'
        t = threading.Thread(target=lauf); t.start(); th.append(t)
    [t.join() for t in th]
    print(json.dumps(bericht, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    try:
        if a[0] == 'umgebung':
            sys.exit(subprocess.run([PY, str(S / 'umgebung.py')]).returncode)
        elif a[0] == 'material':
            material(a[1], a[2:])
        elif a[0] == 'bauen':
            ab = a[a.index('--ab') + 1] if '--ab' in a else None
            rest = [x for x in a[2:] if x not in ('--ab', ab)]
            bauen(Path(a[1]).resolve(), rest[0] if rest else None, ab)
        elif a[0] == 'pruefen':
            for v in varianten(Path(a[1]).resolve(), a[2] if len(a) > 2 else None):
                pruefen_eine(Path(a[1]).resolve(), v)
        elif a[0] == 'rendern':
            rendern(Path(a[1]).resolve(), a[2] if len(a) > 2 else None)
        elif a[0] == 'abliefern':
            abliefern(Path(a[1]).resolve())
        elif a[0] == 'alles':
            alles(Path(a[1]).resolve())
        elif a[0] == 'stapel':
            stapel([Path(x).resolve() for x in a[1:]])
        else:
            sys.exit(__doc__)
    except Fehler as e:
        print('ABBRUCH:', e, file=sys.stderr); sys.exit(e.code or 1)
