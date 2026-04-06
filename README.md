# Oref Alert

[![HACS Badge](https://img.shields.io/badge/HACS-Default-31A9F4.svg?style=for-the-badge)](https://github.com/hacs/integration)

[![GitHub Release](https://img.shields.io/github/release/amitfin/oref_alert.svg?style=for-the-badge&color=blue)](https://github.com/amitfin/oref_alert/releases)

![Download](https://img.shields.io/github/downloads/amitfin/oref_alert/total.svg?style=for-the-badge&color=blue) ![Analytics](https://img.shields.io/badge/dynamic/json?style=for-the-badge&color=blue&label=Analytics&suffix=%20Installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.oref_alert.total)

![Project Maintenance](https://img.shields.io/badge/maintainer-Amit%20Finkelstein-blue.svg?style=for-the-badge)

The integration is used to monitor the emergency messages coming from the [Israeli National Emergency Portal](https://www.oref.org.il//12481-he/Pakar.aspx) (Pikud Haoref). Its main usage is via the entity `sensor.oref_alert`. The entity receives the relevant messages based on HA's home location (coordinate). `sensor.oref_alert`'s state is one of: `ok`, `pre_alert`, and `alert`.
The integration is installed and configured via the user interface. There is no YAML or templates involved.

A demo video (in Hebrew) can be found [here](https://youtu.be/p6PzAlceoSY).

## Install

[HACS](https://hacs.xyz/) is the preferred and easier way to install the component. When HACS is installed, the integration can be installed using this My button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=amitfin&repository=oref_alert&category=integration)

Otherwise, download `oref_alert.zip` from the [latest release](https://github.com/amitfin/oref_alert/releases), extract and copy the content under `custom_components` directory.

Home Assistant restart is required once the integration files are copied (either by HACS or manually).

The integration should also be added to the configuration. This can be done via this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=oref_alert)

The setup identifies the area according to the [Home location in the Zones settings](https://my.home-assistant.io/redirect/zones/) (the latitude and longitude coordinate). If the detection fails, the user is asked to select the area manually.

Once the component is installed, it's possible to control additional parameters using the Configure dialog which can be accessed via this My button:

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=oref_alert)

There is a single configuration parameter **Selected area**. By default the integration finds the area based on HA's home location. There is no need to change this default. Note: it's highly discouraged to select more than a single area. `sensor.oref_alert` doesn't support more than a single area, and will not be created when choosing multiple areas or a district. It's possible to create additional `sensor` entities by using the action `oref_alert.add_sensor` (check below for more information), each with a single area.

<kbd><img width="379" height="234" alt="image" src="https://github.com/user-attachments/assets/4dbb4a39-c9dd-47f3-8df8-685189e38bac" /></kbd>

## Map Card

<img width="619" height="482" alt="image" src="https://github.com/user-attachments/assets/6ea2d479-b4ea-4f91-8e1e-9cf465a53b71" />

The integration adds a map card for displaying all active alerts. It's recommended to place the map card inside a [panel view](https://www.home-assistant.io/dashboards/panel/), so it can take full width and provide the best map experience.

Card configuration:
- `auto_fit` (optional, default: `true`): Automatically adjust the map view to include all currently active alerts and pre-alerts.
- `show_home` (optional, default: `false`): Show `zone.home` on the map. This option is typically used together with `auto_fit: false`, allowing the map to stay centered on the home area. This view is useful for users who are interested in their home's surroundings.
- `hebrew_basemap` (optional, default: `true`): Use a Hebrew basemap tile layer. It is not recommended to enable this option when both `auto_fit` and `show_home` are enabled. The Hebrew basemap supports zoom levels only up to 15, while most other map providers support zoom levels up to 19–20. When `show_home` is enabled, `auto_fit` often selects a higher zoom level, which may exceed the Hebrew basemap's maximum supported zoom level.
- `show_pre_alert` (optional, default: `true`): include `pre_alert` areas on the map (in yellow).
- `entities` (optional, YAML only, no UI): additional entities passed to the [map card](https://www.home-assistant.io/dashboards/map). See also [here](https://www.home-assistant.io/dashboards/map/#entities) and [here](https://www.home-assistant.io/dashboards/map/#options-for-entities).
- Additional [map card options](https://www.home-assistant.io/dashboards/map/#yaml-configuration) can be passed through in YAML and are forwarded to the underlying Home Assistant map card. This card still enforces `type`, `geo_location_sources`, `fit_zones`, and computes `entities` and `auto_fit` from its own settings.

| <img width="344" height="551" alt="image" src="https://github.com/user-attachments/assets/f2d17037-4e40-4edb-ae21-0375bd32f224" /> |
|---|

A demo (in Hebrew) can be found [here](https://youtu.be/j5jny3WrgJk).

## Record's Attribute

`sensor.oref_alert` has `record` attribute which holds additional information about the last message. This record has the following fields:
1. `alertDate`: e.g. `2025-06-30 15:00:00` (Israel timezone).
2. `title`: e.g. `ירי רקטות וטילים`. Always in Hebrew.
3. `data`: a single area name, e.g. `תל אביב - מרכז העיר`.
4. `category`: an integer of the category as listed [here](https://www.oref.org.il/alerts/alertCategories.json). Categories 14 and 13 are used for `pre_alert` and `end`, respectively.
5. `channel`: the receiving channel. Below is the list of options. When the same alert is coming on multiple channels, only the first channel to send the alert will be used and the following ones are ignored. The fields of the messages are normalized and have the same format regardless of the channel.
    1. `website-history`: the history file of the official website.
    2. `website`: the real-time file of the official website.
    3. `mobile`: the mobile notification channel of the official app.
    4. `tzevaadom`: the notification channel of [tzevaadom.co.il](https://www.tzevaadom.co.il/).
    5. `synthetic`: synthetic records generated via custom actions (e.g. [synthetic alert](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.synthetic_alert) and [manual event end](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.manual_event_end)).

## Automation

Here are 3 different examples of typical automation triggers:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.oref_alert
    from: ok
    to: pre_alert

triggers:
  - trigger: state
    entity_id: sensor.oref_alert
    from:
      - ok
      - pre_alert
    to: alert

triggers:
  - trigger: state
    entity_id: sensor.oref_alert
    from:
      - pre_alert
      - alert
    to: ok
```

Note: if `pre_alert` doesn't change to `alert` within 20 minutes, the state is getting reverted back to `ok`.

## Additional Sensors

It's possible to create additional entities using the action `oref_alert.add_sensor`. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.add_sensor)

The selected areas of an additional sensor can be different (non overlapping) than the primary entity.

The action `oref_alert.remove_sensor` can be used for deleting an additional sensor. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.remove_sensor)

The action `oref_alert.edit_sensor` can be used for editing an additional sensor by adding or removing areas. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.edit_sensor)

## Event Entity

`event.oref_alert` is an additional entity which can be used to get the messages. There are 3 type of events: `pre_alert`, `alert` and `end`.

*Note: this sensor is not created when the configuration contains multiple areas or a district. It's possible in such a case to create an additional sensor configuration for the specific area of interest by using the action `oref_alert.add_sensor`.*

## Binary Sensor

`binary_sensor.oref_alert` is `on` when there is an active alert in the Home area.

| Feature | `binary_sensor.oref_alert` | `sensor.oref_alert` |
|---------|----------------------------|---------------------|
| `pre_alert` support | ❌ Not supported (`pre_alert` is reported as `off`) | ✅ Supported |
| Multiple areas | ✅ Supported — state becomes `on` if **any area** has an active alert | ❌ Not supported |

## All Areas Sensor

`binary_sensor.oref_alert_all_areas` is an additional sensor monitoring any active alert in the country. The sensor is `on` when there is one or more active alerts in Israel.

## Binary Sensors Attributes

Binary sensors have the following attributes:
1. `Areas`: the list of areas provided by the user.
2. `Selected areas active alerts`: when the sensor is `on`, the alerts are listed here.
3. `Selected areas updates`: the list of updates for the selected areas.
4. `Country active alerts`: all active alerts in Israel.
5. `Country updates`: the updates in Israel over the last 5 minutes.

## Time To Shelter Sensors

The integration creates an additional set of sensors which monitor the time to shelter for a specific area. The ID of the entity is similar to the corresponding binary sensor, with the suffix of `_time_to_shelter`. For example, `sensor.oref_alert_time_to_shelter`. When there is a new alert in the area, the `state` of the sensor is set according to the instructions of Pikud Haoref for the selected area (e.g. 90 seconds in the middle of Israel). The `state` of the sensor decrements as time passes, and it becomes `unknown` once it reaches -60 seconds (one minute past due). The sensor has the following extra attributes:
1. `Area`: the name of the area.
2. `Time to shelter`: as provided by Pikud Haoref for the selected area (constant value).
3. `Alert`: the active alert (when there is such).
4. `Display`: a user-friendly string of the time in the format of "mm:ss".

*Note: this sensor is not created when the configuration contains multiple areas or a district. It's possible in such a case to create an additional sensor configuration for the specific area of interest by using the action `oref_alert.add_sensor`.*

## Geo Location Entities

Geo-location entities are created for every active alert in Israel (regardless of the selected areas). These entities exist while the corresponding alert is active. The state of the entity is the distance in kilometers from HA home's coordinate. In addition, each entity has the following attributes:
1. `friendly_name`: alert's area
2. `latitude`
3. `longitude`
4. `home_distance`: same as the state, but an integer type and not a string (state is always a string)
5. `title`: alert's description
7. `date`
6. `category`: integer with alert's category
7. `icon`: Material icon ("mdi:xxx") based on the category
8. `emoji`: based on the category
9. `district`: area's district

These entities provide the data that powers the map card described above.

## Home Assistant Events

A new event is fired on HA bus for any new alert. Here are 2 examples of such an events:

```yaml
event_type: oref_alert_record
data:
  area: תל אביב - מרכז העיר
  home_distance: 9.7
  latitude: 32.0798
  longitude: 34.7772
  category: 1
  title: ירי רקטות וטילים
  type: alert
  icon: mdi:rocket-launch
  emoji: 🚀
  district: דן
  source: mobile
```

```yaml
event_type: oref_alert_record
data:
  area: תל אביב - מרכז העיר
  home_distance: 9.7
  latitude: 32.0798
  longitude: 34.7772
  category: 14
  title: הנחיה מקדימה
  type: pre_alert
  icon: mdi:flash-alert
  emoji: ⚡
  district: דן
  source: tzevaadom
```

In the [Mobile Notifications: Detailed Alerts](#detailed-alerts) section there is an example for usage of this event.

For backward compatibility, events are also fired on `oref_alert_event` and `oref_alert_update_event` for alert and update, respectively. Here is an example of such an update event:

```yaml
event_type: oref_alert_update_event
data:
  area: תל אביב - מרכז העיר
  home_distance: 9.7
  latitude: 32.0798
  longitude: 34.7772
  category: 13
  title: ניתן לצאת מהמרחב המוגן
  icon: mdi:message-alert
  emoji: ⚠
  district: דן
  source: website
```

## Synthetic Alert

Synthetic alerts are useful for testing purposes. The action `oref_alert.synthetic_alert` can be used to create a synthetic alert. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.synthetic_alert)

*Note: a synthetic alert is an additional alert. A synthetic alert disappears after the amount of seconds supplied to the action. This is different from a regular alert which disappears only after 24 hours.*

## Manual Event End

The action `oref_alert.manual_event_end` can be used to mark active alerts as ended manually (title: `האירוע סומן כהסתיים ידנית`). The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.manual_event_end)

The optional `area` field can be used to limit this action to specific areas.

```yaml
action: oref_alert.manual_event_end
data:
  area:
    - תל אביב - דרום העיר ויפו
    - קריית שמונה
```

## Areas Status

The action `oref_alert.areas_status` returns the current areas whose status is `pre_alert` or `alert`. The response is keyed by area name, and each area contains the published fields used by the integration: `area`, `home_distance`, `latitude`, `longitude`, `category`, `title`, `icon`, `emoji`, `district`, `channel`, `type`, and `date`.

The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.areas_status)

```yaml
action: oref_alert.areas_status
response_variable: active_areas
```

Example response:

```yaml
קריית שמונה:
  area: קריית שמונה
  home_distance: 150.2
  latitude: 33.2077
  longitude: 35.5696
  category: 14
  channel: website
  date: "2025-06-30T15:00:00+03:00"
  title: "ירי רקטות וטילים"
  icon: mdi:flash-alert
  emoji: ⚡
  district: קו העימות
  type: pre_alert
תל אביב - דרום העיר ויפו:
  area: תל אביב - דרום העיר ויפו
  home_distance: 9.2
  latitude: 32.0463
  longitude: 34.7656
  category: 1
  channel: website
  date: "2025-06-30T15:01:00+03:00"
  title: "ירי רקטות וטילים"
  icon: mdi:rocket-launch
  emoji: 🚀
  district: דן
  type: alert
```

## Last Update

The action `oref_alert.last_update` returns `last_update`, the last time any area's status was changed, and `version`, the integration's version. The map card uses these values to decide whether it should re-render or force a page reload after an integration update.

## Template Functions

The integration adds the following template helper functions:

### `oref_alerts`

The historical alerts (last 24h), sorted from newest to oldest. Each item contains:
`date`, `area`, `title`, `icon`, `emoji`, `category`, `district`, `home_distance`, `latitude`, `longitude`, `channel`.

`{{ oref_alerts | list }}`

### `oref_areas`

Returns the list of areas. Districts are not included by default. It's possible to set the 1st parameter (`groups`) to `True` to include them.

`{{ oref_areas }}`

`{{ oref_areas(True) }}`

### `oref_district`

Gets an area name and returns its district. If no mapping is found, the return value is the input area name. Can be used also as a filter.

`{{ oref_district('פתח תקווה') == 'דן' }}`

`{{ ['area name'] | map('oref_district') }}`

### `oref_coordinate`

Gets an area name and returns the coordinate of the city center as a tuple (lat, lon). If no mapping is found, the return value is None. Can be used also as a filter.

`{{ oref_coordinate('פתח תקווה') == (32.084, 34.8878) }}`

`{{ 'area name' | oref_coordinate }}`

### `oref_shelter`

Gets an area name and returns its time to shelter (seconds). If no mapping is found, the return value is None. Can be used also as a filter.

`{{ oref_shelter('פתח תקווה') == 90 }}`

`{{ 'area name' | oref_shelter }}`

### `oref_icon`

Gets a category (int) and returns the corresponding MDI icon (has "mdi:" prefix). If no mapping is found, the return value is "mdi:alert". Can be used also as a filter.

`{{ oref_icon(1) == 'mdi:rocket-launch' }}`

`{{ 2 | oref_icon == 'mdi:airplane-alert' }}`

### `oref_emoji`

Gets a category (int) and returns the corresponding emoji. If no mapping is found, the return value is "🚨". Can be used also as a filter.

`{{ oref_emoji(1) == '🚀' }}`

`{{ [2] | map('oref_emoji') | list == ['✈️'] }}`

### `oref_distance`

Gets an area name and measures the distance between the area's coordinate and home, an entity, or coordinate (similar to the built-in [`distance`](https://www.home-assistant.io/docs/configuration/templating/#distance) function). The unit of measurement (kilometers or miles) depends on the system’s configuration settings. If the area name is not found, the return value is None. Can be used also as a filter.

`{{ oref_distance('פתח תקווה') }}`

`{{ ['area name'] | map('oref_distance', 'device_tracker.amits_iphone') }}`

### `oref_test_distance`

Gets an area name and a distance and other optional parameters that will be passed to `oref_distance`. Returns True if the distance is less than or equals to the distance. If the area name is not found, the return value is False. Can be used also as a test.

`{{ oref_test_distance('area name', 5, 'device_tracker.amits_iphone')}}`

`{{ ['area name'] | select('oref_test_distance', 5) }}`

### `oref_polygon`

Gets an area name and returns the polygon of the area's perimeter. If the area name is not found, the return value is None. Can be used also as a filter.

`{{ oref_polygon('פתח תקווה') }}`

`{{ 'area name' | oref_polygon }}`

### `oref_find_area`

Returns area by coordinate (lat, lon). The coordinate can be anywhere inside the area's polygon. If no area is found, the return value is None.  Can be used also as a filter. Unavailable for [limited templates](https://www.home-assistant.io/docs/configuration/templating/#limited-templates).

`{{ oref_find_area(32.072, 34.879) == 'פתח תקווה' }}`

`{{ (32.0798, 34.7772) | oref_find_area == 'תל אביב - מרכז העיר' }}`

`{{ oref_find_area(state_attr('device_tracker.amits_iphone', 'latitude'), state_attr('device_tracker.amits_iphone', 'longitude')) }}`

## Usages

The basic usage is to trigger an automation rule when `sensor.oref_alert` state is changed. Some ideas for the `actions` section can be: play a song (can be less stressful when choosing the right song and setting the volume properly), open the lights and TV in the shelter, etc'.

Below are a few more examples:

### Displaying States

Below is an example of a card with the main entities and color coding of the icons.

```yaml
- type: entities
  card_mod:
    style: |
      :host {
        --state-binary_sensor-off-color: green;
        --state-binary_sensor-on-color: red;
      }
  entities:
    - entity: sensor.oref_alert
      card_mod:
        style: |
          :host {
            {% if is_state('sensor.oref_alert', 'ok') %}
            --card-mod-icon-color: green;
            {% elif is_state('sensor.oref_alert', 'pre_alert') %}
            --card-mod-icon-color: orange;
            {% else %}
            --card-mod-icon-color: red;
            {% endif %}
          }
    - entity: binary_sensor.oref_alert
    - entity: binary_sensor.oref_alert_all_areas
    - entity: sensor.oref_alert_time_to_shelter
      type: attribute
      attribute: display
```

Note that is requires the installation of [card-mod](https://github.com/thomasloven/lovelace-card-mod) lovelace custom component.

### Presenting Active Alerts in Israel

Here is a [markdown card](https://www.home-assistant.io/dashboards/markdown/) for presenting all active alerts sorted by their distance from HA's home coordinate (the list of categories is based on [this file](https://www.oref.org.il/alerts/alertCategories.json)):

```yaml
type: markdown
content: >-
  {% for alert in states.geo_location |
     selectattr('entity_id', 'in', integration_entities('oref_alert')) |
     sort(attribute='attributes.home_distance') %}
    <p>
      <font color="red"><ha-icon icon="{{ alert.attributes.icon }}"></ha-icon></font>
      <a href="https://maps.google.com/?q={{ alert.attributes.latitude }},{{ alert.attributes.longitude }}">{{ alert.name }}</a>
      [{{ alert.state | int }} ק״מ]
      ({{ alert.attributes.date | as_timestamp | timestamp_custom('%H:%M') }})
    </p>
  {% endfor %}
entity_id: binary_sensor.oref_alert_all_areas
card_mod:
  style: |
    ha-card {
      direction: rtl;
    }
```

(The `card_mod` section at the bottom is only required when the language is English. It forces RTL for this element. Note that it requires the installation of [card-mod](https://github.com/thomasloven/lovelace-card-mod) lovelace custom component.)

<kbd><img width="310" alt="image" src="https://github.com/user-attachments/assets/21ad82ea-6ff6-43c3-8c57-a1f6b2785498"></kbd>

### Presenting Last 100 Alerts

Here is a [markdown card](https://www.home-assistant.io/dashboards/markdown/) for presenting the last 100 alerts (in the last 24 hours):

```yaml
type: markdown
content: >-
  {% set ns = namespace(count=0) %}
  {% for alert in oref_alerts %}
    {% if ns.count >= 100 %}
      {% break %}
    {% endif %}
    <p>
      <font color="red"><ha-icon icon="{{ alert.icon }}"></ha-icon></font>
      <a href="https://maps.google.com/?q={{ alert.latitude }},{{ alert.longitude }}">{{ alert.area }}</a>
      [{{ alert.home_distance | int }} ק״מ]
      ({{ alert.date | as_timestamp | timestamp_custom('%H:%M') }})
    </p>
    {% set ns.count = ns.count + 1 %}
  {% endfor %}
entity_id: binary_sensor.oref_alert_all_areas
card_mod:
  style: |
    ha-card {
      direction: rtl;
    }
```

### Presenting Alerts in the Home's Area

Here is a [markdown card](https://www.home-assistant.io/dashboards/markdown/) for presenting the home's alerts (in the last 24 hours):

```yaml
type: markdown
content: >-
  {% for alert in (oref_alerts | selectattr('area', 'in', state_attr('binary_sensor.oref_alert', 'areas'))) %}
    <p>
      {{ loop.index }}.
      {{ alert.date | as_timestamp | timestamp_custom('%H:%M') }}
      <font color="red"><ha-icon icon="{{ alert.icon }}"></ha-icon></font>
    </p>
  {% endfor %}
entity_id: binary_sensor.oref_alert
card_mod:
  style: |
    ha-card {
      direction: rtl;
    }
```

### Mobile Notifications

#### Combined Alerts

Here is an automation rule for getting mobile notifications for new alerts:

```yaml
alias: Oref Alert Country Notifications
id: oref_alert_country_notifications
triggers:
  - trigger: state
    entity_id: binary_sensor.oref_alert
    attribute: country_active_alerts
actions:
  - variables:
      current: "{{ trigger.to_state.attributes.country_active_alerts | map(attribute='data') | list }}"
      previous: "{{ trigger.from_state.attributes.country_active_alerts | map(attribute='data') | list }}"
      alerts: "{{ current | difference(previous) | unique | sort | list }}"
      alerts_per_push: "{{ (150 / (alerts | map('length') | average(0) | add(3))) | int }}"
  - repeat:
      while:
        - condition: template
          value_template: "{{ alerts | length > 0 }}"
      sequence:
        - action: notify.mobile_app_amits_iphone
          data:
            title: התרעות פיקוד העורף
            message: "{{ alerts[:alerts_per_push] | join(' | ') }}"
        - variables:
            alerts: "{{ alerts[alerts_per_push:] }}"
mode: queued
```

<img width="400" src="https://github.com/user-attachments/assets/ab12abf4-042e-4099-a1ef-e26db57b653a">

It's possible to get only alerts which are close to home (in the example below it's 10km from home). To do that, the `current` variable should be defined as:

```yaml
current: "{{ trigger.to_state.attributes.country_active_alerts | map(attribute='data') | select('oref_test_distance', 10) | list }}"
```

#### Detailed Alerts

This is a different approach where only alerts which are either within 30km from home or 5km from Amit's current location generate notifications. However, each notification has additional information (and being sent separately):

```yaml
alias: Oref Alert Country Notifications Details
id: oref_alert_country_notifications_details
triggers:
  - trigger: event
    event_type: oref_alert_record
actions:
  - condition: or
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.home_distance < 30 }}"
      - condition: template
        value_template: "{{ distance('device_tracker.amits_iphone', trigger.event.data.latitude, trigger.event.data.longitude) < 5 }}"
  - action: notify.mobile_app_amits_iphone
    data:
      title: התרעות פיקוד העורף
      message: "{{ trigger.event.data.emoji }} {{ trigger.event.data.area }} [{{ trigger.event.data.title }}] ({{ trigger.event.data.home_distance | int }} ק״מ)"
mode: queued
```

<img width="400" src="https://github.com/user-attachments/assets/3262dd19-0f65-44f4-8983-270da96200e5">

#### Custom Sound

It's possible to set a custom sound for a specific mobile app push notification. Here is an iOS example:

```yaml
action: notify.mobile_app_amits_iphone
data:
  title: התרעות פיקוד העורף
  message: <<omitted-in-example>>
  data:
    push:
      sound: US-EN-Morgan-Freeman-Vacate-The-Premises.wav
```

Additional information (for Android and iOS) can be found [here](https://companion.home-assistant.io/docs/notifications/notification-sounds).

#### Custom Status Bar Icon

As it is possible to set a custom notification icon on Android devices, the `oref_icon` helper function, which returns an MDI icon, can be used:

```yaml
action: notify.mobile_app_<<omitted-in-example>>
data:
  title: <<omitted-in-example>>
  message: <<omitted-in-example>>
  data:
    notification_icon: "{{ oref_icon(trigger.to_state.attributes.record.category) }}"
```

Additional information (for Android only) can be found [here](https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-status-bar-icon).

#### Critical Notifications

For the notifications to be displayed immediately on the screen after dispatching, it is recommended to set them as critical.

For example, for Android devices:

```yaml
action: notify.mobile_app_<<omitted-in-example>>
data:
  title: <<omitted-in-example>>
  message: <<omitted-in-example>>
  data:
    priority: high
    ttl: 0
```

This is useful as by default, notifications may not ring the device when it is stationary, or when the screen has been turned off for a prolonged period of time.

Additional information (for Android and iOS) can be found [here](https://companion.home-assistant.io/docs/notifications/critical-notifications).

### Time To Shelter Countdown

Here is another advanced usage for counting down (every 5 seconds) the time to shelter:
```yaml
alias: Oref Alert Time To Shelter Countdown
id: oref_alert_time_to_shelter_countdown
triggers:
  - trigger: state
    entity_id: sensor.oref_alert_time_to_shelter
actions:
  - variables:
      time_to_shelter: "{{ states('sensor.oref_alert_time_to_shelter') | int(-1) }}"
  - condition: "{{ time_to_shelter >= 0 and time_to_shelter % 5 == 0}}"
  - action: tts.google_translate_say
    data:
      entity_id: media_player.shelter_speaker
      language: iw
      message: "{{ time_to_shelter }}"
max: 100
mode: parallel
```

## Removing the Integration

1. **Delete the configuration:**
   - Open the integration page ([my-link](https://my.home-assistant.io/redirect/integration/?domain=oref_alert)), click the 3‑dot menu (⋮), and select **Delete**.

2. **Remove the integration files:**
   - If the integration was installed via **HACS**, follow the [official HACS removal instructions](https://www.hacs.xyz/docs/use/repositories/dashboard/#removing-a-repository).
   - Otherwise, manually delete the integration’s folder `custom_components/oref_alert`.

📌 A **Home Assistant core restart** is required in both cases to fully apply the removal.

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Acknowledgements

- Thanks to [Edo Yeheskel](https://github.com/yeheskel2016) for the idea, reference and tremendous help in implementing the MQTT channel.
- Thanks to [Gugulator](https://github.com/Gugulator) for the Russian translation as well as many great ideas during our brainstorming sessions.
