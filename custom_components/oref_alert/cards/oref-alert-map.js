function _getUiLanguage() {
  return (
    document.querySelector("home-assistant")?.hass?.language ||
    document.documentElement?.lang ||
    navigator.language ||
    "en"
  );
}

function _isHebrewLanguage() {
  return _getUiLanguage().toLowerCase().startsWith("he");
}

function _t(english, hebrew) {
  return _isHebrewLanguage() ? hebrew : english;
}

const ALERT_COLOR = "rgb(241, 146, 146)";
const PRE_ALERT_COLOR = "rgb(253, 224, 71)";
const RELOAD_GUARD_KEY = "oref-alert-map-reload-version";
const CURRENT_VERSION = new URL(import.meta.url).searchParams.get("v");

class OrefAlertMap extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._layout = undefined;
    this._mapCard = null;
    this._polygons = null;
    this._applyHassPromise = null;
    this._lastUpdated = undefined;
    this._refreshId = null;
    this._bootstrapWindow = Date.now() + 10_000;
    this._geoWatchId = undefined;
    this._locationMarker = null;
  }

  set hass(hass) {
    this._hass = hass;
    void this._applyHass();
  }

  setConfig(config) {
    this._config = config;
    if (this._hass) {
      void this._applyHass(true);
    } else {
      this._resetCardState();
    }
  }

  set layout(value) {
    this._layout = value;
    if (this._mapCard) {
      this._mapCard.layout = value;
    }
  }

  getCardSize() {
    return this._mapCard ? this._mapCard.getCardSize() : 7;
  }

  getGridOptions() {
    return this._mapCard
      ? this._mapCard.getGridOptions()
      : {
          columns: "full",
          rows: 4,
          min_columns: 6,
          min_rows: 2,
        };
  }

  async _applyHass(reset = false) {
    while (true) {
      const inflightApply = this._applyHassPromise;
      if (inflightApply) {
        await inflightApply.catch(() => {});
        if (this._applyHassPromise === inflightApply) {
          this._applyHassPromise = null;
        }
        continue;
      }

      if (reset) {
        this._resetCardState();
      }

      const applyPromise = this._performApplyHass().catch((error) => {
        if (error && typeof error === "object") {
          const { message, stack } = error;
          if (typeof message === "string" || typeof stack === "string") {
            console.error("oref-alert-map apply failed", message, stack, error);
            return;
          }
        }
        console.error("oref-alert-map apply failed", error);
      });
      const inflightPromise = applyPromise.finally(() => {
        if (this._applyHassPromise === inflightPromise) {
          this._applyHassPromise = null;
        }
      });
      this._applyHassPromise = inflightPromise;
      return applyPromise;
    }
  }

  async _performApplyHass() {
    this._startRefresh();

    const mapCard = await this._ensureMapCard();
    if (!mapCard) {
      return;
    }

    mapCard.hass = this._hass;
    this._setTileLayer();
    void this._startLocationWatch();

    if (this.firstElementChild !== mapCard) {
      this.replaceChildren(mapCard);
    }

    await this._refreshAreas();
  }

  _resetCardState() {
    this._stopRefresh();
    this._stopLocationWatch();
    this._removeLocationMarker();
    this._mapCard = null;
    this._lastUpdated = undefined;
    this._bootstrapWindow = Date.now() + 10_000;
    this.replaceChildren();
  }

  disconnectedCallback() {
    this._resetCardState();
  }

  async _getLastUpdate() {
    const result = await this._hass?.callService(
      "oref_alert",
      "last_update",
      {},
      undefined,
      false,
      true,
    );

    return {
      lastUpdated: result?.response?.last_update ?? null,
      version: result?.response?.version ?? null,
    };
  }

  async _getOrefAreas() {
    const result = await this._hass?.callService(
      "oref_alert",
      "areas_status",
      {},
      undefined,
      false,
      true,
    );

    return Object.values(result?.response || {})
      .filter(
        (area) =>
          (this._config?.show_pre_alert ?? true) || area.type === "alert",
      )
      .sort((a, b) => a.area.localeCompare(b.area));
  }

  async _refreshAreas() {
    const { lastUpdated, version } = await this._getLastUpdate();
    if (this._maybeReloadForVersion(version)) {
      return;
    }
    if (this._lastUpdated !== undefined && this._lastUpdated === lastUpdated) {
      return;
    }

    const areas = await this._getOrefAreas();
    const layers = await this._createLayers(areas);
    const map = this._map;
    if (map && layers.length === areas.length) {
      map.layers = layers;
      this._lastUpdated = lastUpdated;
    }
  }

  _maybeReloadForVersion(version) {
    const currentVersion = this._getCurrentVersion();
    if (!version || !currentVersion || version === currentVersion) {
      if (version) {
        try {
          if (window.sessionStorage.getItem(RELOAD_GUARD_KEY) === version) {
            window.sessionStorage.removeItem(RELOAD_GUARD_KEY);
          }
        } catch (_) {
          // Ignore storage issues.
        }
      }
      return false;
    }

    try {
      if (window.sessionStorage.getItem(RELOAD_GUARD_KEY) === version) {
        return true;
      }
      window.sessionStorage.setItem(RELOAD_GUARD_KEY, version);
    } catch (_) {
      // Ignore storage issues and still try to reload once.
    }

    window.location.reload();
    return true;
  }

  _getCurrentVersion() {
    return CURRENT_VERSION;
  }

  async _createLayers(areas) {
    const polygons = await this._getPolygons();
    const createPolygon = this._map?.Leaflet?.polygon;
    if (!createPolygon || !polygons) {
      return [];
    }

    const layers = [];
    for (const area of areas) {
      const layer = createPolygon(polygons[area.area], {
        color: area.type === "alert" ? ALERT_COLOR : PRE_ALERT_COLOR,
      });
      const date = new Date(area.date);
      layer.bindTooltip(
        `${area.area}<br />` +
          `${String(date.getHours()).padStart(2, "0")}:` +
          `${String(date.getMinutes()).padStart(2, "0")} ` +
          area.emoji,
      );
      layers.push(layer);
    }
    return layers;
  }

  async _ensureMapCard() {
    if (this._mapCard) {
      return this._mapCard;
    }

    try {
      this._mapCard = await this._createMapCard();
    } catch (error) {
      console.error("oref-alert-map failed to create map card", error);
      return null;
    }
    return this._mapCard;
  }

  async _createMapCard() {
    const helpers = await window.loadCardHelpers();
    const mapCard = await helpers.createCardElement(this._buildMapConfig());
    if (this._layout !== undefined) {
      mapCard.layout = this._layout;
    }
    return mapCard;
  }

  _buildMapConfig() {
    return {
      ...(this._config ?? {}),
      type: "map",
      geo_location_sources: ["dummy"],
      entities: (this._config?.show_home ? ["zone.home"] : []).concat(
        this._config?.entities ? this._config.entities : [],
      ),
      auto_fit: this._config?.auto_fit ?? true,
      fit_zones: true,
    };
  }

  get _map() {
    return this._mapCard?.shadowRoot?.querySelector("ha-map") ?? null;
  }

  async _getPolygons() {
    if (!this._polygons) {
      const polygonsTag = "oref-alert-polygons";
      await customElements.whenDefined(polygonsTag);
      const card = document.createElement(polygonsTag);
      if (card) {
        this._polygons = card.polygons;
      }
    }
    return this._polygons;
  }

  _setTileLayer() {
    let tileLayer;
    if (this._config?.tileLayer) {
      tileLayer = this._config.tileLayer;
    } else if (this._config?.hebrew_basemap ?? true) {
      tileLayer = {
        url: "https://cdnil.govmap.gov.il/xyz/heb/{z}/{x}/{y}.png",
        options: {
          minZoom: 8,
          maxZoom: 15,
          attribution: "© GovMap / המרכז למיפוי ישראל",
        },
      };
    } else {
      return;
    }

    const map = this._map;
    const leafletMap = map?.leafletMap;
    const leaflet = map?.Leaflet;
    if (!leafletMap || !leaflet) {
      return;
    }

    let found = false;
    leafletMap.eachLayer((layer) => {
      if (layer instanceof leaflet.TileLayer) {
        if (layer._url !== tileLayer.url) {
          leafletMap.removeLayer(layer);
        } else {
          found = true;
        }
      }
    });

    if (!found) {
      leaflet
        .tileLayer(tileLayer.url, tileLayer.options || {})
        .addTo(leafletMap);

      if (tileLayer.options?.maxZoom !== undefined) {
        leafletMap.setMaxZoom(tileLayer.options.maxZoom);
      }

      if (tileLayer.options?.minZoom !== undefined) {
        leafletMap.setMinZoom(tileLayer.options.minZoom);
      }
    }
  }

  _supportsLocation() {
    return (
      typeof navigator !== "undefined" &&
      !!navigator.geolocation?.getCurrentPosition &&
      !!navigator.geolocation?.watchPosition &&
      !!navigator.geolocation?.clearWatch
    );
  }

  async _startLocationWatch() {
    const showLocation = this._config?.show_location ?? true;
    if (
      !showLocation ||
      this._geoWatchId !== undefined ||
      !this._supportsLocation()
    ) {
      return;
    }

    this._geoWatchId = null;
    try {
      const denied = await this._isLocationPermissionDenied();
      if (denied) {
        this._geoWatchId = undefined;
        return;
      }

      navigator.geolocation.getCurrentPosition(
        (position) => {
          this._updateLocation(position);
        },
        (error) => {
          if (error?.code === 1) {
            this._stopLocationWatch();
          }
        },
        {
          enableHighAccuracy: false,
          maximumAge: 30_000,
          timeout: 10_000,
        },
      );

      this._geoWatchId = navigator.geolocation.watchPosition(
        (position) => {
          this._updateLocation(position);
        },
        (error) => {
          if (error?.code === 1) {
            this._stopLocationWatch();
          }
        },
        {
          enableHighAccuracy: false,
          maximumAge: 30_000,
        },
      );
    } catch (_) {
      this._geoWatchId = undefined;
    }
  }

  _stopLocationWatch() {
    if (
      this._geoWatchId !== undefined &&
      this._geoWatchId !== null &&
      this._supportsLocation()
    ) {
      navigator.geolocation.clearWatch(this._geoWatchId);
    }
    this._geoWatchId = undefined;
    this._removeLocationMarker();
  }

  async _isLocationPermissionDenied() {
    if (!navigator.permissions?.query) {
      return false;
    }

    try {
      const permission = await navigator.permissions.query({
        name: "geolocation",
      });
      return permission.state === "denied";
    } catch (_) {
      return false;
    }
  }

  _updateLocation(position) {
    this._syncLocationMarker(
      position.coords.latitude,
      position.coords.longitude,
    );
  }

  _syncLocationMarker(latitude, longitude) {
    const map = this._map;
    const leafletMap = map?.leafletMap;
    const leaflet = map?.Leaflet;
    if (!leafletMap || !leaflet?.marker || !leaflet?.divIcon) {
      return;
    }

    if (!this._locationMarker) {
      const icon = leaflet.divIcon({
        html: '<span style="display:block;width:14px;height:14px;background:#4285F4;border:3px solid #fff;border-radius:50%;box-shadow:0 0 6px rgba(66,133,244,0.6);"></span>',
        className: "",
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });
      this._locationMarker = leaflet
        .marker([latitude, longitude], {
          icon,
          interactive: false,
          zIndexOffset: 1000,
        })
        .addTo(leafletMap);
      this._locationMarker.bindTooltip(_t("Location", "מיקום"));
      return;
    }

    this._locationMarker.setLatLng([latitude, longitude]);
  }

  _removeLocationMarker() {
    const leafletMap = this._map?.leafletMap;
    if (this._locationMarker && leafletMap) {
      leafletMap.removeLayer(this._locationMarker);
    }
    this._locationMarker = null;
  }

  _startRefresh() {
    if (!this._refreshId && Date.now() < this._bootstrapWindow) {
      this._refreshId = window.setInterval(() => {
        if (!this.isConnected || Date.now() >= this._bootstrapWindow) {
          this._stopRefresh();
          return;
        }
        void this._applyHass();
      }, 1000);
    }
  }

  _stopRefresh() {
    if (this._refreshId) {
      window.clearInterval(this._refreshId);
      this._refreshId = null;
    }
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "auto_fit", selector: { boolean: {} } },
        { name: "show_home", selector: { boolean: {} } },
        { name: "hebrew_basemap", selector: { boolean: {} } },
        { name: "show_pre_alert", selector: { boolean: {} } },
        { name: "show_location", selector: { boolean: {} } },
      ],
      computeLabel: (schema) => {
        if (schema.name === "auto_fit") {
          return _t(
            "Auto fit map to active alerts",
            "התאם את המפה אוטומטית להתרעות פעילות",
          );
        }
        if (schema.name === "show_home") {
          return _t("Show home", "הצג בית");
        }
        if (schema.name === "hebrew_basemap") {
          return _t("Hebrew basemap", "מפת בסיס בעברית");
        }
        if (schema.name === "show_pre_alert") {
          return _t("Show pre-alert", "הצג הנחיות מקדימות");
        }
        if (schema.name === "show_location") {
          return _t("Show location", "הצג מיקום");
        }
        return undefined;
      },
    };
  }

  static getStubConfig() {
    return {
      auto_fit: true,
      show_home: false,
      hebrew_basemap: true,
      show_pre_alert: true,
      show_location: true,
    };
  }
}

const elementTag = "oref-alert-map";
customElements.define(elementTag, OrefAlertMap);
customElements.whenDefined("home-assistant").then(() => {
  if (!customElements.get(elementTag)) {
    customElements.define(elementTag, OrefAlertMap);
  }
});
window.customCards = window.customCards || [];
window.customCards.push({
  type: elementTag,
  name: _t("Oref Alert", "התרעות פיקוד העורף"),
  description: _t(
    "Map card for Oref Alert integration.",
    "כרטיס מפה לאינטגרציית פיקוד העורף.",
  ),
  documentationURL: "https://github.com/amitfin/oref_alert",
  preview: true,
  configurable: true,
});
