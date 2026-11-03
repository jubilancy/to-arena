// Flickr: gallery-dl output → tools/flickr_to_export.py → engine plan. Run: node tests/flickr.test.mjs
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const T = require(new URL('../arena.js', import.meta.url).pathname);
const root = new URL('..', import.meta.url).pathname;

/* Shaped like `gallery-dl -j`: [2, directory] then [3, url, file] per photo (fields from its flickr extractor). */
const user = { nsid: '1@N01', username: 'someone', path_alias: 'someone' };
const photo = (id, extra = {}) => ({
  id,
  title: `Photo ${id}`,
  description: id % 2 ? 'A description' : '',
  dateupload: '1700000000',
  tags: id % 3 ? ['sunset', 'sky'] : [],
  owner: { nsid: `${id}@N02`, username: `owner${id}`, path_alias: id % 2 ? `owner${id}` : '' },
  url: `https://live.staticflickr.com/65535/${id}_abc_o.jpg`,
  width: 2000,
  height: 1500,
  media: 'photo',
  ...extra,
});
const gallery = { gallery_id: '72157', id: '1-72157', title: 'Sunsets', description: 'Golden hour', url: 'https://www.flickr.com/photos/someone/galleries/72157/' };
const album = { id: '7215', title: 'Trip', description: '' };
const rows = [
  [2, { gallery, user }],
  ...[1, 2, 3].map((id) => [3, `https://live.staticflickr.com/65535/${id}_abc_o_d.jpg`, { ...photo(id), gallery, user }]),
  [3, 'https://www.flickr.com/photos/x/9/play/orig/abc/', { ...photo(9, { url: 'https://www.flickr.com/photos/x/9/play/orig/abc/', media: 'video' }), gallery, user }],
  [2, { album, user }],
  ...[3, 4].map((id) => [3, `https://live.staticflickr.com/65535/${id}_abc_o_d.jpg`, { ...photo(id), album, user }]),
];

const dir = mkdtempSync(join(tmpdir(), 'flickr-'));
writeFileSync(join(dir, 'in.json'), JSON.stringify(rows) + '\n' + JSON.stringify(rows.slice(0, 2)));
execFileSync('uv', ['run', '--no-project', join(root, 'tools/flickr_to_export.py'), join(dir, 'in.json'), join(dir, 'out.json')], { stdio: 'pipe' });
const data = T.normalizeExport(JSON.parse(readFileSync(join(dir, 'out.json'), 'utf8')));

assert.equal(data.source, 'flickr');
assert.deepEqual(data.collections.map((c) => [c.id, c.name, c.elementIds]), [
  ['gallery-72157', 'Sunsets', ['1', '2', '3']],
  ['album-7215', 'Trip', ['3', '4']],
]);
assert.equal(data.elements['9'], undefined, 'video skipped');
assert.equal(data.elements['1'].source.url, 'https://www.flickr.com/photos/owner1/1/');
assert.equal(data.elements['2'].source.url, 'https://www.flickr.com/photos/2@N02/2/', 'falls back to the nsid');
assert.match(data.elements['1'].description, /Tags: #sunset, #sky/);

const plan = T.buildPlan(data, { selected: ['gallery-72157', 'album-7215'], source: 'flickr' });
assert.deepEqual(plan.channels.map((c) => c.key), ['flickr:gallery-72157', 'flickr:album-7215']);
assert.deepEqual(plan.channels[0].metadata, { flickr_collection_id: 'gallery-72157' });
const block = T.blockPayloads(data.elements['1'], { source: 'flickr' })[0];
assert.equal(block.kind, 'image');
assert.equal(block.mediaUrl, 'https://live.staticflickr.com/65535/1_abc_o.jpg');
assert.deepEqual(block.payload.metadata, { flickr_photo_id: '1', flickr_media_index: 0, flickr_url: 'https://www.flickr.com/photos/owner1/1/' });
console.log('✓ Flickr: gallery-dl output → collections, photos, plan');
