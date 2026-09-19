export function tiltedPitch(pitch, deltaY) {
  return Math.max(0, Math.min(65, pitch - deltaY * 0.22));
}

export function projectClip(matrix, point, width, height) {
  const p = [point.x, point.y, point.z, 1];
  const clip = [0, 0, 0, 0].map((_, row) =>
    p.reduce((sum, v, col) => sum + matrix[col * 4 + row] * v, 0),
  );
  return {
    clip,
    x: ((clip[0] / clip[3] + 1) * width) / 2,
    y: ((1 - clip[1] / clip[3]) * height) / 2,
    inFront: clip[3] > 0 && clip[2] >= -clip[3],
  };
}

// Include the vertical extent, not just the latitude/longitude footprint.
export function aircraftFitBounds(vehicles, groundAt) {
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  let count = 0;
  for (const v of vehicles) {
    const p = v.position;
    if (
      !v.position_valid ||
      !p ||
      !Number.isFinite(p.lat) ||
      !Number.isFinite(p.lon) ||
      (v.coverage?.GLOBAL_POSITION_INT ?? Infinity) > 3 ||
      (v.heartbeat_age ?? Infinity) > 3
    )
      continue;
    const ground = groundAt(p);
    const vertical =
      Number.isFinite(ground) && Number.isFinite(p.amsl)
        ? Math.max(0, p.amsl - ground)
        : 0;
    const radius = Math.max(60, vertical * 1.7);
    const latSpan = radius / 111320;
    const lonSpan = latSpan / Math.max(0.09, Math.cos((p.lat * Math.PI) / 180));
    bounds[0] = Math.min(bounds[0], p.lon - lonSpan);
    bounds[1] = Math.min(bounds[1], p.lat - latSpan);
    bounds[2] = Math.max(bounds[2], p.lon + lonSpan);
    bounds[3] = Math.max(bounds[3], p.lat + latSpan);
    count++;
  }
  return count ? bounds : null;
}
