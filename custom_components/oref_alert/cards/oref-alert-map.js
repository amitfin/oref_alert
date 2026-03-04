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
  }

  set hass(hass) {
    this._hass = hass;
    const token = ++this._updateToken;
    void this._applyHass(token).catch((error) => {
      console.error("oref-alert-map update failed", error);
    });
  }

  setConfig(config) {
    this._config = config;
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
      this._areas.every((area, i) => area === areas[i])
    ) {
      return;
    }

    const layers = await this._createLayers(areas);
    const map = this._map;

    if (token === this._updateToken && map && layers.length === areas.length) {
      map.layers = layers;
      this._areas = areas;
    }
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
      .map((stateObj) => stateObj.attributes.friendly_name)
      .sort();
  }

  async _createLayers(areas) {
    const polygons = await this._getPolygons();
    const createPolygon = this._map?.Leaflet?.polygon;
    if (!createPolygon || !polygons) {
      return [];
    }

    const layers = [];
    for (const area of areas) {
      const layer = createPolygon(polygons[area], {
        color: "#f19292",
      });
      layer.bindTooltip(area);
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
    const mapCard = await helpers.createCardElement({
      type: "map",
      geo_location_sources: ["dummy"],
      auto_fit: true,
      fit_zones: true,
    });
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
  name: "Oref Alert",
  description: "Map card for Oref Alert integration.",
  documentationURL: "https://github.com/amitfin/oref_alert",
  preview: true,
});
