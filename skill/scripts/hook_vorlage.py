#!/usr/bin/env python3
"""The 50 hook templates are the basis of every text hook (Nico 17.10.2026: "die 50 Vorlagen, woran sich immer orientiert
werden soll und wovon eine benutzt werden soll, die passendste"). Until round 5 the rule only lived in SKILL.md; reel.json
could leave "vorlage" out or name anything. This module reads references/hook-vorlagen.md and checks a "vorlage" field:
it must start with a template number 1 to 50 that exists in the file. Used by plan_bauen.py (spoken hook, hook.vorlage)
and clip.py (cover, titelbild.vorlage).
Usage: python3 hook_vorlage.py "40 Der eine Unterschied"   prints the template, exit 1 if unknown."""
import re, sys
from pathlib import Path

DATEI = Path(__file__).resolve().parent.parent / 'references' / 'hook-vorlagen.md'


def alle():
    """number -> (pattern, template, cover example) from the tables of hook-vorlagen.md"""
    out = {}
    for z in DATEI.read_text().splitlines():
        m = re.match(r'\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|', z)
        if m:
            out[int(m.group(1))] = tuple(x.strip() for x in m.groups()[1:])
    return out


def pruefe(wert, wofuer='Hook'):
    """returns (number, pattern) or raises ValueError with what to do"""
    V = alle()
    assert len(V) == 50, f'{DATEI}: {len(V)} statt 50 Vorlagen'
    m = re.match(r'\s*(\d+)', str(wert or ''))
    if not m or int(m.group(1)) not in V:
        raise ValueError(f'{wofuer}: "vorlage" fehlt oder ist keine der 50 Vorlagen ({wert!r}). Alle 50 in references/hook-vorlagen.md '
                         f'lesen, die passendste wählen und als "Nr Muster" eintragen, z. B. "40 Der eine Unterschied"')
    n = int(m.group(1))
    return n, V[n][0]


if __name__ == '__main__':
    try:
        n, muster = pruefe(sys.argv[1] if len(sys.argv) > 1 else '')
    except ValueError as e:
        sys.exit(str(e))
    print(n, muster, '|', alle()[n][1])
