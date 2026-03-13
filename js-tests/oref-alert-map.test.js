import { afterEach, describe, expect, test, vi } from "vitest";

async function ensureDefined() {
  if (!customElements.get("oref-alert-map")) {
    await import("../custom_components/oref_alert/cards/oref-alert-map.js");
  }
}

function waitForTasks() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function createMapCardWithInnerMap() {
  const mapCard = document.createElement("div");
  const shadow = mapCard.attachShadow({ mode: "open" });
  const innerMap = document.createElement("ha-map");
  shadow.appendChild(innerMap);
  mapCard.getCardSize = vi.fn().mockReturnValue(3);
  mapCard.getGridOptions = vi.fn().mockReturnValue({
    columns: 12,
    rows: 6,
    min_columns: 6,
    min_rows: 3,
  });
  return { mapCard, innerMap };
}

afterEach(() => {
  document.body.innerHTML = "";
  delete window.loadCardHelpers;
  delete window.L;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("oref-alert-map", () => {
  test("registers custom element and metadata", async () => {
    vi.resetModules();
    delete window.customCards;
    const defineSpy = vi.spyOn(customElements, "define");

    await import("../custom_components/oref_alert/cards/oref-alert-map.js");

    expect(defineSpy).toHaveBeenCalledWith(
      "oref-alert-map",
      expect.any(Function),
    );
    expect(customElements.get("oref-alert-map")).toBeDefined();
    expect(
      window.customCards.some((card) => card.type === "oref-alert-map"),
    ).toBe(true);
  });

  test("creates map card and wires hass/layout getters", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    expect(el._map).toBeNull();
    const { mapCard } = createMapCardWithInnerMap();
    const hassSetter = vi.fn();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(value) {
        hassSetter(value);
      },
    });

    const createCardElement = vi.fn().mockResolvedValue(mapCard);
    window.loadCardHelpers = vi.fn().mockResolvedValue({ createCardElement });

    el.setConfig({ ignored: true });
    el.layout = "panel";
    el._hass = { states: {}, connection: {} };

    expect(el.getCardSize()).toBe(7);
    expect(el.getGridOptions()).toEqual({
      columns: "full",
      rows: 4,
      min_columns: 6,
      min_rows: 2,
    });

    const created = await el._createMapCard();
    expect(created).toBe(mapCard);
    expect(hassSetter).toHaveBeenCalledWith(el._hass);
    expect(mapCard.layout).toBe("panel");
    expect(el._map).toBe(mapCard.shadowRoot.querySelector("ha-map"));

    expect(el.getCardSize()).toBe(3);
    expect(el.getGridOptions()).toEqual({
      columns: 12,
      rows: 6,
      min_columns: 6,
      min_rows: 3,
    });

    el.layout = "masonry";
    expect(mapCard.layout).toBe("masonry");
  });

  test("ensureMapCard reuses in-flight promise and retries after failure", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    const createCardElement = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce(mapCard);
    window.loadCardHelpers = vi.fn().mockResolvedValue({ createCardElement });
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const p1 = el._ensureMapCard();
    const p2 = el._ensureMapCard();
    await Promise.all([p1, p2]);

    expect(createCardElement).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map failed to create map card",
      expect.any(Error),
    );
    expect(el._mapCardPromise).toBeNull();

    await expect(el._ensureMapCard()).resolves.toBe(mapCard);
    expect(createCardElement).toHaveBeenCalledTimes(2);
    await expect(el._ensureMapCard()).resolves.toBe(mapCard);
    expect(createCardElement).toHaveBeenCalledTimes(2);
  });

  test("getPolygons caches after success and handles unresolved/missing polygons", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");

    if (!customElements.get("oref-alert-polygons")) {
      customElements.define(
        "oref-alert-polygons",
        class extends HTMLElement {
          constructor() {
            super();
            this.polygons = { "Area A": [[1, 1]] };
          }
        },
      );
    }

    const el = new Card();
    await expect(el._getPolygons()).resolves.toEqual({ "Area A": [[1, 1]] });
    const createSpy = vi.spyOn(document, "createElement");
    await expect(el._getPolygons()).resolves.toEqual({ "Area A": [[1, 1]] });
    expect(createSpy).not.toHaveBeenCalled();

    const waitingEl = new Card();
    const whenDefinedSpy = vi
      .spyOn(customElements, "whenDefined")
      .mockImplementation(() => new Promise(() => {}));

    let settled = false;
    void waitingEl._getPolygons().then(() => {
      settled = true;
    });
    await waitForTasks();
    expect(settled).toBe(false);
    expect(whenDefinedSpy).toHaveBeenCalledWith("oref-alert-polygons");

    const nullCreateEl = new Card();
    whenDefinedSpy.mockResolvedValue(undefined);
    const createElementSpy = vi
      .spyOn(document, "createElement")
      .mockReturnValue(null);
    await expect(nullCreateEl._getPolygons()).resolves.toBeNull();
    createElementSpy.mockRestore();
  });

  test("createLayers handles missing dependencies and creates layers", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;

    vi.spyOn(el, "_getPolygons").mockResolvedValue({ "Area A": [[1, 1]] });
    await expect(
      el._createLayers([
        { friendly_name: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
      ]),
    ).resolves.toEqual([]);

    innerMap.Leaflet = { polygon: vi.fn() };
    el._getPolygons.mockResolvedValueOnce(null);
    await expect(
      el._createLayers([
        { friendly_name: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
      ]),
    ).resolves.toEqual([]);

    const created = [];
    innerMap.Leaflet.polygon = vi.fn().mockImplementation((points, opts) => {
      const layer = { points, opts, bindTooltip: vi.fn() };
      created.push(layer);
      return layer;
    });
    el._getPolygons.mockResolvedValueOnce({
      "Area A": [
        [1, 1],
        [1, 2],
      ],
      "Area B": [
        [2, 1],
        [2, 2],
      ],
    });

    const layers = await el._createLayers([
      { friendly_name: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
      { friendly_name: "Area B", date: "2026-03-13T11:42:00Z", emoji: "✈️" },
    ]);
    expect(layers).toHaveLength(2);
    expect(innerMap.Leaflet.polygon).toHaveBeenNthCalledWith(
      1,
      [
        [1, 1],
        [1, 2],
      ],
      { color: "#f19292" },
    );
    expect(innerMap.Leaflet.polygon).toHaveBeenNthCalledWith(
      2,
      [
        [2, 1],
        [2, 2],
      ],
      { color: "#f19292" },
    );
    expect(created[0].bindTooltip).toHaveBeenCalledWith("Area A<br />08:05 🚀");
    expect(created[1].bindTooltip).toHaveBeenCalledWith("Area B<br />11:42 ✈️");
  });

  test("applyHass handles stale token, unchanged areas, and map assignment", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });

    el._hass = null;
    expect(el._getOrefAreas()).toEqual([]);

    const states = {
      "geo_location.b": {
        entity_id: "geo_location.b",
        attributes: {
          source: "oref_alert",
          friendly_name: "Area B",
          date: "2026-03-13T11:42:00Z",
          emoji: "✈️",
        },
      },
      "geo_location.a": {
        entity_id: "geo_location.a",
        attributes: {
          source: "oref_alert",
          friendly_name: "Area A",
          date: "2026-03-13T08:05:00Z",
          emoji: "🚀",
        },
      },
      "geo_location.x": {
        entity_id: "geo_location.x",
        attributes: { source: "other", friendly_name: "Area X" },
      },
      "sensor.y": {
        entity_id: "sensor.y",
        attributes: { source: "oref_alert", friendly_name: "Area Y" },
      },
    };

    el._hass = { states, connection: {} };
    expect(el._getOrefAreas()).toEqual([
      {
        source: "oref_alert",
        friendly_name: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
      },
      {
        source: "oref_alert",
        friendly_name: "Area B",
        date: "2026-03-13T11:42:00Z",
        emoji: "✈️",
      },
    ]);

    el._updateToken = 2;
    await el._applyHass(1);

    vi.spyOn(el, "_ensureMapCard").mockResolvedValue(null);
    await el._applyHass(2);

    el._mapCard = mapCard;
    el._ensureMapCard.mockResolvedValue(mapCard);
    el._areas = [
      {
        source: "oref_alert",
        friendly_name: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
      },
      {
        source: "oref_alert",
        friendly_name: "Area B",
        date: "2026-03-13T11:42:00Z",
        emoji: "✈️",
      },
    ];
    const createLayersSpy = vi.spyOn(el, "_createLayers");
    await el._applyHass(2);
    expect(createLayersSpy).not.toHaveBeenCalled();
    expect(innerMap.layers).toBeUndefined();

    el._areas = [];
    createLayersSpy.mockImplementation(async () => {
      el._updateToken = 3;
      return [{ id: 1 }];
    });
    el._updateToken = 2;
    await el._applyHass(2);
    expect(innerMap.layers).toBeUndefined();

    createLayersSpy.mockResolvedValue([{ id: 2 }, { id: 3 }]);
    el._updateToken = 4;
    await el._applyHass(4);
    expect(innerMap.layers).toEqual([{ id: 2 }, { id: 3 }]);
    expect(el._areas).toEqual([
      {
        source: "oref_alert",
        friendly_name: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
      },
      {
        source: "oref_alert",
        friendly_name: "Area B",
        date: "2026-03-13T11:42:00Z",
        emoji: "✈️",
      },
    ]);
  });

  test("setTileLayer updates tile layers and honors options defaults", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;

    class TileLayer {}
    const matchingLayer = new TileLayer();
    matchingLayer._url = "https://tiles.example/{z}/{x}/{y}.png";
    const oldLayer = new TileLayer();
    oldLayer._url = "https://old.example/{z}/{x}/{y}.png";
    const nonTileLayer = {};
    const removeLayer = vi.fn();
    const eachLayer = vi.fn((cb) => {
      cb(nonTileLayer);
      cb(oldLayer);
      cb(matchingLayer);
    });
    const leafletMap = { eachLayer, removeLayer };
    const addTo = vi.fn();
    const tileLayerFactory = vi.fn(() => ({ addTo }));
    innerMap.leafletMap = leafletMap;
    innerMap.Leaflet = {
      TileLayer,
      tileLayer: tileLayerFactory,
    };

    el._config = {
      tileLayer: {
        url: "https://tiles.example/{z}/{x}/{y}.png",
        options: { maxZoom: 12 },
      },
    };
    await el._setTileLayer();
    expect(removeLayer).toHaveBeenCalledTimes(1);
    expect(removeLayer).toHaveBeenCalledWith(oldLayer);
    expect(tileLayerFactory).not.toHaveBeenCalled();
    expect(addTo).not.toHaveBeenCalled();

    const onlyOldLayerMap = {
      eachLayer: (cb) => cb(oldLayer),
      removeLayer: vi.fn(),
    };
    innerMap.leafletMap = onlyOldLayerMap;
    await el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenCalledWith(
      "https://tiles.example/{z}/{x}/{y}.png",
      { maxZoom: 12 },
    );
    expect(addTo).toHaveBeenCalledWith(onlyOldLayerMap);

    el._config = {
      tileLayer: {
        url: "https://tiles2.example/{z}/{x}/{y}.png",
      },
    };
    await el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenLastCalledWith(
      "https://tiles2.example/{z}/{x}/{y}.png",
      {},
    );
  });

  test("setTileLayer no-ops when map prerequisites are missing", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();

    el._config = {
      tileLayer: { url: "https://tiles.example/{z}/{x}/{y}.png" },
    };
    await expect(el._setTileLayer()).resolves.toBeUndefined();

    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    innerMap.leafletMap = { eachLayer: vi.fn(), removeLayer: vi.fn() };
    await expect(el._setTileLayer()).resolves.toBeUndefined();
  });

  test("buildMapConfig uses defaults and show_home entity", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();

    el._config = null;
    expect(el._buildMapConfig()).toEqual({
      type: "map",
      geo_location_sources: ["dummy"],
      entities: [],
      auto_fit: true,
      fit_zones: true,
    });

    el._config = { auto_fit: false, show_home: true };
    expect(el._buildMapConfig()).toEqual({
      type: "map",
      geo_location_sources: ["dummy"],
      entities: ["zone.home"],
      auto_fit: false,
      fit_zones: true,
    });
  });

  test("setConfig updates map config only when built config changes", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const setConfigSpy = vi.fn();
    el._mapCard = { setConfig: setConfigSpy };

    el.setConfig({ auto_fit: true, show_home: false });
    expect(setConfigSpy).not.toHaveBeenCalled();

    el.setConfig({ auto_fit: false, show_home: false });
    expect(setConfigSpy).toHaveBeenCalledTimes(1);
    expect(setConfigSpy).toHaveBeenLastCalledWith({
      type: "map",
      geo_location_sources: ["dummy"],
      entities: [],
      auto_fit: false,
      fit_zones: true,
    });

    el.setConfig({ auto_fit: false, show_home: false });
    expect(setConfigSpy).toHaveBeenCalledTimes(1);

    el.setConfig({ auto_fit: false, show_home: true });
    expect(setConfigSpy).toHaveBeenCalledTimes(2);
    expect(setConfigSpy).toHaveBeenLastCalledWith({
      type: "map",
      geo_location_sources: ["dummy"],
      entities: ["zone.home"],
      auto_fit: false,
      fit_zones: true,
    });
  });

  test("getConfigForm labels support english and hebrew", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const form = Card.getConfigForm();
    const previousLang = document.documentElement.lang;

    const homeAssistant = document.createElement("home-assistant");
    homeAssistant.hass = { language: "he-IL" };
    document.body.append(homeAssistant);
    expect(form.computeLabel({ name: "auto_fit" })).toBe(
      "התאם את המפה אוטומטית להתרעות פעילות",
    );
    expect(form.computeLabel({ name: "show_home" })).toBe("הצג בית");
    homeAssistant.remove();

    document.documentElement.lang = "en-US";
    expect(form.computeLabel({ name: "auto_fit" })).toBe(
      "Auto fit map to active alerts",
    );
    expect(form.computeLabel({ name: "show_home" })).toBe("Show home");
    expect(form.computeLabel({ name: "unknown" })).toBeUndefined();

    const homeAssistantNoHass = document.createElement("home-assistant");
    document.body.append(homeAssistantNoHass);
    document.documentElement.lang = "";
    const navigatorLanguageGet = vi
      .spyOn(window.navigator, "language", "get")
      .mockReturnValue("en-US");
    expect(form.computeLabel({ name: "show_home" })).toBe("Show home");

    navigatorLanguageGet.mockReturnValue("");
    expect(form.computeLabel({ name: "show_home" })).toBe("Show home");
    homeAssistantNoHass.remove();

    document.documentElement.lang = previousLang;
  });

  test("stub config includes defaults", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    expect(Card.getStubConfig()).toEqual({
      auto_fit: true,
      show_home: false,
    });
  });

  test("hass setter catches errors from applyHass", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("boom");
    vi.spyOn(el, "_applyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el.hass = { states: {}, connection: {} };
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map update failed",
      error,
    );
  });

  test("empty areas refresh retries every second until areas are set", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(1000);
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
    expect(applyHassSpy).toHaveBeenCalledWith(1);

    el._areas = ["Area A"];
    vi.advanceTimersByTime(1000);
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
    expect(el._refreshId).toBeNull();
  });

  test("empty areas refresh is cleared on disconnect", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    el.disconnectedCallback();
    expect(el._refreshId).toBeNull();

    vi.advanceTimersByTime(1000);
    expect(applyHassSpy).not.toHaveBeenCalled();
  });

  test("empty areas refresh logs retry errors", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const error = new Error("retry failed");
    vi.spyOn(el, "_applyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el._checkRefresh();
    vi.advanceTimersByTime(1000);
    await Promise.resolve();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map refresh retry failed",
      error,
    );
  });

  test("refresh resumes if areas become empty again within first minute", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    el._areas = ["Area A"];
    el._checkRefresh();
    expect(el._refreshId).toBeNull();

    el._areas = [];
    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(1000);
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
  });

  test("bootstrap refresh stops after one minute when areas stay empty", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(60_000);
    expect(el._refreshId).toBeNull();
    const callsAtStop = applyHassSpy.mock.calls.length;

    vi.advanceTimersByTime(5_000);
    expect(applyHassSpy).toHaveBeenCalledTimes(callsAtStop);
    expect(el._refreshId).toBeNull();
  });

  test("checkRefresh stops immediately once bootstrap deadline has passed", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);

    el._refreshDeadline = Date.now() - 1;
    el._checkRefresh();

    expect(el._refreshId).toBeNull();
  });

  test("re-import throws on duplicate custom element registration", async () => {
    await ensureDefined();
    vi.resetModules();
    await expect(
      import("../custom_components/oref_alert/cards/oref-alert-map.js"),
    ).rejects.toThrow();
  });

  test("home-assistant callback re-defines when tag is missing", async () => {
    vi.resetModules();
    delete window.customCards;
    const defineSpy = vi
      .spyOn(customElements, "define")
      .mockImplementation(() => {});
    vi.spyOn(customElements, "get").mockImplementation(() => undefined);
    vi.spyOn(customElements, "whenDefined").mockResolvedValue(undefined);

    await import("../custom_components/oref_alert/cards/oref-alert-map.js");
    await waitForTasks();

    expect(defineSpy).toHaveBeenCalledTimes(2);
  });

  test("home-assistant callback skips re-define when tag exists", async () => {
    vi.resetModules();
    delete window.customCards;
    const defineSpy = vi
      .spyOn(customElements, "define")
      .mockImplementation(() => {});
    vi.spyOn(customElements, "get").mockImplementation(
      () => function MockCard() {},
    );
    vi.spyOn(customElements, "whenDefined").mockResolvedValue(undefined);

    await import("../custom_components/oref_alert/cards/oref-alert-map.js");
    await waitForTasks();

    expect(defineSpy).toHaveBeenCalledTimes(1);
  });
});
