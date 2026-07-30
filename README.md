# Skylight Calendar for Home Assistant

Integrate your [Skylight Frame](https://www.ourskylight.com/) into Home Assistant — calendar events, chores, meals, shopping/to-do lists, and reward stars.

> **v2.0.0 — breaking change.** Skylight migrated their API to OAuth2. The legacy username / password login no longer works. You now capture your tokens once from your browser's DevTools and paste them into the config flow. Home Assistant then rotates the refresh token automatically forever.

---

## Features

| HA Platform | What you get |
|---|---|
| `calendar` | One HA calendar entity per frame, showing all events (Google-synced + native Skylight events). |
| `todo` | One HA todo list entity per Skylight list — **Grocery List**, **To-Do List**, and any other list you create on the frame. Create / complete / rename / delete items round-trip to the frame. |
| `sensor.<frame> chores_today` | Count of chores due today, with full chore list in attributes. |
| `sensor.<frame> meals_today` | Count of meals planned for today, with details in attributes. |
| `sensor.<frame> <person>_stars` | One reward-star balance sensor per family profile (Devin, Tabi, Logan, …). |

Frame device is registered in HA's device registry, so every entity is grouped under its frame.

Photo upload is **not yet supported** — planned as a future stretch goal.

---

## Installation (HACS)

1. In HACS → Integrations → three dots → **Custom repositories**, add:
   `https://github.com/devinslick/skylight_calendar` — Category: **Integration**
2. Search for **Skylight Calendar** and click **Download**.
3. Restart Home Assistant.
4. Settings → Devices & Services → **Add Integration** → **Skylight Calendar**.

Or use this button once the repo is in HACS's default index:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=devinslick&repository=skylight_calendar&category=integration)

---

## Manual installation

1. Copy `custom_components/skylight_calendar/` into your Home Assistant config directory:
   `config/custom_components/skylight_calendar/`
2. Restart Home Assistant.
3. Settings → Devices & Services → **Add Integration** → **Skylight Calendar**.

---

## Authentication — capturing your tokens

Skylight's mobile app / web UI both use OAuth2 with rotating refresh tokens. The refresh handshake requires a browser-signed device fingerprint, so the integration cannot log you in from HA directly — but it *can* keep a captured token pair alive indefinitely.

### One-time setup

1. In **Google Chrome** (or any Chromium browser with DevTools), open **[https://app.ourskylight.com](https://app.ourskylight.com)** and log in normally.
2. Open **DevTools** (⌘⌥I / Ctrl+Shift+I) → **Network** tab.
3. In the filter box, type `oauth/token`.
4. Click **Sign in** if you're not already logged in. You should see one or more `POST` requests to `https://app.ourskylight.com/oauth/token`.
5. Click the **most recent successful** `oauth/token` request. Two tabs matter:

   **Response tab** (JSON body):
   ```json
   {
     "access_token": "eyJhbGciOi...LONG_STRING",
     "refresh_token": "def502...ANOTHER_LONG_STRING",
     "token_type": "Bearer",
     "expires_in": 7200,
     ...
   }
   ```
   Copy the `access_token` and `refresh_token` values.

   **Payload tab** → **Form Data** view (the request body sent to the server):
   ```
   grant_type: authorization_code
   ...
   skylight_api_client_device_fingerprint: 91c3aa2f-e39d-4b41-...
   ```
   Copy the `skylight_api_client_device_fingerprint` value.

6. In Home Assistant, the integration's config flow will ask for those three values. Paste them and submit.
7. HA immediately does a refresh-token exchange to verify the pair and store the freshly-rotated tokens. From then on, HA rotates them automatically on every 401 — you never need to touch DevTools again unless you sign out of Skylight in your browser or the refresh grant is invalidated server-side.

### If auth ever breaks later

- Symptom: HA logs `Skylight auth failed after refresh` or `Refresh token was rejected`.
- Fix: **Remove** the integration in Settings → Devices & Services, redo the DevTools capture above, and **Add Integration** again.

---

## Multi-frame support

The current release supports **one frame per config entry**. If your Skylight account owns multiple frames, the config flow will let you pick which one to add. To add a second frame, add the integration a second time with the same tokens — it will offer the other frames.

---

## Troubleshooting

Enable debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.skylight_calendar: debug
```

Then Settings → System → **Logs** and look for `custom_components.skylight_calendar`.

Common issues:

| Symptom | Cause / fix |
|---|---|
| `invalid_auth` on config flow | Refresh token was pasted with surrounding whitespace or is stale. Re-copy from DevTools. |
| Calendar entity has no events | The API returns `[]` when `date_max == date_min`; the integration handles this by fetching a 60-day forward window. If you still see nothing, check that you have events on your frame in that window. |
| Todo entities missing after adding a new list on the frame | New lists show up on the next 2-minute refresh — reload the integration to force it immediately. |
| Star sensors missing for one profile | The profile is only shown if `linked_to_profile=true` on its category. Ensure the profile is fully set up on the frame. |

---

## What changed in v2.0.0

- **Auth**: rewritten to OAuth2 Bearer + `Skylight-Api-Version: 2026-05-01` header + automatic refresh cascade with rotation persisted to the config entry.
- **New platforms**: `todo` (all Skylight lists), `sensor` (chores today, meals today, per-profile reward stars).
- **Calendar**: now backed by a `DataUpdateCoordinator`, fetches a rolling ±14/+60 day window every 5 minutes; `event` property returns the currently active event, or the next upcoming one if none is active.
- **Device registry**: all entities are grouped under one HA device per frame.
- **Removed**: username / password login (Skylight's `/api/sessions` endpoint no longer issues usable tokens for the current API version).

---

## Credits

Originally forked from [MegaTheLEGEND/skylight_calendar](https://github.com/MegaTheLEGEND/skylight_calendar). OAuth2 rewrite + platform expansion by [@devinslick](https://github.com/devinslick).

## License

MIT — see [LICENSE](LICENSE).
