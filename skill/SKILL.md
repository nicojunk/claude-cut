---
name: smm-clipping
description: "Cut raw talking-head footage of any creator channel (coaches, trainers, experts, new clients) into a finished, 95 % ready Instagram reel pair, with and without comment keyword, in a premium interview-reel style. Does the whole job from transcripts to delivery: dramatic hook from the creator's own most emotional sentence, lock-in, benefit by second 15, animated explainer cards only where viewers drop off, word-by-word captions in the channel's colours and fonts, hiss-free audio at -14 LUFS, optional Higgsfield B-roll under credit control, cover as frame 0, frame and millisecond checks, independent inspection. Use it whenever someone wants a reel cut, clipped, edited or geschnitten from Rohmaterial, a take or an IMG_xxxx.MOV, says mach daraus ein Reel, so wie beim Referenzkanal or SMM Clipping, wants many videos turned into reels at once, or sets up a new channel for reel production, even without naming the skill."
---

# SMM Clipping

One raw recording in, one reel pair out: `…-mit-kommentarwort.mp4` and `…-ohne-kommentarwort.mp4` plus the cover, on the
desktop root, each checked to the frame and the millisecond. The machine does 95 %: story order, edit, captions, cards,
audio, checks. The last 5 % are the user's eye ("premium") and the decision what gets posted. Nothing is posted or sent by this
skill.

Why it exists: the four reference reels of 14 to 16.10.2026 took about 24 hours and 8+ inspection rounds each, because every
lesson was learned live. Those lessons are now code (scripts/) and rules (references/). Target with this skill: at most
60 minutes of machine time per reel pair and at most 2 fix rounds.

## Rules that are never bent

- **No black start, no black end.** Every delivered video starts its picture at 0.000 s. The pipeline encodes with
  `setpts=PTS-STARTPTS`, `-bf 0`, exact frame count; `pruefe_schwarz.py` runs on every delivery file. In the report, one
  sentence per video: "Bild beginnt bei 0,000 s, Prüfung bestanden."
- **The creator's own words only.** Hook, captions, card texts, numbers: everything comes from the creator's recordings.
  A number on a card must be spoken in the reel (the build refuses otherwise) or carry a `quelle` that the user approves.
  Card texts never fall back to the reference examples for another channel (the build refuses).
- **Compliance stop.** The channel profile lists what the creator may never say on camera (a health channel: drug names,
  doses, injection intervals under the Heilmittelwerbegesetz). If the chosen material contains it, the build stops with `STOPP.md`.
  Never cut the words out yourself: a cut changes what the person says under their name. Report the exact words with time
  codes; the user decides (re-record, choose other material, legal check).
- **Nothing leaves the machine without the user.** No posting and no sending to the creator: the skill only writes files.
- **Higgsfield costs the user's money.** Ledger before and after every run, stop limits, cheapest model first
  (references/broll-higgsfield.md). Never generate a person who could pass for the creator.
- **Freeze the tool during a round.** Never edit scripts while renders or checks of the current round run (rounds 7, 7b and
  8 of the reference job were lost that way). Collect fixes, apply them between rounds, run the regression
  (references/quality-gates.md).
- **Load limits.** `clip.py` allows 1 build, 2 renders and 1 Whisper/alignment job at a time on the machine (file locks).
  Do not start pipeline steps outside `clip.py` in parallel.

## Before the first reel of a channel (once, 15 minutes)

1. `python3 scripts/clip.py umgebung` checks ffmpeg, avconvert, hyperframes, Python packages, Whisper large-v3, the German
   alignment model, the Apple Vision tools and the settings; it prints the install command for anything missing.
2. Channel profile: `kanaele/vorlage.json` → `<settings kanaele folder>/<name>.json`. Read `references/creator-profile.md`:
   colour roles, the contrast rules, fonts, call to action, rules and compliance stop words, where they come from (the
   channel's design system or a measured reference reel, never from memory). Check it:
   `python3 scripts/kanal.py pruefen <name>`.

## The workflow for one reel

Work in a reel folder inside the channel's work folder, e.g. `<arbeitsordner>/reels/2026-10-17-wochenplan/`. The
folder holds `reel.json`; the two versions are built in `mit/` and `ohne/`.

### 1 Material (3 to 5 min per recording)

```bash
python3 scripts/clip.py material <kanal> aufnahme-31.mov aufnahme-33.mov
```
Converts iPhone HDR with Apple's tonemapper (ffmpeg filters give a yellow cast), checks each clip is a raw take (portrait
or croppable landscape, no burned-in captions), transcribes every clip once with word times, scans the transcripts for the
channel's stop words and writes one report per clip, `<arbeitsordner>/material/<clip>.md` (full text, stop hits with
seconds). A stop hit inside the span a reel would use stops that reel; report it to the user instead of cutting around it.
Raw clips are found by file name in the profile's raw footage folders. Transcripts and caches always go into the channel's
folders from the profile, also in test runs: they are reused by every later reel of that channel.
Read the topic words in the text: Whisper mishears technical terms and names (a technical term written as a similar-sounding word). Correct the
captions with `fix` in reel.json (references/reel-spec.md); the spoken audio stays as recorded.

**When the build stops (exit 3, `STOPP.md`)**, report to the user in this form and build nothing else from that span:
```
STOPP <Reel>: <Clip> sagt bei <Sekunde> s "<genauer Wortlaut>" (Kanalregel: <Grund>).
Satz zum Neuaufnehmen: <Clip> <von> bis <bis> s: "<ganzer Satz>".
Möglichkeiten: 1 neu aufnehmen, 2 andere Aufnahme ohne die Stelle, 3 rechtliche Freigabe (dann "stopp_freigabe" in reel.json).
```
Write the reel.json and run the build even when the material report already shows a hit: the tool decides with the
exact span and writes `STOPP.md`.

### 2 Story: hook, lock-in, benefit, end (10 min)

Read `references/story-rules.md` first. From the transcripts choose:
- **Hook**: the strongest emotional sentence the creator says anywhere in the material, as the first 3 to 4 seconds,
  dark and slowly zooming from frame 0. Set its end in the silence after the last word; the tool never shortens it and
  lengthens it into the raw clip's silence when the afterglow (300 ms to the visible flash) is short.
  Choose it with `references/hook-vorlagen.md`: read all 50 templates, map the creator's candidate sentences to their
  mechanisms (e.g. "Zwei Menschen trainieren gleich viel, aber nur einer sieht nach drei Monaten etwas." is
  40 "Der eine Unterschied") and name the template in `hook.vorlage`. The hook is a whole sentence that starts at a sentence
  start: `plan_bauen auswahl` stops on a hook that begins mid-sentence ("dass ..." after a comma, the user 17.10.2026: "Das ist ja kein richtiges Deutsch"). A story already used as the hook of another
  reel of the channel is not used again.
- **Lock-in**: the sentence right after the hook decides if the viewer stays: an open question, a contrast, a guess.
- **Benefit**: the creator's own sentence that says what the viewer gets, starting by second 15 of the finished reel.
- **End**: question or call to action, never a flat statement; "mit" ends on the comment keyword card, "ohne" on the
  creator's own "Link in der Bio" sentence.
  No such sentence in the material? Build only "mit" (a reel.json may have one version) and say so in the report;
  never assemble an "ohne" ending from other words.
Write the order as a table (seconds, sentence, purpose, back-reference) and check every back-reference has its partner.
Pieces must start and end in silence between sentences; the montage snaps to measured pauses and refuses a seam inside a
sentence.

### 3 Drop-off map and cards (5 min)

Read `references/kallaway-rules.md` and `references/card-catalog.md`. Mark every place where viewers are likely to swipe
away (hook, lock-in, a term they cannot picture, the end of a thought, before the payoff). Only there goes an animation,
"nicht einfach willkürlich" (the user 15.10.2026). At least 2 of them are dopamine hits: an open question, anticipation of at
least 0.7 s, payoff on the payoff word, a soft sound. Pick the card by the mechanism the moment needs, then fill every
visible text from the creator's sentence.

### 4 reel.json (5 min)

Write it following `references/reel-spec.md` (hook, pieces, versions, beats with state, card and drop-off entry,
`nutzen_bei`, roles, cover). Anchors are the creator's words; use 2-word anchors where a word occurs often.

### 5 Build and look (about 10 min machine time per version)

```bash
python3 scripts/clip.py bauen <reelordner>            # both versions
python3 scripts/clip.py bauen <reelordner> mit --ab plan   # after a change in reel.json or woerter-korrektur.json
```
Montage (pause-snapped seams, per-clip noise reduction), word times (Whisper per piece, then forced alignment), the hook's
last word checked complete (raw clip quiet after the cut, heard without context), word gaps
lowered 14 dB, plan, composition, hyperframes check, cut pre-check (no clipped word), dramaturgy check (afterglow, benefit
by 15 s, 2 dopamine hits, keyword card, first word after the hook captioned). Then **look** at every page `mit/kontaktbogen-*.jpg` (9 stills each: start, every card at entry, middle and end):
every card fully visible and readable, nothing over eyes or mouth, cards never cover the face, white captions on a dark
part of the picture. A build error message says which rule broke and what to change.

### 6 B-roll (optional)

Only where a picture explains something the speaker says (references/broll-higgsfield.md). Still lifes first
(0.12 credits), video only if motion is the point. B-roll is a segment `"zustand": "broll", "src": "media/x.jpg"` and the
file goes into `assets` of reel.json.

### 7 Render and checks (about 8 min per version, 2 in parallel)

```bash
python3 scripts/clip.py rendern <reelordner>
```
Render outside iCloud, master (de-esser, fixed gain to -14 LUFS, limiter), delivery encode, then all checks into
`pruefung.txt` and `pruefung.json`. Machine time per phase is written to `zeiten.json` in the reel folder; report the sum. Sort every finding with `references/quality-gates.md`:
visible or audible = fix it; below the perception threshold (sound up to 20 ms at a word end, up to 3 still frames,
a value at a limit, a recognition difference far from any cut) = hint. Never call a finding an artefact without looking at
the frames (`flimmern.png`, a frame strip) or listening. A hint that stands gets `"freigabe_trotz_hinweis": "<measurement>"`
in `pruefung.json`.

### 8 Independent inspection (parallel to the next reel)

Spawn a fresh agent with the inspector prompt in `references/quality-gates.md`, on exactly the delivery files and the
reel folder's `kanalregeln.md` (written by the build). It writes its own code and blocks only on visible or audible
defects. A reel with one version gets the same brief for that one folder. Start the next reel's build meanwhile. Fix rounds: at most 2.
After the second round, findings go into the report instead of a third round.

### 9 Cover and delivery (3 min)

Pick the cover still: `python3 scripts/titelbild_kandidaten.py <reelordner>/mit` (sharpest stills of the hook; choose open
eyes, clear expression). Pick the text from `references/hook-vorlagen.md` (template that fits the reel's core sentence,
2 lines, no punctuation, one clear subject and object: "warum dein Training nicht wirkt", not a line without its object),
enter it as `titelbild` in reel.json, then:
```bash
python3 scripts/clip.py abliefern <reelordner>
```
Cover as frame 0 (WhatsApp and Instagram preview), both versions and the cover to the desktop root as
`JJJJ-MM-TT-<praefix>-reel<NR>-<thema>-mit-kommentarwort.mp4` / `-ohne-…` / `-cover.jpg`, md5 checked, phone preview.

Report to the user in 2 to 5 lines (German, real umlauts, no dashes as punctuation): what the reel says in one line, length,
per video "Bild beginnt bei 0,000 s, Prüfung bestanden.", the hints that stand, credits used.

## Many videos at once (batch)

1. Run `material` for all recordings.
2. Propose a topic list as one table: per reel the hook sentence (seconds), the lock-in, the benefit sentence, the end,
   the 2 dopamine hits, any stop-word hit. **One approval from the user for the whole list**, then autonomous.
3. Write all reel.json files, then `python3 scripts/clip.py stapel <reel1> <reel2> …`: builds one after another, each
   finished build renders in one of 2 lanes, cover and delivery when `titelbild` is set. Overnight for 30 videos
   (about 15 h). Inspect in batches; a reel that needs a third round goes to the report.

## Files

- `scripts/clip.py`: the pipeline (umgebung, material, bauen, rendern, pruefen, abliefern, alles, stapel).
  `scripts/umgebung.py` (environment check), `scripts/transkribiere.py` (Whisper large-v3 with word times, per clip).
- `scripts/kanal.py`: channel profile, colour mapping, fonts, stop words. `kanaele/vorlage.json`, `kanaele/config-vorlage.json`.
- `scripts/plan_bauen.py`: reel.json → montage list, plan, drop-off map, rule checks, compliance stop.
- `scripts/baue_reel.py`, `scripts/erklaerer.py`, `assets/style.css`: the composition (HyperFrames + GSAP), card toolkit.
- `scripts/montiere_take.py`, `naehte.py`, `entrauschen.py`, `woerter_je_stueck.py`, `ausrichten.py`, `zahlwort.py`,
  `pausen_absenken.py`, `mastern.py`, `einsatz.py` (audible word onset on the 1 ms envelope), `hook_ende.py`: montage, word times and
  audio. `pausen_liste.py`: diagnosis, lists long pauses in a reel's audio.
- Checks: `schnitte_vorab.py`, `pruefe_dramaturgie.py`, `ton_pakete.py`, `pruefe_ton_spitze.py`, `pruefe_schwarz.py`,
  `flimmern.py`, `eigenpruefung.py`, `pruefe_ms.py`, `pruefe_take.py`, `hook_vorlage.py` (hook and cover must name one of
  the 50 templates). `bin/` holds the Apple Vision tools (face boxes, eye landmarks, text recognition), built from
  `gesicht.swift`, `augen.swift` and `ocr.swift`.
- Delivery: `titelbild_kandidaten.py`, `titelbild.py`, `abliefern.sh`, `render_ausserhalb.sh`, `snap.sh`.
- References: `reel-spec.md`, `creator-profile.md`, `story-rules.md`, `kallaway-rules.md`, `card-catalog.md`,
  `hook-vorlagen.md`, `broll-higgsfield.md`, `quality-gates.md`, `pitfalls.md` (read when a check fails or something looks
  odd: 40+ measured traps with their fixes).
