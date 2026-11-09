#!/usr/bin/env python3
"""Build pinned Kelee Bilibili configuration without runtime user settings."""
import base64
import hashlib
import json
import re
from pathlib import Path
import convert_lpx_to_qx as C

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://kelee.one/Tool/Loon/Lpx/Bilibili_remove_ads.lpx'
SNAPSHOT = 'tools/upstream/bilibili-kelee/Bilibili_remove_ads.lpx'
SETTINGS = dict(displayUpList='hide', purifyComment=True, optimizeRequest=True,
                sponsorBlock=False, logLevel='off')
SCRIPT_BASE = 'https://kelee.one/Resource/JavaScript/Bilibili/'
JQ_BASE = 'https://kelee.one/Resource/JQLang/Bilibili/'
RULE_AND = 'AND, ((DOMAIN-SUFFIX, chat.bilibili.com), (OR, ((DOMAIN-KEYWORD, stun), (DOMAIN-KEYWORD, tracker), (DOMAIN-KEYWORD, p2p)))), REJECT'
GRPC_HEADER_RX = r'(?i)^https:\/\/grpc\.biliapi\.net\/bilibili\.app\.(interface\.v1\.(Teenagers\/ModeStatus|Search\/DefaultWords)|view\.v1\.View\/TFInfo|viewunite\.v1\.View\/(PlayPause|ViewEndPage))$'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def asset(assets, relative, generated, original, source):
    assets[relative] = dict(source=source,
        upstream_sha256=hashlib.sha256(original).hexdigest(),
        sha256=hashlib.sha256(generated.encode()).hexdigest(), adapted=True)


def js_regex(pattern):
    """The pinned Loon rules use only /i; strip slash escapes for JS RegExp."""
    if not pattern.startswith('(?i)'):
        raise ValueError('Expected case-insensitive source regex')
    return pattern[4:].replace(r'\/', '/')


def parse_rules(text, raw):
    sections = C.sections(text)
    filters, rewrites, mocks, upstream_jq, scripts = [], [], [], [], []
    skipped_sponsor = 0
    for line in sections.get('Rule', []):
        if not line.strip() or line.lstrip().startswith('#'): continue
        if line == 'DOMAIN, bsbsb.top, PROXY':
            skipped_sponsor += 1
        elif line == RULE_AND:
            filters += [f'host-wildcard, *{keyword}*.chat.bilibili.com, reject'
                        for keyword in ('stun','tracker','p2p')]
        else:
            fields = C.split_args(line)
            if len(fields)!=3 or fields[0]!='DOMAIN' or fields[2]!='REJECT':
                raise ValueError('Unexpected Bilibili filter: '+line)
            if fields[1] not in {'api.biliapi.com','app.biliapi.com','api.biliapi.net','app.biliapi.net'}:
                raise ValueError('Bilibili domain scope changed; review '+fields[1])
            filters.append(f'host, {fields[1]}, reject')
    if len(filters)!=7 or len(set(filters))!=7:
        raise ValueError('Pinned Bilibili domain scope/count changed')
    header_actions = []
    for line in sections.get('Rewrite', []):
        if not line.strip() or line.lstrip().startswith('#'): continue
        match = C.REWRITE_RE.fullmatch(line)
        if not match: raise ValueError('Unknown rewrite '+line)
        stage, body = match['stage'], match['body']
        rx = C.regex_flags(match['re'], match['flag'])
        action_match = re.fullmatch(r'([\w.]+)\((.*)\)',body)
        if not action_match: raise ValueError('Unknown action '+body)
        action, arg = action_match.groups()
        if action=='reject_dict' and stage=='request' and arg=='200':
            rewrites.append(rx+' url reject-dict')
        elif action=='response.json.jq' and stage=='response':
            expression = C.unq(arg)
            if "'" in expression: raise ValueError('jq single quote needs review')
            rewrites.append(rx+" url jsonjq-response-body '"+expression+"'")
        elif action=='response.json.delete' and stage=='response':
            rewrites.append(rx+" url jsonjq-response-body 'del("+C.jq_path(C.unq(arg))+")'")
        elif action=='response.json.jq_file' and stage=='response':
            url = C.unq(arg)
            if not url.startswith(JQ_BASE): raise ValueError('Unknown jq origin')
            name = url[len(JQ_BASE):]
            if name not in {'tab_Bilibili_remove_ads.jq','mine_Bilibili_remove_ads.jq'}:
                raise ValueError('Unknown jq file')
            original = (ROOT/'tools/upstream/bilibili-kelee'/name).read_text()
            expression = C.jq_comment_strip(original)
            if "'" in expression: raise ValueError('jq quote needs review')
            rewrites.append(rx+" url jsonjq-response-body '"+expression+"'")
            upstream_jq.append(dict(source=url,snapshot='tools/upstream/bilibili-kelee/'+name,
                                   sha256=hashlib.sha256(original.encode()).hexdigest()))
        elif action=='response.body.mock' and stage=='response':
            args = json.loads('['+arg+']')
            if len(args) not in (3,4) or args[0]!='text' or args[2]!=200:
                raise ValueError('Unknown mock format')
            binary = len(args)==4 and args[3] is True
            data = list(base64.b64decode(args[1], validate=True)) if binary else args[1]
            if binary and (len(data)<5 or data[0]!=0 or int.from_bytes(bytes(data[1:5]),'big')!=len(data)-5):
                raise ValueError('Invalid pinned gRPC frame')
            mocks.append(dict(pattern=js_regex(rx), body=data, binary=binary))
            rewrites.append(rx+' url script-echo-response '+raw+'/js/BilibiliKelee/mock.js')
        elif action=='response.header.add' and stage=='response':
            if rx!=GRPC_HEADER_RX or json.loads('['+arg+']')!=['grpc-status','0']:
                raise ValueError('Unexpected header action')
            header_actions.append(rx)
        else: raise ValueError('Unsupported Bilibili action '+body)
    if len(header_actions)!=1 or len(mocks)!=6:
        raise ValueError('Pinned mock/header source changed')
    for mock in mocks:
        mock['grpc_status'] = mock['binary']
    for line in sections.get('Script', []):
        if not line.strip() or line.lstrip().startswith('#'): continue
        match = C.SCRIPT_RE.fullmatch(line)
        if not match: raise ValueError('Unknown script rule '+line)
        if 'enable=${sponsorBlock}' in line:
            if 'DmSegMobile' not in line: raise ValueError('Unknown sponsor rule')
            skipped_sponsor += 1
            continue
        rx = C.regex_flags(match['re'],match['flag'])
        name = match['url'].removeprefix(SCRIPT_BASE)
        allowed = {'Bilibili_proto_request_kokoryh.js':'request.js',
                   'Bilibili_proto_response_kokoryh.js':'response.js',
                   'Bilibili_json_kokoryh.js':'json.js'}
        if not match['url'].startswith(SCRIPT_BASE) or name not in allowed:
            raise ValueError('Unknown script asset')
        if match['stage']=='request' and ('enable=${optimizeRequest}' not in line or 'requires_body=true' not in line):
            raise ValueError('Request optimization options changed')
        scripts.append((name,allowed[name]))
        rewrites.append(rx+' url script-'+match['stage']+'-body '+raw+'/js/BilibiliKelee/'+allowed[name])
    if skipped_sponsor!=2 or len(scripts)!=3 or len(rewrites)!=22:
        raise ValueError('Source rule count/disabled sponsor changed; review')
    hosts=[]
    for line in sections.get('MitM',[]):
        if line.startswith('hostname='):
            hosts += [host.strip() for host in line.split('=',1)[1].split(',')]
    if hosts != ['grpc.biliapi.net','app.bilibili.com','api.bilibili.com',
                  'api.live.bilibili.com','line3-h5-mobile-api.biligame.com']:
        raise ValueError('Source MITM scope changed')
    # Pin the grpc-status union to the three binary mock regexes: any change
    # needs review, since QX cannot run a second response-header rewrite later.
    expected_binary = {
        r'^https://grpc\.biliapi\.net/bilibili\.app\.interface\.v1\.Teenagers/ModeStatus$',
        r'^https://grpc\.biliapi\.net/bilibili\.app\.interface\.v1\.Search/DefaultWords$',
        r'^https://grpc\.biliapi\.net/bilibili\.app\.(view\.v1\.View/TFInfo|viewunite\.v1\.View/(PlayPause|ViewEndPage))$'}
    if {mock['pattern'] for mock in mocks if mock['binary']} != expected_binary:
        raise ValueError('Binary mock/header scope changed; review final header actions')
    return dict(filters=filters,rewrites=rewrites,hosts=hosts,mocks=mocks,jq=upstream_jq,scripts=scripts)


def mock_script(mocks):
    # Loon response.body.mock runs BEFORE upstream. QX script-echo-response
    # preserves this phase, including the subsequent grpc-status header action.
    return '''// Generated from Kelee Bilibili LPX; original author kokoryh.
// No network request, storage, subscription parameters or SponsorBlock.
(() => {
  const routes = __ROUTES__;
  const url = $request.url;
  const route = routes.find(item => new RegExp(item.pattern, "i").test(url));
  if (!route) { $done({}); return; }
  const response = {status: "HTTP/1.1 200 OK", headers: {"Content-Type": "text/plain; charset=utf-8"}};
  if (route.grpc_status) response.headers["grpc-status"] = "0";
  if (route.binary) {
    // The source base64 contains the ENTIRE five-byte-prefixed gRPC frame.
    const bytes = new Uint8Array(route.body);
    response.bodyBytes = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  } else response.body = route.body;
  $done(response);
})();
'''.replace('__ROUTES__',json.dumps(mocks,ensure_ascii=False,separators=(',',':')))


def emit(out, raw, assets, supplement=None):
    from bilibili_kelee_scripts import emit as emit_scripts
    out = Path(out)
    source_bytes = (ROOT/SNAPSHOT).read_bytes()
    parsed = parse_rules(source_bytes.decode('utf-8'), raw)
    # Assets are rebuilt from pinned upstream sources, never fetched at runtime.
    script_assets = emit_scripts(out/'js/BilibiliKelee')
    assets.update({'js/BilibiliKelee/'+name: {key:value for key,value in meta.items() if key!='path'}
                   for name,meta in script_assets.items()})
    mock = mock_script(parsed['mocks'])
    mock_relative = 'js/BilibiliKelee/mock.js'
    write(out/mock_relative,mock)
    asset(assets,mock_relative,mock,source_bytes,SOURCE)
    if not supplement or supplement.get('rewrites'):
        raise ValueError('Missing or unexpected shared Bilibili rules; review scope')
    if supplement.get('filters') != ['host, httpdns.bilivideo.com, reject']:
        raise ValueError('Only the audited Bilibili HTTPDNS domain may be supplemented')
    if any(item['source']!='https://kelee.one/Tool/Loon/Lpx/Block_HTTPDNS.lpx'
           for item in supplement.get('sources',[])):
        raise ValueError('No BlockAdvertisers rule was identified for Bilibili')
    filters = list(dict.fromkeys(supplement['filters']+parsed['filters']))
    notes = ['原作者：kokoryh（可莉收录）；固定配置，无需用户参数或 BoxJS。',
             '最常访问=hide；移除评论区置顶广告=true；优化评论区加载异常=true；日志=off。',
             '不迁移空降助手：不含 DmSegMobile 请求脚本或 bsbsb.top 分流。',
             '域名拦截已合并；仅纳入明确属于 B 站的公共补充，停用其它 B 站规则。',
             '评论加载优化已开启兼容重放，但无已核实的强制 HTTP/2/trailers 等价接口；推荐 QX build 934+。',
             '二进制脚本已适配 QX bodyBytes；本地测试不能代替手机 HTTP/2/gRPC 实测。']
    header = ['#!name=哔哩哔哩去广告', '#!desc=可莉版固定配置；动态最常访问隐藏，评论净化和请求优化开启，无空降助手',
              '#!author=kokoryh[https://github.com/kokoryh]', '#!qx_version=1.5.2-854',
              '#!icon=https://raw.githubusercontent.com/luestr/IconResource/main/App_icon/120px/Bilibili.png',
              '# Source: '+SOURCE]
    header += ['# '+note for note in notes]
    header += ['# Shared source: '+item['source'] for item in (supplement or {}).get('sources',[])]
    snippet = 'snippets/bilibili.snippet'
    write(out/snippet,'\n'.join(header+filters+parsed['rewrites']+
          ['hostname = '+', '.join(parsed['hosts'])])+'\n')
    (out/'lists/bilibili.list').unlink(missing_ok=True)
    row = dict(name='哔哩哔哩去广告',fname='Bilibili_remove_ads.lpx',slug='bilibili',kind='snippets',
               rewrite=len(parsed['rewrites']),filter=len(filters),hosts=parsed['hosts'],notes=notes,
               has_list=False,snippet=snippet,list=None,source=SOURCE,snapshot=SNAPSHOT,
               upstream_sha256=hashlib.sha256(source_bytes).hexdigest(),
               embedded_filter=True,qx_min_version='1.5.2-854',settings=SETTINGS,
               jq_sources=parsed['jq'])
    if supplement: row['supplements']=supplement.get('sources',[])
    return row,parsed['rewrites'],filters,[]
