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

class OrefAlertMap extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._layout = undefined;
    this._mapCard = null;
    this._mapCardPromise = null;
    this._areas = [];
    this._polygons = null;
    this._updateToken = 0;
    this._refreshId = null;
    this._refreshDeadline = Date.now() + 60_000;
  }

  set hass(hass) {
    this._hass = hass;
    void this._applyHass(++this._updateToken).catch((error) => {
      console.error("oref-alert-map update failed", error);
    });
  }

  setConfig(config) {
    const previousMapConfig = this._buildMapConfig();
    this._config = config;
    const newMapConfig = this._buildMapConfig();
    if (
      this._mapCard &&
      JSON.stringify(previousMapConfig) !== JSON.stringify(newMapConfig)
    ) {
      this._mapCard.setConfig(newMapConfig);
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

  async _applyHass(token) {
    this._checkRefresh();

    if (token !== this._updateToken) {
      return;
    }

    const mapCard = await this._ensureMapCard();
    if (!mapCard) {
      return;
    }
    mapCard.hass = this._hass;
    this._setTileLayer();

    const areas = this._getOrefAreas();
    if (
      this._areas.length === areas.length &&
      this._areas.every((area, i) =>
        Object.keys(area).every((key) => area[key] === areas[i][key]),
      )
    ) {
      return;
    }

    const layers = await this._createLayers(areas);
    const map = this._map;

    if (token === this._updateToken && map && layers.length === areas.length) {
      map.layers = layers;
      this._areas = areas;
      this._checkRefresh();
    }
  }

  disconnectedCallback() {
    this._stopRefresh();
  }

  _getOrefAreas() {
    const states = this._hass?.states;
    if (!states) {
      return [];
    }
    return Object.values(states)
      .filter(
        (stateObj) =>
          stateObj.entity_id.startsWith("geo_location.") &&
          stateObj.attributes?.source === "oref_alert",
      )
      .map((stateObj) => stateObj.attributes)
      .sort((a, b) => a.friendly_name.localeCompare(b.friendly_name));
  }

  async _createLayers(areas) {
    const polygons = await this._getPolygons();
    const createPolygon = this._map?.Leaflet?.polygon;
    if (!createPolygon || !polygons) {
      return [];
    }

    const layers = [];
    for (const area of areas) {
      const layer = createPolygon(polygons[area.friendly_name], {
        color: "#f19292",
      });
      const date = new Date(area.date);
      layer.bindTooltip(
        `${area.friendly_name}<br />` +
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
    if (!this._mapCardPromise) {
      this._mapCardPromise = this._createMapCard().catch((error) => {
        console.error("oref-alert-map failed to create map card", error);
        this._mapCardPromise = null;
      });
    }
    return this._mapCardPromise;
  }

  async _createMapCard() {
    const helpers = await window.loadCardHelpers();
    const mapCard = await helpers.createCardElement(this._buildMapConfig());
    if (this._hass) {
      mapCard.hass = this._hass;
    }
    if (this._layout !== undefined) {
      mapCard.layout = this._layout;
    }
    this._mapCard = mapCard;
    this._setTileLayer();
    this.replaceChildren(mapCard);
    return mapCard;
  }

  _buildMapConfig() {
    return {
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

  async _setTileLayer() {
    if (!this._config?.tileLayer) {
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
        if (layer._url !== this._config.tileLayer.url) {
          leafletMap.removeLayer(layer);
        } else {
          found = true;
        }
      }
    });

    if (!found) {
      leaflet
        .tileLayer(
          this._config.tileLayer.url,
          this._config.tileLayer.options || {},
        )
        .addTo(leafletMap);
    }
  }

  _checkRefresh() {
    if (this._areas.length > 0) {
      this._stopRefresh();
      return;
    }

    if (Date.now() >= this._refreshDeadline) {
      this._stopRefresh();
      return;
    }

    this._startRefresh();
  }

  _startRefresh() {
    if (!this._refreshId) {
      this._refreshId = window.setInterval(() => {
        if (
          !this.isConnected ||
          this._areas.length > 0 ||
          Date.now() >= this._refreshDeadline
        ) {
          this._stopRefresh();
          return;
        }
        const token = ++this._updateToken;
        void this._applyHass(token).catch((error) => {
          console.error("oref-alert-map refresh retry failed", error);
        });
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
        return undefined;
      },
    };
  }

  static getStubConfig() {
    return {
      auto_fit: true,
      show_home: false,
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
