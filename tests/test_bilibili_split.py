"""Build-only split contract; does not simulate iOS/QX transport or benchmark it."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import bilibili_kelee_scripts as B

class BilibiliSplitTests(unittest.TestCase):
    def test_rebuild_is_deterministic_and_routes_remain_static(self):
        info=json.loads((ROOT/'build-info.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            assets=B.emit(Path(tmp))
            for name,meta in assets.items():
                with self.subTest(file=name):
                    self.assertEqual((Path(tmp)/name).read_bytes(),(ROOT/'js/BilibiliKelee'/name).read_bytes())
                    self.assertEqual(meta['sha256'],info['assets']['js/BilibiliKelee/'+name]['sha256'])
            self.assertEqual(assets['reply.js']['retained_descriptors'],5)
            self.assertEqual(assets['video.js']['retained_descriptors'],21)
            self.assertEqual(assets['reply.js']['specialized_routes'],['bilibili.main.community.reply.v1.Reply/MainList'])
            self.assertEqual(len(assets['video.js']['specialized_routes']),7)
            self.assertTrue(all('.view.' in r or '.viewunite.' in r for r in assets['video.js']['specialized_routes']))

    def test_changed_descriptor_core_requires_explicit_reaudit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'core.js';source.write_text('const unsafe = 1;')
            process=subprocess.run(['node','--expose-internals',str(ROOT/'tools/bilibili_split.cjs'),
                                    str(source),str(ROOT/'tools/bilibili_kelee_runtime.js'),str(Path(tmp)/'out')],
                                   capture_output=True,text=True,timeout=30)
            self.assertNotEqual(process.returncode,0)
            self.assertIn('Reviewed protobuf core changed',process.stderr)
            self.assertFalse((Path(tmp)/'out').exists())

if __name__=='__main__':unittest.main()
