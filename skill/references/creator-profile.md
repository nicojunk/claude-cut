# Channel profile (Kanal-Profil)

One JSON file per channel in the settings' `kanaele` folder (default `~/.config/smm-clipping/kanaele/`, set in
`~/.config/smm-clipping/config.json`). Template: `kanaele/vorlage.json`. Check after every change:
`python3 scripts/kanal.py pruefen <name>` (folders, fonts, colour contrast rules, stop word syntax).

Profiles hold client data (raw footage paths, compliance rules, sometimes NDA material). They never go into the skill
folder and never travel with the skill.

## Where the values come from
Never from memory. In this order:
1. The channel's design system (tokens with measured sources).
2. A reel or post the channel published, measured (colour picker on frames, fonts from the export).
3. Ask Nico for the brand kit. Write the source into `quelle_marke`.

## Fields

| Field | Meaning |
|---|---|
| `name`, `anzeige` | file name of the profile, display name |
| `sprache` | `de` (alignment, number words and Whisper are German; another language needs a new alignment model) |
| `rohmaterial` | list of folders searched for raw clips by file name |
| `transkripte` | folder of `<clip>.woerter.json` / `.txt` (written by `clip.py material`) |
| `cache` | folder for SDR copies, noise calibration (`entrauschen.json`), default `~/.cache/smm-clipping/<name>` |
| `arbeitsordner` | where reel folders and the material report go |
| `ablage_praefix` | file name prefix on the desktop root (`kanal-name`) |
| `farben` | colour roles, see below |
| `raster` | grid line colour on the split-screen paper, or `null` |
| `schriften_ordner`, `schriften` | font files for the roles `text`, `hero`, `akzent` with the CSS weight range |
| `css_zusatz` | extra CSS appended last (uppercase heroes, a flat key box, the bright brand accent on dark surfaces) |
| `aufruf` | default call to action per version (`lead`, `keyword`); reel.json overrides it |
| `regeln` | sentences with the channel's hard rules (shown to the agent, checked by the inspector) |
| `stopp` | compliance stop list: `[{"muster": regex, "grund": "…"}]`, checked on the transcripts, on the reel's words and on every card text |
| `rollen` | channel-wide caption roles (`key`, `accent`) |
| `plan_standard` | defaults for the plan (`tail`, `whoosh`, `pause_cap`, `start_zoom`, `scale`) |
| `pflicht_karten` | `[{"wenn": regex on the reel's words, "text": regex on the card texts, "grund": "…"}]`: when the reel talks about the topic, one card must carry the text (a health channel: a doctor note whenever hormones are the topic); checked by `pruefe_dramaturgie.py` and the inspector |
| `titelbild` | cover colours and fonts: `grund`, `rand`, `welle`, `zeile1_farbe`, `zeile2_farbe` (role or #hex), `zeile1_schrift`, `zeile2_schrift` (`text`/`hero`/`akzent`), `zeile1_versal`, `motiv` (`welle` = sound wave over the text, fits a voice channel; `keins`), start sizes `zeile1_px` / `zeile2_px` (default 64 / 82; an uppercase condensed font needs a bigger line 1) |
| `kartentext_vorgabe_erlaubt` | only the reference channel: card defaults are her own words |

## Colour roles
The engine is written in the reference channel's palette; each role is mapped to the channel colour in one pass over the finished
composition (`kanal.farben_umsetzen`). After the build, `kanal.farbreste` refuses any base colour left over.

| Role | the reference channel (base) | Used for |
|---|---|---|
| `ink` | #1E2430 slate | text on paper and white cards, dark cards, background, caption shadow |
| `ink2` | #283040 | second dark, gradients on dark cards |
| `ink_tief` | #12161E (rgb 18,22,30) | deepest dark, vignette edge |
| `accent` | #3FB8AF teal | key box, rings, borders, lines **on white cards and on dark cards** |
| `accent2` | #52C7BE | highlights, waves, glow, bars |
| `accent_hell` | #A8E2DD sand | italic text on dark cards |
| `accent_blass` | #E3F5F3 champagne | sheen, middle of gradients, light tints, flash edge |
| `papier` | #F7F8F6 pearl | split-screen paper |
| `signal` | #3FB8B0 (same as the accent, so the reference channel's reels stay unchanged) | blood, danger, a wrong value: needs >= 2:1 on white; a health channel sets a red |

### Contrast rules (checked by `kanal.py pruefen`)
- `accent` and `accent2` at least 2.0:1 against white: most card types draw accent lines on white.
- `accent` at least 3.0:1 against `ink` (borders on dark cards), `accent_hell` at least 4.5:1 against `ink` (text).
- `ink` at least 7:1 against `papier` and against white (all text on light ground).

A brand accent that is too light for white (neon, pastel) is split: `accent`/`accent2` get a darker step of the same hue,
and `css_zusatz` puts the bright brand colour only on dark surfaces and on the call to action. Measured example
(17.10.2026): a neon green brand colour has 1.15:1 against white and vanished on white cards in a test build; `accent`
became a darker step of the same hue (about 2.1:1), the neon came back through `css_zusatz` on the dark card boxes, their
stamps and headers, and the key box. Look at a test build's contact sheet before the first real reel of a new channel.

## Fonts
Three roles, each a file plus its CSS weight range: `text` (captions base, card text; the reference channel Inter),
`hero` (the big word of a caption group; the reference channel Cormorant Garamond; a bold condensed font like Anton works uppercase via
`css_zusatz`), `akzent` (italic accent words and headings; the reference channel Cormorant Italic). A single-weight font gets the range
`100 900`, so the browser never fakes bold.

## Compliance stop words
Write each forbidden thing as a regex with its reason. They run four times: on all transcripts (`clip.py material`,
listed with seconds in the material report), on the source span of every clip a reel uses (`plan_bauen.py auswahl`: a hit
between the first and the last used second stops the reel even when the chosen pieces skip it, because skipping it is
cutting it out), on the words of the montage (`plan_bauen.py plan`) and on every card text and caption (`baue_reel.py`).
A stop means: exit 3, `STOPP.md` with the words and seconds, report to Nico, choose nothing around it. Example of a health channel (Heilmittelwerbegesetz § 10): `injektion\w*`,
`\bdosi[sz]\w*`, amounts with units, `(alle|jeden) <n> (Tage|Wochen)`, prescription drug and brand names, syringes and
needles. A recording that names an injection interval must stop, not be cut. The channel's topic word
itself (a hormone name without product, dose or interval) stays allowed: write the patterns narrowly.

## Profiles on this machine
The settings' `kanaele` folder may hold a `README.md` with the existing profiles, their sources and rules. Read it before
working for a channel for the first time.
