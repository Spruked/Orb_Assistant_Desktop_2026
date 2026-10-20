export type PrimaryState = "presence" | "listening" | "processing" | "speaking" | "cooldown";

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

export function cancelInFlightGuidance(state: OrbState): OrbState {
  return { ...state, guidance: "none" };
}
