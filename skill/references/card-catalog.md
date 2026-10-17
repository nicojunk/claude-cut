# Card catalogue (generated from scripts/erklaerer.py and baue_reel.py, 17.10.2026)

Every card shows only what the speaker says in the take: `satz` = the take sentence it illustrates (required for explainers),
`quelle` = source for anything the take does not say (a date, a number), the user decides. Anchor fields (`at`, `until`, `*_at`, `*_bis`)
take a word of the speaker in reel.json ("Betonung", "Das ist die", "weil@2", or a list ["weil", "weil", "weil"]); plan_bauen.py turns
them into word indices. Text fields: every visible text. Defaults are the words of the reference reel the card was built for; for any
other channel the build refuses a card that would show a default (profile flag `kartentext_vorgabe_erlaubt` is set only for the reference channel).
Defaults come from the reel the card was built for (the reference channel's voice reels), so a
default is never neutral. Required anchors: every `*_at` the card lists below must be found, else the plan stops.
The first visible content must land on `at` (a container that waits for a later anchor stands empty: give it placeholders
or move `at`). Colours of blood, danger and wrong values use the channel's `signal` role (cards that show such values).

Ground: "weiß" cards draw their accent lines on white (the channel accent needs >= 2:1 against white, kanal.py pruefen checks it),
"dunkel" cards sit on the channel dark with accent and light accent text (a neon brand: neon only here).

Placeholders (the user 15.10.2026, R2 freebie card): no card may stand half empty after it enters. eigenpruefung.py measures the card
interior at appear + 0.35 s (content >= 2 %); when content lands later than that, draw dashed "?" placeholders that pulse until the
anchor word (see the `.exslot` placeholders of the premium shell).

## Explainer cards (erklaerer.py)

| Typ | Grund | Anker | Textfelder | Was sie zeigt (Beispiel aus dem Reel, für das sie gebaut wurde) |
|---|---|---|---|---|

The public version ships without channel explainer cards. Build your own in `scripts/erklaerer.py` (see "Choosing a card").

## Base cards (baue_reel.py)

| Typ | Felder | Einsatz |
|---|---|---|
| `title` | icon (warn, check, up, cross, drop, dot, heart), num, text, sub, sub_at | Hook-Versprechen, Urteil |
| `chip` | num, text | Abschnittsbeginn nach einem Blitz |
| `list` | icon, title, rows[] (text, icon, at, label, label_at), foot, foot_at | Aufzählung, die Zeile für Zeile wächst |
| `flow` | nodes[] (text, icon, hot, dark, verb, at) | Ursache und Wirkung |
| `image` | src, label, label_at, img_w, img_h | ein Ding zum Anschauen (eigenes Foto, B-Roll-Standbild) |
| `pills` | pills[] (text, at), sub, sub_at | 2 oder 3 Optionen nebeneinander |
| `bars` | heading [Teil 1, Teil 2], bars[] (text, value 0 bis 1, tone grey/ink/red, at, pill, pill_at) | 2 oder 3 Werte im Vergleich, Höhe statt Zahl |
| `monitor` | tab, tab_at, value, tone, unit, icon, rise {at, to, frames}, label, label_at | ein Körperwert, der sich ändert (nur gesprochene Zahlen) |
| `counter` | label, icon, steps[] (text, tone, at) | Zahl, die auf dem Sprecherbild hochzählt |
| `keyword` | lead, keyword, sub | Aufruf: wird aus reel.json `varianten.<v>.aufruf` erzeugt |

Zone: `top` = auf dem Video (Sprecher, B-Roll), `paper` = im Splitscreen. 1 Karte je Segment. Zahlen auf Karten nur, wenn
die Aufnahme sie sagt (Bau bricht sonst ab) oder mit `quelle`.

## Choosing a card

1. Start from the drop-off map: what must the viewer see at this moment to stay (a guess to make, a comparison, a number that
   lands, a metaphor)? Pick the card whose mechanism matches, not the one whose reference text sounds similar.
2. A dopamine hit = open question (anticipation >= 0.7 s) + payoff on the payoff word + a soft sound >= 100 ms from any cut.
   Mark it with `"dopamin": true` in the takt's `absprung`. At least 2 per reel.
3. If no card fits, build a new one in erklaerer.py following the existing pattern: `_shell` (white) or `zjbox` (dark),
   every visible text through `_t(c, "feld", "")`, start state set at time 0, opacity in 2 to 3 frames, SVG transforms inside `<g>`.
   Add it to TYPES and to this catalogue, then rerun the reference regression (references/quality-gates.md).
