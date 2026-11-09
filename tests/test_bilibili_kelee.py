"""Independent Kelee regressions: real jq, Node VM, and publication contract.

Run: python3 -m unittest discover -s tests -p 'test_bilibili_kelee.py' -v
Requires jq and node. Reads only pinned snapshots / repository artifacts;
never calls emit(), writes generated assets, fetches upstream, or tests protobuf.
Publication tests intentionally fail until the stable resource is rebuilt.
"""
import base64
import copy
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import build_bilibili_kelee as K
import shared_scope as S

RAW = 'https://raw.githubusercontent.com/TO8E/loon2qx/main'
SNAPSHOT = REPO / 'tools/upstream/bilibili-kelee'
SOURCE = (SNAPSHOT / 'Bilibili_remove_ads.lpx').read_text(encoding='utf-8')
SETTINGS = dict(displayUpList='hide', purifyComment=True, optimizeRequest=True,
                sponsorBlock=False, logLevel='off')
SOURCE_FILTERS = [f'host, {prefix}.biliapi.{suffix}, reject'
                  for suffix in ('com', 'net') for prefix in ('api', 'app')]
SOURCE_FILTERS += [f'host-wildcard, *{word}*.chat.bilibili.com, reject'
                   for word in ('stun', 'tracker', 'p2p')]
FILTERS = SOURCE_FILTERS + ['host, httpdns.bilivideo.com, reject']
HOSTS = ['grpc.biliapi.net', 'app.bilibili.com', 'api.bilibili.com',
         'api.live.bilibili.com', 'line3-h5-mobile-api.biligame.com']
TAB = 'https://app.bilibili.com/x/resource/show/tab/v2?fixture=1'
MINE = 'https://app.bilibili.com/x/v2/account/mine?fixture=1'
MYINFO = 'https://app.bilibili.com/x/v2/account/myinfo?fixture=1'
MOCK_URLS = [
    'https://app.bilibili.com/x/v2/splash/list?fixture=1',
    'https://api.bilibili.com/pgc/activity/deliver/material/receive?fixture=1',
    'https://app.bilibili.com/x/v2/search/square?fixture=1',
    'https://grpc.biliapi.net/bilibili.app.interface.v1.Teenagers/ModeStatus',
    'https://grpc.biliapi.net/bilibili.app.interface.v1.Search/DefaultWords',
    'https://grpc.biliapi.net/bilibili.app.view.v1.View/TFInfo',
]


def active(text):
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith(('#', ';'))]


def rewrites(lines):
    return [tuple(line.split(' url ', 1)) for line in lines if ' url ' in line]


def policy(lines, host):
    """QX exact-host / wildcard semantics, independent of builder helpers."""
    host = host.lower()
    for line in lines:
        kind, value, action = (part.strip() for part in line.split(','))
        if ((kind == 'host' and host == value.lower()) or
                (kind == 'host-wildcard' and fnmatch.fnmatchcase(host, value.lower()))):
            return action
    return None


def source_mocks():
    result = []
    for line in SOURCE.splitlines():
        match = re.fullmatch(r'response if \$\{url\} ~= /(.*)/i then response\.body\.mock\((.*)\)', line)
        if match:
            args = json.loads('[' + match[2] + ']')
            result.append(('(?i)' + match[1], args))
    return result


NODE_VM = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = input.urls.map(url => {
  let calls = 0, network = 0, response;
  const forbidden = () => { network++; throw Error('Unexpected I/O'); };
  const context = {
    $request: {url, method: 'GET'},
    $done: value => { calls++; response = value; },
    fetch: forbidden, XMLHttpRequest: forbidden, WebSocket: forbidden,
    $task: {fetch: forbidden},
    $httpClient: new Proxy({}, {get: () => forbidden}),
    $prefs: new Proxy({}, {get: () => forbidden}),
    $persistentStore: new Proxy({}, {get: () => forbidden}),
    console: {log() {}, warn() {}, error() {}}
  };
  Object.defineProperty(context, '$response', {get: forbidden});
  vm.runInNewContext(input.script, context, {timeout: 1000});
  const result = {calls, network, response};
  if (response && Object.prototype.hasOwnProperty.call(response, 'bodyBytes')) {
    const bytes = new Uint8Array(response.bodyBytes);
    result.bytes = Array.from(bytes);
    result.base64 = Buffer.from(bytes).toString('base64');
  }
  return result;
});
process.stdout.write(JSON.stringify(results));
'''


class BilibiliKeleeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for command in ('jq', 'node'):
            if not shutil.which(command):
                raise RuntimeError(command + ' is required; do not silently skip execution tests')
        cls.parsed = K.parse_rules(SOURCE, RAW)
        cls.rows = rewrites(cls.parsed['rewrites'])

    def jq(self, expression, value):
        run = subprocess.run(['jq', '-c', expression], input=json.dumps(value),
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        lines = run.stdout.splitlines()
        self.assertEqual(len(lines), 1, run.stdout)
        return json.loads(lines[0])

    def expression(self, url):
        rows = [(pattern, action) for pattern, action in self.rows
                if re.search(pattern, url) and action.startswith('jsonjq-response-body ')]
        self.assertEqual(len(rows), 1, url)
        quoted = rows[0][1].removeprefix('jsonjq-response-body ')
        self.assertTrue(quoted.startswith("'") and quoted.endswith("'"))
        return quoted[1:-1]

    def apply(self, url, value):
        return self.jq(self.expression(url), value)

    def mock(self, urls):
        run = subprocess.run(['node', '-e', NODE_VM],
                             input=json.dumps(dict(script=K.mock_script(self.parsed['mocks']), urls=urls)),
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(len(result), len(urls))
        for row in result:
            self.assertEqual(row['calls'], 1)
            self.assertEqual(row['network'], 0)
        return result

    def published(self):
        return active((REPO / 'snippets/bilibili.snippet').read_text(encoding='utf-8'))

    def test_pinned_source_and_jq_hashes(self):
        expected = {
            'Bilibili_remove_ads.lpx': '8db02264fa15b0271ccad40eaa5c14ea3f40864aa5af501c7a64941620e6b0e5',
            'tab_Bilibili_remove_ads.jq': '69b4b2129be425dfa26fe7f06786a8710129c2ce5702fdcd36d90f842aea4dec',
            'mine_Bilibili_remove_ads.jq': 'e99d5ea7038cb973996a04fde3cd9a2840dbba6dcfbfb437c00cb383f53fda2f',
        }
        for name, digest in expected.items():
            with self.subTest(snapshot=name):
                self.assertEqual(hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest(), digest)

    def test_parse_is_offline_and_fixed_settings(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(K.parse_rules(SOURCE, RAW), self.parsed)
        self.assertEqual(K.SETTINGS, SETTINGS)
        self.assertEqual(self.parsed['filters'], SOURCE_FILTERS)
        self.assertCountEqual(self.parsed['hosts'], HOSTS)

    def test_22_rewrites_and_action_inventory_without_pinning_request_body(self):
        actions = [action for _, action in self.rows]
        self.assertEqual(len(actions), 22)  # Review deliberately if request optimization expands.
        self.assertEqual(sum(a.startswith('jsonjq-response-body ') for a in actions), 11)
        self.assertEqual(actions.count('reject-dict'), 2)
        self.assertEqual(sum(a.startswith('script-echo-response ') for a in actions), 6)
        self.assertEqual(sum(a.startswith('script-response-body ') for a in actions), 2)
        request = [a for a in actions if 'request' in a.split()[0]]
        self.assertEqual(len(request), 1)  # Native request-header or a request script is allowed.
        for filename in ('response.js', 'json.js'):
            self.assertEqual(sum(a.endswith('/js/BilibiliKelee/' + filename) for a in actions), 1)
        self.assertEqual(len(self.parsed['mocks']), 6)
        self.assertEqual(len(self.parsed['jq']), 2)
        self.assertEqual(len(set(self.parsed['rewrites'])), 22)

    def test_disabled_sponsor_rules_and_global_reject_are_absent(self):
        lines = '\n'.join(self.parsed['filters'] + self.parsed['rewrites'])
        for token in ('bsbsb.top', 'DmSegMobile', '${', 'SponsorBlock', 'sponsorBlock'):
            self.assertNotIn(token, lines)
        for pattern, action in self.rows:
            self.assertTrue(pattern.startswith('(?i)^https:'), pattern)
            self.assertFalse(re.search(pattern, 'https://unrelated.example/test'))
            self.assertNotIn(action.split()[0], ('reject', 'reject-200', 'reject-img'))

    def test_shared_profile_has_one_httpdns_and_zero_advertisers(self):
        groups = [group for group in S.PROFILES['Block_HTTPDNS.lpx']
                  if '哔哩哔哩' in group['apps']]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['rules'], [('DOMAIN', 'httpdns.bilivideo.com')])
        self.assertFalse([g for g in S.PROFILES['BlockAdvertisers.lpx']
                          if '哔哩哔哩' in g['apps']])

    def test_eight_filter_behavior_and_exact_host_boundaries(self):
        # Supplement identity is independently asserted above and in publication.
        filters = self.parsed['filters'] + ['host, httpdns.bilivideo.com, reject']
        self.assertCountEqual(filters, FILTERS)
        self.assertEqual(len(filters), 8)
        for host in ['api.biliapi.com', 'app.biliapi.com', 'api.biliapi.net',
                     'app.biliapi.net', 'httpdns.bilivideo.com']:
            for candidate in (host, host.upper()):
                self.assertEqual(policy(filters, candidate), 'reject')
            for candidate in ('child.' + host, host + '.evil.test', 'evil' + host):
                self.assertIsNone(policy(filters, candidate), candidate)
        for host in HOSTS + ['bilibili.com', 'biliapi.net', 'bilivideo.com',
                             'bsbsb.top', 'httpdns.baidu.com', 'dns.weixin.qq.com']:
            self.assertIsNone(policy(filters, host), host)

    def test_and_wildcards_require_keyword_and_strict_chat_suffix(self):
        filters = self.parsed['filters']
        for keyword in ('stun', 'tracker', 'p2p'):
            for host in [keyword + '.chat.bilibili.com',
                         'prefix-' + keyword + '-suffix.chat.bilibili.com',
                         'nested.' + keyword + '.chat.bilibili.com']:
                self.assertEqual(policy(filters, host), 'reject', host)
                self.assertEqual(policy(filters, host.upper()), 'reject', host)
            for host in [keyword + '.bilibili.com', keyword + 'chat.bilibili.com',
                         keyword + '.evilchat.bilibili.com', keyword + '.chat.bilibili.com.evil.test',
                         keyword + '.example.com', keyword + '.chatXbilibili.com']:
                self.assertIsNone(policy(filters, host), host)
        for host in ['chat.bilibili.com', 'live.chat.bilibili.com', 'chat.bilibili.com.stun']:
            self.assertIsNone(policy(filters, host), host)

    def test_all_eleven_jq_expressions_execute_with_independent_expected_results(self):
        item = lambda **kw: dict(card_goto='av', card_type='small_cover_v2', **kw)
        fixtures = [
            ('https://api.bilibili.com/x/pd-proxy/tracker?',
             {'data': {'a': ['real:1', 'real:2'], 'b': ['real:3']}},
             {'data': {'a': ['stun.chat.bilibili.com:3478'] * 2,
                       'b': ['stun.chat.bilibili.com:3478']}}),
            ('https://app.bilibili.com/x/v2/splash/show?',
             {'data': {'show': [1], 'event_list': [2], 'keep': 3}},
             {'data': {'show': [], 'event_list': [], 'keep': 3}}),
            ('https://app.bilibili.com/x/v2/feed/index?',
             {'data': {'items': [item(id=1), item(id=2, ad_info={}),
                                item(id=3, banner_item={}),
                                {'card_goto': 'live', 'card_type': 'small_cover_v2'},
                                {'card_goto': 'av', 'card_type': 'large_cover_single_v9', 'id': 4},
                                {'card_goto': 'av', 'card_type': 'large_cover_v1', 'id': 5},
                                {'card_goto': 'av', 'card_type': 'unknown'}]}},
             {'data': {'items': [item(id=1),
                                {'card_goto': 'av', 'card_type': 'large_cover_single_v9', 'id': 4},
                                {'card_goto': 'av', 'card_type': 'large_cover_v1', 'id': 5}]}}),
            ('https://api.bilibili.com/pgc/view/v2/app/season?',
             {'data': {'payment': {'ad': 1}, 'episodes': [1]}}, {'data': {'episodes': [1]}}),
            ('https://api.bilibili.com/pgc/page/channel?',
             {'data': {'modules': [{'type': 'TIP'}, {'type': 'NORMAL', 'keep': 1},
                                  {'type': 'BANNER', 'module_data': {'items': [
                                      {'url': 'https://www.bilibili.com/blackboard/era/ad'},
                                      {'url': 'https://www.bilibili.com/video/normal'}]}}]}},
             {'data': {'modules': [{'type': 'NORMAL', 'keep': 1},
                                  {'type': 'BANNER', 'module_data': {'items': [
                                      {'url': 'https://www.bilibili.com/video/normal'}]}}]}}),
            ('https://app.bilibili.com/x/v2/feed/index/story?',
             {'data': {'items': [{'id': 1, 'card_goto': 'av', 'story_cart_icon': {},
                                 'free_flow_toast': {}, 'image_infos': [], 'course_info': {}, 'game_info': {}},
                                {'card_goto': 'av', 'ad_info': {}},
                                *[{'card_goto': value} for value in
                                  ('vertical_ad_av', 'vertical_ad_live', 'vertical_ad_picture')]]}},
             {'data': {'items': [{'id': 1, 'card_goto': 'av'}]}}),
            ('https://api.live.bilibili.com/xlive/open-interface/v2/tracker/conf?',
             {'data': {'domains': ['wss://ad.example'], 'keep': 1}},
             {'data': {'domains': ['wss://tracker.chat.bilibili.com'], 'keep': 1}}),
            ('https://app.bilibili.com/x/resource/show/skin?',
             {'data': {'common_equip': {'ad': 1}, 'keep': 2}}, {'data': {'keep': 2}}),
            (MYINFO, {'data': {'vip': {'status': 0, 'keep': 2}}},
             {'data': {'vip': {'status': 1, 'type': 2, 'due_date': 9005270400000, 'role': 15, 'keep': 2}}}),
        ]
        reached = set()
        for url, value, expected in fixtures:
            with self.subTest(url=url):
                value['sentinel'] = expected['sentinel'] = {'unchanged': True}
                self.assertEqual(self.apply(url, value), expected)
                reached.add(self.expression(url))
        for url, name in [(TAB, 'tab_Bilibili_remove_ads.jq'),
                          (MINE, 'mine_Bilibili_remove_ads.jq')]:
            with self.subTest(upstream=name):
                value = {'code': 0, 'data': {'keep': 9, 'vip': {'status': 0},
                                           'sections_v2': [], 'ipad_sections': []}}
                original = (SNAPSHOT / name).read_text(encoding='utf-8')
                self.assertEqual(self.apply(url, value), self.jq(original, value))
                reached.add(self.expression(url))
        self.assertEqual(reached, {action.removeprefix('jsonjq-response-body ')[1:-1]
                                  for _, action in self.rows if action.startswith('jsonjq-response-body ')})
        self.assertEqual(len(reached), 11)

    def test_tab_equals_upstream_and_bottom_is_home_following_mine(self):
        original = (SNAPSHOT / 'tab_Bilibili_remove_ads.jq').read_text(encoding='utf-8')
        for data in ({}, {'tab': [1], 'top': [2], 'bottom': [3], 'keep': {'a': 1}}):
            value = {'code': 0, 'data': data, 'message': 'unchanged'}
            result = self.apply(TAB, value)
            self.assertEqual(result, self.jq(original, value))
            bottom = result['data']['bottom']
            self.assertEqual([item['name'] for item in bottom], ['首页', '动态', '我的'])
            self.assertEqual([item['uri'] for item in bottom],
                             ['bilibili://main/home/', 'bilibili://following/home/', 'bilibili://user_center/'])
            self.assertEqual([item['name'] for item in result['data']['tab']],
                             ['推荐', '热门', '动画', '影视', '直播'])

    def test_mine_phone_ipad_equal_upstream_and_preserve_account_fields(self):
        original = (SNAPSHOT / 'mine_Bilibili_remove_ads.jq').read_text(encoding='utf-8')
        data = dict(mid=123, coins=37, level=6, username='fixture',
                    vip={'status': 0, 'label': 'unchanged'}, sections_v2=[{'ad': 1}],
                    ipad_sections=[1], ipad_upper_sections=[2],
                    ipad_recommend_sections=[3], ipad_more_sections=[4],
                    answer={}, live_tip={}, vip_section={}, vip_section_v2={}, modular_vip_section={})
        for url in (MINE, MINE.replace('mine?', 'mine/ipad?')):
            value = {'code': 0, 'data': copy.deepcopy(data)}
            result = self.apply(url, value)
            self.assertEqual(result, self.jq(original, value))
            for field in ('mid', 'coins', 'level', 'username'):
                self.assertEqual(result['data'][field], data[field])
            for field in ('answer', 'live_tip', 'vip_section', 'vip_section_v2', 'modular_vip_section'):
                self.assertNotIn(field, result['data'])
            self.assertEqual(result['data']['vip_type'], 2)
            self.assertEqual([x['title'] for x in result['data']['sections_v2'][0]['items']],
                             ['离线缓存', '历史记录', '我的收藏', '稍后再看'])

    def test_vip_is_display_defaults_only_not_existing_entitlement_replacement(self):
        # Local JSON display fields are NOT a claim of server-side VIP access.
        for url in (MINE, MYINFO):
            for vip in (None, {}, {'status': 1, 'type': 1, 'due_date': 123},
                        {'status': 2, 'role': 4}, {'status': '0', 'type': 9}):
                with self.subTest(url=url, vip=vip):
                    value = {'data': {'vip': vip, 'server_entitlement': False}}
                    result = self.apply(url, value)['data']
                    self.assertEqual(result['vip'], vip)
                    self.assertFalse(result['server_entitlement'])
            empty = self.apply(url, {'data': {}})['data']
            self.assertIsNone(empty.get('vip'))
            self.assertNotIn('sections_v2', empty)
            self.assertNotIn('ipad_sections', empty)

    def test_feed_and_story_absent_items_and_empty_arrays(self):
        for suffix in ('index', 'index/story'):
            url = 'https://app.bilibili.com/x/v2/feed/' + suffix + '?fixture=1'
            for value in ({'data': {'keep': 1}}, {'data': {'items': None}}, {'data': {'items': []}}):
                self.assertEqual(self.apply(url, value), value)

    def test_six_mock_routes_preserve_source_bytes_status_and_content_type(self):
        sources = source_mocks()
        self.assertEqual(len(sources), 6)
        results = self.mock(MOCK_URLS)
        for index, (url, result) in enumerate(zip(MOCK_URLS, results)):
            with self.subTest(route=index, url=url):
                matches = [args for pattern, args in sources if re.search(pattern, url)]
                self.assertEqual(len(matches), 1)
                args = matches[0]
                self.assertEqual(args[0], 'text')
                self.assertEqual(args[2], 200)
                response = result['response']
                self.assertEqual(response['status'], 'HTTP/1.1 200 OK')
                headers = {key.lower(): value for key, value in response['headers'].items()}
                self.assertEqual(headers['content-type'], 'text/plain; charset=utf-8')
                binary = len(args) == 4 and args[3] is True
                if binary:
                    self.assertNotIn('body', response)
                    self.assertEqual(headers.get('grpc-status'), '0')
                    self.assertEqual(result['base64'], args[1])
                    self.assertEqual(bytes(result['bytes']), base64.b64decode(args[1], validate=True))
                else:
                    self.assertNotIn('bodyBytes', response)
                    self.assertNotIn('grpc-status', headers)
                    self.assertEqual(response['body'].encode('utf-8'), args[1].encode('utf-8'))
                    self.assertEqual(json.loads(response['body']), json.loads(args[1]))

    def test_three_binary_mocks_are_complete_five_byte_grpc_frames(self):
        expected_lengths = (19, 33, 0)
        for result, expected_length in zip(self.mock(MOCK_URLS[3:]), expected_lengths):
            frame = bytes(result['bytes'])
            self.assertEqual(frame[0], 0, 'compression flag must remain uncompressed')
            declared = int.from_bytes(frame[1:5], 'big')
            self.assertEqual(declared, expected_length)
            self.assertEqual(len(frame), 5 + declared, 'no missing or double framing')
        self.assertEqual(self.mock([MOCK_URLS[-1]])[0]['bytes'], [0, 0, 0, 0, 0])

    def test_mock_multi_endpoint_alternatives_and_case_insensitivity(self):
        alternatives = [
            'https://grpc.biliapi.net/bilibili.app.viewunite.v1.View/PlayPause',
            'https://grpc.biliapi.net/bilibili.app.viewunite.v1.View/ViewEndPage',
        ]
        for result in self.mock(alternatives + [url.upper() for url in MOCK_URLS]):
            self.assertEqual(result['response']['status'], 'HTTP/1.1 200 OK')
        for host in ('api.bilibili.com', 'app.bilibili.com'):
            for path in ('/x/resource/top/activity', '/x/resource/patch/tab',
                         '/x/resource/patch/tab/v2', '/x/v2/search/square', '/x/vip/ads/materials'):
                result = self.mock(['https://' + host + path + '?fixture=1'])[0]
                self.assertEqual(json.loads(result['response']['body']),
                                 {'code': -404, 'message': '-404', 'ttl': 1, 'data': None})

    def test_unknown_mock_path_is_done_empty_without_publishing_catch_all(self):
        unknown = ['https://unrelated.example/path',
                   'https://app.bilibili.com/x/v2/splash/list',
                   'https://app.bilibili.com/x/v2/splash/list/other?',
                   MOCK_URLS[3] + '?fixture=1', MOCK_URLS[3] + '/other',
                   MOCK_URLS[0].replace('app.bilibili.com', 'app.bilibili.com.evil.test'),
                   MOCK_URLS[0].replace('https:', 'http:')]
        for result in self.mock(unknown):
            self.assertEqual(result['response'], {})
        for url in unknown:
            self.assertFalse([line for line in self.parsed['rewrites']
                              if ' script-echo-response ' in line and
                              re.search(line.split(' url ', 1)[0], url)], url)

    def test_all_output_regexes_preserve_original_source_scope(self):
        expected = []
        for line in SOURCE.splitlines():
            match = re.match(r'(request|response) if \$\{url\} ~= /(.*)/i then ', line)
            if not match or 'response.header.add(' in line or 'enable=${sponsorBlock}' in line:
                continue
            expected.append('(?i)' + match[2])
        self.assertEqual([pattern for pattern, _ in self.rows], expected)
        self.assertEqual(len(expected), 22)

    def test_rejects_have_only_two_known_endpoints_and_no_catch_all(self):
        targets = [
            'https://line3-h5-mobile-api.biligame.com/game/live/large_card_material?fixture=1',
            'https://api.live.bilibili.com/xlive/e-commerce-interface/v1/ecommerce-user/get_shopping_info?fixture=1',
        ]
        rejects = [pattern for pattern, action in self.rows if action == 'reject-dict']
        self.assertEqual(len(rejects), 2)
        for url in targets:
            self.assertEqual(sum(bool(re.search(pattern, url)) for pattern in rejects), 1)
            self.assertEqual(sum(bool(re.search(pattern, url.upper())) for pattern in rejects), 1)
            parts = urlsplit(url)
            for bad in [url.replace('https:', 'http:'), url.split('?')[0],
                        url.replace(parts.netloc, parts.netloc + '.evil.test'),
                        url.replace('?', '/other?')]:
                self.assertFalse(any(re.search(pattern, bad) for pattern in rejects), bad)
        for url in MOCK_URLS + [TAB, MINE, MYINFO, 'https://api.bilibili.com/x/web-interface/view?bvid=test']:
            self.assertFalse(any(re.search(pattern, url) for pattern in rejects), url)

    def test_parse_guards_reject_changed_source_shapes(self):
        mutations = {
            'unknown-filter': ('DOMAIN, api.biliapi.com, REJECT', 'DOMAIN-SUFFIX, api.biliapi.com, REJECT'),
            'unknown-policy': ('DOMAIN, api.biliapi.com, REJECT', 'DOMAIN, api.biliapi.com, DIRECT'),
            'changed-and': ('(DOMAIN-KEYWORD, p2p)', '(DOMAIN-KEYWORD, unknown)'),
            'sponsor-host': ('DOMAIN, bsbsb.top, PROXY', ''),
            'sponsor-script': ('enable=${sponsorBlock}', 'enable=false'),
            'unknown-jq-origin': ('https://kelee.one/Resource/JQLang/Bilibili/tab_',
                                  'https://evil.example/Resource/JQLang/Bilibili/tab_'),
            'unknown-jq-file': ('tab_Bilibili_remove_ads.jq', 'new_Bilibili_remove_ads.jq'),
            'mock-status': ('"AAAAAAA=", 200, true', '"AAAAAAA=", 201, true'),
            'bad-frame-length': ('AAAAAAA=', 'AAAAAAE='),
            'bad-frame-compression': ('AAAAAAA=', 'AQAAAAA='),
            'bad-base64': ('AAAAAAA=', '!!!'),
            'grpc-header': ('response.header.add("grpc-status", "0")', 'response.header.add("grpc-status", "1")'),
            'unknown-script': ('Bilibili_json_kokoryh.js', 'unknown.js'),
            'optimization-option': ('enable=${optimizeRequest}', 'enable=false'),
            'mitm-count': ('hostname=grpc.biliapi.net, ', 'hostname='),
        }
        for label, (old, new) in mutations.items():
            with self.subTest(mutation=label):
                self.assertIn(old, SOURCE)
                with self.assertRaises(ValueError):
                    K.parse_rules(SOURCE.replace(old, new, 1), RAW)

    def test_parse_guards_detect_missing_or_duplicated_action_counts(self):
        tokens = ('response.body.mock(', 'response.header.add(',
                  'response.json.jq("del(.data.payment)")', 'tag="移除直播间广告"')
        for token in tokens:
            line = next(line for line in SOURCE.splitlines() if token in line)
            for replacement in ('', line + '\n' + line):
                with self.subTest(action=token, duplicate=bool(replacement)):
                    with self.assertRaises(ValueError):
                        K.parse_rules(SOURCE.replace(line, replacement, 1), RAW)

    def test_parse_guards_do_not_silently_expand_filter_scope(self):
        for changed in [SOURCE.replace('[Rule]', '[Rule]\nDOMAIN, unrelated.example, REJECT', 1),
                        SOURCE.replace('DOMAIN, api.biliapi.com, REJECT',
                                       'DOMAIN, unrelated.example, REJECT', 1)]:
            with self.subTest(change=changed.split('[Rule]', 1)[1].split('[Rewrite]', 1)[0]):
                with self.assertRaises(ValueError, msg='Pinned Bilibili filter inventory must fail closed'):
                    K.parse_rules(changed, RAW)

    def test_publication_eight_inline_filters_and_22_source_rewrites(self):
        lines = self.published()
        filters = [line for line in lines if ' url ' not in line and not line.startswith('hostname')]
        self.assertCountEqual(filters, FILTERS)
        self.assertEqual(len(filters), 8)
        self.assertEqual([line for line in lines if ' url ' in line], self.parsed['rewrites'])
        hostlines = [line for line in lines if line.startswith('hostname')]
        self.assertEqual(len(hostlines), 1)
        self.assertCountEqual([x.strip() for x in hostlines[0].split('=', 1)[1].split(',')], HOSTS)
        self.assertEqual(len(lines), 8 + 22 + 1)

    def test_publication_manifest_fixed_settings_one_resource_and_provenance(self):
        manifest = json.loads((REPO / 'build-info.json').read_text(encoding='utf-8'))
        rows = [row for row in manifest['rows'] if row.get('slug', '').startswith('bilibili')]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        expected = dict(slug='bilibili', snippet='snippets/bilibili.snippet',
                        rewrite=22, filter=8, list=None, has_list=False,
                        embedded_filter=True, settings=SETTINGS,
                        source='https://kelee.one/Tool/Loon/Lpx/Bilibili_remove_ads.lpx',
                        snapshot='tools/upstream/bilibili-kelee/Bilibili_remove_ads.lpx')
        for key, value in expected.items():
            with self.subTest(field=key):
                self.assertEqual(row.get(key), value)
        self.assertEqual(row.get('upstream_sha256'), hashlib.sha256(SOURCE.encode()).hexdigest())
        self.assertEqual(row.get('jq_sources'), self.parsed['jq'])
        self.assertFalse(any('BlockAdvertisers' in item['source'] for item in row.get('supplements', [])))
        self.assertFalse(any(path.startswith('js/Bilibili/') for path in manifest['assets']))

    def test_publication_has_one_parameter_free_config_entry_and_no_old_list(self):
        remote = active((REPO / 'config/rewrite_remote.conf').read_text())
        entries = [line for line in remote if re.search(r'/snippets/bilibili[^/,]*\.snippet', line)]
        self.assertEqual(len(entries), 1)
        parts = [item.strip() for item in entries[0].split(',')]
        self.assertEqual(parts[0], RAW + '/snippets/bilibili.snippet')
        self.assertIn('opt-parser=false', parts)
        self.assertIn('enabled=true', parts)
        filters = active((REPO / 'config/filter_remote.conf').read_text())
        self.assertFalse(any('bilibili' in line.lower() for line in filters))
        self.assertEqual(sorted(path.name for path in (REPO / 'snippets').glob('bilibili*.snippet')),
                         ['bilibili.snippet'])
        self.assertFalse(list((REPO / 'lists').glob('bilibili*.list')))
        for line in self.published():
            self.assertNotIn('${', line)
            self.assertNotIn('$argument', line)
            self.assertNotIn('script-argument', line)
            if ' url script-' in line:
                script_url = line.rsplit(' ', 1)[1]
                self.assertFalse(urlsplit(script_url).query)
                self.assertFalse(urlsplit(script_url).fragment)
                self.assertTrue(script_url.startswith(RAW + '/js/BilibiliKelee/'))

    def test_publication_has_no_legacy_script_references_or_global_blocking(self):
        forbidden = ('/js/Bilibili/', 'bilibili_json.js', 'bilibili.protobuf.js',
                     'bilibili-navigation.js', 'bilibili-enhance.snippet',
                     'bsbsb.top', 'DmSegMobile', 'SponsorBlock', 'sponsorBlock')
        files = [REPO / 'snippets/bilibili.snippet',
                 REPO / 'config/rewrite_remote.conf', REPO / 'config/filter_remote.conf']
        for path in files:
            text = '\n'.join(active(path.read_text(encoding='utf-8')))
            for token in forbidden:
                with self.subTest(file=path.name, token=token):
                    self.assertNotIn(token, text)
        self.assertEqual(len(rewrites(self.published())), 22)

    def test_publication_shared_scope_reports_no_advertisers_for_bilibili(self):
        scope = json.loads((REPO / 'config/shared-scope.json').read_text(encoding='utf-8'))
        def bili(group):
            return 'bilibili' in group.get('targets', []) or '哔哩哔哩' in group.get('apps', [])
        self.assertFalse([g for g in scope['BlockAdvertisers.lpx']['groups'] if bili(g)])
        groups = [g for g in scope['Block_HTTPDNS.lpx']['groups'] if bili(g)]
        self.assertEqual(len(groups), 1)
        self.assertEqual([entry['rule'] for entry in groups[0]['entries']],
                         ['DOMAIN, httpdns.bilivideo.com, REJECT'])


if __name__ == '__main__':
    unittest.main()
