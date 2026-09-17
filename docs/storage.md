# Storage: what the hub runs from, and knowing when it is wearing out

*Written 16 September 2026, from two questions asked in a row: is eMMC capable of this job or is NVMe better, and
what would it take for the hub to say, months ahead, that its storage is wearing out. The first is a finding and a
decision, recorded here so it is not re-argued. The second is a plan, not yet built; the section "Where this stands"
says what has landed. `docs/shipping.md` is the wider plan this belongs to.*

## The finding: eMMC is capable, and it is the right part for the unit that is sold

**What the hub writes.** The engine's recorder is the heavy writer: a SQLite database committed every second by
default and kept for ten days. Behind it come the brain's event log, Zigbee2MQTT's and Mosquitto's state, and the
image layers an update pulls. A busy house lands somewhere between one and five gigabytes a day. The failure people
associate with "flash on a Pi" is the microSD card: a weak controller and little wear levelling. eMMC is a different
class of part, a managed controller with real wear levelling, rated for hundreds to a few thousand program cycles per
cell. A 32 GB part at a conservative rating outlasts the product at that write rate by a wide margin. The strongest
evidence is that Home Assistant's own hardware, Green and Yellow, ships on eMMC and runs this same stack.

**Where NVMe wins, and whether it matters here.**

| | eMMC on a Compute Module 5 | NVMe on a Pi 5 or a CM5 carrier |
|---|---|---|
| Sequential speed | ~250 MB/s | ~450 MB/s, capped by the Pi's PCIe Gen2 x1 |
| Capacity | 16 to 64 GB | 256 GB and up for the same money |
| Endurance | Enough for this workload | Far more than needed |
| Assembly | None; it is on the module | A HAT or M.2 slot, a screw, boot-order firmware |
| Field repair | Replace the module, or the hub | Swap the drive |
| Power and heat | Negligible | A few watts more, inside a sealed box |

Speed is irrelevant: the panel waits on the engine's start-up and on the radios, never on disk throughput. Capacity is
the one real gap, and it only bites in two futures that are not in the product today: recorded camera video, and a
large local speech model kept alongside long history.

**The decision.**

- **The CM5 unit ships on 64 GB eMMC.** 32 GB works, but the undo in `docs/updates.md` keeps the previous brain image
  beside the new one and the driver images together run to several gigabytes, so 64 GB is the size nobody has to
  think about.
- **NVMe stays for the Pi 5 kit and the voice tier.** A Pi 5 has no eMMC, and a microSD hub is not something to sell.
  Most CM5 partner carriers carry an M.2 slot too, so an NVMe option on the same board costs no redesign later.
- **The software side is done either way.** The recorder's commit interval and retention (item 4 in
  `docs/shipping.md`) is what turns a gigabyte a day into a fraction of that, and it matters more than the part.
- **A microSD card is never the product**, and a hand-installed hub on one is told so once, quietly (below).

What makes the eMMC choice safe rather than merely probable is the plan that follows: both parts report their own
wear, and the hub should say so long before the part fails.

## Rules that do not change

- **Say the effect, and what to do.** "The hub's storage is wearing out; back up the house and plan to replace it",
  never a percentage of program cycles, never a device path, never the word SMART. `brain/hub/health.py` already
  holds the rule that every line carries what can be done about it, in `acts`; this line is no exception.
- **The brain never touches the hardware.** Reading wear needs root and the raw device (an ioctl for NVMe, sysfs for
  eMMC). The host reads it and writes a small file into the data volume; the brain only reads the file. This is the
  same shape as `update.json` and `channel.json`, and for the same reason: the thing with a network port is not the
  thing with root.
- **Works with the internet down.** Nothing here asks anyone anything. A hub in a house with no connection still
  learns that its storage is wearing out.
- **A line is a job, said once.** The line appears when a threshold is crossed and stays until the storage is
  replaced; it is not repeated, and it does not turn into three lines as the number grows. Crossing a threshold is one
  `storage` event in the log, so *Recent* and the backup carry it.
- **Nothing is claimed that cannot be known.** A memory card reports nothing about its wear, so a hub on one is never
  told it is fine. It is told, once and only under *This hub*, that it cannot know.

## What exists today

- `Health.storage()` in `brain/hub/health.py` says "The hub's storage is nearly full: 1.2 GB left" from
  `shutil.disk_usage` on the data directory, with no `acts`. It stays exactly as it is; the wear line sits beside it.
- The host already runs a periodic job for the brain: `home-hub-channel.timer` runs `host/channel.sh` every half hour
  and writes `channel.json` into `brain-data/`; `install.sh` copies the units, enables the timer, and runs the script
  once. The wear job copies that arrangement with a daily period.
- `driver-layer/host/harden.sh` is where the host is made an appliance; installing a small tool the wear reader needs
  belongs in `install.sh` beside it.
- *This hub* (`app/src/HubPage.vue`) is a list of facts and one action each: the version, the backup, the restore.
  The storage row goes there.

## The plan

### 1. The host reads the wear, once a day

`driver-layer/host/storage.sh`, run by `home-hub-storage.timer` three minutes after boot and once a day after that,
with a few minutes of jitter. `install.sh` copies the pair, enables the timer, and runs the script once, the same way
it does for the channel. The script never fails the timer: anything it cannot read becomes `null`, not an error.

**Which device.** The data directory's filesystem, from `findmnt`, walked up to its whole-disk parent through `lsblk`.
Then its kind, from the kernel:

| Kind | How it is recognised | What it can say about wear |
|---|---|---|
| eMMC | `mmcblk*` whose `/sys/block/<dev>/device/type` is `MMC` | `life_time` and `pre_eol_info` in the same sysfs directory |
| memory card | `mmcblk*` whose type is `SD` | Nothing |
| NVMe | `nvme*` | `nvme smart-log -o json` from `nvme-cli`, which `install.sh` installs when an NVMe is present |
| disk | `sd*` (a USB SSD, a VM's virtual disk) | SMART through `smartctl` if it is there; otherwise nothing, and that is fine |

**What eMMC reports, exactly**, so nobody has to look it up again. `life_time` is two hex bytes, one per cell type
the part uses (`0x01 0x02`): each is the wear in ten-percent steps, `0x01` meaning 0 to 10 % used, `0x0A` 90 to
100 %, `0x0B` past its rating. The larger of the two is the number. `pre_eol_info` is one byte: `0x01` normal,
`0x02` warning (eighty percent of the reserved blocks consumed), `0x03` urgent. Both files exist on any kernel that
runs a Pi 5 or CM5.

**What NVMe reports.** `percentage_used`, a vendor's own estimate of life used, 0 to 255 and allowed past 100;
`available_spare` and `available_spare_threshold`, where spare below the threshold is the drive saying it is out of
room to remap; `media_errors`, a count that should stay at zero; and `critical_warning`, a bitfield where any set bit
is the drive asking to be replaced.

**The file.** `brain-data/storage.json`, written atomically (a temp file and a rename):

```json
{"checked": 1789574000, "kind": "emmc", "size": 62537072640,
 "worn": 0.1, "spare_low": false, "errors": 0, "eol": "normal"}
```

`worn` is 0 to 1 or `null` when the part cannot say. `eol` is `normal`, `warning` or `urgent` from eMMC's own word,
and for NVMe is derived: `urgent` when the spare is below threshold or any critical bit is set, else `normal`. Kinds
are `emmc`, `sd`, `nvme`, `disk`. Nothing in the file names a device path.

### 2. The brain turns the file into one line, when it is earned

`Health.storage()` reads `storage.json` beside the free-space check. The line appears at the first of these and is
worded by the worst of them:

| Condition | The line | `acts` |
|---|---|---|
| `worn` ≥ 0.8, or `eol` is `warning` | *The hub's storage is wearing out: about a fifth of its life is left. Back up the house, and plan to replace the hub's storage.* | Back up |
| `worn` ≥ 0.9, or `eol` is `urgent`, or `spare_low`, or `errors` > 0 | *The hub's storage is nearly worn out. Back up now, and replace it soon; everything is still working today.* | Back up |
| file older than three days | No line. *This hub* shows when it was last checked, which is the honest version of this. | |
| kind is `sd` | No line in *Needs a look*. | |

The one act is *Back up*, which is the `backup` route *This hub* already has, behind the code, because for an eMMC
unit the repair is a replacement hub restored from that file, and for an NVMe hub the repair is a new drive and the
same restore. `since` is the first time the threshold was crossed, kept in settings as `storage_worn_since` so it
survives a restart and rides the backup; it is cleared when a check comes back under the threshold, which is what a
replaced part looks like. The crossing, and the clearing, are each one `storage` event in the log.

The brain also adds `storage` to `status()`, in words the panel draws without interpreting: the kind as a household
word (*eMMC*, *memory card*, *NVMe drive*, *disk*), the size, what is free, the wear as a sentence ("3 % worn", "cannot
say how worn it is"), and when it was checked. Those words are written in `health.py`, not in the panel, for the same
reason every other line is.

### 3. *This hub* gets a Storage row

One row under the version: *Storage · eMMC · 64 GB · 41 GB free · 3 % worn · checked yesterday*. On a memory card:
*Storage · memory card · 32 GB · 20 GB free · a card cannot say how worn it is*, and nothing more, ever. When the
wear line is showing in *Needs a look*, the row says the same sentence in fewer words, and the *Back up* button beside
it is the same one as always.

### 4. Tests, before any of it is called done

- `driver-layer/host/tests.sh` gains a group for `storage.sh`: a fake `/sys` directory for an eMMC at each
  `life_time` step and each `pre_eol_info`, a fake `nvme` on `PATH` printing a smart-log, a memory card, a disk with
  no tool; each checked for the JSON written and for the script exiting 0 whatever it found.
- `brain/tests/test_health.py`: a temp `storage.json` for each row of the table above, the stale file, the memory
  card, the crossing that writes `storage_worn_since` and the check that clears it, and the exact words.
- `app/tests`: the row on *This hub* draws the words it is given and nothing else.

### 5. What a household sees, in order

Nothing, for years. The first line anyone sees is at eighty percent, with the backup button beside it. Nothing here
runs on day one except a row on *This hub* that says what the hub runs from, which is also the first thing a support
conversation would ask.

## Where this stands

*16 September 2026: planned, nothing built. Update this line as pieces land.*

## Open decisions

- **Should a worn hub stop updating itself overnight?** No, on current thinking: an update writes a few hundred
  megabytes, which is nothing against the daily recorder, and a hub that stops updating because it is worn has traded a
  slow problem for a security one. Worth writing down that it was chosen.
- **Temperature.** NVMe reports it and eMMC does not. A sealed box on a shelf could use a line about it; it is not this
  plan, because it is not about wear.
- **The Pi 5 kit on a card by mistake.** A hand install can boot from microSD with an empty NVMe attached and never
  copy across if `firstboot.sh` did not run. The *This hub* row will say *memory card*, which is the tell; whether that
  deserves a *Needs a look* line with a way to fix it is a decision for when the kit exists.
