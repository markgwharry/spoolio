# SlotCard

One printer slot, such as an AMS bay or the external holder, showing the spool on loan to it or an empty slot waiting for one.

- Provide `slot` ("AMS 1", "External") and a `spool` object: `no`, `name`, `material`, `hex`, `since`, `used` and `left` in grams. Omit `spool` for a free slot.
- `inUse` marks the slot feeding the current print with a sepia border and an "In use" label. Only one slot at a time.
- `onReturn` and `onLend` wire the buttons.
- Lay a printer's slots out in one row, equal widths, inside the printer's card.
