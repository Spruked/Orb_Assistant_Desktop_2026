/**
 * Shared state model — Section 2 of the doctrine.
 *
 * Three independent tracks. Primary + Guidance are the pointer system's
 * tracks (unaffected by escalation except one suppression rule). Case
 * status is escalation-owned. Nothing outside orbEscalation.ts should
 * write to CaseStatus, and nothing outside orbPointerRuntime.ts should
 * write to GuidanceOverlay.
 */

export type PrimaryState =
  | "presence"
  | "listening"
  | "processing"
  | "speaking"
  | "cooldown";

export type GuidanceOverlay =
  | "none"
  | "resolving"
  | "map_recovering"
  | "pointer_traveling"
  | "ping_blooming"
  | "re-ping_available"
  | "awaiting_permission";

export type CaseStatus =
  | "none"
  | "escalation_offered"
  | "escalation_confirmed"
  | "human_owned"
  | "case_returned";

export interface OrbState {
  primary: PrimaryState;
  guidance: GuidanceOverlay;
  caseStatus: CaseStatus;
  /** Non-null only while caseStatus is human_owned or case_returned. */
  escalatedIssueId: string | null;
}

export function createInitialOrbState(): OrbState {
  return {
    primary: "presence",
    guidance: "none",
    caseStatus: "none",
    escalatedIssueId: null,
  };
}

/**
 * The ONE cross-system rule (Section 6/7): if an escalation is
 * confirmed while guidance is mid-flight, guidance must be cleanly
 * cancelled, never left hanging. Call this from the escalation
 * trigger handler before starting the handoff flow.
 */
export function cancelInFlightGuidance(state: OrbState): OrbState {
  return { ...state, guidance: "none" };
}
