# Button

Secondary is the default; use **primary** at most once per view, for the thing the screen is for ("Lend to a printer", "Accession a spool", "Scan a spool to lend").

- `variant`: `primary` (sepia fill, `on-sepia` label), `secondary` (paper-raised with a `control-edge` border), `quiet` (sepia text, for small in-card actions like "Add a note"), `danger` (oxblood underlined text, only for withdraw and archive).
- `size="lg"` (48px) for the main action on a record page; otherwise 44px.
- `icon`: an inline stroke SVG, 18px, `currentColor`, placed before the label.
- Labels are verb first, sentence case, in the library vocabulary: Lend, Return, Accession, Withdraw. Never "Submit" or "OK".
- An icon-only button needs an `aria-label`.
