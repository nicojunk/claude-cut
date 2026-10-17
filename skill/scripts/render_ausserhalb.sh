#!/bin/zsh
# Render a HyperFrames project with its work folder OUTSIDE iCloud, then move only the finished file to the target.
# Why (Nico's decision 16.10.2026, memory project-icloud-renderlast-2026-10-16): hyperframes always puts its ~1,900
# captured frames next to --output. Inside the iCloud Desktop one render cost the iCloud daemons 101.5 s CPU,
# outside 3.4 s; copying the finished MP4 back costs 3.6 s. Render time is the same either way.
# Usage, from inside projekt/:  zsh <skill>/scripts/render_ausserhalb.sh ../render-roh.mp4 --quality looks --fps 30
# On failure the partial output stays in ~/Renders/<stamp>/ (outside iCloud) and the target is left untouched.
set -e
[ -n "$1" ] || { echo "Aufruf: render_ausserhalb.sh ZIEL.mp4 [weitere hyperframes-render-Argumente]" >&2; exit 2; }
Z=${1:A}; shift
O=${SMM_RENDERS:-$HOME/Renders}/$(date +%Y%m%d-%H%M%S)-$$
mkdir -p $O
npx --yes hyperframes@${SMM_HYPERFRAMES:-0.8.166} render "$@" --output $O/${Z:t}
mv -f $O/${Z:t} $Z
rmdir $O 2>/dev/null || true
echo "render_ausserhalb: $Z (Arbeitsordner war $O)"
