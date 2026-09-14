# API Coverage — Phase 2 (Safe Geospatial Discovery)

> The deterministic API-coverage detector returned `detected: true` on a single signal: the phrase
> "the API Phase 3 consumes in-process" in `02-CONTEXT.md` D-29. That phrase names an **internal
> in-process Python object** (`ImportManifest`), not an external API, SDK, or service. Per the
> capability's rule for a true-but-not-really detection, a capability matrix is not fabricated here.

No external API integration: Phase 2 reads a local archive with the Python standard library's
`zipfile`, profiles it in-process with `pyogrio`/`pyproj`, and shells out read-only to the locally
installed GDAL `ogrinfo` CLI — it opens no network connection and no database connection.

## Why no matrix applies

| Boundary | Kind | In this phase |
|---|---|---|
| `artifacts/Order_{id}.zip` | Local filesystem read | Re-hashed (D-28) and unpacked; no remote endpoint. |
| `runs/{order_id}/{utc_timestamp}/` | Local filesystem write | The extraction destination; no remote endpoint. |
| `pyogrio` / `pyproj` | In-process Python libraries | Imported and called directly; no service, no versioned wire contract. |
| `ogrinfo -json -al -so` | Local read-only subprocess | Supplies the field width/precision/nullability `pyogrio.read_info()` does not expose. |
| `ImportManifest` / `manifest.json` | In-process object + local file | The Phase 2 → Phase 3 handoff (D-29). Internal, not a published API. |
| Microsoft Graph / HTTPS artifact host | External APIs | **Phase 1 only.** Phase 2 never contacts them. |
| PostGIS / PostgreSQL | External service | **Phase 3 and 4 only.** D-23 is explicit that Phase 2 never contacts the database. |

## Related

- Phase 1's real capability matrix lives at
  `.planning/phases/01-trusted-graph-acquisition/COVERAGE.md` — that phase does integrate two
  external APIs (Microsoft Graph and the artifact HTTPS host) and carries a full decision matrix.

---
*Declared: 2026-09-14 during Phase 2 planning*
