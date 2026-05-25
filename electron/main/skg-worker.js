'use strict';

const crypto = require('crypto');

const SKG_CONFIG = {
  vault: {
    similarityThreshold: 0.82,
    maxAPrioriEntries: 10000,
    ttlAPosteriori: 604800000,
    checksumAlgo: 'SHA-256',
  },

  tension: {
    minimumThreshold: 0.15,
    warningThreshold: 0.30,
  },

  hume: {
    structureWeight: 0.7,
    languageWeight: 0.3,
  },

  llm: {
    local: {
      endpoint: process.env.ORB_BRIDGE_ENDPOINT || 'http://127.0.0.1:5199/query',
      model: process.env.ORB_LOCAL_LLM_MODEL || 'qwen2.5:3b',
      timeoutMs: 15000,
    },
    api: {
      endpoint: 'https://api.openai.com/v1/chat/completions',
      model: 'gpt-4o',
      timeoutMs: 30000,
      apiKey: process.env.LLM_API_KEY || process.env.OPENAI_API_KEY || '',
    },
    cali: {
      endpoint: 'http://localhost:7700/cali/query',
      timeoutMs: 5000,
    },
  },

  governance: {
    logAll: true,
    haltOnViolation: true,
    allowAveraging: false,
    allowWinnerTakeAll: false,
  },
};

const VIOLATIONS = {
  CONFIDENCE_INCREASE_AFTER_ATTENUATION: 'V001',
  OUTCOME_INFLUENCED_EPISTEMIC_WEIGHT: 'V002',
  CONVERGENCE_WITHOUT_TENSION: 'V003',
  MISSING_OR_MUTABLE_LOG: 'V004',
  CROSS_ROLE_BEHAVIOR: 'V005',
  ADAPTIVE_SKEPTICISM: 'V006',
  CONFIDENCE_RECOVERY: 'V007',
  AVERAGING_FORBIDDEN: 'V008',
  SILENT_ELEVATION: 'V009',
  EXECUTION_BACK_PROPAGATION: 'V010',
};

class GovernanceWrapper {
  constructor(config) {
    this.config = config;
    this._auditLog = [];
  }

  async govern(input, pluginFn, pluginLabel) {
    const packet = this._initPacket(input, pluginLabel);

    try {
      packet.kant = this._kant(input);
      packet.locke = this._locke(input, packet.kant);
      packet.hume = this._hume(packet.locke);

      const rawResult = await pluginFn(input);
      packet.rawResult = rawResult;

      packet.spinoza = this._spinoza(rawResult, packet.hume);
      packet.harmonizer = this._harmonizer(packet.spinoza, packet.hume);
      packet.cali = this._caliBridge(packet.harmonizer, packet);

      packet.violations = this._scanViolations(packet);

      if (packet.violations.length > 0 && this.config.governance.haltOnViolation) {
        packet.trustHalted = true;
        packet.trustHaltReason = packet.violations;
      } else {
        packet.trustHalted = false;
      }

      packet.status = 'COMPLETE';
    } catch (err) {
      packet.status = 'ERROR';
      packet.error = err.message;
      this._appendLog({ event: 'PLUGIN_ERROR', plugin: pluginLabel, error: err.message });
    }

    this._appendLog({ event: 'PACKET_SEALED', plugin: pluginLabel, packetId: packet.id });
    return packet;
  }

  _kant(input) {
    const modality = this._inferModality(input);
    return {
      modality,
      scope: this._inferScope(input),
      claimType: this._inferClaimType(input),
      formalized: true,
    };
  }

  _inferModality(input) {
    const text = this._inputText(input).toLowerCase();
    if (/must|always|never|necessarily/.test(text)) return 'analytic';
    if (/should|ought|recommend/.test(text)) return 'normative';
    if (/data|evidence|observe|measure/.test(text)) return 'empirical';
    return 'synthetic';
  }

  _inferScope(input) {
    const text = this._inputText(input);
    if (text.length < 80) return 'narrow';
    if (text.length < 300) return 'moderate';
    return 'broad';
  }

  _inferClaimType(input) {
    const text = this._inputText(input).toLowerCase();
    if (/\?/.test(text)) return 'interrogative';
    if (/compare|vs|versus|difference/.test(text)) return 'comparative';
    if (/explain|how|why|what/.test(text)) return 'explanatory';
    return 'declarative';
  }

  _locke(input, kant) {
    const evidenceScore = this._scoreEvidence(input);
    return {
      evidenceScore,
      grounded: evidenceScore > 0.5,
      groundingSource: 'input_analysis',
      violation: kant.modality === 'empirical' && evidenceScore < 0.3
        ? 'EVIDENCE_AS_NECESSITY_RISK'
        : null,
    };
  }

  _scoreEvidence(input) {
    let score = 0.5;
    const text = this._inputText(input);
    if (input.context) score += 0.15;
    if (input.sourceDocument) score += 0.15;
    if (text.length > 200) score += 0.10;
    if (/\d/.test(text)) score += 0.05;
    return Math.min(score, 1.0);
  }

  _hume(locke) {
    const { structureWeight, languageWeight } = this.config.hume;

    const structureAttenuation = 1 - structureWeight;
    const languageAttenuation = 1 - languageWeight;

    const attenuatedConfidence = locke.evidenceScore
      * (1 - (structureAttenuation * structureWeight + languageAttenuation * languageWeight));

    return {
      attenuatedConfidence,
      structureWeight,
      languageWeight,
      isImmutable: true,
      adaptive: false,
      preAttenuationScore: locke.evidenceScore,
    };
  }

  _spinoza(rawResult, hume) {
    const ceiling = hume.attenuatedConfidence;
    const resultConfidence = this._estimateResultConfidence(rawResult);
    const reconstructedConfidence = Math.min(resultConfidence, ceiling);

    const discarded = resultConfidence > ceiling
      ? { originalConfidence: resultConfidence, reason: 'EXCEEDS_ATTENUATED_CEILING' }
      : null;

    return {
      reconstructedConfidence,
      ceiling,
      discardLog: discarded ? [discarded] : [],
      amplified: reconstructedConfidence > ceiling,
      coherent: reconstructedConfidence <= ceiling,
    };
  }

  _estimateResultConfidence(rawResult) {
    if (!rawResult) return 0.1;
    if (rawResult.confidence !== undefined) return rawResult.confidence;
    if (rawResult.text && rawResult.text.length > 100) return 0.65;
    return 0.50;
  }

  _harmonizer(spinoza, hume) {
    const signals = [
      { id: 'hume_attenuation', value: hume.attenuatedConfidence, weight: 0.7 },
      { id: 'spinoza_reconstruction', value: spinoza.reconstructedConfidence, weight: 0.3 },
    ];

    if (this.config.governance.allowAveraging) {
      throw new Error(`${VIOLATIONS.AVERAGING_FORBIDDEN}: Averaging is forbidden by doctrine`);
    }

    const tension = this._computeTension(signals);
    const tensionSufficient = tension >= this.config.tension.minimumThreshold;

    return {
      signals,
      tension,
      tensionSufficient,
      tensionWarning: tension < this.config.tension.warningThreshold,
      dominanceChecked: true,
      averagingApplied: false,
      winnerTakeAll: false,
    };
  }

  _computeTension(signals) {
    if (signals.length < 2) return 0;
    const values = signals.map((signal) => signal.value);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / values.length;
    return Math.sqrt(variance);
  }

  _caliBridge(harmonizer) {
    const anomalies = [];

    if (!harmonizer.tensionSufficient) {
      anomalies.push({
        code: 'LOW_TENSION',
        message: 'Convergence insufficiently stressed. Trust accordingly.',
        severity: 'HIGH',
      });
    }

    if (harmonizer.tensionWarning) {
      anomalies.push({
        code: 'TENSION_WARNING',
        message: 'Tension below warning threshold.',
        severity: 'MEDIUM',
      });
    }

    return {
      articulated: true,
      preparationAnomalies: anomalies,
      advisoryField: {
        confidence: harmonizer.signals[1] ? harmonizer.signals[1].value : 0,
        tension: harmonizer.tension,
        trustHalted: false,
      },
      altered: false,
      overrode: false,
    };
  }

  _scanViolations(packet) {
    const found = [];

    if (packet.spinoza && packet.spinoza.amplified) {
      found.push({ code: VIOLATIONS.CONFIDENCE_INCREASE_AFTER_ATTENUATION, article: 'III' });
    }

    if (packet.harmonizer && !packet.harmonizer.tensionSufficient) {
      found.push({ code: VIOLATIONS.CONVERGENCE_WITHOUT_TENSION, article: 'V' });
    }

    if (packet.hume && !packet.hume.isImmutable) {
      found.push({ code: VIOLATIONS.ADAPTIVE_SKEPTICISM, article: 'II' });
    }

    if (packet.harmonizer && packet.harmonizer.averagingApplied) {
      found.push({ code: VIOLATIONS.AVERAGING_FORBIDDEN, article: 'IV' });
    }

    if ((packet.cali && packet.cali.altered) || (packet.cali && packet.cali.overrode)) {
      found.push({ code: VIOLATIONS.SILENT_ELEVATION, article: 'VIII' });
    }

    return found;
  }

  _initPacket(input, pluginLabel) {
    return {
      id: `skgp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      pluginLabel,
      input,
      kant: null,
      locke: null,
      hume: null,
      rawResult: null,
      spinoza: null,
      harmonizer: null,
      cali: null,
      violations: [],
      trustHalted: false,
      status: 'INITIALIZING',
    };
  }

  _appendLog(entry) {
    this._auditLog.push({ ...entry, ts: new Date().toISOString() });
  }

  _inputText(input) {
    if (!input) return '';
    return String(input.query || input.text || '');
  }

  getAuditLog() {
    return [...this._auditLog];
  }
}

class VaultLayer {
  constructor(config) {
    this.config = config;
    this._aPriori = new Map();
    this._aPosteriori = new Map();
  }

  async resolve(input) {
    const key = this._hashInput(input);

    const prior = this._aPriori.get(key);
    if (prior && prior.confidence >= this.config.vault.similarityThreshold) {
      return { source: 'A_PRIORI', result: prior.result, cost: 0, confidence: prior.confidence };
    }

    const posterior = this._aPosteriori.get(key);
    if (posterior) {
      const age = Date.now() - posterior.storedAt;
      if (age < this.config.vault.ttlAPosteriori
          && posterior.confidence >= this.config.vault.similarityThreshold) {
        return { source: 'A_POSTERIORI', result: posterior.result, cost: 0, confidence: posterior.confidence };
      }
      this._aPosteriori.delete(key);
    }

    return null;
  }

  store(input, result, confidence) {
    const key = this._hashInput(input);
    if (this._aPriori.has(key)) return;

    this._aPosteriori.set(key, {
      result,
      confidence,
      storedAt: Date.now(),
    });
  }

  seedAPriori(entries) {
    if (!entries || typeof entries !== 'object') return;

    const keys = Object.keys(entries);
    for (const key of keys) {
      if (this._aPriori.size >= this.config.vault.maxAPrioriEntries) {
        break;
      }
      const hashedKey = this._hashText(String(key));
      if (!this._aPriori.has(hashedKey)) {
        this._aPriori.set(hashedKey, entries[key]);
      }
    }
  }

  _hashInput(input) {
    const text = String(input && (input.query || input.text || JSON.stringify(input)) || '').trim().toLowerCase();
    return this._hashText(text.slice(0, 2000));
  }

  _hashText(text) {
    const algorithm = this.config.vault.checksumAlgo.toLowerCase().replace('-', '');
    return crypto.createHash(algorithm).update(text).digest('hex');
  }

  stats() {
    return {
      aPrioriSize: this._aPriori.size,
      aPosterioriSize: this._aPosteriori.size,
      maxAPriori: this.config.vault.maxAPrioriEntries,
    };
  }
}

class LLMPluginLayer {
  constructor(config) {
    this.config = config;
  }

  async query(input, governance) {
    try {
      const caliResult = await this._queryCALI(input);
      if (caliResult) {
        return {
          pluginLabel: 'CALI',
          rawResult: caliResult,
          governed: false,
          trustHalted: false,
          violations: [],
          spinoza: { reconstructedConfidence: caliResult.confidence || 0.90 },
          harmonizer: { tension: null },
          status: 'COMPLETE',
        };
      }
    } catch (err) {
      console.warn(`[SKG] CALI unavailable - escalating to governed LLM layer: ${err.message}`);
    }

    const governed = [
      { label: 'LOCAL_LLM', fn: () => this._queryLocalLLM(input) },
      { label: 'API_LLM', fn: () => this._queryAPILLM(input) },
    ];

    let lastError;

    for (const { label, fn } of governed) {
      try {
        const packet = await governance.govern(input, fn, label);

        if (packet.trustHalted) {
          console.warn(`[SKG] Trust halted on ${label}. Violations:`, packet.violations);
          lastError = new Error(`Trust halted: ${JSON.stringify(packet.violations)}`);
          continue;
        }

        return packet;
      } catch (err) {
        lastError = err;
        console.warn(`[SKG] ${label} failed: ${err.message}`);
      }
    }

    throw lastError || new Error('[SKG] All governed LLM plugins failed or trust halted');
  }

  async _queryCALI(input) {
    const { endpoint, timeoutMs } = this.config.llm.cali;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: input.query || input.text, context: input.context }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`CALI HTTP ${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async _queryLocalLLM(input) {
    const { endpoint, timeoutMs } = this.config.llm.local;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: 'orb_articulation',
          prompt: input.query || input.text,
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`LocalLLM HTTP ${res.status}`);
      const data = await res.json();
      return { text: data.text, confidence: 0.70, source: 'LOCAL_LLM' };
    } finally {
      clearTimeout(timer);
    }
  }

  async _queryAPILLM(input) {
    const { endpoint, model, timeoutMs, apiKey } = this.config.llm.api;
    if (!apiKey) throw new Error('API_LLM: No API key configured');

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: [
            { role: 'system', content: input.systemPrompt || 'You are a precise, factual assistant.' },
            { role: 'user', content: input.query || input.text },
          ],
          temperature: 0.3,
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`API_LLM HTTP ${res.status}`);
      const data = await res.json();
      const text = data.choices && data.choices[0] && data.choices[0].message
        ? data.choices[0].message.content || ''
        : '';
      return { text, confidence: 0.85, source: 'API_LLM' };
    } finally {
      clearTimeout(timer);
    }
  }
}

class SKGWorker {
  constructor(config = SKG_CONFIG) {
    this.config = config;
    this.vault = new VaultLayer(config);
    this.governance = new GovernanceWrapper(config);
    this.llm = new LLMPluginLayer(config);
    this._callCount = { total: 0, vaultHits: 0, llmCalls: 0 };
  }

  async query(input) {
    this._callCount.total += 1;

    const vaultHit = await this.vault.resolve(input);
    if (vaultHit) {
      this._callCount.vaultHits += 1;
      return {
        source: vaultHit.source,
        result: vaultHit.result,
        confidence: vaultHit.confidence,
        cost: 0,
        governed: false,
        trustHalted: false,
        stats: this._stats(),
      };
    }

    this._callCount.llmCalls += 1;
    const packet = await this.llm.query(input, this.governance);

    if (!packet.trustHalted && packet.spinoza && packet.spinoza.reconstructedConfidence > 0) {
      this.vault.store(input, packet.rawResult, packet.spinoza.reconstructedConfidence);
    }

    return {
      source: packet.pluginLabel,
      result: packet.rawResult,
      governed: true,
      packet,
      trustHalted: packet.trustHalted,
      violations: packet.violations,
      tension: packet.harmonizer ? packet.harmonizer.tension : undefined,
      confidence: packet.spinoza ? packet.spinoza.reconstructedConfidence : undefined,
      cost: 1,
      stats: this._stats(),
    };
  }

  seedAPriori(entries) {
    this.vault.seedAPriori(entries);
  }

  configurePlugin(layer, settings) {
    if (!['local', 'api', 'cali'].includes(layer)) {
      throw new Error(`Unknown plugin layer: ${layer}`);
    }
    Object.assign(this.config.llm[layer], settings);
  }

  getAuditLog() {
    return this.governance.getAuditLog();
  }

  _stats() {
    const vaultPct = this._callCount.total > 0
      ? ((this._callCount.vaultHits / this._callCount.total) * 100).toFixed(1)
      : '0.0';
    return {
      ...this._callCount,
      vaultSavingsPct: `${vaultPct}%`,
      vaultSize: this.vault.stats(),
    };
  }
}

module.exports = {
  SKGWorker,
  GovernanceWrapper,
  VaultLayer,
  LLMPluginLayer,
  SKG_CONFIG,
  VIOLATIONS,
};
