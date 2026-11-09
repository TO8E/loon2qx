"""Offline ChinaUnicom regressions; jq is executed, not emulated.

Run: python3 -m unittest discover -s tests -p 'test_chinaunicom.py' -v
Only repository snapshots/public artifacts are read; outputs use temporary dirs.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import build_qx_repo as B
import convert_lpx_to_qx as C

FILENAME = 'ChinaUnicom.lpx'
SOURCE = 'https://loon.103516.xyz/Plugin/ChinaUnicom.lpx'
SOURCE_SHA256 = '3ec16886d2c3f5ad337d673b112b7d64220f896c611340a948c7e5676e3f51da'
SNAPSHOT = REPO / 'tools/upstream' / FILENAME
SNIPPET = 'snippets/chinaunicom.snippet'
FILTER = 'host, m1.ad.10010.com, reject'
HOSTS = ['m.client.10010.com', 'img.client.10010.com']
ORIGIN = 'https://m.client.10010.com'
DISCOVER = '/search_service/tyfbSearch/searchDiscoverListExpress'
SCROLL = '/search_service/search/searchScrollWord'
NAV = '/clientIndex/v1/api/navHome'
FUSION = '/clientIndex/homefusion/fuInter'
WALLET = '/clientMyPage/v1/api/myWallet'


def active_lines(text):
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith(('#', ';'))]


def rewrite_rows(lines):
    """Parse QX output independently, keeping its first-match ordering."""
    return [tuple(line.split(' url ', 1)) for line in lines if ' url ' in line]


class ChinaUnicomTests(unittest.TestCase):
    def converted(self):
        return C.convert('中国联通去广告', FILENAME,
                         text=SNAPSHOT.read_text(encoding='utf-8'))

    def published(self):
        return active_lines((REPO / SNIPPET).read_text(encoding='utf-8'))

    def rules(self):
        return rewrite_rows(self.published())

    def apply_first(self, url, value, rules=None):
        """QX applies the FIRST matching rule, not every matching response."""
        for pattern, action in self.rules() if rules is None else rules:
            if re.search(pattern, url):
                prefix = 'jsonjq-response-body '
                self.assertTrue(action.startswith(prefix), action)
                expression = action[len(prefix):]
                self.assertTrue(expression.startswith("'") and expression.endswith("'"))
                process = subprocess.run(
                    ['jq', '-c', expression[1:-1]], input=json.dumps(value),
                    text=True, capture_output=True, timeout=10)
                self.assertEqual(process.returncode, 0, process.stderr)
                outputs = process.stdout.splitlines()
                self.assertEqual(len(outputs), 1, process.stdout)
                return json.loads(outputs[0])
        self.fail('No matching response rewrite: ' + url)

    def assert_row(self, row):
        expected = dict(name='中国联通去广告', fname=FILENAME, slug='chinaunicom',
                        kind='snippets', snippet=SNIPPET, rewrite=9, filter=1,
                        has_list=False, list=None, source=SOURCE, embedded_filter=True)
        for key, value in expected.items():
            with self.subTest(field=key):
                self.assertIn(key, row)
                self.assertEqual(row[key], value)
        self.assertCountEqual(row['hosts'], HOSTS)

    def test_source_snapshot_hash_and_external_registration(self):
        self.assertEqual(hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(), SOURCE_SHA256)
        self.assertIn(FILENAME, B.EXTERNAL_PLUGINS)
        self.assertEqual(B.EXTERNAL_PLUGINS[FILENAME]['source'], SOURCE)

    def test_conversion_has_native_rules_without_scripts_or_tasks(self):
        result = self.converted()
        self.assertEqual(result['filters'], [FILTER])
        self.assertCountEqual(result['hosts'], HOSTS)
        self.assertEqual(result['tasks'], [])
        self.assertEqual(result['jq'], {})
        rows = result['rewrites']
        self.assertEqual(len(rows), 9)
        self.assertCountEqual([row[2][0] for row in rows],
                              ['reject'] * 3 + ['jsonjq-response-body'] * 6)
        self.assertEqual(sum(row[1] == 'response' for row in rows), 6)
        for _, stage, (action, arg), _ in rows:
            if action == 'reject':
                self.assertEqual((stage, arg), ('request', None))
            else:
                self.assertEqual(stage, 'response')

    def test_response_order_matches_source_not_all_nine_rule_order(self):
        # Rejects may move before responses; ONLY response order is significant.
        source_rows = []
        for line in SNAPSHOT.read_text(encoding='utf-8').splitlines():
            match = re.fullmatch(
                r'response if \$\{url\} ~= /(.*)/i then response\.json\.jq\((.*)\)', line)
            if match:
                source_rows.append(('(?i)' + match[1],
                                    "jsonjq-response-body '" + json.loads(match[2]) + "'"))
        self.assertEqual(len(source_rows), 6)
        # Loon executes the later broad .data={} after the specific wallet rule.
        # QX's first match must already yield that final value; all other actions
        # and all regexes/order remain exactly as in the source.
        self.assertEqual(source_rows[4][1], "jsonjq-response-body '.data.payShowFlag = false'")
        source_rows[4] = (source_rows[4][0], "jsonjq-response-body '.data={}'")
        converted_rows = rewrite_rows([C.fmt_rewrite(row)[0]
                                       for row in self.converted()['rewrites']])
        for rows in (converted_rows, self.rules()):
            responses = [row for row in rows if row[1].startswith('jsonjq-response-body ')]
            self.assertEqual(responses, source_rows)

    def test_published_combines_exact_host_filter_and_converted_rewrites(self):
        lines = self.published()
        result = self.converted()
        expected = [C.fmt_rewrite(row)[0] for row in result['rewrites']]
        rewrites = [line for line in lines if ' url ' in line]
        self.assertCountEqual(rewrites, expected)
        self.assertEqual(len(rewrites), len(set(rewrites)))
        self.assertEqual(lines.count(FILTER), 1)
        hostlines = [line for line in lines if line.startswith('hostname = ')]
        self.assertEqual(len(hostlines), 1)
        self.assertCountEqual([host.strip() for host in hostlines[0].split('=', 1)[1].split(',')], HOSTS)
        self.assertEqual(len(lines), 11)  # hostname + one filter + nine rewrites
        self.assertFalse((REPO / 'lists/chinaunicom.list').exists())
        self.assertFalse(any('script-' in action for _, action in self.rules()))

    def test_emit_is_offline_snapshot_based_and_byte_identical_to_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = {}
            # A fallback to a private/local mirror must not satisfy this test.
            with patch.object(C, 'SRC', str(root / 'missing-source')), \
                    patch.object(C, 'MIRROR', str(root / 'missing-mirror')):
                row, rules, filters, tasks = B.emit(
                    root / 'out', '中国联通去广告', FILENAME, 'chinaunicom',
                    'snippets', B.RAW, assets)
            self.assert_row(row)
            self.assertEqual(len(rules), 9)
            self.assertEqual(filters, [FILTER])
            self.assertEqual(tasks, [])
            self.assertEqual(assets, {})
            emitted = root / 'out' / SNIPPET
            self.assertEqual(emitted.read_bytes(), (REPO / SNIPPET).read_bytes())
            self.assertIn('# Source: ' + SOURCE, emitted.read_text(encoding='utf-8'))
            self.assertFalse((root / 'out/lists/chinaunicom.list').exists())
            self.assertFalse(list((root / 'out').rglob('*.js')))
            self.assertCountEqual(rules, [line for line in active_lines(emitted.read_text())
                                          if ' url ' in line])

    def test_build_manifest_has_one_merged_resource(self):
        info = json.loads((REPO / 'build-info.json').read_text(encoding='utf-8'))
        rows = [row for row in info['rows'] if row.get('slug') == 'chinaunicom'
                or row.get('fname') == FILENAME or row.get('snippet') == SNIPPET]
        self.assertEqual(len(rows), 1)
        self.assert_row(rows[0])
        for host in HOSTS:
            self.assertIn(host, info['hosts'])

    def test_remote_subscription_is_once_and_not_a_filter_subscription(self):
        rewrites = active_lines((REPO / 'config/rewrite_remote.conf').read_text())
        entries = [line for line in rewrites if '/snippets/chinaunicom.snippet' in line]
        self.assertEqual(len(entries), 1)
        parts = [part.strip() for part in entries[0].split(',')]
        self.assertEqual(parts[0], B.RAW + '/' + SNIPPET)
        self.assertIn('enabled=true', parts)
        self.assertIn('opt-parser=false', parts)
        filters = active_lines((REPO / 'config/filter_remote.conf').read_text())
        self.assertFalse(any('chinaunicom' in line.casefold() for line in filters))

    def test_domain_filter_is_exact_not_parent_suffix_or_keyword(self):
        filters = [line for line in self.published()
                   if ' url ' not in line and not line.startswith('hostname = ')]
        parsed = [tuple(part.strip() for part in line.split(',')) for line in filters]
        self.assertEqual(parsed, [('host', 'm1.ad.10010.com', 'reject')])

        def policy(host):
            return next((action for kind, value, action in parsed
                         if kind == 'host' and host.casefold() == value.casefold()), None)

        self.assertEqual(policy('m1.ad.10010.com'), 'reject')
        self.assertEqual(policy('M1.AD.10010.COM'), 'reject')
        for host in ['ad.10010.com', '10010.com', 'm2.ad.10010.com',
                     'child.m1.ad.10010.com', 'm1.ad.10010.com.evil.test',
                     'xm1.ad.10010.com', *HOSTS]:
            with self.subTest(host=host):
                self.assertIsNone(policy(host))

    def test_three_reject404_rules_cover_http_https_and_case(self):
        rejects = [(pattern, action) for pattern, action in self.rules()
                   if action.startswith('reject')]
        self.assertEqual(len(rejects), 3)
        self.assertEqual([action for _, action in rejects], ['reject'] * 3)
        targets = [
            'm.client.10010.com/mobileserviceimportant/customer/querySmartServicekhd.htm',
            'm.client.10010.com/clientIndex/api/v1/index/queryIndexExclusiveOffers',
            'img.client.10010.com/homejingxuan12/js/pubuliu',
            'img.client.10010.com/homejingxuan12/js/1homeView',
        ]
        reached = set()
        for target in targets:
            for scheme in ('http://', 'https://'):
                for url in (scheme + target + '?fixture=1', (scheme + target).upper()):
                    with self.subTest(url=url):
                        matches = [pattern for pattern, _ in rejects if re.search(pattern, url)]
                        self.assertEqual(len(matches), 1)
                        reached.update(matches)
        self.assertEqual(reached, {pattern for pattern, _ in rejects})
        for url in [ORIGIN + DISCOVER, ORIGIN + WALLET,
                    ORIGIN + '/mobileserviceimportant/customer/normal.htm',
                    ORIGIN + '/clientIndex/api/v2/index/queryIndexExclusiveOffers',
                    'https://img.client.10010.com/homejingxuan12/js/normal',
                    ORIGIN + '/homejingxuan12/js/pubuliu']:
            with self.subTest(url=url):
                self.assertFalse(any(re.search(pattern, url) for pattern, _ in rejects))

    def test_all_patterns_are_case_insensitive_and_domain_anchored(self):
        rules = self.rules()
        for pattern, _ in rules:
            self.assertTrue(pattern.startswith('(?i)^'), pattern)
        paths = [DISCOVER, SCROLL, NAV, FUSION, WALLET,
                 '/clientMyPage/v2/api/myPoints',
                 '/mobileserviceimportant/customer/querySmartServicekhd.htm',
                 '/clientIndex/api/v1/index/queryIndexExclusiveOffers']
        urls = [ORIGIN + path for path in paths]
        urls.append('https://img.client.10010.com/homejingxuan12/js/pubuliu')
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(any(re.search(pattern, url.upper()) for pattern, _ in rules))
                for wrong in (url.replace('.10010.com/', '.10010.com.evil.test/'),
                              url.replace('.10010.com/', 'x10010.com/'),
                              'https://example.test/?next=' + url):
                    self.assertFalse(any(re.search(pattern, wrong) for pattern, _ in rules), wrong)

    def test_https_only_responses_do_not_match_http(self):
        responses = [(pattern, action) for pattern, action in self.rules()
                     if action.startswith('jsonjq-response-body ')]
        self.assertEqual(len(responses), 6)
        https_only = responses[:5]
        for path in (DISCOVER, SCROLL, NAV, FUSION, WALLET):
            with self.subTest(path=path):
                self.assertEqual(sum(bool(re.search(pattern, ORIGIN + path))
                                     for pattern, _ in https_only), 1)
                for url in ('http://m.client.10010.com' + path,
                            ('http://m.client.10010.com' + path).upper()):
                    self.assertFalse(any(re.search(pattern, url) for pattern, _ in https_only))
        # HTTP v1 wallet intentionally remains covered by the broader sixth rule.
        self.assertEqual(sum(bool(re.search(pattern, 'http://m.client.10010.com' + WALLET))
                             for pattern, _ in responses), 1)

    def test_search_discover_clears_only_data_array(self):
        body = {'data': [{'title': '推广'}, 'ad'], 'code': '0000',
                'keep': {'data': ['nested']}, 'message': 'ok'}
        expected = copy.deepcopy(body)
        expected['data'] = []
        self.assertEqual(self.apply_first(ORIGIN + DISCOVER + '?fixture=1', body), expected)

    def test_search_scroll_clears_only_numeric_top_level_key(self):
        body = {'113000004': [{'text': '推广'}], '113000005': ['keep'],
                'data': {'113000004': ['nested']}, 'code': '0000'}
        expected = copy.deepcopy(body)
        expected['113000004'] = []
        self.assertEqual(self.apply_first((ORIGIN + SCROLL).upper(), body), expected)

    def test_nav_home_filters_four_names_and_keeps_normal_items_unchanged(self):
        normal = [{'menuName': '话费充值', 'id': 1, 'extra': {'keep': True}},
                  {'menuName': '签到入口', 'id': 2}, {'menuName': 'VOWIFI', 'id': 3},
                  {'menuName': ' ', 'id': 4}, {'id': 5}, {'menuName': None, 'id': 6}]
        removed = [{'menuName': name, 'id': 'ad-' + str(index)}
                   for index, name in enumerate(('通通', 'vowifi', '签到', ''))]
        items = [normal[0], removed[0], normal[1], removed[1], removed[2],
                 *normal[2:], removed[3]]
        body = {'datas': {'homeTopMenuItems': items, 'keep': {'menuName': '通通'}},
                'data': ['untouched'], 'code': '0000'}
        expected = copy.deepcopy(body)
        expected['datas']['homeTopMenuItems'] = normal
        self.assertEqual(self.apply_first(ORIGIN + NAV, body), expected)
        empty = {'datas': {'homeTopMenuItems': [], 'keep': 1}, 'status': 'ok'}
        self.assertEqual(self.apply_first(ORIGIN + NAV, empty), empty)

    def test_fu_inter_deletes_literal_dotted_keys_not_nested_names(self):
        keys = ('HomeFusion.backGroundQuery', 'HomeFusion.fuchuangAdv_A8',
                'HomeFusion.bottomLabel')
        nested = {'backGroundQuery': {'keep': 1}, 'fuchuangAdv_A8': [2],
                  'bottomLabel': 'keep'}
        body = {key: {'ad': True} for key in keys}
        body.update(HomeFusion=nested, data={key: ['nested'] for key in keys},
                    code='0000', **{'HomeFusion.other': 'keep',
                                   'HomeFusion.backGroundQueryExtra': 'keep'})
        expected = {key: value for key, value in body.items() if key not in keys}
        self.assertEqual(self.apply_first(ORIGIN + FUSION, body), expected)

    def test_https_v1_wallet_first_match_equals_loon_sequential_final_value(self):
        body = {'data': {'payShowFlag': True, 'balance': '123.45',
                         'cards': [{'id': 1}], 'nested': {'payShowFlag': True}},
                'payShowFlag': True, 'code': '0000'}
        expected = dict(body, data={})
        original = []
        for line in SNAPSHOT.read_text().splitlines():
            match = re.fullmatch(
                r'response if \$\{url\} ~= /(.*)/i then response\.json\.jq\((.*)\)', line)
            if match and re.search('(?i)' + match[1], ORIGIN + WALLET):
                original.append(json.loads(match[2]))
        self.assertEqual(original, ['.data.payShowFlag = false', '.data={}'])
        # Simulate Loon's documented execution, including skip-on-action-error.
        for data in (body['data'], None, [], 'unexpected', 7):
            value = dict(body, data=data)
            sequential = value
            for expression in original:
                result = subprocess.run(['jq', '-c', expression], input=json.dumps(sequential),
                                        text=True, capture_output=True, timeout=10)
                if result.returncode == 0:
                    sequential = json.loads(result.stdout)
            self.assertEqual(sequential, expected)
            for url in (ORIGIN + WALLET, (ORIGIN + WALLET).upper() + '?fixture=1'):
                with self.subTest(url=url, data=data):
                    matches = [(pattern, action) for pattern, action in self.rules()
                               if re.search(pattern, url)]
                    self.assertEqual(len(matches), 2)
                    self.assertEqual(self.apply_first(url, value), sequential)
                    self.assertEqual(self.apply_first(url, value, matches[1:]), sequential)

    def test_changed_upstream_wallet_overlap_fails_instead_of_silently_changing_behavior(self):
        source = SNAPSHOT.read_text(encoding='utf-8')
        for changed in (source.replace('.data={}', '.data=[]'),
                        source.replace('.data.payShowFlag = false', '.data.payShowFlag = true')):
            with self.subTest(source=changed):
                with self.assertRaisesRegex(ValueError, 'wallet overlap changed'):
                    C.convert('中国联通去广告', FILENAME, text=changed)

    def test_generic_response_clears_data_for_wallet_points_ringtone_and_banners(self):
        body = {'data': {'payShowFlag': True, 'ad': [1], 'balance': 8},
                'code': '0000', 'keep': {'data': ['nested'], 'value': False}}
        expected = dict(body, data={})
        endpoints = ('myWallet', 'myPoints', 'myColorfulRingtone', 'newUserInfo', 'getDeviceInfo')
        for endpoint in endpoints:
            for scheme in ('http', 'https'):
                for version in (1, 2, 9):
                    # Includes HTTPS v1: its earlier QX rule incorporates the
                    # later Loon data-clearing action rather than only the flag.
                    url = f'{scheme}://m.client.10010.com/clientMyPage/v{version}/api/{endpoint}'
                    with self.subTest(url=url):
                        self.assertEqual(self.apply_first(url + '?fixture=1', body), expected)
        self.assertEqual(self.apply_first(
            'HTTP://M.CLIENT.10010.COM/CLIENTMYPAGE/V1/API/MYWALLET', body), expected)
        for path in ('/clientMyPage/v10/api/myPoints', '/clientMyPage/vx/api/myPoints',
                     '/clientMyPage/v2/api/normal'):
            with self.subTest(path=path):
                self.assertFalse(any(re.search(pattern, ORIGIN + path)
                                     for pattern, _ in self.rules()))


if __name__ == '__main__':
    unittest.main()
