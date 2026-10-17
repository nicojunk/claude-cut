# B-roll and generated images (Higgsfield), with credit control

B-roll is optional. It earns its place only where a picture explains something the speaker says and a card cannot.
Most reference reels had none: the creator's face plus cards carried them.

## Look
A cinematic still life of one object that shows the sentence: dark, low key, one warm side light, no person (the user
08.10.2026 preferred this over lifestyle shots). Prompt pattern (Higgsfield `soul_2`, 9:16):
"Cinematic moody still life, vertical. [one object that shows the sentence]. Low-key lighting, single warm side light, deep
soft shadows, teal shadows and warm highlights, shallow depth of field, shot on 35mm film, subtle film grain. No people,
no hands, no readable text, no logos, no brands." Add the channel's own exclusions from its profile (health channels:
"no needles, no syringes, no pills"). Never a person who could pass for the creator, never the creator's face.
A living still: a luminance mask of the moving part (`"live": "media/<mask>.png"` on the B-roll segment) lets highlights
flow through it, no video model needed.

## Models and measured costs
| Model | Use | Credits (measured) |
|---|---|---|
| `soul_2` (CLI name `text2image_soul_v2`) | still life B-roll, 9:16; a 1.5k request was delivered as 720p (17.10.2026), enough for B-roll | 0.12 |
| `nano_banana` | drafts, motif search | 1 |
| `nano_banana_2` | sharpening a chosen motif | 1.5 |
| `nano_banana_pro` | the one final image, exactly 1 run (the user 15.09.2026) | 2 |
| Kling 3.0 std 3 s, no sound | motion only if motion is the point | 3.75 |
| Kling 3.0 std 5 s, no sound | | 6.25 |
| Seedance 2.5 15 s | never as a first attempt | 97.5 to 135 |
Video models need at least the Basic plan; a free account rejects them.

## Credit control (every session that touches a paid generator)
1. Before the first run: read the balance (`higgsfield account status --json` or MCP `balance`), write it with date, time and
   purpose into the ledger file from the settings (`credit_log` in `~/.config/smm-clipping/config.json`).
2. Before every run: estimate with `higgsfield generate cost <model> …` (the MCP `get_cost` flag was ignored once and
   billed a real job) and write the estimate into the ledger.
3. Hard stops without the user's explicit go in the conversation: a single run above 50 credits, a session above 100, or a
   balance that would fall below 200.
4. First attempt always the cheapest: shortest duration, std/720p, sound off, one clip. Lengthen or upscale only the
   take that is kept.
5. After every run: the real delta from `higgsfield account transactions --size 5 --json` next to the estimate; more than
   20 % above the estimate: stop and report.
6. Session end: one ledger line with total spent and balance left; the same two numbers in the report.
   With parallel runs the balance moves under you: assign each charge by its timestamp in `transactions`, never by the
   balance difference.
7. Reuse first: a paid still of the channel (its `media/` folders, the ledger) that shows the sentence is used again
   before anything new is generated.
8. A "probe" call to a generation tool is a real, billed run. Find parameters with `models_explore` or schema tools.
9. Rejected jobs (status nsfw) are billed too.

## Into the reel
Downscale to 1080 px wide JPEG, save in the reel folder `media/`, list in reel.json `assets`, use as a beat with
`"zustand": "broll", "src": "media/<file>.jpg"` (1.5 to 2.5 s) or as an `image` card. The build pushes it in slowly
(1.0 → 1.08).
