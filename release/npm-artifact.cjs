const crypto = require('node:crypto');
const fs = require('node:fs');

async function artifactExists(name, version, archive, fetchImpl = fetch) {
  if (!/^(@[a-z0-9_-]+\/)?[a-z0-9_.-]+$/.test(name) ||
      !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) {
    throw new Error('Expected an npm package name and stable SemVer version');
  }
  const integrity = `sha512-${crypto.createHash('sha512').update(fs.readFileSync(archive)).digest('base64')}`;
  const response = await fetchImpl(`https://registry.npmjs.org/${encodeURIComponent(name)}/${version}`,
    { signal: AbortSignal.timeout(30000) });
  if (response.status === 404) return false;
  if (!response.ok) throw new Error(`npm registry lookup failed: HTTP ${response.status}`);
  const metadata = await response.json();
  if (metadata.name !== name || metadata.version !== version || metadata.dist?.integrity !== integrity) {
    throw new Error('Existing npm artifact differs in name, version or integrity; investigate without moving the tag');
  }
  return true;
}

module.exports = { artifactExists };
if (require.main === module) {
  (async () => {
    if (process.argv.length !== 5 || !process.env.GITHUB_OUTPUT) {
      throw new Error('Usage: npm-artifact.cjs PACKAGE VERSION ARCHIVE; GITHUB_OUTPUT is required');
    }
    const exists = await artifactExists(...process.argv.slice(2));
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `exists=${exists}\n`);
  })().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
