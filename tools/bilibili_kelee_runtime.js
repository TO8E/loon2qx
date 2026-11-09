// QX adapter: no arguments, storage, remote modules, or SponsorBlock.
const FIXED = Object.freeze({displayUpList: 'hide', purifyComment: true,
  optimizeRequest: false, sponsorBlock: false, logLevel: 'off'});
const QX_MAX = 16 * 1024 * 1024;
const QX_ROUTES = {
  'bilibili.app.dynamic.v2.Dynamic/DynAll': Jn,
  'bilibili.app.playerunite.v1.Player/PlayViewUnite': Xn,
  'bilibili.app.playurl.v1.PlayURL/PlayView': Yn,
  'bilibili.app.show.v1.Popular/Index': Zn,
  'bilibili.app.view.v1.View/View': zn,
  'bilibili.app.view.v1.View/ViewProgress': Qn,
  'bilibili.app.view.v1.View/RelatesFeed': ei,
  'bilibili.app.viewunite.v1.View/ViewProgress': ti,
  'bilibili.app.viewunite.v1.View/RelatesFeed': ri,
  'bilibili.app.viewunite.v1.View/View': si,
  'bilibili.app.viewunite.v1.View/AIRelateAsync': oi,
  'bilibili.community.service.dm.v1.DM/DmView': fi,
  'bilibili.main.community.reply.v1.Reply/MainList': pi,
  'bilibili.pgc.gateway.player.v2.PlayURL/PlayView': di,
  'bilibili.polymer.app.search.v1.Search/SearchAll': ui
};
function qxHeader(headers, name) {
  const key = Object.keys(headers || {}).find(k => k.toLowerCase() === name);
  return key === undefined ? '' : String(headers[key]);
}
function qxBytes(value) {
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  throw Error('Binary body unavailable'); // Never reinterpret a UTF-8 body as protobuf.
}
function qxBuffer(bytes) { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength); }
function qxCRC(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let k = 0; k < 8; k++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function qxGunzip(bytes) {
  if (bytes.length < 18 || bytes[0] !== 31 || bytes[1] !== 139 || bytes[2] !== 8 || (bytes[3] & 224)) throw Error('Invalid gzip');
  const tail = new DataView(bytes.buffer, bytes.byteOffset + bytes.length - 8, 8);
  const size = tail.getUint32(4, true);
  if (size > QX_MAX) throw Error('Oversized gzip');
  const result = qxGunzipSync(bytes, {out: new Uint8Array(size)});
  if (result.length !== size || qxCRC(result) !== tail.getUint32(0, true)) throw Error('Invalid gzip checksum');
  return result;
}
function qxUnframe(value, headers) {
  let bytes = qxBytes(value);
  if (bytes.length > QX_MAX) throw Error('Oversized body');
  const httpEncoding = qxHeader(headers, 'content-encoding').toLowerCase();
  if (httpEncoding && !['identity', 'gzip'].includes(httpEncoding)) throw Error('Unsupported HTTP encoding');
  // QX normally handles HTTP Content-Encoding; also accept still-compressed bytes.
  if (bytes[0] === 31 && bytes[1] === 139) bytes = qxGunzip(bytes);
  if (bytes.length < 5 || bytes[0] > 1) throw Error('Not a unary gRPC data frame');
  const length = new DataView(bytes.buffer, bytes.byteOffset + 1, 4).getUint32(0);
  if (length !== bytes.length - 5) throw Error('Truncated or multi-frame/streaming gRPC');
  if (!bytes[0]) return bytes.subarray(5);
  if (qxHeader(headers, 'grpc-encoding').toLowerCase() !== 'gzip') throw Error('Unsupported gRPC compression');
  return qxGunzip(bytes.subarray(5));
}
function qxFrame(bytes) {
  const framed = new Uint8Array(bytes.length + 5);
  new DataView(framed.buffer).setUint32(1, bytes.length);
  framed.set(bytes, 5);
  return qxBuffer(framed); // The QX API requires ArrayBuffer, not Uint8Array.
}
function qxCleanHeaders(headers) {
  const result = {};
  // QX owns HTTP length/encoding in response-body rewrites; preserve both.
  const remove = ['grpc-encoding', 'content-md5', 'etag'];
  for (const key of Object.keys(headers || {})) {
    if (!remove.includes(key.toLowerCase())) result[key] = headers[key];
  }
  return result;
}
function qxTransform(handler, value, headers) {
  const payload = qxUnframe(value, headers);
  const ctx = {argument: FIXED, request: {headers: {}}, response: {bodyBytes: payload}};
  handler(ctx, () => {});
  return qxFrame(ctx.response.bodyBytes);
}
function qxMain() {
  let finished = false;
  const done = value => { if (!finished) { finished = true; $done(value || {}); } };
  try {
    // Response-only purification. Never fetch, retry, wait for a request or
    // manufacture a response in the request phase. Cannot add HTTP/2 support.
    if (typeof $response === 'undefined') return done();
    const match = /^https:\/\/(grpc\.biliapi\.net|app\.bilibili\.com)\/(bilibili\.[^?#]+)$/i.exec($request.url);
    if (!match || String($request.method).toUpperCase() !== 'POST') return done();
    const route = Object.keys(QX_ROUTES).find(key => key.toLowerCase() === match[2].toLowerCase());
    const handler = QX_ROUTES[route];
    if (!handler) return done();
    const headers = $response.headers || {};
    const status = qxHeader(headers, 'grpc-status');
    if (($response.statusCode && $response.statusCode !== 200) || (status && status !== '0')) return done();
    const bodyBytes = qxTransform(handler, $response.bodyBytes, headers);
    done({bodyBytes, headers: qxCleanHeaders(headers)});
  } catch (_) { done(); }
}
qxMain();
