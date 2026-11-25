import assert from 'node:assert/strict';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const root = resolve('.'), fixture = resolve(root, '.runtime', `viewer-test-${process.pid}`);
await mkdir(resolve(fixture, 'assets'), { recursive: true });
const urlPath = '/.runtime/' + fixture.split(sep).pop();
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="red"/></svg>';
for (const name of ['a', 'b']) await writeFile(resolve(fixture, 'assets', name + '.svg'), svg);
await writeFile(resolve(fixture, 'entry.js'), 'window.testVersion=1;');
await writeFile(resolve(fixture, 'index.html'), '<script type="module" src="./entry.js"></script>');
const server = await createServer({ root, server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' });
await server.listen();
const address = server.httpServer!.address() as { port: number };
const origin = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let revision = 1, removed = false;
  await page.route('**/api/catalog', route => route.fulfill({ json: {
    revision: String(revision), projects: [{ name: 'test', sandboxes: [] }],
    assets: (removed ? ['a'] : ['a', 'b']).map(name => ({ project: 'test', subpath: name + '.svg', filename: name + '.svg', format: 'svg', mtime: revision, size: 100, url: urlPath + '/assets/' + name + '.svg' }))
  } }));
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin + '/viewer/');
  await page.getByText('b.svg', { exact: true }).first().click();
  await page.evaluate(() => { (window as any).testImage = document.querySelector('#stage-img'); (window as any).testToken = 1; });
  await page.click('[data-zoom="1.0"]');
  await page.locator('#stage-container').hover();
  const box = await page.locator('#stage-container').boundingBox();
  await page.mouse.move(box!.x + 100, box!.y + 100); await page.mouse.down(); await page.mouse.move(box!.x + 150, box!.y + 130); await page.mouse.up();
  const pan = await page.locator('#stage-box').getAttribute('style');
  revision = 2; await page.click('#refresh-btn');
  await page.waitForFunction(() => document.querySelector<HTMLImageElement>('#stage-img')!.src.endsWith('t=2'));
  assert.equal(await page.evaluate(() => (window as any).testImage === document.querySelector('#stage-img')), true);
  assert.equal(await page.locator('#stage-box').getAttribute('style'), pan);
  const sandbox = await browser.newPage(); await sandbox.goto(origin + urlPath + '/index.html');
  await writeFile(resolve(fixture, 'entry.js'), 'window.testVersion=2;');
  await page.waitForTimeout(500);
  assert.equal(await page.evaluate(() => (window as any).testToken), 1);
  assert.equal(await page.locator('#stage-img').getAttribute('alt'), 'b.svg');
  await page.screenshot({ path: resolve(root, '.runtime', 'viewer-2d.png') });
  removed = true; revision++; await page.click('#refresh-btn');
  await page.getByText('Asset removido.', { exact: false }).waitFor();
  assert.deepEqual(errors, []);
  console.log('Viewer: selection, incremental image update, pan, cross-tab isolation and removal passed.');
} finally {
  await browser.close(); await server.close();
  assert.ok(fixture.startsWith(resolve(root, '.runtime') + sep));
  await rm(fixture, { recursive: true, force: true });
}
