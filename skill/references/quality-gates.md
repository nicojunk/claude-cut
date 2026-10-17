# Quality gates: what is checked, what blocks, what is a hint

## The stop rule (the user 15.10.2026 16:13)
Everything visible or audible is fixed. Below the perception threshold it is a hint in the report: a sound up to 20 ms
at a word end, up to 3 still frames in a row, a measured value right at a limit, a word that speech recognition hears
differently far away from any cut. Reason: each strict round found 1 or 2 new micro findings and the delivery did not
converge ("seit über 12 Stunden"). At most 2 fix rounds per reel; after that the report lists what remains.

Never classify a finding without evidence. Look at the frames (`flimmern.png`, a frame strip
`ffmpeg -ss T -i liefer.mp4 -frames:v 6 -vf scale=270:480 f_%d.png`) or listen; a waiver names the measurement
(17.10.2026: a zoom finding first looked like a camera cut in the raw interview; the take showed factor 1.000, the face
band 1.000: a caption artefact, not a cut).

## Gates in order

| Step | Script | Checks | Blocks when |
|---|---|---|---|
| profile | `kanal.py pruefen` | folders, fonts, colour contrast, stop word syntax | anything missing or below contrast |
| selection | `plan_bauen.py auswahl` | compliance on the whole used span of every clip first; hook end never moved earlier: sound in its last 20 ms stops, missing afterglow comes from the raw clip after the end (the next piece of the same clip starts after it), only what the clip cannot give becomes `stille_danach`; fixed edges not in a sound (start: first 20 ms, end: last 20 ms); a raw clip starting inside a word is a hint for the user | any rule; exit 3 = compliance stop; a hook word stretched over a pause of >= 300 ms (false start, repetition) stops |
| words | `hook_ende.py` | the hook's last word complete: raw clip quiet in the 100 ms after the hook cut, Whisper without context hears the last word | either test fails |
| plan | `plan_bauen.py plan` | anchors (bounded to the next beat), 2 dopamine hits, every card in the drop-off map, `nutzen_bei`, stop words in the montage | any rule; exit 3 = compliance stop |
| montage | `montiere_take.py` | every seam in a measured pause (>= 200 ms) | seam inside a sentence |
| build | `baue_reel.py` | numbers on cards spoken, no reference default texts for other channels, stop words on cards and captions, no base colour left | any |
| build | `hyperframes check` | layout, overlapping content | errors (3 tries for load hiccups) |
| pre-render | `schnitte_vorab.py` | A every cut in silence (±15 ms below noise + 12 dB), B caption not > 250 ms off the audible onset after a pause, C no speech residue at piece edges, D no caption more than 120 ms after the audible onset (`einsatz.py`: never across a cut, onset at the take's speech level held 30 ms, a dip owned by the next aligned word is skipped; an early caption is only a hint here, consonant dips inside a word fool the envelope, pruefe_ms 3b measures early captions after the render), E card sound audible over a word end (click's first 15 ms > 10 dB above the voice in 1 to 7.9 kHz, voice still sounding, aligned word end 20 ms before to 60 ms after), F a clip mask cuts text above or below (inset top or bottom >= 0 on text whose line height is <= 1.05 of its size), G caption shown > 50 ms after its edl time (`projekt/untertitel-zeiten.json` from baue_reel.py; D used the planned time) | any; A2 no sound running into a cut on the render source take-ton.mp4 (40 ms > quietest 10 ms of that side + 12 dB) |
| pre-render | `pruefe_dramaturgie.py` | afterglow, benefit by 15 s, dopamine cards present, keyword card in "mit", first word after the hook captioned | any (length outside 20 to 90 s is a hint) |
| delivery | frame count | exactly round(total × 30) | differs |
| delivery | `ton_pakete.py` | every AAC packet 1024 samples, no gaps (Apple players insert silence otherwise) | any |
| delivery | `pruefe_ton_spitze.py` | true peak of the decoded delivery over the whole file (also `liefer-titel.mp4`), one-sided click in the first 60 ms (L and R differ > 6 dB above -20 dBFS) | > -1.5 dBTP or a one-sided click |
| delivery | `pruefe_schwarz.py` | picture starts at 0.000 s, audio ends before the picture, first/last frame not black, no brightness drop | any (exit 2 = not checkable = blocks) |
| delivery | `flimmern.py` | there-and-back brightness jumps per band, single odd frames (planned flashes, dips, the transition frame of a card entering on a state change and a planned card turn, edl `drehung`, excluded) | any |
| delivery | `eigenpruefung.py` | zoom jumps > 3 % between frames (re-measured on the face band, without the caption band for speaker and B-roll, and in the take), dark caption shadow at flash peaks, card content >= 2 % at appear + 0.35 s, 4 a top card over eyes or brows (largest card-white area against the Vision face box: card bottom below box top minus 18 % of its height) | any BEFUND line |
| delivery | `pruefe_ms.py` | 1 cuts in silence, 2 wording vs. the finished audio (Whisper), 3b caption start vs. aligned word start of every shown word (95 % within 120 ms, none > 250 ms early), 4 card anchors, 5 black start | cut not in silence, wording difference next to a cut, timing over limits |
| cover | `abliefern.sh` | frame 0 is the cover (mean diff <= 6 grey levels), audio bit-identical to the checked file, PSNR from frame 3, md5 of the copies | any |

`clip.py rendern` writes `pruefung.json` with every exit code and `bestanden`. When a hint stands after looking, add
`"freigabe_trotz_hinweis": "<what was measured, where>"`; `abliefern.sh` accepts that.

## Independent inspection (step 8)
My own checks are necessary, not sufficient: on 15.10.2026 independent inspectors found 5 defects in R4 v7 that every own
gate passed. Spawn a fresh agent (no history of this build) per reel pair, in parallel with the next reel, with this brief:

```
Du bist unabhängiger Prüfer für die Reels im Ordner <pfad>: Fassung "mit" und "ohne" Kommentarwort, oder nur die Fassung,
deren Ordner es gibt. Prüfe NUR diese Dateien: <pfad>/<fassung>/liefer.mp4, dazu je projekt/edl.json, woerter.json,
take.stuecke.json und plan.json, außerdem <pfad>/kanalregeln.md.
Schreib deinen eigenen Prüfcode (ffmpeg, numpy, opencv, faster-whisper sind installiert; python3.14 für Whisper/torch).
Prüfe Bild für Bild und auf die Millisekunde:
1 Jeder Schnitt (Pausenschnitt und Naht) liegt in Stille, kein angeschnittenes Wort, kein Wortrest an einem Stückrand.
  Laut heißt: mindestens 12 dB über dem Grundrauschen der Pause.
2 Untertitel: jedes Wort erscheint höchstens 250 ms vor und höchstens 120 ms nach seinem hörbaren Beginn; Wortlaut stimmt.
  Jeden Verdacht bestätigst du am Spektrum oder durch Hören, bevor er ein Befund wird: der Laut muss zu genau diesem Wort
  gehören, nicht zum Wort davor (ein kurzes tiefes Wort davor), nicht zum Raumrauschen einer Pause und nicht zur
  anderen Seite eines Schnitts. Eine reine Pegelkurve reicht nicht: bei einer tiefen Männerstimme (rund 10 ms je Schwingung)
  fällt ein 5-ms-Fenster zwischen zwei Stimmstößen um 15 dB, und Rauschen um -40 dB schwankt ebenso stark. Ein Konsonant
  mitten im Wort (das "v" in "Avatar", das "t" nach einem "Sch") ist kein Wortbeginn.
3 Karten: kein Element sichtbar vor seiner Animation, keine Karte steht leer oder halb leer, nichts verdeckt Augen oder Mund.
  Ein pulsierender gestrichelter "?"-Platzhalter oder eine blinkende Schreibmarke zählt als Inhalt (the user 15.10.2026 19:45).
  Leer heißt: ein Behälter steht länger als 15 Bilder ohne Text, Bild oder Platzhalter.
4 Kein Zoomsprung, kein Aufblitzen, kein Einzelbild, kein Bild des nächsten Clips im alten Layout.
  Geplant und kein Befund: Blitze und Abblenden aus edl.json; nach dem Hook ein Standbild mit Abblende, wenn
  take.stuecke.json beim ersten Stück "stille_danach" nennt (prüfe nur, dass die Helligkeit stetig fällt und kein
  Hänger entsteht); ein Zoom in eine Karte, wenn edl.json bei ihr "zoom": true nennt; eine Karte, die sich umdreht, wenn
  edl.json bei ihr "drehung" nennt.
5 Ton: kein Zischen, kein Rauschen in Pausen, keine hörbaren Lautheitssprünge an Nähten (Sprach-LUFS je 3 s vor und nach
  jeder Naht messen und nennen), -14 LUFS, True Peak unter -1,5 dBTP. Leise Kartentöne (Pop, Stempel) sind gewollt, sie
  dürfen aber nicht auf einem Schnitt oder über einem Wortende liegen.
6 Bild 0 und letztes Bild nicht schwarz, Bild beginnt bei 0,000 s.
7 Dramaturgie: Hook ab Bild 0; vom letzten Laut des Hooks bis zum ersten sichtbaren Bild des Wechsels mindestens 300 ms
  (ein Blitz ist etwa 6 Bilder vor dem Schnitt sichtbar); Nutzen bis Sekunde 15; Schluss mit Frage oder Aufruf.
8 Kanalregeln aus kanalregeln.md: kein Sperrwort im Ton, in Untertiteln oder auf Karten, jede Pflichtkarte vorhanden.
Regel (the user 15.10.2026): Sichtbares oder Hörbares ist ein BEFUND. Unter der Wahrnehmungsgrenze ist es ein HINWEIS:
ein Laut bis 20 ms an einem Wortende, bis 3 stehende Bilder, ein Messwert genau an der Grenze, eine Erkennungsabweichung
ohne Schnitt in 150 ms Nähe.
Ergebnis: je Fassung FREIGABE oder NICHT FREIGEGEBEN, jede Stelle mit Zeit in s, Bildnummer, Messwert und Einordnung.
Schreib den Bericht nach <pfad>/<fassung>/abnahme-unabhaengig.md.
Lies keine Skripte des Werkzeugs und keine anderen Prüfberichte (pruefung.txt, pruefung.json, bau.txt): dein Urteil soll
unabhängig sein. Deinen Prüfcode legst du unter <pfad>/abnahme-code/ ab.
```
Only BEFUND lines block. Fix the cause in reel.json (or, between rounds, in the tool), rebuild, re-render, re-inspect.

## Changing the tool (between rounds only)
1. Never while renders or checks run (zsh reads scripts incrementally; a mid-round change lost whole render sets).
2. After any change to `baue_reel.py`, `erklaerer.py`, `style.css` or `kanal.py`: run the regression, which rebuilds the
   8 delivered reference reels and must reproduce `index.html` and `edl.json` byte for byte:
   `zsh <workspace>/regression/vergleich.sh` (on the user's machine: `~/.claude/skills/smm-clipping-workspace/regression/`).
   On another machine (no delivered reels there): build `assets/beispiel-reel.json` before and after the change and
   compare `index.html` and the contact sheets; every difference must be one you intended.
   A deliberate change of the look is the exception: then say what changed and look at the new contact sheets.
3. Write every new trap into pitfalls.md with the measurement that found it.
