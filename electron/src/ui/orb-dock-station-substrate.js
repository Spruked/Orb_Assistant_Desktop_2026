(function () {
  const root = document.getElementById("substrate-dock-extension");
  if (!root) return;
  const params = new URLSearchParams(window.location.search);
  if (params.get("view") === "studio") {
    root.style.display = "none";
    return;
  }

  const TAB_KEY = "orb.dock.substrate.activeTab.v1";
  const VALID_TABS = new Set(["orbDock", "overview", "apps", "acp", "memory", "skills", "services"]);
  const domains = [
    "spruked.com",
    "truemarkmint.com",
    "shilohridgekatahdins.com",
    "shilohridgekatahdins.com/butch",
    "dragonithome.spruked.com"
  ];

  const state = {
    activeTab: VALID_TABS.has(params.get("substrateTab"))
      ? params.get("substrateTab")
      : VALID_TABS.has(localStorage.getItem(TAB_KEY))
        ? localStorage.getItem(TAB_KEY)
        : "overview",
    status: null,
    appStatus: {},
    lastResearch: null,
    lastSkill: null,
    lastService: null,
    lastApp: null,
    lastBridgeType: "none",
    updatedAt: null,
    bootstrapAttempted: false,
    bootstrapInFlight: false,
  };

  const appItems = [
    {
      id: "mail",
      label: "Mail",
      role: "Desktop mail shell",
      port: "19000",
      url: "http://127.0.0.1:19000",
      healthUrl: "http://127.0.0.1:19000/api/health",
    },
    {
      id: "spruk_email",
      label: "Spruk_Email",
      role: "Spruk email app",
      port: "19000",
      url: "http://127.0.0.1:19000",
      healthUrl: "http://127.0.0.1:19000/api/health",
    },
    {
      id: "crm",
      label: "CRM",
      role: "Spruked CRM frontend",
      port: "21001",
      url: "http://127.0.0.1:21001",
      healthUrl: "http://127.0.0.1:21000/health",
    },
    {
      id: "spruked_site",
      label: "spruked.com",
      role: "Public umbrella ORB website",
      port: "3001",
      url: "http://localhost:3001",
      healthUrl: "http://localhost:3001",
      healthCandidates: ["http://localhost:3001", "http://127.0.0.1:3001"],
    },
    {
      id: "truemark_site",
      label: "truemarkmint.com",
      role: "Product/business ORB website",
      port: "3300",
      url: "http://127.0.0.1:3300",
      healthUrl: "http://127.0.0.1:3300",
      healthCandidates: ["http://127.0.0.1:3300"],
    },
    {
      id: "shiloh_site",
      label: "shilohridgekatahdins.com",
      role: "Ranch ORB website/API alias",
      port: "8001",
      url: "http://127.0.0.1:8001",
      healthUrl: "http://127.0.0.1:8001/api/health",
      healthCandidates: ["http://127.0.0.1:8001/api/health", "http://127.0.0.1:8001/openapi.json", "http://127.0.0.1:8001"],
    },
    {
      id: "butch_site",
      label: "Butch / Ranch-hand ORB",
      role: "Specialized ranch-hand ORB alias",
      port: "8002",
      url: "http://127.0.0.1:8002",
      healthUrl: "http://127.0.0.1:8002/api/health",
      healthCandidates: ["http://127.0.0.1:8002/api/health", "http://127.0.0.1:8002/openapi.json", "http://127.0.0.1:8002"],
    },
  ];

  const prioritySiteBadgeMap = [
    { siteId: "spruked.com", appId: "spruked_site" },
    { siteId: "truemarkmint.com", appId: "truemark_site" },
    { siteId: "shilohridgekatahdins.com", appId: "shiloh_site" },
    { siteId: "shilohridgekatahdins.com/butch", appId: "butch_site" },
  ];

  const tabs = [
    { id: "orbDock", label: "Orb Dock" },
    { id: "overview", label: "Overview" },
    { id: "apps", label: "Apps" },
    { id: "acp", label: "ACP I/O" },
    { id: "memory", label: "Memory" },
    { id: "skills", label: "Skills" },
    { id: "services", label: "Services" },
  ];

  function esc(value) {
    return String(value ?? "n/a")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function boolLabel(value, unknownLabel = "CHECKING") {
    if (value === true) return "ONLINE";
    if (value === false) return "OFF";
    return unknownLabel;
  }

  function runtimeLabel(statusValue, readyValue) {
    const normalized = String(statusValue || "").toLowerCase();
    if (readyValue === true) return "ONLINE";
    if (normalized === "loading" || normalized === "pending") return "CHECKING";
    if (normalized === "online") return "ONLINE";
    if (normalized === "error") return "ERROR";
    if (normalized === "unavailable") return "OFF";
    return boolLabel(readyValue);
  }

  function runtimeOk(statusValue, readyValue) {
    const normalized = String(statusValue || "").toLowerCase();
    if (readyValue === true || normalized === "online") return true;
    if (normalized === "loading" || normalized === "pending") return null;
    if (normalized === "error" || normalized === "unavailable" || readyValue === false) return false;
    return null;
  }

  function pill(label, value, ok) {
    const color = ok === false ? "#ffcc66" : ok === true ? "#5af2a5" : "#d9f7ff";
    return `
      <div class="substrate-pill">
        <span>${esc(label)}</span>
        <b style="color:${color}">${esc(value)}</b>
      </div>
    `;
  }

  function pathLine(label, value) {
    return `
      <div class="substrate-path">
        <span>${esc(label)}</span>
        <code>${esc(value || "n/a")}</code>
      </div>
    `;
  }

  function panel(title, body, badge) {
    return `
      <section class="substrate-panel">
        <div class="substrate-panel-head">
          <h2>${esc(title)}</h2>
          ${badge ? `<span>${esc(badge)}</span>` : ""}
        </div>
        ${body}
      </section>
    `;
  }

  function serviceStateLabel(service) {
    const status = service?.service_status || {};
    if (service?.enabled === false) return { label: "DISABLED", ok: false };
    if (!status.configured) return { label: "NOT CONFIGURED", ok: false };
    if (status.reachable === true) return { label: status.status_code ? `HTTP ${status.status_code}` : "REACHABLE", ok: true };
    if (status.reachable === false) return { label: "UNREACHABLE", ok: false };
    if (Array.isArray(status.port_checks) && status.port_checks.length > 0) {
      const hasListening = status.port_checks.some((entry) => entry.listening);
      return { label: hasListening ? "PORT LISTENING" : "PORT OFF", ok: hasListening };
    }
    return { label: "CHECKING", ok: null };
  }

  function pathStateLine(label, value, exists) {
    const ok = exists === true ? "ONLINE" : exists === false ? "MISSING" : "CHECK";
    const color = exists === true ? "#5af2a5" : exists === false ? "#ffcc66" : "#d9f7ff";
    return `
      <div class="substrate-path">
        <span>${esc(label)} <b style="color:${color};font-weight:700;margin-left:6px;">${ok}</b></span>
        <code>${esc(value || "n/a")}</code>
      </div>
    `;
  }

  function serviceRows(items) {
    return `
      <div class="substrate-list substrate-service-list">
        ${items.map((service) => {
          const id = service.service_id || service.id || service.domain;
          const stateLabel = serviceStateLabel(service);
          const health = service?.service_status?.health_url || service?.health_url || service?.local_url || service?.public_url || "n/a";
          return `
            <div class="substrate-service-row">
              <span class="substrate-service-name">${esc(service.display_name || service.domain || id)}</span>
              <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
                <code>${esc(service.service_type || "service")}</code>
                <b style="color:${stateLabel.ok === true ? "#5af2a5" : stateLabel.ok === false ? "#ffcc66" : "#d9f7ff"};font-size:12px;">${esc(stateLabel.label)}</b>
              </div>
              <code>${esc(health)}</code>
              <div class="substrate-actions">
                <button class="primary" data-service-id="${esc(id)}" data-service-action="status">Status</button>
                <button data-service-id="${esc(id)}" data-service-action="open">Open</button>
                <button data-service-id="${esc(id)}" data-service-action="start" ${service.start_command ? "" : "disabled"}>Start</button>
                <button class="danger" data-service-id="${esc(id)}" data-service-action="stop" ${service.stop_command ? "" : "disabled"}>Stop</button>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  function siteComplianceRows(siteStatus) {
    const entries = Object.entries(siteStatus || {});
    if (!entries.length) {
      return `<div class="substrate-list"><div>No site ORB compliance data yet.</div></div>`;
    }
    return `
      <div class="substrate-list substrate-service-list">
        ${entries.map(([siteId, row]) => `
          <div class="substrate-service-row">
            <span class="substrate-service-name">${esc(siteId)}</span>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
              ${pill("CRM", row?.crm_ok ? "OK" : "OFF", row?.crm_ok === true)}
              ${pill("MAIL", row?.mail_ok ? "OK" : "OFF", row?.mail_ok === true)}
              ${pill("MESH", row?.mesh_ok ? "OK" : "OFF", row?.mesh_ok === true)}
              ${pill("VOICE", row?.voice_ok ? "OK" : "OFF", row?.voice_ok === true)}
              ${pill("LISTENERS", row?.listeners_on ? "ON" : "OFF", row?.listeners_on === true)}
              ${pill("E2E", row?.e2e_ok ? "PASS" : "FAIL", row?.e2e_ok === true)}
            </div>
            <code>${esc(row?.last_interaction_at || "n/a")}</code>
            ${row?.last_error ? `<code>${esc(row.last_error)}</code>` : ""}
          </div>
        `).join("")}
      </div>
    `;
  }

  function appRows(items) {
    return `
      <div class="substrate-list substrate-service-list">
        ${items.map((item) => `
          <div class="substrate-service-row">
            <span class="substrate-service-name">${esc(item.label)}</span>
            <code>${esc(item.url)}</code>
            <div class="substrate-actions">
              <button class="primary" data-local-app-id="${esc(item.id)}" type="button">Open</button>
            </div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function appCard(item) {
    const status = state.appStatus[item.id] || { label: "CHECKING", ok: null };
    return panel(item.label, [
      pill("STATE", status.label, status.ok),
      pill("PORT", item.port, status.ok !== false),
      pill("ROLE", item.role, true),
      pathLine("URL", item.url),
      pathLine("HEALTH", status.endpoint || item.healthUrl || item.url),
      `<div class="substrate-actions app-actions">
        <button class="primary" data-local-app-id="${esc(item.id)}" type="button">Open</button>
        <button data-app-health-id="${esc(item.id)}" type="button">Check</button>
      </div>`,
    ].join(""), status.ok === true ? "ONLINE" : status.ok === false ? "CHECK" : "LOCAL");
  }

  function syncDockPageVisibility() {
    const dockRoot = document.getElementById("root");
    const showDock = state.activeTab === "orbDock";
    document.body.classList.toggle("substrate-orb-dock-active", showDock);
    document.body.classList.toggle("substrate-orb-dock-hidden", !showDock);
    if (dockRoot) {
      dockRoot.setAttribute("aria-hidden", showDock ? "false" : "true");
    }
  }

  function renderTabBar(bridgeState) {
    return `
      <div class="substrate-tab-shell">
        <div class="substrate-title">
          <span>Substrate Dock</span>
          <b>${esc(bridgeState)}</b>
        </div>
        <div class="substrate-tabs">
          ${tabs.map((tab) => `
            <button
              class="${tab.id === state.activeTab ? "active" : ""}"
              data-substrate-tab="${esc(tab.id)}"
              type="button"
            >
              ${esc(tab.label)}
            </button>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderTabContent(model) {
    const {
      cp3,
      bridgeState,
      lastSkillDecision,
      notes,
      researchVault,
      services,
      serviceItems,
      skills,
      status,
      substrate,
    } = model;
    const audioRuntime = cp3.audio_runtime_status || {};
    const adapterStatus = cp3.adapter_import_status;

    if (state.activeTab === "acp") {
      return `
        <div class="substrate-grid three">
          ${panel("CP3 Runtime", [
            pill("CP3 ROOT", boolLabel(cp3.cp3_root_exists), cp3.cp3_root_exists),
            pill("SPEECH ADAPTER", runtimeLabel(adapterStatus, cp3.speech_adapter_available), runtimeOk(adapterStatus, cp3.speech_adapter_available)),
            pill("MIC RUNTIME", runtimeLabel(audioRuntime.speech, cp3.speech_runtime_ready), runtimeOk(audioRuntime.speech, cp3.speech_runtime_ready)),
            pill("VOICE ADAPTER", runtimeLabel(adapterStatus, cp3.voice_adapter_available), runtimeOk(adapterStatus, cp3.voice_adapter_available)),
            pill("VOICE RUNTIME", runtimeLabel(audioRuntime.voice, cp3.voice_runtime_ready), runtimeOk(audioRuntime.voice, cp3.voice_runtime_ready)),
            pill("TEXT FRAME", runtimeLabel(adapterStatus, cp3.text_framing_available), runtimeOk(adapterStatus, cp3.text_framing_available)),
          ].join(""), "HEARING")}
          ${panel("Input State", [
            pill("LISTENING", boolLabel(cp3.listening_enabled), cp3.listening_enabled),
            pill("CP3 IMPORT", runtimeLabel(adapterStatus, adapterStatus === "online"), runtimeOk(adapterStatus, adapterStatus === "online")),
            pathLine("AUDIO SOURCE", cp3.audio_input_source),
            pathLine("TEXT SOURCE", cp3.text_input_source),
            pathLine("CP3.0", cp3.cp3_root),
          ].join(""), "LIVE")}
          ${panel("Bridge", [
            pill("BRIDGE", bridgeState, bridgeState === "CONNECTED" ? true : (bridgeState === "ERROR" || String(bridgeState).startsWith("DEGRADED")) ? false : null),
            status.error ? pathLine("ERROR", status.error) : pathLine("LAST EVENT", state.lastBridgeType),
            pathLine("UPDATED", state.updatedAt || "waiting"),
          ].join(""), "IPC")}
        </div>
      `;
    }

    if (state.activeTab === "orbDock") {
      return `
        <div class="substrate-orb-dock-page">
          <span>Orb dock page active</span>
          <b>Docked orb remains visible below</b>
        </div>
      `;
    }

    if (state.activeTab === "apps") {
      return `
        <div class="substrate-grid apps-grid">
          ${appItems.map(appCard).join("")}
          ${panel("Last App", state.lastApp
            ? [
                pill("APP", state.lastApp.title || state.lastApp.id || "opened", true),
                pill("STATUS", state.lastApp.status || "opened", state.lastApp.status !== "error"),
                pathLine("URL", state.lastApp.url || "n/a"),
                state.lastApp.error ? pathLine("ERROR", state.lastApp.error) : "",
              ].join("")
            : pill("RESULT", "none opened", false), "LIVE")}
        </div>
      `;
    }

    if (state.activeTab === "memory") {
      return `
        <div class="substrate-grid three">
          ${panel("Research Vault", [
            pill("VAULT", boolLabel(researchVault.available), researchVault.available),
            pill("LAST RESULT", state.lastResearch ? "RECORDED" : "NONE", Boolean(state.lastResearch)),
            pathLine("ACTIVE LOG", researchVault.active_path),
            pathLine("INDEX", researchVault.index_path),
            pathLine("SHORT CACHE", substrate.short_term_cache_path),
          ].join(""), "AUDIT")}
          ${panel("Notes", [
            pill("TAKING NOTES", boolLabel(notes.taking_notes), notes.taking_notes),
            pill("PENDING NOTEPAD", boolLabel(notes.pending_notepad_summary), notes.pending_notepad_summary),
            pill("TOPIC", notes.active_topic || "none", Boolean(notes.active_topic)),
            pathLine("SESSION", notes.active_session),
            pathLine("LAST NOTEPAD", notes.last_notepad_path),
          ].join(""), "MEMORY")}
          ${panel("Substrate Paths", [
            pathStateLine("CALI SYSTEM", substrate.cali_system_root, substrate.cali_system_exists),
            pathStateLine("MEMORY", substrate.memory_root, substrate.memory_exists),
            pathStateLine("NOTES", substrate.notes_root, substrate.notes_exists),
            pathStateLine("VOICE CACHE", substrate.voice_cache_root, substrate.voice_cache_exists),
            pathStateLine("LOGS", substrate.logs_root, substrate.logs_exists),
          ].join(""), "R DRIVE")}
        </div>
      `;
    }

    if (state.activeTab === "skills") {
      return `
        <div class="substrate-grid three">
          ${panel("Skill Library", [
            pill("LIBRARY", boolLabel(skills.available), skills.available),
            pill("CATALOG", skills.catalog_count || 0, Number(skills.catalog_count || 0) > 0),
            pill("ACTIVE", (skills.active || []).length, (skills.active || []).length > 0),
            pathLine("DECISIONS", substrate.decisions_path),
          ].join(""), "ARBITER")}
          ${panel("Active Skills", `
            <div class="substrate-list">${(skills.active || []).map((skill) => `<div>${esc(skill)}</div>`).join("") || "<div>none</div>"}</div>
          `, "10")}
          ${panel("Last Skill Decision", state.lastSkill
            ? [
                pill("SKILL", state.lastSkill.data?.skill_id || state.lastSkill.data?.skill?.skill_id || "routed", true),
                pill("STATUS", state.lastSkill.data?.status || "received", true),
                pathLine("RESPONSE", state.lastSkill.data?.response_text || state.lastSkill.data?.result || "received"),
              ].join("")
            : lastSkillDecision
              ? [
                  pill("SKILL", lastSkillDecision.selected_skill || "none", Boolean(lastSkillDecision.selected_skill)),
                  pill("STATUS", lastSkillDecision.status || "recorded", lastSkillDecision.status === "success"),
                  pill("CONFIDENCE", lastSkillDecision.result_confidence ?? "n/a", true),
                  pathLine("COMMAND", lastSkillDecision.command || "n/a"),
                  pathLine("INTENT", lastSkillDecision.intent || "n/a"),
                ].join("")
              : pill("RESULT", "none received", false), "LIVE")}
        </div>
      `;
    }

    if (state.activeTab === "services") {
      const localLlm = status.local_llm || {};
      const qwenTts = status.qwen_tts || {};
      const cp3Audio = (cp3.audio_runtime_status || {});
      const runtimeSnapshot = status.runtime_snapshot || {};
      const siteOrbStatus = status.site_orb_status || {};
      const caliLlmStatus = status?.cali_status?.llm_status || {};
      const llmConnected =
        runtimeSnapshot.llm_connected === true ||
        localLlm.connected === true ||
        localLlm.ready === true ||
        caliLlmStatus.connected === true;
      const resolvedLlmEndpoint =
        localLlm.endpoint ||
        caliLlmStatus.endpoint ||
        runtimeSnapshot.llm_endpoint ||
        "n/a";
      const resolvedLlmModel =
        localLlm.model ||
        caliLlmStatus.model ||
        runtimeSnapshot.active_llm ||
        status?.cali_status?.orb_state?.llm_local_model ||
        "n/a";
      const qwenReady =
        runtimeSnapshot.qwen_tts_ready === true ||
        qwenTts.ready === true ||
        String(cp3Audio.tts_provider || "").toLowerCase() === "qwen";
      const voiceReady =
        runtimeSnapshot.voice_ready === true ||
        qwenReady ||
        cp3.voice_runtime_ready === true;
      const voiceLabel = voiceReady
        ? (String(cp3Audio.tts_provider || "").toLowerCase() === "qwen" || qwenReady ? "QWEN ACTIVE" : "VOICE READY")
        : "NO VOICE";
      const siteBadgeRows = prioritySiteBadgeMap.map(({ siteId, appId }) => {
        const siteRow = siteOrbStatus?.[siteId] || {};
        const appState = state.appStatus?.[appId] || {};
        const connected = appState.ok === true;
        const listenersOn = siteRow.listeners_on === true ? true : cp3.listening_enabled === true;
        const llmOk = siteRow.llm_ok === true ? true : llmConnected;
        const voiceOk = siteRow.voice_ok === true ? true : voiceReady;
        return `
          <div class="substrate-service-row">
            <span class="substrate-service-name">${esc(siteId)}</span>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
              ${pill("CONNECTED", connected ? "ON" : (appState.label || "OFF"), connected)}
              ${pill("LISTENERS", listenersOn ? "ON" : "OFF", listenersOn)}
              ${pill("LLM", llmOk ? "OK" : "OFF", llmOk)}
              ${pill("VOICE", voiceOk ? "OK" : "OFF", voiceOk)}
              ${pill("CRM", siteRow.crm_ok ? "OK" : "OFF", siteRow.crm_ok === true)}
              ${pill("MAIL", siteRow.mail_ok ? "OK" : "OFF", siteRow.mail_ok === true)}
              ${pill("MESH", siteRow.mesh_ok ? "OK" : "OFF", siteRow.mesh_ok === true)}
              ${pill("E2E", siteRow.e2e_ok ? "PASS" : "FAIL", siteRow.e2e_ok === true)}
            </div>
            <code>${esc(appState.endpoint || "n/a")}</code>
          </div>
        `;
      }).join("");
      return `
        <div class="substrate-grid substrate-services-layout">
          ${panel("Sites / Services", [
            pill("MODE", services.mode || "local_manifest_required", true),
            pathLine("MANIFEST", services.manifest_path),
            serviceRows(serviceItems),
          ].join(""), "LOCAL")}
          ${panel("Runtime Connections", [
            pill("LLM ROUTE", localLlm.route || "n/a", true),
            pill("LLM CONNECTED", llmConnected ? "TRUE" : "FALSE", llmConnected),
            pathLine("LLM ENDPOINT", resolvedLlmEndpoint),
            pathLine("LLM MODEL", resolvedLlmModel),
            pill("GOV WRAPPER", localLlm.governance_wrapper ? "ON" : "OFF", localLlm.governance_wrapper === true),
            pill("QWEN TTS READY", qwenReady ? "TRUE" : "FALSE", qwenReady),
            pathLine("VOICE ENDPOINT", qwenTts.endpoint || cp3Audio.qwen_tts_endpoint || "n/a"),
            pill("VOICE PROVIDER", cp3Audio.tts_provider || voiceLabel, voiceReady),
            pill("CP3 VOICE RUNTIME", runtimeLabel(cp3Audio.voice, cp3.voice_runtime_ready), runtimeOk(cp3Audio.voice, cp3.voice_runtime_ready)),
            pathLine("MEMORY PATH", substrate.memory_root || "n/a"),
            pathLine("NOTES PATH", substrate.notes_root || "n/a"),
            pathLine("VOICE CACHE", substrate.voice_cache_root || "n/a"),
          ].join(""), "RUNTIME")}
          ${panel("Site ORB Compliance", [
            pill("SITES", Object.keys(siteOrbStatus || {}).length, Object.keys(siteOrbStatus || {}).length > 0),
            siteComplianceRows(siteOrbStatus),
          ].join(""), "E2E")}
          ${panel("Priority Site Runtime", [
            `<div class="substrate-list substrate-service-list">${siteBadgeRows}</div>`,
          ].join(""), "BADGES")}
          ${panel("Last Service", state.lastService
            ? [
                pill("ACTION", state.lastService.action || "status", true),
                pill("STATUS", state.lastService.status || "received", state.lastService.status === "success"),
                pathLine("SERVICE", state.lastService.service?.display_name || state.lastService.service?.domain || state.lastService.service_id || "n/a"),
                pathLine("RESULT", state.lastService.result || state.lastService.error || "received"),
                pathLine("STATUS CODE", state.lastService.status_code || state.lastService.service_status?.status_code || state.lastService.process_result?.exit_code || "n/a"),
                pathLine("ERROR", state.lastService.error || state.lastService.process_result?.stderr || "none"),
                pathLine("TIMESTAMP", state.lastService.timestamp || "n/a"),
              ].join("")
            : pill("RESULT", "none received", false), "LIVE")}
        </div>
      `;
    }

    return `
      <div class="substrate-grid five">
        ${panel("Bridge", [
          pill("BRIDGE", bridgeState, bridgeState === "CONNECTED" ? true : (bridgeState === "ERROR" || String(bridgeState).startsWith("DEGRADED")) ? false : null),
          pill("CACHE", boolLabel(substrate.short_term_cache_exists), substrate.short_term_cache_exists),
          pill("DECISIONS", boolLabel(substrate.decisions_exists), substrate.decisions_exists),
          status.error ? pathLine("ERROR", status.error) : pathLine("UPDATED", state.updatedAt || "waiting"),
        ].join(""), "R DRIVE")}
        ${panel("CP3", [
          pill("ROOT", boolLabel(cp3.cp3_root_exists), cp3.cp3_root_exists),
          pill("MIC", runtimeLabel(audioRuntime.speech, cp3.speech_runtime_ready), runtimeOk(audioRuntime.speech, cp3.speech_runtime_ready)),
          pill("VOICE", runtimeLabel(audioRuntime.voice, cp3.voice_runtime_ready), runtimeOk(audioRuntime.voice, cp3.voice_runtime_ready)),
          pill("TEXT", runtimeLabel(adapterStatus, cp3.text_framing_available), runtimeOk(adapterStatus, cp3.text_framing_available)),
        ].join(""), "I/O")}
        ${panel("Skills", [
          pill("LIBRARY", boolLabel(skills.available), skills.available),
          pill("CATALOG", skills.catalog_count || 0, Number(skills.catalog_count || 0) > 0),
          pill("ACTIVE", (skills.active || []).length, (skills.active || []).length > 0),
          pill("LAST", lastSkillDecision?.selected_skill || "none", Boolean(lastSkillDecision?.selected_skill)),
        ].join(""), "ARBITER")}
        ${panel("Memory", [
          pill("VAULT", boolLabel(researchVault.available), researchVault.available),
          pill("NOTES", notes.active_topic || "none", Boolean(notes.active_topic)),
          pill("NOTEPAD", boolLabel(notes.pending_notepad_summary), notes.pending_notepad_summary),
          pathLine("LOG", researchVault.active_path),
        ].join(""), "AUDIT")}
        ${panel("Services", [
          pill("MODE", services.mode || "local_manifest_required", true),
          pill("DOMAINS", serviceItems.length, serviceItems.length > 0),
          pathLine("MANIFEST", services.manifest_path),
        ].join(""), "LOCAL")}
      </div>
    `;
  }

  function render() {
    syncDockPageVisibility();
    const status = state.status || {};
    const substrate = status.substrate || {};
    const cp3 = status.cp3_io || status.acp_io || {};
    const researchVault = status.research_vault || {};
    const skills = status.skills || {};
    const notes = status.notes || {};
    const services = status.services || { domains };
    const serviceDomains = services.domains || domains;
    const serviceItems = (services.items || serviceDomains.map((domain) => ({ id: domain, domain })))
      .map((item) => ({ ...item, enabled: item.enabled !== false }));
    const bridgePending = status.pending || status.ready === false;
    const runtime = status.runtime_snapshot || {};
    const hasLiveSignals = Boolean(
      String(runtime.last_updated || "").trim() ||
      (state.lastBridgeType && String(state.lastBridgeType).trim() && String(state.lastBridgeType).toLowerCase() !== "none")
    );
    const specificError = String(status.error || runtime.last_error || "").trim();
    const optionalTelemetryError = (() => {
      const e = specificError.toLowerCase();
      if (!e) return false;
      return (
        e.includes("egf_unavailable") ||
        e.includes("bulkmirrorcache") ||
        e.includes("manifest not found") ||
        e.includes("cali_substrate") ||
        e.includes("domain_knowledge") ||
        e.includes("timed out waiting for status_response")
      );
    })();
    const bridgeState = specificError && !optionalTelemetryError
      ? `DEGRADED: ${specificError}`
      : specificError && optionalTelemetryError
      ? "DEGRADED: PARTIAL TELEMETRY"
      : bridgePending
      ? (hasLiveSignals ? "DEGRADED: STATUS PENDING" : "STARTING")
      : status.running
      ? "CONNECTED"
      : (hasLiveSignals ? "DEGRADED: PARTIAL TELEMETRY" : "WAITING");
    const lastSkillDecision = skills.last_decision || null;

    root.innerHTML = `
      <style>
        #substrate-dock-extension {
          --orb-surface: rgba(9, 24, 35, .86);
          --orb-line: rgba(174, 220, 232, .18);
          --orb-text: #edfaff;
          --orb-muted: rgba(211, 236, 243, .66);
          --orb-faint: rgba(211, 236, 243, .46);
          --orb-accent: #8bdff0;
          --orb-good: #5af2a5;
          --orb-warn: #ffcc66;
          background: linear-gradient(150deg, rgba(7,19,29,.98), rgba(3,10,17,.99));
          border-bottom: 1px solid rgba(174,220,232,.22);
          color: var(--orb-text);
          font-family: "Courier New", monospace;
          padding: 12px 16px 14px;
          max-height: none;
          overflow: auto;
          position: relative;
          z-index: 2;
          flex: 1 1 auto;
          min-height: 0;
        }
        body.substrate-orb-dock-active #substrate-dock-extension {
          flex: 0 0 auto;
          overflow: visible;
          padding-bottom: 8px;
        }
        body.substrate-orb-dock-active #root {
          display: block !important;
          flex: 1 1 auto;
          min-height: 0;
          overflow: hidden;
        }
        body.substrate-orb-dock-hidden #root {
          display: none !important;
        }
        .substrate-tab-shell {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 8px;
        }
        .substrate-title {
          display: flex;
          align-items: baseline;
          gap: 10px;
          min-width: 220px;
          color: var(--orb-text);
          font-size: 15px;
          letter-spacing: 1.2px;
          text-transform: uppercase;
          font-weight: 800;
        }
        .substrate-title b {
          color: var(--orb-good);
          font-size: 11px;
          letter-spacing: .6px;
        }
        .substrate-tabs {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          justify-content: flex-end;
        }
        .substrate-tabs button,
        .substrate-actions button {
          border: 1px solid rgba(0,229,255,.28);
          border-radius: 4px;
          background: rgba(139,223,240,.08);
          color: var(--orb-muted);
          font-family: inherit;
          font-size: 12px;
          font-weight: 700;
          padding: 6px 10px;
          cursor: pointer;
        }
        .substrate-tabs button.active {
          border-color: rgba(90,242,165,.7);
          background: rgba(90,242,165,.14);
          color: var(--orb-good);
        }
        .substrate-grid {
          display: grid;
          gap: 10px;
        }
        .substrate-grid.two { grid-template-columns: repeat(2, minmax(260px, 1fr)); }
        .substrate-services-layout { grid-template-columns: minmax(320px, .85fr) minmax(420px, 1.15fr); align-items: start; }
        .substrate-grid.three { grid-template-columns: repeat(3, minmax(220px, 1fr)); }
        .substrate-grid.five { grid-template-columns: repeat(5, minmax(160px, 1fr)); }
        .substrate-grid.apps-grid { grid-template-columns: repeat(4, minmax(220px, 1fr)); align-items: stretch; }
        .substrate-panel {
          border: 1px solid var(--orb-line);
          border-radius: 8px;
          background: var(--orb-surface);
          padding: 12px;
          min-height: 0;
          display: flex;
          flex-direction: column;
        }
        .substrate-panel-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 10px;
          border-bottom: 1px solid var(--orb-line);
          padding-bottom: 8px;
        }
        .substrate-panel h2 {
          margin: 0;
          font-size: 15px;
          letter-spacing: .8px;
          color: var(--orb-text);
          text-transform: uppercase;
          font-weight: 800;
        }
        .substrate-panel-head span {
          color: var(--orb-good);
          font-size: 11px;
          letter-spacing: .4px;
          font-weight: 700;
        }
        .substrate-pill {
          display: flex;
          justify-content: space-between;
          gap: 8px;
          padding: 6px 0;
          border-bottom: 1px solid rgba(211,236,243,.08);
          font-size: 13px;
          line-height: 1.35;
        }
        .substrate-pill span,
        .substrate-path span {
          color: var(--orb-muted);
        }
        .substrate-pill b {
          font-size: 13px;
          font-weight: 700;
          text-align: right;
          max-width: 58%;
          overflow-wrap: anywhere;
        }
        .substrate-path {
          display: grid;
          gap: 5px;
          margin: 8px 0;
          font-size: 13px;
          line-height: 1.45;
        }
        .substrate-path code {
          color: var(--orb-text);
          word-break: break-all;
          white-space: normal;
          font-size: 13px;
          line-height: 1.45;
          background: rgba(255,255,255,.045);
          border: 1px solid rgba(255,255,255,.07);
          border-radius: 5px;
          padding: 6px 8px;
        }
        .substrate-list {
          display: grid;
          gap: 6px;
          margin-top: 8px;
          max-height: 252px;
          overflow: auto;
        }
        .substrate-list > div {
          font-size: 13px;
          color: var(--orb-text);
          border: 1px solid rgba(211,236,243,.09);
          background: rgba(255,255,255,.035);
          border-radius: 6px;
          padding: 8px;
        }
        .substrate-service-row {
          display: grid;
          gap: 8px;
        }
        .substrate-service-name {
          color: var(--orb-text);
          font-size: 14px;
          font-weight: 700;
        }
        .substrate-service-row code {
          color: var(--orb-muted);
          font-size: 12px;
          overflow-wrap: anywhere;
        }
        .substrate-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .app-actions {
          margin-top: auto;
          padding-top: 8px;
        }
        .substrate-actions button {
          font-size: 12px;
          padding: 5px 8px;
          color: var(--orb-muted);
          border-color: var(--orb-line);
          background: rgba(255,255,255,.045);
        }
        .substrate-actions button.primary {
          color: var(--orb-text);
          border-color: rgba(139,223,240,.42);
          background: rgba(139,223,240,.12);
        }
        .substrate-actions button.danger {
          color: #ffc0c0;
          border-color: rgba(255,125,125,.22);
        }
        .substrate-actions button[disabled] {
          opacity: .45;
          cursor: not-allowed;
        }
        .substrate-footer {
          font-size: 12px;
          color: var(--orb-faint);
          margin-top: 10px;
        }
        .substrate-orb-dock-page {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          border: 1px solid rgba(174,220,232,.16);
          background: rgba(255,255,255,.035);
          border-radius: 6px;
          padding: 8px 10px;
          font-size: 12px;
          color: var(--orb-muted);
        }
        .substrate-orb-dock-page b {
          color: var(--orb-good);
          font-size: 12px;
          text-align: right;
        }
        @media (max-width: 1180px) {
          .substrate-grid.five,
          .substrate-grid.three,
          .substrate-grid.apps-grid { grid-template-columns: repeat(2, minmax(220px, 1fr)); }
          .substrate-services-layout { grid-template-columns: 1fr; }
        }
        @media (max-width: 720px) {
          .substrate-tab-shell { align-items: flex-start; flex-direction: column; }
          .substrate-grid.five,
          .substrate-grid.three,
          .substrate-grid.two,
          .substrate-grid.apps-grid { grid-template-columns: 1fr; }
          .substrate-orb-dock-page { align-items: flex-start; flex-direction: column; }
          .substrate-orb-dock-page b { text-align: left; }
        }
      </style>
      ${renderTabBar(bridgeState)}
      ${renderTabContent({
        cp3,
        bridgeState,
        lastSkillDecision,
        notes,
        researchVault,
        services,
        serviceItems,
        skills,
        status,
        substrate,
      })}
      <div class="substrate-footer">
        Last bridge event: ${esc(state.lastBridgeType)} | Updated: ${esc(state.updatedAt || "waiting")}
      </div>
    `;
  }

  async function checkAppHealth(item) {
    const candidates = Array.isArray(item.healthCandidates) && item.healthCandidates.length
      ? item.healthCandidates
      : [item.healthUrl || item.url];
    for (const endpoint of candidates) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3000);
      try {
        const response = await fetch(endpoint, {
          cache: "no-store",
          signal: controller.signal,
        });
        clearTimeout(timer);
        const reachable = response.status >= 100 && response.status < 500;
        state.appStatus[item.id] = {
          label: response.ok ? "ONLINE" : `HTTP ${response.status}`,
          ok: reachable,
          endpoint,
        };
        if (reachable) return;
      } catch (_error) {
        clearTimeout(timer);
      }
    }
    state.appStatus[item.id] = {
      label: "OFF",
      ok: false,
      endpoint: candidates[0] || item.url,
    };
  }

  async function refreshAppHealth() {
    await Promise.all(appItems.map(checkAppHealth));
    render();
  }

  async function refresh() {
    const api = window.electronAPI;
    if (!api || typeof api.getOrbStatus !== "function") {
      state.updatedAt = "electronAPI unavailable";
      render();
      return;
    }
    try {
      state.status = await api.getOrbStatus();
      state.updatedAt = new Date().toLocaleTimeString();
    } catch (error) {
      state.status = { ...(state.status || {}), ready: false, pending: true, error: error?.message || String(error) };
      state.updatedAt = new Date().toLocaleTimeString();
    }
    render();
  }

  async function bootstrapLocalRuntime() {
    const api = window.electronAPI;
    if (!api || state.bootstrapInFlight) return;
    state.bootstrapInFlight = true;
    try {
      if (typeof api.dispatchPrimeOrbCommand === "function") {
        await api.dispatchPrimeOrbCommand({ command: "activate", source: "substrate_bootstrap" });
      }
      if (typeof api.discoverLocalLlm === "function") {
        const discovery = await api.discoverLocalLlm([
          "http://wsl.localhost:11434",
          "http://127.0.0.1:11434",
        ]);
        const endpoint = discovery?.endpoint || "http://127.0.0.1:11434";
        const model = discovery?.model || "llama3.2:1b";
        if (typeof api.setOrbState === "function") {
          await Promise.allSettled([
            api.setOrbState("llm_route", "local"),
            api.setOrbState("llm_local_endpoint", endpoint),
            api.setOrbState("llm_local_model", model),
          ]);
        }
      } else if (typeof api.setOrbState === "function") {
        await Promise.allSettled([
          api.setOrbState("llm_route", "local"),
          api.setOrbState("llm_local_endpoint", "http://127.0.0.1:11434"),
          api.setOrbState("llm_local_model", "llama3.2:1b"),
        ]);
      }
    } catch (_error) {
      // Non-fatal bootstrap path.
    } finally {
      state.bootstrapInFlight = false;
    }
  }

  render();
  refresh();
  refreshAppHealth();
  setTimeout(async () => {
    const status = state.status || {};
    const local = status.local_llm || {};
    const runtime = status.runtime_snapshot || {};
    const connected = runtime.llm_connected === true || local.connected === true || local.ready === true;
    if (!connected && !state.bootstrapAttempted) {
      state.bootstrapAttempted = true;
      await bootstrapLocalRuntime();
      await refresh();
    }
  }, 600);
  setInterval(refresh, 5000);
  setInterval(refreshAppHealth, 15000);

  const api = window.electronAPI;
  if (api && typeof api.onOrbBridgeMessage === "function") {
    api.onOrbBridgeMessage((_event, message) => {
      state.lastBridgeType = message?.type || "unknown";
      if (message?.type === "status_response" && message.data) {
        state.status = message.data;
        state.updatedAt = new Date().toLocaleTimeString();
      }
      if (message?.type === "research_result") {
        state.lastResearch = message;
      }
      if (message?.type === "skill_result") {
        state.lastSkill = message;
      }
      render();
    });
  }

  if (api && typeof api.onOrbStatusChange === "function") {
    api.onOrbStatusChange((_event, status) => {
      if (status && typeof status === "object") {
        state.status = { ...(state.status || {}), ...status };
        state.updatedAt = new Date().toLocaleTimeString();
        render();
      }
    });
  }

  root.addEventListener("click", async (event) => {
    const tabButton = event.target.closest("button[data-substrate-tab]");
    if (tabButton) {
      state.activeTab = tabButton.getAttribute("data-substrate-tab") || "overview";
      if (!VALID_TABS.has(state.activeTab)) state.activeTab = "overview";
      localStorage.setItem(TAB_KEY, state.activeTab);
      render();
      if (state.activeTab === "apps") refreshAppHealth();
      return;
    }

    const healthButton = event.target.closest("button[data-app-health-id]");
    if (healthButton) {
      const appId = healthButton.getAttribute("data-app-health-id");
      const item = appItems.find((candidate) => candidate.id === appId);
      if (item) {
        state.appStatus[item.id] = { label: "CHECKING", ok: null };
        render();
        await checkAppHealth(item);
        render();
      }
      return;
    }

    const appButton = event.target.closest("button[data-local-app-id]");
    if (appButton) {
      const appId = appButton.getAttribute("data-local-app-id");
      const appInfo = appItems.find((item) => item.id === appId) || { id: appId, label: appId };
      const api = window.electronAPI;
      try {
        if (api && typeof api.openLocalApp === "function") {
          try {
            const result = await api.openLocalApp(appId);
            state.lastApp = { status: "opened", ...result };
          } catch (_openLocalError) {
            if (api && typeof api.openSearch === "function") {
              await api.openSearch(appInfo.url, "web");
              state.lastApp = { status: "opened", title: appInfo.label, url: appInfo.url };
            } else {
              throw _openLocalError;
            }
          }
        } else if (api && typeof api.openSearch === "function") {
          await api.openSearch(appInfo.url, "web");
          state.lastApp = { status: "opened", title: appInfo.label, url: appInfo.url };
        } else {
          state.lastApp = { status: "error", title: appInfo.label, url: appInfo.url };
        }
      } catch (error) {
        state.lastApp = {
          status: "error",
          title: appInfo.label,
          url: appInfo.url,
          error: error?.message || String(error),
        };
      }
      render();
      return;
    }

    const button = event.target.closest("button[data-service-id]");
    if (!button) return;
    const api = window.electronAPI;
    if (!api || typeof api.serviceControl !== "function") {
      state.lastService = { status: "error", error: "serviceControl unavailable" };
      render();
      return;
    }
    const serviceId = button.getAttribute("data-service-id");
    const action = button.getAttribute("data-service-action") || "status";
    try {
      const result = await api.serviceControl(serviceId, action);
      let effectiveResult = {
        ...result,
        timestamp: result?.timestamp || new Date().toISOString(),
      };
      if (action === "open" && result?.url && typeof api.openSearch === "function") {
        await api.openSearch(result.url, "web");
      }
      if ((action === "start" || action === "stop") && result?.status === "success") {
        try {
          const postStatus = await api.serviceControl(serviceId, "status");
          effectiveResult = {
            ...effectiveResult,
            status_code: postStatus?.status_code || postStatus?.service_status?.status_code || effectiveResult.status_code,
            service_status: postStatus?.service_status || effectiveResult.service_status,
          };
        } catch (_postError) {}
      }
      state.lastService = effectiveResult;
      await refresh();
    } catch (error) {
      state.lastService = {
        status: "error",
        action,
        service_id: serviceId,
        error: error?.message || String(error),
        timestamp: new Date().toISOString(),
      };
    }
    render();
  });
})();
