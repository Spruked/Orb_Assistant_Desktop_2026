# ORB Pointer System + Human Escalation — Partial Build

This is real, structured code — not pseudocode. The **control flow, ordering,
guardrails, and rules from the locked doctrine are fully implemented.**
What's stubbed is only the small set of things that must plug into your
existing systems (Orb Weaver's crawler, your DOM/animation layer, Kokoro TTS,
your storage layer, your agent/support vendor).

Hand this to Codex with the instruction: **"Fill in every `TODO(integration)`
marker. Do not change the control flow, state transitions, or guardrail logic
around them."**

## File map

| File | Package | What it does | What's real vs stub |
|---|---|---|---|
| `python/pointer_plot_schema.py` | Shared | The one data contract (PlotRecord, CandidateCorrection) | Fully real — do not change field names |
| `python/promotion.py` | A | Promotion threshold logic, stale-hit escalation logic | Logic fully real; storage calls stubbed |
| `python/scan_extraction.py` | A | Turns crawled page elements into PlotRecords | Shape/rules real; element-type mapping and classifier hookup stubbed |
| `typescript/pointerPlotTypes.ts` | Shared | TS mirror of the Python schema | Fully real |
| `typescript/orbState.ts` | Shared | The three-track state model | Fully real |
| `typescript/pointerResolution.ts` | B | Four-tier resolution chain, confidence floor | Ordering/floor/control-flow real; 3 of 4 tier implementations stubbed |
| `typescript/pointerRuntime.ts` | B | Full point → resolve → recover → ping → ploop orchestration | Fully real control flow; hooks (TTS, animation, audio, DOM query) stubbed |
| `typescript/orbEscalation.ts` | C | Trigger detection, privacy-tiered handoff, suppression rule | Fully real control flow; intent classifier and vendor calls stubbed |

## Every TODO(integration) point, in one list

1. `scan_extraction.py` — wire `page_elements` to Orb Weaver's actual
   crawler/classifier output instead of the placeholder dict shape.
2. `scan_extraction.py::_summarize_meaning` — optionally call the LLM
   articulation layer for real summaries (currently naive truncation).
3. `promotion.py` — wire `load_candidate_corrections` / `save_plot_record`
   to your actual ORB context store.
4. `promotion.py::evaluate_stale_hits` — wire real failure-event timestamps
   from Package B's `logRecoveryFailure` calls.
5. `pointerResolution.ts::trySemanticLocator` — confirm/adjust the locator
   scheme (data attribute vs accessibility path vs stable selector).
6. `pointerResolution.ts::tryContentFingerprint` — implement real fingerprint
   matching against live page text.
7. `pointerResolution.ts::tryAccessibilityRole` — implement ARIA role +
   accessible-name matching.
8. `pointerResolution.ts::tryVisualVerification` — wire to Tesseract-style
   visual fallback, current viewport/section scope only.
9. `pointerRuntime.ts::Hooks` — wire `matchIntent`, `speak` (Kokoro),
   animation functions, and `playPloop` (respecting existing mute state)
   to your real systems.
10. `pointerRuntime.ts::describeElementForCorrection` — produce a real
    stable locator string instead of an HTML snippet.
11. `orbEscalation.ts::classifyEscalationIntent` — wire to a real,
    extensible intent classifier (explicit request vs frustration-only
    vs neither). Must not be a hardcoded string match.
12. `orbEscalation.ts::executeHandoff` — await actual visitor response
    before attaching sensitive data.
13. `orbEscalation.ts::EscalationHooks.openAgentBubble` /
    `sendHandoffPacket` — wire to whichever agent/support vendor you pick
    (open decision — see doctrine doc Section 9).
14. `orbEscalation.ts::shouldSuppressForEscalatedIssue` — wire
    `isQueryAboutIssue` to your existing intent-matching capability.

## What NOT to let Codex change

- The **order of operations** in `pointerRuntime.ts::handleVisitorQuery`
  (confidence check → resolve → recover → point → ping → ploop). This
  order is doctrine, not style.
- The **promotion threshold gate** in `promotion.py::should_promote` — a
  single session must never be able to overwrite the authoritative map.
- The **explicit-only escalation trigger** in `orbEscalation.ts` —
  frustration language must route through the offer-then-confirm path,
  never straight to `escalation_confirmed`.
- The **suppression scoping** in `shouldSuppressForEscalatedIssue` — it
  must remain scoped to the specific escalated issue, never a global mute.
