'use strict';
// No JSON mock codecs: fixtures are actual protobuf wire bytes in actual gRPC frames.
// Tag numbers were checked against pinned upstream generated message descriptors.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const zlib = require('node:zlib');
const root = path.resolve(__dirname, '..');
const dir = process.argv[2] || path.join(root, 'js/BilibiliKelee');
const scripts = Object.fromEntries(['request', 'response', 'json'].map(k => [k, fs.readFileSync(path.join(dir, k + '.js'), 'utf8')]));
const U = b => new Uint8Array(b);
const ab = b => U(b).buffer;
const concat = (...a) => Buffer.concat(a.map(b => Buffer.from(b)));
function varint(n) { let x = BigInt(n), a = []; do { let c = Number(x & 127n); x >>= 7n; a.push(c | (x ? 128 : 0)); } while (x); return Buffer.from(a); }
const v = (tag, n) => concat(varint(tag * 8), varint(n));
const b = (tag, value) => { const data = typeof value === 'string' ? Buffer.from(value) : value; return concat(varint(tag * 8 + 2), varint(data.length), data); };
const msg = (...a) => concat(...a);
function frame(payload, compressed = false, options = {}) {
  const data = compressed ? zlib.gzipSync(payload, options) : payload;
  const head = Buffer.alloc(5); head[0] = +compressed; head.writeUInt32BE(data.length, 1);
  return concat(head, data);
}
function parse(buffer) {
  const data = Buffer.from(buffer), result = []; let offset = 0;
  const read = () => { let n = 0n, shift = 0n, c; do { assert(offset < data.length); c = data[offset++]; n |= BigInt(c & 127) << shift; shift += 7n; } while (c & 128); return n; };
  while (offset < data.length) {
    const start = offset, key = Number(read()), no = key >>> 3, wire = key & 7; let value;
    if (wire === 0) value = read();
    else if (wire === 2) { const length = Number(read()); value = data.subarray(offset, offset + length); offset += length; }
    else if (wire === 1 || wire === 5) { const length = wire === 1 ? 8 : 4; value = data.subarray(offset, offset + length); offset += length; }
    else throw Error('Unsupported fixture wire type');
    assert(offset <= data.length); result.push({no, wire, value, raw: data.subarray(start, offset)});
  }
  return result;
}
const values = (m, no) => parse(m).filter(f => f.no === no).map(f => f.value);
const first = (m, no) => values(m, no)[0];
function outputPayload(result) {
  assert(result.bodyBytes instanceof ArrayBuffer, 'QX requires ArrayBuffer');
  assert(!('body' in result), 'never pass protobuf as a UTF-8 string');
  const x = Buffer.from(result.bodyBytes); assert.equal(x[0], 0); assert.equal(x.readUInt32BE(1), x.length - 5);
  return x.subarray(5);
}
const RPC = {
  reply: 'bilibili.main.community.reply.v1.Reply/MainList',
  view: 'bilibili.app.viewunite.v1.View/View',
  dyn: 'bilibili.app.dynamic.v2.Dynamic/DynAll'
};
const unknown = msg(v(200, 987654321012345n), b(201, 'normal future data'),
  concat(varint(202 * 8 + 1), Buffer.from('0102030405060708', 'hex')),
  concat(varint(203 * 8 + 5), Buffer.from('aabbccdd', 'hex')));
const keepReply = b(12, msg(b(1, '正常置顶评论'), b(5, msg(b(1, 'https://b23.tv/normal'), b(2, b(1, '链接')))), unknown));
const keywordAd = b(12, b(1, '淘宝优惠'));
const linkAd = b(12, msg(b(1, '查看介绍'), b(5, msg(b(1, 'https://b23.tv/cm123'), b(2, b(1, '广告'))))));
const textAd = b(12, b(1, 'https://b23.tv/mall/123'));
const reply = msg(b(11, 'commercial'), b(14, keepReply), b(14, keywordAd), b(14, linkAd), b(14, textAd),
  b(27, 'mixed'), b(28, v(1, 3)), b(28, v(1, 5)), b(28, msg(v(1, 1), unknown)), b(6, keywordAd), unknown);
const modules = [msg(v(1, 3), b(5, msg(b(1, 'label'), unknown))), ...[18, 29, 37, 55, 63].map(type => v(1, type)),
  msg(v(1, 28), b(22, msg(b(1, msg(v(1, 1), unknown)), b(1, v(1, 4)), b(1, msg(v(1, 1), b(11, 'ad'))),
    b(1, msg(v(1, 1), b(12, b(6, 'promoted'))))))), msg(v(1, 999), unknown)];
const view = msg(b(3, msg(b(7, 'elec'), unknown)), b(5, b(1, msg(v(1, 1), b(2, msg(...modules.map(m => b(2, m))))))), b(7, 'cm'), unknown);
const dyn = msg(b(1, msg(b(1, msg(v(1, 1), unknown)), b(1, v(1, 15)), b(1, v(1, 18)))), b(2, unknown), b(3, 'topic'), unknown);
function assertUnknown(payload) {
  for (const field of parse(unknown)) assert.deepEqual(parse(payload).find(f => f.no === field.no)?.raw, field.raw);
}
function assertReply(payload) {
  assert.equal(values(payload, 11).length, 0); assert.equal(values(payload, 27).length, 0);
  assert.equal(values(payload, 14).length, 1); assert.deepEqual(first(payload, 14), keepReply);
  assert.equal(first(first(payload, 28), 1), 1n);
  assert.deepEqual(first(payload, 6), keywordAd, 'non-pinned comments must be retained'); assertUnknown(payload);
}
function assertView(payload) {
  assert.equal(values(payload, 7).length, 0); assert.equal(values(first(payload, 3), 7).length, 0);
  assertUnknown(first(payload, 3)); assertUnknown(payload);
  const intro = first(first(first(payload, 5), 1), 2), remaining = values(intro, 2);
  assert.deepEqual(remaining.map(m => first(m, 1)), [3n, 28n, 999n]);
  assert.equal(values(first(remaining[0], 5), 1).length, 0); assertUnknown(first(remaining[0], 5));
  const cards = values(first(remaining[1], 22), 1); assert.equal(cards.length, 1); assertUnknown(cards[0]);
}
async function run(mode, route, body, options = {}) {
  const calls = [], fetches = [], logs = []; let settle;
  const completed = new Promise(resolve => { settle = resolve; });
  const headers = {'content-type': 'application/grpc', ...(options.headers || {})};
  const request = {url: 'https://' + (options.host || 'grpc.biliapi.net') + '/' + route, method: 'POST',
    headers: {'x-bili-moss-engine-type': '1', ...(options.requestHeaders || {})}, bodyBytes: ab(frame(v(1, 12345)))};
  if (options.requestBody !== undefined) request.bodyBytes = options.requestBody;
  const ctx = {ArrayBuffer, Uint8Array, DataView, TextDecoder, TextEncoder, URL, setTimeout, clearTimeout,
    $request: request, $response: {statusCode: options.statusCode || 200, headers, bodyBytes: body},
    $argument: {displayUpList: 'show', purifyComment: false, sponsorBlock: true, logLevel: 'debug'},
    $environment: {'device-model': 'iPadPro', variables: {sponsorBlock: true}},
    $prefs: {valueForKey() { throw Error('Must not read prefs'); }},
    $persistentStore: {read() { throw Error('Must not read persistent storage'); }},
    $utils: {ungzip() { throw Error('Must not use Loon utility'); }},
    console: {log(...x) { logs.push(x); }, warn(...x) { logs.push(x); }, error(...x) { logs.push(x); }},
    $task: {fetch: async req => { fetches.push(req); if (!options.fetch) throw Error('Unexpected network'); return options.fetch(req, fetches.length); }},
    $done: result => { calls.push(result); settle(result); }};
  if (mode === 'json') ctx.$response.body = body;
  vm.runInNewContext(scripts[mode], ctx, {timeout: 3000});
  let timer;
  const result = await Promise.race([completed, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Missing $done')), 10000); })]);
  clearTimeout(timer); await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.length, 1, 'exactly one $done'); assert.equal(logs.length, 0, 'logLevel=off');
  return {result, fetches, calls};
}
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const passthrough = result => assert.equal(Object.keys(result).length, 0);
const response = (rpc, payload, opts) => run('response', rpc, ab(frame(payload)), opts);

test('Reply: purify pinned ads, keep normal comments and unknown wire fields', async () => assertReply(outputPayload((await response(RPC.reply, reply)).result)));
test('View: cm/elec/modules/headline/relates and nested unknown data', async () => assertView(outputPayload((await response(RPC.view, view)).result)));
test('DynAll: hide is fixed even on iPad; keep normal future cards', async () => {
  const p = outputPayload((await response(RPC.dyn, dyn)).result); assert.equal(values(p, 2).length, 0); assert.equal(values(p, 3).length, 0);
  const list = values(first(p, 1), 1); assert.equal(list.length, 1); assertUnknown(list[0]); assertUnknown(p);
});
for (const [name, opts] of [['dynamic', {}], ['fixed', {strategy: zlib.constants.Z_FIXED}], ['stored', {level: 0}]]) {
  test('Real gzip gRPC compression: ' + name, async () => {
    const {result} = await run('response', RPC.reply, ab(frame(reply, true, opts)), {headers: {'Grpc-Encoding': 'gzip', 'Content-Length': '123'}});
    assertReply(outputPayload(result)); assert(!Object.keys(result.headers).some(k => /^grpc-encoding$/i.test(k))); assert.equal(result.headers['Content-Length'], '123', 'QX owns length recalculation');
  });
}
test('Whole HTTP gzip envelope plus compressed gRPC frame', async () => {
  const {result} = await run('response', RPC.reply, ab(zlib.gzipSync(frame(reply, true))), {headers: {'content-encoding': 'gzip', 'grpc-encoding': 'gzip'}});
  assertReply(outputPayload(result)); assert.equal(result.headers['content-encoding'], 'gzip', 'QX owns HTTP content encoding');
});
test('HTTP layer already decompressed by QX', async () => assertReply(outputPayload((await response(RPC.reply, reply, {headers: {'content-encoding': 'gzip'}})).result)));
test('Sliced Uint8Array input uses only byteOffset/byteLength', async () => {
  const data = frame(reply), padded = U(concat(Buffer.alloc(9, 255), data, Buffer.alloc(12)));
  assertReply(outputPayload((await run('response', RPC.reply, padded.subarray(9, 9 + data.length))).result));
});
for (const [name, body, options] of [
  ['missing binary body', undefined, {}], ['UTF-8 body is not binary', 'AAAA', {}],
  ['truncated frame', ab(Buffer.from([0, 0, 0, 0, 9, 8])), {}],
  ['invalid protobuf varint', ab(frame(Buffer.from([128]))), {}],
  ['streaming/multiple data frames', ab(concat(frame(reply), frame(reply))), {}],
  ['grpc-web trailer', ab(Buffer.from([128, 0, 0, 0, 0])), {}],
  ['unsupported grpc compression', ab(frame(reply, true)), {headers: {'grpc-encoding': 'deflate'}}],
  ['unsupported HTTP compression', ab(frame(reply)), {headers: {'content-encoding': 'br'}}],
  ['gRPC error status', ab(frame(reply)), {headers: {'grpc-status': '13'}}],
  ['HTTP error', ab(frame(reply)), {statusCode: 500}],
]) test('Fail-open: ' + name, async () => passthrough((await run('response', RPC.reply, body, options)).result));
test('Corrupt gzip checksum does not silently corrupt protobuf', async () => {
  const bad = frame(reply, true); bad[bad.length - 8] ^= 1;
  passthrough((await run('response', RPC.reply, ab(bad), {headers: {'grpc-encoding': 'gzip'}})).result);
});
test('Unknown route, removed DmSegMobile, and plain unknown fields preserved', async () => {
  for (const route of ['bilibili.future.v1.X/Unknown', 'bilibili.community.service.dm.v1.DM/DmSegMobile']) {
    const r = await response(route, unknown); passthrough(r.result); assert.equal(r.fetches.length, 0);
  }
  const p = outputPayload((await response(RPC.reply, unknown)).result); assert.deepEqual(p, unknown);
});
test('SponsorBlock removed: original Chronos file/md5/sign retained', async () => {
  const chronos = msg(b(1, 'original-md5'), b(2, 'https://bilibili.example/original.zip'), b(3, 'original-sign'), unknown);
  for (const [rpc, ad] of [['bilibili.app.view.v1.View/ViewProgress', 1], ['bilibili.app.viewunite.v1.View/ViewProgress', 4]]) {
    const p = outputPayload((await response(rpc, msg(b(2, chronos), b(ad, 'interactive')))).result);
    assert.deepEqual(first(p, 2), chronos); assert.equal(values(p, ad).length, 0);
  }
});
test('Request replay: binary request fields unchanged; View response filtered', async () => {
  const original = frame(msg(v(1, 100000), b(200, 'opaque request'))), bytes = ab(original);
  const r = await run('request', RPC.view, undefined, {requestBody: bytes, requestHeaders: {'Cookie': 'fixture-cookie'}, fetch: async req => {
    assert.deepEqual(Buffer.from(req.bodyBytes), original); assert(req.bodyBytes instanceof ArrayBuffer); assert(!('body' in req));
    assert.equal(req.opts['auto-cookie'], false); assert.equal(req.opts.redirection, false); assert.equal(req.headers.Cookie, 'fixture-cookie');
    return {statusCode: 200, headers: {'Grpc-Status': '0'}, bodyBytes: ab(frame(view))};
  }});
  assert.equal(r.fetches.length, 1); assert.equal(r.result.status, 'HTTP/1.1 200 OK'); assert(!('response' in r.result));
  assertView(outputPayload(r.result)); assert.deepEqual(Buffer.from(bytes), original);
});
test('Request passthrough still permits View and Reply response purification', async () => {
  passthrough((await run('request', RPC.view)).result);
  assertView(outputPayload((await response(RPC.view, view)).result));
  passthrough((await run('request', RPC.reply)).result);
  assertReply(outputPayload((await response(RPC.reply, reply)).result));
});
test('No undocumented native H2 trailers invented', async () => {
  const r = await run('request', RPC.reply, undefined, {fetch: async () => ({statusCode: 200, headers: {}, bodyBytes: ab(frame(reply))})});
  assert.equal(r.fetches.length, 1); passthrough(r.result);
  const native = await run('request', RPC.reply, undefined, {requestHeaders: {'x-bili-moss-engine-type': '2'}});
  assert.equal(native.fetches.length, 0); passthrough(native.result);
});
test('Request optimization waits for settled fetch before fallback', async () => {
  let inflight = false;
  const r = await run('request', RPC.reply, undefined, {fetch: async (req, n) => {
    assert.equal(inflight, false); inflight = true;
    await new Promise(resolve => setImmediate(resolve)); inflight = false;
    if (n === 1) throw Error('native timeout/network failure');
    assert(req.url.startsWith('https://app.bilibili.com/'));
    return {statusCode: 200, headers: {'grpc-status': '0', 'grpc-encoding': 'gzip'}, bodyBytes: ab(frame(reply, true))};
  }});
  assert.equal(r.fetches.length, 2); assertReply(outputPayload(r.result));
});
test('Successful transport but malformed protobuf returns original without replay', async () => {
  const original = frame(Buffer.from([128]));
  const r = await run('request', RPC.reply, undefined, {fetch: async () => ({statusCode: 200, headers: {'grpc-status': '0'}, bodyBytes: ab(original)})});
  assert.equal(r.fetches.length, 1); assert.equal(r.result.status, 'HTTP/1.1 200 OK'); assert.deepEqual(Buffer.from(r.result.bodyBytes), original);
});
test('Request optimization failed native transport passes through once', async () => {
  const r = await run('request', RPC.reply, undefined, {fetch: async () => { throw Error('unreachable'); }});
  assert.equal(r.fetches.length, 2); passthrough(r.result);
});
test('Case-insensitive paths match rule flags consistently', async () => {
  assertReply(outputPayload((await response(RPC.reply.toUpperCase(), reply)).result));
  const r = await run('json', 'XLIVE/APP-ROOM/V1/INDEX/GETINFOBYROOM?X=1', JSON.stringify({code: 0, data: {shopping_info: {is_show: 1}}}), {host: 'API.LIVE.BILIBILI.COM'});
  assert.equal(JSON.parse(r.result.body).data.shopping_info.is_show, 0);
});
test('Request unsupported/invalid data never creates network work', async () => {
  for (const [route, requestBody] of [[RPC.reply, 'not bytes'], [RPC.view, ab([0])], [RPC.dyn, ab(frame(dyn))], ['bilibili.community.service.dm.v1.DM/DmSegMobile', ab(frame(unknown))]]) {
    const r = await run('request', route, undefined, {requestBody}); assert.equal(r.fetches.length, 0); passthrough(r.result);
  }
});
test('Live JSON original three routes only, invalid JSON fails open', async () => {
  const prefix = 'xlive/';
  const feed = JSON.stringify({code: 0, data: {card_list: [{card_type: 'banner_v2'}, {card_type: 'normal', keep: 3}, {card_type: 'activity_card_v1'}], unknown: 7}});
  const r = await run('json', prefix + 'app-interface/v2/index/feed?x=1', feed, {host: 'api.live.bilibili.com'});
  assert.deepEqual(JSON.parse(r.result.body).data, {card_list: [{card_type: 'normal', keep: 3}], unknown: 7});
  const room = JSON.stringify({code: 0, data: {room_info: {short_id: 100}, shopping_info: {is_show: 1}, reserve_info: {show_reserve_status: true}, function_card: {ad: 9}, new_tab_info: {outer_list: [{biz_id: 33}, {biz_id: 9}]}}});
  const rr = await run('json', prefix + 'app-room/v1/index/getInfoByRoom?x=1', room, {host: 'api.live.bilibili.com'});
  const data = JSON.parse(rr.result.body).data; assert.equal(data.shopping_info.is_show, 0); assert.equal(data.reserve_info.show_reserve_status, false); assert.equal(data.function_card.ad, null); assert.deepEqual(data.new_tab_info.outer_list, [{biz_id: 9}]);
  const user = await run('json', prefix + 'app-room/v1/index/getInfoByUser?x=1', JSON.stringify({code: 0, data: {play_together_info: {}, play_together_info_v2: {}, function_card: {ad: 1}, keep: 7}}), {host: 'api.live.bilibili.com'});
  assert.deepEqual(JSON.parse(user.result.body).data, {function_card: {ad: null}, keep: 7});
  passthrough((await run('json', prefix + 'app-room/v1/index/getInfoByRoom?', '{invalid', {host: 'api.live.bilibili.com'})).result);
});
test('No runtime parameter, persistence, Loon utility, or SponsorBlock entry point', () => {
  for (const source of Object.values(scripts)) for (const banned of ['$argument', '$persistentStore', '$prefs', '$httpClient', '$utils', 'bsbsb.top', '/chronos/', 'DmSegMobile', 'skipSegments']) assert(!source.includes(banned), banned);
});
test('Synthetic responses drop stale HTTP encoding/length and normalize original fallback', async () => {
  for (const payload of [reply, Buffer.from([128])]) {
    const data = zlib.gzipSync(frame(payload, true));
    const r = await run('request', RPC.reply, undefined, {fetch: async () => ({statusCode: 200,
      headers: {'grpc-status': '0', 'Content-Encoding': 'gzip', 'Content-Length': String(data.length),
        'Transfer-Encoding': 'chunked', 'Connection': 'keep-alive', 'Trailer': 'grpc-status', 'Grpc-Encoding': 'gzip'}, bodyBytes: ab(data)})});
    assert.equal(r.fetches.length, 1); assert.equal(r.result.status, 'HTTP/1.1 200 OK');
    assert.deepEqual(Object.keys(r.result.headers), ['grpc-status']);
    const p = outputPayload(r.result);
    if (payload === reply) assertReply(p); else assert.deepEqual(p, payload);
  }
});
(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log('PASS ' + name); }
    catch (e) { failed++; console.error('FAIL ' + name, e.stack); }
  }
  console.log(`${tests.length - failed}/${tests.length} tests passed`);
  if (failed) process.exitCode = 1;
})();
