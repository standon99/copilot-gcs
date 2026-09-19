import type { Map } from "maplibre-gl";

export async function captureMapImage(
  map: Map,
  vehicle: any,
  vehicles: any[],
  draft: any,
) {
  const camera = {
    center: map.getCenter(),
    zoom: map.getZoom(),
    pitch: map.getPitch(),
    bearing: map.getBearing(),
  };
  const terrain = map.getTerrain();
  map.setTerrain(null);
  map.jumpTo({ pitch: 0, bearing: 0 });
  try {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        map.off("render", rendered);
        reject(
          Error("Map tiles are still loading. Wait a moment and send again."),
        );
      }, 8000);
      const rendered = () => {
        if (!map.areTilesLoaded()) return;
        window.clearTimeout(timeout);
        map.off("render", rendered);
        resolve();
      };
      map.on("render", rendered);
      map.triggerRepaint();
    });
    const source = map.getCanvas();
    const canvas = document.createElement("canvas");
    const factor = Math.min(1, 1280 / source.width, 1280 / source.height);
    canvas.width = Math.round(source.width * factor);
    canvas.height = Math.round(source.height * factor);
    const context = canvas.getContext("2d")!;
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    context.font = "12px sans-serif";
    for (let x = 0; x < canvas.width; x += 200)
      for (let y = 0; y < canvas.height; y += 200) {
        context.fillStyle = "#14202ba0";
        context.fillRect(x, y, 75, 17);
        context.fillStyle = "#fff";
        context.fillText(`${x},${y}`, x + 3, y + 12);
      }
    const annotations: any[] = [];
    const annotate = (
      kind: string,
      label: string,
      position: any,
      color: string,
      heading: number | null = null,
      age: number | null = null,
    ) => {
      if (
        !position ||
        !Number.isFinite(position.lon) ||
        !Number.isFinite(position.lat)
      )
        return;
      const p = map.project([position.lon, position.lat]);
      const x = (p.x * canvas.width) / source.clientWidth;
      const y = (p.y * canvas.height) / source.clientHeight;
      const inView =
        x >= 0 && x <= canvas.width && y >= 0 && y <= canvas.height;
      annotations.push({
        kind,
        label,
        coordinates: [position.lon, position.lat],
        pixel: [x, y],
        in_view: inView,
        heading_deg: heading,
        age_s: age,
      });
      if (!inView) return;
      context.beginPath();
      context.arc(x, y, kind === "aircraft" ? 8 : 5, 0, 2 * Math.PI);
      context.fillStyle = color;
      context.fill();
      context.strokeStyle = "#fff";
      context.lineWidth = 2;
      context.stroke();
      const width = context.measureText(label).width + 8;
      const tx = Math.max(0, Math.min(canvas.width - width, x + 10));
      const ty = Math.max(
        20,
        Math.min(canvas.height - 35, y + (kind === "home" ? 21 : -9)),
      );
      context.fillStyle = "#14202bee";
      context.fillRect(tx, ty - 13, width, 18);
      context.fillStyle = color;
      context.fillText(label, tx + 4, ty);
    };
    annotate("home", "HOME", vehicle.home, "#ffc46d");
    for (const v of vehicles.slice(0, 6))
      if (v.position_valid)
        annotate(
          "aircraft",
          `${v.id === vehicle.id ? "SELECTED " : ""}${v.profile.toUpperCase()} ${v.id.slice(0, 4)}`,
          v.position,
          "#80e0cb",
          v.heading,
          v.coverage?.GLOBAL_POSITION_INT ?? null,
        );
    for (const [i, w] of (draft?.waypoints || []).slice(0, 70).entries())
      if ([16, 17, 19, 21, 22].includes(w.command))
        annotate("waypoint", `WP ${i + 1}`, w, "#e7eaff");
    const bounds = map.getBounds();
    const metersPerPixel =
      (40075016.686 *
        Math.cos((map.getCenter().lat * Math.PI) / 180) *
        (bounds.getEast() - bounds.getWest())) /
      360 /
      canvas.width;
    const desired = metersPerPixel * Math.min(160, canvas.width / 4);
    const power = 10 ** Math.floor(Math.log10(desired));
    const scaleMeters =
      [5, 2, 1].map((n) => n * power).find((n) => n <= desired) || power;
    const length = scaleMeters / metersPerPixel;
    context.fillStyle = "#14202bee";
    context.fillRect(5, canvas.height - 71, Math.max(110, length + 18), 40);
    context.strokeStyle = "white";
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(14, canvas.height - 48);
    context.lineTo(14 + length, canvas.height - 48);
    context.stroke();
    context.fillStyle = "white";
    context.fillText(
      `${scaleMeters >= 1000 ? scaleMeters / 1000 + " km" : scaleMeters + " m"} · N ↑`,
      14,
      canvas.height - 57,
    );
    context.fillStyle = "#14202bee";
    context.fillRect(0, canvas.height - 24, canvas.width, 24);
    context.fillStyle = "white";
    context.fillText(
      "Imagery © Esri, Maxar, Earthstar Geographics | © OpenStreetMap contributors",
      8,
      canvas.height - 8,
    );
    return {
      vehicle_id: vehicle.id,
      draft_revision: draft.revision,
      captured_at: Date.now() / 1000,
      image: canvas.toDataURL("image/png"),
      width: canvas.width,
      height: canvas.height,
      bounds: [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ],
      annotations,
    };
  } finally {
    map.setTerrain(terrain);
    map.jumpTo(camera);
  }
}
