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

## Three shapes, in the order to build them

### 1. Push-to-talk on the panel

A microphone button beside the command box. Hold it, speak, let go; the words appear in the box, are sent to `/say`
exactly as if typed, and the answer shows the same way. Nothing new on the hub.

Speech-to-text comes from the browser (`SpeechRecognition`, on the kiosk tablet and on phones). That API needs a
**secure context**: `https://`, or a browser told to trust `http://hub.local`. So this shape waits on the https
decision from *Out of the Box* (plain http for family now; a real name under a domain with issued certificates before a
customer). For the wall panel, which is a device the hub owner controls, a kiosk browser can be told to treat the hub's
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

What has to be measured before committing: on a Raspberry Pi 5, a short sentence through Whisper's *tiny* or *base*
model takes on the order of one to three seconds; the *small* model is noticeably better and noticeably slower. The
right model is the fastest one that hears the house's own names reliably, and the grammar can help by handing the
recogniser the vocabulary it should expect (room and device names as a bias list). If the Pi cannot do this inside about
two seconds, this shape needs a Pi 5 with more memory, a small accelerator, or a mini PC, and that is a hardware
decision for phase 5 rather than a reason to reach for a cloud.

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
   brain speaks Wyoming; the offline test; the measured latency written into this document.
4. **Shape 3 with one satellite.** One box in the kitchen, paired from the panel, placed on New devices, the guest test.
