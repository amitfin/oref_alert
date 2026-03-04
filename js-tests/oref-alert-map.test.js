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

    vi.spyOn(el, "_getPolygons").mockResolvedValue({ "Area A": [[1, 1]] });
    await expect(el._createLayers(["Area A"])).resolves.toEqual([]);

    window.L = { polygon: vi.fn() };
    el._getPolygons.mockResolvedValueOnce(null);
    await expect(el._createLayers(["Area A"])).resolves.toEqual([]);

    const created = [];
    window.L.polygon = vi.fn().mockImplementation((points, opts) => {
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

    const layers = await el._createLayers(["Area A", "Area B"]);
    expect(layers).toHaveLength(2);
    expect(window.L.polygon).toHaveBeenNthCalledWith(
      1,
      [
        [1, 1],
        [1, 2],
      ],
      { color: "#f19292" },
    );
    expect(window.L.polygon).toHaveBeenNthCalledWith(
      2,
      [
        [2, 1],
        [2, 2],
      ],
      { color: "#f19292" },
    );
    expect(created[0].bindTooltip).toHaveBeenCalledWith("Area A");
    expect(created[1].bindTooltip).toHaveBeenCalledWith("Area B");
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
        attributes: { source: "oref_alert", friendly_name: "Area B" },
      },
      "geo_location.a": {
        entity_id: "geo_location.a",
        attributes: { source: "oref_alert", friendly_name: "Area A" },
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
    expect(el._getOrefAreas()).toEqual(["Area A", "Area B"]);

    el._updateToken = 2;
    await el._applyHass(1);

    vi.spyOn(el, "_ensureMapCard").mockResolvedValue(null);
    await el._applyHass(2);

    el._mapCard = mapCard;
    el._ensureMapCard.mockResolvedValue(mapCard);
    el._areas = ["Area A", "Area B"];
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

    createLayersSpy.mockResolvedValue([{ id: 2 }]);
    el._updateToken = 4;
    await el._applyHass(4);
    expect(innerMap.layers).toEqual([{ id: 2 }]);
    expect(el._areas).toEqual(["Area A", "Area B"]);
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
