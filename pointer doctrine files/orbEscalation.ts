/**
 * Package C — Human Escalation.
 *
 * Explicit-request-only trigger, privacy-tiered handoff, and the
 * post-handoff suppression rule (scoped to the escalated issue only,
 * never a global mute).
 *
 * TODO(integration): replace `classifyEscalationIntent` with a real
 * intent classifier (likely a call into your existing NLU/LLM
 * articulation layer) — this must remain an EXTENSIBLE intent
 * category, not a hardcoded string list, per the doctrine. The
 * function signature/contract below is what matters.
 */

import { cancelInFlightGuidance, type OrbState } from "./orbState";

export type EscalationIntent = "explicit_request" | "frustration_only" | "none";

export interface HandoffPacket {
  issue: string;
  visitor_intent: string;
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
  /** Renders the human-agent chat bubble. Returns an issueId used to
   *  track the case. ORB must never write messages into this bubble. */
  openAgentBubble(packet: HandoffPacket): Promise<string>;
  /** Sends the assembled packet to the agent/support system. */
  sendHandoffPacket(issueId: string, packet: HandoffPacket): Promise<void>;
}

/**
 * Call this on every visitor utterance alongside normal query handling.
 * Explicit request → confirmed immediately, no confirmation prompt.
 * Frustration-only → offered, requires a subsequent explicit yes.
 */
export async function evaluateEscalationTrigger(
  utterance: string,
  state: OrbState,
  hooks: EscalationHooks,
): Promise<OrbState> {
  const intent = await hooks.classifyEscalationIntent(utterance);

  if (intent === "explicit_request") {
    // The explicit request IS the approval — no "are you sure" prompt.
    return { ...cancelInFlightGuidance(state), caseStatus: "escalation_confirmed" };
  }

  if (intent === "frustration_only") {
    await hooks.speak("Would you like me to connect you with a support person?");
    return { ...state, caseStatus: "escalation_offered" };
  }

  return state;
}

/**
 * Call this when caseStatus is "escalation_offered" and the visitor
 * responds affirmatively to the offer.
 */
export function confirmOfferedEscalation(state: OrbState): OrbState {
  if (state.caseStatus !== "escalation_offered") return state;
  return { ...cancelInFlightGuidance(state), caseStatus: "escalation_confirmed" };
}

/**
 * Assembles the basic-tier handoff packet. Sensitive data is NEVER
 * included here — it must be separately, explicitly offered and
 * approved via `attachSensitiveData` before the packet is sent.
 */
export function buildBaseHandoffPacket(params: {
  issue: string;
  visitorIntent: string;
  context: string;
  category: string;
  orbVerification: string;
  attemptsReported: string[];
}): HandoffPacket {
  return {
    issue: params.issue,
    visitor_intent: params.visitorIntent,
    context: params.context,
    category: params.category,
    orb_verification: params.orbVerification,
    attempts_reported: params.attemptsReported,
    sensitive_data: null,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Only call this after the ORB has named the specific sensitive item
 * aloud and received an explicit yes. Never bundle sensitive data
 * into the base packet automatically.
 */
export function attachSensitiveData(
  packet: HandoffPacket,
  approvedFields: Record<string, string>,
): HandoffPacket {
  return { ...packet, sensitive_data: approvedFields };
}

/**
 * Full escalation flow: speak the handoff line(s), open the bubble,
 * send the packet, and transition case status to human_owned.
 *
 * `escalatedIssueId` scopes the subsequent suppression rule — the
 * ORB stays fully available for anything NOT related to this issue.
 */
export async function executeHandoff(
  packet: HandoffPacket,
  state: OrbState,
  hooks: EscalationHooks,
  sensitiveItemOffered?: { label: string; onApprove: () => Record<string, string> },
): Promise<OrbState> {
  if (sensitiveItemOffered) {
    await hooks.speak(
      `I can include ${sensitiveItemOffered.label} for the agent. Would you like me to send that too?`,
    );
    // TODO(integration): await actual visitor response here before
    // calling sensitiveItemOffered.onApprove() and attachSensitiveData().
  }

  await hooks.speak(
    "I'm connecting you with support now. I'll include what you already told me so you don't have to start over.",
  );

  const issueId = await hooks.openAgentBubble(packet);
  await hooks.sendHandoffPacket(issueId, packet);

  return { ...state, caseStatus: "human_owned", escalatedIssueId: issueId };
}

/**
 * Suppression check — call before the ORB attempts to answer or
 * re-diagnose ANY query while a case is human_owned. Only suppresses
 * engagement on the specific escalated issue; everything else passes
 * through untouched (return false = ORB may proceed normally).
 *
 * TODO(integration): `isQueryAboutIssue` should use whatever
 * intent-matching capability you already have to compare the new
 * query against the escalated issue's topic/category.
 */
export function shouldSuppressForEscalatedIssue(
  state: OrbState,
  newQueryTopic: string,
  isQueryAboutIssue: (topic: string, issueId: string) => boolean,
): boolean {
  if (state.caseStatus !== "human_owned" || !state.escalatedIssueId) return false;
  return isQueryAboutIssue(newQueryTopic, state.escalatedIssueId);
}

/**
 * Call this from the webhook/callback your agent system fires when
 * the case is closed or returned (vendor-dependent — see the open
 * decision in the doctrine doc).
 */
export function handleCaseReturned(state: OrbState): OrbState {
  return { ...state, caseStatus: "case_returned" };
}
