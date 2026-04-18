# NFC Integration

Bodn supports NFC-tagged cards and stickers via a PN532 reader connected
over I2C. Cards carry self-describing data and are used as input for
classification games, storytelling, vocabulary, and free exploration.

See `docs/science/nfc_tangible_learning.md` for the developmental science
behind this feature.

## Tag Data Format

Tags use **NDEF URI Records** — phones scanning them open a URL, while the
device parses the URL path to extract mode and card data.

```
https://bodn.thias.se/1/sortera/cat_red
                       │ │       └─ card ID (optional, unique within the set)
                       │ └─ mode (matches card set template filename)
                       └─ schema version
```

### Special tags

| URL | Purpose |
|-----|---------|
| `https://bodn.thias.se/1/admin/unlock` | Admin fob — opens settings without web UI |
| `https://bodn.thias.se/1/simon` | Launcher tag — starts Simon (no card ID) |
| `https://bodn.thias.se/1/launcher/simon` | Alternative launcher format |

### NDEF encoding

The tag stores an NDEF URI Record with prefix code `0x04` (`https://`):

```
Byte 0:     0x04 (NDEF URI prefix for "https://")
Bytes 1+:   "bodn.thias.se/1/sortera/cat_red"
```

Total: ~33 bytes. NTAG213 (144 bytes usable) has plenty of room.

NDEF URI prefix compression stores `https://` as a single byte, making
the tag data shorter than a full URL string. Phones reconstruct the full
URL automatically when scanning.

### Backward compatibility

Tags written with the old NDEF Text Record format (`\x02enBODN:1:…`) are
still readable. The device detects the format by the first payload byte:
`0x04` = URI record (new), `0x02` = Text record (legacy).

## Card Set Templates

Card sets are JSON files stored on the SD card at `/sd/nfc/{mode}.json`.
They define the cards in a deck, their properties, and sorting dimensions.

```json
{
  "mode": "sortera",
  "version": 1,
  "dimensions": ["category", "colour"],
  "cards": [
    {
      "id": "cat_red",
      "category": "animal",
      "colour": "red",
      "label_sv": "katt",
      "label_en": "cat",
      "icon": "1F431"
    }
  ]
}
```

### Fields

| Field | Description |
|-------|-------------|
| `mode` | Mode identifier, matches the filename |
| `version` | Schema version (currently 1) |
| `dimensions` | List of sortable property names |
| `cards[].id` | Unique card identifier (written to NFC tag) |
| `cards[].label_sv` | Swedish display name |
| `cards[].label_en` | English display name |
| `cards[].icon` | OpenMoji Unicode codepoint (hex string) |
| `cards[].sound` | *(optional)* Stem name for a Blippa free-play sound, resolved as `/sounds/blippa/<stem>.wav` (SD first, flash fallback). Missing or unresolved → procedural default blip. |
| `cards[].<dim>` | Value for each dimension (e.g., `category`, `colour`) |

### Adding a new card set

1. Create `assets/nfc/{mode}.json` following the schema above
2. Run `uv run python tools/sd-sync.py` to copy it to the SD card
3. The card set will appear in the settings NFC screen and web UI
4. If the cards should work in Blippa free-play mode, append the new mode
   name to `_SUBSCRIBED` in `firmware/bodn/ui/blippa.py`.  Launcher tags
   are handled globally — do not subscribe to `"launcher"`.

## UID Cache

After the first read of a tag, the device caches the UID→card mapping at
`/data/nfc_cache.json` on flash. This speeds up subsequent reads from
~200 ms (full data read) to ~50 ms (UID only).

The cache is **not the source of truth** — it's rebuilt automatically from
tag data on cache miss. Deleting the cache file has no impact beyond a
brief speed penalty on first scans.

## Card Face Generation

A host-side tool generates printable PDF sheets from card set templates:

```bash
# One-time: clone OpenMoji SVGs
git clone --depth 1 https://github.com/hfg-gmuend/openmoji.git ~/openmoji

# Generate all card sets
uv run python tools/generate_cards.py --openmoji ~/openmoji

# Specific set only
uv run python tools/generate_cards.py --set sortera --openmoji ~/openmoji

# Preview without generating
uv run python tools/generate_cards.py --dry-run
```

Output: `build/cards/{mode}_cards.pdf` — A4 pages with credit-card-sized
(85×54 mm) card faces in a 2×4 grid.

### Card production workflow

1. Generate the PDF: `uv run python tools/generate_cards.py --openmoji ~/openmoji`
2. Print on cardstock or thick paper
3. Attach an NFC sticker (NTAG213) to the back of each card
4. Laminate for durability
5. Provision tags via the on-device screen or web UI (requires PN532, issue #121)

## Hardware (Issue #121)

The PN532 NFC reader connects via I2C:

| PN532 Pin | ESP32-S3 | Notes |
|-----------|----------|-------|
| VCC | 3.3V | Check board regulator |
| GND | GND | |
| SDA | Shared I2C bus | With MCP23017s |
| SCL | Shared I2C bus | |
| IRQ | Free GPIO (optional) | Power-efficient detection |

I2C address: **0x24** (no conflict with MCP23017 at 0x21/0x23 or PCA9685 at 0x40).

## Module API

```python
from bodn.nfc import (
    parse_tag_data,    # bytes or str → {prefix, version, mode, id} or None
    encode_tag_data,   # (mode, card_id) → NDEF bytes
    load_card_set,     # mode → dict or None
    lookup_card,       # (mode, card_id) → card dict or None
    list_card_sets,    # () → [mode_name, ...]
    UIDCache,          # .lookup(uid), .store(uid, mode, id), .clear()
    NFCReader,         # .scan() → (uid, data), .write(data), .available()
)
```

## Web API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/nfc/sets` | GET | List available card sets |
| `/api/nfc/set/{mode}` | GET | Full card set data |
| `/api/nfc/cache` | GET | UID cache contents |
