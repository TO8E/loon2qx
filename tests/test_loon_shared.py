import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_loon_shared as B


def matches(rules, url):
    """Small reference evaluator for the three published native rule forms.

    Exercises scope boundaries, not the Loon runtime or live app traffic.
    """
    host = (urlsplit(url).hostname or '').lower()
    for rule in rules:
        if rule.startswith('DOMAIN, '):
            if host == rule.split(',')[1].strip():
                return True
        elif rule.startswith('URL-REGEX, '):
            if re.search(rule.split('"')[1], url):
                return True
        elif rule.startswith('AND, '):
            keyword = re.search(r'\(DOMAIN-KEYWORD, ([^)]+)\)', rule)[1]
            suffix = re.search(r'\(DOMAIN-SUFFIX, ([^)]+)\)', rule)[1]
            if keyword in host and (host == suffix or host.endswith('.' + suffix)):
                return True
        else:
            raise AssertionError(f'Unexpected published rule: {rule}')
    return False


class LoonSharedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = json.loads((ROOT / 'loon/profile.json').read_text())
        cls.snapshots = {p['file']: (ROOT / 'loon/upstream' / p['file']).read_bytes()
                         for p in cls.profile['plugins']}
        cls.artifacts = B.build_artifacts(cls.profile, cls.snapshots)
        cls.rules = {}
        for name in cls.snapshots:
            text = cls.artifacts['plugins/' + name].decode()
            cls.rules[name] = [line for _, line in B.source_sections(text)['rule']]
        cls.all_rules = sum(cls.rules.values(), [])

    def test_published_outputs_match_reviewed_sources(self):
        for path, expected in self.artifacts.items():
            with self.subTest(path=path):
                self.assertEqual((ROOT / 'loon' / path).read_bytes(), expected)
        self.assertEqual(len(self.rules['Block_HTTPDNS.lpx']), 7)
        self.assertEqual(len(self.rules['BlockAdvertisers.lpx']), 4)
        for plugin in self.profile['plugins']:
            source = self.snapshots[plugin['file']].decode()
            result = self.artifacts['plugins/' + plugin['file']].decode()
            self.assertEqual(set(B.source_sections(result)), {'rule'})
            for key in ('author', 'loon_version', 'icon'):
                self.assertIn(re.search(r'^#!' + key + r'=.*$', source, re.M)[0], result)
        report = json.loads(self.artifacts['build-info.json'])
        self.assertEqual([p['upstream_rule_count'] for p in report['plugins']], [162, 346])
        self.assertEqual([p['removed_rewrite_count'] for p in report['plugins']], [6, 4])

    def test_exact_domains_match_without_expanding_subdomains(self):
        domains = ['httpdns.bilivideo.com', 'httpdns.danuoyi.tbcache.com',
                   'tmeadcomm.y.qq.com', 'stat.y.qq.com', 'stat6.y.qq.com']
        for domain in domains:
            with self.subTest(domain=domain):
                self.assertTrue(matches(self.all_rules, 'https://' + domain + '/'))
                self.assertTrue(matches(self.all_rules, 'https://' + domain.upper() + '/'))
                self.assertFalse(matches(self.all_rules, 'https://other.' + domain + '/'))
                self.assertFalse(matches(self.all_rules, 'https://' + domain + '.example.org/'))

    def test_taobao_dispatch_only_targets_five_original_http_urls(self):
        for host in ['amdc.m.taobao.com', '47.246.103.9', '47.246.103.10',
                     '59.82.113.10', '59.82.113.219']:
            with self.subTest(host=host):
                self.assertTrue(matches(self.all_rules, f'http://{host}/amdc/mobileDispatch?x=1'))
                for url in [f'https://{host}/amdc/mobileDispatch', f'http://{host}/',
                            f'http://{host}/other', f'http://{host}:8080/amdc/mobileDispatch',
                            f'http://{host}.example.org/amdc/mobileDispatch']:
                    self.assertFalse(matches(self.all_rules, url), url)
        self.assertFalse(matches(self.all_rules, 'http://47.246.103.11/amdc/mobileDispatch'))

    def test_taobao_adash_requires_both_keyword_and_domain_boundary(self):
        for host in ['h-adashx.ut.taobao.com', 'adash.ut.taobao.com', 'x.adash.ut.taobao.com']:
            self.assertTrue(matches(self.all_rules, 'https://' + host + '/'), host)
        for host in ['ut.taobao.com', 'api.ut.taobao.com', 'adash.taobao.com',
                     'adash.evilut.taobao.com', 'adash.ut.taobao.com.example.org',
                     'adash.snssdk.com', 'adash.man.aliyuncs.com']:
            self.assertFalse(matches(self.all_rules, 'https://' + host + '/'), host)

    def test_unrelated_httpdns_and_ordinary_ip_requests_are_not_blocked(self):
        for url in ['http://119.29.29.90/d?dn=example.org',
                    'http://203.107.1.1/resolve?host=example.org',
                    'http://[2001:db8::1]/d?dn=example.org',
                    'http://192.0.2.1:8080/httpdns/resolve',
                    'https://httpdns-api.aliyuncs.com/', 'https://httpdns.alicdn.com/',
                    'https://httpdns.example.org/', 'https://httpsdns.example.org/',
                    'https://dns.jd.com/', 'https://dns.weixin.qq.com/']:
            self.assertFalse(matches(self.all_rules, url), url)

    def test_bytedance_and_shared_sdks_are_outside_the_scope(self):
        # Representative negatives, not a captured Douyin session or a claim
        # that these hosts caused the reported live-preview stutter.
        for host in ['mcs.snssdk.com', 'extlog.snssdk.com', 'bds.snssdk.com',
                     'lf-ad-ies.bytecdn.cn', 'x-ad-y.byteimg.com',
                     'ads-normal.zijieapi.com', 'tnc.snssdk.com', 'pangle.io',
                     'pangolin.example.org', 'pglstatp.example.org',
                     'adstrategy.example.org', 'live.douyin.com',
                     'mob.com', 'sdk.verification.jiguang.cn', 'jpush.cn', 'getui.com',
                     'atoken.m.taobao.com', 'retcode.alicdn.com', 'acs4baichuan.m.taobao.com',
                     'doubleclick.net', 'ad.12306.cn', 'youtubei.googleapis.com']:
            self.assertFalse(matches(self.all_rules, 'https://' + host + '/'), host)

    def test_upstream_additions_do_not_expand_the_whitelist(self):
        for plugin in self.profile['plugins']:
            name = plugin['file']
            source = self.snapshots[name].decode()
            changed = source.replace('[Rule]', '[Rule]\nDOMAIN-KEYWORD, httpdns, REJECT\n'
                                     'DOMAIN-SUFFIX, snssdk.com, REJECT', 1)
            selected = B.select_rules(changed, plugin['rules'], name)
            self.assertEqual([e['rule'] for e in selected], self.rules[name])

    def test_removed_or_changed_selected_rules_fail(self):
        for plugin in self.profile['plugins']:
            name = plugin['file']
            source = self.snapshots[name].decode()
            for entry in plugin['rules']:
                rule = entry['rule']
                for replacement in ['', rule.removesuffix('REJECT') + 'DIRECT']:
                    with self.subTest(file=name, rule=rule, replacement=replacement):
                        with self.assertRaisesRegex(ValueError, 'missing|changed'):
                            B.select_rules(source.replace(rule, replacement), plugin['rules'], name)

    def test_conflicting_action_cannot_hide_behind_an_unchanged_rule(self):
        plugin = self.profile['plugins'][0]
        source = self.snapshots[plugin['file']].decode()
        rule = plugin['rules'][0]['rule']
        changed = source.replace(rule, rule.replace('REJECT', 'DIRECT') + '\n' + rule)
        with self.assertRaisesRegex(ValueError, 'action changed'):
            B.select_rules(changed, plugin['rules'], plugin['file'])

    def test_snapshot_drift_requires_review_even_when_selected_rules_unchanged(self):
        snapshots = dict(self.snapshots)
        name = self.profile['plugins'][0]['file']
        snapshots[name] += b'\n# new upstream release\n'
        with self.assertRaisesRegex(ValueError, 'SHA-256 changed'):
            B.build_artifacts(self.profile, snapshots)

    def test_duplicate_and_global_rules_are_rejected(self):
        plugin = self.profile['plugins'][0]
        source = self.snapshots[plugin['file']].decode()
        entries = copy.deepcopy(plugin['rules'])
        entries.append(entries[0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            B.select_rules(source, entries, plugin['file'])
        for rule in ['DOMAIN-KEYWORD, httpdns, REJECT', 'USER-AGENT, "httpdns*", REJECT',
                     'IP-CIDR, 203.107.1.0/24, REJECT, no-resolve',
                     'DOMAIN-SUFFIX, snssdk.com, REJECT']:
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                B.validate_rule(rule)

    def test_subscriptions_replace_only_the_two_public_plugins(self):
        rows = self.artifacts['plugin.conf'].decode().splitlines()
        self.assertEqual(rows, [
            'https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/Block_HTTPDNS.lpx, pin=true, enabled=true',
            'https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/BlockAdvertisers.lpx, pin=true, enabled=true',
        ])

    def test_check_detects_stale_output_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'loon', root / 'loon')
            (root / 'tools').mkdir()
            shutil.copyfile(ROOT / 'tools/build_loon_shared.py', root / 'tools/build_loon_shared.py')
            stale = root / 'loon/plugins/Block_HTTPDNS.lpx'
            stale.write_text('stale artifact\n')
            result = subprocess.run([sys.executable, str(root / 'tools/build_loon_shared.py'), '--check'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Generated artifacts differ', result.stderr)
            self.assertEqual(stale.read_text(), 'stale artifact\n')


if __name__ == '__main__':
    unittest.main()
