# Voice: the plan

*Written 7 September 2026, once the command box landed. This is a plan, not a commitment to build now; the field
test in other households is deferred, so the order below is by what the software needs, not by what a household has asked for.*

## Where we start

The panel already takes plain words. The command box (`app/src/Say.vue`) sends a sentence to `POST /say`,
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

## What voice may do, and how the house heard you

*Added 12 September 2026, from the question "should the model-in-the-loop rule be softened so voice can do lights and
fans but not locks and the garage?"*

**The answer is no, because that rule is not what would be stopping you.** "The model is never in the control loop"
is about who EXECUTES, not about which things voice may touch. The grammar executes; the model only proposes. So a
spoken "close the garage" does not reach the model at all -- `garage( door)?` is a cover in `commands.py`'s KINDS
table, `close` is one of its direction words, and it runs at once, exactly the way a tap does. Locking up is already
there too: "lock the front door", "lock up", "lock the house". **Voice closing a garage door is allowed by the rule as
written, today, and would work the moment a microphone lands.**

Softening the rule would therefore buy nothing that was wanted, and would cost the thing it is for: an LLM's misparse
of "unlock the back door" is a class of accident a deterministic grammar cannot have.

**But the question underneath it is a real one, and there is no rule for it yet.** It is not *which devices may voice
control*. It is *who is allowed to be heard*, and that depends on how the sentence arrived:

| how the house heard it | who could have said it |
|---|---|
| typed in the command box | somebody standing at the panel, indoors |
| the orb tapped (on the wall, or shape 1 on a phone) | somebody standing at the panel, indoors |
| the orb woken by a wake word (later; see *A wake word is another route*) | anybody within earshot of the panel -- and a panel is often in a hall, near the door |
| a satellite with a wake word (shape 3) | anybody within earshot -- including through a door, a window or a letterbox |

The orb on the wall is the same trust as tapping the tile: your hand is on the panel, so you are already inside.
There is nothing to gate. A satellite listening for a wake word is a different promise, and the attack is not
hypothetical -- shouting a command through a letterbox at a voice assistant to unlock a door is a known one.

So the rule to add is **about the route, not about the kind**:

> What the house will do without asking depends on how it heard you. Anything you can do with a tap, you can do by
> tapping the orb and speaking. Anything woken by a wake word -- on a satellite, or later on the panel itself -- may
> do everything except open a way into the house.

**And the direction matters more than the device.** Closing and locking make a house safer; opening and unlocking are
the only dangerous half. The grammar already distinguishes them -- `(open|close|shut|raise|lower)` for a cover,
`(lock|unlock)` for a lock -- so a satellite can be allowed "close the garage" and "lock up" from anywhere in the
house while "open the garage" and "unlock the front door" are the two that need more than a voice. Note that the
fourth row is the panel's own, once a wake word runs on it: the gate follows the route, so it reaches the wall panel
too, indoors or not. That gives the
wish that prompted this question in full, at no cost: **closing the garage door by voice, from any room, is safe
because the failure mode of a misheard "close the garage" is a closed garage.**

What "more than a voice" should be is the open part, and it is a choice between three, in order of how much they ask
of a person: the panel says what was heard and waits for a tap; or the settings code, which the house already has and
already gates the settings behind; or the household turns the whole class on per kind, with the risk in plain words,
the way a nudge says what it is for. None of the three needs building first, because every route that exists today is
a microphone touched by a hand -- the orb on the wall, and shape 1 on a phone -- and the question does not arise until
something in the house listens for a word.

Two things this does not change. The model still only proposes, by voice as by typing. And nothing here is voice-only:
every one of these has a tap, which is the whole reason the gated half can be gated at all.

## Three shapes, in the order to build them

*The order below is the order they were conceived. The order to build them is in **Milestones**, and 14 September 2026
split shape 1 in two: its gesture, which the wall gets first, and its browser recogniser, which turns out to be only
ever the phone's.*

### 1. Tap the orb and talk

**Tap the orb.** Not a microphone button beside the box -- see *The orb already is the microphone* below, which is
the one part of this plan the design has overtaken since it was written. Tap, speak, stop; the words appear in the
box, are sent to `/say` exactly as if typed, and the answer shows the same way. Nothing new on the hub. The gesture
was settled on 12 September 2026: **the orb is the microphone, and typing is reached from inside the box once it is
open.**

Speech-to-text comes from the browser (`SpeechRecognition`). That API needs a **secure context**: `https://`, or a
browser told to trust `http://hub.local`. So this shape waits on the real certificate per hub from `docs/away.md` (a
public name per house, reached directly at home and through the maker's relay away). Where the browser cannot
recognise speech there is nothing to hide and no branch to write: the tap opens the box to type in, which is exactly
what a tap does today.

**The wall is no longer in that paragraph, and this is the part to read twice.** It used to be: a kiosk browser could
be told to treat the hub's address as secure without a certificate, so the wall would listen before phones did. The
wall stopped being a browser on 13 September 2026. It is `kiosk/`, an Android launcher around a WebView, and **a
WebView has no Web Speech API at all** -- `SpeechRecognition` there is not throttled or cloud-backed, it does not
exist. Nor can a WebView be told to trust `http://hub.local` the way a Chrome kiosk can with a flag. Both halves of
the wall's route are gone, so **shape 1 is the phone's shape**, and the wall's microphone is settled below in *The
wall's microphone is the hub's ear*. What this section still owns for both is the gesture, which is the substance of
it and depends on neither.

**And the thing to establish before building rather than after is now only the phone's.** Chrome's
`SpeechRecognition` has historically sent the audio away to be recognised on Google's servers. Chrome has since added
an on-device mode, but it is opted into explicitly and the model is fetched first; it is not what a page gets by
default. This plan files browser speech-to-text under *runs on the device holding the microphone* and promises
**works with the internet down**, and shipping this to a phone without knowing which of the two is actually happening
would honour neither. So it is still to be measured, on a phone browser rather than on the wall -- and if on-device
recognition is not there, phones wait for shape 2 as well. The wall answers the question by not asking it.

**Measured, 14 September 2026, and the contingency above has fired.** Chrome does expose the on-device mode, as
`processLocally` on a `SpeechRecognition`. Asking for it fails at `start()` with `language-not-supported` until the
model has been fetched -- which, on a machine that has never used this API, is every single time. What a page gets
when it falls back is the cloud. So on this browser, today, speech-to-text in a phone browser is a network service,
and the sentence above is the one that applies: **phones wait for shape 2 as well.** The plan was built to absorb
this answer, and absorbing it costs nothing that was not already being built, because the hub has to hear for the
wall regardless.

Two notes for whoever re-measures it. It must be real Chrome: Playwright's bundled Chromium has the API and no speech
service behind it, so it neither errors nor hears, and a harness will tell you less than nothing. And the instrument
is in the panel already -- `?listen=browser` in `app/src/ear.ts` asks for on-device and falls back loudly, warning in
the console every time audio leaves the machine; `?listen=browser-local` refuses the fallback, and that refusal *is*
the measurement. Neither flag is on in any house: `canListen()` is false without one.

Exit test: from a phone on the house's own Wi-Fi, tap the orb and say "kitchen lights off"; the orb holds its
listening state while the sentence is spoken, the lights go off, and the toast reads *Kitchen lights off.* within two
seconds of the last word. No model was called, and no audio left the house -- the house, and not the phone, because
once phones wait for shape 2 the recogniser is the hub and the audio has to cross the LAN to reach it. That is the
same promise the wall makes, and it is the one *works with the internet down* was always about.

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

## The orb already is the microphone

*Added 12 September 2026, after moves 6 and 7 landed. This section is the only part of the plan above that the
design has overtaken, and it is worth reading before shape 1 is built.*

When this plan was written the command box was a box: a field at the top of Home, always open, always the full
width. So "a microphone button beside the command box" was the obvious place to put a microphone. It is not any
more. Under the Top navigation the box lives in the bar along the bottom and, under the Glass face, it **rests as
its orb** and opens on a touch -- 460ms of width with the words 180ms behind (move 7, `design/nightfall/PORT.md`).
Under Side navigation it is still a box at the top of the stage.

And the canvas already draws what listening looks like. It is **move 6 of the eight**, the last one with nowhere to
live, and its subject is that same orb rather than a new control:

| | |
|---|---|
| what moves | the orb itself, scaled to **1.18** |
| timing | **320ms in, 520ms out** |
| the ring | one ring, once: `scale(.86)` to `scale(2.2)`, opacity peaking at `.55` and fading out across it |
| why once | once per utterance, not a pulse. A pulse is a loading spinner; this is the house hearing one thing |

So the affordance exists, it is drawn, and it is already on the screen. What is missing is not a control. It is a
decision about a gesture.

**One orb, two jobs.** Today a touch on the orb opens the box to type in. If talking to the house happens on the orb
too, then two gestures live on one object, and nothing on the panel currently teaches that. Three ways out were
weighed:

1. **Tap types, hold talks.** One object, two gestures, no new furniture, and it matches how a phone's keyboard
   dictation key behaves. The cost is discoverability: a wall panel has no tooltip and nobody reads a hint twice.
2. **Tap talks, the keyboard types.** Invert it: the orb is the microphone, and typing is reached from inside the
   opened box. Better for the hands-full case voice exists for, worse for the case the box exists for today.
3. **The orb splits when it opens.** At rest one orb; opened, the box carries a microphone at its far end. Two
   objects, each with one job, at the cost of the drawn composition -- the board's opened box has an orb, a line of
   words and nothing else.

**Settled on 12 September 2026: (2), tap talks.** The orb is the microphone; the keyboard is reached from inside the
box once it has opened. Two things follow, one free and one that has to be drawn.

*Free: it degrades correctly.* Where the browser cannot recognise speech, a tap opens the box to type in -- which is
precisely what a tap does today. There is no control to hide, no "the button does not appear" branch, and no second
path through the code for the panels that cannot listen. Hold-to-talk never had that property: it needed a microphone
to go missing from a control that is also the way in to typing. Tap is also the kinder gesture on a panel mounted at
head height, and for anybody who cannot hold a press steady.

*Not free: there is no letting go.* Holding gives you an endpoint for nothing -- the sentence ends when the finger
lifts. With a tap, the house decides when you have stopped talking, and that has a consequence for move 6 as the
canvas draws it. One ring, once, 320ms in and 520ms out is *the house heard one thing*: an utterance mark, and it is
right where it is, at the end. What tap-to-talk needs as well is the state before it -- **the house is listening, held
for as long as the person takes** -- and then the ring when the sentence lands. So three things fall out of the
decision: move 6 gains a resting listening state it was not drawn with, a second tap has to mean stop, and the
recogniser's endpointer becomes something a person can feel -- cut off mid-sentence if it is impatient, left hanging
if it is not. Getting that right is the substance of shape 1, and it is the one thing hold would have given away
free.

**Two constraints on building move 6, both already paid for once elsewhere in this codebase.**

- *Reduced motion.* All eight moves collapse to opacity -- `PORT.md` slice 6 -- and a scale to 1.18 is exactly what
  that block is for. The blanket rule at the top of `panel.css` kills animations and transitions, and
  `e2e/face.spec.ts` asserts nothing anywhere is left moving. That test will fail on a new scale, which is it working.
  Note that the orb's blooms are already a named exception there: a static blur is not a move. The listening state the
  tap adds has to collapse the same way, and it is the harder half: it persists, so under reduced motion it still has
  to *say* the house is listening without moving to do it.
- *Where the scale goes.* On the orb itself, with the ring as a sibling -- not on a wrapper around both. The orb's
  blooms are blurred with `filter` and the frost over them is `backdrop-filter`, and this file has three entries
  already (the rail's cards, the pane over the room, the weather column) for what happens when an ancestor forms a
  backdrop root. Whether a `transform` on an ancestor does that is worth **measuring rather than assuming**, and
  keeping the scale on the orb means never having to find out.

**What does not change.** Speech-to-text still goes to `/say` as text; the grammar still executes and the model still
only proposes; and there is still a tap for everything voice can do. Listening is a state of a control that is
already there, which is the cheapest possible way for this to arrive.

## The wall's microphone is the hub's ear

*Settled 14 September 2026, after `kiosk/` landed and turned up that a WebView has no Web Speech API. This replaces
what shape 1 said about the wall. It changes no rule and no route -- only which engine the wall reaches, and in which
order the two shapes arrive.*

`kiosk/README.md` recorded two ways out and picked neither: hand the panel **Android's own recogniser** through a
small bridge, or let the wall's voice wait for **shape 2**.

**Not Android's recogniser.** It fails the same test Chrome's was going to be held to, on worse hardware.
`SpeechRecognizer` routes to Google's recognition service and is cloud-backed by default; on-device recognition is
`createOnDeviceSpeechRecognizer()` at **API 33 or later**, and the kiosk's `minSdk` is 23 for the reason its own
README gives -- wall tablets are older than the resolvers they ship with. A tablet with no Play services has no
recogniser at all. This plan's contingency had already decided that case: if on-device recognition is not there, the
wall waits for shape 2 rather than quietly becoming a cloud feature.

**But the microphone is worth building before the recogniser, and apart from it.** The kiosk bridges **capture, not
recognition** -- `AudioRecord`, and the audio goes to the hub, where shape 2 has to be anyway. Three things follow.

*It deletes a dependency instead of adding one.* `getUserMedia` in a WebView needs a secure context too, so the
"kiosk browser told to trust `hub.local`" line was load-bearing for capture as much as for recognition -- and there
is no such flag in a WebView. Native capture never meets the question: no origin, no certificate, nothing to trust.

*The order this plan wanted survives.* **The wall still listens before phones do**, through shape 2 instead of
shape 1. Everything the wall needs is on this side of the box -- a container, a route, an APK -- while phones are
behind the certificate, which is behind the relay.

*And **works with the internet down** becomes true on the wall by construction*, rather than by a measurement that
could have gone the other way.

**One instruction shapes the bridge.** The panel asks for **an audio stream, not for text**, with two sources behind
one interface: `getUserMedia` where it exists, the kiosk's bridge where it does not. Same panel code, same route on
the brain, same Wyoming behind it. That keeps `docs/apps.md`'s *nothing lives only in the app* true -- the wall
contributes hardware, not a feature -- and the degradation settled on 12 September falls out free: no bridge and no
`getUserMedia` means a tap opens the box to type, which is what a tap does today.

Two details land in the wall's favour. A kiosk made device owner can grant itself `RECORD_AUDIO` with
`setPermissionGrantState`, so there is no permission dialog on a panel with nobody standing at it -- one more thing
the `dpm` step buys. And Android lights its own microphone indicator whenever something is capturing, which under
tap-to-talk is exactly right: an OS-level proof of *the microphone is visibly off until then*, free, and one more
reason the wall does not want a wake word.

Exit test: from the wall, tap the orb and say "kitchen lights off"; the orb holds its listening state while the
sentence is spoken, the lights go off, and the toast reads *Kitchen lights off.* within two seconds of the last word.
No model was called, and no audio left the house.

## A wake word is another route, not a replacement for the tap

*Added 12 September 2026, from the question "isn't it possible to have a wake word too, or instead?"*

It is possible, and this plan already assumes it arrives: the tier table above puts `openWakeWord` on the hub for a
panel microphone at Medium, and for every microphone, satellites included, at Large. So the question was never
whether. It is where it runs, what that costs, and whether it replaces the tap.

| where the wake word runs | what it costs |
|---|---|
| **In the panel's browser**, a small model in WASM (openWakeWord through onnxruntime-web, or Porcupine) | A build of its own, and a microphone indicator lit all day on a wall tablet. Honours *nothing leaves the room*. |
| **On the hub**, which is what the tier table says | Cheapest to build, and the panel then streams audio across the LAN all day. Worth saying plainly: the satellite rule above calls on-device detection *the only acceptable arrangement*, and the hub is a different room from the panel. This is the row to be honest about rather than the one to pick by default. |
| **A satellite standing near the panel** (ESP32, microWakeWord) | On-device by construction, which is the arrangement this plan prefers -- but it is shape 3, and it is a second box on the wall. |

**Why "too" and not "instead", in the order the reasons matter.**

1. *It is a different promise.* A wake word means always listening. The decision table already settled that against
   the panel, and the reason has not changed: a wall tablet listening all day is not the same product as a panel that
   listens when it is touched.
2. *It changes the route, and the route is what the gate is made of.* That is the fourth row added to the table in
   *What voice may do* above. A wake word on the panel does not inherit the panel's trust, because the trust came
   from the hand on the glass and not from the panel being indoors -- and a wall panel is often in a hall, within
   earshot of the front door. So the closing-half-only rule reaches the panel the moment a wake word is live on it.
   The tap does not have this problem and never will: a hand on the glass is the whole proof.
3. *Wake words miss.* In a kitchen with a tap running and a radio on, the word is not always heard, and a browser
   with no model has no wake word at all. Nothing here is voice-only, and the tap is the thing that keeps that true.

So the tap is shape 1 and does not go away. The wake word belongs with shape 2, where recognition is on the hub
anyway and the audio path already exists -- and it arrives as a switch the household turns on, with the fourth row of
the route table turned on alongside it.

## What to answer, and how

The grammar's answers are text today. Read aloud, they need to be shorter and kinder: "Front door is locked." works;
"Kitchen ceiling is on. Kitchen counter is off." should become "One of the two kitchen lights is on." A `spoken`
variant of each answer, alongside the `text`, is cheap to add in `commands.py` when shape 2 lands. Answers from the
model (explanations, proposals) are not read aloud; a proposal is a card to look at, and an explanation is a paragraph
to read.

### Where the voice comes out

*Added 14 September 2026, from the question "will the wall answer back, the way Alexa and Siri do?" The tier table
above names Piper and sizes it per host, and then never says which loudspeaker it reaches. This is that missing half,
and it is smaller than it looks: every piece is already in the house.*

**The panel plays it, the same way a speaker plays rain.** The brain synthesises the sentence with Piper and hands
the panel a URL on the hub's LAN address; the panel plays it with an `Audio` element and nothing else. That is the
arrangement `sounds.py` already has with a Cast speaker -- the hub hosts the audio, the thing with the loudspeaker
fetches it from the hub's own address -- and *works with the internet down* is inherited from it rather than argued
for again.

Three routes were weighed, and two are written down only to be refused:

| where the sound comes out | what it costs |
|---|---|
| **The panel, as audio in the page** | Nothing that is not already built. `mediaPlaybackRequiresUserGesture = false` is set in `kiosk/app/src/main/java/app/elyir/kiosk/Wall.kt:201` with a comment that anticipates exactly this -- *a sound a rule started just plays* -- so a WebView with nobody standing at it can be handed a clip and play it. The same few lines of panel code answer on a phone in shape 1. |
| **The kiosk, natively** (`MediaPlayer` behind a bridge) | A second path for what the first path already does, an APK release for a feature, and phones still need the browser path anyway. It breaks `docs/apps.md`'s *nothing lives only in the app* for nothing: the wall contributes a loudspeaker, not a feature -- the same sentence *The wall's microphone is the hub's ear* ends on. |
| **The room's speaker**, through `sounds.py` | Tempting, because that path exists whole today. Refused: an answer has to come from where the hand was, and a Cast join alone is seconds. The speaker in the corner answering a question you asked the wall is a different product, and a worse one. |

**The one trap, and it is a real one.** The clip must not land in the sounds folder. That folder is a person's own
library -- `sounds.py`'s first paragraph is *drop in rain.mp3 and "Rain" appears on every speaker's tile* -- and
minted speech there would turn up as something to play in a bedroom. So: a route of its own beside `/say`,
synthesising on demand for a short-lived token, never a file under `DATA / "sounds"` and never in `catalog()`.

**What is open, and it is the only thing here that is:** the wall has no volume. `sounds.py` takes a volume per
speaker; the panel has none, the tier table does not mention one, and a wall tablet's rocker is usually behind the
mount. The kiosk is device owner and can set the media stream itself, which is the likely answer -- but which
control a *person* touches is undecided, and it wants deciding alongside move 6 rather than after it, because a wall
that answers too loudly at night is the first thing a household will complain about.

Exit test: with the router's uplink unplugged, from the wall, tap the orb and say "is the front door locked?"; the
answer is spoken from the panel inside the same two seconds shape 2's own test already allows.

### When the house speaks, and when it stays quiet

**The house speaks when it was spoken to.** That is the whole rule, and it is the same shape as the trust rule in
*What voice may do*: the route decides, not the kind. A sentence that arrived as speech is answered as speech; a
sentence that arrived as typing is answered on the glass, silently, exactly as it is today. Nobody types at a wall
and wants it to talk back, and nobody speaks to it with their hands full and wants to walk over and read.

| how the sentence arrived | how it is answered |
|---|---|
| typed in the box | on the screen only. Nothing changes from today |
| the orb tapped and spoken to | spoken, and on the screen as well |
| the orb woken by a wake word (later) | spoken, on whichever panel heard it |
| a satellite with a wake word (shape 3) | spoken by the satellite that heard it, and on no screen at all |

Only one thing ever speaks: whatever heard the sentence. Two panels in earshot both answering it is what this
rule quietly prevents -- the answer belongs to the turn, and the turn belongs to the microphone.

**What it says depends on the kind, because two of the five must not be read aloud.** `commands.py` answers with one
of five kinds, and the paragraph above already rules out the model's: a proposal is a card to look at, an explanation
is a paragraph to read. But refusing to read those aloud leaves a person standing there, hands full, hearing nothing
at all -- which is worse than either. So each gets a **spoken pointer**: not the answer, a sentence saying where the
answer is.

| kind | spoken |
|---|---|
| `done` | the `spoken` variant. *"Living room TV on."* |
| `answer` | the `spoken` variant, shortened as above. *"One of the two kitchen lights is on."* |
| `explain` | a pointer, never the paragraph. *"There's an answer on the screen."* |
| `action` | a pointer, never the proposal. *"There's something to confirm on the screen."* Nothing happens until a hand does it; that rule does not move for voice |
| `rule` | a pointer. *"I've written that up; it's waiting under Routines."* |
| not understood -- the 422 | spoken, always. *"I didn't catch that."* Silence here reads as the house ignoring you, and `Say.vue` has already learned that lesson once on the screen |

**A message is never spoken.** Not a receipt, not a house message, not an attention chip, and -- the one worth saying
plainly -- **not an alert**. `docs/messages.md` gives the four classes and routes an alert to the band, the log, and a
push to a phone; none of those is a voice in a hall at 2am. Three reasons, in the order they matter: that plan's own
rule *a message is never the only way to know something* goes false the moment the house says a thing out loud to an
empty room; *alert-class is the household's list, not ours*, and a default that speaks is not the quiet default it
promises; and a wall panel talking to nobody is the fastest way to make a person unplug it. The wall is a screen in
the room -- `docs/messages.md` says exactly that when it refuses the wall a push of its own -- and it stays one. A
household that wants the hall to announce the front door is a new plan, and it starts from the alert class rather
than from here.

**Bedtime is the one case the route rule does not cover, and the house already knows the answer.** `RoomState.asleep`
is real state, per room and house-wide, and it is set by "good night" through this very grammar. A panel in a room
that is asleep answers on the glass and does not speak, whoever asked it -- and the sentence that put the house to
bed is the last thing it says aloud. One condition, no clock, no quiet hours, no setting: the kind of thing the house
is meant to work out rather than be told.

**No new switch.** Turning voice on is already one switch with one sentence of explanation, and answering aloud
arrives inside it -- a house that can hear can answer. The rules above are what a knob would otherwise have been for,
and each of them is something the house can decide for itself. If a household genuinely wants a wall that listens and
stays silent, that is a second line under *This hub* on the sheet the switch is already on; it should wait for
somebody to ask, rather than shipping as the fourth line of a settings sheet nobody reads.

## Decisions to make before a microphone

| Question | Proposal |
|---|---|
| Secure origin for the browser microphone | Phones only, after the https decision. The wall needs none: it captures natively, and a WebView could not have been told to trust `hub.local` in any case |
| How the wall hears at all, now that it is a WebView | The kiosk captures the audio and the hub recognises it -- settled 14 September 2026. Not Android's own recogniser, which is cloud-backed below API 33 and absent without Play services. See *The wall's microphone is the hub's ear* |
| Touched or always listening on the panel | Touched. A wall tablet listening all day is a different promise and needs a wake word (shape 2 at the earliest; see *A wake word is another route*) |
| Where talking to the house lives, now that the box rests as an orb | The orb, **tapped** -- settled 12 September 2026. The orb is the microphone and the keyboard is reached from inside the opened box. See *The orb already is the microphone* |
| What the tap costs, having no "letting go" | A listening state move 6 was not drawn with, a second tap that means stop, and an endpointer whose patience a person can feel. This is the substance of shape 1 |
| A wake word on the panel as well as the tap | Yes, but with shape 2 and not before, and as a switch a household turns on. It adds a route rather than inheriting the panel's, so the closing-half-only rule reaches the panel with it |
| Whether the browser's recognition really runs on the device | **Measured 14 September 2026: no.** Chrome offers `processLocally` and then refuses it with `language-not-supported` until the model has been fetched, which on a machine that has never used the API is every time; the fallback is a cloud. So phones wait for shape 2 as well, exactly as shape 1 said they would. Behind `?listen=browser` in `app/src/ear.ts`; real Chrome, not a test harness |
| Where speech-to-text runs | The browser in shape 1, which is phones; the hub in shape 2, which is the wall and everything after it; never a cloud by default |
| How big a model | Chosen from the host's class at install, overridable in `.env`; the Large tier is the design point, the Small tier the floor |
| Does voice ever bypass confirmation for the model's proposals | No |
| May voice do locks, doors and the garage | Yes, from the panel -- it is the same trust as a tap. From a wake-word satellite, the closing half only. See *What voice may do* |
| Does the assistant see audio | No. It sees text, the same text a person could have typed |
| Where a spoken answer comes out | The panel plays it as audio in the page, from a clip the hub synthesised -- not natively in the kiosk, and not on the room's speaker. Settled 14 September 2026; see *Where the voice comes out* |
| When the house answers aloud at all | When it was spoken to, never when it was typed to, and never in a room that is asleep. The route decides, the same way it decides what voice may do |
| Whether the wall reads messages and alerts aloud | No. A message is never spoken, alerts included; `docs/messages.md`'s classes route those to the band, the log and a phone. A household that wants the hall to announce the front door is a new plan |
| What the model's answers sound like | They are not read out -- a proposal is a card and an explanation is a paragraph -- but silence is worse, so each gets a one-line spoken pointer to the screen |
| How loud the wall is, and who turns it down | **Open.** The kiosk is device owner and can set the media stream, which is the likely answer; which control a person touches is undecided and belongs with move 6 |

## Not in this plan

Conversation (a back-and-forth with the model by voice), music search by voice, voice-driven setup, per-person voice
recognition, and anything that needs a vendor's account. If a household needs one of these, it is a new plan.

**And speaking to the house from away.** *Added 14 September 2026, because the exit test above stopped covering it.*
Shape 1 is gated behind the real certificate per hub, and that certificate is the same public name per house that
`docs/away.md` reaches through the maker's relay -- so the first phones that can speak to the house are, by
construction, phones that can also be away from it. A phone away that tapped the orb would stream audio to the hub
across a VPS somebody else runs.

The promise would survive it: nothing between a phone and the house terminates TLS, the relay routes by SNI and
carries bytes it cannot read, and the house holds the only key. What would leak is not the audio but the fact of it --
that a house streamed audio, and when. `docs/messages.md` has already reasoned about exactly this shape once, for web
push: *that rule is kept by the encryption and broken by the metadata.*

Nobody has asked for it, the exit test above is an at-home test, and a microphone is not a thing to extend to a new
route quietly. So it is deferred rather than designed: **voice works on the house's own Wi-Fi.** A panel away shows
the box and the keyboard, which is what it has today. If a household wants to speak to their house from the car, that
is a new plan, and the first thing it has to say is what the relay can see.

## Milestones

1. **Grow the grammar from the log.** Two weeks of `said` events from the house here; every not-understood phrase
   that a reasonable person would expect to work becomes a pattern with a test. Exit: fewer than one in ten typed
   sentences reach the assistant or a "didn't catch that".
2. **Move 6 on the orb.** The gesture is decided -- tap talks -- so what is left is the drawing: the listening state
   the orb holds while somebody speaks, then the ring once when the sentence lands (scale 1.18, 320/520), a second
   tap that means stop, and an endpointer whose patience a person can feel. It needs no recogniser and can be built
   against a stub. Move 6 is the last of the eight with nowhere to live, so this milestone finishes the canvas before
   voice has an engine at all.
3. **Shape 2 on the hub, which is the wall's voice.** Wyoming, faster-whisper and Piper as containers with profiles
   like the radios; the tier chooser in `install.sh`; a route beside `/say` that takes audio; the brain speaks
   Wyoming; the offline test on a Pi 5 and on a NUC-class box; the measured latency for each tier written into the
   table above. The answering half rides along with it and needs no microphone at all -- Piper, the `spoken` variants
   in `commands.py`, the route that mints a clip and the panel that plays it can be built and heard behind a preview
   flag, the way `?listen=1` gave the orb something to listen to before any engine existed. Then the smallest native
   piece in the whole plan -- `AudioRecord` and the bridge in `kiosk/` -- last,
   because until the rest of this lands it has nothing to talk to.
4. **Shape 1 on phones** -- which is now a smaller milestone than it was, and later. Its recognition was measured on
   14 September 2026 and Chrome's is a cloud service unless somebody has fetched the model, so this no longer waits
   only on the certificate in `docs/away.md`: it waits on shape 2, whose recogniser it will use. What is left of it
   is the certificate, a secure origin, and pointing the orb at the hub instead of at the browser -- the same route
   and the same answers the wall already has. A browser that grows real on-device recognition would make it a shape
   of its own again, and nothing here has to change for that to be true.
5. **Shape 3 with one satellite.** One box in the kitchen, paired from the panel, placed on New devices, the guest
   test. And, before it ships rather than after, what "more than a voice" means for opening and unlocking -- this is
   the milestone where a wake word in a room makes that question real.
