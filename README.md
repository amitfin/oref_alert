# Oref Alert

[![HACS Badge](https://img.shields.io/badge/HACS-Default-31A9F4.svg?style=for-the-badge)](https://github.com/hacs/integration)

[![GitHub Release](https://img.shields.io/github/release/amitfin/oref_alert.svg?style=for-the-badge&color=blue)](https://github.com/amitfin/oref_alert/releases)

![Download](https://img.shields.io/github/downloads/amitfin/oref_alert/total.svg?style=for-the-badge&color=blue) ![Analytics](https://img.shields.io/badge/dynamic/json?style=for-the-badge&color=blue&label=Analytics&suffix=%20Installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.oref_alert.total)

![Project Maintenance](https://img.shields.io/badge/maintainer-Amit%20Finkelstein-blue.svg?style=for-the-badge)

***A demo (in Hebrew) of the installation, configuration and usage can be found [here](https://youtu.be/uT77BKvOSyw).***

The integrartion provides `binary_sensor.oref_alert` which truns on when an alert is reported by the [Israeli National Emergency Portal](https://www.oref.org.il//12481-he/Pakar.aspx) (Pikud Haoref). The sensor monitors the alerts in the user selected areas. An alert is considered active for a certain period of time as configured by the user (10 minutes by default).
The integraion is installed and configured via the user interface. There is no YAML or templates involved.

## Install

[HACS](https://hacs.xyz/) is the preferred and easier way to install the component. When HACS is installed, the integration can be installed using this My button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=amitfin&repository=oref_alert&category=integration)

Otherwise, download `oref_alert.zip` from the [latest release](https://github.com/amitfin/oref_alert/releases), extract and copy the content under `custom_components` directory.

Home Assistant restart is required once the integration files are copied (either by HACS or manually).

The integration should also be added to the configuration. This can be done via this My button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=oref_alert)

There are 5 configuration fields, but only the first one doesn't have a good default:
1. Selected areas: list of areas to monitor. It's also possible to select a district (מחוז) and all-areas (כל האזורים) for cities with sub-areas.
2. Max age of an alert: this is the alert's active time period (in minutes). The default is 10 minutes.
3. Update frequency: the time to wait between updates of the sensor (in seconds). The default is 5 seconds.
4. On icon: the icon to be used when there are active alerts in one of the selected areas. This is the icon which is displayed when the state of the binary sensor is "on".
5. Off icon: the icon to  be used when the state of the binary sensor is "off".

<kbd><img src="https://github.com/amitfin/oref_alert/assets/19599059/2422d891-15f5-4393-b713-59d09f20c308" width="400"></kbd>

## Additional Sensors

It's possible to create additional sensors using the service `oref_alert.add_sensor`. The service can be accessed via this My button:

[![Open your Home Assistant instance and show your service developer tools with a specific service selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.add_sensor)

The selected areas of an additional sensor can be different (non overlapping) than the primary sensor. Additional sensors can be re-added (with the same name) for overriding their configuration (there is no edit page).

The service `oref_alert.remove_sensor` can be used for deleting an additioanl sensor. The service can be accessed via this My button:

[![Open your Home Assistant instance and show your service developer tools with a specific service selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=oref_alert.remove_sensor)

Note: additional sensros created before v2.2.0 use a different implementaiton. It's better to delete such entities and to create new sensors using the new functionality (old sensors are not broken and can be used).

## Additional Attributes

All sensors have the following extra attributes:
1. `Areas`: the list of areas provided by the user.
2. `Alert max age`: as configured by the user.
3. `Selected areas active alerts`: when the sensor is `on`, the alerts are listed here. 
4. `Selected areas alerts`: active and inactive alerts in the selected areas.
5. `Country active alerts`: all active alerts in Israel.
6. `Country alerts`: all alerts in Israel.

## Time To Shelter Sensors

The integration creates an additional set of non-binary sensors holding the time to shelter. The initial `state` of the sensor is according to the instructions of Pikud Haoref for the selected area (e.g. 90 seconds in the middle of Israel). The `state` of the sensor decrements as time passes, and it becomes `unknown` once it reaches -60 seconds (one minute past due). The sensor has the following extra attributes:
1. `Area`: the name of the area.
2. `Time to shelter`: as provided by Pikud Haoref for the selected area (constant value).
3. `Alert`: the active alert (when there is such).

*Note: this sensor is not created when the configuration contains multiple areas or groups (e.g. cities with multiple areas or districts). It's possible in such a case to create an additional sensor configuration for the specific area of interest.*

## Usages

The basic usage is to trigger an automation rule when the binary sensor is turning `on`. Some ideas for the `actions` section can be: play a song (less stressful), open the lights and TV in the shelter, etc'. It's also possible to trigger an alert when the sensor is turning `off` for getting an indication when it's safe to get out of the shelter.

Here is an advanced usage for getting mobile notifications on any alert in the country (can also be created via the UI):
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

And here is another advanced usage for counting down (every 5 seconds) the time to shelter:
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
