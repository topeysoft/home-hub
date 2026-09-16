# Release notes, written for a house

One file per release, named for its version: `0.3.0.md`. **A release without one does not ship** —
`tools/release-manifest.py` refuses to build a record for a tag whose notes are missing, and CI
would rather fail a tag than let a family read a commit subject off their kitchen wall.

```markdown
## What's new

- Speakers remember how loud you had them.
- The kitchen comes up on the wall faster after the hub restarts.

## Details

Optional, and for whoever goes looking. Anything that needs more than a sentence.
```

The `What's new` lines are what a household actually sees: on the wall the morning after the hub
updated itself, and under *This hub → What's new* afterwards. So:

- **Say the effect, not the change.** "Speakers remember how loud you had them", not "persist volume
  in MediaPane". Somebody who does not know this hub has a codebase should be able to tell whether
  the line matters to them.
- **Two to four lines.** A release with eleven things worth saying has one or two things worth
  saying and nine that belong in Details.
- **No filenames, no containers, no commit subjects, and never Home Assistant** — the same rule that
  holds everywhere else on the panel. The tool checks for these and refuses; the list of what it
  refuses is in `tools/release-manifest.py`, and it is deliberately short, because a checker that
  tries to detect jargon in general would either miss it or block a real sentence.

Everything in `Details` is free-form and nothing reads it but a person who asked for it.

These files ship *inside the brain's image*, so the notes a hub shows are the notes for the code it
is actually running: no fetch, nothing to verify separately, and they read with the internet down.
The history under *This hub* is every file the image carries, which is every release up to its own.
