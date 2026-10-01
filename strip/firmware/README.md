# strip/firmware

A light strip controller: a Matter device in its own right, and a little more in a house with our hub.
**The decisions behind it are `docs/strip.md`**, which opens with where the whole thing stands; this file is
only how to build it and put it on a board.

It is ESP-IDF and esp-matter, not PlatformIO and not Arduino. That is not taste: the Arduino framework ships
its Matter libraries with `CONFIG_ENABLE_CHIPOBLE` unset on every target, so a strip built that way can never
advertise itself for commissioning and a household with an Apple TV and no hub of ours could not set one up
at all.

## What you need once

ESP-IDF **v6.0.2** and esp-matter, which is what esp-matter's own README asks for. Neither is small — about
9 GB with toolchains, and the first build takes tens of minutes because connectedhomeip is enormous.

    git clone -b v6.0.2 --depth 1 --recurse-submodules --shallow-submodules \
        https://github.com/espressif/esp-idf.git ~/esp/esp-idf-v6.0.2
    ~/esp/esp-idf-v6.0.2/install.sh esp32s3

    git clone --depth 1 https://github.com/espressif/esp-matter.git ~/esp/esp-matter
    cd ~/esp/esp-matter && git submodule update --init --depth 1
    cd connectedhomeip/connectedhomeip && ./scripts/checkout_submodules.py --platform esp32 linux --shallow
    cd ~/esp/esp-matter && ./install.sh

**On a Mac, read the last section first.** Three of those steps failed here for reasons that had nothing to do
with Espressif, and the fixes are not guessable.

## Every session

    export IDF_PYTHON_ENV_PATH=~/.espressif/python_env/idf6.0_py3.10_env
    . ~/esp/esp-idf-v6.0.2/export.sh
    . ~/esp/esp-matter/export.sh

**The first line is not optional on a machine with more than one Python**, which is most of them. `export.sh`
works out which virtual environment to use from whichever `python3` is on the PATH *at that moment*, so a shell
with 3.14 goes looking for `idf6.0_py3.14_env` and fails with:

    ERROR: ESP-IDF Python virtual environment ".../idf6.0_py3.14_env" not found.
    Please run the install script to set it up before proceeding.

The install script has already been run; the environment is just under a different Python's name. `ls
~/.espressif/python_env/` says which one exists, and `IDF_PYTHON_ENV_PATH` points at it regardless of what the
shell's `python3` happens to be. Re-running `install.sh` also works, but it builds a second multi-gigabyte
environment to solve a naming problem, and a Python new enough to cause this is often too new for ESP-IDF.

## Build and flash

Once per checkout, because `sdkconfig` and `build/` are not in git:

    idf.py set-target esp32s3

**A checkout that built before 24 September has a stale `sdkconfig`.** `sdkconfig.defaults` only fills in
settings `sdkconfig` has never had an answer for, and "not set" is an answer, so turning rollback on and
Matter's own updates off there does not reach an existing `sdkconfig`. Remove it and run `set-target`
again; `tools/build-strip.sh` refuses to build a release from one that is still wrong.

Then, with the board on USB:

    idf.py -p /dev/cu.usbserial-XXXX build flash monitor

`idf.py -p <port>` wants the port the board actually enumerates as. A devkit with a UART bridge shows up as
`/dev/cu.wchusbserial*` or `/dev/cu.usbserial*`; an S3 on its native USB port shows up as `/dev/cu.usbmodem*`.
Both work — the firmware logs to whichever console is open, which it did not always do.

A board that has been commissioned before keeps its fabric in NVS, and a plain flash does not clear it. To
start genuinely new:

    idf.py -p <port> erase-flash flash

## The data pin

`DATA_PIN` is GPIO 5 by default and is a fact about the board on the desk rather than about this firmware.
GPIO 5 is free on a bare devkit and is a camera pin on several of the S3 boards people actually have.

    idf.py -p <port> -DDATA_PIN=21 build flash

To go back to the default, **unset** it rather than passing an empty one — `idf.py -UDATA_PIN build`. The
value is a CMake cache entry and survives until it is removed.

`-DCLOCK_PIN=6` gives the devkit a clock line too, so a two-wire strip (APA102, SK9822) can be tried on a
bench before there is a product board to try it on. Without it the devkit has one wire, as it always had.

## Rev A, the strip controller

The product board (`home-hub-hardware`, `strip/strip-revA/`) is a different build of the same firmware,
chosen when it is built, because a pin map is soldered and cannot be asked. Nothing given is the devkit,
exactly as above; `STRIP_BOARD=reva` is the controller. Give it a build directory of its own:

    idf.py -B build-reva -DSTRIP_BOARD=reva set-target esp32s3
    idf.py -B build-reva -DSTRIP_BOARD=reva build
    idf.py -B build-reva -p <port> flash monitor

Its `sdkconfig` lives in `build-reva/`, not beside this file, so the devkit's settings and the board's never
mix; `sdkconfig.defaults.reva` adds 16 MB of flash, `partitions-reva.csv` and the module's quad PSRAM on top
of the usual defaults. The image is `build-reva/strip-reva.bin`, and the different name is not cosmetic: it
is written into the image, and a strip refuses an update built for the other board. Every pin is in
`main/board.h`, copied from the schematic's netlist; `DATA_PIN`, `CLOCK_PIN` and `BUTTON_PIN` mean nothing
for this board and the build stops if one is set (`idf.py -UDATA_PIN`).

**It has no USB socket.** It is programmed through the factory jig's pads: GND, 3.3 V, reset, BOOT, USB D−/D+
(GPIO 19/20) and UART0 (43/44), powered through its supply socket. **Its first flash has to be by cable**,
because `partitions-reva.csv` — like the 8 MB table every strip already in a house carries, which stays as it
is — is the one thing an update can never change.

**What it does before it lights anything** (`main/guard.h`): both runs are held off while the supply is
measured; it is classed as a 5, 12 or 24 V supply, or out of range; and each run is switched on only if the
supply is the kind it was first lit on. Then each frame is dimmed so a run stays under 4.75 A — less once the
board is past 85 °C — and a run whose switch keeps tripping, or whose data line has more than 6 V on it, is
held off until the board is next powered on. A healthy boot says, as well as the usual lines:

    I (390) guard: supply 12.1 V, a 12 V supply
    I (391) guard: run 1 on
    I (391) guard: run 2 on
    I (452) strip: 0.4.1  chip 2e4258  pin 11  300 lights, order grb
    I (453) strip: board reva  run 2 on pin 13  300 lights, order grb

The first boot also says `run 1 is first lit on a 12 V supply`; a later boot on a different kind of supply
says `run 1 was set up on a 12 V supply and this one is 24 V` and leaves it dark. (Those lines are what the
code prints. No board has printed them yet.)

**A run that has never been told its wire finds it** (`main/wire.h`), once, at the first boot it lights:
faintly on one wire, then on two, reading the switch's current monitor after each, before the setup glow.
A clear answer is kept where `type/set` keeps one; an unclear one drives one wire and is not asked again.
The boot says which, with the three readings, and the hub hears it on `wire` (`run2/wire`):

    I (470) strip: run 1 at first power: two wires (dark 0.021 A, one wire 0.022 A, two wires 0.064 A)

The thresholds it decides by have not been measured; a bench with one-wire and two-wire strips of a few
lengths sets them. A one-wire strip may flicker for an instant during it.

**The button is GPIO 4**, sealed into the wall of the box, with the devkit's rules and one more: a press
shorter than 30 ms is a contact bouncing, not a finger.

## When a strip stays dark, run this first

    idf.py -p <port> -DSELFTEST=1 -DDATA_PIN=48 build flash monitor

Nothing attached: it drives the board's own WS2812 through red, green, blue and warm white, 1.5 seconds each,
saying which is which. Four colors in that order means the driver, the timing, the bit order and the RMT setup
are all fine and the fault is on the bench — most often a common ground, `DIN` rather than `DOUT`, or the
strip's own 5 V. A color in the *wrong* place is still a pass: it means that board's own light is not `grb`,
which is the same question the panel asks about a strip. Nothing at all means the fault is in `pixels.cpp`.

It exists because the first dead strip here turned out to be a power problem after an evening of swapping pins.

## What a healthy boot says

    I (610)  strip: 0.4.0  chip 2e4258  pin 5  300 lights, order grb
    I (612)  strip: maker's keys d123,0604
    I (1470) chip[DL]: CHIPoBLE advertising started

Two lines you will also see and can ignore: `OTA app partition slot 1 is not bootable` is the empty spare
update slot, which is what an unflashed one looks like; and Wi-Fi connect failures before commissioning are
Matter retrying a network it has not been given yet.

If it says **`THE LIGHT DRIVER DID NOT START`**, the RMT peripheral refused the pin. Change it.

## Updates

A strip takes its fixes from the hub, the way a bridge puck does (`docs/strip.md`, "Updates, the puck's way";
`main/fwupdate.h`). The version is `STRIP_FW` in `main/fwupdate.h` and names the *next* release.

    tools/build-strip.sh          the release image, into releases/strip/
    tools/dev.sh strip            this tree, onto a strip in a house whose hub follows a branch, now

A test build is `STRIP_FW-d<minutes>`, passed as `idf.py -DSTRIP_FW=...`. That is a CMake cache entry, so it
sticks until it is cleared with `idf.py -DSTRIP_FW= build`; `tools/dev.sh strip` clears it itself.

A new image has three minutes to reach the hub or the bootloader puts back the one before. Only a bootloader
built with `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE` can do that, and only a cable writes a bootloader, so a strip
flashed before 24 September needs flashing once more over USB (a plain `idf.py flash` writes the bootloader).

## Commissioning it

The board prints its pairing code at boot while it has no fabric. On a development build that code is the same
on every device — CHIP's own `20202021`, discriminator 3840, manual code `3497-011-2332` — because
`CONFIG_ENABLE_TEST_SETUP_PARAMS` is on. It is published in connectedhomeip's source, so it is not a secret and
a unit carrying it cannot be sold.

Add it in Apple Home or Google Home like any other Matter accessory; expect an "uncertified accessory" warning,
which is the test vendor id being honest. **Commissioning through our own hub does not work on a Mac** — see
`docs/strip.md`, item `2-mac`.

## Forgetting the house

Hold the **BOOT** button. After a second the strip goes red to say the hold registered; keep holding to five
seconds and it forgets its fabric and its settings and comes back new. Let go before then and nothing happens.

A hold only counts once the button has been seen released since boot. Without that, a board whose BOOT pin is
held or simply sits low factory-resets itself five seconds into every boot, for ever, which from the outside is
a strip that paired once and never again. (`main/press.h`, held to it by `test_press_native.cpp`.)

## The tests that run on a Mac

    c++ -std=c++17 -O1 -o /tmp/px test_pixels_native.cpp && /tmp/px
    c++ -std=c++17 -O1 -DSTRIP_BOARD_REVA -o /tmp/px test_pixels_native.cpp && /tmp/px
    c++ -std=c++17 -O1 -DSTRIP_BOARD_REVA -o /tmp/guard test_guard_native.cpp && /tmp/guard
    c++ -std=c++17 -O1 -o /tmp/press test_press_native.cpp && /tmp/press
    c++ -std=c++17 -O1 -o /tmp/uri test_hub_uri_native.cpp && /tmp/uri
    c++ -std=c++17 -O1 -o /tmp/versions test_versions_native.cpp && /tmp/versions
    c++ -std=c++17 -O1 -o /tmp/wire test_wire_native.cpp && /tmp/wire
    c++ -std=c++17 -O1 -o /tmp/look test_look_native.cpp && /tmp/look

On a Mac whose newest SDK will not link, add `-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk`.

## On a Mac, the things that are not your fault

Three of the setup steps above failed here, and none of the causes were Espressif's.

- **The Command Line Tools SDKs had no C headers at all** and the default one carried a corrupt architecture
  entry, so nothing native could compile. Every build here borrowed Xcode's instead:

      export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

  The proper fix is `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.

- **Rosetta 2 was not installed**, and CHIP's `zap-cli` is x86_64, so `install.sh` died with
  `Bad CPU type in executable`. `softwareupdate --install-rosetta`.

- **Two PlatformIO cores** fought over the build directory back when this was a PlatformIO project: builds
  failed in under a second and then succeeded unchanged. Irrelevant here now, but it still affects `brilliant/`.
