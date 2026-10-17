# Pitfalls: measured traps and where the fix lives

Each item: what went wrong, how it was measured, what the pipeline does now. Numbers 1 to 40 come from the reference
production 14 to 16.10.2026 (found by independent inspectors or Nico), 41 onwards from building this skill 17.10.2026.
Read the section that matches a failing check.

## Audio
1. **afftdn delays audio by exactly 25.0 ms** (cross-correlation): word ends were cut at every seam. montiere_take fetches
   25 ms more and trims them after the filter.
2. **loudnorm makes a ~100 ms pts jump** about 3 s before the end (flush of its lookahead). `asetpts=N/SR/TB` after every
   loudness filter; `ton_pakete.py` blocks any AAC packet != 1024 samples (Apple players insert silence).
3. **Fixed noise reduction dulled the voice** (nf -30: speech 1 to 13 kHz -7 to -13 dB, heard as "Zischen", Nico 15.10.).
   `entrauschen.py` calibrates nf per raw clip (speech loss <= 1 dB in 1 to 10 kHz), cached per channel with a content key.
4. **Brighter speech made S-peaks 10 dB louder**: split-band de-esser in mastern.py (crossover 4.8 kHz, compressor on the
   high band, threshold = p80 of HF level in speech, ratio 8, attack 0.5 ms). ffmpeg `deesser` was too weak.
5. **Compression lifted room tone in pauses**: `pausen_absenken.py` lowers gaps >= 120 ms between words by 14 dB (35 ms
   cosine ramps) on a separate render copy of the take; the edit is measured on the original.
6. **loudnorm linear=true silently falls back to dynamic** when the gain would push true peak over the limit. mastern.py
   uses a fixed gain to -14 LUFS plus alimiter at 4x oversampling (true peak <= -1.5 dBTP asserted).
7. **A pop sound over a word end masked it** ("Auge" heard as "auf"). Sounds move before the last 120 ms of a word and
   100 ms away from cuts; on short words 40 ms after the voiced end (autocorrelation, not the aligned end, which includes
   the exhale).
8. **Lip hum or murmur after a piece's last word** (R4 "Warum?" + 150 ms hum). End the piece in real silence; fade 5 to
   40 ms only where needed (`blende_aus`).

## Word times and captions
9. **Whisper starts sit 190 to 520 ms early** after pauses. Word times come from forced alignment per montage piece
   (`ausrichten.py`, German wav2vec2), Whisper only for the text.
10. **CTC put the first word of a piece onto the piece start** (R3 "Hör" 0.34 s early in the louder room tone of the
    hook). Fixed 17.10.2026: the alignment window starts 120 ms before the first sound of the piece (piece noise floor +
    12 dB for 30 ms), and the first word of a piece moves onto its own onset when it is glued to the piece start (later) or
    clearly late (earlier). Onset = 30 ms above max(piece floor + 12 dB, word peak - 20 dB): a single breath blip once moved
    a correct "Den" 0.75 s too early. Rebuilt R3 against the hand-corrected delivery: median 0 ms, p95 20 ms, max 112 ms
    (that one: "Meine" now 63.16 s, the audible onset is 63.19 s, the delivery had 63.27 s).
11. **A stricter onset threshold (+26 dB) put "Du" 0.63 s late** in a noisy interview opening: use the speech threshold
    sustained 30 ms, never a high fixed level.
12. **Never move a word start later from the envelope** (aspirated "Kostenfrei": caption 299 ms late). Onset corrections
    only move earlier; starts inside silence have their own rule.
13. **First match finds the wrong occurrence** ("Wie" 3.4 s before "Wie klingst"). Use 2-word anchors or "Wort@2".
14. **Digits must be spoken words for the aligner**: `zahlwort.py` covers any number, ordinals ("26." → sechsundzwanzigsten),
    dates, decimals, percent, times. The old fixed table (7, 10, 11, 26, 35, 37) failed on every other number.
15. **Changing montage edges invalidates old word times**: clip.py always re-transcribes and re-aligns after a montage.
16. **Speech recognition hears a word differently** (R3 "Brust" as "Wurst", R1 "bei einem" as "deinem"). Far from any
    cut: hint, confirm by ear; within 150 ms of a cut: block (clipped word). pruefe_ms.py sorts them.

## Edit and timing
17. **GSAP positions printed with 4 decimals fire 1 frame late** for every third frame. baue_reel snaps every position
    within 0.01 frame after an edge to n/30 - 0.0005 (`bildgenau`, `fs`, `ds`, `dd`).
18. **A pause cut next to a montage seam leaves a 1-frame sliver**: cuts within 120 ms snap onto the seam (`naehte`).
19. **State changes 1 to 4 frames off a seam** show the next piece in the old layout. Changes snap onto a seam or cut
    within 0.3 s before (0.5 s for dips); anchored cards follow; captions end at the first seam after their last word.
20. **Fixed -35 dB silence detection cut quiet word tails** (R2: 4 cuts). Cut edges move until 40 ms before and after lie
    below noise floor + 10 dB; `schnitte_vorab.py` blocks before the render.
21. **The renderer adds 1 frame** when the total is not a whole frame count: the delivery is encoded with
    `-frames:v round(total*30)`, and a last-frame brightness drop fails `pruefe_schwarz.py`.
22. **Two zoom tweens on one element jump when the shorter ends** (start zoom + drama zoom: 8 % at 1.53 s). The start
    zoom is skipped when a drama segment starts at 0; any new zoom: check overlapping tweens.
23. **Drama zoom ran half a frame past the state set**: it ends 1 ms before the next state.
24. **A dip centred on the first word, not on the visible cut, flashed the face**: dips start at the seam, opaque on the cut.
25. **The hook switched too early** (flash on the last word): 300 ms afterglow, checked in plan and after the build.

## Cards and picture
26. **An element visible 1 frame before its animation**: every fromTo with immediateRender:false gets its start state set
    at time 0.
27. **Navy cards empty for 1.1 to 1.5 s after entering** and the R2 freebie card half empty until "sieben": dashed "?"
    placeholders that pulse until the content lands; eigenpruefung measures content at appear + 0.35 s.
28. **Text faded over 8 to 12 frames reads as grey**: opacity in 2 to 3 frames, motion separately; no dimmed text.
29. **GSAP x/y/scale on an SVG element with its own transform overwrites it**: wrap in `<g transform>`, tween the child.
30. **clip-path on inline text over 2 lines shows only line 1**: each line its own block.
31. **White flash over cards and captions washes text out**: flash layer under cards and captions; white captions start
    4 frames after a flash peak and pause during it.
32. **White captions on a bright background** (contrast < 3:1): the build moves the block down in 20 px steps until 3:1,
    else warns; the caption shadow uses the channel dark.
33. **A whole-frame zoom estimate reacts to a big caption word** (R3 2.733 s, factor 0.921): eigenpruefung re-measures on
    the face band (1.000 = no jump) and in the take (same factor = camera cut in the raw footage). A real jump (R1 v2
    frame 45, 1.084) shows in the face band too and still blocks.
34. **A card entering on a state change stands half in the change frame by design**: flimmern.py excludes that one frame.
35. **Blend expressions count N from 1** in ffmpeg: frame 0 was a half blend. The cover blend uses the timestamp T;
    frame 0 is verified against the cover file (<= 6 grey levels).
36. **A neon brand accent vanished on white cards** (a neon green, 1.15:1). Profile contrast rule: accent >= 2:1 on white;
    the bright colour goes on dark surfaces via css_zusatz.

## Process
37. **Never change the tool mid-round** (rounds 7, 7b and 8 each lost a full render set; 2 of 5 findings were own
    regressions). Collect, then change between rounds, run the regression.
38. **Never book a finding as an artefact without looking** at the frames or listening, and never trust a remembered
    claim in a waiver: name the measurement.
39. **More than 2 renders plus 1 Whisper job overloads the machine** (load 90 to 117, spurious build failures, Whisper 4x
    slower). clip.py holds machine-wide slots.
40. **Renders inside the iCloud Desktop cost ~100 s iCloud CPU each**: hyperframes writes ~1,900 frames next to the output.
    `render_ausserhalb.sh` renders into the settings' `renders` folder and moves only the finished file.
41. **Never edit a zsh script while a chain runs it**: zsh reads scripts incrementally.
42. **Caches keyed by file name went stale** (faces, noise calibration after a re-cut, or two channels with the same
    camera file name): caches carry a content key (size + first and last MiB).
43. **The montage must snap a piece start into the silence before the wanted word**, not into any 60 ms gap (a gap inside
    "kannst" let the end of the unchosen sentence in). Measure with `naehte.py` before fixing an edge by hand.
44. **iPhone HDR (HLG, 10 bit) through ffmpeg filters gets a yellow cast**: `clip.py material` converts with avconvert
    (Apple's tonemapper) and the pipeline refuses HDR sources.
45. **hyperframes updates can shift timing**: the version is pinned (`SMM_HYPERFRAMES`, default 0.8.166); GSAP is a local
    copy (3.14.2), so renders do not depend on the CDN.
46. **A hook end checked on Whisper times passed with a sound in the afterglow** (probe 17.10.2026: 23 ms from the last
    sound to the first visible flash frame, although the cut came 356 ms after the word). `plan_bauen.py auswahl` measures
    on the 10 ms envelope, ends the hook before a sound and adds `stille_danach` with a fade when the silence is short.
47. **Forced alignment placed words up to 207 ms late after a pause**, and every own check used the same model, so none
    saw it. `einsatz.py` measures the audible onset on a 1 ms envelope; `ausrichten.py` moves starts only earlier,
    `schnitte_vorab.py` D checks each caption against it before the render.
48. **A rule "word start out of the silence" moved 10 words up to 675 ms late** (validation case 2). Removed: an aligned
    start is never moved later (see 12).
49. **A fixed -35 dB silence threshold is blind on a noisy recording**: pauses above the noise floor were never capped.
    The threshold is max(-35 dB, noise floor + 15 dB); a quiet studio keeps -35 dB.
50. **Loudness jumped +6.2 LU at a seam between two recordings** (probe aufnahme-27.mov to aufnahme-33.mov). The montage matches each
    piece's speech loudness to the median of all pieces (at most ±8 dB); `gain` adds to that.
51. **Whisper splits compounds and dates** ("7 -Tage -Challenge", "26 .10."): tokens starting with "-" or "." join the
    word before automatically.
52. **A punch-in was not reset on an invisible speaker to speaker change** and the next cut jumped -3.8 % (probe
    52.833 s). Without a visible change (other state, flash, dip) nothing is reset; eigenpruefung calls a zoom change
    "gewollt" only for a visible change.
53. **A card anchor searched to the end of the reel landed in a later beat.** Anchors are searched only up to the next
    beat; nested fields (`rows[].at`) are resolved the same way.
54. **A fixed edge checked with ±30 ms was refused inside a measured 60 ms pause** (round 2 case 1, 125.467 s in
    125.43 to 125.49 s). A start is checked on its first 20 ms, an end on its last 20 ms; a start at the clip start is not
    checked. The same check then found a real defect round 1 had let through: a fixed start at 5.833 s inside the word
    "Den" (5.74 to 5.89 s), which would have cut its first 90 ms.
55. **Two parallel material runs overwrote one dated report** and a stop hit vanished from it: one report per clip in
    `<arbeitsordner>/material/`.
56. **Blood drawn in the channel accent** (unreadable as a danger colour): colour role `signal`.
57. **A card container waited empty for a later anchor** (kurve 1.5 s, ki_oder_mensch sentence field): the first content
    lands on `at`, or placeholders hold the space (a blinking caret, dashed "?" rows), which count as content.
58. **The audible-onset check reported 5 wrong captions on a deep male voice with room noise around -40 dB** (round 2
    case 2): noise that swings 15 dB looked like a word start, a 5 ms window falls between two glottal pulses of a
    100 Hz voice, the window reached across a pause cut, and a short deep word was taken as the start of the word after
    it. Proved by level curve and spectrum (the voiced vowel near 200 Hz centroid, the noise without periodicity). The
    check now stops at the last cut, needs the take's speech level (p10 + 12 dB) held for 30 ms, and leaves a dip to a
    word whose aligned start lies after it. Still finds the 3 late captions the independent inspection found in the probe.
59. **The millisecond check judged fragments that are never shown**: "7 -Tage -Challenge" is shown as one caption word,
    the hidden "-Tage" was reported 611 ms early. pruefe_ms 3b only checks words that are in a caption group.
60. **A caption popping in on a dark B-roll still read as a zoom jump** (0.920 at 16.867 s; no face there, and the
    caption lies in the face band). eigenpruefung measures speaker and B-roll frames again without the caption band
    (rows 440 to 690 of 960, contrast equalised): 1.001. Synthetic jumps of 4 and 6 % still measure 1.04 and 1.06.
61. **A card turning over read as flicker** (visitenkarte_flip at 36.30 s: edge-on, the dark card is thin and the paper
    shows for a frame). The build writes the turn's start as `drehung` into edl.json; flimmern.py skips those 13 frames.
62. **A card stamp landed exactly on a cut** (round 2 case 2, 37.833 and 51.467 s; pruefe_ms read it as a clipped word).
    The aligner had pulled the word start onto the cut, the sound followed the word start, and the "at most 200 ms before
    the card" cap undid the move away from the cut. A sound still within 100 ms of a cut now goes back to the card's own
    time when that is clear, else 100 ms behind the cut. The pre-render check cannot see this (it measures the take
    without effects): look at `note: Ton` lines in bau.txt.
63. **The planned fade to dark after the hook read as flicker** (18 -> 2 -> 15 at 9.00 to 9.23 s: the fade, then the
    flash). flimmern.py skips the `stille_danach` window of take.stuecke.json.
64. **On a deep male voice the aligner's onset correction pulled starts 160 to 225 ms early** (case 2: 7 words;
    pruefe_ms 3b: 95 % within 167 ms, limit 120). The aligner now uses the same extra rules as the
    check (pitfall 58). A start that lands on a cut also drags card sounds along (62).
65. **The envelope reads a consonant dip inside a word as a pause** and then puts the onset on the vowel after it: a word
    starting with "Scht" after a number (the fricative, the t-closure, the vowel 300 ms later) and "Avatar" after "mein" (the "v") came out
    "273 / 258 ms early" although both captions sit on the word's first sound. Stricter dip rules (10 ms smoothing, dip
    near the speech level) removed these but also lost "mir", a real late caption of the probe. So the envelope check D
    blocks only late captions; early ones are measured by forced alignment on the finished audio (pruefe_ms 3b).
66. **An automatic hook trim cut the last word of both validation hooks** (round 2: "gut" to its "g", "falsch" to its "f";
    found only by the independent inspection). The trim read the closure inside the word as "word over, then residue".
    Every own check passed: the afterglow was measured on the already trimmed take, and Whisper with the sentence as
    context still wrote the word. Now: the hook end is never moved earlier; missing afterglow comes from the raw clip
    after the end (real picture and room tone); `hook_ende.py` fails the build when the last word's sound in the raw clip
    (from its start, gaps up to 120 ms: a stop closure stays inside, a breath after a longer silence does not) runs past
    the hook cut, or when Whisper without context does not hear the last word.
67. **A fade to dark that starts before the last sound and then holds 6 identical frames** reads as a cut word and a hang.
    `stille_danach` now fades from the piece end over the whole added silence, straight into the flash.
68. **Hard audio cuts click in room noise** (round 2 case 2: 11 and 15 dB high-pass spikes; inaudible in a quiet room).
    The render's copy of the take gets 8 ms ramps to zero at every range edge.
69. **A raw clip that starts inside the first word**: the render started hard, the master and the AAC encode turned it
    into a left-channel spike of +0.4 dBTP. The delivery fades in over 10 ms; the missing start of the word is material,
    `plan_bauen auswahl` names it as a hint for Nico.
70. **A card element anchored on the last word before a cut showed for 1 frame** (the "not equal" badge of the premium
    balance). Cards get their end time (`_ende`); late events move inside the card.
71. **The afterglow check measured on the loudness-matched take** and found a low hum 6 dB over the room floor in one
    version only ("ohne" -33 ms, "mit" 347 ms for the same hook piece). The last sound of the hook is measured in the raw
    clip (`naehte.letzter_laut`: local floor + 10 dB, voiceless endings included), by plan_bauen and pruefe_dramaturgie alike.

72. **Captions vanished for 5 frames after a flash** (round 3: 145 to 229 ms late). The pause cut before a flash section took
    the word's lead-in with it. `keep_ranges` keeps 220 ms before the first word of a section with `flash`.
73. **Soft onsets started 138 to 171 ms late** ("Morgen", "Ergebnis"): CTC puts the start on the vowel, the envelope sees
    no dip in connected speech. `anlaut.py` finds the voiceless fricative in the high band and the nasal at the drop of the
    mid band (not "w": a voiced w reaches back into the previous word's "sch"); only earlier, 40 to 250 ms.
74. **A seam in an inhale with a voice residue** (case 1, 7.5 s). `plan_bauen raender` checks every free piece edge against a
    local floor (3rd percentile of the 2 s around it) in a 50 ms window and names the first spot behind the breath with
    30 ms of quiet; `montiere_take` drops a short run cut off by a gap at a free piece end and skips a separate run before
    the speech at a free piece start.
75. **A card sound over a word end** (case 1 "ohne", the pop at 43.77 s). Sound placement uses the attack length (pop 0.10 s,
    stamp 0.15 s) and the word's energy end, capped at the next word's start. A sound that finds no free spot stays with a
    HINWEIS in bau.txt, it is never dropped.
76. **The circles of a checklist card stood empty for 98 frames.** Each circle shows a pulsing placeholder and a "?" until its tick.
77. **CTC stretched a word over a pause** (validation case with a deep male voice: a word aligned over 1.3 s, spoken for
    0.6 s, then 0.6 s of low hum inside the hook). The word mask covered the pause, so it was neither cut nor lowered, and the next word's onset could not
    move earlier because it never may go into the previous word. `ausrichten.py` (before the onset measurement) ends a word
    30 ms after the start of a pause inside its span: `einsatz.pause_im_wort`, band 1 to 7.9 kHz (hum below 1 kHz is not
    speech), at least 250 ms below take p10 + 18 dB, at least 300 ms before the aligned end. A soft word end ("-keit" 18 dB
    under the word's peak) stays above that line in this band; a broadband rule relative to the word's peak would have cut
    it (R2 "Glaubwürdigkeit."). Tested as a dry run on the final aligned times of the 8 reference versions (no word hit; the
    function runs earlier, on CTC times, so the rebuilt validation case 1 is the real check) and on the validation case
    (only the stretched word). A wider acoustic gate in `pausen_absenken` was tried and dropped: it changed the room tone
    of 13 approved reference pauses.
78. **The breath check of 74 read the piece's own first word as a breath** (case 1, round 4: start 125.67 s, onset 40 ms
    later; the hint then pointed to the end of the sentence). A sound counts as cut only when it runs across the edge:
    above the local floor + 12 dB in the 20 ms before AND the 20 ms after it.
79. **`hyperframes check` failed on an intended overlap**: placeholder and circle of the checklist card cross-fade at the
    same spot, both with a "?". The two slot containers carry `data-layout-allow-overlap`; a marker on the scene root does
    not count.
80. **The soft-onset rule of 73 moved a piece's first word across the piece start** (case 1, round 4: the "st" of the
    previous piece's last word before the seam read as the "F" of the next word; schnitte_vorab then reported the real
    word as a residue). anlaut moves a start only to or after the start of its own piece.
81. **The free-edge rule of 74 cut the first syllable of a word** (case 1, round 4: "Wo" of "Wochenplan" stood as its
    own run with a 40 ms gap to "ball" and was dropped as an "inhale"; pruefe_ms caught it, Whisper heard "Balltrainer").
    montiere_take drops a run at a free edge only when its peak stays under the clip's p10 + 22 dB (no speech level) and
    it lies outside every transcript word (30 ms margin).
82. **Own checks measured planned times, the viewer sees shown times** (round 5). The first word after a flash to a speaker
    section was held 4 frames by the white-on-white rule (+139 to +201 ms), and schnitte_vorab D checked the edl time. Now
    baue_reel.py writes the shown time of every caption word (`projekt/untertitel-zeiten.json`, check G), and a flash change
    on the first word of a white-caption section moves 5 frames before that word when a pause lies before it.
83. **ffmpeg's AAC encoder put a one-sided spike into the first audio block** (+0.39 dBTP left at 0.010 s; the master itself
    had -2.50 dBTP), and the delivery and the cover version each encoded the decoded audio again. mastern.py keeps the master
    as `render-ton.wav`, the delivery encodes it once with Apple's encoder (`kanal.aac_kodierer`, fallback ffmpeg's aac) and
    a 20 ms fade-in, the cover and phone versions copy that audio. `pruefe_ton_spitze.py` measures the delivered files.
84. **Card sounds over word ends on a deep voice** (Stempel 10.133 s on "Die", Pop 36.933 s on the nasal of "dein"). A click is
    audible where the voice has little treble; the reference channel's bright voice masked the same placements (approved). A sound that
    starts at a sounding word end with its click 10 dB above the voice's treble moves 25 ms behind the aligned end, and frame
    rounding never moves a sound earlier (10.150 s became 10.133 s by banker's rounding). Check E is the same rule.
85. **The keyword card covered the eyes** (a face standing high in the frame: card to 367 px, pupil at 375 px). baue_reel.py estimates
    the brow line of the face over each top card's time (face box top from the take's face track, 20 % of its height and
    8 px above) and marks the card; a load script moves it to 150 px and shrinks it to fit (at least 70 %). Check 4 of
    eigenpruefung measures the rendered frames. `hyperframes snapshot` shows punch zooms in their start state: never judge
    face positions from snapshots, only from the render.
86. **Chip text lost its descenders**: the reveal mask `inset(0 ...)` cut the "g" of "genug" at the line box (line height 1).
    The mask now reaches 40 px above and below. Check F finds masks that cut text with a tight line height.
87. **A hook that began with a subordinate clause** ("dass ...", cut at the pause after a comma). Every gate passed, the independent inspector approved it; Nico heard it:
    "Das ist ja kein richtiges Deutsch." `plan_bauen auswahl` stops when the transcript word before the hook's first audible
    word does not end a sentence. The first word is the first whose END lies behind the hook start (Whisper starts words up
    to 270 ms early: "Zehn" at 14.68 s, audible from 14.95 s). Override only with `"mitten_im_satz": true`.
88. **The cover filling sounded wrong although the template fit** (a second line whose object is missing). The cover keeps one clear subject and object: "warum dein Training nicht wirkt".
89. **An emphasis flash on a word in connected speech** (speaker to speaker, "das ist der Unterschied") held the word
    4 frames (check G). With the same state before and after, the flash moves 4 frames into the previous word.
90. **The empty-card check measured one frame** and called a date card with rolling digits empty (1.8 % content). It now
    takes the fullest of 4 frames over 15 frames, the inspectors' definition of "empty".
91. **The 50 hook templates were only a sentence in SKILL.md**: reel.json could leave "vorlage" out or name anything
    (Nico 17.10.2026: "die 50 Vorlagen ... das ist hoffentlich implementiert. Das ist ja die Grundlage für die Texthook").
    `hook_vorlage.py` reads references/hook-vorlagen.md (50 rows, asserted); `plan_bauen auswahl` stops without a valid
    `hook.vorlage`, `clip.py abliefern` without a valid `titelbild.vorlage`, and both log the template's pattern.
