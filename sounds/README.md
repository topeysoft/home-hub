# Sounds that ship with the hub

Recordings in this folder ride along in the brain image and are copied into every hub's sounds folder
(`brain-data/sounds/`) the first time the brain sees them there missing. A file already in a hub's folder is
never overwritten, so a household can replace `rain.mp3` with its own rain and keep it across updates.

Add one with `tools/add-sound.sh`: it names the file, trims it to ninety seconds (the brain crossfades and
repeats every sound out to ten minutes, so a short steady source is all that is needed), encodes it small,
and writes the credit line. Only royalty-free recordings belong here; say where each came from in
`CREDITS.md`. White, pink and brown noise are not files: the brain generates them.

Good sources: Freesound filtered to CC0, Pixabay's sound effects, Mixkit. Steady sounds loop best (rain, surf,
a fan, a stream); recordings with distinct events (a thunderclap, a bird) give the loop away.
