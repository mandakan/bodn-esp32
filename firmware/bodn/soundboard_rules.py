# bodn/soundboard_rules.py — Soundboard rule engine (pure logic, testable on host)
#
# 8 mini buttons trigger sounds in the current bank.
# 5 arcade buttons trigger shared sounds (across all banks).
# 2 toggle switches select the bank (2-bit: 0–3).
# Volume is 0–100; mute suppresses output without losing the level.

try:
    import ujson as json
except ImportError:
    import json

import os

from bodn.assets import resolve

NUM_MINI_BUTTONS = 8
NUM_ARCADE_BUTTONS = 5
NUM_BANKS = 4  # 2 toggles → 2² = 4 banks

SOUNDS_ROOT = "/sounds"
MANIFEST_PATH = SOUNDS_ROOT + "/manifest.json"

# Default bank colors (RGB tuples)
_DEFAULT_COLORS = [
    (255, 107, 53),  # bank 0 — orange
    (59, 130, 246),  # bank 1 — blue
    (16, 185, 129),  # bank 2 — teal
    (245, 158, 11),  # bank 3 — amber
]

# Default bank names (Swedish / English keys looked up via i18n)
_DEFAULT_BANK_NAMES = ["sb_bank_0", "sb_bank_1", "sb_bank_2", "sb_bank_3"]

# Volume step per encoder detent
VOLUME_STEP = 5


def bank_from_toggles(sw0, sw1):
    """Return bank index 0–3 from two toggle switch states.

    sw0 is the least-significant bit.
    """
    return (sw1 << 1) | sw0


def wav_path(bank, slot):
    """Return the filesystem path for a mini-button sound.

    Checks SD card first, falls back to flash via assets.resolve().
    bank: 0–3, slot: 0–7
    """
    return resolve("{}/bank_{}/{}".format(SOUNDS_ROOT, bank, slot) + ".wav")


def arcade_wav_path(slot):
    """Return the filesystem path for an arcade-button sound (shared across banks).

    Checks SD card first, falls back to flash via assets.resolve().
    slot: 0–4
    """
    return resolve("{}/arcade/{}".format(SOUNDS_ROOT, slot) + ".wav")


def _file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def scan_bank(bank):
    """Return a list of NUM_MINI_BUTTONS bools: True if the WAV file exists."""
    return [_file_exists(wav_path(bank, i)) for i in range(NUM_MINI_BUTTONS)]


def discover_bank(bank):
    """Scan the bank directory and return up to NUM_MINI_BUTTONS (path, label) pairs.

    Files are sorted alphanumerically; the filename stem (without .wav) is the
    label.  Only .wav files are included; numbered files (0.wav–7.wav) are not
    excluded — this function is only called when none of those are present.
    Returns an empty list if the directory does not exist or is empty.
    """
    dir_path = "{}/bank_{}".format(SOUNDS_ROOT, bank)
    try:
        entries = os.listdir(dir_path)
    except OSError:
        return []
    wavs = sorted(f for f in entries if f.lower().endswith(".wav"))
    result = []
    for fname in wavs[:NUM_MINI_BUTTONS]:
        path = "{}/{}".format(dir_path, fname)
        label = fname[:-4]  # strip .wav extension
        result.append((path, label))
    return result


def scan_arcade():
    """Return a list of NUM_ARCADE_BUTTONS bools: True if the WAV file exists."""
    return [_file_exists(arcade_wav_path(i)) for i in range(NUM_ARCADE_BUTTONS)]


def load_manifest():
    """Load /sounds/manifest.json and return a normalised dict.

    Manifest format::

        {
          "banks": {
            "0": {
              "name_sv": "Djur",
              "name_en": "Animals",
              "color": "#FF6B35",
              "slots": {
                "0": {"sv": "Hund", "en": "Dog"},
                "1": "Katt"
              }
            }
          }
        }

    All fields are optional. ``name`` is accepted as a language-neutral fallback.
    Slot labels can be a plain string (language-neutral) or a ``{lang: str}`` dict.

    Returns a dict with keys:
        "banks": {0: {"name": str, ...per-lang keys..., "color": (r,g,b)}, ...}
        "labels": {(bank, slot): str | dict, ...}
    """
    result = {
        "banks": {
            i: {"name": _DEFAULT_BANK_NAMES[i], "color": _DEFAULT_COLORS[i]}
            for i in range(NUM_BANKS)
        },
        "labels": {},
    }
    try:
        with open(MANIFEST_PATH) as f:
            raw = json.load(f)
    except Exception:
        return result

    banks_raw = raw.get("banks", {})
    for key, val in banks_raw.items():
        try:
            bank_idx = int(key)
        except (ValueError, TypeError):
            continue
        if not (0 <= bank_idx < NUM_BANKS):
            continue
        bank_entry = result["banks"][bank_idx]

        # Language-neutral name fallback
        if isinstance(val.get("name"), str):
            bank_entry["name"] = val["name"]
        # Per-language names: name_sv, name_en
        for lang in ("sv", "en"):
            lang_key = "name_" + lang
            if isinstance(val.get(lang_key), str):
                bank_entry[lang_key] = val[lang_key]

        # Color: "#RRGGBB"
        color = val.get("color")
        if isinstance(color, str) and color.startswith("#") and len(color) == 7:
            try:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
                bank_entry["color"] = (r, g, b)
            except ValueError:
                pass

        # Slot labels nested inside the bank entry
        slots_raw = val.get("slots", {})
        for slot_key, label in slots_raw.items():
            try:
                slot_idx = int(slot_key)
            except (ValueError, TypeError):
                continue
            if not (0 <= slot_idx < NUM_MINI_BUTTONS):
                continue
            if isinstance(label, (str, dict)):
                result["labels"][(bank_idx, slot_idx)] = label

    return result


class SoundboardState:
    """Tracks the runtime state of the soundboard.

    Pure logic — no hardware dependencies.
    """

    def __init__(self):
        self.bank = 0  # current bank index 0–3
        self.playing_slots = set()  # currently-playing mini buttons
        self.playing_arcades = set()  # currently-playing arcade buttons
        self.volume = 50  # 0–100
        self.muted = False
        self.slots_present = [False] * NUM_MINI_BUTTONS
        self._slot_paths = [
            None
        ] * NUM_MINI_BUTTONS  # path per slot (numbered or discovered)
        self._disc_labels = [
            None
        ] * NUM_MINI_BUTTONS  # filename-stem labels from discovery
        self.arcade_present = [False] * NUM_ARCADE_BUTTONS
        self.manifest = None  # loaded lazily

    def load(self):
        """Scan filesystem and load manifest. Call once on mode entry."""
        self.manifest = load_manifest()
        self._rescan()

    def set_bank(self, bank):
        """Switch to a new bank and rescan."""
        self.bank = bank & 0x3
        self.playing_slots.clear()
        self.playing_arcades.clear()
        self._rescan()

    def _rescan(self):
        numbered = scan_bank(self.bank)
        if any(numbered):
            # Numbered mode: use 0.wav–7.wav
            self.slots_present = numbered
            self._slot_paths = [
                wav_path(self.bank, i) if numbered[i] else None
                for i in range(NUM_MINI_BUTTONS)
            ]
            self._disc_labels = [None] * NUM_MINI_BUTTONS
        else:
            # Discovery mode: sort any .wav files in the directory
            found = discover_bank(self.bank)
            self.slots_present = [i < len(found) for i in range(NUM_MINI_BUTTONS)]
            self._slot_paths = [
                found[i][0] if i < len(found) else None for i in range(NUM_MINI_BUTTONS)
            ]
            self._disc_labels = [
                found[i][1] if i < len(found) else None for i in range(NUM_MINI_BUTTONS)
            ]
        self.arcade_present = scan_arcade()

    def bank_name(self):
        """Return the display name for the current bank in the active language."""
        if self.manifest:
            from bodn.i18n import get_language

            entry = self.manifest["banks"][self.bank]
            lang_key = "name_" + get_language()
            return entry.get(lang_key) or entry["name"]
        return _DEFAULT_BANK_NAMES[self.bank]

    def bank_color(self):
        """Return the RGB tuple for the current bank."""
        if self.manifest:
            return self.manifest["banks"][self.bank]["color"]
        return _DEFAULT_COLORS[self.bank]

    def slot_label(self, slot):
        """Return the display label for a mini-button slot in the active language.

        Resolution order:
          1. manifest label (language-aware)
          2. discovered filename stem (from directory scan)
          3. None → caller uses i18n fallback ("Ljud N")
        """
        if self.manifest:
            label = self.manifest["labels"].get((self.bank, slot))
            if label is not None:
                if isinstance(label, dict):
                    from bodn.i18n import get_language

                    lang = get_language()
                    return (
                        label.get(lang)
                        or label.get("sv")
                        or next(iter(label.values()), None)
                    )
                return label  # plain string — language-neutral
        # Discovery mode: use filename stem as label
        return self._disc_labels[slot]

    def adjust_volume(self, delta):
        """Adjust volume by delta detents, clamped to 0–100."""
        self.volume = max(0, min(100, self.volume + delta * VOLUME_STEP))

    def toggle_mute(self):
        self.muted = not self.muted

    def effective_volume(self):
        """Return the volume to apply to the audio engine (0 when muted)."""
        return 0 if self.muted else self.volume

    def press_slot(self, slot):
        """Handle a mini button press. Returns the WAV path to play, or None for boop."""
        if not (0 <= slot < NUM_MINI_BUTTONS):
            return None
        path = self._slot_paths[slot]
        if path:
            self.playing_slots.add(slot)
            return path
        return None

    def press_arcade(self, slot):
        """Handle an arcade button press. Returns WAV path or None for boop."""
        if not (0 <= slot < NUM_ARCADE_BUTTONS):
            return None
        if self.arcade_present[slot]:
            self.playing_arcades.add(slot)
            return arcade_wav_path(slot)
        return None

    def on_playback_done(self):
        """Call when all SFX voices have finished."""
        self.playing_slots.clear()
        self.playing_arcades.clear()
