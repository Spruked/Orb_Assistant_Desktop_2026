export type PointerSource = "cursor" | "scan" | "voice" | "system" | "tamp" | "orbweaver";

export type PointerIntent =
  | "observe"
  | "hover_context"
  | "point_at"
  | "explain"
  | "select"
  | "open"
  | "dismiss"
  | "operator_override";

export type PointerFrameType = "virtual_desktop" | "monitor" | "window" | "capture";

export interface PointerTarget {
  kind: "visible_text" | "ui_element" | "window" | "icon" | "region" | "cursor_relative" | "unknown";
  label?: string;
  description?: string;
  selector?: string;
}

export interface PointerFrame {
  type: PointerFrameType;
  monitorId?: string;
  captureId?: string;
  windowId?: string;
}

export interface PointerPoint {
  x: number;
  y: number;
  monitorId?: string;
  timestamp: string;
}

export interface PointerBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PointerPlot {
  id: string;
  source: PointerSource;
  intent: PointerIntent;
  target?: PointerTarget;
  frame?: PointerFrame;
  point: PointerPoint;
  bbox?: PointerBoundingBox;
  confidence: number;
  label?: string;
  evidence?: string[];
  metadata?: Record<string, unknown>;
}

export interface PointerResolution {
  plotId: string;
  action: "none" | "observe" | "point" | "focus" | "click" | "operator_review";
  reason: string;
  allowed: boolean;
}

export type TargetType =
  | "nav"
  | "heading"
  | "section"
  | "paragraph"
  | "form_field"
  | "button"
  | "faq_answer"
  | "price_card"
  | "policy_line"
  | "download"
  | "other";

export type AllowedAction = "point" | "point_and_navigate" | "point_and_confirm_navigate";
export type PlotStatus = "active" | "stale" | "unresolved" | "needs_review";
export type PlotSource = "scan" | "live_recovery_promoted";

export interface PlotRecord {
  target_id: string;
  page_route: string;
  target_type: TargetType;
  meaning: string;
  intent_aliases: string[];
  content_fingerprint: string;
  semantic_locator: string;
  confidence: number;
  allowed_actions: AllowedAction[];
  status: PlotStatus;
  last_verified_at: string;
  source: PlotSource;
}

export interface CandidateCorrection {
  target_id: string;
  new_locator: string;
  evidence: string;
  observed_count: number;
  first_observed_at: string;
  last_observed_at: string;
}

export interface DesktopTargetReference {
  id: string;
  label?: string;
  locator?: string;
  point?: PointerPoint;
  bbox?: PointerBoundingBox;
  frame?: PointerFrame;
  nativeRef?: unknown;
}
