"""QQMusic domain-only rewrite resource; no phone import is simulated."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_qx_repo as B
import convert_lpx_to_qx as C
import check_qx as K


def active(text):
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith(('#',';'))]


class QQMusicTests(unittest.TestCase):
    def test_plugin_and_legacy_list_have_identical_14_domains(self):
        snippet = (ROOT/'snippets/qqmusic.snippet').read_text()
        rules = active(snippet)
        self.assertEqual(rules, active((ROOT/'lists/qqmusic.list').read_text()))
        self.assertEqual(len(rules), 14)
        self.assertEqual(len(set(rules)), 14)
        self.assertTrue(all(line.startswith('host, ') and line.endswith(', reject') for line in rules))
        self.assertNotIn('hostname', snippet)
        self.assertFalse(any(' url ' in line or 'script-' in line for line in rules))
        self.assertIn('#!name=QQ音乐去广告', snippet)
        self.assertIn('#!qx_version=1.5.2-854', snippet)
        self.assertIn('https://kelee.one/Tool/Loon/Lpx/QQMusic_remove_ads.lpx', snippet)

    def test_all_11_upstream_rules_and_only_three_original_supplements(self):
        source = (ROOT/'tools/upstream/QQMusic_remove_ads.lpx').read_text()
        result = C.convert('QQ音乐', 'QQMusic_remove_ads.lpx', text=source)
        self.assertEqual(len(result['filters']), 11)
        self.assertFalse(result['rewrites'] or result['hosts'] or result['tasks'])
        published = active((ROOT/'snippets/qqmusic.snippet').read_text())
        self.assertEqual(published[3:], result['filters'])
        self.assertEqual(published[:3], ['host, tmeadcomm.y.qq.com, reject',
                                       'host, stat.y.qq.com, reject',
                                       'host, stat6.y.qq.com, reject'])

    def test_default_subscription_uses_only_plugin_while_legacy_file_survives(self):
        rewrites = active((ROOT/'config/rewrite_remote.conf').read_text())
        filters = active((ROOT/'config/filter_remote.conf').read_text())
        self.assertEqual(sum('/snippets/qqmusic.snippet,' in line for line in rewrites), 1)
        self.assertFalse(any('qqmusic' in line for line in filters))
        self.assertTrue((ROOT/'lists/qqmusic.list').is_file())
        row = next(item for item in json.loads((ROOT/'build-info.json').read_text())['rows']
                   if item['slug']=='qqmusic')
        self.assertEqual((row['rewrite'], row['filter'], row['hosts']), (0,14,[]))
        self.assertEqual(row['snippet'], 'snippets/qqmusic.snippet')
        self.assertEqual(row['list'], 'lists/qqmusic.list')
        self.assertTrue(row['embedded_filter'] and row['alternative_list'])

    def test_generator_reproduces_both_formats_without_scripts(self):
        info = json.loads((ROOT/'build-info.json').read_text())
        row = next(item for item in info['rows'] if item['slug']=='qqmusic')
        supplement = dict(filters=active((ROOT/'lists/qqmusic.list').read_text())[:3],
                          sources=row['supplements'])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(C,'SRC',str(ROOT/'tools/upstream')):
                generated,rw,ft,tk = B.emit(out,'QQ音乐去广告','QQMusic_remove_ads.lpx',
                                           'qqmusic','snippets',B.RAW,{},supplement)
            self.assertEqual(generated, row)
            self.assertFalse(rw or tk)
            self.assertEqual(len(ft),14)
            for rel in ('snippets/qqmusic.snippet','lists/qqmusic.list'):
                self.assertEqual((out/rel).read_bytes(), (ROOT/rel).read_bytes())
            B.remove_retired(out)
            self.assertTrue((out/'snippets/qqmusic.snippet').exists())

    def test_validator_accepts_domain_only_nonempty_resource(self):
        with patch.object(K,'bad',[]), patch.object(K,'counts',dict(rewrite=0,filter=0,jqhdr=0)):
            K.check_file(str(ROOT/'snippets/qqmusic.snippet'))
            self.assertEqual(K.bad, [])
            self.assertEqual(K.counts, dict(rewrite=0,filter=14,jqhdr=0))


if __name__ == '__main__':
    unittest.main()
