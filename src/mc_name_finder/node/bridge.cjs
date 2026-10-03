'use strict'
// stdout is a private JSON-lines pipe to Python. Never print library errors/tokens.
process.umask(0o077)
for (const method of ['log', 'info', 'warn', 'error', 'debug']) console[method] = () => {}
const fs = require('node:fs')
const path = require('node:path')
const { Authflow, Titles } = require('prismarine-auth')
const emit = (data) => process.stdout.write(JSON.stringify(data) + '\n')

class PrivateCache {
  constructor (file) { this.file = file }
  async getCached () {
    try { return JSON.parse(fs.readFileSync(this.file, 'utf8')) } catch (error) {
      if (error.code === 'ENOENT') return {}
      throw error
    }
  }
  async setCached (value) {
    const temporary = this.file + '.tmp'
    fs.writeFileSync(temporary, JSON.stringify(value), { mode: 0o600 })
    fs.chmodSync(temporary, 0o600)
    fs.renameSync(temporary, this.file)
  }
  async setCachedPartial (value) { await this.setCached({ ...await this.getCached(), ...value }) }
  async reset () { await this.setCached({}) }
}

async function main () {
  let input = ''
  for await (const chunk of process.stdin) input += chunk
  const options = JSON.parse(input)
  const allowedCaches = new Set(['live', 'msal', 'sisu', 'xbl', 'bed', 'mca', 'mcs', 'pfb'])
  fs.mkdirSync(options.cache_dir, { recursive: true, mode: 0o700 })
  fs.chmodSync(options.cache_dir, 0o700)
  const factory = ({ cacheName }) => {
    if (!allowedCaches.has(cacheName)) throw new Error('Unknown cache name')
    return new PrivateCache(path.join(options.cache_dir, cacheName + '.json'))
  }
  // This is the documented upstream Java-token example. Microsoft may show
  // “Minecraft for Nintendo Switch” during sign-in; no Switch hardware is needed.
  const flow = new Authflow('mc-name-finder', factory, {
    flow: 'live', authTitle: Titles.MinecraftNintendoSwitch, deviceType: 'Nintendo'
  }, (code) => {
    if (!options.interactive) {
      const error = new Error('Interactive login required')
      error.code = 'LOGIN_REQUIRED'
      throw error
    }
    emit({ event: 'device', uri: code.verification_uri || 'https://www.microsoft.com/link',
      code: code.user_code })
  })
  if (options.refresh) flow.mca.forceRefresh = true
  const result = await flow.getMinecraftJavaToken()
  if (!result.token) throw new Error('Minecraft token missing')
  const cached = await flow.mca.getCachedAccessToken()
  emit({ event: 'token', token: result.token, expires_at: cached.until / 1000 })
}
main().catch((error) => {
  emit({ event: 'error', code: error.code === 'LOGIN_REQUIRED' ? 'LOGIN_REQUIRED' : 'AUTH_FAILED' })
  process.exitCode = 1
})
