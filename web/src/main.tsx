import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { api } from "./api";
import { SettingsPanel } from "./SettingsPanel";
import { AttitudeIndicator } from "./AttitudeIndicator";
import { FencePanel } from "./FencePanel";
import { WatchPanel } from "./WatchPanel";
import { MissionWorkflow } from "./MissionWorkflow";
import { missionProgress, taskStarters, uploadReason } from "./missionFlow.mjs";
import { registerGroundStationTools } from "./webmcp";
import * as maplibregl from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import {
  Map as MapIcon,
  SlidersHorizontal,
  FileText,
  FlaskConical,
  Settings,
  ChevronRight,
  Send,
  Plus,
  Undo2,
  Upload,
  ShieldCheck,
  Navigation,
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
}: Json) {
  const el = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map>(null),
    markers = useRef<maplibregl.Marker[]>([]),
    vehicleMarkers = useRef<Record<string, maplibregl.Marker>>({}),
    cueMarkers = useRef<Record<string, maplibregl.Marker>>({}),
    centered = useRef(false);
  const props = useRef<Json>({});
  props.current = {
    vehicle,
    draft,
    editing,
    onAdd,
    onMove,
    setSelected,
    onSelectVehicle,
  };
  const renderMap = useRef<() => void>(() => {});
  const [sat, setSat] = useState(true),
    [mapError, setMapError] = useState("");
  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!,
      center: [home.lon, home.lat],
      zoom: 16,
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
      if (props.current.editing)
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
    for (const ring of draft?.intent?.exclusions || [])
      features.push({
        type: "Feature",
        properties: { kind: "exclusion" },
        geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] },
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
      const marker = new maplibregl.Marker({ element: b, draggable: editing })
        .setLngLat([w.lon, w.lat])
        .addTo(m);
      marker.on("dragend", () => {
        const p = marker.getLngLat();
        props.current.onMove(w.id, p.lat, p.lng);
      });
      markers.current.push(marker);
    }
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
  ]);
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
              ? "MISSION EDITOR · CLICK TO ADD"
              : "LIVE OPERATIONS"}
        </span>
        <div className="map-buttons">
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
        {editing
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
    [tab, setTab] = useState("plan");
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
    [mode, setMode] = useState(""),
    [takeoffAlt, setTakeoffAlt] = useState(20),
    [logEntries, setLogEntries] = useState<Json[]>([]);
  const [evidence, setEvidence] = useState<Json>(null);
  const chatInput = useRef<HTMLTextAreaElement>(null);
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
    setInteractionTargets(vid ? [vid] : []);
    setParams(null);
    setStaged({});
    setSelected("");
    setControl(false);
    setMode("");
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
      setNotice(
        `Mission version ${draft.revision} uploaded and verified. Open Operate to arm and start.`,
      );
    }, "upload");
  const sendChat = () => {
    if (!chat.trim() || chatBusy || !current || work?.vehicle_id !== vid)
      return;
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
        });
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
  if (!config)
    return (
      <div className="loading">
        <Radio /> Connecting to the local ground station…
        {error && <p>{error}</p>}
      </div>
    );
  return (
    <div className="app">
      <header>
        <div className="brand">
          <div className="brand-symbol">
            <img src="/icon.svg" alt="" width="38" height="38" />
          </div>
          <div>
            <strong>
              COPILOT <span>GCS</span>
            </strong>
            <small>AI-ENABLED GROUND CONTROL</small>
          </div>
        </div>
        <div className="header-center">
          <span className={"dot " + (wsState ? "" : "bad")} />
          <span>
            {wsState ? "LOCAL GATEWAY ONLINE" : "GATEWAY DISCONNECTED"}
          </span>
          <span className="divider" />
          <span className="sitl-label">
            {current
              ? current.owned
                ? "SIMULATION"
                : "TELEMETRY CONNECTION"
              : "BUILT FOR ARDUPILOT"}
          </span>
        </div>
        <button onClick={() => setTab("settings")} className="model-chip">
          <span className={"dot " + (config.configured ? "" : "bad")} />
          {config.model}
          <ChevronDown size={14} />
        </button>
      </header>
      <div className="body">
        <nav className="rail">
          {[
            ["plan", MapIcon, "Plan"],
            ["flight", Navigation, "Operate"],
            ["parameters", SlidersHorizontal, "Parameters"],
            ["logs", FileText, "Logs"],
            ["lab", FlaskConical, "Diagnostics"],
            ["settings", Settings, "Settings"],
          ].map(([id, Icon, label]: any) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
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
                  <small>
                    Copilot prepares changes. You review and apply them.
                  </small>
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
              <h1>What do you want your drone to do?</h1>
              <p>
                Turn a simple task into a mission with AI. Describe a flight or
                inspection, review the plan on the map, then put it to work.
              </p>
              <div className="task-brief">
                <label htmlFor="task-brief">Describe your task</label>
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
                    {busy === "launch" ? "Starting…" : "Continue in simulation"}
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
              <div className="welcome-steps">
                <span>1. Describe</span>
                <ChevronRight size={14} />
                <span>2. Review</span>
                <ChevronRight size={14} />
                <span>3. Upload</span>
                <ChevronRight size={14} />
                <span>4. Operate</span>
              </div>
              <small>
                Current release: control simulated vehicles; connect external
                telemetry for monitoring.
              </small>
            </div>
          )}
          {current && tab !== "settings" && (
            <div className="workspace">
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
                      onOperate={() => setTab("flight")}
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
                    />
                    {tab === "flight" ? (
                      <div className="flight-bottom">
                        <AttitudeIndicator vehicle={current} />
                        <div className="section-title">
                          <h2>Vehicle controls</h2>
                          <span>
                            {current.owned
                              ? "Owned simulator"
                              : "Read-only connection"}
                          </span>
                        </div>
                        <p className="control-help">
                          Enable vehicle controls reserves this vehicle for this
                          browser for 30 seconds, renewed while open. It does
                          not arm or start it.
                        </p>
                        <p className="control-help">
                          To run a mission: review and upload in Plan → set{" "}
                          {current.profile === "copter"
                            ? "GUIDED"
                            : current.profile === "plane"
                              ? "FBWA"
                              : "HOLD"}{" "}
                          → Arm → Start mission.{" "}
                          {current.profile !== "rover" &&
                            "A ground-start mission needs a Takeoff item first."}{" "}
                          Native prearm checks still apply; inspect status
                          messages if refused.
                        </p>
                        <div className="controls">
                          <button
                            className={control ? "claimed" : "primary"}
                            disabled={!current.owned}
                            onClick={claimControl}
                          >
                            <Radio size={15} />
                            {control
                              ? "Control held"
                              : "Enable vehicle controls"}
                          </button>
                          <select
                            aria-label="Flight mode"
                            value={mode}
                            onChange={(e) => setMode(e.target.value)}
                          >
                            <option value="">Select mode</option>
                            {profile?.modes.map((m: string) => (
                              <option key={m}>{m}</option>
                            ))}
                          </select>
                          <button
                            disabled={!control || !mode}
                            onClick={() =>
                              guard(() => runAction("mode", { mode }))
                            }
                          >
                            Set mode
                          </button>
                          <button
                            disabled={!control}
                            className={current.armed ? "" : "arm"}
                            onClick={() =>
                              guard(() =>
                                runAction("arm", { armed: !current.armed }),
                              )
                            }
                          >
                            {current.armed ? (
                              <Square size={14} />
                            ) : (
                              <Play size={14} />
                            )}{" "}
                            {current.armed ? "Disarm" : "Arm"}
                          </button>
                          {current.profile === "copter" && (
                            <>
                              <input
                                aria-label="Takeoff altitude"
                                type="number"
                                min="1"
                                max="120"
                                value={takeoffAlt}
                                onChange={(e) => setTakeoffAlt(+e.target.value)}
                              />
                              <button
                                disabled={
                                  !control ||
                                  !current.armed ||
                                  current.mode !== "GUIDED"
                                }
                                onClick={() =>
                                  guard(() =>
                                    runAction("takeoff", { alt: takeoffAlt }),
                                  )
                                }
                              >
                                Take off
                              </button>
                            </>
                          )}
                          <button
                            disabled={!control}
                            onClick={() =>
                              guard(() =>
                                runAction("mode", {
                                  mode:
                                    current.profile === "rover"
                                      ? "HOLD"
                                      : "RTL",
                                }),
                              )
                            }
                          >
                            {current.profile === "rover"
                              ? "Hold"
                              : "Return home"}
                          </button>
                        </div>
                        <button
                          className="primary"
                          disabled={
                            !control ||
                            !current.armed ||
                            !work?.active ||
                            !!busy
                          }
                          onClick={() => guard(() => runAction("start"))}
                        >
                          <Play size={14} /> Start mission
                        </button>
                        {!work?.active && (
                          <small>
                            Upload and verify a mission first. Arming and
                            starting are separate actions.
                          </small>
                        )}
                        <div className="rule-grid">
                          {current.rules.length ? (
                            current.rules.map((r: Json) => (
                              <div
                                key={r.code}
                                className={"rule " + r.severity}
                              >
                                <AlertTriangle size={15} />
                                <div>
                                  <strong>{r.code.replaceAll("_", " ")}</strong>
                                  <p>{r.text}</p>
                                </div>
                              </div>
                            ))
                          ) : (
                            <div className="rule info">
                              <ShieldCheck size={20} />
                              <div>
                                <strong>No deterministic alerts</strong>
                                <p>
                                  Only configured checks are covered. See
                                  telemetry freshness and AI assessment.
                                </p>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
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
                            <button className="primary" onClick={review}>
                              <ShieldCheck size={15} />
                              Review plan
                            </button>
                          </div>
                        </div>
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
                          control={control}
                          onClaim={claimControl}
                          onChanged={() =>
                            setNotice(
                              "Onboard fence verified. Use Fit all / zoom out to see the amber circle.",
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
                              Exclusion polygons · JSON arrays of [longitude,
                              latitude]
                              <textarea
                                key={draft.revision + "polygons"}
                                defaultValue={JSON.stringify(
                                  draft.intent.exclusions,
                                )}
                                onBlur={(e) =>
                                  guard(async () => {
                                    const x = JSON.parse(e.target.value);
                                    if (
                                      JSON.stringify(x) !==
                                      JSON.stringify(draft.intent.exclusions)
                                    )
                                      await save({
                                        ...draft,
                                        intent: {
                                          ...draft.intent,
                                          exclusions: x,
                                        },
                                      });
                                  })
                                }
                              />
                            </label>
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
                    <h1>Practice handling the unexpected.</h1>
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
                    {duration < config.monitor_interval && (
                      <p className="editor-help">
                        Your {config.monitor_interval}s assessment delay exceeds
                        this {duration}s observation window. Increase the trial
                        duration or lower the delay in Settings to collect
                        assessments after the fault. Trials do not silently
                        increase your request rate.
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
                      ? "Live insights paused · chat is available"
                      : !current.monitor_enabled
                        ? "Live insights paused for this vehicle"
                        : current.monitor_status}
                  </span>
                  <button
                    title={
                      current.monitor_enabled
                        ? "Pause monitor"
                        : "Resume monitor"
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
                <WatchPanel
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
                    setInteractionMode(true);
                    setInteractionTargets([vid]);
                    setChat(
                      "Help me set up watch rules for this vehicle. Ask me for the concerns, numerical thresholds and flight phases to watch. Alert and advise only; I choose vehicle actions.",
                    );
                    chatInput.current?.focus();
                  }}
                />
                <div className="conversation">
                  {current.recording_error && (
                    <div className="persistent-alert critical">
                      {current.recording_error}
                    </div>
                  )}
                  {current.rules
                    .filter(
                      (r: Json) =>
                        r.severity === "critical" || r.severity === "warning",
                    )
                    .map((r: Json) => (
                      <div
                        key={r.code}
                        className={"persistent-alert " + r.severity}
                      >
                        <AlertTriangle size={14} />
                        <span>{r.text}</span>
                      </div>
                    ))}
                  {current.assessment && (
                    <div
                      className={
                        "assessment " +
                        (current.assessment_stale
                          ? "insufficient_data"
                          : current.assessment.status)
                      }
                    >
                      <div className="card-kicker">
                        {current.assessment_stale
                          ? "STALE ASSESSMENT · NOT CURRENT"
                          : "CONTINUOUS ASSESSMENT"}{" "}
                        <span>{clock(current.assessment.completed_at)}</span>
                      </div>
                      <p>{current.assessment.summary}</p>
                      {current.assessment.incidents.map(
                        (i: Json, n: number) => (
                          <div className={"incident " + i.severity} key={n}>
                            <strong>{i.summary}</strong>
                            <p>{i.recommendation}</p>
                            <div className="evidence-links">
                              {i.evidence.map((id: string, k: number) => (
                                <button
                                  key={id}
                                  onClick={() => openEvidence(id)}
                                >
                                  Evidence {k + 1}
                                </button>
                              ))}
                            </div>
                          </div>
                        ),
                      )}
                      <small>
                        Data age{" "}
                        {fmt(
                          Date.now() / 1000 - current.assessment.observed_at,
                          0,
                        )}{" "}
                        s · {current.assessment.track} · advisory
                      </small>
                    </div>
                  )}
                  {!work?.chat.length && !current.assessment && (
                    <div className="copilot-intro">
                      <MessageSquare size={24} />
                      <h3>Let's plan your next task.</h3>
                      <p>
                        Describe a waypoint flight or inspection. I'll help
                        prepare the mission, explain the steps and revise it
                        with you.
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
                  {work?.checks && draft?.waypoints.length > 0 && (
                    <div className="review-card">
                      <div className="card-kicker">
                        PLAN REVIEW <span>VERSION {draft.revision}</span>
                      </div>
                      <h3>
                        {work.review ? "Review complete" : "Draft checks"}
                      </h3>
                      <div className="review-stats">
                        <span>{draft.waypoints.length} items</span>
                        <span>
                          {fmt(work.checks.distance_m / 1000, 2)} km route
                        </span>
                        <span>
                          {
                            work.checks.findings.filter(
                              (f: Json) => f.severity === "error",
                            ).length
                          }{" "}
                          blockers
                        </span>
                      </div>
                      {work.checks.findings.map((f: Json, i: number) => (
                        <button
                          className={"finding " + f.severity}
                          key={i}
                          onClick={() => {
                            if (f.waypoint) {
                              setSelected(f.waypoint);
                              setTab("plan");
                            }
                          }}
                        >
                          <span>
                            {f.severity === "error"
                              ? "!"
                              : f.severity === "warning"
                                ? "△"
                                : "?"}
                          </span>
                          {f.text}
                        </button>
                      ))}
                      <small>
                        Reviewed means these checks ran. Unknowns are not safety
                        assurances.
                      </small>
                      <button
                        className="primary wide"
                        disabled={
                          !missionProgress(work, current).reviewed ||
                          missionProgress(work, current).uploaded ||
                          !current.owned ||
                          !control ||
                          current.armed ||
                          !!busy ||
                          chatBusy
                        }
                        onClick={uploadMission}
                      >
                        <Upload size={15} />
                        {busy === "upload"
                          ? "Uploading & verifying…"
                          : missionProgress(work, current).uploaded
                            ? `Uploaded & verified · version ${draft.revision}`
                            : `Upload mission · version ${draft.revision}`}
                      </button>
                      <small className="upload-reason">
                        {uploadReason(
                          work,
                          current,
                          control,
                          !!busy || chatBusy,
                        )}
                      </small>
                      {!work.review && (
                        <button className="wide" onClick={review}>
                          Review plan
                        </button>
                      )}
                      {!control && (
                        <button className="wide" onClick={claimControl}>
                          Enable vehicle controls
                        </button>
                      )}
                    </div>
                  )}
                  {work?.active && (
                    <div className="active-plan">
                      <Check size={17} />
                      <div>
                        <strong>
                          Onboard mission · version {work.active.revision}
                        </strong>
                        <span>
                          Upload verified · intent pinned to this version
                        </span>
                        <button
                          disabled={!control || !current.armed}
                          onClick={() => guard(() => runAction("start"))}
                        >
                          <Play size={14} />
                          Start mission
                        </button>
                      </div>
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
                  {chatBusy && (
                    <div className="thinking">
                      <span className="dot" />
                      Checking context with {config.model}…
                    </div>
                  )}
                  <div ref={chatBottom} />
                </div>
                <div className="chat-compose">
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
                        chatBusy || !chat.trim() || work?.vehicle_id !== vid
                      }
                      onClick={sendChat}
                    >
                      <Send size={18} />
                    </button>
                  </div>
                  <div className="chat-footer">
                    <span>
                      {interactionMode
                        ? "Mission drafts + parameters + watch rules"
                        : "Local draft tools only"}
                    </span>
                    <span>You approve vehicle actions</span>
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
