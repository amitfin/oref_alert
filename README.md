# Oref Alert

[![HACS Badge](https://img.shields.io/badge/HACS-Default-31A9F4.svg?style=for-the-badge)](https://github.com/hacs/integration)

[![GitHub Release](https://img.shields.io/github/release/amitfin/oref_alert.svg?style=for-the-badge&color=blue)](https://github.com/amitfin/oref_alert/releases)

![Download](https://img.shields.io/github/downloads/amitfin/oref_alert/total.svg?style=for-the-badge&color=blue) ![Analytics](https://img.shields.io/badge/dynamic/json?style=for-the-badge&color=blue&label=Analytics&suffix=%20Installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.oref_alert.total)

![Project Maintenance](https://img.shields.io/badge/maintainer-Amit%20Finkelstein-blue.svg?style=for-the-badge)

***Hebrew video of the installation, configuration and usage can be found [here](https://youtu.be/q6QNV7vwkiM). A blog post with Russian instructions can be found [here](https://homeusmart.blogspot.com/2023/10/haidf.html).***

The integration provides `binary_sensor.oref_alert` which turns on when an alert is reported by the [Israeli National Emergency Portal](https://www.oref.org.il//12481-he/Pakar.aspx) (Pikud Haoref). The sensor monitors the alerts in the user selected areas. An alert is considered active for a certain period of time as configured by the user (10 minutes by default).
The integration is installed and configured via the user interface. There is no YAML or templates involved.

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

There are 6 configuration fields:
1. **Selected areas**: list of areas to monitor. It's also possible to select a district (מחוז) and all-areas (כל האזורים) for cities with sub-areas.
2. **Active duration of an alert**: this is the alert's active time period (in minutes). The default is 10 minutes.
3. **Update frequency**: polling frequency from the website (in seconds). The default is 2 seconds. Note: data is received via multiple channels as explained [here](#alerts-attributes). This setting impacts only the channels `website` and `website-history`.
4. **On icon**: the icon to be used when there are active alerts in one of the selected areas. This is the icon which is displayed when the state of the binary sensor is "on".
5. **Off icon**: the icon to  be used when the state of the binary sensor is "off".
6. **Add 'All Alerts' attributes**: when it's off (the default) the attributes `Country alerts` and `Selected areas alerts` are not added to the binary sensors. These attributes hold the list of all alerts over the last 24-hours which can be long and cause performance issues on weaker systems. Both attributes are not used often and are not part of any example below.

<kbd><img src="https://github.com/user-attachments/assets/7a3e27f5-f8f9-4126-a2f3-beea20351270" width="400"></kbd>

## All Areas Sensor

`binary_sensor.oref_alert_all_areas` is an additional sensor monitoring any active alert in the country. The sensor is `on` when there is one or more active alerts in Israel.

## Additional Sensors

It's possible to create additional sensors using the action `oref_alert.add_sensor`. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.add_sensor)

The selected areas of an additional sensor can be different (non overlapping) than the primary sensor.

The action `oref_alert.remove_sensor` can be used for deleting an additional sensor. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.remove_sensor)

The action `oref_alert.edit_sensor` can be used for editing an additional sensor by adding or removing areas. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.edit_sensor)

Note: additional sensors created before v2.2.0 use a different implementation. It's better to delete such entities and to create new sensors using the new functionality (old sensors are not broken and can be used).

## Additional Attributes

All sensors have the following extra attributes:
1. `Areas`: the list of areas provided by the user.
2. `Alert active duration`: as configured by the user.
3. `Selected areas active alerts`: when the sensor is `on`, the alerts are listed here.
4. `Selected areas updates`: the list of updates for the selected areas.
5. `Selected areas alerts`: active and inactive alerts in the selected areas. Exists only when the [configuration](https://my.home-assistant.io/redirect/integration/?domain=oref_alert) "Add 'All Alerts' attributes" is turned on.
6. `Country active alerts`: all active alerts in Israel.
7. `Country updates`: all updates in Israel.
8. `Country alerts`: all alerts in Israel. Exists only when the [configuration](https://my.home-assistant.io/redirect/integration/?domain=oref_alert) "Add 'All Alerts' attributes" is turned on.

## Alert's Attributes

Alerts and updates inside attributes have the following fields:
1. `alertDate`: e.g. `2025-06-30 15:00:00` (Israel timezone).
2. `title`: e.g. `ירי רקטות וטילים`. Always in Hebrew.
3. `data`: a single area name, e.g. `תל אביב - מרכז העיר`.
4. `category`: an integer of the category as listed [here](https://www.oref.org.il/alerts/alertCategories.json). Categories 13 and 14 are used for updates.
5. `channel`: the receiving channel. Below is the ordered list of options. When the same alert is coming on multiple channels, only the higher channel will be used. The fields of the alerts are normalized and have the same format regardless of the channel.
    1. `website-history`: the history file of the official website (polling).
    2. `website`: the real-time file of the official website (polling).
    3. `mobile`: the mobile notification channel of the official app.
    4. `tzevaadom`: the notification channel of [tzevaadom.co.il](https://www.tzevaadom.co.il/).
    5. `synthetic`: synthetic alert for testing purposes generated via the [synthetic-alert action](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.synthetic_alert).

## Time To Shelter Sensors

The integration creates an additional set of sensors which monitor the time to shelter for a specific area. The ID of the entity is similar to the corresponding binary sensor, with the suffix of `_time_to_shelter`. For example, `sensor.oref_alert_time_to_shelter`. When there is a new alert in the area, the `state` of the sensor is set according to the instructions of Pikud Haoref for the selected area (e.g. 90 seconds in the middle of Israel). The `state` of the sensor decrements as time passes, and it becomes `unknown` once it reaches -60 seconds (one minute past due). The sensor has the following extra attributes:
1. `Area`: the name of the area.
2. `Time to shelter`: as provided by Pikud Haoref for the selected area (constant value).
3. `Alert`: the active alert (when there is such).
4. `Display`: a user-friendly string of the time in the format of "mm:ss".

*Note: this sensor is not created when the configuration contains multiple areas or groups (e.g. cities with multiple areas or districts). It's possible in such a case to create an additional sensor configuration for the specific area of interest by using the action `oref_alert.add_sensor`.*

## Alert End Time Sensors

The integration creates an additional set of sensors which monitor the time to the end of the alert for a specific area. The ID of the entity is similar to the corresponding binary sensor, with the suffix of `_end_time`. For example, `sensor.oref_alert_end_time`. When there is a new alert in the area, the `state` of the sensor is set according to the `Alert active duration` as configured by the user (default is 10 minutes). The `state` of the sensor decrements as time passes, and it becomes `unknown` once the alert is `off`. The sensor has the following extra attributes:
1. `Area`: the name of the area.
2. `Alert active duration`: as configured by the user.
3. `Alert`: the active alert (when there is such).
4. `Display`: a user-friendly string of the time in the format of "mm:ss".

*Note: this sensor is not created when the configuration contains multiple areas or groups (e.g. cities with multiple areas or districts). It's possible in such a case to create an additional sensor configuration for the specific area of interest by using the action `oref_alert.add_sensor`.*

## Updates Processing

Updates can be sent a few minutes before the alert. They can also be sent for indicating that it's safe to get out of the shelter. However, these updates are less structured so their parsing is not fully reliable and can get broken if the text (or category) is changed. Nevertheless, this data is valuable. Below you can see how it can be done (currently). Note that it can get broken, so keep monitoring for changes and change your settings accordingly:

[![Open your Home Assistant instance and show your helper entities.](https://my.home-assistant.io/badges/helpers.svg)](https://my.home-assistant.io/redirect/helpers/)

→ Click `+ CREATE HELPER` button → `Template` → `Template a binary sensor`:

### Preemptive Update Binary Sensor

<kbd><img src="https://github.com/user-attachments/assets/5413ca09-8f69-4808-ac6e-066c7be5768e" width="400"/></kbd>

`{{ is_state('binary_sensor.oref_alert', 'off') and state_attr('binary_sensor.oref_alert', 'selected_areas_updates') and state_attr('binary_sensor.oref_alert', 'selected_areas_updates')[0]['title'] is search('בדקות הקרובות') }}`

### Ending Update Binary Sensor

<kbd><img src="https://github.com/user-attachments/assets/c6628c85-868b-4fa0-a0e9-01e85cfb7d95" width="400"/></kbd>

`{{ is_state('binary_sensor.oref_alert', 'off') and state_attr('binary_sensor.oref_alert', 'selected_areas_updates') and state_attr('binary_sensor.oref_alert', 'selected_areas_updates')[0]['title'] is search('האירוע הסתיים') }}`

## Geo Location Entities

Geo-location entities are created for every active alert in Israel (regardless of the selected areas). These entities exist while the corresponding alert is active (10 minutes by default). The state of the entity is the distance in kilometers from HA home's coordinate. In addition, each entity has the following attributes:
1. `friendly_name`: alert's area
2. `latitude`
3. `longitude`
4. `home_distance`: same as the state, but an integer type and not a string (state is always a string)
5. `title`: alert's description
7. `date`
6. `category`: integer with alert's category
7. `icon`: Material icon ("mdi:xxx") based on the category
8. `emoji`: based on the category

The [map card](https://www.home-assistant.io/dashboards/map) can be used to present the entities on a map. `oref_alert` should be added to [geo_location_sources](https://www.home-assistant.io/dashboards/map/#geo_location_sources), and [auto_fit](https://www.home-assistant.io/dashboards/map/#auto_fit) should be set to true:

```
type: map
entities: []
auto_fit: true
geo_location_sources:
  - oref_alert
```

This will create a map presenting all active alerts in Israel:

<kbd><img width="625" alt="image" src="https://github.com/amitfin/oref_alert/assets/19599059/6e5345c5-ba6e-45c0-a8fb-e194ba178e63"></kbd>

(Below you can find a another explanation on how to add a textual element for the data.)

## Events

A new event is fired on HA bus for any new alert. Here is an example of such an event:

```
event_type: oref_alert_event
data:
  area: תל אביב - מרכז העיר
  home_distance: 9.7
  latitude: 32.0798
  longitude: 34.7772
  category: 1
  title: ירי רקטות וטילים
  icon: mdi:rocket-launch
  emoji: 🚀
  source: mobile
```

In the [Mobile Notifications: Detailed Alerts](#detailed-alerts) section there is an example for usage of this event.

Events are also fired for updates. Their type is `oref_alert_update_event` instead of `oref_alert_event`. Here is an example of such an event:

```
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
  source: website
```

## Synthetic Alert

Synthetic alerts are useful for testing purposes. The action `oref_alert.synthetic_alert` can be used to create a synthetic alert. The action can be accessed via this My button:

[![Open your Home Assistant instance and show your action developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.synthetic_alert)

*Note: a synthetic alert is an additional alert. It doesn't override or hide any other alert. A synthetic alert disappears after the amount of seconds supplied to the action. This is different from a regular alert which disappears only after 24 hours.*

## Template Functions

The integration adds the following template helper functions:

### `oref_areas`

Returns the list of areas. By default, group of areas (like districts and cities' "all areas" for cities with multiple areas) are not included. It's possible to set the 1st parameter (`groups`) to `True` to include them.

`{{ oref_areas() }}`

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

### `oref_find_area`

Returns area by coordinate (lat, lon). The coordinate can be anywhere inside the area's polygon. If no area is found, the return value is None.  Can be used also as a filter. Unavailable for [limited templates](https://www.home-assistant.io/docs/configuration/templating/#limited-templates).

`{{ oref_find_area(32.072, 34.879) == 'פתח תקווה' }}`

`{{ (32.0798, 34.7772) | oref_find_area == 'תל אביב - מרכז העיר' }}`

`{{ oref_find_area(state_attr('device_tracker.amits_iphone', 'latitude'), state_attr('device_tracker.amits_iphone', 'longitude')) }}`

## Usages

The basic usage is to trigger an automation rule when the binary sensor is turning `on`. Some ideas for the `actions` section can be: play a song (can be less stressful when choosing the right song and setting the volume properly), open the lights and TV in the shelter, etc'. It's also possible to trigger an alert when the sensor is turning `off` for getting an indication when it's safe to get out of the shelter.

Below are a few more examples:

### Coloring State Icons

```
type: entities
entities:
  - entity: binary_sensor.oref_alert
    card_mod:
      style: |
        :host {
          --state-binary_sensor-on-color: red;
          --state-binary_sensor-off-color: green;
          }
```

<kbd>![image](https://github.com/amitfin/oref_alert/assets/19599059/9f6d08f0-8269-499a-9c2d-1fe263257457)</kbd>


Note that it depends on the installation of [card-mod](https://github.com/thomasloven/lovelace-card-mod) lovelace custom component.

### Displaying Countdown Timers

```
type: entities
entities:
  - entity: sensor.oref_alert_time_to_shelter
    type: attribute
    attribute: display
  - entity: sensor.oref_alert_end_time
    type: attribute
    attribute: display
```

<kbd>![image](https://github.com/user-attachments/assets/bede82e5-022a-41d8-abd7-502821c7d558)</kbd>


### Presenting Active Alerts in Israel

Here is a [markdown card](https://www.home-assistant.io/dashboards/markdown/) for presenting all active alerts sorted by their distance from HA's home coordinate (the list of categories is based on [this file](https://www.oref.org.il/alerts/alertCategories.json)):

```
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
card_mod:
  style: |
    ha-card {
      direction: rtl;
    }
```

(The `card_mod` section at the bottom is only required when the language is English. It forces RTL for this element. Note that it requires the installation of [card-mod](https://github.com/thomasloven/lovelace-card-mod) lovelace custom component.)

<kbd><img width="310" alt="image" src="https://github.com/user-attachments/assets/21ad82ea-6ff6-43c3-8c57-a1f6b2785498"></kbd>

### Mobile Notifications

#### Combined Alerts

Here is an automation rule for getting mobile notifications for new alerts:

```
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

```
current: "{{ trigger.to_state.attributes.country_active_alerts | map(attribute='data') | select('oref_test_distance', 10) | list }}"
```

#### Detailed Alerts

This is a different approach where only alerts which are either within 30km from home or 5km from Amit's current location generate notifications. However, each notification has additional information (and being sent separately):

```
alias: Oref Alert Country Notifications Details
id: oref_alert_country_notifications_details
triggers:
  - trigger: event
    event_type: oref_alert_event
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

#### Updates

Here is an automation rule for getting mobile notifications for updates:

```
alias: Oref Alert Updates
id: oref_alert_updates
mode: parallel
triggers:
  - trigger: state
    entity_id: binary_sensor.oref_alert
    attribute: selected_areas_updates
actions:
  - variables:
      title: הודעה מפיקוד העורף לאזורך
      previous_length: "{{ trigger.from_state.attributes.selected_areas_updates | length }}"
      previous_message: "{{ trigger.from_state.attributes.selected_areas_updates[0]['title'] if previous_length > 0 else None }}"
      length: "{{ trigger.to_state.attributes.selected_areas_updates | length }}"
      message: "{{ trigger.to_state.attributes.selected_areas_updates[0]['title'] if length > 0 else None }}"
  - condition: "{{ message and message != previous_message }}"
  - action: notify.mobile_app_amits_iphone
    data:
      title: "{{ title }}"
      message: "{{ message }}"
  - action: tts.google_translate_say
    data:
      entity_id: media_player.shelter_speaker
      language: iw
      message: "{{ title }}: {{ message }}"
```

<img width="400" src="https://github.com/user-attachments/assets/62a4aab5-39e8-4f5b-bb98-33f55d43ca51">

#### Custom Sound

It's possible to set a custom sound for a specific mobile app push notification. Here is an iOS example:

```
action: notify.mobile_app_amits_iphone
data:
  title: התרעות פיקוד העורף
  message: <<omitted-in-example>>
  data:
    push:
      sound: US-EN-Morgan-Freeman-Vacate-The-Premises.wav
```

Additional information (for Android and iOS) can be found [here](https://companion.home-assistant.io/docs/notifications/notification-sounds).

### Time To Shelter Countdown

Here is another advanced usage for counting down (every 5 seconds) the time to shelter:
```
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
mode: queued
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
