---
name: add-nfc-card-set
description: Add a new NFC card set (e.g. fruit, flowers, clothing) or a new card to an existing set. Use when expanding Sortera/Räkna card collections, adding launcher tags, or introducing a new NFC-driven mode. Covers the JSON schema, OpenMoji icons, printable PDF generation, SD sync, web mirror, and on-device provisioning.
---

# Add an NFC card set

Card sets are the unit of content for NFC-driven modes (Sortera, Räkna,
launcher). Each set is a single JSON file that drives three downstream
artefacts — the firmware runtime, a printable PDF, and the web landing page
at `bodn.thias.se`. Keep the JSON authoritative; everything else regenerates
from it.

## The source of truth

`assets/nfc/{mode}.json` — one file per set.

```json
{
  "mode": "sortera",
  "version": 1,
  "dimensions": ["animal", "vehicle", "colour"],
  "cards": [
    {"id": "cat_red", "category": "animal", "animal": "cat",
     "colour": "red", "label_sv": "katt", "label_en": "cat",
     "icon": "1F431"}
  ]
}
```

- `mode` matches the filename (used in the NDEF URL path).
- `dimensions` are the sortable attributes — each card must carry a value
  for every listed dimension.
- `id` is unique within the set; used both in the URL
  (`https://bodn.thias.se/1/sortera/cat_red`) and as the dict key on the
  device.
- `icon` is an OpenMoji Unicode codepoint (hex, uppercase, no prefix). The
  card generator looks up `~/openmoji/color/svg/{icon}.svg`.
- `label_sv` / `label_en` live **inside the card JSON**, not in
  `firmware/bodn/lang/`. Card-set text is not routed through `i18n.t()`.

Special sets:

| File | Purpose |
|---|---|
| `launcher.json` | Tags that start a game mode (no card id in URL after mode) |
| `sortera.json` | Classification cards with `category` + other dimensions |
| `rakna.json` | Counting/math cards |

## Checklist

1. **Create or edit the JSON** in `assets/nfc/{mode}.json`. Validate every
   card carries the full set of `dimensions` keys plus `id`, `label_sv`,
   `label_en`, `icon`.
2. **Generate printable PDFs** (A4 sheets, 48×80 mm card faces):
   ```bash
   uv run python tools/generate_cards.py --set {mode}
   uv run python tools/generate_cards.py --dry-run            # preview only
   ```
   Requires OpenMoji SVGs at `~/openmoji` (or `$OPENMOJI_DIR`). Output lands
   in `build/cards/{mode}.pdf`.
3. **Sync to SD card** — `tools/sd-sync.py` already maps `assets/nfc/` to
   `/sd/nfc/`, so a normal sync carries the change:
   ```bash
   uv run python tools/sd-sync.py /Volumes/BODN_SD
   ```
4. **Program the physical tags** on the device:
   - Home → Settings → NFC card set viewer.
   - Pick the set, scroll to a card, tap a blank tag to write its NDEF URL
     record. See `firmware/bodn/ui/nfc_provision.py`.
5. **Rebuild the web container** if the set should appear on
   `bodn.thias.se`:
   ```bash
   cd web && docker compose up --build
   ```
   `web/Dockerfile` bakes `assets/nfc/` into the image at build time, so
   fresh JSONs need a rebuild, not a restart.

## NDEF URL scheme

Tags store an NDEF URI Record with prefix `0x04` (`https://`). The device
parses the URL path:

```
https://bodn.thias.se/1/sortera/cat_red
                       │ │       └─ card id (optional)
                       │ └─ mode (matches filename)
                       └─ schema version
```

See `docs/nfc.md` for the full format, legacy Text Record fallback, and
special admin/launcher URLs.

## Firmware integration

```python
from bodn.nfc import load_card_set, lookup_card, list_card_sets

cs = load_card_set("sortera")      # SD first, flash fallback; None on error
card = lookup_card("sortera", "cat_red")
for mode in list_card_sets():      # scans /sd/nfc/ then /nfc/
    ...
```

If a mode filters to only programmed tags, use `UIDCache()` + the
`_filter_by_cache()` pattern in `firmware/bodn/ui/sortera.py:89` — copy it,
don't reinvent.

## Related follow-ups

- **New game mode driven by the set** → see the `add-game-mode` skill for
  the developmental-science docs update.
- **Spoken card labels** → allowlist the keys and run the `tts-pipeline`
  skill.
- **New OpenMoji glyph on the home screen** → `tools/convert_icons.py`
  regenerates BDF sprites (run automatically by `sd-sync.py`).

## Invariants

- JSON is authoritative. Never add card data in firmware code paths —
  always via `assets/nfc/*.json`.
- `id` must be stable once printed. Renaming breaks already-written tags.
- OpenMoji is CC-BY-SA; keep attribution intact. Do not substitute a
  different emoji set without checking the licence.
- The web mirror is public. Do not put anything in card labels you would
  not want on the open internet.
