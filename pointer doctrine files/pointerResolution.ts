/**
 * Package B — target resolution chain.
 *
 * Implements Section 4, steps 2–4 of the doctrine: confidence floor,
 * the four-tier resolution chain, and the map_recovering fallback.
 *
 * TODO(integration): replace the four `try*` function bodies with
 * your actual DOM/accessibility querying. Signatures and control
 * flow are the part that matters — they encode the doctrine's
 * ordering and stop-at-first-success rule.
 */

import type { PlotRecord } from "./pointerPlotTypes";

export interface ResolvedTarget {
  element: Element;
  method: "semantic_locator" | "content_fingerprint" | "accessibility_role" | "visual_verification";
  onScreen: boolean;
}

export interface ResolutionResult {
  status: "resolved" | "unresolved" | "below_confidence";
  target?: ResolvedTarget;
  /** Only set when status === "resolved" via a fallback tier that
   *  didn't match the record's stored semantic_locator — signals the
   *  caller should emit a CandidateCorrection. */
  divergedFromStoredLocator?: boolean;
}

// Minimum scan-time confidence required before attempting resolution
// at all. Below this, the ORB answers verbally and never tries to point.
export const CONFIDENCE_FLOOR = 0.55;

export async function resolveTarget(record: PlotRecord): Promise<ResolutionResult> {
  if (record.confidence < CONFIDENCE_FLOOR) {
    return { status: "below_confidence" };
  }

  // Tier 1: semantic_locator (the stored, presumed-current locator)
  const bySemanticLocator = trySemanticLocator(record.semantic_locator);
  if (bySemanticLocator) {
    return {
      status: "resolved",
      target: { element: bySemanticLocator, method: "semantic_locator", onScreen: isOnScreen(bySemanticLocator) },
    };
  }

  // Tier 2: content fingerprint match within the current page
  const byFingerprint = tryContentFingerprint(record.content_fingerprint);
  if (byFingerprint) {
    return {
      status: "resolved",
      target: { element: byFingerprint, method: "content_fingerprint", onScreen: isOnScreen(byFingerprint) },
      divergedFromStoredLocator: true,
    };
  }

  // Tier 3: accessibility/role-based locator, using target_type + meaning as hints
  const byRole = tryAccessibilityRole(record);
  if (byRole) {
    return {
      status: "resolved",
      target: { element: byRole, method: "accessibility_role", onScreen: isOnScreen(byRole) },
      divergedFromStoredLocator: true,
    };
  }

  // Tier 4: localized visual verification (Tesseract-style), current page/section ONLY
  const byVisual = await tryVisualVerification(record);
  if (byVisual) {
    return {
      status: "resolved",
      target: { element: byVisual, method: "visual_verification", onScreen: isOnScreen(byVisual) },
      divergedFromStoredLocator: true,
    };
  }

  return { status: "unresolved" };
}

function trySemanticLocator(locator: string): Element | null {
  // TODO(integration): replace with your actual locator query strategy
  // (e.g. data-orb-target attribute, accessibility tree path, stable
  // selector scheme). Must NOT be raw pixel coordinates.
  try {
    return document.querySelector(locator);
  } catch {
    return null;
  }
}

function tryContentFingerprint(fingerprint: string): Element | null {
  // TODO(integration): implement real fingerprint matching against
  // current page content (e.g. hash visible text nodes, compare).
  // Placeholder returns null — must be implemented before this tier
  // does anything.
  return null;
}

function tryAccessibilityRole(record: PlotRecord): Element | null {
  // TODO(integration): query by ARIA role + accessible name similarity
  // to record.meaning / record.target_type. Placeholder only.
  return null;
}

async function tryVisualVerification(record: PlotRecord): Promise<Element | null> {
  // TODO(integration): wire to Tesseract-style visual fallback for
  // canvas content, rendered PDFs, or legacy elements with no DOM
  // hooks. Scope: current viewport/section only — never a full-page
  // or full-site scan from this path. Placeholder only.
  return null;
}

function isOnScreen(element: Element): boolean {
  const rect = element.getBoundingClientRect();
  return rect.top >= 0 && rect.bottom <= (window.innerHeight || document.documentElement.clientHeight);
}
