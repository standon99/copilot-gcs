import * as maplibregl from "maplibre-gl";
import {
  type Map,
  type CustomLayerInterface,
  type CustomRenderMethodInput,
} from "maplibre-gl";
import { aircraftFitBounds, projectClip, tiltedPitch } from "./terrainMath.mjs";

const TERRAIN_TILES =
  "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";

export class TerrainView {
  map: Map;
  vehicles: any[] = [];
  selected = "";
  suspended = false;
  autoFrame = true;
  labels = new globalThis.Map<string, HTMLButtonElement>();
  lastFrame = 0;
  ready = false;
  pendingFit: number | null = null;
  onMode: (mode: boolean) => void;
  onSelect: (id: string) => void;
  layer: CustomLayerInterface;
  overlay: HTMLDivElement;
  program: WebGLProgram | null = null;
  buffer: WebGLBuffer | null = null;
  vao: WebGLVertexArrayObject | null = null;

  constructor(
    map: Map,
    onMode: (mode: boolean) => void,
    onSelect: (id: string) => void,
  ) {
    this.map = map;
    this.onMode = onMode;
    this.onSelect = onSelect;
    this.overlay = document.createElement("div");
    this.overlay.className = "aircraft-altitude-overlay";
    map.getCanvasContainer().append(this.overlay);
    this.layer = {
      id: "aircraft-altitude",
      type: "custom",
      renderingMode: "3d",
      onAdd: (_map, gl) => this.setup(gl),
      render: (gl, options) => this.render(gl, options),
      onRemove: (_map, gl) => {
        if (this.program) gl.deleteProgram(this.program);
        if (this.buffer) gl.deleteBuffer(this.buffer);
        if (this.vao) gl.deleteVertexArray(this.vao);
      },
    };
    map.addSource("elevation", {
      type: "raster-dem",
      tiles: [TERRAIN_TILES],
      tileSize: 256,
      encoding: "terrarium",
      maxzoom: 15,
      attribution:
        '<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md">Terrain: Mapzen/AWS sources</a>',
    });
    map.addLayer(this.layer);
    map
      .getCanvas()
      .addEventListener("wheel", this.wheel, { passive: false, capture: true });
    map.on("pitch", this.pitch);
    map.on("dragstart", this.drag);
    map.on("sourcedata", this.sourceData);
  }

  setup(gl: WebGL2RenderingContext) {
    const compile = (type: number, text: string) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, text);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS))
        throw Error("Aircraft layer shader failed");
      return shader;
    };
    const vertex = compile(
      gl.VERTEX_SHADER,
      `#version 300 es
      in vec4 a_clip; uniform float u_size; void main(){gl_Position=a_clip; gl_PointSize=u_size;}`,
    );
    const fragment = compile(
      gl.FRAGMENT_SHADER,
      `#version 300 es
      precision highp float; uniform vec4 u_color; uniform bool u_point; out vec4 color;
      void main(){if(u_point && distance(gl_PointCoord,vec2(0.5))>0.5)discard; color=u_color;}`,
    );
    this.program = gl.createProgram()!;
    gl.attachShader(this.program, vertex);
    gl.attachShader(this.program, fragment);
    gl.linkProgram(this.program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(this.program, gl.LINK_STATUS))
      throw Error("Aircraft layer link failed");
    this.buffer = gl.createBuffer();
    this.vao = gl.createVertexArray();
  }

  wheel = (event: WheelEvent) => {
    if (
      event.ctrlKey ||
      event.metaKey ||
      Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
      this.suspended
    )
      return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const delta = event.deltaY * (event.deltaMode === 1 ? 12 : 1);
    const next = tiltedPitch(this.map.getPitch(), delta);
    if (next > 0 && !this.map.getTerrain())
      this.map.setTerrain({ source: "elevation", exaggeration: 1 });
    this.map.setPitch(next);
  };

  pitch = () => {
    if (this.suspended) return;
    const active = this.map.getPitch() > 1;
    this.onMode(active);
    if (active && !this.map.getTerrain())
      this.map.setTerrain({ source: "elevation", exaggeration: 1 });
    if (!active && this.map.getTerrain()) this.map.setTerrain(null);
    this.map.getContainer().classList.toggle("terrain-active", active);
    if (!active) this.overlay.replaceChildren();
    if (!active) this.labels.clear();
  };

  drag = () => {
    this.autoFrame = false;
    this.pendingFit = null;
  };

  sourceData = () => {
    if (this.pendingFit == null || !this.map.isSourceLoaded("elevation"))
      return;
    const pitch = this.pendingFit;
    this.pendingFit = null;
    requestAnimationFrame(() => {
      if (!this.suspended && this.map.getPitch() > 1) this.fit(pitch);
    });
  };

  setMode(active: boolean) {
    this.autoFrame = true;
    if (!active) this.pendingFit = null;
    if (active) this.map.setTerrain({ source: "elevation", exaggeration: 1 });
    this.map.easeTo({ pitch: active ? 55 : 0, duration: 450 });
    if (active) this.fit(55);
  }

  update(vehicles: any[], selected: string) {
    this.vehicles = vehicles;
    this.selected = selected;
    this.map.triggerRepaint();
  }

  fit(pitch = Math.max(30, this.map.getPitch())) {
    this.autoFrame = true;
    if (!this.map.isSourceLoaded("elevation")) {
      this.pendingFit = pitch;
      return;
    }
    const b = aircraftFitBounds(this.vehicles, (p: any) =>
      this.map.getBounds().contains([p.lon, p.lat])
        ? this.map.queryTerrainElevation([p.lon, p.lat])
        : null,
    );
    if (b)
      this.map.fitBounds(
        [
          [b[0], b[1]],
          [b[2], b[3]],
        ],
        {
          padding: { top: 100, bottom: 75, left: 75, right: 75 },
          maxZoom: 18,
          pitch,
          duration: 450,
        },
      );
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    // MapLibre returns zero while DEM tiles are missing. Do not interpret that
    // as sea-level terrain or use it to frame aircraft hundreds of metres high.
    this.overlay.hidden =
      this.suspended ||
      this.map.getPitch() <= 1 ||
      !this.map.getTerrain() ||
      !this.map.isSourceLoaded("elevation");
    if (!this.program || this.overlay.hidden) return;
    const canvas = this.map.getCanvas();
    const matrix = options.defaultProjectionData.mainMatrix;
    const points: number[] = [],
      lines: number[] = [],
      ids = new Set<string>();
    let outside = false;
    const width = canvas.clientWidth,
      height = canvas.clientHeight;
    const labelBoxes: {
      x: number;
      y: number;
      width: number;
      height: number;
    }[] = [];
    const ordered = [...this.vehicles].sort(
      (a, b) => Number(b.id === this.selected) - Number(a.id === this.selected),
    );
    for (const v of ordered) {
      const p = v.position;
      if (
        !v.position_valid ||
        !p ||
        !Number.isFinite(p.amsl) ||
        !Number.isFinite(p.lon) ||
        !Number.isFinite(p.lat) ||
        v.coverage?.GLOBAL_POSITION_INT == null ||
        v.coverage.GLOBAL_POSITION_INT > 3 ||
        v.heartbeat_age > 3
      )
        continue;
      const ground = this.map.queryTerrainElevation([p.lon, p.lat]);
      if (ground == null || !Number.isFinite(ground)) continue;
      const air = projectClip(
        matrix,
        maplibregl.MercatorCoordinate.fromLngLat([p.lon, p.lat], p.amsl),
        width,
        height,
      );
      const base = projectClip(
        matrix,
        maplibregl.MercatorCoordinate.fromLngLat([p.lon, p.lat], ground),
        width,
        height,
      );
      if (air.inFront) points.push(...air.clip);
      if (air.inFront && base.inFront) lines.push(...base.clip, ...air.clip);
      ids.add(v.id);
      let label = this.labels.get(v.id);
      if (!label) {
        label = document.createElement("button");
        label.className = "aircraft-altitude-label";
        label.onclick = (e) => {
          e.stopPropagation();
          this.onSelect(v.id);
        };
        this.overlay.append(label);
        this.labels.set(v.id, label);
      }
      label.textContent = `${v.profile.toUpperCase()} ${v.id.slice(0, 4)} · ${Math.round(p.amsl)} m AMSL`;
      label.title = `Terrain ${Math.round(ground)} m · ${Math.round(p.amsl - ground)} m above mapped terrain`;
      label.classList.toggle("current", v.id === this.selected);
      const visible =
        air.inFront &&
        air.x >= 0 &&
        air.x <= width &&
        air.y >= 0 &&
        air.y <= height;
      label.hidden = !visible;
      if (visible) {
        const box = {
          x: Math.max(5, Math.min(width - label.offsetWidth - 5, air.x + 9)),
          y: Math.max(5, air.y - 12),
          width: label.offsetWidth,
          height: label.offsetHeight,
        };
        for (const other of labelBoxes)
          if (
            box.x < other.x + other.width + 4 &&
            box.x + box.width + 4 > other.x &&
            box.y < other.y + other.height + 4 &&
            box.y + box.height + 4 > other.y
          )
            box.y = other.y + other.height + 4;
        box.y = Math.min(height - box.height - 5, box.y);
        labelBoxes.push(box);
        label.style.transform = `translate(${box.x}px,${box.y}px)`;
      }
      outside ||=
        !air.inFront ||
        air.x < 70 ||
        air.x > width - 170 ||
        air.y < 90 ||
        air.y > height - 70;
    }
    for (const [id, label] of this.labels)
      if (!ids.has(id)) {
        label.remove();
        this.labels.delete(id);
      }
    // The regular marker remains as the aircraft's ground footprint.
    this.ready = ids.size > 0;
    gl.useProgram(this.program);
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    const location = gl.getAttribLocation(this.program, "a_clip");
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, 4, gl.FLOAT, false, 0, 0);
    gl.enable(gl.DEPTH_TEST);
    gl.depthMask(false);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.uniform1f(
      gl.getUniformLocation(this.program, "u_size"),
      12 * devicePixelRatio,
    );
    gl.uniform4f(
      gl.getUniformLocation(this.program, "u_color"),
      0.45,
      0.95,
      0.84,
      0.65,
    );
    gl.uniform1i(gl.getUniformLocation(this.program, "u_point"), 0);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lines), gl.DYNAMIC_DRAW);
    gl.drawArrays(gl.LINES, 0, lines.length / 4);
    gl.uniform4f(
      gl.getUniformLocation(this.program, "u_color"),
      0.5,
      1,
      0.86,
      1,
    );
    gl.uniform1i(gl.getUniformLocation(this.program, "u_point"), 1);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.DYNAMIC_DRAW);
    gl.drawArrays(gl.POINTS, 0, points.length / 4);
    gl.disableVertexAttribArray(location);
    gl.bindVertexArray(null);
    if (
      outside &&
      this.autoFrame &&
      !this.map.isMoving() &&
      performance.now() - this.lastFrame > 300 &&
      this.map.getZoom() > 2
    ) {
      this.lastFrame = performance.now();
      requestAnimationFrame(() => {
        if (!this.suspended) this.map.setZoom(this.map.getZoom() - 0.25);
      });
    }
  }

  destroy() {
    this.map.getCanvas().removeEventListener("wheel", this.wheel, true);
    this.map.off("pitch", this.pitch);
    this.map.off("dragstart", this.drag);
    this.map.off("sourcedata", this.sourceData);
    this.overlay.remove();
    this.labels.clear();
  }
}
