# Elyir Home Hub

A smart home hub that a household sets up from its own screen and never has to understand. Plug it in, open
**hub.local**, answer a few questions, and the house is yours: rooms, lights, locks, cameras and the rest, run
from a wall panel or any phone, with the internet up or down.

It is built on one principle: **own the experience and the intelligence, rent the drivers.** Under the panel,
Home Assistant does the talking to devices. Nobody in the house ever has to open it, read a setting in it, or
learn a word of its vocabulary.

## Setting one up

1. Plug the hub into power and the router (or its Wi‑Fi). Wait two minutes.
2. On a phone or tablet on the same Wi‑Fi, open **http://hub.local**.
3. Answer the questions on the screen: your name, where home is, which rooms, what to add.

That is the whole setup. From there:

- **Things already on your Wi‑Fi** (TVs, speakers, bridges) are noticed on their own and offered under
  *Found nearby*. Anything else is added by brand from the same screen, including things that live behind an
  account, like Nest, Ring and Tesla.
- **Zigbee, Z‑Wave and Matter devices** pair from the same screen: the hub says what to press.
- **Not sure which one is which?** Every new device can blink: it flashes three times and goes back to how it
  was, so you can stand in the room and name the right one.
- **Plain words work.** The box at the top of Home takes *kitchen lights off*, *movie in the den*, *is the front
  door locked?*. Simple sentences run at once; anything else goes to the assistant, which proposes and waits
  for your tap.
- **Phones are let in, not just connected.** Once the house has a code, a new phone asks from its own screen,
  somebody at the wall taps *Allow*, and every phone is listed in one place with a *Remove*.

## Away from home

A house can have its own web address, so the phones you have let in work from anywhere, with a real
certificate and nothing else to install. It is optional and offered at the end of setup: the house is complete
without it. The relay that carries it passes along traffic it cannot read, and it is part of this repository
(`relay/`), so you can run your own. [`docs/away.md`](docs/away.md) has the design.

## Installing a hub

Any Linux machine with systemd can be a hub: a Raspberry Pi 5, an Intel NUC, a mini PC, or a VM, running
Debian, Ubuntu, Raspberry Pi OS or Fedora.

```sh
curl -fsSL https://raw.githubusercontent.com/topeysoft/home-hub/main/install.sh | sudo bash
```

A ready-made Raspberry Pi image is attached to each release: flash it, power it, open `http://hub.local`.
Zigbee and Z‑Wave radios can be plugged in before or after, and the hub finds them.
[`docs/developing.md`](docs/developing.md) has the details, from preparing a Pi to working on the code.

## How it is built

- **The brain** (`brain/`) is the hub's own service: rooms, rules, the assistant, phones, updates.
- **The panel** (`app/`) is what everyone sees, on the wall and on phones.
- **The driver layer** (`driver-layer/`) is Home Assistant, Zigbee2MQTT, Z‑Wave JS UI, the Matter server and a
  broker, run in containers and reached only through their APIs.
- **The relay** (`relay/`) is the optional service for reaching a house from outside.
- **Devices of our own** live here too: the light strip (`strip/`), the bridge puck (`puck/`), the wall's
  launcher (`kiosk/`) and the bridge to Apple Home, Google Home and Alexa (`matter-bridge/`).

The design boards in `design/` are where every screen was drawn and chosen before it was built, rejected
directions included, and `docs/` holds the decisions behind each part.

## Rules that do not change

- Works with the internet down.
- HA is touched only through its APIs; its UI is the Advanced door, never the product.
- The assistant model writes and explains rules. It never executes one.
- Setup is a conversation on the screen, never a file to edit.
- Controlling the house never needs a code. Changing it does, once one is set.
- Being on the Wi‑Fi gets a phone nothing once there is a code. The owner lets a phone in; only the owner lets it out of the house.

## Contributing

Pull requests are welcome; [CONTRIBUTING.md](CONTRIBUTING.md) says what CI checks and how a change is written,
and a contributor license agreement ([CLA.md](CLA.md)) is needed before one is merged. Coding agents start with
[AGENTS.md](AGENTS.md). To report a security problem, see
[CONTRIBUTING.md](CONTRIBUTING.md#reporting-a-security-problem) rather than opening a public issue.

## License

[GNU Affero General Public License v3.0](LICENSE). Copyright 2026 Temitope Adeyeri.

Free software, in the sense that matters: run it, read it, change it, share it, sell it. The one condition is
that it stays that way: if you distribute this hub, or run a modified version as a service other people reach
over a network, those people are entitled to your source under the same license.

The source is public on purpose, and the license is the promise behind it. A box that claims to work with the
internet down, and to keep a household's life off somebody else's servers, should be readable by the people it
asks to trust it, and no household running this should ever be stranded by a maker who stops caring.

Commercial licenses, for anyone who wants to build on this without the AGPL's obligations, are available
separately. Open an issue or get in touch.

## Names

Brilliant, Home Assistant, Ring, Nest, Tesla, WiZ, Apple Home, Google Home, Alexa, Matter, Zigbee and
Z-Wave are trademarks of their owners. They appear here only to say what the hub works with: this
project is not affiliated with, sponsored by or endorsed by any of them, and nothing it sells carries
their names or logos.
