const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const bridge = path.resolve(__dirname, '../../src/mc_name_finder/node/bridge.cjs')
const stub = path.join(__dirname, 'fake-auth.cjs')
function run (flags, interactive = false) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mc-auth-test-'))
  const result = spawnSync(process.execPath, ['--require', stub, bridge], {
    input: JSON.stringify({ cache_dir: directory, interactive }), encoding: 'utf8',
    env: { ...process.env, ...flags }, timeout: 10000
  })
  const events = result.stdout.trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
  return { directory, result, events }
}
test('cached authentication returns a token through the JSON pipe and writes private cache', () => {
  const { directory, result, events } = run({})
  try {
    assert.equal(result.status, 0)
    assert.equal(events.length, 1)
    assert.equal(events[0].event, 'token')
    assert.equal(events[0].token, 'test-secret')
    assert.equal(result.stderr, '')
    if (process.platform !== 'win32') {
      assert.equal(fs.statSync(path.join(directory, 'mca.json')).mode & 0o777, 0o600)
    }
  } finally { fs.rmSync(directory, { recursive: true, force: true }) }
})
test('interactive device event precedes token', () => {
  const { directory, result, events } = run({ TEST_DEVICE: '1' }, true)
  try {
    assert.equal(result.status, 0)
    assert.deepEqual(events.map(event => event.event), ['device', 'token'])
    assert.equal(events[0].code, 'ABCD1234')
  } finally { fs.rmSync(directory, { recursive: true, force: true }) }
})
test('unattended refresh refuses interactive sign-in and exposes no token', () => {
  const { directory, result, events } = run({ TEST_DEVICE: '1' })
  try {
    assert.equal(result.status, 1)
    assert.deepEqual(events, [{ event: 'error', code: 'LOGIN_REQUIRED' }])
    assert.ok(!result.stdout.includes('test-secret'))
  } finally { fs.rmSync(directory, { recursive: true, force: true }) }
})
test('authentication errors and library logs never expose credentials', () => {
  const { directory, result, events } = run({ TEST_ERROR: '1' })
  try {
    assert.equal(result.status, 1)
    assert.deepEqual(events, [{ event: 'error', code: 'AUTH_FAILED' }])
    assert.ok(!result.stdout.includes('test-secret'))
  } finally { fs.rmSync(directory, { recursive: true, force: true }) }
})
