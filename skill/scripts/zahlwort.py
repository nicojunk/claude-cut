#!/usr/bin/env python3
"""German spoken form of digits for forced alignment (ausrichten.py, pruefe_ms.py). The aligner only knows letters, so
"26." must become "sechsundzwanzigsten" before it can be placed on the audio; the caption keeps the digits.
Replaces the fixed table of the reference reels (7, 10, 11, 26, 35, 37, 2026), which broke on every other number.
Covers cardinals 0 to 999999, ordinals with a trailing dot ("26." -> "sechsundzwanzigsten"), dates ("26.10." ->
"sechsundzwanzigsten zehnten"), decimals ("2,5" -> "zwei komma fünf"), percent ("20%" -> "zwanzig prozent") and times ("19:30")."""
import re

_EIN = ['null', 'eins', 'zwei', 'drei', 'vier', 'fünf', 'sechs', 'sieben', 'acht', 'neun', 'zehn', 'elf', 'zwölf', 'dreizehn',
        'vierzehn', 'fünfzehn', 'sechzehn', 'siebzehn', 'achtzehn', 'neunzehn']
_ZEHN = ['', '', 'zwanzig', 'dreißig', 'vierzig', 'fünfzig', 'sechzig', 'siebzig', 'achtzig', 'neunzig']


def kardinal(n):
    n = int(n)
    if n < 20:
        return _EIN[n]
    if n < 100:
        e, z = n % 10, n // 10
        return (('ein' if e == 1 else _EIN[e]) + 'und' if e else '') + _ZEHN[z]
    if n < 1000:
        h, r = divmod(n, 100)
        return ('ein' if h == 1 else _EIN[h]) + 'hundert' + (kardinal(r) if r else '')
    if n < 1000000:
        t, r = divmod(n, 1000)
        return ('ein' if t == 1 else kardinal(t)) + 'tausend' + (kardinal(r) if r else '')
    return ' '.join(_EIN[int(c)] for c in str(n))


def ordinal(n):
    n = int(n)
    besonders = {1: 'ersten', 3: 'dritten', 7: 'siebten', 8: 'achten'}
    if n in besonders:
        return besonders[n]
    k = kardinal(n)
    return k + ('sten' if n >= 20 else 'ten')


def sprechform(wort):
    """Caption token -> lower-case letters and spaces only (what the aligner can place)."""
    t = wort.strip().lower().replace('-', ' ')
    t = re.sub(r'(\d+)\s*%', lambda m: kardinal(m.group(1)) + ' prozent', t)
    t = re.sub(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})?', lambda m: ordinal(m.group(1)) + ' ' + ordinal(m.group(2)) +
               (' ' + kardinal(m.group(3)) if m.group(3) else ''), t)
    t = re.sub(r'\b(\d{1,2}):(\d{2})\b', lambda m: kardinal(m.group(1)) + ' uhr ' + (kardinal(m.group(2)) if int(m.group(2)) else ''), t)
    t = re.sub(r'(\d+),(\d+)', lambda m: kardinal(m.group(1)) + ' komma ' + ' '.join(_EIN[int(c)] for c in m.group(2)), t)
    t = re.sub(r'\b(\d+)\.(?!\d)', lambda m: ordinal(m.group(1)), t)
    t = re.sub(r'\d+', lambda m: kardinal(m.group(0)), t)
    t = re.sub(r'[^a-zäöüß ]', '', t)
    return ' '.join(t.split())


if __name__ == '__main__':
    for w in ['7', '26.', '26.10.', '2026', '35', '37', '11', '1', '21', '101', '2,5', '20%', '19:30', 'Ober-Grenz-Wert', '3.']:
        print(w, '->', sprechform(w))
