# Voice: the plan

*Written 7 September 2026, once the command box landed. This is a plan, not a commitment to build now; the field
test in other households is deferred, so the order below is by what the software needs, not by what a household has asked for.*

## Where we start

The panel already takes plain words. A box at the top of Home (`app/src/Say.vue`) sends a sentence to `POST /say`,
and `brain/hub/commands.py` answers it. That module is a **fixed grammar over the house's own names**: its rooms and
their usual other names, its devices and their short names inside a room, the kinds of things (lights, doors, blinds,
speakers, the thermostat), the scenes (movie, guests, sleep, all off, everything off) and the sounds on the hub. It
runs at once, the way a tap does, and it is deterministic:

- "kitchen lights off", "dim the den lamp", "movie in the living room", "good night", "we're leaving"
- "lock the front door", "lock up", "open the garage", "make the den warmer", "den thermostat to 72"
- "rain in the bedroom for an hour", "white noise on the kitchen speaker", "stop the noise"
- "is the front door locked?", "what's on?", "what's the temperature in the kitchen?", "is anyone home?"

What the grammar cannot place goes to the assistant, and the assistant **only proposes**: a one-off action the person
confirms with a tap, or a routine that waits under Routines for approval. A question the grammar cannot answer from the
house's state goes to the assistant as a question about the log ("why did the hall light come on?").

Every sentence is logged as a `said` event, understood or not, with what the house made of it. That log is the
material the grammar grows from: a weekly look at the sentences marked not understood says which phrases people
actually reach for, and each one becomes a pattern or an alias in `commands.py` with a test in `tests/test_commands.py`.

Voice is that same path with a microphone in front of it. Nothing below changes what runs; it changes how the sentence arrives.

## Rules that do not change

- **The model is never in the control loop.** The grammar executes; the model proposes. A spoken "turn off the kitchen"
  goes to the grammar and runs at once. A spoken "make it cosy in here" reaches the model and comes back as a card to
  confirm, on the panel, the same as typed. Voice does not get a shortcut past that rule; if the confirmation feels slow,
  the fix is to grow the grammar, not to let the model act.
- **Works with the internet down.** Speech recognition runs on the hub, or on the device holding the microphone. A cloud
  speech service can be an option a household turns on, never the default and never required.
- **No vendor account.** Not Alexa, not Google Assistant, not Siri as the front door. They would hand the experience
  back to a vendor app and put a cloud between a person and their light switch. They stay possible as an *Advanced*
  bridge later, for people who already live in one of them.
- **The room view stays the product.** Voice is a fallback for hands full and lights off, not the main interface. Nothing
  is voice-only; everything voice does has a tap.
- **Setup is a conversation on the screen.** Turning voice on is a switch on the panel with one sentence of explanation,
  not a config file, and the microphone is visibly off until then.
- **The hub host is whatever runs the house.** A Raspberry Pi 5 is the small end, not the design point. An Intel NUC, a
  mini PC or a VM with spare cores runs the same containers with bigger models and hears better. Voice is sized to the
  host it finds itself on (see *Fitting the hardware*), and nothing below is written so that it only works on a Pi.

## Three shapes, in the order to build them

### 1. Push-to-talk on the panel

A microphone button beside the command box. Hold it, speak, let go; the words appear in the box, are sent to `/say`
exactly as if typed, and the answer shows the same way. Nothing new on the hub.

Speech-to-text comes from the browser (`SpeechRecognition`, on the kiosk tablet and on phones). That API needs a
**secure context**: `https://`, or a browser told to trust `http://hub.local`. So on phones this shape waits on the
real certificate per hub from `docs/away.md` (a public name per house, reached directly at home and through the maker's
relay away). For the wall panel, which is a device the hub owner controls, a kiosk browser can be told to treat the hub's
address as secure without a certificate, so the wall can have push-to-talk before phones do. Where the browser cannot
recognise speech, the button does not appear; the box still works.

Exit test: from the wall, hold the button and say "kitchen lights off"; the lights go off and the toast reads *Kitchen
lights off.* within two seconds of letting go. No model was called.

### 2. Local recognition on the hub

For homes that want voice with the internet down, or a panel whose browser has no speech recognition, the hub does the
listening. The panel streams audio to the brain; the brain runs a small speech model and hands the text to the grammar.

The pieces exist as rented drivers, the same way the radios do: **Wyoming** is the protocol Home Assistant's Assist
uses between a microphone, speech-to-text and text-to-speech; **faster-whisper** (Whisper, small models) is the
speech-to-text; **Piper** is the text-to-speech for reading an answer back. Each runs in its own container on the hub.
The brain talks to them directly over Wyoming, not through Home Assistant's Assist pipeline, because the intent
engine here is the grammar and the assistant, and Assist's own intent matching would be a second brain with its own
vocabulary. Home Assistant stays the driver layer.

The right model is the fastest one that hears the house's own names reliably on the host at hand, and the grammar
helps by handing the recogniser the vocabulary it should expect (room and device names as a bias list). What has to be
measured before committing is the latency of each model size on each class of host, written into the table below once
measured; the figures there now are expectations, not results. A Pi 5 is expected to manage Whisper's *tiny* or *base*
model in one to three seconds for a short sentence; a NUC-class x86 box should run *small* or *medium* in under a
second, and a host with a GPU can run *large-v3* and still answer faster than the Pi. None of this is a reason to reach
for a cloud: a house that wants better hearing buys a better box, and the same image runs on it.

Exit test: unplug the router's uplink; from the wall, say "movie in the den"; the room changes and the toast shows.

### 3. A microphone in each room

Voice becomes useful when it is where the hands are, not only where the panel is. A **satellite** is a small box with
a microphone and a speaker that listens for a wake word and streams the sentence to the hub; it speaks the answer
back. The open designs run on an ESP32-S3 (Home Assistant's Voice Preview Edition, the Atom Echo, the ReSpeaker
Lite) and talk Wyoming, so they plug into shape 2 as they are, and a phone or a spare tablet can be a satellite too.

The wake word is the part to be careful about. On-device wake words (microWakeWord on the ESP32, openWakeWord on
the hub) mean nothing leaves the room until the word is heard, which is the only acceptable arrangement; and the word
should be the house's own name from setup ("Hey, Nadine's house") only if the model can be trained for it cheaply,
otherwise one of the stock words. Pairing a satellite is the same conversation as pairing a radio device: *Add a device →
a voice box → plug it in; the hub finds it*. Its room is chosen on the New devices screen like anything else, and that
room becomes the default for "lights off" said there, exactly as `room` does for the command box today.

Exit test: the plan of record's. A guest, hands full in the kitchen, says the wake word and "lights on"; the kitchen
lights come on; nobody explained anything.

## Fitting the hardware

The hub already runs on anything with systemd and Docker: Pi 5, NUC, mini PC, VM. Voice follows the radios' pattern:
the pieces are Compose profiles, and what is turned on and how big depends on the host. The choice is made once, on
the host, and can be overridden.

| Host class | How it is recognised | Speech-to-text | Wake word | Text-to-speech |
|---|---|---|---|---|
| Small: Pi 5 with 4 GB, or any arm64 with 4 cores and under 6 GB | `nproc`, `/proc/meminfo`, `uname -m` | faster-whisper *tiny* or *base*, int8 | On the satellite only (microWakeWord); the hub does not listen | Piper low-quality voice |
| Medium: Pi 5 with 8 GB, or arm64 with 8 GB or more | as above | faster-whisper *small*, int8 | Satellite first; openWakeWord on the hub for a panel microphone | Piper medium voice |
| Large: x86-64 with 4+ cores and 8 GB or more (NUC, mini PC, VM) | `uname -m` x86_64 plus cores and memory | faster-whisper *small* or *medium*, float16 where the CPU allows | openWakeWord on the hub for every microphone, satellites included | Piper high-quality voice |
| Accelerated: any of the above with a usable GPU or NPU | `/dev/dri` with a supported driver, `nvidia-smi`, Hailo or Coral present | *large-v3* on the accelerator | as Large | as Large, or a neural voice if the accelerator has room |

Expected latency for a short sentence, to be replaced by measurements: Small 1 to 3 s, Medium about 1.5 s, Large under
1 s, Accelerated well under 1 s.

How it is chosen: `install.sh` already knows the machine it is on; it writes `VOICE_TIER=small|medium|large|accelerated`
and the matching `VOICE_STT_MODEL`, `VOICE_TTS_VOICE` and `VOICE_WAKE=satellite|hub` into `driver-layer/.env`, the way
it writes the radio profiles today, and a hand-edited value there wins over the guess. The voice containers read
those variables; nothing else in the stack changes between tiers, and the brain speaks the same Wyoming to all of them.
The panel says which tier it is running under *This hub* in plain words ("Listening with the small model; a bigger hub
would hear better"), and the health list says so if the chosen model keeps missing (recognition confidence low, or
answers slower than the budget) rather than silently degrading. Moving a house from a Pi to a NUC is a backup and a
restore; the new host picks its own tier on first start.

Two consequences worth stating. First, the design point for latency and vocabulary is the Large tier, because that is
what a customer's box will most likely be; the Small tier is the floor that must still work, not the target. Second,
where a satellite carries its own wake word and the hub carries speech-to-text, the Pi stays a perfectly good hub for
a house that only ever says short commands, and the upgrade path is the box, not the software.

## What to answer, and how

The grammar's answers are text today. Read aloud, they need to be shorter and kinder: "Front door is locked." works;
"Kitchen ceiling is on. Kitchen counter is off." should become "One of the two kitchen lights is on." A `spoken`
variant of each answer, alongside the `text`, is cheap to add in `commands.py` when shape 2 lands. Answers from the
model (explanations, proposals) are not read aloud; a proposal is a card to look at, and an explanation is a paragraph
to read.

## Decisions to make before shape 1

| Question | Proposal |
|---|---|
| Secure origin for the browser microphone | Wall panel first, in a kiosk browser told to trust `hub.local`; phones after the https decision |
| Push-to-talk or always listening on the panel | Push-to-talk. A wall tablet listening all day is a different promise and needs a wake word (shape 3) |
| Where speech-to-text runs | The browser in shape 1; the hub in shape 2; never a cloud by default |
| How big a model | Chosen from the host's class at install, overridable in `.env`; the Large tier is the design point, the Small tier the floor |
| Does voice ever bypass confirmation for the model's proposals | No |
| Does the assistant see audio | No. It sees text, the same text a person could have typed |

## Not in this plan

Conversation (a back-and-forth with the model by voice), music search by voice, voice-driven setup, per-person voice
recognition, and anything that needs a vendor's account. If a household needs one of these, it is a new plan.

## Milestones

1. **Grow the grammar from the log.** Two weeks of `said` events from the house here; every not-understood phrase
   that a reasonable person would expect to work becomes a pattern with a test. Exit: fewer than one in ten typed
   sentences reach the assistant or a "didn't catch that".
2. **Shape 1 on the wall.** The button, the kiosk browser trusting the hub, the two-second test.
3. **Shape 2 on the hub.** Wyoming, faster-whisper and Piper as containers with profiles like the radios; the
   tier chooser in `install.sh`; the brain speaks Wyoming; the offline test on a Pi 5 and on a NUC-class box; the
   measured latency for each tier written into the table above.
4. **Shape 3 with one satellite.** One box in the kitchen, paired from the panel, placed on New devices, the guest test.
