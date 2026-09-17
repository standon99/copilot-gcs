import React, { useId } from "react";

const number = (v: any, digits = 1) =>
  Number.isFinite(v) ? v.toFixed(digits) : "—";
export function AttitudeIndicator({ vehicle: v }: { vehicle: any }) {
  const clip = useId().replace(/:/g, "");
  const attitudeFresh =
    (v.coverage?.ATTITUDE ?? 999) <= 3 && (v.heartbeat_age ?? 999) <= 3;
  const valid =
    attitudeFresh &&
    Number.isFinite(v.attitude?.roll) &&
    Number.isFinite(v.attitude?.pitch);
  const roll = valid ? (v.attitude.roll * 180) / Math.PI : 0;
  const pitch = valid ? (v.attitude.pitch * 180) / Math.PI : 0;
  const positionFresh = (v.coverage?.GLOBAL_POSITION_INT ?? 999) <= 3;
  const hudFresh = (v.coverage?.VFR_HUD ?? 999) <= 3;
  return (
    <section
      className={"attitude-instrument" + (valid ? "" : " stale")}
      aria-label="Flight instruments"
    >
      <div className="instrument-heading">
        <strong>ATTITUDE / FLIGHT DATA</strong>
        <span>
          {v.profile.toUpperCase()} {v.id.slice(0, 4)} · {v.mode}
        </span>
      </div>
      <div className="instrument-body">
        <svg
          viewBox="0 0 300 230"
          role="img"
          aria-label={
            valid
              ? `Roll ${number(roll)} degrees, pitch ${number(pitch)} degrees`
              : "Attitude unavailable or stale"
          }
        >
          <defs>
            <clipPath id={clip}>
              <rect x="16" y="8" width="268" height="208" rx="16" />
            </clipPath>
            <clipPath id={`${clip}-ladder`}>
              <rect x="18" y="48" width="264" height="137" />
            </clipPath>
          </defs>
          <g clipPath={`url(#${clip})`}>
            <rect x="0" y="0" width="300" height="230" fill="#142333" />
            <g
              transform={`translate(150 112) rotate(${-roll}) translate(0 ${pitch * 2.2})`}
            >
              <rect
                x="-650"
                y="-650"
                width="1300"
                height="650"
                fill="#306a92"
              />
              <rect x="-650" y="0" width="1300" height="650" fill="#775437" />
              <path d="M -650 0 H 650" stroke="#f3f4e9" strokeWidth="2" />
            </g>
            <g clipPath={`url(#${clip}-ladder)`}>
              <g
                transform={`translate(150 112) rotate(${-roll}) translate(0 ${pitch * 2.2})`}
              >
                {[
                  -80, -70, -60, -50, -40, -30, -20, -10, 10, 20, 30, 40, 50,
                  60, 70, 80,
                ].map((deg) => (
                  <g key={deg} transform={`translate(0 ${-deg * 2.2})`}>
                    <path
                      d={`M ${deg % 20 === 0 ? -38 : -24} 0 H ${deg % 20 === 0 ? 38 : 24}`}
                      stroke="white"
                      strokeWidth="1.3"
                      strokeDasharray={deg < 0 ? "4 3" : undefined}
                    />
                    <text
                      x="-46"
                      y="4"
                      textAnchor="end"
                      fill="white"
                      fontSize="10"
                    >
                      {deg}
                    </text>
                    <text x="46" y="4" fill="white" fontSize="10">
                      {deg}
                    </text>
                  </g>
                ))}
              </g>
            </g>
            {[-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60].map((deg) => (
              <path
                key={deg}
                transform={`rotate(${deg} 150 112)`}
                d={`M 150 20 V ${deg % 30 === 0 ? 33 : 27}`}
                stroke="white"
                strokeWidth="2"
              />
            ))}
            <path
              transform={`rotate(${-roll} 150 112)`}
              d="M 150 35 L 144 44 H 156 Z"
              fill="#ffe395"
            />
            <path
              d="M 78 112 H 127 V 119 M 173 119 V 112 H 222 M 144 112 H 156"
              fill="none"
              stroke="#ffdf76"
              strokeWidth="4"
            />
            {!valid && (
              <>
                <rect
                  x="16"
                  y="8"
                  width="268"
                  height="208"
                  fill="#101a25"
                  opacity="0.78"
                />
                <text
                  x="150"
                  y="110"
                  fill="#ffc46d"
                  textAnchor="middle"
                  fontSize="13"
                >
                  NO FRESH ATTITUDE
                </text>
              </>
            )}
            <rect
              x="16"
              y="188"
              width="268"
              height="28"
              fill="#101b26"
              opacity="0.8"
            />
            <text
              x="150"
              y="205"
              fill="white"
              textAnchor="middle"
              fontSize="11"
            >
              ROLL {valid ? number(roll) : "—"}° · PITCH{" "}
              {valid ? number(pitch) : "—"}°
            </text>
          </g>
        </svg>
        <dl className="instrument-values">
          <div>
            <dt>HEADING</dt>
            <dd>
              {number(hudFresh ? v.heading : null, 0)}
              <small>°</small>
            </dd>
          </div>
          <div>
            <dt>ALT / HOME</dt>
            <dd>
              {number(positionFresh ? v.position?.relative : null)}
              <small>m</small>
            </dd>
          </div>
          <div>
            <dt>ALT / AMSL</dt>
            <dd>
              {number(positionFresh ? v.position?.amsl : null)}
              <small>m</small>
            </dd>
          </div>
          <div>
            <dt>GROUND / AIR</dt>
            <dd>
              {number(hudFresh ? v.speed : null)} /{" "}
              {number(hudFresh ? v.airspeed : null)}
              <small>m/s</small>
            </dd>
          </div>
          <div>
            <dt>CLIMB</dt>
            <dd>
              {number(hudFresh ? v.climb : null)}
              <small>m/s</small>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
