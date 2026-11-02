import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import convert_lpx_to_qx as C
import build_qx_repo as B
import shared_scope as S

class ConversionTests(unittest.TestCase):
    def convert(self,text,filename='test.lpx'):
        with tempfile.TemporaryDirectory() as d:
            Path(d,filename).write_text(text)
            with patch.object(C,'SRC',d):return C.convert('Test',filename)

    def jq(self,expression,value):
        p=subprocess.run(['jq','-c',expression],input=json.dumps(value),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def test_case_insensitive_and_string_values(self):
        text=r'''[Rewrite]
response if ${url} ~= /^https:\/\/api\.test\/Config/i then response.json.replace(["data.text", "data.number"], ["0", 0])
'''
        row=self.convert(text)['rewrites'][0]
        self.assertTrue(re.search(row[0],'https://API.TEST/config'))
        self.assertEqual(self.jq(row[2][1][1:-1],{'data':{}}),{'data':{'text':'0','number':0}})

    def test_jq_whitespace_and_comments(self):
        code='{"name": "a  b", "hash":"#keep"} # remove\n | .'
        self.assertEqual(self.jq(C.jq_comment_strip(code),{}),{'name':'a  b','hash':'#keep'})

    def test_quoted_regex_commas(self):
        r=self.convert(r'''[Rule]
URL-REGEX, "^http:\/\/a\.test\/v{1,3},x", REJECT
''')
        self.assertTrue(re.search(r['rewrites'][0][0],'http://a.test/vvv,x'))

    def test_combined_json_operations(self):
        r=self.convert(r'''[Rewrite]
response if ${url} ~= /^https:\/\/a\.test\/data/i then response.json.delete("data.ad")
response if ${url} ~= /^https:\/\/a\.test\/data/i then response.json.replace("data.items", [])
''')
        self.assertEqual(len(r['rewrites']),1)
        self.assertEqual(self.jq(r['rewrites'][0][2][1][1:-1],{'data':{'ad':1,'items':[1],'keep':2}}),{'data':{'items':[],'keep':2}})

    def match_filters(self,lines,host):
        for line in lines:
            kind,value,policy=[x.strip() for x in line.split(',')]
            if kind=='host' and host==value:return policy
            if kind=='host-suffix' and (host==value or host.endswith('.'+value)):return policy
            if kind=='host-keyword' and value in host:return policy
            if kind=='host-wildcard' and fnmatch.fnmatchcase(host,value):return policy
        return None

    def test_and_preserves_domain_boundary(self):
        rows=C.and_domain_filters({'kws':['-ad-'],'sufs':['byteimg.com']},'reject')
        self.assertEqual(self.match_filters(rows,'a-ad-b.byteimg.com'),'reject')
        self.assertIsNone(self.match_filters(rows,'a-ad-b.evilbyteimg.com'))
        self.assertIsNone(self.match_filters(rows,'a-ad-b.byteimg.com.evil.test'))

    def test_and_requires_both_keywords(self):
        rows=C.and_domain_filters({'kws':['ads','-normal.zijieapi.com'],'sufs':[]},'reject')
        for host in ['ads-normal.zijieapi.com','foo-normal.zijieapi.com.ads']:
            self.assertEqual(self.match_filters(rows,host),'reject')
        self.assertIsNone(self.match_filters(rows,'api-normal.zijieapi.com'))

    def test_httpdns_exception_not_whole_app(self):
        r=self.convert(r'''[Rule]
AND, ((URL-REGEX, ^http:\/\/119\.29\.29\.90\/d\?), (USER-AGENT, Dida*)), DIRECT
URL-REGEX, "^http:\/\/\d+\.\d+\.\d+\.\d+\/d\?", REJECT
''')
        self.assertFalse(any('user-agent' in f and 'direct' in f for f in r['filters']))
        def blocked(url,ua):
            headers='GET / HTTP/1.1\r\nUser-Agent: '+ua+'\r\nAccept: */*\r\n'
            for pattern,_,_,_ in r['rewrites']:
                parts=pattern.split(' ',1)
                if re.search(parts[0],url) and (len(parts)==1 or re.search(parts[1],headers)):return True
            return False
        self.assertFalse(blocked('http://119.29.29.90/d?dn=example.com','Dida/1.0'))
        self.assertTrue(blocked('http://119.29.29.90/d?dn=example.com','Other/1.0'))
        self.assertTrue(blocked('http://1.2.3.4/d?dn=example.com','Dida/1.0'))

    def test_scoped_httpdns_blocks_taobao_without_generic_app_exceptions(self):
        rows=[line for line in (REPO/'snippets/taobao.snippet').read_text().splitlines()
              if ' url ' in line and not line.startswith('#')]
        self.assertFalse(any('url-and-header' in row for row in rows))
        patterns=[row.split(' url ',1)[0] for row in rows]
        def blocked(url):return any(re.search(pattern,url) for pattern in patterns)
        self.assertTrue(blocked('http://amdc.m.taobao.com/amdc/mobileDispatch'))
        self.assertTrue(blocked('http://47.246.103.9/amdc/mobileDispatch?fixture=1'))
        for url in ['http://119.29.29.90/d?dn=example.com',
                    'http://1.2.3.4/d?dn=example.com',
                    'http://amdc.m.taobao.com/normal',
                    'https://ucdc2-upaas.uc.cn/api/v1/dns_query?fixture=1']:
            self.assertFalse(blocked(url),url)

    def test_scoped_lists_keep_selected_services_without_unrelated_rules(self):
        def rules(name):return [line for line in (REPO/'lists'/name).read_text().splitlines()
                                if line.strip() and not line.startswith('#')]
        all_rules=rules('jd.list')+rules('bilibili.list')+rules('qqmusic.list')+rules('taobao.list')
        for filename,host in [('jd.list','dns.jd.com'),('bilibili.list','httpdns.bilivideo.com'),
                              ('taobao.list','httpdns-api.aliyuncs.com')]:
            self.assertEqual(self.match_filters(rules(filename),host),'reject')
        for host in ['httpdns.baidu.com','dns.weixin.qq.com','unrelated.httpdns.example.test']:
            self.assertIsNone(self.match_filters(all_rules,host))
        for filename,host in [('qqmusic.list','tmeadcomm.y.qq.com'),('jd.list','dsp-x.jd.com'),
                              ('taobao.list','atoken.m.taobao.com')]:
            self.assertEqual(self.match_filters(rules(filename),host),'reject')
        self.assertIsNone(self.match_filters(all_rules,'www.jiguang.cn'))
        for filename in ['rewrite_remote.conf','filter_remote.conf']:
            self.assertNotIn('/base/',(REPO/'config'/filename).read_text())
        self.assertFalse(any((REPO/'base').glob('*')))

    def test_ali_apps_include_shared_rules_without_other_apps_enabled(self):
        for slug in ['taobao','goofish','amap']:
            lines=[line for line in (REPO/'lists'/(slug+'.list')).read_text().splitlines()
                   if line.strip() and not line.startswith('#')]
            self.assertEqual(self.match_filters(lines,'httpdns-api.aliyuncs.com'),'reject',slug)
            self.assertEqual(self.match_filters(lines,'et.tanx.com'),'reject',slug)
            self.assertEqual(len(lines),len(set(lines)),slug)
            rewrites=[line for line in (REPO/'snippets'/(slug+'.snippet')).read_text().splitlines()
                      if ' url ' in line and not line.startswith('#')]
            matching=[line for line in rewrites if re.search(line.split(' url ')[0],
                         'http://amdc.m.taobao.com/amdc/mobileDispatch')]
            self.assertEqual(len(matching),1,slug)
            self.assertTrue(matching[0].endswith(' url reject'))

    def test_shared_filter_copies_have_no_conflicting_policies(self):
        seen={}
        for path in (REPO/'lists').glob('*.list'):
            for line in path.read_text().splitlines():
                if not line.strip() or line.startswith('#'):continue
                kind,value,policy=[p.strip() for p in line.split(',')]
                key=(kind,value)
                if key in seen:self.assertEqual(seen[key],policy,key)
                seen[key]=policy
        self.assertEqual(seen['host','ad.12306.cn'],'direct')

    def test_shared_selection_ignores_additions_but_fails_on_changed_selected_rule(self):
        profile={'fixture.lpx':[dict(apps=['京东'],purpose='fixture',basis='fixture',
                                    rules=[('DOMAIN','dns.jd.com')])]}
        with patch.object(S,'PROFILES',profile):
            source,report=S.select_shared('fixture.lpx','[Rule]\nDOMAIN, dns.jd.com, REJECT\nDOMAIN, unrelated.test, REJECT\n')
            self.assertIn('dns.jd.com',source)
            self.assertNotIn('unrelated.test',source)
            self.assertEqual(report['selected_rules'],1)
            with self.assertRaises(ValueError):S.select_shared('fixture.lpx','[Rule]\nDOMAIN, dns.jd.com, DIRECT\n')
            with self.assertRaises(ValueError):S.select_shared('fixture.lpx','[Rule]\nDOMAIN, unrelated.test, REJECT\n')

    def test_google_preserves_query_and_rejects_suffix_trick(self):
        r=self.convert(r'''[Rewrite]
request if ${url} ~= /^https?:\/\/(www.)?(g|google)\.cn/i then redirect(307, "https://www.google.com")
''','Google.lpx')
        pattern,_,(_,target),_=r['rewrites'][0]
        match=re.search(pattern,'https://www.google.cn/search?q=a%20b&hl=zh')
        self.assertEqual(target.replace('$1',match.group(1)),'https://www.google.com/search?q=a%20b&hl=zh')
        self.assertIsNone(re.search(pattern,'https://google.cn.evil.test/'))

    def test_hostname_regex_expansion(self):
        rows=[['(?i)^https:\\/\\/ucdc\\d?-upaas\\.uc\\.cn\\/api','request',('reject',None),'']]
        hosts=C.complete_hosts(rows,[])
        self.assertEqual(set(hosts),{'ucdc-upaas.uc.cn'}|{f'ucdc{i}-upaas.uc.cn' for i in range(10)})

    def test_disabled_script_and_cron(self):
        r=self.convert(r'''[Script]
request if ${url} ~= /^https:\/\/a\.test/i then script("https://a.test/a.js") with enable=false
cron "0 6 * * *" then script("https://a.test/a.js") with enable=false, tag="test"
''')
        self.assertEqual(r['rewrites'],[])
        self.assertTrue(r['tasks'][0].startswith('0 6 * * * '))
        self.assertIn('enabled=false',r['tasks'][0])

    def test_parameters_fail_instead_of_silently_dropping(self):
        with self.assertRaises(ValueError):self.convert(r'''[Script]
response if ${url} ~= /^https:\/\/a\.test/i then script("https://a.test/a.js", {"switch":true}) with requires_body=true
''')

    def test_script_refresh_overwrites_stale_generated_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();out=root/'out'
            script=root/'mirror/upstream/kelee.one/Resource/JavaScript/Test/test.js'
            script.parent.mkdir(parents=True);script.write_text('$done({body:"first"});')
            (root/'src/test.lpx').write_text(r'''[Script]
response if ${url} ~= /^https:\/\/a\.test/i then script("https://kelee.one/Resource/JavaScript/Test/test.js") with requires_body=true
''')
            with patch.object(C,'SRC',str(root/'src')),patch.object(C,'MIRROR',str(root/'mirror')):
                B.emit(out,'test','test.lpx','test','snippets',B.RAW,{})
                script.write_text('$done({body:"second"});')
                B.emit(out,'test','test.lpx','test','snippets',B.RAW,{})
            self.assertIn('second',(out/'js/Test/test.js').read_text())
            self.assertNotIn('body:"first"',(out/'js/Test/test.js').read_text())

    def test_caiyun_excluded(self):
        self.assertFalse(any('ColorfulClouds' in f for _,f,_ in C.ENABLED))

    def generated_jq(self,slug,url,body):
        for line in (REPO/'snippets'/(slug+'.snippet')).read_text().splitlines():
            if ' url ' not in line or line.startswith('#'):continue
            pattern,action=line.split(' url ',1)
            if re.search(pattern,url):
                self.assertTrue(action.startswith('jsonjq-response-body '),action)
                return self.jq(action.split(' ',1)[1][1:-1],body)
        self.fail('No matching generated rewrite for '+url)

    def test_coolapk_home_keeps_ordinary_items(self):
        normal={'entityTemplate':'feed','entityId':123,'title':'正常内容'}
        result=self.generated_jq('coolapk','https://api.coolapk.com/v6/main/indexV8',
            {'data':[normal,{'entityTemplate':'feed','entityId':8639,'title':'推广'},
                     {'entityTemplate':'sponsorCard','entityId':124,'title':'广告'}]})
        self.assertEqual(result['data'],[normal])

    def test_coolapk_init_keeps_normal_and_filters_menu(self):
        result=self.generated_jq('coolapk','https://api.coolapk.com/v6/main/init',
            {'data':[{'entityId':944},{'entityId':100},{'entityId':20131,'entities':[{'title':'酷品'},{'title':'普通'}]}]})
        self.assertEqual(result['data'],[{'entityId':100},{'entityId':20131,'entities':[{'title':'普通'}]}])

    def test_goofish_combined_search(self):
        ad={'data':{'item':{'main':{'exContent':{'dislikeFeedback':{'clickParam':{'args':{'bizType':'ad'}}}}}}}}
        result=self.generated_jq('goofish','https://g-acs.m.goofish.com/gw/mtop.taobao.idlemtopsearch.search/1.0',
            {'data':{'resultList':[ad,{'id':'normal'}],'resultPrefixBar':{'ad':1},'keep':2}})
        self.assertEqual(result,{'data':{'resultList':[{'id':'normal'}],'keep':2}})

    def test_xiachufang_config(self):
        result=self.generated_jq('xiachufang','https://api.xiachufang.com/v2/config/get.json',
            {'content':{'recipe_ad':{},'splash_ad_req_time':5,'normal':'keep'}})
        self.assertEqual(result,{'content':{'normal':'keep'}})

    def test_amap_inlined_detail(self):
        result=self.generated_jq('amap','https://info.amap.com/ws/shield/search/poi/detail?fixture=1',
            {'data':{'regions':{'main':['baseInfo','adBanner']},'modules':{
                'baseInfo':{'data':{'user':{'name':'keep','userLocRgeo':{'ad':1}}}},'adBanner':{'ad':1}}}})
        self.assertEqual(result['data']['regions']['main'],['baseInfo'])
        self.assertEqual(set(result['data']['modules']),{'baseInfo'})
        self.assertEqual(result['data']['modules']['baseInfo']['data']['user'],{'name':'keep'})

if __name__=='__main__':unittest.main()
