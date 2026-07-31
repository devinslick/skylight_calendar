# Skylight for Home Assistant

Integrate your [Skylight](https://www.ourskylight.com/) into Home Assistant — calendar events, chores, meals, shopping/to-do lists, and reward stars.

> **v2.1.0.** Skylight uses OAuth2. Home Assistant now handles the whole handshake — click a link, sign in on Skylight's own page, paste the authorization code back into Home Assistant. No browser DevTools, no manually copying tokens. HA rotates the refresh token automatically forever after that.

---

## Features

| HA Platform | What you get |
|---|---|
| `calendar` | One aggregate calendar per frame **plus** one calendar entity per source calendar (Google, Proton, iCloud, native Skylight events). |
| `todo` | One HA todo list entity per Skylight list — **Grocery List**, **To-Do List**, and any other list you create on the frame — plus one **chore queue** per family member. Create / complete / rename / delete items round-trips to the frame in real time. |
| `sensor` | `chores_today`, `meals_today`, one **per-member chores_today** sensor (with `by_status` breakdown attributes), one **per-meal-slot** sensor (Breakfast / Lunch / Dinner / Snack), and one **reward-star balance** sensor per family profile. |
| `image` | `latest_photo` — the most recent photo uploaded to the frame. |
| `switch` | `sleep_mode` — toggle the frame's sleep mode. |
| `number` | `brightness` (0–255) and `slideshow_speed`. |

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

## Authentication

Skylight's mobile app and web UI both use OAuth2 with rotating refresh tokens. The refresh handshake requires a device fingerprint, so the integration cannot log you in from HA with just an email/password — but the config flow now walks you through a **real OAuth authorization_code + PKCE** handshake with zero DevTools.

### One-time setup

1. Settings → Devices & Services → **Add Integration** → **Skylight Calendar**.
2. Home Assistant shows a **Sign in to Skylight** link. Click it — it opens Skylight's sign-in page in a new browser tab.
3. Sign in with your Skylight email and password (the same credentials you use in the Skylight mobile app).
4. Once you're signed in, Skylight redirects you to a `https://ourskylight.com/welcome?code=...` page. **Look at the address bar** — the important part is the `code=...` value at the end of the URL.
5. Copy the value of `code` (or paste the whole URL — Home Assistant extracts the code either way) back into the HA config flow and submit.
6. Home Assistant exchanges the code for an access token + refresh token, enumerates your Skylight frames, and (if you have more than one) asks which frame to set up. From then on HA rotates the refresh token automatically on every 401 — you never need to sign in again unless you sign out of Skylight everywhere or the refresh grant is invalidated server-side.

> **Codes expire in about 30 seconds.** If HA shows *"That code was rejected — codes expire in about 30 seconds"*, just click the sign-in link again to get a fresh one and paste that instead.

### If auth ever breaks later

Home Assistant will surface a **Reauthenticate** button on the integration card and walk you through the same one-step OAuth flow again. You do not need to remove and re-add the integration.

### Adding a second frame

If you have multiple Skylight frames on the same account, click **Add Integration** → **Skylight Calendar** a second time. The flow will list only the frames you haven't already set up.

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
| `invalid_auth` on config flow | The authorization code expired (they're valid for ~30 seconds). Click the sign-in link again and paste the fresh code. |
| `invalid_code` on config flow | The pasted value doesn't look like a Skylight code. Copy the value of `code=` from the browser's address bar (or the whole URL — either works). |
| Calendar entity has no events | The API returns `[]` when `date_max == date_min`; the integration handles this by fetching a 60-day forward window. If you still see nothing, check that you have events on your frame in that window. |
| Todo entities missing after adding a new list on the frame | New lists show up on the next 2-minute refresh — reload the integration to force it immediately. |
| Star sensors missing for one profile | The profile is only shown if `linked_to_profile=true` on its category. Ensure the profile is fully set up on the frame. |

---

## What changed in v2.1.0

- **Auth UX**: replaced the browser-DevTools token-paste flow with a real OAuth2 `authorization_code` + PKCE handshake. You click a link, sign in on Skylight's own hosted page, and paste back a single short code from the address bar. No DevTools, no digging through Network tab.
- **Reauth**: HA's built-in Reauthenticate button now works — no more removing and re-adding the integration.
- **Reconfigure**: use the ⋮ menu on the integration card to re-run the OAuth flow at any time.
- **Multi-frame**: the config flow filters out frames you've already added, so adding a second frame is just "Add Integration" a second time.
- **Per-source calendars**: instead of one merged calendar per frame, you now get one aggregate calendar plus one entity per source calendar (e.g. Google, Proton, iCloud, native Skylight).
- **Per-member chore queues**: one `todo.<frame>_<person>_chores` entity per family member, with `complete_chore` write-back.
- **Per-meal-slot sensors**: `sensor.<frame>_breakfast_today`, `_lunch_today`, `_dinner_today`, `_snack_today` — always present, `none` when empty, with attributes carrying full detail.
- **New platforms**: `image.<frame>_latest_photo`, `switch.<frame>_sleep_mode`, `number.<frame>_brightness` (0–255), `number.<frame>_slideshow_speed`.
- **Attributes**: chores sensors expose a `by_status` breakdown (pending / done / skipped counts + item lists).

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
