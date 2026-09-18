import { ToolTrace } from "./ToolTrace";
import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { api } from "./api";
import { useModelCapabilities } from "./modelCapabilities";
import { SettingsPanel } from "./SettingsPanel";
import { FlightDeck } from "./FlightDeck";
import { AlertsPanel } from "./AlertsPanel";
import { FencePanel } from "./FencePanel";
import { WatchPanel } from "./WatchPanel";
import { MissionWorkflow } from "./MissionWorkflow";
import { taskStarters } from "./missionFlow.mjs";
import { registerGroundStationTools } from "./webmcp";
import * as maplibregl from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import {
  Map as MapIcon,
  SlidersHorizontal,
  FileText,
  FlaskConical,
  Settings,
  Send,
  Plus,
  Undo2,
  Upload,
  ShieldCheck,
  Radio,
  Play,
  Square,
  LocateFixed,
  Satellite,
  Layers,
  AlertTriangle,
  Check,
  Download,
  Trash2,
  RefreshCw,
  ChevronDown,
  Sparkles,
  MessageSquare,
} from "lucide-react";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";

maplibregl.setWorkerUrl(mapWorkerUrl);

type Json = any;

const fmt = (v: any, n = 1) => (v == null ? "—" : Number(v).toFixed(n));
const clock = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
const commands: any = {
  16: "Waypoint",
  17: "Loiter unlimited",
  19: "Loiter time",
  20: "Return home",
  21: "Land",
  22: "Takeoff",
  178: "Change speed",
};
const uid = () => crypto.randomUUID().slice(0, 10);
function download(name: string, data: Json) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function MapView({
  vehicle,
  vehicles,
  onSelectVehicle,
  draft,
  active,
  editing,
  onAdd,
  onMove,
  selected,
  setSelected,
  home,
  historical,
  onSaveAreas,
  proposal,
  captureRef,
}: Json) {
  const el = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map>(null),
    markers = useRef<maplibregl.Marker[]>([]),
    vehicleMarkers = useRef<Record<string, maplibregl.Marker>>({}),
    cueMarkers = useRef<Record<string, maplibregl.Marker>>({}),
    centered = useRef(false);
  const [areaEdit, setAreaEdit] = useState<Json>(null),
    [areaBusy, setAreaBusy] = useState(false),
    [areaError, setAreaError] = useState("");
  const props = useRef<Json>({});
  props.current = {
    vehicle,
    draft,
    editing,
    onAdd,
    onMove,
    setSelected,
    onSelectVehicle,
    areaEdit,
    areaBusy,
  };
  const renderMap = useRef<() => void>(() => {});
  const [sat, setSat] = useState(true),
    [mapError, setMapError] = useState("");
  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!,
      center: [home.lon, home.lat],
      zoom: 16,
      canvasContextAttributes: { preserveDrawingBuffer: true },
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          sat: {
            type: "raster",
            tiles: [
              "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
          },
          street: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [
          { id: "sat", type: "raster", source: "sat" },
          {
            id: "street",
            type: "raster",
            source: "street",
            layout: { visibility: "none" },
          },
        ],
      },
    });
    map.current = m;
    const resizeObserver = new ResizeObserver(() => m.resize());
    resizeObserver.observe(el.current!);
    m.addControl(
      new maplibregl.NavigationControl({ showCompass: true }),
      "bottom-left",
    );
    m.on("click", (e) => {
      if (props.current.areaEdit && !props.current.areaBusy) {
        setAreaEdit((a: Json) => ({
          ...a,
          points: [...a.points, [e.lngLat.lng, e.lngLat.lat]],
        }));
      } else if (props.current.editing && !props.current.areaBusy)
        props.current.onAdd(e.lngLat.lat, e.lngLat.lng);
    });
    m.on("error", () =>
      setMapError(
        "Basemap unavailable. Coordinates and mission editing still work.",
      ),
    );
    m.on("load", () => {
      m.addSource("route", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addSource("areas", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "area-fill",
        type: "fill",
        source: "areas",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": [
            "match",
            ["get", "kind"],
            "inclusion",
            "#58c9ff",
            "proposal-inclusion",
            "#c69bff",
            "onboard-inclusion",
            "#ffc46d",
            "proposal",
            "#c69bff",
            "onboard",
            "#ffc46d",
            "#ff6d65",
          ],
          "fill-opacity": 0.24,
        },
      });
      m.addLayer({
        id: "area-outline",
        type: "line",
        source: "areas",
        paint: {
          "line-color": [
            "match",
            ["get", "kind"],
            "inclusion",
            "#58c9ff",
            "proposal-inclusion",
            "#c69bff",
            "onboard-inclusion",
            "#ffc46d",
            "proposal",
            "#c69bff",
            "onboard",
            "#ffc46d",
            "#ff6d65",
          ],
          "line-width": 3,
          "line-dasharray": [3, 1],
        },
      });
      m.addLayer({
        id: "exclusions",
        type: "fill",
        source: "route",
        filter: ["==", ["get", "kind"], "exclusion"],
        paint: { "fill-color": "#ff6d65", "fill-opacity": 0.23 },
      });
      m.addLayer({
        id: "onboard-fence",
        type: "line",
        source: "route",
        filter: ["==", ["get", "kind"], "fence"],
        paint: {
          "line-color": "#ffc46d",
          "line-width": 3,
          "line-dasharray": [3, 2],
        },
      });
      m.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        filter: [
          "all",
          ["==", ["geometry-type"], "LineString"],
          ["!=", ["get", "kind"], "fence"],
        ],
        paint: {
          "line-color": [
            "case",
            ["==", ["get", "kind"], "active"],
            "#e8b76a",
            "#54e1d0",
          ],
          "line-width": 3,
          "line-dasharray": [2, 1],
        },
      });
      m.addSource("navigation-cue", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "navigation-stick",
        type: "line",
        source: "navigation-cue",
        filter: ["==", ["get", "kind"], "target"],
        paint: {
          "line-color": "#fff0ad",
          "line-width": 3,
          "line-dasharray": [4, 2],
        },
      });
      m.addLayer({
        id: "navigation-carrot",
        type: "line",
        source: "navigation-cue",
        filter: ["==", ["get", "kind"], "carrot"],
        paint: { "line-color": "#ff9b54", "line-width": 4 },
      });
      renderMap.current();
    });
    return () => {
      markers.current.forEach((x) => x.remove());
      Object.values(vehicleMarkers.current).forEach((marker) =>
        marker.remove(),
      );
      Object.values(cueMarkers.current).forEach((marker) => marker.remove());
      resizeObserver.disconnect();
      m.remove();
    };
  }, []);
  const updateMap = () => {
    const m = map.current;
    if (!m?.getSource("route")) return;
    const features: Json[] = [];
    for (const [kind, plan] of [
      ["draft", draft],
      ["active", active],
    ] as any) {
      const pts =
        plan?.waypoints
          ?.filter((w: Json) => [16, 17, 19, 21, 22].includes(w.command))
          .map((w: Json) => [w.lon, w.lat]) || [];
      if (pts.length > 1)
        features.push({
          type: "Feature",
          properties: { kind },
          geometry: { type: "LineString", coordinates: pts },
        });
    }
    if (historical?.points?.length > 1)
      features.push({
        type: "Feature",
        properties: { kind: "active" },
        geometry: {
          type: "LineString",
          coordinates: historical.points.map((p: Json) => [p.lon, p.lat]),
        },
      });
    const areas: Json[] = [];
    const addArea = (ring: Json, kind: string) => {
      if (ring.length < 2) return;
      areas.push({
        type: "Feature",
        properties: { kind },
        geometry:
          ring.length > 2
            ? { type: "Polygon", coordinates: [[...ring, ring[0]]] }
            : { type: "LineString", coordinates: ring },
      });
    };
    for (const type of ["exclusion", "inclusion"]) {
      (draft?.intent?.[type + "s"] || []).forEach((ring: Json, i: number) => {
        if (!(areaEdit?.index === i && areaEdit?.kind === type))
          addArea(ring, type === "inclusion" ? "inclusion" : "draft");
      });
      (proposal?.[type + "s"] || []).forEach((ring: Json) =>
        addArea(ring, type === "inclusion" ? "proposal-inclusion" : "proposal"),
      );
    }
    if (vehicle?.fence?.enabled && vehicle.fence.polygon)
      (vehicle.fence.polygons || []).forEach((ring: Json) =>
        addArea(ring, "onboard"),
      );
    if (vehicle?.fence?.enabled && vehicle.fence.polygon)
      (vehicle.fence.inclusions || []).forEach((ring: Json) =>
        addArea(ring, "onboard-inclusion"),
      );
    if (areaEdit)
      addArea(
        areaEdit.points,
        areaEdit.kind === "inclusion" ? "inclusion" : "drawing",
      );
    (m.getSource("areas") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: areas,
    });
    if (
      vehicle?.home &&
      vehicle?.fence?.enabled &&
      vehicle.fence.circle &&
      vehicle.fence.radius
    ) {
      const rad = Math.PI / 180,
        lat = vehicle.home.lat * rad,
        lon = vehicle.home.lon * rad;
      const distance = vehicle.fence.radius / 6371000;
      const ring = Array.from({ length: 97 }, (_, i) => {
        const bearing = (i / 96) * Math.PI * 2;
        const y = Math.asin(
          Math.sin(lat) * Math.cos(distance) +
            Math.cos(lat) * Math.sin(distance) * Math.cos(bearing),
        );
        const x =
          lon +
          Math.atan2(
            Math.sin(bearing) * Math.sin(distance) * Math.cos(lat),
            Math.cos(distance) - Math.sin(lat) * Math.sin(y),
          );
        return [x / rad, y / rad];
      });
      features.push({
        type: "Feature",
        properties: { kind: "fence" },
        geometry: { type: "LineString", coordinates: ring },
      });
    }
    (m.getSource("route") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features,
    });
    markers.current.forEach((x) => x.remove());
    markers.current = [];
    if (vehicle?.home) {
      const h = document.createElement("div");
      h.className = "home-pin";
      h.textContent = "H";
      h.title = "Reported vehicle home";
      markers.current.push(
        new maplibregl.Marker({ element: h })
          .setLngLat([vehicle.home.lon, vehicle.home.lat])
          .addTo(m),
      );
    }
    for (const [i, w] of (draft?.waypoints || []).entries()) {
      if (![16, 17, 19, 21, 22].includes(w.command)) continue;
      const b = document.createElement("button");
      b.className = "waypoint-pin" + (selected === w.id ? " selected" : "");
      b.textContent = String(i + 1);
      b.title = `${commands[w.command]} · ${w.alt} m`;
      b.onclick = (e) => {
        e.stopPropagation();
        setSelected(w.id);
      };
      const marker = new maplibregl.Marker({
        element: b,
        draggable: editing && !areaEdit && !areaBusy,
      })
        .setLngLat([w.lon, w.lat])
        .addTo(m);
      marker.on("dragend", () => {
        const p = marker.getLngLat();
        props.current.onMove(w.id, p.lat, p.lng);
      });
      markers.current.push(marker);
    }
    (areaEdit?.points || []).forEach((point: Json, index: number) => {
      const element = document.createElement("button");
      element.className = "area-vertex";
      element.textContent = String(index + 1);
      element.title = `Boundary vertex ${index + 1} · drag to adjust`;
      element.onclick = (e) => e.stopPropagation();
      const marker = new maplibregl.Marker({ element, draggable: !areaBusy })
        .setLngLat(point)
        .addTo(m);
      marker.on("dragend", () => {
        const p = marker.getLngLat();
        setAreaEdit(
          (a: Json) =>
            a && {
              ...a,
              points: a.points.map((q: Json, i: number) =>
                i === index ? [p.lng, p.lat] : q,
              ),
            },
        );
      });
      markers.current.push(marker);
    });
    updateVehicle();
  };
  const visibleVehicles = historical
    ? [{ ...vehicle, id: "replay", position: historical.snapshot?.position }]
    : (vehicles || [vehicle]).filter(Boolean);
  const validPosition = (p: Json) =>
    p &&
    Number.isFinite(p.lat) &&
    Number.isFinite(p.lon) &&
    Math.abs(p.lat) <= 90 &&
    Math.abs(p.lon) <= 180;
  const updateVehicle = () => {
    const m = map.current;
    if (!m?.getSource("route")) return;
    const cue = historical ? null : vehicle?.navigation_cue;
    const cueFeatures: any[] = [];
    for (const kind of ["target", "carrot"]) {
      const point = cue?.[kind];
      if (
        !point ||
        vehicle?.position_valid === false ||
        !validPosition(vehicle?.position)
      ) {
        cueMarkers.current[kind]?.remove();
        delete cueMarkers.current[kind];
        continue;
      }
      cueFeatures.push({
        type: "Feature",
        properties: { kind },
        geometry: {
          type: "LineString",
          coordinates: [
            [vehicle.position.lon, vehicle.position.lat],
            [point.lon, point.lat],
          ],
        },
      });
      if (!cueMarkers.current[kind]) {
        const element = document.createElement("div");
        element.className = `navigation-pin ${kind}`;
        element.textContent = kind === "target" ? "⊕" : "◆";
        cueMarkers.current[kind] = new maplibregl.Marker({ element })
          .setLngLat([point.lon, point.lat])
          .addTo(m);
      }
      cueMarkers.current[kind].setLngLat([point.lon, point.lat]);
      cueMarkers.current[kind].getElement().title = point.source;
    }
    (m.getSource("navigation-cue") as maplibregl.GeoJSONSource)?.setData({
      type: "FeatureCollection",
      features: cueFeatures,
    });
    const ids = new Set<string>();
    for (const v of visibleVehicles) {
      if (!validPosition(v.position) || v.position_valid === false) continue;
      const id = v.id || "selected";
      ids.add(id);
      let marker = vehicleMarkers.current[id];
      if (!marker) {
        const element = document.createElement("button");
        element.type = "button";
        element.className = "vehicle-pin";
        const arrow = document.createElement("span");
        arrow.className = "vehicle-arrow";
        arrow.textContent = "▲";
        const label = document.createElement("span");
        label.className = "vehicle-label";
        element.append(arrow, label);
        element.onclick = (e) => {
          e.stopPropagation();
          if (!historical) props.current.onSelectVehicle?.(id);
        };
        marker = new maplibregl.Marker({ element })
          .setLngLat([v.position.lon, v.position.lat])
          .addTo(m);
        vehicleMarkers.current[id] = marker;
      }
      const element = marker.getElement();
      element.className =
        "vehicle-pin" +
        (v.id === vehicle?.id || historical ? " current" : "") +
        (!historical && (v.heartbeat_age > 3 || v.gps_fix < 3) ? " stale" : "");
      element.setAttribute(
        "aria-label",
        `${v.profile || "Vehicle"} ${id.slice(0, 4)} position`,
      );
      element.title = `${v.profile || "Vehicle"} ${id.slice(0, 4)} · ${v.position.lat.toFixed(6)}, ${v.position.lon.toFixed(6)} · ${fmt(v.position.relative)} m above home`;
      (element.querySelector(".vehicle-arrow") as HTMLElement).style.transform =
        `rotate(${v.heading || 0}deg)`;
      element.querySelector(".vehicle-label")!.textContent =
        `${(v.profile || "replay").toUpperCase()} ${historical ? "" : id.slice(0, 4)}`;
      marker.setLngLat([v.position.lon, v.position.lat]);
    }
    for (const [id, marker] of Object.entries(vehicleMarkers.current))
      if (!ids.has(id)) {
        marker.remove();
        delete vehicleMarkers.current[id];
      }
    const position = historical
      ? historical.snapshot?.position_valid
        ? historical.snapshot.position
        : null
      : vehicle?.position_valid
        ? vehicle.position
        : null;
    if (!centered.current && validPosition(position)) {
      m.jumpTo({ center: [position.lon, position.lat], zoom: 17 });
      centered.current = true;
    }
  };
  renderMap.current = () => {
    updateMap();
    updateVehicle();
  };
  useEffect(updateMap, [
    draft,
    active,
    vehicle?.home?.lat,
    vehicle?.home?.lon,
    vehicle?.fence?.radius,
    vehicle?.fence?.enabled,
    vehicle?.fence?.circle,
    editing,
    selected,
    historical,
    areaEdit,
    areaBusy,
    proposal,
    JSON.stringify(vehicle?.fence?.polygons),
    vehicle?.fence?.polygon,
  ]);
  useEffect(() => {
    if (!editing) setAreaEdit(null);
    map.current
      ?.getCanvas()
      .style.setProperty("cursor", areaEdit ? "crosshair" : "");
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !areaBusy) {
        setAreaEdit(null);
        setAreaError("");
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [editing, areaEdit, areaBusy]);
  useEffect(() => {
    if (!captureRef) return;
    captureRef.current = async () => {
      const m = map.current;
      if (!m || !m.loaded() || areaEdit)
        throw Error("Finish drawing and wait for map tiles before attaching.");
      m.jumpTo({ bearing: 0, pitch: 0 });
      await new Promise<void>((resolve) => {
        m.once("render", () => resolve());
        m.triggerRepaint();
      });
      const source = m.getCanvas(),
        canvas = document.createElement("canvas");
      const scale = Math.min(1, 1280 / source.width, 1280 / source.height);
      canvas.width = Math.round(source.width * scale);
      canvas.height = Math.round(source.height * scale);
      const context = canvas.getContext("2d")!;
      context.drawImage(source, 0, 0, canvas.width, canvas.height);
      // Pixel grid gives vision models explicit image-space reference points.
      context.font = "12px monospace";
      for (let x = 0; x < canvas.width; x += 100)
        for (let y = 0; y < canvas.height; y += 100) {
          context.fillStyle = "#14202bcc";
          context.fillRect(x, y, 76, 18);
          context.fillStyle = "#ffffff";
          context.fillText(`${x},${y}`, x + 3, y + 13);
        }
      context.fillStyle = "#14202bee";
      context.fillRect(0, canvas.height - 22, canvas.width, 22);
      context.fillStyle = "#ffffff";
      context.fillText(
        sat
          ? "Imagery © Esri, Maxar, Earthstar Geographics"
          : "© OpenStreetMap contributors",
        8,
        canvas.height - 7,
      );
      const b = m.getBounds();
      return {
        vehicle_id: vehicle.id,
        draft_revision: draft.revision,
        captured_at: Date.now() / 1000,
        image: canvas.toDataURL("image/png"),
        width: canvas.width,
        height: canvas.height,
        bounds: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
      };
    };
    return () => {
      captureRef.current = null;
    };
  }, [captureRef, vehicle?.id, draft?.revision, areaEdit, sat]);
  const saveAreas = async (
    areas: Json,
    revision: number,
    kind = "exclusion",
  ) => {
    setAreaBusy(true);
    setAreaError("");
    try {
      await onSaveAreas(areas, revision, kind);
      setAreaEdit(null);
    } catch (e: any) {
      setAreaError(e.message);
    } finally {
      setAreaBusy(false);
    }
  };
  useEffect(updateVehicle, [vehicles, vehicle, historical]);
  useEffect(() => {
    const m = map.current;
    if (m?.getLayer("sat")) {
      m.setLayoutProperty("sat", "visibility", sat ? "visible" : "none");
      m.setLayoutProperty("street", "visibility", sat ? "none" : "visible");
    }
  }, [sat]);
  return (
    <div className="map-wrap">
      <div className="map" ref={el} />
      <div className="map-top">
        <span className="map-tag">
          <span className="dot" />
          {historical
            ? "HISTORICAL REPLAY"
            : editing
              ? areaEdit
                ? `${areaEdit.kind.toUpperCase()} AREA · CLICK CORNERS`
                : "MISSION EDITOR · CLICK TO ADD"
              : "LIVE OPERATIONS"}
        </span>
        <div className="map-buttons">
          {editing &&
            draft &&
            ["inclusion", "exclusion"].map((kind) => (
              <button
                key={kind}
                disabled={areaBusy || !!areaEdit}
                onClick={() => {
                  setAreaEdit({
                    kind,
                    index: -1,
                    points: [],
                    revision: draft.revision,
                  });
                  setAreaError("");
                }}
              >
                Draw {kind} area
              </button>
            ))}
          <button onClick={() => setSat(!sat)} title="Switch basemap">
            {sat ? <Satellite size={16} /> : <Layers size={16} />}{" "}
            {sat ? "Satellite" : "Street"}
          </button>
          <button
            title="Center vehicle"
            disabled={!historical && !vehicle?.position_valid}
            onClick={() => {
              const p =
                historical?.snapshot?.position || vehicle?.position || home;
              map.current?.flyTo({ center: [p.lon, p.lat], zoom: 16 });
            }}
          >
            <LocateFixed size={17} /> Locate vehicle
          </button>
          {!historical && (
            <button
              onClick={() => {
                const points = visibleVehicles.filter(
                  (v: Json) =>
                    validPosition(v.position) && v.position_valid !== false,
                );
                if (!points.length) return;
                const bounds = new maplibregl.LngLatBounds();
                points.forEach((v: Json) =>
                  bounds.extend([v.position.lon, v.position.lat]),
                );
                map.current?.fitBounds(bounds, { padding: 90, maxZoom: 18 });
              }}
            >
              Fit all ({visibleVehicles.length})
            </button>
          )}
        </div>
      </div>
      {mapError && <div className="map-error">{mapError}</div>}
      {editing &&
        (areaEdit ||
          draft?.intent?.exclusions?.length > 0 ||
          draft?.intent?.inclusions?.length > 0 ||
          areaError) && (
          <div className="map-area-tools">
            {areaEdit ? (
              <>
                <strong>
                  {areaEdit.index < 0
                    ? `Draw ${areaEdit.kind} area`
                    : `Edit ${areaEdit.kind} ${areaEdit.index + 1}`}{" "}
                  · {areaEdit.points.length} vertices
                </strong>
                <span>
                  Click corners; drag a vertex to adjust. Finish closes the
                  boundary.
                </span>
                {areaEdit.revision !== draft?.revision && (
                  <span className="error">
                    Draft changed. Cancel and start again.
                  </span>
                )}
                <div className="button-row">
                  <button
                    className="primary"
                    disabled={
                      areaBusy ||
                      areaEdit.points.length < 3 ||
                      areaEdit.revision !== draft?.revision
                    }
                    onClick={() => {
                      const rings = [
                        ...(draft.intent[areaEdit.kind + "s"] || []),
                      ];
                      if (areaEdit.index < 0) rings.push(areaEdit.points);
                      else rings[areaEdit.index] = areaEdit.points;
                      void saveAreas(rings, areaEdit.revision, areaEdit.kind);
                    }}
                  >
                    {areaBusy ? "Saving…" : "Finish area"}
                  </button>
                  <button
                    disabled={areaBusy || !areaEdit.points.length}
                    onClick={() =>
                      setAreaEdit({
                        ...areaEdit,
                        points: areaEdit.points.slice(0, -1),
                      })
                    }
                  >
                    Undo vertex
                  </button>
                  <button
                    disabled={areaBusy}
                    onClick={() => {
                      setAreaEdit(null);
                      setAreaError("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <details className="area-manager">
                <summary>
                  Manage areas ·{" "}
                  {(draft?.intent?.exclusions?.length || 0) +
                    (draft?.intent?.inclusions?.length || 0)}{" "}
                  in draft
                </summary>
                <div className="area-list">
                  {["inclusion", "exclusion"].flatMap((kind) =>
                    (draft?.intent?.[kind + "s"] || []).map(
                      (ring: Json, index: number) => (
                        <div key={kind + index}>
                          <button
                            disabled={areaBusy}
                            onClick={() => {
                              const bounds = new maplibregl.LngLatBounds();
                              ring.forEach((p: Json) => bounds.extend(p));
                              map.current?.fitBounds(bounds, {
                                padding: 60,
                                maxZoom: 19,
                              });
                              setAreaEdit({
                                kind,
                                index,
                                points: ring.map((p: Json) => [...p]),
                                revision: draft.revision,
                              });
                              setAreaError("");
                            }}
                          >
                            Edit {kind} {index + 1} · {ring.length} corners
                          </button>
                          <button
                            disabled={areaBusy}
                            aria-label={`Remove ${kind} ${index + 1}`}
                            onClick={() =>
                              void saveAreas(
                                draft.intent[kind + "s"].filter(
                                  (_: Json, i: number) => i !== index,
                                ),
                                draft.revision,
                                kind,
                              )
                            }
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ),
                    ),
                  )}
                </div>
                <span>
                  Blue: inclusion · Red: exclusion · Purple: proposal · Amber:
                  onboard
                </span>
              </details>
            )}
            {areaError && (
              <span role="alert" className="error">
                {areaError}
              </span>
            )}
          </div>
        )}
      <div className="map-position">
        {(historical
          ? historical.snapshot?.position_valid
          : vehicle?.position_valid) &&
        validPosition(historical?.snapshot?.position || vehicle?.position)
          ? `${vehicle?.profile?.toUpperCase() || "VEHICLE"} ${vehicle?.id?.slice(0, 4) || ""} · ${fmt((historical?.snapshot?.position || vehicle.position).lat, 6)}, ${fmt((historical?.snapshot?.position || vehicle.position).lon, 6)} · ${fmt((historical?.snapshot?.position || vehicle.position).relative)} m relative${!historical && vehicle?.gps_fix < 3 ? " · waiting for GPS fix" : ""}`
          : "Waiting for a valid vehicle position…"}
      </div>
      {vehicle?.fence?.enabled && vehicle.fence.circle && (
        <div className="map-fence-label">
          Onboard fence · {vehicle.fence.radius} m radius
          {vehicle.fence.max_alt != null
            ? ` · ${vehicle.fence.max_alt} m ceiling`
            : ""}
        </div>
      )}
      {!historical && vehicle?.navigation_cue && (
        <div className="navigation-legend">
          {vehicle.navigation_cue.target && (
            <span>⊕ {vehicle.navigation_cue.target.source}</span>
          )}
          {vehicle.navigation_cue.carrot && (
            <span className="carrot-label">
              ◆ Projected nav bearing ·{" "}
              {fmt(vehicle.navigation_cue.carrot.bearing, 0)}°
            </span>
          )}
          {vehicle.navigation_cue.wp_distance != null && (
            <span>
              WP distance {fmt(vehicle.navigation_cue.wp_distance, 0)} m
            </span>
          )}
        </div>
      )}
      <div className="map-note">
        {areaEdit
          ? "Drawing changes the local draft only."
          : editing
            ? "Drag a waypoint to revise the draft."
            : "Imagery is not obstacle sensing."}
      </div>
    </div>
  );
}

function App() {
  const [config, setConfig] = useState<Json>(null),
    [vehicles, setVehicles] = useState<Json[]>([]),
    [vid, setVid] = useState(""),
    [tab, setTab] = useState("flight");
  const [sidePanel, setSidePanel] = useState("chat");
  const [wsState, setWsState] = useState(false),
    [work, setWorkState] = useState<Json>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState("");
  const [selected, setSelected] = useState(""),
    [jobs, setJobs] = useState<Json[]>([]),
    [params, setParamsState] = useState<Json>(null),
    [search, setSearch] = useState(""),
    [staged, setStaged] = useState<Json>({});
  const [chat, setChat] = useState(""),
    [editAuthorized, setEditAuthorized] = useState(false),
    [interactionMode, setInteractionMode] = useState(true),
    [interactionTargets, setInteractionTargets] = useState<string[]>([]),
    [launchProfile, setLaunchProfile] = useState("copter"),
    [launchCount, setLaunchCount] = useState(1),
    [chatBusy, setChatBusy] = useState(false);
  const [events, setEvents] = useState<Json[]>([]),
    [messages, setMessages] = useState<Json[]>([]),
    [recordings, setRecordings] = useState<Json[]>([]),
    [replay, setReplay] = useState<Json>(null),
    [replayId, setReplayId] = useState("");
  const [scenario, setScenario] = useState("gps_loss"),
    [duration, setDuration] = useState(60),
    [seed, setSeed] = useState(1),
    [track, setTrack] = useState("telemetry");
  const [control, setControl] = useState(false),
    [logEntries, setLogEntries] = useState<Json[]>([]);
  const [evidence, setEvidence] = useState<Json>(null);
  const chatInput = useRef<HTMLTextAreaElement>(null);
  const captureMap = useRef<null | (() => Promise<Json>)>(null);
  const [mapAttachment, setMapAttachment] = useState<Json>(null);
  const modelCapabilities = useModelCapabilities(config);
  const mapModelBlocked =
    modelCapabilities?.vision === false || modelCapabilities?.tools === false;
  const selectedVehicleRef = useRef(vid);
  selectedVehicleRef.current = vid;
  const setWork = (data: Json) => {
    if (data === null || data.vehicle_id === selectedVehicleRef.current)
      setWorkState((previous: Json) =>
        data &&
        previous?.vehicle_id === data.vehicle_id &&
        previous.draft.revision > data.draft.revision
          ? previous
          : data,
      );
  };
  const setParams = (data: Json) => {
    if (data === null || data.vehicle_id === selectedVehicleRef.current)
      setParamsState(data);
  };
  useEffect(
    () =>
      registerGroundStationTools({
        readState: async () => ({
          selected_vehicle: selectedVehicleRef.current,
          vehicles: await api("/vehicles"),
        }),
        readWorkspace: async () => {
          const id = selectedVehicleRef.current;
          if (!id) throw Error("Select a vehicle first");
          return api(`/vehicles/${id}/workspace`);
        },
        stageDraft: async (expected_revision, draft) => {
          const id = selectedVehicleRef.current;
          if (!id) throw Error("Select a vehicle first");
          const data = await api(`/vehicles/${id}/draft`, "PUT", {
            expected_revision,
            draft,
          });
          flushSync(() => {
            setWork(data);
            setTab("plan");
          });
          return {
            vehicle_id: id,
            revision: data.draft.revision,
            checks: data.checks,
          };
        },
      }),
    [],
  );
  const current = vehicles.find((v) => v.id === vid),
    draft = work?.draft,
    profile = config?.profiles[current?.profile],
    chatBottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (current && work?.vehicle_id === current.id)
      void refresh(current.id).catch((e: Error) => setError(e.message));
  }, [
    current?.id,
    current?.draft_revision,
    current?.active_revision,
    current?.epoch,
    current?.agent_run?.status,
  ]);
  const guard = async (fn: () => Promise<any>, label = "") => {
    setError("");
    if (label) setBusy(label);
    try {
      return await fn();
    } catch (e: any) {
      setError(e.message);
    } finally {
      if (label) setBusy("");
    }
  };
  const refresh = async (id = vid) => {
    if (id) setWork(await api(`/vehicles/${id}/workspace`));
  };
  useEffect(() => {
    api("/bootstrap")
      .then(setConfig)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!config) return;
    let socket: WebSocket,
      timer: any,
      closed = false;
    const connect = () => {
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`,
      );
      socket.onopen = () => setWsState(true);
      socket.onmessage = (e) => {
        const data = JSON.parse(e.data);
        setVehicles(data.vehicles);
        setJobs(data.jobs);
        if (data.configuration)
          setConfig((old: any) =>
            old &&
            old.settings_revision !== data.configuration.settings_revision
              ? { ...old, ...data.configuration }
              : old,
          );
      };
      socket.onclose = () => {
        setWsState(false);
        if (!closed) timer = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [config]);
  useEffect(() => {
    if (!vid && vehicles.length) setVid(vehicles[0].id);
    if (vid && !vehicles.some((v) => v.id === vid))
      setVid(vehicles[0]?.id || "");
  }, [vehicles]);
  useEffect(() => {
    setWork(null);
    setMapAttachment(null);
    setInteractionTargets(vid ? [vid] : []);
    setParams(null);
    setStaged({});
    setSelected("");
    setControl(false);
    setReplay(null);
    setReplayId("");
    setLogEntries([]);
    if (vid) guard(() => refresh(vid));
  }, [vid]);
  useEffect(() => {
    if (!vid || !control) return;
    const renew = () =>
      api(`/vehicles/${vid}/lease`, "POST", {}).catch((e) => {
        setControl(false);
        setError(e.message);
      });
    renew();
    const id = setInterval(renew, 10000);
    return () => clearInterval(id);
  }, [vid, control]);
  useEffect(() => {
    chatBottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [work?.chat?.length, chatBusy]);
  useEffect(() => {
    if (!vid) return;
    if (tab === "parameters")
      guard(async () => setParams(await api(`/vehicles/${vid}/parameters`)));
    if (tab === "logs")
      guard(async () => {
        const [ev, msg, rec] = await Promise.all([
          api("/events?vehicle_id=" + vid),
          api(`/vehicles/${vid}/messages`),
          api("/recordings"),
        ]);
        setEvents(ev);
        setMessages(msg);
        setRecordings(rec);
      });
  }, [tab, vid]);
  const runAction = async (action: string, args: Json = {}) => {
    const j = await api(`/vehicles/${vid}/actions`, "POST", {
      action,
      args,
      request_id: crypto.randomUUID(),
    });
    setNotice(`Sent ${action}. Waiting for verification…`);
    return waitJob(j.id);
  };
  const waitJob = async (id: string) => {
    for (let i = 0; i < 900; i++) {
      const j = await api(`/jobs/${id}`);
      if (j.status !== "pending") {
        if (j.status === "failed") throw Error(j.error);
        setNotice(`${j.action}: ${j.status}`);
        await refresh();
        return j;
      }
      await new Promise((r) => setTimeout(r, 400));
    }
    throw Error(
      "Operation still pending. Check command history before retrying.",
    );
  };
  const save = async (next: Json) => {
    setWork(
      await api(`/vehicles/${vid}/draft`, "PUT", {
        expected_revision: draft.revision,
        draft: next,
      }),
    );
  };
  const updatePoint = (id: string, fields: Json) =>
    guard(() =>
      save({
        ...draft,
        waypoints: draft.waypoints.map((w: Json) =>
          w.id === id ? { ...w, ...fields } : w,
        ),
      }),
    );
  const addPoint = (lat: number, lon: number) => {
    if (!draft || replay) return;
    guard(() =>
      save({
        ...draft,
        waypoints: [
          ...draft.waypoints,
          {
            id: uid(),
            command: 16,
            lat,
            lon,
            alt: current.profile === "rover" ? 0 : 30,
            frame: 3,
            p1: 0,
            p2: 0,
            p3: 0,
            p4: 0,
          },
        ],
      }),
    );
  };
  const review = () =>
    guard(async () => {
      setWork(await api(`/vehicles/${vid}/review`, "POST", {}));
      setNotice(
        "Numerical review attached. Requesting the copilot's plan assessment…",
      );
      setSidePanel("chat");
      setChatBusy(true);
      try {
        setWork(
          await api(`/vehicles/${vid}/chat`, "POST", {
            message:
              "Review the current mission, route and declared intent. Explain concrete issues, assumptions and unavailable checks. Do not edit the draft.",
            edit_authorized: false,
          }),
        );
      } finally {
        setChatBusy(false);
      }
    }, "review");
  const describeTask = (text?: string) => {
    setSidePanel("chat");
    setTab("plan");
    setReplay(null);
    setInteractionMode(true);
    setInteractionTargets(vid ? [vid] : []);
    if (text !== undefined) setChat(text);
    setTimeout(() => chatInput.current?.focus(), 0);
  };
  const claimControl = () =>
    guard(async () => {
      await api(`/vehicles/${vid}/lease`, "POST", {});
      if (selectedVehicleRef.current === vid) setControl(true);
    });
  const refreshChecks = () =>
    guard(async () => {
      setWork(await api(`/vehicles/${vid}/review`, "POST", {}));
      setNotice(
        "Numerical checks refreshed for the current vehicle state. No AI request made; earlier AI comments may refer to older context.",
      );
    }, "review");
  const uploadMission = () =>
    guard(async () => {
      const j = await api(`/vehicles/${vid}/upload`, "POST", {
        review_id: work.review.id,
        request_id: crypto.randomUUID(),
      });
      await waitJob(j.id);
      setTab("flight");
      setNotice(
        `Mission version ${draft.revision} uploaded and verified. Use Flight controls to prepare, arm and start.`,
      );
    }, "upload");
  const sendChat = () => {
    if (!chat.trim() || chatBusy || !current || work?.vehicle_id !== vid)
      return;
    if (interactionMode && mapAttachment && mapModelBlocked) {
      setError(
        "Choose a model with image and tool support in Settings before sending the map.",
      );
      return;
    }
    if (
      interactionMode &&
      !interactionTargets.some((id) => vehicles.some((v) => v.id === id))
    ) {
      setError("Select at least one vehicle for AI planning.");
      return;
    }
    const text = chat;
    const targets = interactionTargets.filter((id) =>
      vehicles.some((v) => v.id === id),
    );
    const responseVehicle =
      interactionMode && !targets.includes(vid) ? targets[0] : vid;
    if (responseVehicle !== vid) setVid(responseVehicle);
    setChat("");
    setChatBusy(true);
    guard(async () => {
      if (interactionMode) {
        const result = await api("/interaction", "POST", {
          message: text,
          enabled: true,
          targets,
          map_image: mapAttachment,
        });
        setMapAttachment(null);
        result.workspaces.forEach(setWork);
      } else
        await api(`/vehicles/${vid}/chat`, "POST", {
          message: text,
          edit_authorized: editAuthorized,
        });
      await refresh(responseVehicle);
    }).finally(() => {
      void guard(() => refresh(selectedVehicleRef.current));
      setChatBusy(false);
    });
  };
  const launch = () =>
    guard(async () => {
      for (let i = 0; i < launchCount; i++) {
        const v = await api("/sitl", "POST", { profile: launchProfile });
        setVid(v.id);
      }
      setTab("plan");
      setNotice(
        `${launchCount} ${launchProfile} simulator(s) started. Wait for home and telemetry, then send your task to Copilot.`,
      );
    }, "launch");
  const selectedPoint = draft?.waypoints.find((w: Json) => w.id === selected);
  const replayMaxAltitude = Math.max(
    5,
    ...(replay?.points || []).map((p: Json) => p.alt),
  );
  const openEvidence = (id: string) =>
    guard(async () =>
      setEvidence(
        await api(`/vehicles/${vid}/evidence/${encodeURIComponent(id)}`),
      ),
    );
  const alertCount =
    (current?.rules || []).filter((r: Json) =>
      ["critical", "warning"].includes(r.severity),
    ).length +
    (current?.watches?.rules || []).filter(
      (r: Json) => r.latched || r.state === "triggered",
    ).length +
    (!current?.assessment_stale
      ? (current?.assessment?.incidents || []).filter((i: Json) =>
          ["warning", "critical"].includes(i.severity),
        ).length
      : 0);
  if (!config)
    return (
      <div className="loading">
        <Radio /> Connecting to the local ground station…
        {error && <p>{error}</p>}
      </div>
    );
  return (
    <div className="app">
      <div className="body">
        <nav className="rail">
          {[
            ["flight", MapIcon, "Flight"],
            ["parameters", SlidersHorizontal, "Parameters"],
            ["logs", FileText, "Logs"],
            ["lab", FlaskConical, "Diagnostics"],
            ["settings", Settings, "Settings"],
          ].map(([id, Icon, label]: any) => (
            <button
              key={id}
              className={
                tab === id || (id === "flight" && tab === "plan")
                  ? "active"
                  : ""
              }
              title={label}
              onClick={() => {
                setTab(id);
                setReplay(null);
              }}
            >
              <Icon size={21} />
              <span>{label}</span>
            </button>
          ))}
          <div className="rail-bottom">
            <span>v0.1</span>
            <span>LOCAL</span>
          </div>
        </nav>
        <main>
          <div className="vehicle-bar">
            <div className="vehicle-tabs">
              {vehicles.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setVid(v.id)}
                  className={vid === v.id ? "selected" : ""}
                >
                  <span
                    className={
                      "dot " +
                      (v.heartbeat_age == null || v.heartbeat_age > 3
                        ? "bad"
                        : "")
                    }
                  />
                  {v.profile.toUpperCase()}
                  <small>{v.id.slice(0, 4)}</small>
                </button>
              ))}
              {!vehicles.length && (
                <span className="muted">No vehicle connected</span>
              )}
            </div>
            <header
              className="status-island"
              aria-label="Ground station and model"
            >
              <div className="brand">
                <img src="/icon.svg" alt="" width="23" height="23" />
                <strong>
                  Copilot <span>GCS</span>
                </strong>
              </div>
              <span
                role="status"
                aria-label={
                  wsState ? "Gateway connected" : "Gateway disconnected"
                }
                title={wsState ? "Gateway connected" : "Gateway disconnected"}
                className={"connection-symbol " + (wsState ? "" : "offline")}
              >
                <Radio size={15} />
              </span>
              <button
                onClick={() => setTab("settings")}
                className="model-chip"
                title={`Model: ${config.model}. Open settings.`}
              >
                <span>{config.model}</span>
                <ChevronDown size={12} />
              </button>
            </header>
            <div className="launch">
              <button
                onClick={() => setTab("settings")}
                title="Open connection settings"
              >
                <Radio size={16} /> Connect telemetry
              </button>
              <select
                aria-label="Vehicle to launch"
                value={launchProfile}
                onChange={(e) => setLaunchProfile(e.target.value)}
              >
                {Object.keys(config.profiles).map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
              <select
                aria-label="Number of simulators"
                title="Launch multiple independent vehicles"
                value={launchCount}
                onChange={(e) => setLaunchCount(+e.target.value)}
              >
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>
                    {n} ×
                  </option>
                ))}
              </select>
              <button
                onClick={launch}
                disabled={
                  busy === "launch" || vehicles.length + launchCount > 6
                }
              >
                <Plus size={16} />
                {busy === "launch" ? "Starting…" : "Start simulation"}
              </button>
            </div>
          </div>
          {current && (
            <div
              className={
                "interaction-bar" + (interactionMode ? " enabled" : "")
              }
            >
              <button
                role="switch"
                aria-checked={interactionMode}
                aria-label="AI planning"
                disabled={chatBusy}
                onClick={() => {
                  const enabled = !interactionMode;
                  setInteractionMode(enabled);
                  if (enabled) setInteractionTargets(vid ? [vid] : []);
                }}
              >
                <span className="switch-track">
                  <span />
                </span>{" "}
                AI planning <strong>{interactionMode ? "ON" : "OFF"}</strong>
              </button>
              {interactionMode ? (
                <>
                  <span>For:</span>
                  <div className="interaction-targets">
                    {vehicles.map((v) => (
                      <label key={v.id}>
                        <input
                          type="checkbox"
                          disabled={chatBusy}
                          checked={interactionTargets.includes(v.id)}
                          onChange={(e) =>
                            setInteractionTargets((ids) =>
                              e.target.checked
                                ? [...ids, v.id]
                                : ids.filter((id) => id !== v.id),
                            )
                          }
                        />
                        {v.profile} {v.id.slice(0, 6)}
                      </label>
                    ))}
                  </div>
                </>
              ) : (
                <small>
                  Chat is in review mode. Turn on AI planning to prepare mission
                  changes.
                </small>
              )}
            </div>
          )}
          {error && (
            <div className="banner error">
              <AlertTriangle size={17} />
              <span>{error}</span>
              <button onClick={() => setError("")}>Dismiss</button>
            </div>
          )}
          {notice && (
            <div className="banner notice">
              <Check size={16} />
              <span>{notice}</span>
              <button onClick={() => setNotice("")}>Dismiss</button>
            </div>
          )}
          {current && (
            <div className="telemetry-strip">
              <div>
                <label>FLIGHT MODE</label>
                <strong>{current.mode}</strong>
                <small className={current.armed ? "amber" : ""}>
                  {current.armed ? "ARMED" : "DISARMED"}
                </small>
              </div>
              <div>
                <label>ALTITUDE · REL</label>
                <strong>
                  {fmt(current.position?.relative)} <em>m</em>
                </strong>
              </div>
              <div>
                <label>GROUND SPEED</label>
                <strong>
                  {fmt(current.speed)} <em>m/s</em>
                </strong>
              </div>
              <div>
                <label>
                  {current.profile === "plane" ? "AIR SPEED" : "VERTICAL SPEED"}
                </label>
                <strong>
                  {fmt(
                    current.profile === "plane"
                      ? current.airspeed
                      : current.climb,
                  )}{" "}
                  <em>m/s</em>
                </strong>
              </div>
              <div>
                <label>BATTERY</label>
                <strong>
                  {fmt(current.voltage)} <em>V</em>
                </strong>
                <small>{fmt(current.battery, 0)}%</small>
              </div>
              <div>
                <label>GPS</label>
                <strong>
                  {current.gps_fix >= 3
                    ? "3D FIX"
                    : current.gps_fix == null
                      ? "UNKNOWN"
                      : "NO FIX"}
                </strong>
                <small>{current.satellites ?? "—"} satellites</small>
              </div>
              <div>
                <label>LINK AGE</label>
                <strong className={current.heartbeat_age > 3 ? "red" : ""}>
                  {fmt(current.heartbeat_age)} <em>s</em>
                </strong>
              </div>
            </div>
          )}
          {tab === "settings" && (
            <SettingsPanel
              config={config}
              vehicles={vehicles}
              current={current}
              onSaved={async () => setConfig(await api("/bootstrap"))}
              onConnected={(v: Json) => {
                setVid(v.id);
                setTab("plan");
              }}
              onStopped={() => setVid("")}
            />
          )}
          {!current && tab !== "settings" && (
            <div className="welcome">
              <div className="welcome-icon">
                <Sparkles size={30} />
              </div>
              <span className="eyebrow">COPILOT GCS</span>
              <h1>Connect a vehicle</h1>
              <p>
                Start a simulation, or connect an existing vehicle for
                telemetry.
              </p>
              <div className="task-brief">
                <label htmlFor="task-brief">Mission brief (optional)</label>
                <textarea
                  id="task-brief"
                  ref={chatInput}
                  value={chat}
                  onChange={(e) => setChat(e.target.value)}
                  placeholder="For example: help me plan a waypoint flight and return home when finished."
                />
                <div className="task-starters">
                  {taskStarters(launchProfile).map((task) => (
                    <button
                      key={task.title}
                      onClick={() => setChat(task.prompt)}
                      title={task.detail}
                    >
                      <Sparkles size={14} />
                      {task.title}
                    </button>
                  ))}
                </div>
                <div className="task-start-actions">
                  <select
                    aria-label="Task vehicle type"
                    value={launchProfile}
                    onChange={(e) => setLaunchProfile(e.target.value)}
                  >
                    {Object.keys(config.profiles).map((p) => (
                      <option key={p} value={p}>
                        {p === "copter"
                          ? "Copter"
                          : p === "plane"
                            ? "Plane"
                            : "Rover"}
                      </option>
                    ))}
                  </select>
                  <button
                    className="primary"
                    onClick={launch}
                    disabled={busy === "launch"}
                  >
                    <Play size={16} />
                    {busy === "launch" ? "Starting…" : "Start simulation"}
                  </button>
                  <button onClick={() => setTab("settings")}>
                    <Radio size={16} />
                    Connect telemetry
                  </button>
                </div>
                <small>
                  Your brief stays here until you send it. Starting a simulation
                  makes no AI request.
                </small>
              </div>

              <small>
                Current release: control simulated vehicles; connect external
                telemetry for monitoring.
              </small>
            </div>
          )}
          {current && tab !== "settings" && (
            <div className="workspace">
              {["flight", "plan"].includes(tab) && (
                <FlightDeck
                  key={vid}
                  vehicle={current}
                  workspace={work}
                  control={control}
                  busy={!!busy}
                  modes={profile?.modes || []}
                  onControl={claimControl}
                  onPlan={() => setTab("plan")}
                  alertCount={alertCount}
                  onAlerts={() => setSidePanel("alerts")}
                  onAction={(action: string, args: Json) =>
                    guard(() => runAction(action, args), "vehicle action")
                  }
                />
              )}
              <section className="content">
                {["flight", "plan"].includes(tab) && (
                  <>
                    <MissionWorkflow
                      workspace={work}
                      vehicle={current}
                      control={control}
                      busy={!!busy || chatBusy}
                      onDescribe={() => describeTask()}
                      onReview={review}
                      onUpload={uploadMission}
                      view={tab}
                      onView={setTab}
                      onClaimControl={claimControl}
                      onRefreshChecks={refreshChecks}
                    />
                    <MapView
                      key={vid}
                      vehicle={current}
                      vehicles={vehicles}
                      onSelectVehicle={setVid}
                      draft={draft}
                      active={work?.active}
                      editing={tab === "plan"}
                      onAdd={addPoint}
                      onMove={(id: string, lat: number, lon: number) =>
                        updatePoint(id, { lat, lon })
                      }
                      selected={selected}
                      setSelected={setSelected}
                      home={config.home}
                      captureRef={captureMap}
                      proposal={work?.geofence_proposal}
                      onSaveAreas={async (
                        areas: Json,
                        revision: number,
                        kind: string,
                      ) => {
                        setWork(
                          await api(`/vehicles/${vid}/draft`, "PUT", {
                            expected_revision: revision,
                            draft: {
                              ...draft,
                              intent: { ...draft.intent, [kind + "s"]: areas },
                            },
                          }),
                        );
                      }}
                    />
                    {tab === "plan" && (
                      <div className="mission-editor">
                        <div className="section-title">
                          <h2>
                            Mission draft{" "}
                            <span>Version {draft?.revision ?? 0}</span>
                          </h2>
                          <div className="inline">
                            <button
                              title="Undo last revision"
                              disabled={!draft?.revision}
                              onClick={() =>
                                guard(async () =>
                                  setWork(
                                    await api(`/vehicles/${vid}/undo`, "POST", {
                                      expected_revision: draft.revision,
                                    }),
                                  ),
                                )
                              }
                            >
                              <Undo2 size={15} />
                            </button>
                            <button
                              disabled={!control}
                              onClick={() =>
                                guard(async () => {
                                  const j = await runAction("mission_download");
                                  await save({
                                    ...draft,
                                    waypoints: j.items
                                      .slice(1)
                                      .map((w: Json) => ({
                                        ...w,
                                        id: uid(),
                                        frame: [20, 178].includes(w.command)
                                          ? 3
                                          : w.frame,
                                      })),
                                  });
                                })
                              }
                            >
                              Read onboard
                            </button>
                            <button
                              onClick={() =>
                                download(
                                  `${current.profile}-mission.json`,
                                  draft,
                                )
                              }
                            >
                              <Download size={15} /> Export
                            </button>
                            <label className="file-button">
                              Import
                              <input
                                type="file"
                                accept=".json"
                                onChange={(e) => {
                                  const f = e.target.files?.[0];
                                  if (f)
                                    guard(async () =>
                                      save(JSON.parse(await f.text())),
                                    );
                                  e.target.value = "";
                                }}
                              />
                            </label>
                            <button
                              disabled={
                                !draft?.waypoints.length &&
                                !draft?.intent?.exclusions?.length &&
                                !draft?.intent?.inclusions?.length
                              }
                              onClick={() =>
                                guard(() =>
                                  save({ ...draft, waypoints: [], intent: {} }),
                                )
                              }
                            >
                              Clear draft
                            </button>
                            <button onClick={review}>
                              <ShieldCheck size={15} />
                              Ask AI to review
                            </button>
                          </div>
                        </div>
                        {work?.checks && draft?.waypoints.length > 0 && (
                          <details
                            className="plan-checks"
                            open={work.checks.findings.some(
                              (f: Json) => f.severity === "error",
                            )}
                          >
                            <summary>
                              Mission checks ·{" "}
                              {
                                work.checks.findings.filter(
                                  (f: Json) => f.severity === "error",
                                ).length
                              }{" "}
                              blockers · {draft.waypoints.length} items
                            </summary>
                            {work.checks.findings.map((f: Json, i: number) => (
                              <button
                                className={"finding " + f.severity}
                                key={i}
                                onClick={() =>
                                  f.waypoint && setSelected(f.waypoint)
                                }
                              >
                                {f.text}
                              </button>
                            ))}
                            <small>
                              Numerical checks run on this draft. Unavailable
                              checks remain unknown.
                            </small>
                          </details>
                        )}
                        <p className="editor-help">
                          Set each waypoint's <b>Altitude m</b> below, then
                          choose <b>Relative home</b> or <b>AMSL</b>. Press
                          Enter or leave the field to save the draft; upload the
                          reviewed revision to change the onboard mission.
                        </p>
                        <div className="waypoint-table">
                          <table>
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Command</th>
                                <th>Latitude</th>
                                <th>Longitude</th>
                                <th>Altitude m</th>
                                <th>Reference</th>
                                <th />
                              </tr>
                            </thead>
                            <tbody>
                              {draft?.waypoints.map((w: Json, i: number) => (
                                <tr
                                  key={w.id}
                                  className={
                                    selected === w.id ? "selected" : ""
                                  }
                                  onClick={() => setSelected(w.id)}
                                >
                                  <td>{i + 1}</td>
                                  <td>
                                    <select
                                      value={w.command}
                                      onChange={(e) =>
                                        updatePoint(w.id, {
                                          command: +e.target.value,
                                        })
                                      }
                                    >
                                      {profile.commands.map((c: number) => (
                                        <option key={c} value={c}>
                                          {commands[c]}
                                        </option>
                                      ))}
                                    </select>
                                  </td>
                                  {["lat", "lon", "alt"].map((k) => (
                                    <td key={k}>
                                      <input
                                        aria-label={`Waypoint ${i + 1} ${k === "alt" ? "altitude metres" : k}`}
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter")
                                            e.currentTarget.blur();
                                        }}
                                        type="number"
                                        step={k === "alt" ? 1 : 0.00001}
                                        key={w.id + k + w[k]}
                                        defaultValue={w[k]}
                                        onBlur={(e) => {
                                          if (!e.target.value.trim()) {
                                            setError(
                                              "Waypoint coordinates and altitude must be numbers.",
                                            );
                                            e.target.value = String(w[k]);
                                            return;
                                          }
                                          if (+e.target.value !== w[k])
                                            updatePoint(w.id, {
                                              [k]: +e.target.value,
                                            });
                                        }}
                                      />
                                    </td>
                                  ))}
                                  <td>
                                    <select
                                      value={w.frame}
                                      onChange={(e) =>
                                        updatePoint(w.id, {
                                          frame: +e.target.value,
                                        })
                                      }
                                    >
                                      <option value="3">Relative home</option>
                                      <option value="0">AMSL</option>
                                      <option value="10">
                                        Terrain (blocked)
                                      </option>
                                    </select>
                                  </td>
                                  <td>
                                    <button
                                      title="Remove waypoint"
                                      onClick={() =>
                                        guard(() =>
                                          save({
                                            ...draft,
                                            waypoints: draft.waypoints.filter(
                                              (x: Json) => x.id !== w.id,
                                            ),
                                          }),
                                        )
                                      }
                                    >
                                      <Trash2 size={14} />
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {!draft?.waypoints.length && (
                            <div className="empty-small">
                              Click the map to add waypoints, or describe a
                              route to the copilot.
                            </div>
                          )}
                        </div>
                        {selectedPoint && (
                          <div className="params-row">
                            <span>
                              Item {draft.waypoints.indexOf(selectedPoint) + 1}{" "}
                              command fields
                            </span>
                            {["p1", "p2", "p3", "p4"].map((k) => (
                              <label key={k}>
                                {k}
                                <input
                                  type="number"
                                  key={selectedPoint.id + k + selectedPoint[k]}
                                  defaultValue={selectedPoint[k]}
                                  onBlur={(e) =>
                                    updatePoint(selectedPoint.id, {
                                      [k]: +e.target.value,
                                    })
                                  }
                                />
                              </label>
                            ))}
                            <button
                              onClick={() =>
                                guard(() =>
                                  save({
                                    ...draft,
                                    waypoints: [
                                      selectedPoint,
                                      ...draft.waypoints.filter(
                                        (w: Json) => w.id !== selectedPoint.id,
                                      ),
                                    ],
                                  }),
                                )
                              }
                            >
                              Move to first
                            </button>
                          </div>
                        )}
                        <FencePanel
                          key={vid}
                          vehicle={current}
                          draft={draft}
                          control={control}
                          onClaim={claimControl}
                          onChanged={() =>
                            setNotice(
                              "Onboard fence verified. Refresh mission checks before upload.",
                            )
                          }
                        />
                        {draft && (
                          <details className="intent">
                            <summary>
                              Mission intent & operating constraints{" "}
                              <span>Optional · versioned with this draft</span>
                            </summary>
                            <label>
                              Mission statement
                              <textarea
                                key={draft.revision + "brief"}
                                defaultValue={draft.intent.brief}
                                placeholder="Describe what this mission must accomplish…"
                                onBlur={(e) => {
                                  if (e.target.value !== draft.intent.brief)
                                    guard(() =>
                                      save({
                                        ...draft,
                                        intent: {
                                          ...draft.intent,
                                          brief: e.target.value,
                                        },
                                      }),
                                    );
                                }}
                              />
                            </label>
                            <button
                              style={{ marginTop: 10 }}
                              onClick={() =>
                                guard(async () => {
                                  setWork(
                                    await api(
                                      `/vehicles/${vid}/intent/interpret`,
                                      "POST",
                                      {},
                                    ),
                                  );
                                  setNotice(
                                    "Proposed interpretation is in the copilot panel. Review before accepting.",
                                  );
                                }, "intent")
                              }
                              disabled={busy === "intent"}
                            >
                              {busy === "intent"
                                ? "Interpreting…"
                                : "Interpret statement with copilot"}
                            </button>
                            <div className="intent-fields">
                              {[
                                ["min_alt", "Min cruise altitude (m)"],
                                ["max_alt", "Max altitude (m)"],
                                ["max_speed", "Max ground speed (m/s)"],
                                ["corridor_m", "Route corridor (m)"],
                              ].map(([k, label]) => (
                                <label key={k}>
                                  {label}
                                  <input
                                    type="number"
                                    key={draft.revision + k}
                                    defaultValue={draft.intent[k] ?? ""}
                                    placeholder="Not set"
                                    onBlur={(e) => {
                                      const n =
                                        e.target.value === ""
                                          ? null
                                          : +e.target.value;
                                      if (n !== draft.intent[k])
                                        guard(() =>
                                          save({
                                            ...draft,
                                            intent: { ...draft.intent, [k]: n },
                                          }),
                                        );
                                    }}
                                  />
                                </label>
                              ))}
                              <label>
                                Altitude datum
                                <select
                                  value={draft.intent.altitude_frame}
                                  onChange={(e) =>
                                    guard(() =>
                                      save({
                                        ...draft,
                                        intent: {
                                          ...draft.intent,
                                          altitude_frame: e.target.value,
                                        },
                                      }),
                                    )
                                  }
                                >
                                  <option value="relative_home">
                                    Relative to home
                                  </option>
                                  <option value="amsl">AMSL</option>
                                </select>
                              </label>
                            </div>
                            <label>
                              Multiple inclusion areas
                              <select
                                value={
                                  draft.intent.inclusion_mode || "intersection"
                                }
                                onChange={(e) =>
                                  guard(() =>
                                    save({
                                      ...draft,
                                      intent: {
                                        ...draft.intent,
                                        inclusion_mode: e.target.value,
                                      },
                                    }),
                                  )
                                }
                              >
                                <option value="intersection">
                                  Stay inside all areas (overlap)
                                </option>
                                <option value="union">
                                  Stay inside any area (union)
                                </option>
                              </select>
                            </label>
                            {["inclusions", "exclusions"].map((kind) => (
                              <label key={kind}>
                                {kind} · JSON [longitude, latitude]
                                <textarea
                                  key={draft.revision + kind}
                                  defaultValue={JSON.stringify(
                                    draft.intent[kind] || [],
                                  )}
                                  onBlur={(e) =>
                                    guard(async () => {
                                      const polygons = JSON.parse(
                                        e.target.value,
                                      );
                                      if (
                                        JSON.stringify(polygons) !==
                                        JSON.stringify(draft.intent[kind])
                                      )
                                        await save({
                                          ...draft,
                                          intent: {
                                            ...draft.intent,
                                            [kind]: polygons,
                                          },
                                        });
                                    })
                                  }
                                />
                              </label>
                            ))}
                          </details>
                        )}
                      </div>
                    )}
                  </>
                )}
                {tab === "parameters" && (
                  <div className="page">
                    <div className="section-title">
                      <div>
                        <span className="eyebrow">VEHICLE CONFIGURATION</span>
                        <h1>Parameters</h1>
                      </div>
                      <button
                        onClick={() =>
                          guard(async () => {
                            await runAction("parameters");
                            setParams(await api(`/vehicles/${vid}/parameters`));
                          })
                        }
                        disabled={!control}
                      >
                        <RefreshCw size={16} />
                        Fetch complete set
                      </button>
                    </div>
                    <div className="toolbar">
                      <input
                        placeholder="Search parameter name…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                      <span>
                        {params?.items.length ?? 0} /{" "}
                        {params?.expected ?? current.parameters} received
                      </span>
                      <button
                        onClick={() =>
                          download(
                            `${current.profile}-parameters.json`,
                            params?.items || [],
                          )
                        }
                      >
                        <Download size={15} />
                        Export
                      </button>
                      <label className="file-button">
                        Import changes
                        <input
                          type="file"
                          accept=".json"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f)
                              guard(async () => {
                                const rows = JSON.parse(await f.text());
                                const change: any = {};
                                for (const p of rows) {
                                  const old = params.items.find(
                                    (x: any) => x.name === p.name,
                                  );
                                  if (
                                    old &&
                                    old.value !== p.value &&
                                    !p.name.startsWith("SIM_")
                                  )
                                    change[p.name] = Number(p.value);
                                }
                                setStaged(change);
                              });
                            e.target.value = "";
                          }}
                        />
                      </label>
                    </div>
                    <div className="parameter-notice">
                      Writes require control and a disarmed vehicle. Every
                      change uses a fresh conflict check and a separate
                      readback. Simulator parameters belong to the lab.
                    </div>
                    {Object.keys(staged).length > 0 && (
                      <div className="staged">
                        <strong>
                          {Object.keys(staged).length} staged changes
                        </strong>
                        <button
                          disabled={!control || current.armed}
                          className="primary"
                          onClick={() =>
                            guard(async () => {
                              for (const [name, value] of Object.entries(
                                staged,
                              )) {
                                const old = params.items.find(
                                  (p: Json) => p.name === name,
                                );
                                const j = await api(
                                  `/vehicles/${vid}/parameters`,
                                  "POST",
                                  {
                                    name,
                                    value,
                                    expected: old.value,
                                    request_id: crypto.randomUUID(),
                                  },
                                );
                                await waitJob(j.id);
                                setStaged((s: Json) => {
                                  const n = { ...s };
                                  delete n[name];
                                  return n;
                                });
                              }
                              setParams(
                                await api(`/vehicles/${vid}/parameters`),
                              );
                            }, "parameters")
                          }
                        >
                          Write & verify
                        </button>
                        <button onClick={() => setStaged({})}>Discard</button>
                        <small>
                          Bulk writes are sequential. A failure leaves remaining
                          changes staged.
                        </small>
                      </div>
                    )}
                    <div className="parameter-list">
                      <table>
                        <thead>
                          <tr>
                            <th>Parameter</th>
                            <th>Current value</th>
                            <th>New value</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {params?.items
                            .filter((p: Json) =>
                              p.name.includes(search.toUpperCase()),
                            )
                            .slice(0, 250)
                            .map((p: Json) => (
                              <tr key={p.name}>
                                <td>
                                  <details className="parameter-detail">
                                    <summary>
                                      <code>{p.name}</code>
                                      <span>{p.metadata?.Units || ""}</span>
                                    </summary>
                                    <p>{p.metadata?.DisplayName}</p>
                                    <p>
                                      {p.metadata?.Description ||
                                        "No version-matched description available."}
                                    </p>
                                    {p.metadata?.Range && (
                                      <p>
                                        Range: {p.metadata.Range.low} –{" "}
                                        {p.metadata.Range.high}
                                      </p>
                                    )}
                                    {p.metadata?.Values && (
                                      <pre>
                                        {JSON.stringify(
                                          p.metadata.Values,
                                          null,
                                          2,
                                        )}
                                      </pre>
                                    )}
                                    {p.metadata?.Bitmask && (
                                      <pre>
                                        Bit positions:{" "}
                                        {JSON.stringify(
                                          p.metadata.Bitmask,
                                          null,
                                          2,
                                        )}
                                      </pre>
                                    )}
                                    {p.metadata?.RebootRequired && (
                                      <strong>
                                        Reboot required after write
                                      </strong>
                                    )}
                                  </details>
                                  {p.name.startsWith("SIM_") && (
                                    <small className="muted">
                                      {" "}
                                      diagnostics only
                                    </small>
                                  )}
                                </td>
                                <td>{p.value}</td>
                                <td>
                                  <input
                                    aria-label={"New " + p.name}
                                    type="number"
                                    step="any"
                                    disabled={p.name.startsWith("SIM_")}
                                    value={staged[p.name] ?? ""}
                                    placeholder="No change"
                                    onChange={(e) =>
                                      setStaged((s: Json) => {
                                        const n = { ...s };
                                        if (e.target.value === "")
                                          delete n[p.name];
                                        else n[p.name] = +e.target.value;
                                        return n;
                                      })
                                    }
                                  />
                                </td>
                                <td>{p.type === 9 ? "float" : "integer"}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="muted">
                      Showing up to 250 matches. Narrow the search to inspect
                      more parameters.
                    </p>
                  </div>
                )}
                {tab === "logs" && (
                  <div className="page">
                    <div className="section-title">
                      <div>
                        <span className="eyebrow">OBSERVABILITY</span>
                        <h1>Logs & replay</h1>
                      </div>
                      <button
                        onClick={() =>
                          guard(async () => {
                            setEvents(await api("/events?vehicle_id=" + vid));
                            setMessages(await api(`/vehicles/${vid}/messages`));
                            setRecordings(await api("/recordings"));
                          })
                        }
                      >
                        <RefreshCw size={15} />
                        Refresh
                      </button>
                    </div>
                    <div className="log-downloads">
                      <a
                        href={`/api/recordings/${vid}/download/telemetry.tlog`}
                        download
                      >
                        MAVLink .tlog <Download size={14} />
                      </a>
                      <a
                        href={`/api/recordings/${vid}/download/telemetry.jsonl`}
                        download
                      >
                        Normalized telemetry <Download size={14} />
                      </a>
                      <a
                        href={`/api/recordings/${vid}/download/inference.jsonl`}
                        download
                      >
                        Inference audit <Download size={14} />
                      </a>
                      <button
                        disabled={!control}
                        onClick={() =>
                          guard(async () => {
                            const j = await runAction("log_list");
                            setLogEntries(j.logs || []);
                          })
                        }
                      >
                        List onboard logs
                      </button>
                    </div>
                    {logEntries.map((l) => (
                      <div className="log-entry" key={l.id}>
                        <span>
                          DataFlash #{l.id} · {fmt(l.size / 1024, 0)} KiB
                        </span>
                        <button
                          disabled={!control || current.armed}
                          onClick={() =>
                            guard(async () => {
                              const j = await runAction("log_download", {
                                id: l.id,
                                size: l.size,
                              });
                              location.assign(
                                `/api/recordings/${vid}/download/${j.file}`,
                              );
                            })
                          }
                        >
                          Download
                        </button>
                      </div>
                    ))}
                    <div className="replay">
                      <h2>Historical playback</h2>
                      <select
                        aria-label="Recording"
                        value={replayId}
                        onChange={(e) => {
                          setReplayId(e.target.value);
                          if (e.target.value)
                            guard(async () =>
                              setReplay(
                                await api(
                                  `/recordings/${e.target.value}/replay`,
                                ),
                              ),
                            );
                        }}
                      >
                        <option value="">Choose a recording</option>
                        {recordings.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.id} · {fmt(r.bytes / 1024, 0)} KiB{" "}
                            {r.live ? "(recording)" : ""}
                          </option>
                        ))}
                      </select>
                      {replay && (
                        <>
                          <div className="historical-label">
                            HISTORICAL · NO VEHICLE WRITE CAPABILITY ·{" "}
                            {clock(replay.at)}
                          </div>
                          <input
                            aria-label="Replay cursor"
                            type="range"
                            min={replay.start}
                            max={replay.end}
                            step="1"
                            value={replay.at}
                            onChange={(e) =>
                              guard(async () =>
                                setReplay(
                                  await api(
                                    `/recordings/${replayId}/replay?at=${e.target.value}`,
                                  ),
                                ),
                              )
                            }
                          />
                          <div className="plot">
                            <svg
                              viewBox="0 0 800 100"
                              preserveAspectRatio="none"
                            >
                              <polyline
                                fill="none"
                                stroke="#56dfd0"
                                strokeWidth="2"
                                points={replay.points
                                  .map(
                                    (p: Json, i: number) =>
                                      `${(i / Math.max(1, replay.points.length - 1)) * 800},${95 - (p.alt / replayMaxAltitude) * 85}`,
                                  )
                                  .join(" ")}
                              />
                            </svg>
                            <span>
                              Relative altitude ·{" "}
                              {fmt(replay.snapshot.position?.relative)} m
                            </span>
                          </div>
                          <div className="replay-map">
                            <MapView
                              key={replayId}
                              vehicle={null}
                              draft={null}
                              active={null}
                              home={config.home}
                              historical={replay}
                              editing={false}
                            />
                          </div>
                        </>
                      )}
                    </div>
                    <h2>Status messages</h2>
                    <div className="log-lines">
                      {messages
                        .slice()
                        .reverse()
                        .map((m) => (
                          <div key={m.evidence_id}>
                            <time>{clock(m.ts)}</time>
                            <span>{m.data.text}</span>
                          </div>
                        ))}
                    </div>
                    <h2>Command & application history</h2>
                    <div className="log-lines">
                      {events.slice(0, 80).map((e) => (
                        <details key={e.id}>
                          <summary>
                            <time>{clock(e.ts)}</time>
                            <span>{e.kind.replaceAll("_", " ")}</span>
                          </summary>
                          <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                        </details>
                      ))}
                    </div>
                  </div>
                )}
                {tab === "lab" && (
                  <div className="page lab">
                    <span className="eyebrow">SIMULATION DIAGNOSTICS</span>
                    <h1>Simulation diagnostics</h1>
                    <p>
                      Try a failure scenario in this simulated vehicle and see
                      how Copilot explains the telemetry. The injected fault is
                      hidden from the AI so its observations can be compared
                      with what happened.
                    </p>
                    <div className="lab-config">
                      <label>
                        Failure scenario
                        <select
                          value={scenario}
                          onChange={(e) => setScenario(e.target.value)}
                        >
                          {Object.entries(config.scenarios)
                            .filter(([k, v]: any) =>
                              v.profiles.includes(current.profile),
                            )
                            .map(([k, v]: any) => (
                              <option key={k} value={k}>
                                {v.label}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label>
                        Observation window (seconds)
                        <input
                          type="number"
                          min="30"
                          max="600"
                          value={duration}
                          onChange={(e) => setDuration(+e.target.value)}
                        />
                      </label>
                      <label>
                        Seed
                        <input
                          type="number"
                          value={seed}
                          onChange={(e) => setSeed(+e.target.value)}
                        />
                      </label>
                      <label>
                        Evidence track
                        <select
                          value={track}
                          onChange={(e) => setTrack(e.target.value)}
                        >
                          <option value="telemetry">
                            Telemetry only · no diagnostic labels
                          </option>
                          <option value="operational">
                            Operational · includes autopilot diagnostics
                          </option>
                        </select>
                      </label>
                    </div>
                    <button
                      className="primary"
                      disabled={
                        !control ||
                        !config.monitor_enabled ||
                        !!(
                          current.trial &&
                          !["complete", "failed", "cancelled"].includes(
                            current.trial.state,
                          )
                        )
                      }
                      onClick={() =>
                        guard(async () => {
                          await api(`/vehicles/${vid}/trials`, "POST", {
                            scenario,
                            duration,
                            seed,
                            track,
                          });
                          setNotice(
                            "Trial started. Baseline collection precedes injection.",
                          );
                        })
                      }
                    >
                      <Play size={16} />
                      Run trial on {current.profile}
                    </button>
                    {!control && (
                      <button onClick={claimControl}>
                        Enable vehicle controls for tests
                      </button>
                    )}
                    {!config.monitor_enabled && (
                      <p>
                        Automatic assessments are paused globally. Enable them
                        in Settings to run a monitored trial.
                      </p>
                    )}
                    {current.trial &&
                      !["complete", "failed", "cancelled"].includes(
                        current.trial.state,
                      ) && (
                        <button
                          className="danger"
                          disabled={!control}
                          onClick={() =>
                            guard(async () => {
                              await api(
                                `/vehicles/${vid}/trials/cancel`,
                                "POST",
                                {},
                              );
                              setNotice(
                                "Trial cancelled; injected parameters restored where possible.",
                              );
                            })
                          }
                        >
                          Cancel trial & restore
                        </button>
                      )}
                    {duration <
                      Math.max(
                        config.monitor_interval,
                        config.automatic_min_interval || 60,
                      ) && (
                      <p className="editor-help">
                        Your{" "}
                        {Math.max(
                          config.monitor_interval,
                          config.automatic_min_interval || 60,
                        )}
                        s effective assessment delay exceeds this {duration}s
                        observation window. Increase the trial duration or lower
                        the delay in Settings to collect assessments after the
                        fault. Trials do not silently increase your request
                        rate.
                      </p>
                    )}
                    <div className="lab-guidance">
                      <strong>Flight phase matters</strong>
                      <p>
                        Custom watch cards still update during trials, but their
                        notes, rule context and event-triggered AI calls are
                        excluded. Trials use the configured periodic cadence to
                        avoid operator-written fault hints.
                      </p>
                      <p>
                        Trials preserve the current vehicle state. A motor or
                        wind fault on a disarmed stationary vehicle may be
                        unobservable. Establish the desired flight/driving phase
                        with the normal controls first.
                      </p>
                      <p>
                        Predictions are locked and hashed before results are
                        revealed. Scores are lexical symptom screening, not
                        validated detection accuracy. Run nominal controls and
                        manually adjudicate each result.
                      </p>
                      <p>
                        Inference filesystem isolation:{" "}
                        <b>
                          {config.filesystem_isolated
                            ? "enabled (macOS sandbox)"
                            : "unavailable — results are not isolation-qualified"}
                        </b>
                        .
                      </p>
                    </div>
                    {current.trial && (
                      <div className="trial-result">
                        <span className="eyebrow">CURRENT TRIAL</span>
                        <h2>{current.trial.state}</h2>
                        <pre>{JSON.stringify(current.trial, null, 2)}</pre>
                      </div>
                    )}
                  </div>
                )}
              </section>
              <aside className="copilot">
                <div className="copilot-heading">
                  <div className="copilot-icon">
                    <Sparkles size={21} />
                  </div>
                  <div>
                    <h2>Copilot</h2>
                    <span>
                      {current.profile.toUpperCase()} · {vid.slice(0, 6)}
                    </span>
                  </div>
                  <span className="read-only">
                    {interactionMode ? "AI PLANNING" : "REVIEW"}
                  </span>
                </div>
                <div className="copilot-status">
                  <span
                    className={
                      "dot " +
                      (current.monitor_status.startsWith("unavailable")
                        ? "bad"
                        : "")
                    }
                  />
                  <span>
                    {!current.monitor_effective
                      ? "Periodic monitoring off"
                      : !current.monitor_enabled
                        ? "Live insights paused for this vehicle"
                        : `${current.monitor_status} · every ${current.monitoring?.effective_interval_s || config.monitor_interval}s`}
                  </span>
                  <button
                    title={
                      current.monitor_enabled
                        ? "Pause periodic monitoring"
                        : "Resume periodic monitoring"
                    }
                    onClick={() =>
                      guard(() =>
                        api(`/vehicles/${vid}/monitor`, "POST", {
                          enabled: !current.monitor_enabled,
                          track: current.monitor_track,
                        }),
                      )
                    }
                  >
                    {current.monitor_enabled ? (
                      <Square size={12} />
                    ) : (
                      <Play size={12} />
                    )}
                  </button>
                </div>
                <div className="copilot-tabs" aria-label="Copilot panels">
                  <button
                    className={sidePanel === "chat" ? "active" : ""}
                    onClick={() => setSidePanel("chat")}
                  >
                    Chat
                  </button>
                  <button
                    className={
                      (sidePanel === "alerts" ? "active " : "") +
                      (alertCount ? "has-alert" : "")
                    }
                    onClick={() => setSidePanel("alerts")}
                  >
                    Alerts {alertCount > 0 && <b>{alertCount}</b>}
                  </button>
                  <button
                    className={sidePanel === "watches" ? "active" : ""}
                    onClick={() => setSidePanel("watches")}
                  >
                    Watch rules <b>{current.watches?.rules?.length || 0}</b>
                  </button>
                </div>
                {sidePanel === "alerts" && (
                  <AlertsPanel
                    vehicle={current}
                    onWatches={() => setSidePanel("watches")}
                    onEvidence={openEvidence}
                  />
                )}
                <div
                  className={
                    "watches-pane" +
                    (sidePanel !== "watches" ? " panel-hidden" : "")
                  }
                >
                  <WatchPanel
                    expanded
                    key={vid}
                    vehicle={current}
                    metrics={config.watch_metrics}
                    onSaved={(data: Json) => {
                      setWork(data);
                      setVehicles((items: Json[]) =>
                        items.map((v) =>
                          v.id === data.vehicle_id
                            ? { ...v, watches: data.watches }
                            : v,
                        ),
                      );
                    }}
                    onSettings={() => setTab("settings")}
                    onAsk={() => {
                      setSidePanel("chat");
                      setInteractionMode(true);
                      setInteractionTargets([vid]);
                      setChat(
                        "Help me set up watch rules for this vehicle. Ask me for the concerns, numerical thresholds and flight phases to watch. Alert and advise only; I choose vehicle actions.",
                      );
                      chatInput.current?.focus();
                    }}
                  />
                </div>
                <div
                  className={
                    "conversation" +
                    (sidePanel !== "chat" ? " panel-hidden" : "")
                  }
                >
                  {!work?.chat.length && (
                    <div className="copilot-intro">
                      <MessageSquare size={24} />
                      <h3>Copilot</h3>
                      <p>
                        Ask about telemetry, describe a mission, or configure
                        watch rules.
                      </p>
                      <div className="task-starters vertical">
                        {taskStarters(current.profile).map((task) => (
                          <button
                            key={task.title}
                            disabled={chatBusy}
                            onClick={() => describeTask(task.prompt)}
                          >
                            <Sparkles size={15} />
                            <span>
                              <strong>{task.title}</strong>
                              <small>{task.detail}</small>
                            </span>
                          </button>
                        ))}
                      </div>
                      <span>
                        Choose an idea to edit its request, then send it.
                      </span>
                    </div>
                  )}
                  {work?.chat.map((m: Json, i: number) => (
                    <div className={"chat-message " + m.role} key={i}>
                      <div className="card-kicker">
                        {m.role === "user"
                          ? "YOU"
                          : m.role === "error"
                            ? "INFERENCE ERROR"
                            : "COPILOT"}
                        <span>{clock(m.ts)}</span>
                      </div>
                      <p>{m.text}</p>
                      <ToolTrace steps={m.tool_trace} />
                      {m.change && (
                        <div className="change-card">
                          <strong>
                            Draft versions · {m.change.before.revision} →
                            {m.change.after.revision}
                          </strong>
                          <span>
                            {m.change.operations.length} operations ·{" "}
                            {m.change.before.waypoints.length} →{" "}
                            {m.change.after.waypoints.length} items
                          </span>
                          <details>
                            <summary>Inspect changes</summary>
                            <pre>
                              {JSON.stringify(m.change.operations, null, 2)}
                            </pre>
                          </details>
                          <button
                            disabled={
                              draft?.revision !== m.change.after.revision
                            }
                            onClick={() =>
                              guard(async () =>
                                setWork(
                                  await api(`/vehicles/${vid}/undo`, "POST", {
                                    expected_revision: draft.revision,
                                  }),
                                ),
                              )
                            }
                          >
                            <Undo2 size={13} />
                            Undo draft edit
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {work?.geofence_proposal && (
                    <div className="area-proposal">
                      <strong>AI geofence proposal</strong>
                      <p>{work.geofence_proposal.reason}</p>
                      <p>
                        {work.geofence_proposal.inclusions.length} inclusion ·{" "}
                        {work.geofence_proposal.exclusions.length} exclusion
                        areas. Inclusion mode:{" "}
                        {work.geofence_proposal.inclusion_mode}. Accept changes
                        the draft; upload is separate.
                      </p>
                      <div className="button-row">
                        <button
                          className="primary"
                          disabled={
                            work.geofence_proposal.base_revision !==
                              draft.revision ||
                            work.geofence_proposal.epoch !== current.epoch
                          }
                          onClick={() =>
                            guard(async () => {
                              setWork(
                                await api(
                                  `/vehicles/${vid}/geofences/accept`,
                                  "POST",
                                  { proposal_id: work.geofence_proposal.id },
                                ),
                              );
                            })
                          }
                        >
                          Accept areas
                        </button>
                        <button
                          onClick={() =>
                            guard(async () => {
                              setWork(
                                await api(
                                  `/vehicles/${vid}/geofences/dismiss`,
                                  "POST",
                                  { proposal_id: work.geofence_proposal.id },
                                ),
                              );
                            })
                          }
                        >
                          Dismiss
                        </button>
                      </div>
                      {work.geofence_proposal.base_revision !==
                        draft.revision && (
                        <p>Draft changed; request a new proposal.</p>
                      )}
                    </div>
                  )}
                  {work?.intent_proposal && (
                    <div className="review-card">
                      <div className="card-kicker">
                        PROPOSED INTENT · NOT ACTIVE
                      </div>
                      <p>{work.intent_proposal.explanation}</p>
                      <pre>
                        {JSON.stringify(work.intent_proposal.intent, null, 2)}
                      </pre>
                      <button
                        className="primary wide"
                        onClick={() =>
                          guard(async () =>
                            setWork(
                              await api(
                                `/vehicles/${vid}/intent/accept`,
                                "POST",
                                { proposal_id: work.intent_proposal.id },
                              ),
                            ),
                          )
                        }
                      >
                        Accept interpretation into draft
                      </button>
                      <small>
                        Activates for monitoring only when this draft is
                        uploaded and verified.
                      </small>
                    </div>
                  )}
                  {work?.parameter_proposals
                    ?.slice()
                    .reverse()
                    .map((p: Json) => (
                      <div className="parameter-proposal" key={p.id}>
                        <strong>
                          Parameter proposal · {current.profile}{" "}
                          {vid.slice(0, 6)}
                        </strong>
                        <span className="proposal-status">
                          {p.status.toUpperCase()}
                        </span>
                        {p.parameters.map((x: Json) => (
                          <div key={x.name}>
                            <code>{x.name}</code>
                            <b>
                              {fmt(x.expected, 3)} → {fmt(x.value, 3)}
                            </b>
                            <p>{x.reason}</p>
                          </div>
                        ))}
                        {p.error && <p className="red">{p.error}</p>}
                        {p.results?.map((r: Json) => (
                          <small key={r.job_id}>
                            {r.name}:{" "}
                            {r.result?.status || "Inspect job " + r.job_id}
                          </small>
                        ))}
                        {p.status === "pending" && (
                          <>
                            <small>
                              Expires {clock(p.expires_at)} · writes require a
                              disarmed owned simulator and control.
                            </small>
                            <div className="proposal-actions">
                              <button
                                className="primary"
                                disabled={
                                  !control ||
                                  current.armed ||
                                  !!busy ||
                                  !current.owned ||
                                  p.expires_at < Date.now() / 1000
                                }
                                onClick={() =>
                                  guard(async () => {
                                    setWork(
                                      await api(
                                        `/vehicles/${vid}/parameter-proposals/${p.id}/apply`,
                                        "POST",
                                        {},
                                      ),
                                    );
                                    await refresh();
                                  }, "parameters")
                                }
                              >
                                Apply to {vid.slice(0, 6)}
                              </button>
                              <button
                                disabled={!!busy}
                                onClick={() =>
                                  guard(async () =>
                                    setWork(
                                      await api(
                                        `/vehicles/${vid}/parameter-proposals/${p.id}/discard`,
                                        "POST",
                                        {},
                                      ),
                                    ),
                                  )
                                }
                              >
                                Discard
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  {(chatBusy || current.agent_run?.status === "running") && (
                    <ToolTrace
                      running
                      steps={current.agent_run?.steps || []}
                      round={current.agent_run?.round}
                      maxRounds={current.agent_run?.max_rounds}
                      onCancel={() =>
                        guard(() =>
                          api(`/vehicles/${vid}/agent/cancel`, "POST", {}),
                        )
                      }
                    />
                  )}
                  <div ref={chatBottom} />
                </div>
                <div
                  className={
                    "chat-compose" +
                    (sidePanel !== "chat" ? " panel-hidden" : "")
                  }
                >
                  {!interactionMode && (
                    <label className="edit-toggle">
                      <input
                        type="checkbox"
                        checked={editAuthorized}
                        onChange={(e) => setEditAuthorized(e.target.checked)}
                      />
                      Allow requested draft edits{" "}
                      <span>
                        {editAuthorized ? "DRAFT EDITOR" : "REVIEW ONLY"}
                      </span>
                    </label>
                  )}
                  {interactionMode && (
                    <div className="interaction-context">
                      Planning for:{" "}
                      {vehicles
                        .filter((v) => interactionTargets.includes(v.id))
                        .map((v) => `${v.profile} ${v.id.slice(0, 6)}`)
                        .join(", ") || "select a target above"}
                    </div>
                  )}
                  {interactionMode && (
                    <div className="map-attachment">
                      {mapAttachment ? (
                        <>
                          <img
                            src={mapAttachment.image}
                            alt="Map image attached to the next Copilot message"
                          />
                          <span>
                            Map attached · {mapAttachment.width} ×{" "}
                            {mapAttachment.height} · {config.model}
                          </span>
                          <button onClick={() => setMapAttachment(null)}>
                            Remove image
                          </button>
                        </>
                      ) : (
                        <button
                          disabled={
                            chatBusy ||
                            mapModelBlocked ||
                            !["plan", "flight"].includes(tab)
                          }
                          onClick={() =>
                            guard(async () => {
                              if (!captureMap.current)
                                throw Error("Open Plan to attach the map.");
                              setMapAttachment(await captureMap.current());
                            })
                          }
                        >
                          Attach map
                        </button>
                      )}
                      {mapModelBlocked && (
                        <span role="status">
                          {config.model}:{" "}
                          {modelCapabilities?.vision === false
                            ? "text only"
                            : "tool calls unavailable"}
                          . Choose a model with image and tool support.{" "}
                          <button onClick={() => setTab("settings")}>
                            Model settings
                          </button>
                        </span>
                      )}
                      {!mapModelBlocked &&
                        modelCapabilities?.vision == null && (
                          <span>
                            {modelCapabilities
                              ? "Image support unknown; check the selected model."
                              : "Checking image support…"}
                          </span>
                        )}
                      <a
                        href="/api/ai/capabilities"
                        target="_blank"
                        rel="noreferrer"
                      >
                        AI tool contract
                      </a>
                    </div>
                  )}
                  {(current.watches?.rules || []).some(
                    (r: Json) => r.origin === "AI proposal" && !r.enabled,
                  ) &&
                    sidePanel === "chat" && (
                      <button
                        className="pending-watch-link"
                        onClick={() => setSidePanel("watches")}
                      >
                        Review proposed watch rules →
                      </button>
                    )}
                  <div className="compose-box">
                    <textarea
                      ref={chatInput}
                      aria-label="Message Copilot"
                      placeholder={
                        interactionMode
                          ? "Describe a task, change this plan, or ask about your vehicle…"
                          : editAuthorized
                            ? "Describe a route or request a draft change…"
                            : "Ask about telemetry or review this mission…"
                      }
                      value={chat}
                      onChange={(e) => setChat(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          sendChat();
                        }
                      }}
                    />
                    <button
                      aria-label="Send to copilot"
                      disabled={
                        chatBusy ||
                        !chat.trim() ||
                        work?.vehicle_id !== vid ||
                        (interactionMode && !!mapAttachment && mapModelBlocked)
                      }
                      onClick={sendChat}
                    >
                      <Send size={18} />
                    </button>
                  </div>
                  <div className="chat-footer">
                    <span>
                      {interactionMode
                        ? "Drafts + areas + parameters + watches"
                        : "Local draft tools only"}
                    </span>
                  </div>
                </div>
              </aside>
            </div>
          )}
          <footer>
            <div>
              <span
                className={"dot " + (current?.heartbeat_age > 3 ? "bad" : "")}
              />
              {current
                ? `${current.profile.toUpperCase()} / SYS ${current.sysid ?? "—"} / EPOCH ${current.epoch}`
                : "AWAITING VEHICLE"}
              <span className="divider" />
              {current?.position
                ? `${fmt(current.position.lat, 6)}, ${fmt(current.position.lon, 6)}`
                : "No position"}
            </div>
            <div>
              {
                jobs.filter((j) => j.vehicle === vid && j.status === "pending")
                  .length
              }{" "}
              pending operations
              <span className="divider" />
              Backend owns GCS heartbeat
            </div>
          </footer>
        </main>
      </div>
      {evidence && (
        <div className="modal-backdrop" onClick={() => setEvidence(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="section-title">
              <h2>Evidence · {evidence.type}</h2>
              <button onClick={() => setEvidence(null)}>Close</button>
            </div>
            <pre>{JSON.stringify(evidence, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
