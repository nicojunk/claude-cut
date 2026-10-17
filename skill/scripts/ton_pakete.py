#!/usr/bin/env python3
"""Ton-Zeitachse prüfen (15.10.2026, Abnahme R2: mastern.py erzeugte 1 Paket mit 4226 Samples Dauer, Apple-Player setzen dort 67 ms Stille).
Jedes AAC-Paket außer dem letzten muss 1024 Samples dauern und lückenlos auf das vorige folgen. Aufruf: python3 ton_pakete.py DATEI"""
import json, subprocess, sys
r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'packet=pts,duration', '-of', 'json', sys.argv[1]],
                   capture_output=True, text=True)
P = json.loads(r.stdout)['packets']
schlecht = [(i, p['pts'], p['duration']) for i, p in enumerate(P[:-1]) if int(p['duration']) != 1024]
luecken = [(i, P[i]['pts']) for i in range(len(P) - 1) if int(P[i + 1]['pts']) - int(P[i]['pts']) != int(P[i]['duration'])]
print(f'{sys.argv[1]}: {len(P)} Tonpakete, {len(schlecht)} mit Dauer != 1024, {len(luecken)} Lücken', schlecht[:3], luecken[:3])
sys.exit(1 if (schlecht or luecken) else 0)
