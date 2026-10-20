import type {
  DesktopTargetReference,
  PlotRecord,
  PointerPlot,
  PointerResolution,
} from "./pointerPlotTypes";

export type ResolutionMethod =
  | "semantic_locator"
  | "content_fingerprint"
  | "accessibility_role"
  | "visual_verification";

export interface ResolvedTarget {
  target: DesktopTargetReference;
  method: ResolutionMethod;
  onScreen: boolean;
}

export interface ResolutionResult {
  status: "resolved" | "unresolved" | "below_confidence";
  target?: ResolvedTarget;
  divergedFromStoredLocator?: boolean;
}

export interface DesktopResolutionHooks {
  trySemanticLocator(record: PlotRecord): Promise<DesktopTargetReference | null>;
  tryContentFingerprint(record: PlotRecord): Promise<DesktopTargetReference | null>;
  tryAccessibilityRole(record: PlotRecord): Promise<DesktopTargetReference | null>;
  tryVisualVerification(record: PlotRecord): Promise<DesktopTargetReference | null>;
  isOnScreen(target: DesktopTargetReference): boolean;
}

export const CONFIDENCE_FLOOR = 0.55;

export async function resolveTarget(
  record: PlotRecord,
  hooks: DesktopResolutionHooks,
): Promise<ResolutionResult> {
  if (record.confidence < CONFIDENCE_FLOOR) return { status: "below_confidence" };

  const bySemanticLocator = await hooks.trySemanticLocator(record);
  if (bySemanticLocator) {
    return {
      status: "resolved",
      target: {
        target: bySemanticLocator,
        method: "semantic_locator",
        onScreen: hooks.isOnScreen(bySemanticLocator),
      },
    };
  }

  const byFingerprint = await hooks.tryContentFingerprint(record);
  if (byFingerprint) {
    return {
      status: "resolved",
      target: {
        target: byFingerprint,
        method: "content_fingerprint",
        onScreen: hooks.isOnScreen(byFingerprint),
      },
      divergedFromStoredLocator: true,
    };
  }

  const byRole = await hooks.tryAccessibilityRole(record);
  if (byRole) {
    return {
      status: "resolved",
      target: {
        target: byRole,
        method: "accessibility_role",
        onScreen: hooks.isOnScreen(byRole),
      },
      divergedFromStoredLocator: true,
    };
  }

  const byVisual = await hooks.tryVisualVerification(record);
  if (byVisual) {
    return {
      status: "resolved",
      target: {
        target: byVisual,
        method: "visual_verification",
        onScreen: hooks.isOnScreen(byVisual),
      },
      divergedFromStoredLocator: true,
    };
  }

  return { status: "unresolved" };
}

export function resolvePointerPlot(plot: PointerPlot, operatorOverride = false): PointerResolution {
  if (plot.intent === "operator_override") {
    return {
      plotId: plot.id,
      action: operatorOverride ? "operator_review" : "none",
      reason: operatorOverride ? "operator override accepted" : "operator override required",
      allowed: operatorOverride,
    };
  }

  if (plot.confidence < 0.35) {
    return {
      plotId: plot.id,
      action: "observe",
      reason: "low confidence pointer plot",
      allowed: true,
    };
  }

  if (plot.intent === "point_at" || plot.intent === "explain" || plot.intent === "hover_context") {
    return {
      plotId: plot.id,
      action: "point",
      reason: "safe visual pointer action",
      allowed: true,
    };
  }

  if (plot.intent === "select" || plot.intent === "open") {
    return {
      plotId: plot.id,
      action: "operator_review",
      reason: "desktop action requires local operator review",
      allowed: false,
    };
  }

  return {
    plotId: plot.id,
    action: "observe",
    reason: "passive desktop pointer observation",
    allowed: true,
  };
}
