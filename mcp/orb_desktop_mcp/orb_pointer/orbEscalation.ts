import type { PointerPlot } from "./pointerPlotTypes";
import { cancelInFlightGuidance, type OrbState } from "./orbState";

export interface EscalationDecision {
  allowed: boolean;
  reason: string;
  operatorId?: string;
}

export function operatorEscalation(plot: PointerPlot, operatorId?: string, overrideId?: string): EscalationDecision {
  if (!overrideId || operatorId !== overrideId) {
    return { allowed: false, reason: "operator override identity mismatch", operatorId };
  }

  if (plot.intent !== "operator_override") {
    return { allowed: false, reason: "plot is not an override request", operatorId };
  }

  return { allowed: true, reason: "operator override accepted", operatorId };
}

export type EscalationIntent = "explicit_request" | "frustration_only" | "none";

export interface HandoffPacket {
  issue: string;
  operator_intent: string;
  context: string;
  category: string;
  orb_verification: string;
  attempts_reported: string[];
  sensitive_data: Record<string, string> | null;
  timestamp: string;
}

export interface EscalationHooks {
  classifyEscalationIntent(utterance: string): Promise<EscalationIntent>;
  speak(line: string): Promise<void>;
  openHandoffSurface(packet: HandoffPacket): Promise<string>;
  sendHandoffPacket(issueId: string, packet: HandoffPacket): Promise<void>;
  requestSensitiveDataApproval?(label: string): Promise<boolean>;
}

export async function evaluateEscalationTrigger(
  utterance: string,
  state: OrbState,
  hooks: EscalationHooks,
): Promise<OrbState> {
  const intent = await hooks.classifyEscalationIntent(utterance);
  if (intent === "explicit_request") {
    return { ...cancelInFlightGuidance(state), caseStatus: "escalation_confirmed" };
  }
  if (intent === "frustration_only") {
    await hooks.speak("Would you like me to open a human support handoff?");
    return { ...state, caseStatus: "escalation_offered" };
  }
  return state;
}

export function confirmOfferedEscalation(state: OrbState): OrbState {
  if (state.caseStatus !== "escalation_offered") return state;
  return { ...cancelInFlightGuidance(state), caseStatus: "escalation_confirmed" };
}

export function buildBaseHandoffPacket(params: {
  issue: string;
  operatorIntent: string;
  context: string;
  category: string;
  orbVerification: string;
  attemptsReported: string[];
}): HandoffPacket {
  return {
    issue: params.issue,
    operator_intent: params.operatorIntent,
    context: params.context,
    category: params.category,
    orb_verification: params.orbVerification,
    attempts_reported: params.attemptsReported,
    sensitive_data: null,
    timestamp: new Date().toISOString(),
  };
}

export function attachSensitiveData(
  packet: HandoffPacket,
  approvedFields: Record<string, string>,
): HandoffPacket {
  return { ...packet, sensitive_data: approvedFields };
}

export async function executeHandoff(
  packet: HandoffPacket,
  state: OrbState,
  hooks: EscalationHooks,
  sensitiveItemOffered?: { label: string; onApprove: () => Record<string, string> },
): Promise<OrbState> {
  let approvedPacket = packet;
  if (sensitiveItemOffered && hooks.requestSensitiveDataApproval) {
    const approved = await hooks.requestSensitiveDataApproval(sensitiveItemOffered.label);
    if (approved) approvedPacket = attachSensitiveData(packet, sensitiveItemOffered.onApprove());
  }

  await hooks.speak("I'm opening a human support handoff and including the context you approved.");
  const issueId = await hooks.openHandoffSurface(approvedPacket);
  await hooks.sendHandoffPacket(issueId, approvedPacket);
  return { ...state, caseStatus: "human_owned", escalatedIssueId: issueId };
}

export function shouldSuppressForEscalatedIssue(
  state: OrbState,
  newQueryTopic: string,
  isQueryAboutIssue: (topic: string, issueId: string) => boolean,
): boolean {
  if (state.caseStatus !== "human_owned" || !state.escalatedIssueId) return false;
  return isQueryAboutIssue(newQueryTopic, state.escalatedIssueId);
}

export function handleCaseReturned(state: OrbState): OrbState {
  return { ...state, caseStatus: "case_returned" };
}
