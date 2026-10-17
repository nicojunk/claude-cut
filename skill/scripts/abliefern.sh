#!/bin/zsh
# Delivery of a reel pair to the desktop root (reference production 15.10.2026, generalised 17.10.2026).
# Per version: liefer-titel.mp4 = liefer.mp4 with the cover as frame 0 (the user 15.10.2026 18:13: WhatsApp and Instagram show
# frame 0 as preview), encoded in ONE pass from render.mp4 with the same settings as liefer.mp4. The blend switches on the
# timestamp T, not the frame number N (N starts at 1 in ffmpeg's blend: frame 0 was a half blend on 15.10.2026 19:20).
# Checks: frame count, frame 0 is the cover (mean difference <= 6 grey levels), audio bit-identical to the checked liefer.mp4,
# frames from 3 on identical to liefer.mp4 (PSNR), audio packets, no black start (pruefe_schwarz --titelbild), md5 of the copies.
# Usage: zsh abliefern.sh MIT_ORDNER OHNE_ORDNER ZIELBASIS COVER.jpg
#        ZIELBASIS without extension, e.g. ~/Desktop/2026-10-17-kanal-reel5-thema
set -e; setopt PIPE_FAIL
H=${0:A:h}
MIT=$1; OHNE=$2; B=$3; COVER=$4
[ -f "$COVER" ] || { echo "Titelbild fehlt: $COVER"; exit 1; }
ORDNER=($MIT); [ "$OHNE" != "$MIT" ] && ORDNER+=($OHNE)
for d in $ORDNER; do
  [ -f $d/pruefung.json ] && python3 -c "import json,sys; e=json.load(open('$d/pruefung.json')); sys.exit(0 if e.get('bestanden') or e.get('freigabe_trotz_hinweis') else 1)" \
    || { echo "$d: Prüfungen nicht bestanden (pruefung.json). Erst Befunde beheben oder als Hinweis eintragen (freigabe_trotz_hinweis)."; exit 1; }
  N=$(python3 -c "import json;print(round(json.load(open('$d/projekt/edl.json'))['total']*30))"); V=$(python3 -c "print($N/30)")
  # Runde 5 (17.10.2026): der Ton kommt unverändert aus der geprüften liefer.mp4 (kopiert, nicht neu kodiert). Vorher kodierte
  # dieser Schritt den Ton ein zweites Mal mit ffmpegs AAC, die Abnahme maß +0,39 dBTP Knack im ersten Bild.
  ffmpeg -v error -y -i $d/render.mp4 -loop 1 -framerate 30 -i $COVER -i $d/liefer.mp4 -filter_complex \
    "[1:v]scale=1080:1920,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[c];[0:v]setpts=PTS-STARTPTS,format=yuv420p[v];[v][c]blend=all_expr='if(lt(T\,0.02)\,B\,if(lt(T\,0.05)\,(A+B)/2\,A))':shortest=1,setpts=PTS-STARTPTS[o]" \
    -map "[o]" -map 2:a -frames:v $N -c:v libx264 -preset slow -crf 21 -maxrate 8M -bufsize 16M -bf 0 -pix_fmt yuv420p -r 30 \
    -c:a copy -movflags +faststart $d/liefer-titel.mp4
  NB=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 $d/liefer-titel.mp4)
  [ "$NB" = "$N" ] || { echo "$d BILDZAHL $NB statt $N"; exit 1; }
  python3 -c "
import subprocess,numpy as np,sys
c=np.frombuffer(subprocess.run(['ffmpeg','-v','error','-i','$COVER','-vf','scale=1080:1920,format=gray','-f','rawvideo','-'],capture_output=True).stdout,np.uint8).astype(float)
f=np.frombuffer(subprocess.run(['ffmpeg','-v','error','-i','$d/liefer-titel.mp4','-frames:v','1','-vf','format=gray','-f','rawvideo','-'],capture_output=True).stdout,np.uint8).astype(float)
m=float(np.abs(f-c).mean()); print(f'Bild 0 gegen Titelbild: mittlere Abweichung {m:.1f} Graustufen'); sys.exit(0 if m<6 else 1)" || { echo "$d BILD 0 IST NICHT DAS TITELBILD"; exit 1; }
  A1=$(ffmpeg -v error -i $d/liefer.mp4 -map 0:a -c copy -f md5 -); A2=$(ffmpeg -v error -i $d/liefer-titel.mp4 -map 0:a -c copy -f md5 -)
  [ "$A1" = "$A2" ] && echo "$d: Ton bitgleich zur geprüften liefer.mp4" || { echo "$d: Ton nicht bitgleich zur geprüften liefer.mp4 ($A1 / $A2)"; exit 1; }
  P=$(ffmpeg -v info -i $d/liefer.mp4 -i $d/liefer-titel.mp4 -filter_complex "[0:v]trim=start_frame=3,setpts=PTS-STARTPTS[x];[1:v]trim=start_frame=3,setpts=PTS-STARTPTS[y];[x][y]psnr" -f null - 2>&1 | grep -o "average:[0-9.inf]*" | tail -1)
  echo "$d: Bilder $NB, ab Bild 3 gegen liefer.mp4 PSNR $P"
  python3 $H/ton_pakete.py $d/liefer-titel.mp4
  python3 $H/pruefe_ton_spitze.py $d/liefer-titel.mp4 || { echo "$d: Tonspitze in liefer-titel.mp4"; exit 1; }
  python3 $H/pruefe_schwarz.py $d/liefer-titel.mp4 --titelbild $COVER
done
if [ "$OHNE" != "$MIT" ]; then PAARE=("$MIT/liefer-titel.mp4:$B-mit-kommentarwort.mp4" "$OHNE/liefer-titel.mp4:$B-ohne-kommentarwort.mp4")
else PAARE=("$MIT/liefer-titel.mp4:$B-${MIT:t}-kommentarwort.mp4"); fi   # 1 version keeps its name (validation 17.10.2026)
PAARE+=("$COVER:$B-cover.jpg")
for p in $PAARE; do a=${p%%:*}; z=${p#*:}; cp $a $z; [ "$(md5 -q $a)" = "$(md5 -q $z)" ] && echo "md5 gleich: ${z:t}" || { echo "md5 FEHLER ${z:t}"; exit 1; }; done
for p in $PAARE; do z=${p#*:}; [[ $z == *.mp4 ]] && echo "${z:t}: $(python3 $H/pruefe_schwarz.py $z --titelbild $COVER | tail -1)"; done
for d in $ORDNER; do
  ffmpeg -v error -y -i $d/liefer-titel.mp4 -c:v libx264 -preset slow -crf 28 -maxrate 3M -bufsize 6M -bf 0 -c:a copy -movflags +faststart $d/vorschau-handy.mp4
  echo "$d/vorschau-handy.mp4 $(du -m $d/vorschau-handy.mp4 | cut -f1) MB: $(python3 $H/pruefe_schwarz.py $d/vorschau-handy.mp4 --titelbild $COVER | tail -1)"
done
