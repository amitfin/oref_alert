const polygonCache = new Map();

class OrefAlertMap extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._layout = undefined;
    this._mapCard = null;
    this._mapCardPromise = null;
    this._areas = [];
    this._polygonLoads = new Map();
    this._updateToken = 0;
  }

  set hass(hass) {
    this._hass = hass;
    const token = ++this._updateToken;
    void this._applyHass(token).catch((error) => {
      console.error("oref-alert-map update failed", error);
    });
  }

  setConfig(_) {}

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
    mapCard.hass = this._hass;

    const areas = this._getOrefAreas();
    if (
      this._areas.length === areas.length &&
      this._areas.every((area, i) => area === areas[i])
    ) {
      return;
    }

    const layers = await this._createLayers(areas);
    if (token !== this._updateToken) {
      return;
    }

    const map = this._map;
    if (!map) {
      return;
    }

    map.layers = layers;
    this._areas = areas;
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
    const createPolygon = window.L?.polygon;
    if (!createPolygon) {
      return [];
    }

    const polygons = await Promise.all(
      areas.map((area) => this._loadPolygon(area)),
    );

    const layers = [];
    for (const [index, area] of areas.entries()) {
      const polygon = polygons[index];
      if (!polygon) {
        continue;
      }
      try {
        const layer = createPolygon(polygon, {
          color: "#f19292",
        });
        layer.bindTooltip(area);
        layers.push(layer);
      } catch (error) {
        console.warn(
          `oref-alert-map: failed creating layer for ${area}`,
          error,
        );
      }
    }
    return layers;
  }

  async _ensureMapCard() {
    if (this._mapCard) {
      return this._mapCard;
    }
    if (!this._mapCardPromise) {
      this._mapCardPromise = this._createMapCard().catch((error) => {
        this._mapCardPromise = null;
        throw error;
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
    this.appendChild(mapCard);
    return mapCard;
  }

  get _map() {
    return this._mapCard?.shadowRoot?.querySelector("ha-map") ?? null;
  }

  async _loadPolygon(area) {
    const connection = this._hass.connection;
    const subscribeMessage = connection.subscribeMessage;

    if (polygonCache.has(area)) {
      return polygonCache.get(area);
    }
    if (this._polygonLoads.has(area)) {
      return this._polygonLoads.get(area);
    }

    const loadPromise = new Promise((resolve, reject) => {
      let unsubscribePromise;
      unsubscribePromise = subscribeMessage
        .call(
          connection,
          (payload) => {
            const polygon = payload?.result ?? null;
            if (polygon) {
              polygonCache.set(area, polygon);
            }
            resolve(polygon);
            void unsubscribePromise.then((unsubscribe) => unsubscribe());
          },
          {
            type: "render_template",
            template: "{{ oref_polygon(area) }}",
            variables: { area },
          },
        )
        .catch(reject);
    });

    this._polygonLoads.set(area, loadPromise);
    try {
      return await loadPromise;
    } finally {
      this._polygonLoads.delete(area);
    }
  }
}

if (!customElements.get("oref-alert-map")) {
  customElements.define("oref-alert-map", OrefAlertMap);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: "oref-alert-map",
  name: "Oref Alert",
  description: "Map card for Oref Alert integration.",
  documentationURL: "https://github.com/amitfin/oref_alert",
});
