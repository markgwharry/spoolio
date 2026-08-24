# Spoolman-compatible API

Spoolio exposes a subset of the [Spoolman](https://github.com/Donkie/Spoolman)
v1 REST API so the existing 3D-printing ecosystem — **Moonraker**,
**OctoPrint-Spoolman**, **OrcaSlicer**, and NFC scales like **FilaMan** — can
read your inventory and **auto-decrement spools as you print**, without Spoolio
having to reimplement every integration itself.

## How it works

Spoolman is single-tenant and unauthenticated. Spoolio is multi-user, so the API
is scoped by a **per-user token in the URL**:

```
https://<your-host>/spoolman/<token>/api/v1/...
```

You paste `https://<your-host>/spoolman/<token>` as the **Spoolman server URL**
in your slicer / Moonraker / OctoPrint config. Everything under that path is
scoped to your account only.

### Getting your token

Authenticated (JWT) management endpoint:

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/api/integrations/spoolman` | Current status + URL |
| `POST` | `/api/integrations/spoolman` | Enable (generate token) |
| `POST` | `/api/integrations/spoolman?rotate=true` | Rotate the token |
| `DELETE` | `/api/integrations/spoolman` | Disable the integration |

Response:
```json
{
  "enabled": true,
  "token": "abc123…",
  "spoolman_url": "https://your-host/spoolman/abc123…",
  "hint": "Paste spoolman_url as the Spoolman server URL in Moonraker / OctoPrint-Spoolman / your slicer."
}
```

> Rotating or disabling the token immediately revokes the old URL.

### Example: Moonraker

```ini
[spoolman]
server: https://your-host/spoolman/<token>
sync_rate: 5
```

## Implemented endpoints

All under `/spoolman/<token>/api/v1`:

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/info` | Advertises a Spoolman version + `db_type` |
| `GET` | `/health` | `{"status":"healthy"}` |
| `GET` | `/vendor`, `/vendor/{id}` | Mapped from Manufacturers |
| `GET` | `/filament`, `/filament/{id}` | Synthetic, one per spool |
| `GET` | `/spool`, `/spool/{id}` | `?allow_archived=true` to include empty/inactive |
| `PUT` | `/spool/{id}/use` | Report consumption: body has **exactly one** of `use_weight` (g) or `use_length` (mm) |

`PUT /spool/{id}/use` decrements the spool's remaining weight, marks it empty at
zero, sets `last_used`, and records a Spoolio usage-history entry so your
analytics stay consistent.

## Mapping & limitations

| Spoolman | Spoolio |
|----------|---------|
| Vendor | Manufacturer |
| Filament | Synthetic, derived per spool (material + colour + manufacturer) |
| Spool | FilamentSpool |

- Spoolio doesn't store **density** or **diameter**, so the API defaults to PLA
  values (1.24 g/cm³, 1.75 mm). Weight↔length conversions (and therefore
  `use_length`) use those defaults. Override the advertised version with
  `SPOOLMAN_COMPAT_VERSION` if a client is version-gated.
- The API is currently **read + use** only. Creating/editing spools from the
  Spoolman side (`POST`/`PATCH`/`DELETE`) is not implemented yet — manage
  inventory in Spoolio itself.

## Deployment note

Fresh and existing installs get the `spoolman_token` column through Alembic:

```bash
flask --app app:create_app db upgrade
```

See `docs/deployment/DATABASE_MIGRATIONS.md` for backup and rehearsal steps.
