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

  test("loads polygons for oref geo_location entities, applies layers, and removes missing entities", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    const hassSetter = vi.fn();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(value) {
        hassSetter(value);
      },
    });

    window.loadCardHelpers = vi.fn().mockResolvedValue({
      createCardElement: vi.fn().mockResolvedValue(mapCard),
    });
    const createdLayers = [];
    window.L = {
      polygon: vi.fn().mockImplementation((points, opts) => {
        const layer = {
          points,
          opts,
          id: createdLayers.length + 1,
          bindTooltip: vi.fn(),
        };
        createdLayers.push(layer);
        return layer;
      }),
    };

    const loadPolygonSpy = vi
      .spyOn(el, "_loadPolygon")
      .mockImplementation(async (area) => {
        if (area === "Area A") {
          return [
            [1, 1],
            [1, 2],
            [2, 2],
            [2, 1],
          ];
        }
        if (area === "Area B") {
          return [
            [3, 3],
            [3, 4],
            [4, 4],
            [4, 3],
          ];
        }
        return null;
      });

    const hass1 = {
      states: {
        "geo_location.a": {
          entity_id: "geo_location.a",
          state: "ignored",
          attributes: { source: "oref_alert", friendly_name: "Area A" },
        },
        "geo_location.b": {
          entity_id: "geo_location.b",
          state: "ignored",
          attributes: { source: "oref_alert", friendly_name: "Area B" },
        },
        "geo_location.ignore_source": {
          entity_id: "geo_location.ignore_source",
          state: "Area C",
          attributes: { source: "other", friendly_name: "Area C" },
        },
        "sensor.ignore_domain": {
          entity_id: "sensor.ignore_domain",
          state: "Area D",
          attributes: { source: "oref_alert", friendly_name: "Area D" },
        },
      },
      connection: {},
    };
    el.hass = hass1;
    await el._mapCardPromise;
    await waitForTasks();

    expect(hassSetter).toHaveBeenCalled();
    expect(hassSetter).toHaveBeenLastCalledWith(hass1);
    expect(loadPolygonSpy).toHaveBeenCalledTimes(2);
    expect(loadPolygonSpy).toHaveBeenNthCalledWith(1, "Area A");
    expect(loadPolygonSpy).toHaveBeenNthCalledWith(2, "Area B");
    expect(window.L.polygon).toHaveBeenCalledTimes(2);
    expect(innerMap.layers).toHaveLength(2);
    expect(createdLayers[0].bindTooltip).toHaveBeenCalledWith("Area A");
    expect(createdLayers[1].bindTooltip).toHaveBeenCalledWith("Area B");

    const hass2 = {
      states: {
        "geo_location.b": {
          entity_id: "geo_location.b",
          state: "ignored",
          attributes: { source: "oref_alert", friendly_name: "Area B" },
        },
      },
      connection: {},
    };
    el.hass = hass2;
    await waitForTasks();

    expect(loadPolygonSpy).toHaveBeenCalledTimes(3);
    expect(loadPolygonSpy).toHaveBeenLastCalledWith("Area B");
    expect(innerMap.layers).toHaveLength(1);
    expect(innerMap.layers[0].points).toEqual([
      [3, 3],
      [3, 4],
      [4, 4],
      [4, 3],
    ]);
    expect(innerMap.layers[0].bindTooltip).toHaveBeenCalledWith("Area B");
  });

  test("loadPolygon uses cache and de-duplicates in-flight subscriptions", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const subscribers = [];
    const unsubscribe = vi.fn();
    const subscribeMessage = vi.fn().mockImplementation((cb) => {
      subscribers.push(cb);
      return Promise.resolve(unsubscribe);
    });
    el._hass = {
      connection: {
        subscribeMessage,
      },
    };

    const p1 = el._loadPolygon("Area A");
    const p2 = el._loadPolygon("Area A");
    expect(subscribeMessage).toHaveBeenCalledTimes(1);
    expect(el._polygonLoads.has("Area A")).toBe(true);

    subscribers[0]({
      result: [
        [1, 1],
        [1, 2],
        [2, 2],
        [2, 1],
      ],
    });
    await expect(Promise.all([p1, p2])).resolves.toEqual([
      [
        [1, 1],
        [1, 2],
        [2, 2],
        [2, 1],
      ],
      [
        [1, 1],
        [1, 2],
        [2, 2],
        [2, 1],
      ],
    ]);
    await waitForTasks();
    expect(unsubscribe).toHaveBeenCalledTimes(1);

    const fromCache = await el._loadPolygon("Area A");
    expect(subscribeMessage).toHaveBeenCalledTimes(1);
    expect(fromCache).toEqual([
      [1, 1],
      [1, 2],
      [2, 2],
      [2, 1],
    ]);

    const p3 = el._loadPolygon("Area B");
    subscribers[1]({
      result: [
        [9, 9],
        [9, 10],
        [10, 10],
        [10, 9],
      ],
    });
    await expect(p3).resolves.toEqual([
      [9, 9],
      [9, 10],
      [10, 10],
      [10, 9],
    ]);

    const p4 = el._loadPolygon("Area C");
    subscribers[2](undefined);
    await expect(p4).resolves.toBeNull();
    const p5 = el._loadPolygon("Area C");
    expect(subscribeMessage).toHaveBeenCalledTimes(4);
    subscribers[3]({
      result: [
        [7, 7],
        [7, 8],
        [8, 8],
        [8, 7],
      ],
    });
    await expect(p5).resolves.toEqual([
      [7, 7],
      [7, 8],
      [8, 8],
      [8, 7],
    ]);
  });

  test("handles map/leaflet absence and null payload safely", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    mapCard.shadowRoot.innerHTML = "";
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });

    window.loadCardHelpers = vi.fn().mockResolvedValue({
      createCardElement: vi.fn().mockResolvedValue(mapCard),
    });

    el.hass = {
      states: {
        "geo_location.a": {
          entity_id: "geo_location.a",
          state: "ignored",
          attributes: { source: "oref_alert", friendly_name: "Area A" },
        },
      },
      connection: {},
    };
    await el._mapCardPromise;
    await waitForTasks();

    const subscribers = [];
    const subscribeMessage = vi.fn().mockImplementation((cb) => {
      subscribers.push(cb);
      return Promise.resolve(() => {});
    });
    el._hass = { connection: { subscribeMessage } };
    const parsed = el._loadPolygon("Area X");
    subscribers[0](undefined);
    await expect(parsed).resolves.toBeNull();
  });

  test("covers stale-token exits and empty helpers", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();

    el._hass = null;
    expect(el._getOrefAreas()).toEqual([]);
    expect(await el._createLayers()).toEqual([]);

    const { mapCard, innerMap } = createMapCardWithInnerMap();
    const hassSetter = vi.fn();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(value) {
        hassSetter(value);
      },
    });
    el._mapCard = mapCard;
    el._hass = {
      states: {
        "geo_location.a": {
          entity_id: "geo_location.a",
          state: "ignored",
          attributes: { source: "oref_alert", friendly_name: "Area A" },
        },
      },
      connection: {},
    };
    el._updateToken = 2;
    await el._applyHass(1);
    expect(hassSetter).not.toHaveBeenCalled();

    const createLayersSpy = vi
      .spyOn(el, "_createLayers")
      .mockImplementation(async () => {
        el._updateToken = 3;
        return [{ id: 1 }];
      });
    el._updateToken = 2;
    await el._applyHass(2);
    expect(createLayersSpy).toHaveBeenCalled();
    expect(innerMap.layers).toBeUndefined();
  });

  test("ensureMapCard reuses in-flight promise and createLayers uses provided areas", async () => {
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
    const createCardElement = vi.fn().mockResolvedValue(mapCard);
    window.loadCardHelpers = vi.fn().mockResolvedValue({ createCardElement });
    el.layout = "panel";

    const p1 = el._ensureMapCard();
    const p2 = el._ensureMapCard();
    await Promise.all([p1, p2]);
    expect(createCardElement).toHaveBeenCalledTimes(1);
    expect(hassSetter).not.toHaveBeenCalled();
    expect(await el._ensureMapCard()).toBe(mapCard);
    expect(mapCard.layout).toBe("panel");

    window.L = {
      polygon: vi.fn().mockReturnValue({
        id: 1,
        bindTooltip: vi.fn(),
      }),
    };
    vi.spyOn(el, "_loadPolygon")
      .mockResolvedValueOnce([
        [1, 1],
        [1, 2],
        [2, 2],
        [2, 1],
      ])
      .mockResolvedValueOnce(null);
    el._areas = ["A", "B"];
    const layers = await el._createLayers(el._areas);
    expect(layers).toHaveLength(1);
    expect(layers[0]).toEqual(
      expect.objectContaining({ id: 1, bindTooltip: expect.any(Function) }),
    );
    expect(window.L.polygon).toHaveBeenCalledTimes(1);
  });

  test("forwards layout to an existing map card", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    el._mapCard = mapCard;

    el.layout = "panel";
    expect(mapCard.layout).toBe("panel");

    el.layout = "masonry";
    expect(mapCard.layout).toBe("masonry");
  });

  test("ensureMapCard retries after a transient create failure", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();
    const createCardElement = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce(mapCard);
    window.loadCardHelpers = vi.fn().mockResolvedValue({ createCardElement });

    await expect(el._ensureMapCard()).rejects.toThrow("transient");
    await expect(el._ensureMapCard()).resolves.toBe(mapCard);
    expect(createCardElement).toHaveBeenCalledTimes(2);
  });

  test("returns early when areas unchanged and throws when subscribeMessage is missing", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard, innerMap } = createMapCardWithInnerMap();
    Object.defineProperty(mapCard, "hass", {
      configurable: true,
      set(_) {},
    });
    el._mapCard = mapCard;
    el._hass = {
      states: {
        "geo_location.a": {
          entity_id: "geo_location.a",
          state: "ignored",
          attributes: { source: "oref_alert", friendly_name: "Area A" },
        },
      },
      connection: {},
    };
    el._areas = ["Area A"];
    const createLayersSpy = vi.spyOn(el, "_createLayers");
    el._updateToken = 1;
    await el._applyHass(1);
    expect(createLayersSpy).not.toHaveBeenCalled();
    expect(innerMap.layers).toBeUndefined();

    el._hass = { connection: {} };
    await expect(
      el._loadPolygon(`Area Missing Subscribe ${Date.now()}`),
    ).rejects.toThrow(TypeError);
  });

  test("set hass catches update errors and logs them", async () => {
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

  test("createLayers skips null polygons and warns when layer creation fails", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    window.L = {
      polygon: vi
        .fn()
        .mockImplementationOnce(() => {
          throw new Error("bad layer");
        })
        .mockImplementationOnce(() => ({
          id: 2,
          bindTooltip: vi.fn(),
        })),
    };
    vi.spyOn(el, "_loadPolygon")
      .mockResolvedValueOnce([
        [1, 1],
        [1, 2],
        [2, 2],
        [2, 1],
      ])
      .mockResolvedValueOnce([
        [3, 3],
        [3, 4],
        [4, 4],
        [4, 3],
      ])
      .mockResolvedValueOnce(null);

    const layers = await el._createLayers(["Area A", "Area B", "Area C"]);
    expect(window.L.polygon).toHaveBeenCalledTimes(2);
    expect(layers).toHaveLength(1);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0][0]).toContain("Area A");
  });

  test("supports getCardSize/getGridOptions/setConfig and define guard", async () => {
    await ensureDefined();
    const Card = customElements.get("oref-alert-map");
    const el = new Card();
    const { mapCard } = createMapCardWithInnerMap();

    expect(() => el.setConfig({ title: "ignored" })).not.toThrow();
    expect(el.getCardSize()).toBe(7);
    expect(el.getGridOptions()).toEqual({
      columns: "full",
      rows: 4,
      min_columns: 6,
      min_rows: 2,
    });

    el._mapCard = mapCard;
    expect(el.getCardSize()).toBe(3);
    expect(el.getGridOptions()).toEqual({
      columns: 12,
      rows: 6,
      min_columns: 6,
      min_rows: 3,
    });

    vi.resetModules();
    window.customCards = [];
    const defineSpy = vi.spyOn(customElements, "define");
    await import("../custom_components/oref_alert/cards/oref-alert-map.js");
    expect(defineSpy).not.toHaveBeenCalled();
  });
});
