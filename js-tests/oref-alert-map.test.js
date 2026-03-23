import { afterEach, describe, expect, test, vi } from "vitest";

async function ensureDefined() {
  if (!customElements.get("oref-alert-map")) {
    await import("../custom_components/oref_alert/cards/oref-alert-map.js");
  }
}

function waitForTasks() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function createHass({
  areasStatusResponse = {},
  subscribeEvents = vi.fn().mockResolvedValue(vi.fn()),
} = {}) {
  const callService = vi.fn().mockResolvedValue(areasStatusResponse);
  return {
    states: {},
    callService,
    connection: {
      subscribeEvents,
    },
  };
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
    const hass = createHass();
    vi.spyOn(el, "_applyAreas").mockResolvedValue();

    el.setConfig({ ignored: true });
    el.layout = "panel";
    el._hass = hass;

    expect(el.getCardSize()).toBe(7);
    expect(el.getGridOptions()).toEqual({
      columns: "full",
      rows: 4,
      min_columns: 6,
      min_rows: 2,
    });

    const created = await el._createMapCard();
    expect(created).toBe(mapCard);
    expect(hassSetter).not.toHaveBeenCalled();
    expect(mapCard.layout).toBe("panel");
    expect(el._map).toBeNull();

    el._hassUpdateToken = 1;
    await el._applyHass(1);
    expect(hassSetter).toHaveBeenCalledWith(hass);
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

    el._hassUpdateToken = 1;
    const p1 = el._ensureMapCard(1);
    const p2 = el._ensureMapCard(1);
    await Promise.all([p1, p2]);

    expect(createCardElement).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map failed to create map card",
      expect.any(Error),
    );
    expect(el._mapCardPromise).toBeNull();

    el._hassUpdateToken = 2;
    await expect(el._ensureMapCard(2)).resolves.toBe(mapCard);
    expect(createCardElement).toHaveBeenCalledTimes(2);
    await expect(el._ensureMapCard(2)).resolves.toBe(mapCard);
    expect(createCardElement).toHaveBeenCalledTimes(2);

    const staleMapCard = createMapCardWithInnerMap().mapCard;
    el._mapCard = null;
    el._mapCardPromise = Promise.resolve(staleMapCard);
    el._hassUpdateToken = 3;
    await expect(el._ensureMapCard(2)).resolves.toBeNull();
    expect(el._mapCard).toBeNull();
    expect(el._mapCardPromise).toBeNull();
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
        { area: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
      ]),
    ).resolves.toEqual([]);

    innerMap.Leaflet = { polygon: vi.fn() };
    el._getPolygons.mockResolvedValueOnce(null);
    await expect(
      el._createLayers([
        { area: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
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
      { area: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
      { area: "Area B", date: "2026-03-13T11:42:00Z", emoji: "✈️" },
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

  test("getOrefAreas loads areas_status via callService and sorts areas", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    expect(await el._getOrefAreas()).toEqual([]);

    const hass = createHass({
      areasStatusResponse: {
        "Area B": {
          area: "Area B",
          date: "2026-03-13T11:42:00Z",
          emoji: "✈️",
          type: "alert",
        },
        "Area A": {
          area: "Area A",
          date: "2026-03-13T08:05:00Z",
          emoji: "🚀",
          type: "alert",
        },
        ignored: "not-an-area",
      },
    });
    el._hass = hass;

    expect(await el._getOrefAreas()).toEqual([
      {
        area: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
        type: "alert",
      },
      {
        area: "Area B",
        date: "2026-03-13T11:42:00Z",
        emoji: "✈️",
        type: "alert",
      },
    ]);
    expect(hass.callService).toHaveBeenCalledWith(
      "oref_alert",
      "areas_status",
      {},
      undefined,
      true,
    );
  });

  test("applyHass handles stale hass token and does not update layers directly", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });

    el._hass = createHass();

    el._hassUpdateToken = 2;
    await el._applyHass(1);

    vi.spyOn(el, "_ensureMapCard").mockResolvedValue(null);
    await el._applyHass(2);

    el._mapCard = mapCard;
    el._ensureMapCard.mockResolvedValue(mapCard);
    const applyAreasSpy = vi.spyOn(el, "_applyAreas").mockResolvedValue();
    await el._applyHass(2);
    expect(applyAreasSpy).toHaveBeenCalledWith(0);
    expect(innerMap.layers).toBeUndefined();

    applyAreasSpy.mockImplementation(async () => {
      el._hassUpdateToken = 3;
    });
    el._hassUpdateToken = 2;
    await el._applyHass(2);
    expect(innerMap.layers).toBeUndefined();
  });

  test("applyAreas handles stale areas token and map assignment", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    el._areas = [
      {
        area: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
      },
      {
        area: "Area B",
        date: "2026-03-13T11:42:00Z",
        emoji: "✈️",
      },
    ];

    const createLayersSpy = vi.spyOn(el, "_createLayers");
    el._areasUpdateToken = 2;
    await el._applyAreas(1);
    expect(innerMap.layers).toBeUndefined();

    createLayersSpy.mockImplementation(async () => {
      el._areasUpdateToken = 3;
      return [{ id: 1 }];
    });
    el._areasUpdateToken = 2;
    await el._applyAreas(2);
    expect(innerMap.layers).toBeUndefined();

    createLayersSpy.mockResolvedValue([{ id: 2 }, { id: 3 }]);
    el._areasUpdateToken = 4;
    await el._applyAreas(4);
    expect(innerMap.layers).toEqual([{ id: 2 }, { id: 3 }]);
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

    el._config = {
      hebrew_basemap: true,
    };
    await el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenLastCalledWith(
      "https://cdnil.govmap.gov.il/xyz/heb/{z}/{x}/{y}.png",
      {
        minZoom: 8,
        maxZoom: 15,
        attribution: "© GovMap / המרכז למיפוי ישראל",
      },
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

    el._config = {
      auto_fit: false,
      entities: ["person.alice", "device_tracker.bob"],
    };
    expect(el._buildMapConfig()).toEqual({
      type: "map",
      geo_location_sources: ["dummy"],
      entities: ["person.alice", "device_tracker.bob"],
      auto_fit: false,
      fit_zones: true,
    });

    el._config = {
      auto_fit: false,
      show_home: true,
      entities: ["person.alice", "device_tracker.bob"],
    };
    expect(el._buildMapConfig()).toEqual({
      type: "map",
      geo_location_sources: ["dummy"],
      entities: ["zone.home", "person.alice", "device_tracker.bob"],
      auto_fit: false,
      fit_zones: true,
    });
  });

  test("setConfig resets state and reapplies hass when available", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const stopRefreshSpy = vi.spyOn(el, "_stopRefresh");
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();
    const child = document.createElement("div");
    el.append(child);

    el._mapCard = { id: "map-card" };
    el._mapCardPromise = Promise.resolve(el._mapCard);
    el._areas = [{ id: "Area A" }];
    el._refreshDeadline = 0;
    el._hass = createHass();
    el._hassUpdateToken = 7;

    el.setConfig({ auto_fit: false, show_home: true });

    expect(stopRefreshSpy).toHaveBeenCalledTimes(1);
    expect(el._mapCard).toBeNull();
    expect(el._mapCardPromise).toBeNull();
    expect(el._areas).toEqual([{ id: "Area A" }]);
    expect(el.childElementCount).toBe(0);
    expect(el._refreshDeadline).toBeGreaterThan(Date.now() - 1000);
    expect(applyHassSpy).toHaveBeenCalledWith(8);

    const elNoHass = new Card();
    const applyHassNoHassSpy = vi
      .spyOn(elNoHass, "_applyHass")
      .mockResolvedValue();
    elNoHass.setConfig({ auto_fit: true, show_home: false });
    expect(applyHassNoHassSpy).not.toHaveBeenCalled();
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
    expect(form.computeLabel({ name: "hebrew_basemap" })).toBe(
      "מפת בסיס בעברית",
    );
    homeAssistant.remove();

    document.documentElement.lang = "en-US";
    expect(form.computeLabel({ name: "auto_fit" })).toBe(
      "Auto fit map to active alerts",
    );
    expect(form.computeLabel({ name: "show_home" })).toBe("Show home");
    expect(form.computeLabel({ name: "hebrew_basemap" })).toBe(
      "Hebrew basemap",
    );
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
      hebrew_basemap: true,
    });
  });

  test("hass setter catches errors from applyHass", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("boom");
    vi.spyOn(el, "_applyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el.hass = createHass();
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map hass apply failed",
      error,
    );
  });

  test("setConfig catches errors from applyHass", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("set-config boom");
    el._hass = createHass();
    vi.spyOn(el, "_applyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el.setConfig({ auto_fit: true, show_home: false });
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map setConfig apply failed",
      error,
    );
  });

  test("hass setter catches errors from subscribeToEvents", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("subscribe boom");
    vi.spyOn(el, "_subscribeToEvents").mockRejectedValue(error);
    vi.spyOn(el, "_applyHass").mockResolvedValue();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el.hass = createHass();
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map hass subscribe failed",
      error,
    );
  });

  test("hass setter resubscribes when connection changes", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const unsubscribe1 = vi.fn();
    const unsubscribe2 = vi.fn();
    const subscribeEvents1 = vi.fn().mockResolvedValue(unsubscribe1);
    const subscribeEvents2 = vi.fn().mockResolvedValue(unsubscribe2);
    const hass1 = createHass({ subscribeEvents: subscribeEvents1 });
    const hass2 = createHass({ subscribeEvents: subscribeEvents2 });
    vi.spyOn(el, "_applyHass").mockResolvedValue();

    el.hass = hass1;
    await waitForTasks();
    expect(subscribeEvents1).toHaveBeenCalledTimes(1);
    expect(unsubscribe1).not.toHaveBeenCalled();

    el.hass = hass1;
    await waitForTasks();
    expect(subscribeEvents1).toHaveBeenCalledTimes(1);

    el.hass = hass2;
    await waitForTasks();
    expect(unsubscribe1).toHaveBeenCalledTimes(1);
    expect(subscribeEvents2).toHaveBeenCalledTimes(1);
  });

  test("applyHass returns when token changes after ensureMapCard resolves", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    const hassSetter = vi.fn();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(value) {
        hassSetter(value);
      },
    });

    el._areas = [{ id: "existing" }];
    el._hass = createHass();
    el._hassUpdateToken = 1;
    vi.spyOn(el, "_ensureMapCard").mockImplementation(async () => {
      el._hassUpdateToken = 2;
      return mapCard;
    });
    const replaceChildrenSpy = vi.spyOn(el, "replaceChildren");

    await el._applyHass(1);

    expect(replaceChildrenSpy).not.toHaveBeenCalled();
    expect(hassSetter).not.toHaveBeenCalled();
  });

  test("refreshAreas loads areas and renders them", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const applyAreasSpy = vi.spyOn(el, "_applyAreas").mockResolvedValue();
    vi.spyOn(el, "_getOrefAreas").mockResolvedValue([
      { area: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
    ]);
    el._areasUpdateToken = 3;

    await el._refreshAreas(3);

    expect(el._areas).toEqual([
      { area: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
    ]);
    expect(applyAreasSpy).toHaveBeenCalledWith(3);
  });

  test("refreshAreas ignores stale areas token", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    el._areas = [
      { area: "Old Area", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
    ];
    vi.spyOn(el, "_getOrefAreas").mockResolvedValue([
      { area: "New Area", date: "2026-03-13T09:05:00Z", emoji: "✈️" },
    ]);
    const applyAreasSpy = vi.spyOn(el, "_applyAreas").mockResolvedValue();
    el._areasUpdateToken = 4;

    await el._refreshAreas(3);

    expect(el._areas).toEqual([
      { area: "Old Area", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
    ]);
    expect(applyAreasSpy).not.toHaveBeenCalled();
  });

  test("applyAreas returns early when areas are already rendered", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const areas = [
      { area: "Area A", date: "2026-03-13T08:05:00Z", emoji: "🚀" },
    ];
    el._areas = areas;
    el._renderedAreas = areas;
    const createLayersSpy = vi.spyOn(el, "_createLayers");

    await el._applyAreas(1);

    expect(createLayersSpy).not.toHaveBeenCalled();
  });

  test("subscribeToEvents subscribes once and refreshes on oref_alert_record", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    let eventCallback;
    const unsubscribe = vi.fn();
    const subscribeEvents = vi
      .fn()
      .mockImplementation((callback, eventType) => {
        eventCallback = callback;
        expect(eventType).toBe("oref_alert_record");
        return Promise.resolve(unsubscribe);
      });
    const hass = createHass({ subscribeEvents });
    el._hass = hass;
    el._eventConnection = hass.connection;
    const refreshAreasSpy = vi.spyOn(el, "_refreshAreas").mockResolvedValue();

    await el._subscribeToEvents();
    await el._subscribeToEvents();

    expect(subscribeEvents).toHaveBeenCalledTimes(1);
    eventCallback();
    await waitForTasks();
    expect(refreshAreasSpy).toHaveBeenCalledWith(1);

    el.disconnectedCallback();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
    expect(el._eventConnection).toBeNull();
  });

  test("subscribeToEvents logs callback refresh errors", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    let eventCallback;
    const subscribeEvents = vi.fn().mockImplementation((callback) => {
      eventCallback = callback;
      return Promise.resolve(vi.fn());
    });
    const hass = createHass({ subscribeEvents });
    el._hass = hass;
    el._eventConnection = hass.connection;
    const error = new Error("event refresh failed");
    vi.spyOn(el, "_refreshAreas")
      .mockResolvedValueOnce()
      .mockRejectedValueOnce(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    await el._subscribeToEvents();
    eventCallback();
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map event refresh failed",
      error,
    );
  });

  test("subscribeToEvents unsubscribes if connection changes before subscribe resolves", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const unsubscribe = vi.fn();
    let resolveSubscribe;
    const subscribeEvents = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSubscribe = () => resolve(unsubscribe);
        }),
    );
    const hass1 = createHass({ subscribeEvents });
    const hass2 = createHass();
    el._hass = hass1;
    el._eventConnection = hass1.connection;

    const subscribePromise = el._subscribeToEvents();
    el._hass = hass2;
    el._eventConnection = hass2.connection;
    resolveSubscribe();
    await subscribePromise;

    expect(unsubscribe).toHaveBeenCalledTimes(1);
    expect(el._eventUnsub).toBeNull();
  });

  test("bootstrap refresh retries every second until the map element is ready", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
    expect(applyHassSpy).toHaveBeenCalledWith(1);

    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    vi.advanceTimersByTime(1000);
    await Promise.resolve();
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
    await Promise.resolve();
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

  test("refresh resumes if the map element disappears again within first minute", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    el._checkRefresh();
    expect(el._refreshId).toBeNull();

    el._mapCard = null;
    el._checkRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
  });

  test("bootstrap refresh stops after one minute when the map stays unavailable", async () => {
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
    await Promise.resolve();
    const callsAtStop = applyHassSpy.mock.calls.length;

    vi.advanceTimersByTime(5_000);
    await Promise.resolve();
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
