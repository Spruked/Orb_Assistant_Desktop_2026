# ORBS Multi-Dock Station Plan

## Purpose

The Platinum ORB Desktop Assistant is the primary local proving-ground ORB. It is the operator's reference implementation for ORBS: Origin of Reasoning Bilateral Substrate.

The Dock Station must manage up to eight docked ORBs on the operator PC while preserving one architecture, one registry contract, and one deterministic mesh protocol.

## Hierarchy

- `desktop` is the primary ORB.
- All other local ORBs are subordinate unless explicitly promoted by registry role.
- Subordinate ORBs may publish state, tasks, results, and heartbeats to the mesh.
- Subordinate ORBs do not override the primary ORB's routing, governance, substrate, or mesh policy.

## Eight-Slot Dock Model

Dock capacity is fixed at eight visible slots:

1. Slot 0: Primary desktop ORB, pinned, not removable.
2. Slots 1-7: Subordinate ORBs discovered from `R:/orb_mesh/manifests/orb_registry.json`.
3. Overflow ORBs remain connected in the registry but collapse into an overflow list.
4. Offline ORBs retain their slots until manually released or replaced.
5. A slot binds to `instance_id`, not process ID, so restarts do not reorder the dock.

## Required Registry Fields

Each ORB entry should include:

- `instance_id`
- `role`
- `orb_type`: `desktop|website|browser|app|swarm`
- `hierarchy`: `primary|subordinate`
- `root`
- `system_root`
- `exports_root`
- `imports_root`
- `checkpoint_root`
- `dock`: `{ "enabled": true, "slot": 0-7|null, "pinned": true|false }`

## Dock Station UI

The ORB tab should contain:

- Primary ORB header with health, listening, Qwen route, ACP, and Kokoro state.
- Eight-slot dock rail showing online/offline/subordinate status.
- Active subordinate detail panel.
- Promote-to-focus control for a subordinate ORB.
- Mesh task controls scoped to the selected subordinate.
- No control may change the primary/subordinate hierarchy without writing a registry event.

## Runtime Rules

- Heartbeat path: `R:/orb_mesh/exports/{instance_id}/state_snapshots/heartbeat.json`
- Dock online threshold: heartbeat modified within five minutes.
- Primary reads all subordinate heartbeats.
- Subordinates pull imports only from their own `imports/{instance_id}` path.
- Shared knowledge promotion goes through `promoted_knowledge` or TPC governance.

## Implementation Sequence

1. Extend `orb_registry.json` with `orb_type`, `hierarchy`, and `dock`.
2. Update `orb:mesh-registry` to sort pinned primary first, then dock slots, then overflow.
3. Replace the single Connected Orbs list with an eight-slot dock rail.
4. Add per-slot controls: focus, dock/undock, voice, route, heartbeat, task queue.
5. Add primary-only policy checks before mesh-wide task dispatch.
6. Add tests for registry parsing, slot ordering, offline status, and overflow.

## Product Boundary

This PC installation is the reference substrate. Deployable ORBS products are fashioned from this architecture but must ship as independent local-first deployments with their own mesh root and registry.
