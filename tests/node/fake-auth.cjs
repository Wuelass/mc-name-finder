// Dependency stub for offline bridge protocol tests; never contacts Microsoft.
const Module = require('node:module')
const original = Module._load
Module._load = function (name, ...args) {
  if (name !== 'prismarine-auth') return original.call(this, name, ...args)
  class Authflow {
    constructor (user, factory, options, callback) {
      this.cache = factory({ cacheName: 'mca', username: user })
      this.callback = callback
      this.mca = { getCachedAccessToken: async () => ({ until: Date.now() + 3600000 }) }
    }
    async getMinecraftJavaToken () {
      console.log('library log with test-secret must be suppressed')
      if (process.env.TEST_DEVICE === '1') this.callback({
        verification_uri: 'https://www.microsoft.com/link', user_code: 'ABCD1234'
      })
      if (process.env.TEST_ERROR === '1') throw new Error('test-secret raw failure')
      await this.cache.setCachedPartial({ token: 'test-secret' })
      return { token: 'test-secret' }
    }
  }
  return { Authflow, Titles: { MinecraftNintendoSwitch: 'stub-title' } }
}
