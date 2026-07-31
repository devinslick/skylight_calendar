# Skylight for Home Assistant

Full Home Assistant integration for [Skylight Frames](https://www.ourskylight.com/) — calendar events, chores, meals, shopping/to-do lists, task-box templates, and reward stars, all exposed as native HA entities.

> ⚠️ **v2.0.0 is a breaking change.** Skylight migrated their API to OAuth2. The legacy username / password login no longer works. You now capture your tokens once from your browser's DevTools and paste them into the config flow. Home Assistant then rotates the refresh token automatically — you never touch DevTools again unless the grant is revoked.

---

## What you get

| Entity | Notes |
|---|---|
| `calendar.<frame>_calendar` | One HA calendar per frame with all events (Google-synced + native Skylight). Standard `calendar.get_events` service works. |
| `todo.<list_name>` | One HA todo entity **per Skylight list** — Grocery, To-Do, and any custom list you create on the frame. Full create / rename / complete / delete round-trip. |
| `sensor.<frame>_chores_today` | Count of today's chores. Full per-chore details in `extra_state_attributes.chores[]`. |
| `sensor.<frame>_meals_today` | Count of today's meal sittings. Category (Breakfast/Lunch/Dinner), recipe title, description, notes, and RRULE all in `extra_state_attributes.meals[]`. |
| `sensor.<frame>_task_box` | Count of reusable chore-template items (the "Task Box" on the frame). Full list in `extra_state_attributes.items[]`. |
| `sensor.<person>_stars` | One reward-star balance sensor per family profile (Devin, Tabi, Logan, …). Lifetime earned in attributes. |

All entities are grouped under one HA device per frame.

**Not yet supported (planned):** photo upload, chore/meal write operations, task-box → chore instantiation.

---

## Installation

### HACS (recommended)

1. HACS → Integrations → three-dot menu → **Custom repositories**.
2. Repository: `https://github.com/devinslick/skylight_hass` — Category: **Integration**.

   [![Open your Home Assistant instance and open a repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=devinslick&repository=skylight_hass&category=integration)
3. Search for **Skylight** and click **Download**. If you want the beta channel, toggle **Show beta versions** and pick the newest `v2.0.0-beta.N` tag.
4. Restart Home Assistant.
5. Settings → Devices & Services → **Add Integration** → **Skylight**.

### Manual

Copy `custom_components/skylight/` into `config/custom_components/skylight/` and restart HA.

---

## Authentication — capturing your tokens

Skylight's mobile app / web UI use OAuth2 with rotating refresh tokens. The refresh handshake requires a browser-signed device fingerprint, so the integration cannot log you in from HA directly — but it *can* keep a captured token pair alive indefinitely.

### One-time setup

1. In **Google Chrome** (or any Chromium browser with DevTools), open **https://app.ourskylight.com** and log in normally.
2. Open **DevTools** (⌘⌥I / Ctrl+Shift+I) → **Network** tab.
3. In the filter box, type `oauth/token`.
4. If you don't see any requests, click **Sign in** or reload the page. You'll see one or more `POST` requests to `https://app.ourskylight.com/oauth/token`.
5. Click the **most recent successful** `oauth/token` request. Two views matter:

   **Response tab** (JSON body):
   ```json
   {
     "access_token": "eyJhbGciOi...LONG_STRING",
     "refresh_token": "def502...ANOTHER_LONG_STRING",
     "token_type": "Bearer",
     "expires_in": 7200
   }
   ```
   Copy the `access_token` and `refresh_token` values.

   **Payload tab → Form Data** (the request body sent to the server):
   ```
   grant_type: authorization_code
   ...
   skylight_api_client_device_fingerprint: 91c3aa2f-e39d-4b41-...
   ```
   Copy the `skylight_api_client_device_fingerprint` value.

6. In Home Assistant, paste those three values into the config flow and submit.
7. HA immediately does a refresh-token exchange to verify the pair and store freshly-rotated tokens. From then on HA rotates them automatically on every 401 — no more DevTools needed.

### If auth ever breaks later

- Symptom: HA logs `Skylight auth failed after refresh` or `Refresh token was rejected`.
- Fix: **Remove** the integration in Settings → Devices & Services, redo the DevTools capture above, and **Add Integration** again.

---

## Reading item details in Lovelace

Every sensor stashes the full record for each item in `extra_state_attributes`. Use a **Markdown card** with Jinja templates to render whatever detail you want. The same pattern works for chores, meals, task-box items, todo lists, and calendar events.

### Today's chores

```yaml
type: markdown
title: Today's chores
content: |
  {% for c in state_attr('sensor.slickfam_chores_today', 'chores') %}
  ### {{ c.emoji or '📋' }} {{ c.summary }}
  {% if c.description %}> {{ c.description }}{% endif %}
  - **Assigned to:** {{ c.assignee or 'Anyone' }}
  - **Reward:** ⭐ {{ c.reward_points or 0 }}
  - **Status:** {{ c.status }}{% if c.start_time %} · Due at {{ c.start_time }}{% endif %}
  {% if c.recurrence_rrule %}- **Repeats:** {{ c.recurrence_rrule }}{% endif %}

  {% endfor %}
```

### Today's meals

```yaml
type: markdown
title: Today's meals
content: |
  {% for m in state_attr('sensor.slickfam_meals_today', 'meals') %}
  ### {{ m.category or '🍽️' }} — {{ m.summary }}
  {% if m.recipe_title and m.recipe_title != m.summary %}*Recipe:* **{{ m.recipe_title }}**{% endif %}
  {% if m.description %}{{ m.description }}{% endif %}
  {% if m.note %}> Note: {{ m.note }}{% endif %}

  {% endfor %}
```

### Task-box items (reusable chore templates)

```yaml
type: markdown
title: Task Box
content: |
  {% for t in state_attr('sensor.slickfam_task_box', 'items') %}
  - {{ t.emoji or '☐' }} **{{ t.summary }}**{% if t.reward_points %} · ⭐ {{ t.reward_points }}{% endif %}{% if t.routine %} · _routine_{% endif %}
  {% endfor %}
```

### Reading a to-do list with details

The `todo` platform is best consumed via the native **Todo list** card, which supports adding, checking, and deleting items:

```yaml
type: todo-list
entity: todo.grocery_list
```

If you want a read-only, richly-formatted view of a todo list — for example on a dashboard alongside chores and meals — pull items from the entity's `items` attribute:

```yaml
type: markdown
title: Grocery list
content: |
  {% for item in state_attr('todo.grocery_list', 'items') or [] %}
  - {% if item.status == 'completed' %}~~{{ item.summary }}~~{% else %}{{ item.summary }}{% endif %}
  {% endfor %}
```

*Note:* Skylight list items only carry a **label**. There is no per-item description or due date on Skylight's side, so the todo entity exposes summary + status only. If you need richer item metadata, use a chore instead.

### Upcoming calendar events

```yaml
type: markdown
title: Next 5 events
content: |
  {%- set events = states.calendar.slickfam_calendar.attributes -%}
  {%- for e in states.calendar | selectattr('entity_id','eq','calendar.slickfam_calendar') | list -%}
  {{ e.attributes.message }} — {{ e.attributes.start_time }}
  {%- endfor %}
```

For a proper multi-event view, use the built-in **Calendar** card or a community card like `calendar-card-pro`:

```yaml
type: calendar
entities:
  - calendar.slickfam_calendar
```

---

## Automation examples

**Announce chores at breakfast:**
```yaml
alias: Morning chores announcement
trigger:
  - platform: time
    at: "07:30:00"
action:
  - service: tts.google_translate_say
    data:
      entity_id: media_player.kitchen_display
      message: >
        Good morning. Today's chores:
        {% for c in state_attr('sensor.slickfam_chores_today', 'chores') %}
        {{ c.assignee }}: {{ c.summary }}.
        {% endfor %}
```

**Notify when someone hits a star milestone:**
```yaml
alias: Star milestone
trigger:
  - platform: numeric_state
    entity_id: sensor.logan_stars
    above: 100
action:
  - service: notify.family
    data:
      message: "🎉 Logan just crossed 100 stars!"
```

---

## Multi-frame support

Each frame gets its own HA config entry. To add a second frame, run **Add Integration → Skylight** again with the same tokens — the picker will show frames not already configured.

Multi-frame within a single entry is deferred.

---

## Troubleshooting

Enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.skylight: debug
```

| Symptom | Cause / fix |
|---|---|
| `invalid_auth` on config flow | Refresh token was pasted with surrounding whitespace or is stale. Re-copy from DevTools. |
| Calendar entity has no events | Check that events exist in the ±14/+60 day window on your frame. |
| Todo entities missing after adding a new list on the frame | New lists show up on the next 2-minute refresh — reload the integration to force it. |
| Star sensors missing for a profile | The profile must have `linked_to_profile=true` on its category. Ensure the profile is fully set up on the frame. |

---

## What changed in v2.0.0

- **Auth**: rewritten to OAuth2 Bearer + `Skylight-Api-Version: 2026-05-01` + automatic refresh cascade with rotation persisted to the config entry.
- **New platforms**: `todo` (all Skylight lists), `sensor` (chores today, meals today, task box, per-profile reward stars).
- **Calendar**: `DataUpdateCoordinator`-backed, rolling ±14/+60 day window.
- **Enriched attributes**: chores now expose description, emoji, RRULE, start-time, reward points, assignee label; meals resolve category label + recipe title + description via JSON:API `included`.
- **Device registry**: all entities grouped under one HA device per frame.
- **Removed**: username / password login (Skylight's `/api/sessions` endpoint no longer issues usable tokens for the current API).

---

## Credits

Originally forked from [MegaTheLEGEND/skylight_calendar](https://github.com/MegaTheLEGEND/skylight_calendar). OAuth2 rewrite + platform expansion by [@devinslick](https://github.com/devinslick).

## License

MIT — see [LICENSE](LICENSE).
