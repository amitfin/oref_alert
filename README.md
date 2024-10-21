# Oref Alert

[![HACS Badge](https://img.shields.io/badge/HACS-Default-31A9F4.svg?style=for-the-badge)](https://github.com/hacs/integration)

[![GitHub Release](https://img.shields.io/github/release/amitfin/oref_alert.svg?style=for-the-badge&color=blue)](https://github.com/amitfin/oref_alert/releases)

![Download](https://img.shields.io/github/downloads/amitfin/oref_alert/total.svg?style=for-the-badge&color=blue) ![Analytics](https://img.shields.io/badge/dynamic/json?style=for-the-badge&color=blue&label=Analytics&suffix=%20Installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.oref_alert.total)

![Project Maintenance](https://img.shields.io/badge/maintainer-Amit%20Finkelstein-blue.svg?style=for-the-badge)

***Hebrew demos of the installation, configuration and usage can be found here: [part1](https://youtu.be/uT77BKvOSyw), [part2](https://youtu.be/rFkKvkv3JuQ), [part3](https://youtu.be/xZpMudcdZv8). A blog post with Hebrew instructions can be found [here](https://homeusmart.blogspot.com/2023/10/haoref-heb.html). A blog post with Russian instructions can be found [here](https://homeusmart.blogspot.com/2023/10/haidf.html).***

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

## Geo Location Entities

Geo-location entities are created for every active alert in Israel (regardless of the selected areas). These entities exist while the corresponding alert is active (10 minutes by default). The [map card](https://www.home-assistant.io/dashboards/map) can be used to present the entities on a map. `oref_alert` should be added to [geo_location_sources](https://www.home-assistant.io/dashboards/map/#geo_location_sources), and [auto_fit](https://www.home-assistant.io/dashboards/map/#auto_fit) should be set to true:

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

## Synthetic Alert

Synthetic alerts are useful for testing purposes. The service `oref_alert.synthetic_alert` can be used to create a synthetic alert. The service can be accessed via this My button:

[![Open your Home Assistant instance and show your service developer tools with a specific service selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.synthetic_alert)

*Note: a synthetic alert is an additional alert. It doesn't override or hide any other alert. A synthetic alert disappears after the amount of seconds supplied to the custom service. This is different from a regular alert which disappears only after 24 hours.*

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
  {% set icons = {
    1: "rocket-launch",
    2: "airplane-alert",
    3: "chemical-weapon",
    4: "alert",
    5: "firework",
    6: "firework",
    7: "earth",
    8: "earth",
    9: "nuke",
    10: "shield-home",
    11: "home-flood",
    12: "biohazard",
    13: "update",
    14: "flash-alert",
    15: "alert-circle-check",
    16: "alert-circle-check",
    17: "alert-circle-check",
    18: "alert-circle-check",
    19: "alert-circle-check",
    20: "alert-circle-check",
    21: "alert-circle-check",
    22: "alert-circle-check",
  } %}
  {% for alert in states.geo_location |
     selectattr('entity_id', 'in', integration_entities('oref_alert')) |
     sort(attribute='attributes.home_distance') %}
    <p>
      <font color="red"><ha-icon icon="mdi:{{ icons.get(alert.attributes.category, 'alert') }}"></ha-icon></font>
      {{ alert.name }}
      [{{ alert.home_distance | int }} ק״מ]
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

<kbd>![image](https://github.com/user-attachments/assets/bc1830dc-07d2-4a3b-a5c4-c08d1e620a79)</kbd>

### Mobile Notifications

Here is an advanced usage for getting mobile notifications on any alert in the country:
```
alias: Oref Alert Country Notifications
id: oref_alert_country_notifications
trigger:
  - platform: state
    entity_id: binary_sensor.oref_alert
    attribute: country_active_alerts
action:
  - variables:
      current: "{{ state_attr('binary_sensor.oref_alert', 'country_active_alerts') | map(attribute='data') | list }}"
      previous: "{{ trigger.from_state.attributes.country_active_alerts | map(attribute='data') | list }}"
      alerts: "{{ current | reject('in', previous) | unique | sort | list }}"
  - condition: "{{ alerts | length > 0 }}"
  - service: notify.mobile_app_amits_iphone
    data:
      message: "התרעות פיקוד העורף: {{ alerts | join(' | ') }}"
mode: queued
```

### Time To Shelter Countdown

Here is another advanced usage for counting down (every 5 seconds) the time to shelter:
```
alias: Oref Alert Time To Shelter Countdown
id: oref_alert_time_to_shelter_countdown
trigger:
  - platform: state
    entity_id: sensor.oref_alert_time_to_shelter
action:
  - variables:
      time_to_shelter: "{{ states('sensor.oref_alert_time_to_shelter') | int(-1) }}"
  - condition: "{{ time_to_shelter >= 0 and time_to_shelter % 5 == 0}}"
  - service: tts.google_translate_say
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
