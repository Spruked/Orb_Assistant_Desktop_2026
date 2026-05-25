const fs = require('fs');
const path = require('path');

const moduleRoot = path.resolve(__dirname, '..', '..', '..', 'substrate', 'spruk_legacy_orb');
const indicesDir = path.join(moduleRoot, 'memory_graph', 'indices');
const nodesDir = path.join(moduleRoot, 'memory_graph', 'nodes');
const statePath = path.join(moduleRoot, 'presence', 'orb_state.json');
const interactionsLog = path.join(indicesDir, 'interactions.jsonl');
const observationsLog = path.join(indicesDir, 'observations.jsonl');
const profilePath = path.join(indicesDir, 'profile_snapshot.json');

function ensurePaths() {
  fs.mkdirSync(indicesDir, { recursive: true });
  fs.mkdirSync(nodesDir, { recursive: true });
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  if (!fs.existsSync(interactionsLog)) fs.writeFileSync(interactionsLog, '', 'utf8');
  if (!fs.existsSync(observationsLog)) fs.writeFileSync(observationsLog, '', 'utf8');
  if (!fs.existsSync(profilePath)) {
    fs.writeFileSync(profilePath, JSON.stringify({
      profile_version: 1,
      updated_at: null,
      interaction_count: 0,
      observation_count: 0,
      voice_observation_count: 0,
      top_topics: [],
      behavior_patterns: [],
      voice_markers: { common_phrases: [], observed_tones: [] },
    }, null, 2), 'utf8');
  }
  if (!fs.existsSync(statePath)) {
    fs.writeFileSync(statePath, JSON.stringify({
      status: 'standby',
      last_updated: null,
      last_interaction_id: null,
      last_observation_id: null,
    }, null, 2), 'utf8');
  }
}

function utcNow() {
  return new Date().toISOString();
}

function extractTopics(text) {
  const lowered = String(text || '').toLowerCase();
  const topicMap = {
    family: ['abby', 'family', 'daughter', 'father'],
    fear: ['fear', 'scared', 'panic', 'afraid'],
    truth: ['truth', 'honest', 'lie'],
    work: ['build', 'work', 'business', 'project'],
    love: ['love', 'care', 'heart', 'relationship'],
    legacy: ['legacy', 'inherit', 'future'],
    money: ['money', 'cash', 'debt', 'bills'],
    faith: ['faith', 'hope', 'pray', 'god'],
  };
  const topics = Object.entries(topicMap)
    .filter(([, keywords]) => keywords.some((keyword) => lowered.includes(keyword)))
    .map(([topic]) => topic);
  return topics.length ? topics : ['general'];
}

function appendJsonl(target, record) {
  ensurePaths();
  fs.appendFileSync(target, `${JSON.stringify(record)}\n`, 'utf8');
}

function readJsonl(target) {
  ensurePaths();
  const raw = fs.readFileSync(target, 'utf8');
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function writeNode(record, kind) {
  const node = {
    node_id: record.id,
    kind,
    timestamp: record.timestamp,
    summary: record.content || record.user_text || record.orb_text || '',
    topics: record.topics || [],
    metadata: record.metadata || {},
  };
  fs.writeFileSync(path.join(nodesDir, `${record.id}.json`), JSON.stringify(node, null, 2), 'utf8');
}

function updateState(updates) {
  ensurePaths();
  const current = JSON.parse(fs.readFileSync(statePath, 'utf8'));
  const next = { ...current, ...updates, last_updated: utcNow() };
  fs.writeFileSync(statePath, JSON.stringify(next, null, 2), 'utf8');
}

function rebuildProfile() {
  const interactions = readJsonl(interactionsLog);
  const observations = readJsonl(observationsLog);
  const topicCounts = new Map();
  for (const row of [...interactions, ...observations]) {
    for (const topic of row.topics || []) {
      topicCounts.set(topic, (topicCounts.get(topic) || 0) + 1);
    }
  }
  const topTopics = [...topicCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([topic, count]) => ({ topic, count }));
  const profile = {
    profile_version: 1,
    updated_at: utcNow(),
    interaction_count: interactions.length,
    observation_count: observations.length,
    voice_observation_count: 0,
    top_topics: topTopics,
    behavior_patterns: [],
    voice_markers: { common_phrases: [], observed_tones: [] },
  };
  fs.writeFileSync(profilePath, JSON.stringify(profile, null, 2), 'utf8');
  return profile;
}

function recordInteraction(userText, orbText = '', channel = 'desktop_chat', metadata = {}) {
  const record = {
    id: `interaction_${Date.now()}`,
    timestamp: utcNow(),
    channel,
    user_text: userText,
    orb_text: orbText,
    metadata,
    topics: extractTopics(`${userText} ${orbText}`),
  };
  appendJsonl(interactionsLog, record);
  writeNode(record, 'interaction');
  rebuildProfile();
  updateState({ status: 'learning', last_interaction_id: record.id });
  return record;
}

function recordObservation(observationType, content, metadata = {}) {
  const record = {
    id: `observation_${Date.now()}`,
    timestamp: utcNow(),
    observation_type: observationType,
    content,
    metadata,
    topics: extractTopics(content),
  };
  appendJsonl(observationsLog, record);
  writeNode(record, 'observation');
  rebuildProfile();
  updateState({ status: 'learning', last_observation_id: record.id });
  return record;
}

module.exports = {
  recordInteraction,
  recordObservation,
  rebuildProfile,
};
