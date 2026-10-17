# reel.json: the description of one reel

One file per reel, in the reel folder. `plan_bauen.py` turns it into the montage list (`auswahl.json`), the build plan
(`plan.json`) and the drop-off map (`absprung-karte.json`) of each version. Worked example that rebuilds the reference channel's R3
"Mensch oder KI" to within 20 ms of the delivered word times: `assets/beispiel-reel.json`.

## Fields

```json
{
 "kanal": "demo",                        // profile name (kanal.py), also decides colours, fonts, stop words
 "titel": "Reel 5 Wochenplan",          // free text, shown in plan and logs
 "nummer": 5, "thema": "wochenplan",   // file name on the desktop: <date>-<praefix>-reel5-wochenplan-… (nummer optional)
 "hook": {                                  // the first piece, dark and zooming from frame 0
   "clip": "aufnahme-31.mov", "von": 129.40, "bis": 134.80,   // seconds in the raw clip, both kept exactly (no snapping)
   "satz": "…",                             // what is said, for the reader of the file
   "vorlage": "40 Der eine Unterschied",    // REQUIRED: the best fitting of the 50 templates (references/hook-vorlagen.md)
   "crop": "608:1080:686:0", "gain": -4.8,  // optional: landscape source cropped to 9:16, level match in dB
   "drama": true, "drama_zoom": 1.15, "drama_filter": "saturate(0.35) brightness(0.7) contrast(1.12)"   // defaults
 },
 "stuecke": [                               // pieces after the hook, common to both versions, in reel order
   {"clip": "aufnahme-31.mov", "von": 95.0, "bis": 123.0, "satz": "…"}
 ],
 "nutzen_bei": "Der Unterschied",            // first words of the benefit sentence; must start by second 15 of the reel
 "rollen": {"key": ["Wirkung"], "accent": ["Stimmt"]},   // caption roles beyond the automatic ones (see below)
 "fix": {"Ober -Grenz -Wert": "Obergrenz-Wert"},      // caption corrections, see below
 "takte": [ … ],                            // beats, see below
 "varianten": {
   "mit":  {"stuecke": [ … ], "aufruf": {"bei": "schreib", "lead": "Kommentiere", "keyword": "WIRKUNG"}, "takte": [ … ]},
   "ohne": {"stuecke": [ … ], "aufruf": {"bei": "Link", "lead": "Link in der", "keyword": "BIO"}, "takte": [ … ]}
 },
 "titelbild": {"zeit": 3.9, "zeile1": "Mensch oder KI", "zeile2": "Hör genau hin", "vorlage": "46 Gegenüberstellung"},   // "vorlage" REQUIRED, a number 1 to 50 from hook-vorlagen.md (clip.py abliefern stops otherwise)
                                            // zeit = seconds in the version's take.mp4 (the montage), not in the raw clip
 "assets": ["media/b_mikro.jpg"],           // images used by B-roll segments or image cards, relative to the reel folder
 "plan": {"scale": 1.12},                   // optional overrides of the profile's plan defaults
 "keep_pauses": [], "weg": [], "hero_punch": [],          // rarely needed, see below
 "stopp_freigabe": []                       // only on Nico's explicit decision, see below
}
```

### Pieces (`hook`, `stuecke`, `varianten.<v>.stuecke`)
- Times in seconds of the raw clip (from the transcript `takes/<clip>.woerter.json` or `material-<date>.md`).
- The montage snaps every edge to the nearest measured pause (±0.35 s) unless `"von_fest"` / `"bis_fest"` is true. Use the
  fixed edges only with a measured value (a pause found with `SMM_KANAL=<kanal> python3 scripts/naehte.py CLIP von bis`).
- The hook is always fixed and must end at least 300 ms after its last word, with no word of the next sentence inside.
- Optional per piece: `crop` (ffmpeg crop before scaling to 1080x1920), `gain` (dB, added on top of the automatic
  loudness match: the montage brings every piece's speech loudness to the median of all pieces, at most ±8 dB; leave
  `gain` out unless a listening test says otherwise), `blende_aus` (fade-out in s, default
  0.03; 0.005 where the next word starts right after the seam), `stille_danach` + `stille_farbe` (hold silence after the
  piece under a fade into a colour), `stil: "rueckblende"` (flashback look for a landscape interview).

### Beats (`takte`)
Each beat starts at a word of the creator and can switch the picture, show a card and carry its drop-off entry.
```json
{"bei": "Was", "zustand": "split", "blitz": true,
 "karte": {"type": "welle_flach_lebendig", "zone": "paper", "flach_at": "wenn", "weil_at": ["weil", "weil", "weil"], …},
 "absprung": {"stelle": "Vergleich", "absprung": "Mitte", "regel": "Vorfreude in 3 Stufen", "animation": "Welle wächst je weil", "dopamin": true}}
```
- `bei`: anchor, searched after the previous beat (the first beat after the hook). Forms: `"Wort"`, `"zwei Wörter"` (phrase,
  safer for frequent words), `"weil@2"` (second occurrence), or a word index (int).
- `zustand`: `speaker` (full screen), `split` (paper above, speaker below), `broll` (with `"src": "media/x.jpg"` or `.mp4`).
  Optional with it: `blitz` (light flash on the cut, for a new section), `punch` (punch-in), `drama` / `drama_zoom` /
  `drama_filter` (dark emotional look), `dip` (fade through the channel dark, for a flashback).
  The first beat after the hook gets a flash automatically.
- `karte`: any card of `references/card-catalog.md`. Anchor fields (`at`, `until`, `*_at`, `*_bis`) take words like `bei`
  and are searched from the beat's word up to the next beat (an anchor not found there is an error, never a word of a
  later beat); lists are searched one after another, also inside nested fields (`rows[].at`, `nodes[].at`,
  `rise.at`). `at` defaults to the beat's word. A word Whisper heard slightly differently (up to 2 letters off, words of
  5+ letters) is accepted with a note in the plan output.
  Explainer cards need `satz` (the sentence they show) and every visible text field filled with the creator's words.
- `absprung`: the drop-off entry (Kallaway model, not measured): `stelle`, `absprung` (why viewers might leave here),
  `regel` (the rule from kallaway-rules.md), `animation`, `dopamin: true` for a dopamine hit. Every card needs an entry;
  at least 2 dopamine hits per version.

### Versions
`mit` and `ohne` share hook, `stuecke` and `takte`; each adds its end pieces, its own beats and its call to action.
`aufruf.bei` is the word on which the keyword card appears (version "mit" requires it). A reel may have only one version.

### Caption corrections (`fix`)
Keys are the tokens as Whisper wrote them (space separated), values the caption text. Same number of words on both sides:
word for word (`"Zoom Kohl": "Zoom Call"`); fewer words on the right: the tokens join into one caption word.
Fragments starting with `-` or `.` join the word before automatically ("7 -Tage -Challenge" becomes "7-Tage-Challenge",
"26 .10." becomes "26.10."), no `fix` needed. `fix` changes captions only; the audio stays as recorded.

### Caption roles
Automatic: groups of up to 4 words or 24 characters, closed at every sentence end; per group one `hero` (the longest
content word, capitalised preferred), function words `base`. `rollen.key` marks words that get the keyword box (the topic
word, the comment keyword), `rollen.accent` words in italic accent (connectors like "Stimmt", "Also"). The profile can
add channel-wide roles.

### Rare fields
`keep_pauses`: `[[s, e]]` take seconds the pause removal must not cut (quiet speech). `weg`: `[[s, e]]` take seconds that
always go (a breath before a seam). `hero_punch`: word indices with a mini flash and punch-in (1 or 2 per reel, never
within 6 frames of a card entrance). `woerter-korrektur.json` in a version folder: hand-measured word starts
`[{"wort": "Hör", "s": 3.767, "e": 3.973, "beleg": "Hüllkurve …"}]`, applied by the alignment; then
`clip.py bauen <reel> <v> --ab plan`.
`stopp_freigabe`: `[{"wort": "…", "clip": "IMG_….MOV", "sekunde": 12.3, "von": "Nico", "datum": "2026-10-17",
"beleg": "rechtliche Prüfung …"}]` lets exactly this stop hit through and names it in the plan output. Only Nico enters it,
after a legal check or his explicit decision; never to get a build through.

## Exit codes of plan_bauen.py
- 2: a rule is broken; the message names it and what to change (anchor not found, afterglow too short, fewer than
  2 dopamine hits, a card without drop-off entry, `nutzen_bei` missing).
- 3: compliance stop; `STOPP.md` in the version folder lists the words, the rule and the raw clip second. Report to Nico.
