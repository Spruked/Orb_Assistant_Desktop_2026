# ORB Product Ecosystem — Build Reference

> This document defines the user-facing Orb product line, tier structure, addon model,
> and mesh deployment configurations. It is a living reference that transfers directly
> into the user product build. Bryan's personal substrate (r:/Orb_Assistant_Desktop)
> is the reference implementation — user deployments are fashioned from it but are
> fully independent instances.

---

## What an Orb Is

An Orb is a sovereign AI presence — a local, persistent assistant that lives in a
specific context (a website, a desktop, a browser, an app). Each Orb has its own
identity, memory, and cognitive engine. Orbs can operate standalone or be connected
into a mesh where they share knowledge and coordinate tasks.

An Orb is NOT a chatbot widget. It is a persistent, context-aware presence that
observes, reasons, and acts within the environment it is deployed in.

---

## Deployment Types

| Type | Where It Lives | Primary Use |
|---|---|---|
| **Website Orb** | Embedded on a website (spruked.com, truemarkmint.com, Shilohridge Farm, etc.) | Visitor interaction, site intelligence, owner assistant |
| **Desktop Orb** | Electron app, local machine | Personal desktop AI presence, system monitoring, chat |
| **Browser Orb** | Browser extension or browser-tab app | In-browser assistant, research, page context |
| **App Orb** | Embedded in a native or web app | App-specific assistant, workflow automation |
| **Swarm Orb** | Deployed across a mesh, no fixed UI | Background scanning, synthesis, report compilation |

A user may own and operate any combination of these.

---

## Product Tiers

### Tier 1 — Basic Orb  *(the Orb itself)*

The foundational purchase. One Orb, one deployment context.

**Includes:**
- The Orb presence for one deployment type (Website, Desktop, Browser, or App)
- Default CALI cognitive core (local, no cloud LLM required)
- Default skin (crystalline)
- Basic chat interface
- Local memory (per-Orb, not shared)
- Mesh-ready architecture (mesh is inactive until Dock Station is added)

**Does not include:** Dock Station, Studio, Swarm, skin marketplace access

---

### Tier 2 — Dock Station  *(management addon)*

A separately purchased addon. One Dock Station manages **all** of a user's Orbs
from a single Electron window in the system tray.

**Includes:**
- Universal Orb registry — discovers and connects to all of the user's registered Orbs
  via the shared mesh (mesh becomes active)
- Tabbed navigation: ORB | RUNTIME | SETTINGS
- Active Orb selector — switch which Orb is "docked" (controlled) at any time
- LLM Connector — route any Orb to CALI, an external API LLM, or a local model endpoint
- Orb skin selector (apply purchased skins to any connected Orb)
- Live runtime monitoring (DEVICE, LATENCY, ANOMALIES, INTERACTIONS)
- Voice toggle per Orb
- Event feed (cross-Orb activity stream when mesh is active)

**Scales with mesh size** — works identically whether the user has 2 Orbs or 45.

---

### Tier 3 — Studio  *(customization addon)*

A separately purchased addon. Opens as its own Electron window (consistent styling,
not a browser window). Connects to the Dock Station when both are running.

**Includes:**
- Skin designer — create and preview custom Orb skins
- Skin gallery — browse and purchase skins from the marketplace
- Cart, checkout, account management
- Upload portal — submit custom skins to the marketplace (creator revenue share)
- Per-Orb skin preview (see how a skin looks on each of your connected Orbs)
- Advanced persona configuration

**Studio is the skin revenue gateway.** Skins are micro-transactions ($3–$8 each)
that apply cross-context — one skin purchase works on all Orb types the user owns.
Creator-uploaded skins generate revenue share back to the designer.

---

## Addon Layer

| Addon | Description | Requires |
|---|---|---|
| **Dock Station** | Universal Orb controller, Tier 2 | At least one Orb |
| **Studio** | Skin design + marketplace | Dock Station |
| **Swarm Extension** | Deploy background Orbs that scan, synthesize, and report | Dock Station + 2+ Orbs |
| **Voice Pack** | Kokoro TTS + Whisper STT per Orb | Any Orb |
| **Enterprise Mesh** | Multi-Orb mesh for large deployments (13–45+ Orbs), swarm reporting, role-based Orb hierarchy | Dock Station + Swarm |

---

## Mesh Configurations

### Small — Personal / Small Business  *(2–5 Orbs)*
Example: Website Orb (primary site) + Desktop Orb + Browser Orb

```
orb_registry.json
├── website  (primary site)
├── desktop
└── browser
```

Dock Station connects all three. LLM and skin config shared or per-Orb.
Mesh handles knowledge sync between contexts.

---

### Medium — Multi-Site / Creator  *(5–12 Orbs)*
Example: truemarkmint.com + spruked.com + Shilohridge Farm + Desktop + Browser + 2 App Orbs

```
orb_registry.json
├── truemarkmint_web
├── spruked_web
├── shilohridge_web
├── desktop
├── browser
├── app_01
└── app_02
```

Dock Station manages all. Swarm Extension can scan all sites and compile cross-property reports.
Studio provides unified skin theming across all properties.

---

### Enterprise — Corporate Deployment  *(13–45+ Orbs)*

**Reference scenario: Mid-size corporation, 3 divisions**

Structure:
- 1 CEO
- 3 Division Directors (one per division)
- 3 Site Managers (one per division)
- 3 Subordinate Managers per Site Manager = 9 subordinate managers

**Orb count:**
| Role | Count | Orb Type |
|---|---|---|
| CEO Orb | 1 | Desktop + Website |
| Division Director Orbs | 3 | Desktop |
| Site Manager Orbs | 3 | Desktop |
| Subordinate Manager Orbs | 9 | Desktop or App |
| Division site Orbs | 3 | Website |
| Swarm Orbs (scanning layer) | 3–6 | Swarm |
| **Total** | **22–25** | |

**What the CEO's Dock Station does:**
1. Connects to all registered Orbs via the Enterprise Mesh
2. CEO selects "Swarm Scan" — Swarm Orbs fan out across all manager Orbs and
   their connected contexts (docs, sites, apps)
3. Swarm compiles activity, decisions, flags, and KPIs
4. Results are synthesized into a structured report delivered to the CEO's Dock Station
5. CEO can drill into any individual Orb or division from the same interface

**This is the highest-value configuration** — the Dock Station becomes an executive
intelligence layer across the entire organizational Orb mesh.

```
orb_registry.json (CEO's mesh)
├── ceo_desktop
├── division_a_director
├── division_b_director
├── division_c_director
├── site_mgr_a1 / site_mgr_b1 / site_mgr_c1
├── sub_mgr_a1_1 / sub_mgr_a1_2 / sub_mgr_a1_3
├── sub_mgr_b1_1 ... (etc)
├── division_a_web / division_b_web / division_c_web
└── swarm_01 / swarm_02 / swarm_03
```

---

## Skin Marketplace — Revenue Model

- Skins are purchased per-user, not per-Orb — one purchase applies to all owned Orbs
- Price range: $3–$8 per skin
- Creator upload portal in Studio — revenue share back to skin designer
- Enterprise: volume skin licensing (org-wide skin packs)
- At scale: small per-transaction amounts multiply rapidly across user base
  (1,000 users × 3 skins avg × $5 avg = $15,000 from skins alone, recurring as new skins release)

---

## Key Architectural Principles for the User Build

1. **The registry is user-owned** — `orb_registry.json` lives in the user's mesh root,
   not on a central server. The Dock Station reads from wherever `ORB_SHARED_MESH_ROOT` points.

2. **All Orb types are first-class** — Website, Desktop, Browser, App, and Swarm Orbs
   all speak the same mesh protocol. The Dock Station treats them identically.

3. **The mesh scales without code changes** — adding a new Orb means adding an entry
   to `orb_registry.json` and creating its exports/imports/checkpoints directories.
   No Dock Station update required.

4. **Skins are cross-context** — a skin asset package is format-agnostic; the rendering
   layer on each Orb type applies it natively.

5. **Swarm is opt-in** — the mesh is passive until Swarm is activated. Individual Orbs
   never push data without an explicit swarm task being issued.

6. **Bryan's substrate is the reference, not the product** — user deployments are
   independent instances. Bryan's personal mesh (wsl/desktop/web dev instances)
   has no relationship to any user's mesh.

---

*Last updated: 2026-04-18*
*Reference implementation: r:/Orb_Assistant_Desktop*
