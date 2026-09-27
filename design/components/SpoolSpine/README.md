# SpoolSpine

A spool shown as a book spine: the filament colour, the colour name set vertically, the accession number at the top and the grams at the foot.

- Provide `no`, `name`, `hex` and `grams`; `material` goes into the accessible name. The label colour (white or ink) is picked automatically; `fg` overrides it.
- `flag` (`low` or `dry`) replaces the accession number with a `Sticker`.
- Vary `width` (40–54px) and `height` (132–158px) a little across a shelf so it looks like real books. Keep names short enough to fit: "Clear Orange", not "Translucent Orange".
- Give `href` to make the spine a link to the spool's record.
