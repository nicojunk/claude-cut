"""Explainer animations (Erklärer) for the moments where viewers are most likely to swipe away: a term they do not
understand, the lock-in zone after the hook, a re-hook (Kallaway, see references/erklaerer.md). Same design language
as the cards: heading on the paper, white card 880 x 484 at (100, 208), ink, red, measured entrance curve.

An explainer only shows what the speaker says in the take. A mechanism they do not say needs `quelle` (their own words
in another take, with file and timecode); the build refuses an explainer without `satz` (the take sentence it shows).

Drawn in SVG and HTML layers, animated with GSAP.
"""
import html, random

FPS = 30


VORGABE_GENUTZT = []   # (card type, field, text): a card showed a default text from the reference reels


def _t(c, key, vorgabe):
    """Visible card text from the plan. The default is the text of the reference reel the card was built for; another channel
    must give its own words (baue_reel.py refuses a build that used a default unless the profile allows it)."""
    if key in c:
        return c[key]
    VORGABE_GENUTZT.append((c.get('type', '?'), key, vorgabe))
    return vorgabe


def _esc(s):
    return html.escape(str(s), quote=True)


def _head(hd):
    return f'<div class="bhead"><span class="r">{_esc(hd[0])}</span>{_esc(hd[1] if len(hd) > 1 else "")}</div>'




TYPES = {}

CSS = '''
/* explainers (Erklärer), same card geometry as the bar chart: card 880 x 484 at (100, 208) */
.exc { overflow: visible; }
.exc .exsvg { position: absolute; left: 0; top: 0; width: 880px; height: 484px; overflow: visible; }
.exc .exlab { position: absolute; left: 0; top: 440px; width: 880px; text-align: center; font-weight: 800; font-size: 36px; line-height: 1; color: %INK%; }
.exc .expill { left: 40px; top: 30px; }
.exc .extag { position: absolute; top: 418px; width: 230px; text-align: center; font-weight: 800; font-size: 34px; line-height: 50px; color: #fff; background: %INK%; border-radius: 30px; }
.expic .expw { position: absolute; left: 16px; top: 16px; width: 848px; height: 452px; border-radius: 18px; overflow: hidden; }
.expic .expw img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: 50% 50%; }
.expic .exhalf { position: absolute; left: 50%; top: 0; width: 50%; height: 100%; background: #fff; }
.expic .exsweep { position: absolute; top: -10%; left: 0; width: 26%; height: 120%; background: linear-gradient(100deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.55) 50%, rgba(255,255,255,0) 100%); transform: skewX(-12deg); }
.expic .extag { top: 404px; }
'''



CSS += '''
.expr .exzoom { position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; object-fit: cover; z-index: 4; }
.exc .exlpill { position: absolute; z-index: 3; left: 630px; top: 340px; font-size: 34px; padding: 6px 22px; }
.exc .exsheen { position: absolute; z-index: 1; top: 0; left: 0; width: 120px; height: 484px; border-radius: 28px; pointer-events: none;
  background: linear-gradient(100deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.65) 50%, rgba(255,255,255,0) 100%); mix-blend-mode: soft-light; }
.broll .live { position: absolute; inset: 0; mix-blend-mode: screen; opacity: .6; background-image: repeating-linear-gradient(180deg, rgba(255,255,255,0) 0px, rgba(255,255,255,.0) 60px, rgba(255,255,255,.9) 80px, rgba(255,255,255,0) 100px, rgba(255,255,255,0) 160px); background-size: 100% 160px; }
'''

CSS += '''
.exc .exloupe { position: absolute; z-index: 2; left: 600px; top: 70px; width: 240px; height: 240px; border-radius: 50%; box-shadow: 0 14px 30px rgba(0,0,0,.22); }
.exc .exloupe svg { width: 240px; height: 240px; display: block; }
.exc .exstamp { position: absolute; z-index: 4; left: 96px; top: 250px; width: 300px; line-height: 92px; text-align: center; border: 8px solid %SIGNAL%; border-radius: 16px;
  background: rgba(255,255,255,.86); color: %SIGNAL%; font-weight: 900; font-size: 66px; letter-spacing: 3px; }
'''


# ---------------------------------------------------------------------------------------------------------------
# Premium shell shared by all premium explainers (Nico 08.10.2026: "Richtung stimmt", premium level approved).
# Rules learned in the prototypes: never scale an SVG <g> with GSAP (pivots drift), use HTML layers for pops and
# stamps; SVG only gets attr tweens, stroke-dashoffset and rotation with svgOrigin.
# ---------------------------------------------------------------------------------------------------------------
def _shell(cid, heading, svg, extra=''):
    return (f'<div class="card-wrap z-abs"><div id="{cid}" class="barsw expr"><div class="bhead" id="{cid}hd"><span class="r">{_esc(heading[0])}</span>'
            f'{_esc(heading[1] if len(heading) > 1 else "")}</div><div class="card bcard exc" id="{cid}cd">{svg}{extra}'
            f'<i class="exsheen" id="{cid}sw"></i></div></div></div>')


def _shell_js(cid, tc, k, push=6.0):
    # Alle Einblendungen erreichen volle Deckkraft in 2 Bildern (Abnahme R4 v8-ohne: Schrift 2 bis 5 Bilder halb deckend = gedimmt).
    # Glanzstreifen läuft ganz aus der Karte (Ende 800 % von 120 px > 880 px); bei 520 % blieb er auf nachtblauen Karten
    # als heller Streifen stehen (Abnahme R4 v8 G2, "Fünf Stimmen" 1,8 s)
    F = lambda n: n / FPS
    # Einblendung beginnt 1 Bild vor dem Ankerwort und dauert 2 Bilder: im Wechselbild steht die Karte halb, danach ganz.
    # Vorher 1 Bild nach dem Wort über 3 Bilder: 1 bis 2 Bilder leeres Papier und graue Zwischenbilder (Abnahme R4 v7-ohne G4).
    ti = max(0.0, tc - k['CAP_DELAY'] / FPS - F(1))
    return [f'tl.set("#{cid}cd",{{opacity:0,scale:0.97}},0);tl.to("#{cid}cd",{{opacity:1,scale:1.0375,duration:{F(2):.4f},ease:"power2.out"}},{ti:.4f});'
            f'tl.to("#{cid}cd",{{scale:1,duration:{F(4):.4f},ease:"sine.inOut"}},{ti + F(2):.4f});',
            # Überschrift: Deckkraft in 3 Bildern (8 Bilder halbe Deckkraft lasen sich als graue Schrift), Bewegung weiter 8 Bilder
            f'tl.set("#{cid}hd",{{opacity:0,y:-24}},0);tl.to("#{cid}hd",{{opacity:1,duration:{2/FPS:.4f},ease:"power1.out"}},{tc + F(2):.4f});'
            f'tl.to("#{cid}hd",{{y:0,duration:{F(8):.4f},ease:"back.out(1.6)"}},{tc + F(2):.4f});',
            f'tl.set("#{cid}sw",{{xPercent:-160}},0);tl.fromTo("#{cid}sw",{{xPercent:-140}},{{xPercent:800,duration:{F(22):.4f},ease:"power1.inOut",immediateRender:false}},{tc + F(6):.4f});',
            f'tl.fromTo("#{cid}",{{scale:1}},{{scale:1.035,duration:{push:.2f},ease:"none",transformOrigin:"540px 450px",immediateRender:false}},{tc:.4f});']


def _pop_html(sel, t, frames=6, s0=0.4, ease='back.out(2)'):
    return (f'tl.set("{sel}",{{opacity:0,scale:{s0},transformOrigin:"50% 50%"}},0);'
            f'tl.to("{sel}",{{opacity:1,duration:{2/FPS:.4f},ease:"power1.out"}},{t:.4f});tl.to("{sel}",{{scale:1,duration:{frames/FPS:.4f},ease:"{ease}"}},{t:.4f});')


def _stamp(cid, text, left, top, sid='st'):
    return f'<div class="exstamp" id="{cid}{sid}" style="left:{left}px;top:{top}px">{_esc(text).upper()}</div>'


def _stamp_js(cid, t, sid='st', shake=True):
    F = lambda n: n / FPS
    js = (f'tl.set("#{cid}{sid}",{{opacity:0,scale:2.2,rotation:-14,transformOrigin:"50% 50%"}},0);'
          f'tl.to("#{cid}{sid}",{{opacity:1,duration:{2/FPS:.4f},ease:"power1.out"}},{t:.4f});tl.to("#{cid}{sid}",{{scale:1,rotation:-8,duration:{F(6):.4f},ease:"power4.in"}},{t:.4f});')
    if shake:
        js += (f'tl.to("#{cid}cd",{{keyframes:[{{x:-7,duration:{F(1):.4f}}},{{x:6,duration:{F(1):.4f}}},{{x:-4,duration:{F(1):.4f}}},'
               f'{{x:2,duration:{F(1):.4f}}},{{x:0,duration:{F(2):.4f}}}]}},{t + F(6):.4f});')
    return js


def _sfx(k, name, t, vol):
    if k.get('sfx') is not None:
        k['sfx'].append((name, t, vol))



CSS += '''
.exc .exslot { position: absolute; z-index: 2; width: 112px; height: 112px; }
.exc .exslot svg { width: 112px; height: 112px; display: block; }
.exc .exicon { position: absolute; z-index: 2; left: 0; top: 0; width: 80px; height: 80px; }
.exc .exicon svg { width: 80px; height: 80px; display: block; }
.exc .exclock { position: absolute; z-index: 2; left: 24px; top: 20px; width: 120px; height: 120px; }
.exc .exclock svg { width: 120px; height: 120px; display: block; }
.exc .exdot { position: absolute; z-index: 3; left: 0; top: 0; width: 28px; height: 28px; border-radius: 50%; background: %RED%; box-shadow: 0 0 0 7px rgba(254,82,72,.25), 0 6px 14px rgba(0,0,0,.2); }
.exc .exbig { position: absolute; z-index: 3; width: 160px; text-align: center; font-weight: 900; font-size: 96px; line-height: 1; color: #fff; text-shadow: 0 4px 14px rgba(0,0,0,.25); }
.exc .exbig small { font-size: 48px; font-weight: 800; margin-left: 4px; }
.exc .extag2 { position: absolute; z-index: 3; display: flex; align-items: center; gap: 14px; background: %INK%; color: #fff; font-weight: 800; font-size: 40px; line-height: 1; padding: 14px 18px 14px 26px; border-radius: 40px; box-shadow: 0 8px 20px rgba(0,0,0,.2); }
.exc .extag2 .tkk { width: 48px; height: 48px; background: %RED%; border-radius: 50%; }
.exc .exbell { position: absolute; z-index: 3; left: 40px; top: 160px; width: 250px; height: 150px; }
.exc .exbell svg { width: 250px; height: 150px; display: block; }
.exc .exbell .kreuz { position: absolute; left: 65px; top: 15px; width: 120px; height: 120px; }
.exc .exbell .ml { position: absolute; left: 20px; top: -40px; width: 160px; height: 24px; opacity: 0;
  background: repeating-linear-gradient(90deg, %INK% 0 14px, transparent 14px 36px); border-radius: 12px; }
.exc .expill2 { position: absolute; z-index: 4; left: 620px; top: 54px; }
.exc .exne { position: absolute; z-index: 4; left: 380px; top: 180px; width: 120px; height: 120px; filter: drop-shadow(0 8px 14px rgba(0,0,0,.25)); }
.exc .exne svg { width: 120px; height: 120px; display: block; }
'''


# Channel explainer cards are added here with the premium shell (_shell, _shell_js, _stamp, _sfx) and registered in
# TYPES. The public version ships without the reference channel's cards (their texts came from her reels).
