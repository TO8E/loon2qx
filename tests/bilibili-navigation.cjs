const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const original = fs.readFileSync(path.join(root, 'tools/upstream/bilibili_json.js'), 'utf8');
const patched = fs.readFileSync(path.join(root, 'js/Bilibili/bilibili_json.js'), 'utf8');
let checks = 0;
function run(code, payload, url = 'https://app.bilibili.com/x/resource/show/tab/v2?fixture=1') {
  const calls = [];
  vm.runInNewContext(code, {
    $request: {url}, $response: {body: typeof payload === 'string' ? payload : JSON.stringify(payload)},
    $done: response => calls.push(response), console: {log() {}}
  }, {timeout: 1000, codeGeneration: {strings: false, wasm: false}});
  assert.equal(calls.length, 1); checks++;
  return calls[0].body ? JSON.parse(calls[0].body) : JSON.parse(JSON.stringify(calls[0]));
}
const home = {id: 177, name: '首页', tab_id: 'home', uri: 'bilibili://main/home/', icon: 'home-icon', pos: 1};
const following = {id: 179, name: '关注', tab_id: 'dynamic', uri: 'bilibili://following/home/', icon: 'original-icon', icon_selected: 'selected-icon', pos: 3};
const mine = {id: 181, name: '我的', tab_id: '我的Bottom', uri: 'bilibili://user_center/', pos: 5};
const mall = {id: 102, name: '会员购', uri: 'bilibili://mall/home', pos: 2};
function payload(tab = following) { return {code: 0, data: {bottom: [home, mall, tab, mine], keep: 'normal'}}; }
const before = run(original, payload());
assert.equal(before.data.bottom.some(tab => tab.uri === following.uri), false); checks++;
const after = run(patched, payload());
assert.deepEqual(after.data.bottom, [home, following, mine]); checks++;
assert.equal(after.data.keep, 'normal'); checks++;
assert.deepEqual(after.data.tab, before.data.tab); checks++;
assert.deepEqual(after.data.top, before.data.top); checks++;
// Existing 动态, localized labels, identifiers, and URI-based recognition.
for (const tab of [
  {...following, name: '动态'}, {...following, name: '關注'}, {...following, name: 'Following'},
  {...following, name: 'new-label', id: 999, tab_id: 'changed'},
  {name: 'new-label', tab_id: 'dynamic', uri: 'bilibili://other-route/'},
  {name: '关注', id: 999, tab_id: 'unknown', uri: 'bilibili://other-route/'}
]) {
  const result = run(patched, payload(tab));
  assert.deepEqual(result.data.bottom, [home, tab, mine]); checks++;
}
// Preserve unknown layouts instead of guessing and removing navigation.
const unknown = {name: 'future-entry', id: 999, tab_id: 'future', uri: 'bilibili://future/home'};
const unfamiliar = payload(unknown);
assert.deepEqual(run(patched, unfamiliar).data.bottom, unfamiliar.data.bottom); checks++;
const three = {data: {bottom: [home, following, mine], keep: 'three'}};
assert.deepEqual(run(patched, three).data.bottom, three.data.bottom); checks++;
assert.deepEqual(run(patched, '<html>upstream error</html>'), {}); checks++;
// A non-navigation route keeps the original upstream processing behavior.
const splash = {data: {show: [{id: 'ad'}], keep: 1}};
const splashUrl = 'https://app.bilibili.com/x/v2/splash/show';
assert.deepEqual(run(patched, splash, splashUrl), run(original, splash, splashUrl)); checks++;
console.log(JSON.stringify({checks,originalBugReproduced: true,networkRequests: 0,phoneTested: false}));
