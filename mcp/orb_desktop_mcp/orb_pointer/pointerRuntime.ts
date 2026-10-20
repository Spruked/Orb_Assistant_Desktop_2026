import type {
  CandidateCorrection,
  DesktopTargetReference,
  PlotRecord,
  PointerBoundingBox,
  PointerFrame,
  PointerFrameType,
  PointerIntent,
  PointerPlot,
  PointerPoint,
  PointerSource,
  PointerTarget,
} from "./pointerPlotTypes";
import type { OrbState } from "./orbState";
import {
  CONFIDENCE_FLOOR,
  resolveTarget,
  type DesktopResolutionHooks,
} from "./pointerResolution";

const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

const cleanSource = (source: string | undefined): PointerSource => {
  if (
    source === "cursor" ||
    source === "scan" ||
    source === "voice" ||
    source === "system" ||
    source === "tamp" ||
    source === "orbweaver"
  ) return source;
  return "system";
};

const cleanIntent = (intent: string | undefined): PointerIntent => {
  if (
    intent === "observe" ||
    intent === "hover_context" ||
    intent === "point_at" ||
    intent === "explain" ||
    intent === "select" ||
    intent === "open" ||
    intent === "dismiss" ||
    intent === "operator_override"
  ) {
    return intent;
  }
  return "observe";
};

const cleanFrameType = (frameType: string | undefined): PointerFrameType => {
  if (
    frameType === "virtual_desktop" ||
    frameType === "monitor" ||
    frameType === "window" ||
    frameType === "capture"
  ) return frameType;
  return "virtual_desktop";
};

export function normalizePointerPoint(input: Partial<PointerPoint>): PointerPoint {
  return {
    x: Number.isFinite(input.x) ? Number(input.x) : 0,
    y: Number.isFinite(input.y) ? Number(input.y) : 0,
    monitorId: input.monitorId,
    timestamp: input.timestamp || new Date().toISOString(),
  };
}

export function normalizePointerTarget(input?: Partial<PointerTarget>): PointerTarget | undefined {
  if (!input) return undefined;
  const allowedKinds = ["visible_text", "ui_element", "window", "icon", "region", "cursor_relative", "unknown"];
  const kind = allowedKinds.includes(String(input.kind)) ? input.kind : "unknown";
  return {
    kind,
    label: input.label,
    description: input.description,
    selector: input.selector,
  };
}

export function normalizePointerFrame(input?: Partial<PointerFrame>): PointerFrame {
  return {
    type: cleanFrameType(input?.type),
    monitorId: input?.monitorId,
    captureId: input?.captureId,
    windowId: input?.windowId,
  };
}

export function normalizePointerBoundingBox(input?: Partial<PointerBoundingBox>): PointerBoundingBox | undefined {
  if (!input) return undefined;
  return {
    x: Number.isFinite(input.x) ? Number(input.x) : 0,
    y: Number.isFinite(input.y) ? Number(input.y) : 0,
    width: Math.max(0, Number.isFinite(input.width) ? Number(input.width) : 0),
    height: Math.max(0, Number.isFinite(input.height) ? Number(input.height) : 0),
  };
}

export function normalizePointerPlot(input: Partial<PointerPlot>): PointerPlot {
  const point = normalizePointerPoint(input.point || {});
  return {
    id: input.id || `pointer-${Date.now()}`,
    source: cleanSource(input.source),
    intent: cleanIntent(input.intent),
    target: normalizePointerTarget(input.target),
    frame: normalizePointerFrame(input.frame),
    point,
    bbox: normalizePointerBoundingBox(input.bbox),
    confidence: clamp01(Number(input.confidence ?? 0)),
    label: input.label,
    evidence: Array.isArray(input.evidence) ? input.evidence.map(String) : [],
    metadata: input.metadata || {},
  };
}

export interface DesktopPointerHooks extends DesktopResolutionHooks {
  matchIntent(query: string, plotMap: PlotRecord[]): Promise<PlotRecord | null>;
  speak(line: string): Promise<void>;
  playTravelAnimation(target: DesktopTargetReference): Promise<void>;
  playBloomToPeak(target: DesktopTargetReference): Promise<void>;
  playBloomSettleAndFade(): Promise<void>;
  playPloop(intensity: "full" | "soft"): void;
  saveCandidateCorrection(correction: CandidateCorrection): Promise<void>;
  attemptLocalizedRecovery(record: PlotRecord): Promise<DesktopTargetReference | null>;
  logRecoveryFailure(targetId: string): void;
}

const REPING_COOLDOWN_MS = 8000;
let lastPingAt = 0;

export async function handleDesktopPointerQuery(
  query: string,
  plotMap: PlotRecord[],
  state: OrbState,
  hooks: DesktopPointerHooks,
): Promise<OrbState> {
  state = { ...state, primary: "processing", guidance: "none" };
  const record = await hooks.matchIntent(query, plotMap);

  if (!record || record.confidence < CONFIDENCE_FLOOR) {
    return { ...state, primary: "speaking", guidance: "none" };
  }

  state = { ...state, guidance: "resolving" };
  let result = await resolveTarget(record, hooks);

  if (result.status === "below_confidence") {
    return { ...state, primary: "speaking", guidance: "none" };
  }

  if (result.status === "unresolved") {
    state = { ...state, guidance: "map_recovering" };
    await hooks.speak("One moment - I'm checking that on your desktop.");
    const recovered = await hooks.attemptLocalizedRecovery(record);

    if (!recovered) {
      hooks.logRecoveryFailure(record.target_id);
      return { ...state, primary: "speaking", guidance: "none" };
    }

    await hooks.saveCandidateCorrection(makeCorrection(record, recovered, "localized_recovery"));
    result = {
      status: "resolved",
      target: {
        target: recovered,
        method: "visual_verification",
        onScreen: hooks.isOnScreen(recovered),
      },
    };
  }

  const resolved = result.target!;
  if (result.divergedFromStoredLocator) {
    await hooks.saveCandidateCorrection(
      makeCorrection(record, resolved.target, `fallback_match:${resolved.method}`),
    );
  }

  if (!resolved.onScreen) {
    return { ...state, primary: "speaking", guidance: "none" };
  }

  state = { ...state, primary: "speaking", guidance: "pointer_traveling" };
  await hooks.playTravelAnimation(resolved.target);
  state = { ...state, guidance: "ping_blooming" };
  await hooks.playBloomToPeak(resolved.target);
  hooks.playPloop("full");
  await hooks.playBloomSettleAndFade();

  lastPingAt = Date.now();
  return { ...state, guidance: "re-ping_available" };
}

export const handleVisitorQuery = handleDesktopPointerQuery;

export async function handleRePingRequest(
  record: PlotRecord,
  state: OrbState,
  hooks: DesktopPointerHooks,
): Promise<OrbState> {
  const now = Date.now();
  const withinCooldown = now - lastPingAt < REPING_COOLDOWN_MS;
  const result = await resolveTarget(record, hooks);
  if (result.status !== "resolved" || !result.target?.onScreen) return state;

  state = { ...state, primary: "presence", guidance: "re-ping_available" };
  await hooks.playTravelAnimation(result.target.target);
  await hooks.playBloomToPeak(result.target.target);
  if (!withinCooldown) {
    hooks.playPloop("soft");
    lastPingAt = now;
  }
  await hooks.playBloomSettleAndFade();
  return state;
}

export function requiresExplicitConfirmation(record: PlotRecord, targetIsOnCurrentSurface: boolean): boolean {
  if (!targetIsOnCurrentSurface) return true;
  return record.allowed_actions.includes("point_and_confirm_navigate");
}

function makeCorrection(
  record: PlotRecord,
  target: DesktopTargetReference,
  evidence: string,
): CandidateCorrection {
  const now = new Date().toISOString();
  return {
    target_id: record.target_id,
    new_locator: describeTargetForCorrection(target),
    evidence,
    observed_count: 1,
    first_observed_at: now,
    last_observed_at: now,
  };
}

function describeTargetForCorrection(target: DesktopTargetReference): string {
  if (target.locator) return target.locator;
  if (target.frame?.windowId && target.label) return `window:${target.frame.windowId}/label:${target.label}`;
  if (target.bbox) {
    const { x, y, width, height } = target.bbox;
    return `bbox:${x},${y},${width},${height}`;
  }
  return `desktop-target:${target.id}`;
}
