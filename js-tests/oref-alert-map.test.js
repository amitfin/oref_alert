import { afterEach, describe, expect, test, vi } from "vitest";

async function ensureDefined() {
  if (!customElements.get("oref-alert-map")) {
    await import(
      "../custom_components/oref_alert/cards/oref-alert-map.js?v=1.0.0"
    );
  }
}

function waitForTasks() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function createHass({
  lastUpdateResponse = { last_update: null, version: null },
  areasStatusResponse = {},
} = {}) {
  const callService = vi.fn().mockImplementation((domain, service) => {
    if (domain !== "oref_alert") {
      return Promise.resolve({ response: {} });
    }
    if (service === "last_update") {
      return Promise.resolve({ response: lastUpdateResponse });
    }
    if (service === "areas_status") {
      return Promise.resolve({ response: areasStatusResponse });
    }
    return Promise.resolve({ response: {} });
  });
  return {
    callService,
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
  window.sessionStorage.clear();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("oref-alert-map", () => {
  test("registers custom element and metadata", async () => {
    vi.resetModules();
    delete window.customCards;
    const defineSpy = vi.spyOn(customElements, "define");

    await import(
      "../custom_components/oref_alert/cards/oref-alert-map.js?v=1.0.0"
    );

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
    vi.spyOn(el, "_refreshAreas").mockResolvedValue();

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

    await el._applyHass();
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

  test("ensureMapCard retries after failure and caches after success", async () => {
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

    await expect(el._ensureMapCard()).resolves.toBeNull();
    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map failed to create map card",
      expect.any(Error),
    );

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
    el._config = null;

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
    expect(layers).toHaveLength(2);
    expect(innerMap.Leaflet.polygon).toHaveBeenNthCalledWith(
      1,
      [
        [1, 1],
        [1, 2],
      ],
      { color: "rgb(241, 146, 146)" },
    );
    expect(innerMap.Leaflet.polygon).toHaveBeenNthCalledWith(
      2,
      [
        [2, 1],
        [2, 2],
      ],
      { color: "rgb(241, 146, 146)" },
    );
    expect(created[0].bindTooltip).toHaveBeenCalledWith(
      `Area A<br />${String(new Date("2026-03-13T08:05:00Z").getHours()).padStart(2, "0")}:${String(new Date("2026-03-13T08:05:00Z").getMinutes()).padStart(2, "0")} 🚀`,
    );
    expect(created[1].bindTooltip).toHaveBeenCalledWith(
      `Area B<br />${String(new Date("2026-03-13T11:42:00Z").getHours()).padStart(2, "0")}:${String(new Date("2026-03-13T11:42:00Z").getMinutes()).padStart(2, "0")} ✈️`,
    );
  });

  test("createLayers uses default pre-alert layer color at runtime", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    el._config = null;
    innerMap.Leaflet = {
      polygon: vi.fn().mockImplementation(() => ({ bindTooltip: vi.fn() })),
    };
    vi.spyOn(el, "_getPolygons").mockResolvedValue({ "Area A": [[1, 1]] });

    await el._createLayers([
      {
        area: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
        type: "pre_alert",
      },
    ]);

    expect(innerMap.Leaflet.polygon).toHaveBeenCalledWith([[1, 1]], {
      color: "rgb(253, 224, 71)",
    });
  });

  test("getLastUpdate loads last_update via callService", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    await expect(el._getLastUpdate()).resolves.toEqual({
      lastUpdated: null,
      version: null,
    });

    const hass = createHass({
      lastUpdateResponse: {
        last_update: "2026-03-24T10:00:00+00:00",
        version: "2.3.4",
      },
    });
    el._hass = hass;

    await expect(el._getLastUpdate()).resolves.toEqual({
      lastUpdated: "2026-03-24T10:00:00+00:00",
      version: "2.3.4",
    });
    expect(hass.callService).toHaveBeenCalledWith(
      "oref_alert",
      "last_update",
      {},
      undefined,
      false,
      true,
    );
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
      false,
      true,
    );
  });

  test("getOrefAreas includes pre-alert by default and excludes it when disabled", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const hass = createHass({
      areasStatusResponse: {
        "Area B": {
          area: "Area B",
          date: "2026-03-13T11:42:00Z",
          emoji: "✈️",
          type: "pre_alert",
        },
        "Area A": {
          area: "Area A",
          date: "2026-03-13T08:05:00Z",
          emoji: "🚀",
          type: "alert",
        },
      },
    });
    el._hass = hass;
    el._config = null;

    await expect(el._getOrefAreas()).resolves.toEqual([
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
        type: "pre_alert",
      },
    ]);

    el._config = { show_pre_alert: false };
    await expect(el._getOrefAreas()).resolves.toEqual([
      {
        area: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
        type: "alert",
      },
    ]);
  });

  test("applyHass handles missing map card and does not update areas directly", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });

    el._hass = createHass();

    vi.spyOn(el, "_ensureMapCard").mockResolvedValue(null);
    await el._applyHass();

    el._mapCard = mapCard;
    el._ensureMapCard.mockResolvedValue(mapCard);
    const refreshAreasSpy = vi.spyOn(el, "_refreshAreas").mockResolvedValue();
    await el._applyHass();
    expect(refreshAreasSpy).toHaveBeenCalledWith();
    expect(innerMap.layers).toBeUndefined();
  });

  test("refreshAreas skips work when last_updated is already tracked", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    el._hass = createHass({
      lastUpdateResponse: {
        last_update: "2026-03-24T10:00:00+00:00",
      },
    });
    el._lastUpdated = "2026-03-24T10:00:00+00:00";
    const createLayersSpy = vi.spyOn(el, "_createLayers");

    await el._refreshAreas();

    expect(createLayersSpy).not.toHaveBeenCalled();
  });

  test("refreshAreas reloads the page when backend version changes", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const getLastUpdateSpy = vi.spyOn(el, "_getLastUpdate").mockResolvedValue({
      lastUpdated: "2026-03-24T10:00:00+00:00",
      version: "mismatch-version",
    });
    vi.spyOn(el, "_maybeReloadForVersion").mockReturnValue(true);
    const createLayersSpy = vi.spyOn(el, "_createLayers");

    await el._refreshAreas();

    expect(getLastUpdateSpy).toHaveBeenCalledWith();
    expect(el._maybeReloadForVersion).toHaveBeenCalledWith("mismatch-version");
    expect(createLayersSpy).not.toHaveBeenCalled();
  });

  test("refreshAreas avoids repeated reload attempts for the same version", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const getLastUpdateSpy = vi.spyOn(el, "_getLastUpdate").mockResolvedValue({
      lastUpdated: "2026-03-24T10:00:00+00:00",
      version: "mismatch-version",
    });
    vi.spyOn(el, "_maybeReloadForVersion")
      .mockReturnValueOnce(true)
      .mockReturnValueOnce(true);
    const createLayersSpy = vi.spyOn(el, "_createLayers");

    await el._refreshAreas();
    await el._refreshAreas();

    expect(getLastUpdateSpy).toHaveBeenCalledTimes(2);
    expect(el._maybeReloadForVersion).toHaveBeenNthCalledWith(
      1,
      "mismatch-version",
    );
    expect(el._maybeReloadForVersion).toHaveBeenNthCalledWith(
      2,
      "mismatch-version",
    );
    expect(createLayersSpy).not.toHaveBeenCalled();
  });

  test("maybeReloadForVersion clears the guard when versions match", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    vi.spyOn(el, "_getCurrentVersion").mockReturnValue("1.0.0");
    window.sessionStorage.setItem("oref-alert-map-reload-version", "1.0.0");

    expect(el._maybeReloadForVersion("1.0.0")).toBe(false);
    expect(
      window.sessionStorage.getItem("oref-alert-map-reload-version"),
    ).toBeNull();
  });

  test("maybeReloadForVersion reloads and stores guard on mismatch", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    vi.spyOn(el, "_getCurrentVersion").mockReturnValue("1.0.0");

    expect(el._maybeReloadForVersion("2.0.0")).toBe(true);
    expect(window.sessionStorage.getItem("oref-alert-map-reload-version")).toBe(
      "2.0.0",
    );
  });

  test("maybeReloadForVersion skips repeated reload for same mismatched version", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    vi.spyOn(el, "_getCurrentVersion").mockReturnValue("1.0.0");
    window.sessionStorage.setItem("oref-alert-map-reload-version", "2.0.0");

    expect(el._maybeReloadForVersion("2.0.0")).toBe(true);
    expect(window.sessionStorage.getItem("oref-alert-map-reload-version")).toBe(
      "2.0.0",
    );
  });

  test("maybeReloadForVersion still reloads when session storage fails", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    vi.spyOn(el, "_getCurrentVersion").mockReturnValue("1.0.0");
    const storageProto = Object.getPrototypeOf(window.sessionStorage);
    const getItemSpy = vi
      .spyOn(storageProto, "getItem")
      .mockImplementation(() => {
        throw new Error("storage unavailable");
      });

    expect(el._maybeReloadForVersion("2.0.0")).toBe(true);
    expect(getItemSpy).toHaveBeenCalledWith("oref-alert-map-reload-version");
  });

  test("maybeReloadForVersion returns false when current version is unavailable", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    vi.spyOn(el, "_getCurrentVersion").mockReturnValue(null);

    expect(el._maybeReloadForVersion("2.0.0")).toBe(false);
  });

  test("refreshAreas renders once on first load even when last_update is null", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    el._hass = createHass({
      lastUpdateResponse: {
        last_update: null,
      },
      areasStatusResponse: {
        "Area A": {
          area: "Area A",
          date: "2026-03-13T08:05:00Z",
          emoji: "🚀",
          type: "alert",
        },
      },
    });
    vi.spyOn(el, "_createLayers").mockResolvedValue([{ id: 1 }]);

    await el._refreshAreas();

    expect(el._lastUpdated).toBeNull();
    expect(innerMap.layers).toEqual([{ id: 1 }]);
  });

  test("refreshAreas assigns map layers and updates tracked last_updated after success", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    el._hass = createHass({
      lastUpdateResponse: {
        last_update: "2026-03-24T10:00:00+00:00",
      },
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
      },
    });
    vi.spyOn(el, "_createLayers").mockResolvedValue([{ id: 2 }, { id: 3 }]);

    await el._refreshAreas();

    expect(innerMap.layers).toEqual([{ id: 2 }, { id: 3 }]);
    expect(el._lastUpdated).toBe("2026-03-24T10:00:00+00:00");
  });

  test("applyHass runs serially for queued applies", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });

    el._hass = createHass();
    const ensureMapCardSpy = vi
      .spyOn(el, "_ensureMapCard")
      .mockResolvedValue(mapCard);
    const phases = [];
    let resolveFirstRefresh;
    const firstRefreshPromise = new Promise((resolve) => {
      resolveFirstRefresh = resolve;
    });
    const refreshAreasSpy = vi
      .spyOn(el, "_refreshAreas")
      .mockImplementation(async () => {
        phases.push("start");
        if (phases.length === 1) {
          await firstRefreshPromise;
        }
        phases.push("end");
      });

    const firstApply = el._applyHass();
    const secondApply = el._applyHass();
    await waitForTasks();

    expect(ensureMapCardSpy).toHaveBeenCalledTimes(1);
    expect(refreshAreasSpy).toHaveBeenCalledTimes(1);
    expect(phases).toEqual(["start"]);

    resolveFirstRefresh();

    await Promise.all([firstApply, secondApply]);

    expect(ensureMapCardSpy).toHaveBeenCalledTimes(2);
    expect(refreshAreasSpy).toHaveBeenCalledTimes(2);
    expect(phases).toEqual(["start", "end", "start", "end"]);
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
    const leafletMap = {
      eachLayer,
      removeLayer,
      setMaxZoom: vi.fn(),
      setMinZoom: vi.fn(),
    };
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
    el._setTileLayer();
    expect(removeLayer).toHaveBeenCalledTimes(1);
    expect(removeLayer).toHaveBeenCalledWith(oldLayer);
    expect(tileLayerFactory).not.toHaveBeenCalled();
    expect(addTo).not.toHaveBeenCalled();
    expect(leafletMap.setMaxZoom).not.toHaveBeenCalled();
    expect(leafletMap.setMinZoom).not.toHaveBeenCalled();

    const onlyOldLayerMap = {
      eachLayer: (cb) => cb(oldLayer),
      removeLayer: vi.fn(),
      setMaxZoom: vi.fn(),
      setMinZoom: vi.fn(),
    };
    innerMap.leafletMap = onlyOldLayerMap;
    el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenCalledWith(
      "https://tiles.example/{z}/{x}/{y}.png",
      { maxZoom: 12 },
    );
    expect(addTo).toHaveBeenCalledWith(onlyOldLayerMap);
    expect(onlyOldLayerMap.setMaxZoom).toHaveBeenCalledWith(12);
    expect(onlyOldLayerMap.setMinZoom).not.toHaveBeenCalled();

    el._config = {
      tileLayer: {
        url: "https://tiles2.example/{z}/{x}/{y}.png",
      },
    };
    el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenLastCalledWith(
      "https://tiles2.example/{z}/{x}/{y}.png",
      {},
    );

    el._config = {
      tileLayer: {
        url: "https://tiles3.example/{z}/{x}/{y}.png",
        options: { minZoom: 0, maxZoom: 5 },
      },
    };
    el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenLastCalledWith(
      "https://tiles3.example/{z}/{x}/{y}.png",
      { minZoom: 0, maxZoom: 5 },
    );
    expect(onlyOldLayerMap.setMinZoom).toHaveBeenCalledWith(0);
    expect(onlyOldLayerMap.setMaxZoom).toHaveBeenLastCalledWith(5);

    el._config = {
      hebrew_basemap: true,
    };
    el._setTileLayer();
    expect(tileLayerFactory).toHaveBeenLastCalledWith(
      "https://cdnil.govmap.gov.il/xyz/heb/{z}/{x}/{y}.png",
      {
        minZoom: 8,
        maxZoom: 15,
        attribution: "© GovMap / המרכז למיפוי ישראל",
      },
    );
    expect(onlyOldLayerMap.setMinZoom).toHaveBeenLastCalledWith(8);
    expect(onlyOldLayerMap.setMaxZoom).toHaveBeenLastCalledWith(15);
  });

  test("setTileLayer no-ops when map prerequisites are missing", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();

    el._config = {
      tileLayer: { url: "https://tiles.example/{z}/{x}/{y}.png" },
    };
    expect(el._setTileLayer()).toBeUndefined();

    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    innerMap.leafletMap = { eachLayer: vi.fn(), removeLayer: vi.fn() };
    expect(el._setTileLayer()).toBeUndefined();
  });

  test("setTileLayer returns early when hebrew basemap is explicitly disabled", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    const tileLayerFactory = vi.fn();

    el._mapCard = mapCard;
    el._config = { hebrew_basemap: false };
    innerMap.leafletMap = { eachLayer: vi.fn(), removeLayer: vi.fn() };
    innerMap.Leaflet = {
      TileLayer: class {},
      tileLayer: tileLayerFactory,
    };

    expect(el._setTileLayer()).toBeUndefined();
    expect(tileLayerFactory).not.toHaveBeenCalled();
  });

  test("startLocationWatch performs initial fetch, starts watch once, and updates marker state", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const syncMarkerSpy = vi
      .spyOn(el, "_syncLocationMarker")
      .mockImplementation(() => {});
    const originalGeolocation = window.navigator.geolocation;

    let initialSuccessCallback;
    let watchSuccessCallback;
    const getCurrentPosition = vi.fn((success) => {
      initialSuccessCallback = success;
    });
    const watchPosition = vi.fn((success) => {
      watchSuccessCallback = success;
      return 7;
    });
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      await el._startLocationWatch();

      expect(getCurrentPosition).toHaveBeenCalledTimes(1);
      expect(getCurrentPosition).toHaveBeenCalledWith(
        expect.any(Function),
        expect.any(Function),
        {
          enableHighAccuracy: false,
          maximumAge: 30_000,
          timeout: 10_000,
        },
      );

      expect(watchPosition).toHaveBeenCalledTimes(1);
      expect(watchPosition).toHaveBeenCalledWith(
        expect.any(Function),
        expect.any(Function),
        {
          enableHighAccuracy: false,
          maximumAge: 30_000,
        },
      );

      initialSuccessCallback({
        coords: { latitude: 31.77, longitude: 35.21, accuracy: 25 },
      });
      watchSuccessCallback({
        coords: { latitude: 31.78, longitude: 35.22, accuracy: 20 },
      });

      expect(syncMarkerSpy).toHaveBeenCalledTimes(2);
      expect(syncMarkerSpy).toHaveBeenNthCalledWith(1, 31.77, 35.21);
      expect(syncMarkerSpy).toHaveBeenNthCalledWith(2, 31.78, 35.22);

      el._stopLocationWatch();
      expect(clearWatch).toHaveBeenCalledWith(7);
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch skips geolocation calls when permissions are denied", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalPermissions = window.navigator.permissions;
    const originalGeolocation = window.navigator.geolocation;

    const query = vi.fn().mockResolvedValue({ state: "denied" });
    const getCurrentPosition = vi.fn();
    const watchPosition = vi.fn();
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "permissions", {
      configurable: true,
      value: { query },
    });
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      expect(query).toHaveBeenCalledWith({ name: "geolocation" });
      expect(getCurrentPosition).not.toHaveBeenCalled();
      expect(watchPosition).not.toHaveBeenCalled();
      expect(el._geoWatchId).toBeUndefined();
    } finally {
      Object.defineProperty(window.navigator, "permissions", {
        configurable: true,
        value: originalPermissions,
      });
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch exits early when show_location is disabled", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalGeolocation = window.navigator.geolocation;
    el._config = { show_location: false };

    const getCurrentPosition = vi.fn();
    const watchPosition = vi.fn();
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      expect(getCurrentPosition).not.toHaveBeenCalled();
      expect(watchPosition).not.toHaveBeenCalled();
      expect(el._geoWatchId).toBeUndefined();
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch keeps watch active on non-permission geolocation errors", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalGeolocation = window.navigator.geolocation;

    let errorCallback;
    const getCurrentPosition = vi.fn();
    const watchPosition = vi.fn((_, error) => {
      errorCallback = error;
      return 12;
    });
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      errorCallback({ code: 2 });

      expect(clearWatch).not.toHaveBeenCalled();
      expect(el._geoWatchId).toBe(12);
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch stops watching when initial position request is denied", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalGeolocation = window.navigator.geolocation;

    let initialErrorCallback;
    const getCurrentPosition = vi.fn((_, error) => {
      initialErrorCallback = error;
    });
    const watchPosition = vi.fn(() => 13);
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      initialErrorCallback({ code: 1 });

      expect(clearWatch).toHaveBeenCalledWith(13);
      expect(el._geoWatchId).toBeUndefined();
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch keeps watching when initial position request fails without permission denial", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalGeolocation = window.navigator.geolocation;

    let initialErrorCallback;
    const getCurrentPosition = vi.fn((_, error) => {
      initialErrorCallback = error;
    });
    const watchPosition = vi.fn(() => 15);
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      initialErrorCallback({ code: 2 });

      expect(clearWatch).not.toHaveBeenCalled();
      expect(el._geoWatchId).toBe(15);
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch stops watching when watchPosition reports permission denied", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalGeolocation = window.navigator.geolocation;

    let watchErrorCallback;
    const getCurrentPosition = vi.fn();
    const watchPosition = vi.fn((_, error) => {
      watchErrorCallback = error;
      return 14;
    });
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await el._startLocationWatch();
      watchErrorCallback({ code: 1 });

      expect(clearWatch).toHaveBeenCalledWith(14);
      expect(el._geoWatchId).toBeUndefined();
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("startLocationWatch recovers when geolocation APIs throw synchronously", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalGeolocation = window.navigator.geolocation;

    const getCurrentPosition = vi.fn(() => {
      throw new Error("sync geolocation failure");
    });
    const watchPosition = vi.fn(() => 16);
    const clearWatch = vi.fn();
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition, watchPosition, clearWatch },
    });

    try {
      await expect(el._startLocationWatch()).resolves.toBeUndefined();
      expect(el._geoWatchId).toBeUndefined();
      await expect(el._startLocationWatch()).resolves.toBeUndefined();
      expect(getCurrentPosition).toHaveBeenCalledTimes(2);
    } finally {
      Object.defineProperty(window.navigator, "geolocation", {
        configurable: true,
        value: originalGeolocation,
      });
    }
  });

  test("isLocationPermissionDenied returns false when permission query fails", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const originalPermissions = window.navigator.permissions;

    Object.defineProperty(window.navigator, "permissions", {
      configurable: true,
      value: {
        query: vi.fn().mockRejectedValue(new Error("unavailable")),
      },
    });

    try {
      await expect(el._isLocationPermissionDenied()).resolves.toBe(false);
    } finally {
      Object.defineProperty(window.navigator, "permissions", {
        configurable: true,
        value: originalPermissions,
      });
    }
  });

  test("syncLocationMarker uses a dedicated non-interactive marker and updates it", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    const marker = {
      addTo: vi.fn(),
      bindTooltip: vi.fn(),
      setLatLng: vi.fn(),
    };
    const markerFactory = vi.fn(() => marker);
    const divIconFactory = vi.fn(() => ({ id: "icon" }));
    const leafletMap = { removeLayer: vi.fn() };
    innerMap.Leaflet = {
      marker: markerFactory,
      divIcon: divIconFactory,
    };
    innerMap.leafletMap = leafletMap;
    marker.addTo.mockReturnValue(marker);

    el._syncLocationMarker(31.77, 35.21);

    expect(divIconFactory).toHaveBeenCalledWith({
      html: '<span style="display:block;width:14px;height:14px;background:#4285F4;border:3px solid #fff;border-radius:50%;box-shadow:0 0 6px rgba(66,133,244,0.6);"></span>',
      className: "",
      iconSize: [20, 20],
      iconAnchor: [10, 10],
    });
    expect(markerFactory).toHaveBeenCalledWith([31.77, 35.21], {
      icon: { id: "icon" },
      interactive: false,
      zIndexOffset: 1000,
    });
    expect(marker.addTo).toHaveBeenCalledWith(leafletMap);
    expect(marker.bindTooltip).toHaveBeenCalledWith("Location");

    el._syncLocationMarker(31.79, 35.23);
    expect(markerFactory).toHaveBeenCalledTimes(1);
    expect(marker.setLatLng).toHaveBeenCalledWith([31.79, 35.23]);
  });

  test("syncLocationMarker no-ops when map marker prerequisites are missing", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    expect(el._syncLocationMarker(31.77, 35.21)).toBeUndefined();
  });

  test("refreshAreas keeps map layers fitted to alert layers only", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    vi.spyOn(el, "_getLastUpdate").mockResolvedValue({
      lastUpdated: "2026-03-24T10:00:00+00:00",
      version: null,
    });
    vi.spyOn(el, "_getOrefAreas").mockResolvedValue([
      {
        area: "Area A",
        date: "2026-03-13T08:05:00Z",
        emoji: "🚀",
        type: "alert",
      },
    ]);
    vi.spyOn(el, "_createLayers").mockResolvedValue([{ id: "alert-layer" }]);
    await el._refreshAreas();

    expect(innerMap.layers).toEqual([{ id: "alert-layer" }]);
    expect(el._lastUpdated).toBe("2026-03-24T10:00:00+00:00");
  });

  test("removeLocationMarker removes marker from map when present", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    innerMap.leafletMap = { removeLayer: vi.fn() };
    const marker = { id: "marker" };
    el._locationMarker = marker;

    el._removeLocationMarker();

    expect(innerMap.leafletMap.removeLayer).toHaveBeenCalledWith(marker);
    expect(el._locationMarker).toBeNull();
  });

  test("buildMapConfig uses defaults, home entity, and passes through map options", async () => {
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

    el._config = {
      auto_fit: false,
      show_home: true,
      theme_mode: "satellite",
      title: "Alerts map",
      fit_zones: false,
      geo_location_sources: ["should-be-overridden"],
    };
    expect(el._buildMapConfig()).toEqual({
      auto_fit: false,
      theme_mode: "satellite",
      title: "Alerts map",
      type: "map",
      geo_location_sources: ["dummy"],
      entities: ["zone.home"],
      fit_zones: true,
    });
  });

  test("setConfig resets state and reapplies hass when available", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();
    const resetSpy = vi.spyOn(el, "_resetCardState");
    const child = document.createElement("div");
    el.append(child);

    el._mapCard = { id: "map-card" };
    el._lastUpdated = "2026-03-24T10:00:00+00:00";
    el._refreshDeadline = 0;
    el._hass = createHass();

    el.setConfig({ auto_fit: false, show_home: true });

    expect(resetSpy).not.toHaveBeenCalled();
    expect(applyHassSpy).toHaveBeenCalledWith(true);

    const elNoHass = new Card();
    const resetNoHassSpy = vi.spyOn(elNoHass, "_resetCardState");
    const applyHassNoHassSpy = vi
      .spyOn(elNoHass, "_applyHass")
      .mockResolvedValue();
    elNoHass.setConfig({ auto_fit: true, show_home: false });
    expect(applyHassNoHassSpy).not.toHaveBeenCalled();
    expect(resetNoHassSpy).toHaveBeenCalledWith();
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
    expect(form.computeLabel({ name: "show_pre_alert" })).toBe(
      "הצג הנחיות מקדימות",
    );
    expect(form.computeLabel({ name: "show_location" })).toBe("הצג מיקום");
    homeAssistant.remove();

    document.documentElement.lang = "en-US";
    expect(form.computeLabel({ name: "auto_fit" })).toBe(
      "Auto fit map to active alerts",
    );
    expect(form.computeLabel({ name: "show_home" })).toBe("Show home");
    expect(form.computeLabel({ name: "hebrew_basemap" })).toBe(
      "Hebrew basemap",
    );
    expect(form.computeLabel({ name: "show_pre_alert" })).toBe(
      "Show pre-alert",
    );
    expect(form.computeLabel({ name: "show_location" })).toBe("Show location");
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
      show_pre_alert: true,
      show_location: true,
    });
  });

  test("hass setter relies on applyHass to log failures", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("boom");
    vi.spyOn(el, "_performApplyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el.hass = createHass();
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map apply failed",
      "boom",
      error.stack,
      error,
    );
  });

  test("setConfig relies on applyHass to log failures", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("set-config boom");
    el._hass = createHass();
    vi.spyOn(el, "_performApplyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el.setConfig({ auto_fit: true, show_home: false });
    await waitForTasks();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map apply failed",
      "set-config boom",
      error.stack,
      error,
    );
  });

  test("hass setter refreshes areas on first load and tracked last_updated changes", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();
    const hass1 = createHass();
    const hass2 = createHass();
    const hass3 = createHass();

    el.hass = hass1;
    el.hass = hass2;
    el.hass = hass3;

    expect(applyHassSpy).toHaveBeenNthCalledWith(1);
    expect(applyHassSpy).toHaveBeenNthCalledWith(2);
    expect(applyHassSpy).toHaveBeenNthCalledWith(3);
  });

  test("hass setter passes through applyHass when tracked last_updated is unchanged", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();
    el._lastUpdated = "2026-03-24T10:00:00+00:00";

    el.hass = createHass();

    expect(applyHassSpy).toHaveBeenCalledWith();
  });

  test("refreshAreas keeps tracked last_updated unchanged when rendering cannot complete", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    el._hass = createHass({
      lastUpdateResponse: {
        last_update: "2026-03-24T10:00:00+00:00",
      },
      areasStatusResponse: {
        "Area A": {
          area: "Area A",
          date: "2026-03-13T08:05:00Z",
          emoji: "🚀",
          type: "alert",
        },
      },
    });
    vi.spyOn(el, "_createLayers").mockResolvedValue([]);

    await el._refreshAreas();

    expect(el._lastUpdated).toBeUndefined();
  });

  test("refreshAreas retries when last render did not advance tracked last_updated", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    el._hass = createHass({
      lastUpdateResponse: {
        last_update: "2026-03-24T10:00:00+00:00",
      },
      areasStatusResponse: {
        "New Area": {
          area: "New Area",
          date: "2026-03-13T09:05:00Z",
          emoji: "✈️",
          type: "alert",
        },
      },
    });
    const createLayersSpy = vi
      .spyOn(el, "_createLayers")
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: 1 }]);

    await el._refreshAreas();
    await el._refreshAreas();

    expect(createLayersSpy).toHaveBeenCalledTimes(2);
    expect(el._lastUpdated).toBe("2026-03-24T10:00:00+00:00");
  });

  test("getLastUpdate returns null when backend does not provide one", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    el._hass = createHass({
      lastUpdateResponse: {},
    });

    await expect(el._getLastUpdate()).resolves.toEqual({
      lastUpdated: null,
      version: null,
    });
  });

  test("applyHass refreshes areas through refreshAreas", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });
    el._hass = createHass();
    vi.spyOn(el, "_ensureMapCard").mockResolvedValue(mapCard);
    const refreshAreasSpy = vi.spyOn(el, "_refreshAreas").mockResolvedValue();

    await el._applyHass();

    expect(refreshAreasSpy).toHaveBeenCalledWith();
  });

  test("applyHass enables location by default and honors disabled config", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });
    el._hass = createHass();
    vi.spyOn(el, "_ensureMapCard").mockResolvedValue(mapCard);
    vi.spyOn(el, "_refreshAreas").mockResolvedValue();
    const startLocationWatchSpy = vi
      .spyOn(el, "_startLocationWatch")
      .mockResolvedValue();
    const stopLocationWatchSpy = vi
      .spyOn(el, "_stopLocationWatch")
      .mockImplementation(() => {});

    el._config = null;
    await el._applyHass();
    expect(startLocationWatchSpy).toHaveBeenCalledTimes(1);
    expect(stopLocationWatchSpy).not.toHaveBeenCalled();

    el._config = { show_location: false };
    await el._applyHass();
    expect(startLocationWatchSpy).toHaveBeenCalledTimes(2);
    expect(stopLocationWatchSpy).not.toHaveBeenCalled();
  });

  test("applyHass continues after a rejected queued apply", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    el._applyHassPromise = Promise.reject(new Error("previous failure"));
    const ensureMapCardSpy = vi
      .spyOn(el, "_ensureMapCard")
      .mockResolvedValue(null);

    await el._applyHass();

    expect(ensureMapCardSpy).toHaveBeenCalledWith();
  });

  test("applyHass keeps the queue alive when a run rejects", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const error = new Error("apply failed");
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(el, "_ensureMapCard").mockRejectedValue(error);

    await expect(el._applyHass()).resolves.toBeUndefined();
    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map apply failed",
      "apply failed",
      error.stack,
      error,
    );

    el._ensureMapCard.mockResolvedValueOnce(null);
    await expect(el._applyHass()).resolves.toBeUndefined();
    expect(el._ensureMapCard).toHaveBeenCalledTimes(2);
  });

  test("applyHass logs non-Error failures without throwing", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(el, "_performApplyHass").mockRejectedValue("plain failure");

    await expect(el._applyHass()).resolves.toBeUndefined();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map apply failed",
      "plain failure",
    );
  });

  test("applyHass logs message and stack for error-like objects", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const error = {
      message: "foreign failure",
      stack: "foreign-stack",
    };
    vi.spyOn(el, "_performApplyHass").mockRejectedValue(error);

    await expect(el._applyHass()).resolves.toBeUndefined();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map apply failed",
      "foreign failure",
      "foreign-stack",
      error,
    );
  });

  test("applyHass falls back to logging plain objects without message details", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const error = {
      code: 500,
      detail: "plain object failure",
    };
    vi.spyOn(el, "_performApplyHass").mockRejectedValue(error);

    await expect(el._applyHass()).resolves.toBeUndefined();

    expect(errorSpy).toHaveBeenCalledWith("oref-alert-map apply failed", error);
  });

  test("applyHass clears its inflight promise after normal completion", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    vi.spyOn(el, "_performApplyHass").mockResolvedValue(undefined);

    await el._applyHass();

    expect(el._applyHassPromise).toBeNull();
  });

  test("applyHass cleanup keeps a newer inflight promise intact", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();

    let resolveApply;
    const applyPromise = new Promise((resolve) => {
      resolveApply = resolve;
    });
    vi.spyOn(el, "_performApplyHass").mockReturnValue(applyPromise);

    const pendingApply = el._applyHass();
    const newerInflight = Promise.resolve();
    el._applyHassPromise = newerInflight;
    resolveApply();

    await pendingApply;

    expect(el._applyHassPromise).toBe(newerInflight);
  });

  test("bootstrap refresh retries every second during the first 10 seconds", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._startRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
    expect(applyHassSpy).toHaveBeenCalledWith();

    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    vi.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(applyHassSpy).toHaveBeenCalledTimes(2);
    expect(applyHassSpy).toHaveBeenLastCalledWith();
    expect(el._refreshId).not.toBeNull();
  });

  test("empty areas refresh is cleared on disconnect", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._startRefresh();
    expect(el._refreshId).not.toBeNull();

    el.disconnectedCallback();
    expect(el._refreshId).toBeNull();

    vi.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(applyHassSpy).not.toHaveBeenCalled();
  });

  test("empty areas refresh keeps errors inside applyHass", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const error = new Error("retry failed");
    vi.spyOn(el, "_performApplyHass").mockRejectedValue(error);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    el._startRefresh();
    vi.advanceTimersByTime(1000);
    await Promise.resolve();

    expect(errorSpy).toHaveBeenCalledWith(
      "oref-alert-map apply failed",
      "retry failed",
      error.stack,
      error,
    );
  });

  test("bootstrap refresh keeps retrying even after the map element appears", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._startRefresh();
    expect(el._refreshId).not.toBeNull();

    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;
    vi.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(applyHassSpy).toHaveBeenCalledTimes(1);
    expect(el._refreshId).not.toBeNull();
  });

  test("bootstrap refresh stops after 10 seconds when the map stays unavailable", async () => {
    await ensureDefined();
    vi.useFakeTimers();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    document.body.append(el);
    const applyHassSpy = vi.spyOn(el, "_applyHass").mockResolvedValue();

    el._startRefresh();
    expect(el._refreshId).not.toBeNull();

    vi.advanceTimersByTime(10_000);
    expect(el._refreshId).toBeNull();
    await Promise.resolve();
    const callsAtStop = applyHassSpy.mock.calls.length;

    vi.advanceTimersByTime(5_000);
    await Promise.resolve();
    expect(applyHassSpy).toHaveBeenCalledTimes(callsAtStop);
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
