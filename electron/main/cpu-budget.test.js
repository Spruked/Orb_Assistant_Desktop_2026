// Run from electron/:  node --test main/cpu-budget.test.js
// Static guards for the CPU budget on a 4-core machine: these limits must not silently disappear.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const main = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8').replace(/\r\n/g, '\n');

function functionBody(source, startMarker) {
  const start = source.indexOf(startMarker);
  assert.ok(start >= 0, `${startMarker} not found`);
  const end = source.indexOf('\n}\n', start);
  return source.slice(start, end + 3);
}

test('the cursor is only forwarded when it moved, and Python is rate limited', () => {
  const sampler = functionBody(main, 'function sampleDesktopCursor()');
  assert.ok(sampler.includes('const moved = cursor.x !== lastCursorX || cursor.y !== lastCursorY;'));
  assert.ok(sampler.includes('!moved && now - lastCursorBroadcastAt < CURSOR_IDLE_REFRESH_MS'));
  assert.ok(sampler.includes('now - lastCursorToPythonAt >= CURSOR_PYTHON_MIN_INTERVAL_MS'));
  // sendCursorMove must only be reachable through the rate-limited branch.
  assert.equal((sampler.match(/sendCursorMove\(/g) || []).length, 1);
  assert.ok(sampler.indexOf('CURSOR_PYTHON_MIN_INTERVAL_MS') < sampler.indexOf('sendCursorMove('));
});

test('the default Python cursor rate is at most about 10 per second', () => {
  const interval = Number(/ORB_CURSOR_PYTHON_MIN_INTERVAL_MS', (\d+)/.exec(main)[1]);
  assert.ok(interval >= 100, `interval ${interval} ms would send more than 10 cursor messages a second`);
  const idle = Number(/ORB_CURSOR_IDLE_REFRESH_MS', (\d+)/.exec(main)[1]);
  assert.ok(idle >= 1000);
});
