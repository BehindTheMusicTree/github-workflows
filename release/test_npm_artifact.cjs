const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { artifactExists } = require('./npm-artifact.cjs');

test('two-package partial publication accepts the matching first artifact and leaves the second to publish', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'npm-recovery-'));
  const archive = path.join(dir, 'package.tgz');
  fs.writeFileSync(archive, 'first');
  const integrity = `sha512-${crypto.createHash('sha512').update('first').digest('base64')}`;
  const metadata = { name: '@org/first', version: '1.2.3', dist: { integrity } };
  const response = (status, body = metadata) => async () => ({ status, ok: status === 200, json: async () => body });
  try {
    const registry = async url => {
      if (url === 'https://registry.npmjs.org/%40org%2Ffirst/1.2.3') return response(200)();
      assert.equal(url, 'https://registry.npmjs.org/%40org%2Fsecond/1.2.3');
      return response(404)();
    };
    assert.equal(await artifactExists('@org/first', '1.2.3', archive, registry), true);
    assert.equal(await artifactExists('@org/second', '1.2.3', archive, registry), false);
    for (const status of [401, 403, 429, 500]) {
      await assert.rejects(artifactExists('@org/first', '1.2.3', archive, response(status)));
    }
    for (const body of [{ ...metadata, name: 'wrong' }, { ...metadata, version: '1.2.4' }, { ...metadata, dist: {} }]) {
      await assert.rejects(artifactExists('@org/first', '1.2.3', archive, response(200, body)));
    }
    fs.writeFileSync(archive, 'different archive');
    await assert.rejects(artifactExists('@org/first', '1.2.3', archive, response(200)));
    await assert.rejects(artifactExists('@org/first', '1.2.3', archive, async () => { throw new Error('network'); }));
    await assert.rejects(artifactExists('@org/first', '1.2.3', archive, async () => ({ status: 200, ok: true, json: async () => { throw new Error('invalid JSON'); } })));
    await assert.rejects(artifactExists('https://bad', '1.2.3', archive, registry));
    await assert.rejects(artifactExists('@org/first', 'v1.2.3', archive, registry));
  } finally {
    fs.rmSync(dir, { recursive: true });
  }
});
