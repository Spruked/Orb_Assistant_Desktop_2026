// Run from electron/:  node --test main/orb-appearance.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { validateSkin, loadPresets, createAppearanceStore, CUSTOM_ID, DEFAULT_ID } = require('./orb-appearance');

const PRESETS = path.join(__dirname, '..', 'src', 'skins', 'orb-skins.json');
const read = (...parts) => fs.readFileSync(path.join(__dirname, ...parts), 'utf8').replace(/\r\n/g, '\n');
const quiet = { warn() {} };

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'orb-appearance-'));
}

function goodSkin(overrides = {}) {
  return {
    id: 'test-skin',
    name: 'Test Skin',
    description: 'for tests',
    gradient: { core: '#112233', mid: '#445566', edge: '#778899', deep: '#aabbcc' },
    ...overrides,
  };
}

test('a well-formed skin validates and colors are normalized to lowercase', () => {
  const result = validateSkin(goodSkin({ gradient: { core: '#ABCDEF', mid: '#445566', edge: '#778899', deep: '#aabbcc' } }));
  assert.equal(result.ok, true);
  assert.equal(result.skin.gradient.core, '#abcdef');
});

test('bad colors, ids and shapes are rejected with reasons', () => {
  const bad = [
    goodSkin({ gradient: { core: 'red', mid: '#445566', edge: '#778899', deep: '#aabbcc' } }),
    goodSkin({ gradient: { core: '#12345', mid: '#445566', edge: '#778899', deep: '#aabbcc' } }),
    goodSkin({ gradient: { core: '#112233', mid: '#445566', edge: '#778899' } }), // missing deep
    goodSkin({ gradient: null }), // only the default skin may have no gradient
    goodSkin({ gradient: 'not-an-object' }),
    goodSkin({ id: 'Has Spaces' }),
    goodSkin({ id: '../escape' }),
    goodSkin({ name: '' }),
    goodSkin({ id: DEFAULT_ID, gradient: { core: '#112233', mid: '#445566', edge: '#778899', deep: '#aabbcc' } }),
    null,
    'string',
  ];
  for (const skin of bad) {
    const result = validateSkin(skin);
    assert.equal(result.ok, false, JSON.stringify(skin));
    assert.ok(result.errors.length > 0);
  }
});

test('css or script text cannot enter a color field', () => {
  for (const evil of ['url(javascript:alert(1))', '#112233; background:url(x)', 'expression(alert(1))', '#11223g']) {
    const result = validateSkin(goodSkin({ gradient: { core: evil, mid: '#445566', edge: '#778899', deep: '#aabbcc' } }));
    assert.equal(result.ok, false, evil);
  }
});

test('every shipped preset is valid, the default has no gradient, and ids are unique', () => {
  const { presets, defaultId } = loadPresets(PRESETS, quiet);
  assert.equal(defaultId, DEFAULT_ID);
  assert.equal(presets.length, 13);
  assert.equal(presets.find((p) => p.id === DEFAULT_ID).gradient, null);
  assert.equal(new Set(presets.map((p) => p.id)).size, presets.length);
  assert.equal(JSON.parse(fs.readFileSync(PRESETS, 'utf8')).skins.length, presets.length, 'a shipped preset failed validation');
});

test("the original nine color schemes are presets and match the renderer's gradients", () => {
  const renderer = read('..', 'src', 'orb-renderer.js');
  const { presets } = loadPresets(PRESETS, quiet);
  const schemes = { 'brilliant-blue': 'brilliant_blue', cyber: 'cyber', sunset: 'sunset', forest: 'forest', neon: 'neon', cosmic: 'cosmic', fire: 'fire', ice: 'ice', plasma: 'plasma' };
  for (const [id, scheme] of Object.entries(schemes)) {
    const preset = presets.find((p) => p.id === id);
    assert.ok(preset, id);
    const line = renderer.split('\n').find((l) => l.trim().startsWith(`${scheme}:`));
    for (const color of Object.values(preset.gradient)) {
      assert.ok(line.includes(color), `${id}: ${color} missing from the renderer's ${scheme} gradient`);
    }
  }
});

test('applying a preset persists and survives a restart', () => {
  const dir = tempDir();
  const first = createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet });
  assert.equal(first.currentId(), DEFAULT_ID);
  assert.equal(first.applyPreset('fire').ok, true);
  const second = createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet });
  assert.equal(second.currentId(), 'fire');
  assert.equal(second.current().gradient.edge, '#ff4500');
});

test('an unknown preset is refused and nothing changes', () => {
  const store = createAppearanceStore({ presetsPath: PRESETS, dataDir: tempDir(), log: quiet });
  assert.equal(store.applyPreset('does-not-exist').ok, false);
  assert.equal(store.currentId(), DEFAULT_ID);
});

test('a custom skin is validated, saved, listed and restored', () => {
  const dir = tempDir();
  const store = createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet });
  const bad = store.applyCustom({ gradient: { core: 'nope', mid: '#445566', edge: '#778899', deep: '#aabbcc' } });
  assert.equal(bad.ok, false);
  assert.equal(store.currentId(), DEFAULT_ID);
  assert.equal(store.list().some((s) => s.id === CUSTOM_ID), false);

  const saved = store.applyCustom(goodSkin({ id: 'ignored-id', name: 'My Orb' }));
  assert.equal(saved.ok, true);
  assert.equal(saved.skin.id, CUSTOM_ID, 'a custom skin always gets the reserved id');
  assert.equal(store.list().length, 14);

  const reopened = createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet });
  assert.equal(reopened.currentId(), CUSTOM_ID);
  assert.equal(reopened.current().name, 'My Orb');
});

test('a corrupt or hostile settings file falls back to the default instead of crashing', () => {
  const dir = tempDir();
  fs.writeFileSync(path.join(dir, 'appearance.json'), '{ not json', 'utf8');
  assert.equal(createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet }).currentId(), DEFAULT_ID);

  fs.writeFileSync(path.join(dir, 'appearance.json'), JSON.stringify({ selected: 'custom', custom: { gradient: 'evil' } }), 'utf8');
  const store = createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet });
  assert.equal(store.currentId(), DEFAULT_ID);

  fs.writeFileSync(path.join(dir, 'appearance.json'), JSON.stringify({ selected: 'removed-skin' }), 'utf8');
  assert.equal(createAppearanceStore({ presetsPath: PRESETS, dataDir: dir, log: quiet }).currentId(), DEFAULT_ID);
});

test('reset returns to the live default', () => {
  const store = createAppearanceStore({ presetsPath: PRESETS, dataDir: tempDir(), log: quiet });
  store.applyPreset('plasma');
  const result = store.reset();
  assert.equal(result.skin.id, DEFAULT_ID);
  assert.equal(result.skin.gradient, null);
});

test('main process wires the skin API and rejects untrusted senders', () => {
  const main = read('main.js');
  const preload = read('preload.js');
  for (const channel of ['orb:skins-list', 'orb:skin-current', 'orb:skin-apply', 'orb:skin-custom', 'orb:skin-reset']) {
    assert.ok(main.includes(`ipcMain.handle('${channel}'`), channel);
    assert.ok(preload.includes(`'${channel}'`), channel);
  }
  const handlers = main.slice(main.indexOf("ipcMain.handle('orb:skins-list'"), main.indexOf('dockedMotionReporter'));
  assert.equal((handlers.match(/isTrustedUiSender\(event\)/g) || []).length, 5, 'every skin handler must check the sender');
  assert.ok(preload.includes('onOrbAppearanceChanged'));
});

test('the 2D renderer applies the saved skin to the orb body and follows changes', () => {
  const renderer = read('..', 'src', 'orb-renderer.js');
  assert.ok(renderer.includes('getCurrentOrbSkin'));
  assert.ok(renderer.includes('onOrbAppearanceChanged'));
  assert.ok(renderer.includes('customSkinGradient(skinConfig.colors)'));
  // colors are re-validated before they reach a style
  assert.ok(renderer.includes('const HEX_COLOR = /^#[0-9a-f]{6}$/i;'));
});

test('the Dock has a Skins tab that talks to the validated skin API and escapes user-visible text', () => {
  const substrate = read('..', 'src', 'ui', 'orb-dock-station-substrate.js');
  assert.ok(substrate.includes('{ id: "skins", label: "Skins" }'));
  for (const call of ['getOrbSkins', 'applyOrbSkin', 'applyCustomOrbSkin', 'resetOrbSkin', 'onOrbAppearanceChanged']) {
    assert.ok(substrate.includes(call), call);
  }
  assert.ok(substrate.includes('${esc(skin.name)}') && substrate.includes('${esc(skin.description)}'));
  assert.ok(substrate.includes('skinState.renderDeferred = true'), 'the editor must not be rebuilt while a color is being edited');
});

test('no 3D code or Three.js wiring remains in the live overlay', () => {
  const html = read('..', 'src', 'orb-shell.html');
  const renderer = read('..', 'src', 'orb-renderer.js');
  assert.equal(/three/i.test(html), false, 'orb-shell.html must not load Three.js');
  assert.equal(/createOrbThreeScene|orb-three-body|threeSceneRef|__ORB_THREE/.test(renderer), false);
  assert.equal(fs.existsSync(path.join(__dirname, '..', 'src', 'orb-three-scene.js')), false);
  assert.equal(fs.existsSync(path.join(__dirname, '..', 'src', 'vendor', 'three-r160.min.js')), false);
  // the 2D body is visible again (it was hidden with opacity: 0 while the 3D scene was the body)
  assert.ok(renderer.includes('opacity: dockTransitionOpacity * sleepVisualOpacity,'));
});
