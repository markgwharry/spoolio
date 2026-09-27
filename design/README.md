Filamentarium is a filament tracker that treats a 3D-printing filament collection as a small library. Spools are catalogued, shelved, lent to printers and returned, and the interface borrows the materials of a reading room: warm paper, bookbinding colours, index cards, date stamps and book spines. It should feel like a well-kept e-book manager or a library catalogue, never like a dark dashboard with orange accents.

## Voice and vocabulary

Write in British English, sentence case, plain and short. No exclamation marks, no emoji, no superlatives. Name things by what the person recognises, using the library vocabulary consistently:

| Say | Means | Never |
| --- | --- | --- |
| Accession a spool | Add a new spool to the catalogue | Create item, add entry |
| No. 0142 | A spool's accession number, always four digits | ID, #142 |
| Shelf, dry box | A storage location | Bin, location ID |
| Lend / Return | Load a spool onto a printer / unload it | Assign, detach |
| On loan, circulation | Spools currently on printers | Active, in use (except the one slot actually printing) |
| Ledger | The usage log per print | History, events |
| Acquisitions | The reorder list | Shopping cart |
| Archive, withdraw | Empty or retired spools | Delete |
| Bookplate | The printed spool label | Sticker, tag |
| Marginalia | The person's own notes on a spool | Comments |
| Reading room | The humidity panel | Sensors |
| Due for drying | Too long open to the air | Moisture alert |

Units: `612 g` (space before g), `1,000 g`, `190–230 °C` with an en dash, `18% RH`, dates as `24 Sep 2026` or stamped `24 SEP`. Accession numbers always read `No. 0142`.

## Colour

- Use `paper` for every page ground, `paper-sunk` for the sidebar, `paper-raised` for cards and inputs, `vellum` for a card inside a card, and `case` plus `plank` only for shelves.
- Set text in `ink`, secondary text in `ink-muted`. Both hold 4.5:1 on every paper token and on `case`, in both themes.
- `sepia` is the only accent. Spend it on the primary action (once per view), links, eyebrows, accession numbers and the remaining-weight meter. Text on a sepia fill is `on-sepia`, never literal white.
- `oxblood` means attention: low stock, due for drying, destructive actions, date stamps, and the top rule of an index card. Do not use it decoratively anywhere else.
- `ledger-blue` means a good state: on the shelf, dried, returned. It is deliberately blue, not green, so good and bad never depend on red versus green. Every status also carries a word or a sticker letter.
- Show filament colours only on `swatch-ground` with a `swatch-edge` hairline (the `Swatch`, `SpoolDrawing` and `SpoolSpine` components do this). Never place a filament colour directly on warm paper, because the paper shifts how the colour reads.
- Bookplates print in `print-ink` on `print-paper` whatever the theme.

## Themes

Two themes: **Daylight** (default) and **Reading lamp**. Reading lamp is deep ink-brown with brass and cream, never pure black. The same tokens drive both; never hard-code a hex that only works in one.

## Typography

- Literata (`serif`) names things: page titles in `display`, printer and section names in `heading`, card headings and shelf names in `subheading`, spine labels in `spine`, notes in `marginalia`.
- IBM Plex Sans (`sans`) runs the interface: `body`, `control`, `small`, and uppercase `eyebrow` and `label`.
- IBM Plex Mono (`mono`) sets anything counted, dated or catalogued: `accession`, `figure`, `stamp`. Weights and temperatures always go in mono so columns line up.
- Self-host all three (the app installs them from Fontsource); never load them from a third-party CDN. The design previews use Google Fonts only for convenience:
  `https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap`
- Avoid Inter, Roboto and Arial.

## Layout and shape

- Desktop screens are a `sidebar-width` sidebar plus a content column padded `space-10` top and `space-12` sides. Sections sit `space-6` apart.
- Corners are small: `radius-md` for controls, `radius-lg` for cards, `radius-xs` for spine tops and stamps. Only pills, chips, stickers and swatches use `radius-pill`.
- Borders do most of the separating. Use `shadow-card` only for the index card and anything lifted off the page, and `shadow-case` only inside a shelf.
- Every interactive control is at least `control-height` tall.
- Keyboard focus is `focus-ring`: a paper-coloured gap, then solid sepia.

## Signature patterns

- **Shelves.** The main inventory view is a set of shelves, each a `Shelf` of `SpoolSpine`s. A spine's colour is the filament's colour, its label is the colour name, and a sticker replaces the accession number when it is low (`L`, oxblood) or due for drying (`D`, ink).
- **The index card.** A spool's record is an `IndexCard`: an oxblood top rule, the accession number, the colour name as the title, then ruled fields.
- **Circulation.** Printers are borrowers. Each AMS slot is a `SlotCard`; returning a spool records a `DateStamp` line in its circulation record.
- **The spool drawing.** `SpoolDrawing` shows the remaining filament as the wound radius against a dashed full-spool ring.

## Iconography

No icon set has been chosen yet. For now, draw icons as inline SVG strokes: 24px viewBox, 1.8px stroke, round caps and joins, `currentColor`, shown at 18px. Never use emoji. There is no logo: set the name in `wordmark`.

## Motion

Keep it minimal. Spines may lift 4px on hover; nothing else moves. Respect `prefers-reduced-motion`.

## Using the components

Components are in `components/bundle.js` as `window.Filamentarium` and expect React 18 on the page, with `components/bundle.css` after the tokens stylesheet.
