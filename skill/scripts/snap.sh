#!/bin/zsh
# Standbilder je Karte (Auftritt +0,4 s, Mitte, Ende -0,15 s) plus erstes und letztes Bild, Kontaktbogen im Projekt.
cd ${1:-.}/projekt
T=$(python3 -c "
import json;E=json.load(open('edl.json'))
t=[0.0]
for c in E['cards']:
    a,b=c['appear'],c['end']; t+= [a+0.4,(a+b)/2,max(a+0.5,b-0.15)]
t.append(E['total']-0.1)
print(','.join(f'{x:.2f}' for x in sorted(set(round(v,2) for v in t))))")
npx --yes hyperframes@${SMM_HYPERFRAMES:-0.8.166} snapshot --at=$T --no-end > /dev/null 2>&1
D=.hyperframes/artifacts/snapshots/$(ls -t .hyperframes/artifacts/snapshots/ | head -1)
ls $D/contact-sheet*.jpg | sed "s|^|$PWD/|"
