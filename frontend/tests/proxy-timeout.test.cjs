/* Transport regression: supported solve time must fit the standalone API proxy. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

test('portable proxy allows the maximum core solve plus secondary activity solves', async () => {
  const source = path.resolve(__dirname, '../next.config.ts');
  const compiled = ts.transpileModule(fs.readFileSync(source, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  const loaded = new Module(source, module);
  const previous = process.env.PORTABLE_WINDOWS_BUILD;
  try {
    process.env.PORTABLE_WINDOWS_BUILD = '1';
    loaded._compile(compiled, source);
    const config = loaded.exports.default;
    // Regression: undefined selects Next's 30-second default, producing a 500
    // even when the Python endpoint successfully generates all six activities.
    assert.ok(config.experimental?.proxyTimeout >= 180_000);
    assert.ok(config.experimental.proxyTimeout <= 300_000, 'transport remains bounded');
    assert.equal(config.output, 'standalone');
    assert.deepEqual(await config.rewrites(), [{source: '/api/:path*', destination: 'http://127.0.0.1:8000/api/:path*'}]);
  } finally {
    if (previous === undefined) delete process.env.PORTABLE_WINDOWS_BUILD;
    else process.env.PORTABLE_WINDOWS_BUILD = previous;
  }
});
