// Optional browser-agent access is limited to observations and local mission drafts.
// It intentionally exposes no arming, upload, parameter-write or lab tools.
export function registerGroundStationTools(actions: {
  readState: () => Promise<unknown>;
  readWorkspace: () => Promise<unknown>;
  stageDraft: (revision: number, draft: unknown) => Promise<unknown>;
}) {
  const context = (document as any).modelContext;
  if (!context?.registerTool) return () => {};
  const lifecycle = new AbortController();
  const tools = [
    {
      name: "read_ground_station_state",
      title: "Read ground station telemetry",
      description:
        "Read current vehicle snapshots, freshness, advisory findings and selected-session context. No vehicle control.",
      inputSchema: {
        type: "object",
        properties: {},
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true, untrustedContentHint: true },
      execute: actions.readState,
    },
    {
      name: "read_selected_mission_workspace",
      title: "Read selected mission draft",
      description:
        "Read the selected vehicle's versioned local draft, approved intent, checks and uploaded-plan snapshot.",
      inputSchema: {
        type: "object",
        properties: {},
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true, untrustedContentHint: true },
      execute: actions.readWorkspace,
    },
    {
      name: "stage_selected_mission_draft",
      title: "Stage a local mission revision",
      description:
        "Replace the selected local draft at an expected revision and show it in the mission editor. This does not upload or control a vehicle. Requires an operator request to edit the draft.",
      inputSchema: {
        type: "object",
        properties: {
          expected_revision: { type: "integer", minimum: 0 },
          draft: { type: "object" },
        },
        required: ["expected_revision", "draft"],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: true },
      execute: async (input: unknown) => {
        const data = input as any;
        if (
          !data ||
          !Number.isInteger(data.expected_revision) ||
          data.expected_revision < 0 ||
          !data.draft ||
          typeof data.draft !== "object" ||
          Array.isArray(data.draft)
        )
          throw new Error(
            "A revision and structured mission draft are required",
          );
        return actions.stageDraft(data.expected_revision, data.draft);
      },
    },
  ];
  for (const tool of tools) {
    try {
      Promise.resolve(
        context.registerTool(tool, { signal: lifecycle.signal }),
      ).catch(() => {});
    } catch {
      /* Optional browser capability; the normal app remains usable. */
    }
  }
  return () => lifecycle.abort();
}
