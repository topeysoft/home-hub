# Security

Elyir Home Hub runs inside people's homes: it unlocks doors, opens garages and shows cameras. A flaw in
it is a flaw in somebody's house, so please tell us privately first.

## Reporting a problem

Email **security@elyir.app**. Please don't open a public issue, pull request or discussion for it.

Say what you found, where (a file, a screen, an address on the hub), and how to see it happen. A rough
note is better than none; we will ask for what we need.

What happens next:

- We answer within three working days to say it arrived and who is looking at it.
- We tell you what we found, and what we will do about it, as soon as we know.
- A fix ships in a release, and the release notes credit you unless you would rather they didn't.
- Please give us 90 days, or until the fix ships if that is sooner, before you publish anything.

## What is in scope

Everything in this repository: the brain, the panel, the driver layer's configuration, the installer and
update scripts, the relay and its registration service, the bridge puck, the light strip and the wall
launcher. The maker-run service at `elyir.app` is in scope too.

Problems in Home Assistant, Zigbee2MQTT, Z-Wave JS UI, the Matter server or Mosquitto themselves belong
with those projects. Tell us as well if the hub makes one of them worse than it would otherwise be.

## What we will never ask for

We will never ask for your hub's code, a phone's pass, an account password or a key. Nobody from this
project needs any of them to look at a report.
