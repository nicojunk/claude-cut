#!/usr/bin/env python3
"""Environment check for SMM Clipping. Run once per machine (python3 clip.py umgebung); prints the exact command for every
missing piece. Exit 1 if something the pipeline needs is missing.

Measured working set (17.10.2026, macOS): ffmpeg 9.0, hyperframes 0.8.166 (npx), Python 3.15 with numpy 2.5 / Pillow 12 /
opencv 5.0, Python 3.14 with faster-whisper 1.2.1 + torch 2.10 + torchaudio 2.10, Whisper model large-v3, torchaudio
VOXPOPULI_ASR_BASE_10K_DE (German forced alignment), avconvert (macOS, HDR -> SDR), Swift tools gesicht + ocr (Apple Vision)."""
import importlib.util, json, os, platform, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanal

S = Path(__file__).resolve().parent
ok = True


def zeile(gut, was, hilfe=''):
    global ok
    print(('ok    ' if gut else 'FEHLT ') + was + ('' if gut or not hilfe else f'\n       -> {hilfe}'))
    ok &= gut


E = kanal.einstellungen()
zeile(kanal.CONFIG.exists(), f'Einstellungen {kanal.CONFIG}',
      f'mkdir -p {kanal.CONFIG.parent} && cp {S.parent / "kanaele" / "config-vorlage.json"} {kanal.CONFIG}  (Pfade anpassen)')
for t, hilfe in (('ffmpeg', 'brew install ffmpeg'), ('ffprobe', 'brew install ffmpeg'), ('npx', 'brew install node'),
                 ('zsh', 'macOS hat zsh; Linux: apt install zsh')):
    zeile(bool(shutil.which(t)), t, hilfe)
if shutil.which('ffmpeg'):
    f = subprocess.run(['ffmpeg', '-hide_banner', '-filters'], capture_output=True, text=True).stdout
    for flt in ('afftdn', 'acrossover', 'alimiter', 'loudnorm', 'ebur128', 'blend', 'silencedetect'):
        zeile(f' {flt} ' in f, f'ffmpeg-Filter {flt}', 'ffmpeg mit vollem Filtersatz installieren (brew install ffmpeg)')
    enc = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    zeile('libx264' in enc, 'ffmpeg-Encoder libx264', 'brew reinstall ffmpeg')
zeile(platform.system() == 'Darwin' and bool(shutil.which('avconvert')), 'avconvert (HDR -> SDR mit Apples Tonemapper)',
      'nur macOS. Ohne avconvert keine iPhone-HDR-Clips verarbeiten (ffmpeg-Tonemapping ergibt Gelbstich)')
if shutil.which('npx'):
    r = subprocess.run(['npx', '--yes', 'hyperframes', '--version'], capture_output=True, text=True, timeout=180)
    v = (r.stdout.strip().splitlines() or ['?'])[-1]
    zeile(r.returncode == 0 and v.startswith('0.8'), f'hyperframes {v} (getestet 0.8.164 bis 0.8.166)', 'npx --yes hyperframes@0.8.166 --version')
for mod in ('numpy', 'PIL', 'cv2'):
    zeile(importlib.util.find_spec(mod) is not None, f'{sys.executable}: {mod}',
          f'{sys.executable} -m pip install --break-system-packages ' + {'PIL': 'pillow', 'cv2': 'opencv-python'}.get(mod, mod))
ml = E['python_ml']
r = subprocess.run([ml, '-c', 'import faster_whisper, torch, torchaudio, numpy, cv2; print(faster_whisper.__version__, torch.__version__, torchaudio.__version__)'],
                   capture_output=True, text=True)
zeile(r.returncode == 0, f'{ml}: faster-whisper, torch, torchaudio, numpy, opencv ({r.stdout.strip() or r.stderr.strip().splitlines()[-1:] })',
      f'{ml} -m pip install --break-system-packages faster-whisper torch torchaudio numpy opencv-python  (Python 3.11 bis 3.14; '
      f'"python_ml" in {kanal.CONFIG} auf diesen Interpreter setzen)')
hf = Path.home() / '.cache' / 'huggingface' / 'hub' / 'models--Systran--faster-whisper-large-v3'
zeile(hf.exists(), 'Whisper-Modell large-v3 (3 GB)',
      f'{ml} -c "from faster_whisper import WhisperModel; WhisperModel(\'large-v3\', device=\'cpu\', compute_type=\'int8\')"')
ta = Path.home() / '.cache' / 'torch' / 'hub' / 'checkpoints' / 'wav2vec2_voxpopuli_base_10k_asr_de.pt'
zeile(ta.exists(), 'Ausrichtungsmodell VOXPOPULI_ASR_BASE_10K_DE (Deutsch)',
      f'{ml} -c "import torchaudio; torchaudio.pipelines.VOXPOPULI_ASR_BASE_10K_DE.get_model()"')
for b in ('gesicht', 'ocr'):
    p = S / 'bin' / b
    gut = p.exists() and os.access(p, os.X_OK) and subprocess.run([str(p)], capture_output=True).returncode in (0, 1, 2)
    zeile(gut, f'scripts/bin/{b} (Apple Vision)', f'swiftc -O {S / (b + ".swift")} -o {p}')
kd = Path(os.path.expanduser(E['kanaele']))
profile = sorted(kd.glob('*.json')) if kd.exists() else []
zeile(bool(profile), f'Kanal-Profile in {kd}: {", ".join(p.stem for p in profile) or "keine"}',
      f'mkdir -p {kd} && cp {S.parent / "kanaele" / "vorlage.json"} {kd}/<kanal>.json  (references/creator-profile.md)')
rd = Path(os.path.expanduser(E['renders'])); rd.mkdir(parents=True, exist_ok=True)
frei = shutil.disk_usage(rd).free / 1e9
zeile(frei > 20, f'Render-Ordner {rd} (außerhalb iCloud), frei {frei:.0f} GB', 'mindestens 20 GB frei halten (ein Render legt ~1.900 Bilder ab)')
zeile('Mobile Documents' not in str(rd.resolve()) and 'Desktop' not in str(rd.resolve()).split(os.sep)[-1:],
      'Render-Ordner liegt nicht in iCloud', '"renders" in den Einstellungen auf einen Ordner außerhalb von Desktop/Dokumente setzen')
print('UMGEBUNG', 'VOLLSTÄNDIG' if ok else 'UNVOLLSTÄNDIG')
sys.exit(0 if ok else 1)
