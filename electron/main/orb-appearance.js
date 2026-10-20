/*
 * ORB appearance (skins): validated skin model and a small persistent store.
 *
 * A skin is pure data: four colors for the 2D orb body's radial gradient (highlight, body, edge, depth), or no
 * gradient at all (the "default" skin, where the orb's colors follow its current mode). It is validated here, in the
 * main process, before it reaches any window, so renderers only ever receive well-formed skins. Persistence is one
 * small JSON file (selected skin id plus one optional custom skin) in the app's skin directory.
 *
 * Presets live in src/skins/orb-skins.json. The overlay renderer turns a skin's gradient into the orb body's
 * background (orb-renderer.js, customSkinGradient).
 */

const fs = require('fs');
const path = require('path');

const HEX = /^#[0-9a-f]{6}$/i;
const ID = /^[a-z0-9][a-z0-9-]{0,31}$/;
const TEXT = /^[\x20-\x7e]{1,120}$/;
const GRADIENT_KEYS = ['core', 'mid', 'edge', 'deep'];
const CUSTOM_ID = 'custom';
const DEFAULT_ID = 'default';

function validateSkin(raw) {
  const errors = [];
  if (!raw || typeof raw !== 'object') {
    return { ok: false, errors: ['skin must be an object'] };
  }
  const id = String(raw.id ?? '');
  const name = String(raw.name ?? '').trim();
  const description = String(raw.description ?? '').trim();
  if (!ID.test(id)) errors.push('id must be lowercase letters, digits and dashes (max 32)');
  if (!name || name.length > 32 || !TEXT.test(name)) errors.push('name must be 1-32 printable characters');
  if (description && !TEXT.test(description)) errors.push('description must be printable text (max 120)');

  const skin = { id, name, description, gradient: null };
  if (raw.gradient === null || raw.gradient === undefined) {
    if (id !== DEFAULT_ID) errors.push('gradient is required (only the default skin has none)');
  } else if (typeof raw.gradient !== 'object') {
    errors.push('gradient must be an object');
  } else if (id === DEFAULT_ID) {
    errors.push('the default skin has no gradient');
  } else {
    skin.gradient = {};
    for (const key of GRADIENT_KEYS) {
      const value = raw.gradient[key];
      if (typeof value !== 'string' || !HEX.test(value)) {
        errors.push(`gradient.${key} must be a #rrggbb color`);
      } else {
        skin.gradient[key] = value.toLowerCase();
      }
    }
  }
  return errors.length ? { ok: false, errors } : { ok: true, skin };
}

function loadPresets(presetsPath, log = console) {
  const parsed = JSON.parse(fs.readFileSync(presetsPath, 'utf8'));
  const presets = [];
  const seen = new Set();
  for (const raw of parsed.skins || []) {
    const result = validateSkin(raw);
    if (!result.ok) {
      log.warn?.(`[appearance] preset "${raw && raw.id}" rejected: ${result.errors.join('; ')}`);
    } else if (seen.has(result.skin.id) || result.skin.id === CUSTOM_ID) {
      log.warn?.(`[appearance] preset id "${result.skin.id}" is reserved or duplicated`);
    } else {
      seen.add(result.skin.id);
      presets.push(result.skin);
    }
  }
  const defaultId = presets.some((p) => p.id === parsed.default) ? parsed.default : presets[0] && presets[0].id;
  if (!defaultId) {
    throw new Error('no valid skin presets');
  }
  return { presets, defaultId };
}

function createAppearanceStore({ presetsPath, dataDir, log = console }) {
  const { presets, defaultId } = loadPresets(presetsPath, log);
  const stateFile = path.join(dataDir, 'appearance.json');
  let state = { selected: defaultId, custom: null };

  function persist() {
    fs.mkdirSync(dataDir, { recursive: true });
    const temp = `${stateFile}.${process.pid}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(state, null, 2), 'utf8');
    fs.renameSync(temp, stateFile);
  }

  function load() {
    try {
      const saved = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
      const custom = saved.custom ? validateSkin({ ...saved.custom, id: CUSTOM_ID }) : null;
      state.custom = custom && custom.ok ? custom.skin : null;
      const known = presets.some((p) => p.id === saved.selected) || (saved.selected === CUSTOM_ID && state.custom);
      state.selected = known ? saved.selected : defaultId;
    } catch (_error) {
      state = { selected: defaultId, custom: null };
    }
  }

  function find(id) {
    return id === CUSTOM_ID ? state.custom : presets.find((p) => p.id === id) || null;
  }

  load();
  return {
    defaultId,
    list: () => [...presets, ...(state.custom ? [state.custom] : [])],
    current: () => find(state.selected) || find(defaultId),
    currentId: () => state.selected,
    applyPreset(id) {
      const skin = find(String(id));
      if (!skin) return { ok: false, errors: [`unknown skin: ${String(id).slice(0, 40)}`] };
      state.selected = skin.id;
      persist();
      return { ok: true, skin };
    },
    applyCustom(raw) {
      const result = validateSkin({ name: 'Custom', description: 'Your custom skin.', ...(raw || {}), id: CUSTOM_ID });
      if (!result.ok) return result;
      state.custom = result.skin;
      state.selected = CUSTOM_ID;
      persist();
      return { ok: true, skin: result.skin };
    },
    reset() {
      state.selected = defaultId;
      persist();
      return { ok: true, skin: find(defaultId) };
    },
  };
}

module.exports = { validateSkin, loadPresets, createAppearanceStore, CUSTOM_ID, DEFAULT_ID };
