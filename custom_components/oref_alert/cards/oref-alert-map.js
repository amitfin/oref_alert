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

class OrefAlertMap extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._layout = undefined;
    this._mapCard = null;
    this._mapCardPromise = null;
    this._polygons = null;
    this._hassUpdateToken = 0;
    this._lastUpdated = undefined;
    this._refreshId = null;
    this._refreshDeadline = Date.now() + 60_000;
  }

  set hass(hass) {
    this._hass = hass;
    void this._applyHass(++this._hassUpdateToken).catch((error) => {
      console.error("oref-alert-map hass apply failed", error);
    });
  }

  setConfig(config) {
    this._config = config;

    this._stopRefresh();
    this._mapCard = null;
    this._mapCardPromise = null;
    this._lastUpdated = undefined;
    this._refreshDeadline = Date.now() + 60_000;
    this.replaceChildren();

    if (this._hass) {
      void this._applyHass(++this._hassUpdateToken).catch((error) => {
        console.error("oref-alert-map setConfig apply failed", error);
      });
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

  async _applyHass(hassToken) {
    this._checkRefresh();

    if (hassToken !== this._hassUpdateToken) {
      return;
    }

    const mapCard = await this._ensureMapCard(hassToken);
    if (!mapCard) {
      return;
    }

    if (hassToken !== this._hassUpdateToken) {
      return;
    }

    mapCard.hass = this._hass;
    this._setTileLayer();

    if (this.firstElementChild !== mapCard) {
      this.replaceChildren(mapCard);
    }

    await this._refreshAreas(hassToken);

    this._checkRefresh();
  }

  disconnectedCallback() {
    this._stopRefresh();
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

    return result?.response?.last_update ?? null;
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
      .filter((area) => this._config?.show_pre_alert || area.type === "alert")
      .sort((a, b) => a.area.localeCompare(b.area));
  }

  async _refreshAreas(hassToken) {
    const lastUpdated = await this._getLastUpdate();
    if (this._lastUpdated !== undefined && this._lastUpdated === lastUpdated) {
      return;
    }

    const areas = await this._getOrefAreas();
    const layers = await this._createLayers(areas);
    const map = this._map;
    if (
      hassToken === this._hassUpdateToken &&
      map &&
      layers.length === areas.length
    ) {
      map.layers = layers;
      this._lastUpdated = lastUpdated;
    }
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

  async _ensureMapCard(hassToken) {
    if (this._mapCard) {
      return this._mapCard;
    }
    if (!this._mapCardPromise) {
      this._mapCardPromise = this._createMapCard().catch((error) => {
        console.error("oref-alert-map failed to create map card", error);
        this._mapCardPromise = null;
      });
    }
    const mapCardPromise = this._mapCardPromise;
    const mapCard = await mapCardPromise;

    if (this._mapCardPromise === mapCardPromise) {
      this._mapCardPromise = null;
    }

    if (!mapCard) {
      return null;
    }

    if (hassToken !== this._hassUpdateToken) {
      return null;
    }

    this._mapCard = mapCard;
    return mapCard;
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
    let tileLayer;
    if (this._config?.tileLayer) {
      tileLayer = this._config.tileLayer;
    } else if (this._config?.hebrew_basemap) {
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
    }
  }

  _checkRefresh() {
    if (this._map) {
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
          this._map ||
          Date.now() >= this._refreshDeadline
        ) {
          this._stopRefresh();
          return;
        }
        void this._applyHass(++this._hassUpdateToken).catch((error) => {
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
        { name: "hebrew_basemap", selector: { boolean: {} } },
        { name: "show_pre_alert", selector: { boolean: {} } },
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
        return undefined;
      },
    };
  }

  static getStubConfig() {
    return {
      auto_fit: true,
      show_home: false,
      hebrew_basemap: true,
      show_pre_alert: false,
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
