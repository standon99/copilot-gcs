"""Validated exclusion geometry and georeferenced, operator-attached map images."""

import base64
import hashlib
import math
import struct
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import Polygon


def validate_polygons(polygons):
    if len(polygons) > 20:
        raise ValueError("At most 20 exclusion areas")
    result = []
    for points in polygons:
        ring = [tuple(p) for p in points]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        if (
            not 3 <= len(ring) <= 1000
            or any(not (-180 <= x <= 180 and -85 <= y <= 85) for x, y in ring)
            or len(set(ring)) != len(ring)
            or max(x for x, _ in ring) - min(x for x, _ in ring) > 180
            or not Polygon(ring).is_valid
            or Polygon(ring).area <= 1e-14
        ):
            raise ValueError(
                "Exclusion areas need 3–1000 distinct vertices and a non-crossing boundary; "
                "polar and antimeridian polygons are unsupported"
            )
        result.append(ring)
    return result


class MapImage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: str
    draft_revision: int
    captured_at: float = Field(allow_inf_nan=False)
    image: str = Field(max_length=4_000_000)
    width: int = Field(ge=64, le=1600)
    height: int = Field(ge=64, le=1600)
    # North-up, zero-pitch Web Mercator; bounds are west, south, east, north.
    bounds: tuple[float, float, float, float]

    @model_validator(mode="after")
    def valid(self):
        west, south, east, north = self.bounds
        if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
            raise ValueError("Map capture needs non-wrapping geographic bounds")
        if east - west > 5 or north - south > 5:
            raise ValueError("Zoom in before attaching the map (maximum extent 5 degrees)")
        if not -10 <= time.time() - self.captured_at <= 180:
            raise ValueError("Map image expired; attach a fresh view")
        if not self.image.startswith("data:image/png;base64,"):
            raise ValueError("Only a PNG map capture is accepted")
        try:
            data = base64.b64decode(self.image.split(",", 1)[1], validate=True)
            if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
                raise ValueError()
            if struct.unpack(">II", data[16:24]) != (self.width, self.height):
                raise ValueError()
        except (ValueError, struct.error) as exc:
            raise ValueError("Map image dimensions/encoding are invalid") from exc
        return self

    def context(self):
        return {
            **self.model_dump(exclude={"image"}),
            "projection": "Web Mercator, north-up, zero pitch",
            "pixel_origin": "top left; x right, y down; use image pixels, not screen pixels",
            "sha256": hashlib.sha256(self.image.encode()).hexdigest(),
        }

    def geographic(self, point):
        x, y = point
        if not (0 <= x <= self.width and 0 <= y <= self.height):
            raise ValueError("Proposed vertex is outside the attached map image")
        west, south, east, north = self.bounds
        top = math.asinh(math.tan(math.radians(north)))
        bottom = math.asinh(math.tan(math.radians(south)))
        return (
            west + x / self.width * (east - west),
            math.degrees(math.atan(math.sinh(top + y / self.height * (bottom - top)))),
        )


class ExclusionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)
    coordinate_space: Literal["geographic", "map_pixels"] = "geographic"
    polygons: list[list[tuple[float, float]]] = Field(max_length=20)

    def resolve(self, map_image=None):
        polygons = self.polygons
        if self.coordinate_space == "map_pixels":
            if map_image is None:
                raise ValueError("Pixel vertices require an operator-attached map image")
            polygons = [[map_image.geographic(p) for p in ring] for ring in polygons]
        return {"reason": self.reason, "polygons": validate_polygons(polygons)}
