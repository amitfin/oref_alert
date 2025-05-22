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

The setup identifies the area according to the [Home location in the Zones settings](https://my.home-assistant.io/redirect/zones/) (the latitude and longitude coordinates). If the detection fails, the user is asked to select the area manually.

Once the component is installed, it's possible to control additional parameters using the Configure dialog which can be accessed via this My button:

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=oref_alert)

There are 5 configuration fields:
1. Selected areas: list of areas to monitor. It's also possible to select a district (מחוז) and all-areas (כל האזורים) for cities with sub-areas.
2. Active duration of an alert: this is the alert's active time period (in minutes). The default is 10 minutes.
3. Update frequency: the time to wait between updates of the sensor (in seconds). The default is 2 seconds.
4. On icon: the icon to be used when there are active alerts in one of the selected areas. This is the icon which is displayed when the state of the binary sensor is "on".
5. Off icon: the icon to  be used when the state of the binary sensor is "off".

<kbd><img src="https://github.com/amitfin/oref_alert/assets/19599059/2422d891-15f5-4393-b713-59d09f20c308" width="400"></kbd>

## All Areas Sensor

`binary_sensor.oref_alert_all_areas` is an additional sensor monitoring any active alert in the country. The sensor is `on` when there is one or more active alerts in Israel.

## Additional Sensors

It's possible to create additional sensors using the service `oref_alert.add_sensor`. The service can be accessed via this My button:

[![Open your Home Assistant instance and show your service developer tools with a specific service selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.add_sensor)

The selected areas of an additional sensor can be different (non overlapping) than the primary sensor. Additional sensors can be re-added (with the same name) for overriding their configuration (there is no edit page).

The service `oref_alert.remove_sensor` can be used for deleting an additional sensor. The service can be accessed via this My button:

[![Open your Home Assistant instance and show your service developer tools with a specific service selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.remove_sensor)

Note: additional sensors created before v2.2.0 use a different implementation. It's better to delete such entities and to create new sensors using the new functionality (old sensors are not broken and can be used).

## Additional Attributes

All sensors have the following extra attributes:
1. `Areas`: the list of areas provided by the user.
2. `Alert active duration`: as configured by the user.
3. `Selected areas active alerts`: when the sensor is `on`, the alerts are listed here.
4. `Selected areas alerts`: active and inactive alerts in the selected areas.
5. `Country active alerts`: all active alerts in Israel.
6. `Country alerts`: all alerts in Israel.

## Time To Shelter Sensors

The integration creates an additional set of sensors which monitor the time to shelter for a specific area. The ID of the entity is similar to the corresponding binary sensor, with the suffix of `_time_to_shelter`. For example, `sensor.oref_alert_time_to_shelter`. When there is a new alert in the area, the `state` of the sensor is set according to the instructions of Pikud Haoref for the selected area (e.g. 90 seconds in the middle of Israel). The `state` of the sensor decrements as time passes, and it becomes `unknown` once it reaches -60 seconds (one minute past due). The sensor has the following extra attributes:
1. `Area`: the name of the area.
2. `Time to shelter`: as provided by Pikud Haoref for the selected area (constant value).
3. `Alert`: the active alert (when there is such).

*Note: this sensor is not created when the configuration contains multiple areas or groups (e.g. cities with multiple areas or districts). It's possible in such a case to create an additional sensor configuration for the specific area of interest by using the service `oref_alert.add_sensor`.*

## Alert End Time Sensors

The integration creates an additional set of sensors which monitor the time to the end of the alert for a specific area. The ID of the entity is similar to the corresponding binary sensor, with the suffix of `_end_time`. For example, `sensor.oref_alert_end_time`. When there is a new alert in the area, the `state` of the sensor is set according to the `Alert active duration` as configured by the user (default is 10 minutes). The `state` of the sensor decrements as time passes, and it becomes `unknown` once the alert is `off`. The sensor has the following extra attributes:
1. `Area`: the name of the area.
2. `Alert active duration`: as configured by the user.
3. `Alert`: the active alert (when there is such).

*Note: this sensor is not created when the configuration contains multiple areas or groups (e.g. cities with multiple areas or districts). It's possible in such a case to create an additional sensor configuration for the specific area of interest by using the service `oref_alert.add_sensor`.*

## Preemptive Update Binary Sensors

The integration creates an additional set of binary sensors which turns on when there is a preemptive warning for a potential future alert. The ID of the entity is similar to the corresponding binary sensor, with the suffix of `_preemptive_update`. For example, `binary_sensor.oref_alert_preemptive_update`. The entity's state turns `off` when the corresponding binary sensor turns `on` (i.e. a regular alert has been activated). If the warning is not converted to a real alert, the state turns `off` after the user-configured active period (10 minutes by default). The entity has the following extra attributes:
1. `Areas`: the name of the areas.
2. `Alert active duration`: as configured by the user.
3. `Selected areas active alerts`: active warnings.

A [synthetic alert](#synthetic-alert) with category `13` can be used to turn `on` this entity for testing purposes.

## Geo Location Entities

Geo-location entities are created for every active alert in Israel (regardless of the selected areas). These entities exist while the corresponding alert is active (10 minutes by default). The state of the entity is the distance in kilometers from HA home's coordinates. In addition, each entity has the following attributes:
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
```

In the [Mobile Notifications: Detailed Alerts](#detailed-alerts) section there is an example for usage of this event.

## Synthetic Alert

Synthetic alerts are useful for testing purposes. The service `oref_alert.synthetic_alert` can be used to create a synthetic alert. The service can be accessed via this My button:

[![Open your Home Assistant instance and show your service developer tools with a specific service selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.synthetic_alert)

*Note: a synthetic alert is an additional alert. It doesn't override or hide any other alert. A synthetic alert disappears after the amount of seconds supplied to the custom service. This is different from a regular alert which disappears only after 24 hours.*

## Template Functions

The integration adds the following template helper functions:

### `oref_district`

Gets an area name and returns its district. If no mapping is found, the return value is the input area name. Can be used also as a filter.

`{{ oref_district('פתח תקווה') == 'דן' }}`

`{{ ['area name'] | map('oref_district') }}`

### `oref_icon`

Gets a category (int) and returns the corresponding MDI icon (has "mdi:" prefix). If no mapping is found, the return value is "mdi:alert". Can be used also as a filter.

`{{ oref_icon(1) == 'mdi:rocket-launch' }}`

`{{ 2 | oref_icon == 'mdi:airplane-alert' }}`

### `oref_emoji`

Gets a category (int) and returns the corresponding emoji. If no mapping is found, the return value is "🚨". Can be used also as a filter.

`{{ oref_emoji(1) == '🚀' }}`

`{{ [2] | map('oref_emoji') | list == ['✈️'] }}`

### `oref_distance`

Gets an area name and returns the distance (km) from home's coordinates as configured in the system. If the area name is not found, the return value is -1. Can be used also as a filter.

`{{ oref_distance('פתח תקווה') }}`

`{{ ['area name'] | map('oref_distance') }}`

### `oref_test_distance`

Gets an area name and a distance (km). Returns True if the distance from home's coordinates is less than or equals to the distance . If the area name is not found, the return value is False. Can be used also as a test.

`{{ oref_test_distance('area name', 5)}}`

`{{ ['area name'] | select('oref_test_distance', 5) }}`

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

### Presenting Active Alerts in Israel

Here is a [markdown card](https://www.home-assistant.io/dashboards/markdown/) for presenting all active alerts sorted by their distance from HA's home coordinates (the list of categories is based on [this file](https://www.oref.org.il/alerts/alertCategories.json)):

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

#### Preemptive Updates

Here is an automation rule for getting mobile notifications for preemptive updates:

```
alias: Oref Alert Preemptive Updates
id: oref_alert_preemptive_updates
triggers:
  - trigger: state
    entity_id: binary_sensor.oref_alert_all_areas_preemptive_update
    attribute: country_active_alerts
actions:
  - variables:
      current: "{{ trigger.to_state.attributes.country_active_alerts | map(attribute='data') | map('oref_district') | unique | list }}"
      previous: "{{ trigger.from_state.attributes.country_active_alerts | map(attribute='data') | map('oref_district') | unique | list }}"
      districts: "{{ current | difference(previous) | sort | list }}"
      districts_per_push: "{{ (90 / (districts | map('length') | average(0) | add(2))) | int }}"
  - repeat:
      while:
        - condition: template
          value_template: "{{ districts | length > 0 }}"
      sequence:
        - action: notify.mobile_app_amits_iphone
          data:
            title: מבזק פיקוד העורף
            message: "בעקבות זיהוי שיגורים לעבר ישראל, יתכן ויפעלו התרעות בדקות הקרובות במרחבים הבאים: {{ districts[:districts_per_push] | join(', ') }}"
        - variables:
            districts: "{{ districts[districts_per_push:] }}"
mode: queued
```

<img width="400" src="https://github.com/user-attachments/assets/60b6ff3a-0d3d-4b76-bf60-3ea389e3a5c1">

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

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Acknowledgements

- Thanks to [Gugulator](https://github.com/Gugulator) for the Russian translation as well as many great ideas during our brainstorming sessions.
