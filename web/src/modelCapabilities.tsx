import { useEffect, useState } from "react";
import { api } from "./api";

export function useModelCapabilities(options: any, preview = false) {
  const model = options?.model;
  const endpoint = options?.base_url || options?.provider;
  const key = JSON.stringify([model, endpoint]);
  const [state, setState] = useState<any>(null);
  useEffect(() => {
    if (!model || !endpoint) return;
    let current = true;
    const timer = setTimeout(
      async () => {
        try {
          const result = await api(
            "/settings/capabilities",
            preview ? "POST" : "GET",
            preview ? options : undefined,
          );
          if (current) setState({ key, result });
        } catch {
          if (current) setState({ key, result: { vision: null, tools: null } });
        }
      },
      preview ? 400 : 0,
    );
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [key, preview]);
  return state?.key === key ? state.result : null;
}

export function capabilityLabel(capabilities: any) {
  if (!capabilities) return "Checking model capabilities…";
  if (capabilities.vision === null)
    return "Endpoint does not report image/tool support. Check your model's documentation before attaching a map.";
  return `${capabilities.vision ? "Text + images" : "Text only · Map images unavailable"} · ${capabilities.tools ? "Tool calls supported" : "Tool calls unavailable"}`;
}
