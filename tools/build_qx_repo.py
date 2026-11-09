#!/usr/bin/env python3
"""Build native QX resources from a local mirror. No network or private config is read."""
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_lpx_to_qx as C
import shared_scope as S

ROOT = Path(C.ROOT)
RAW = 'https://raw.githubusercontent.com/TO8E/loon2qx/main'
SLUGS = {'QQMusic_remove_ads.lpx':'qqmusic','JD_remove_ads.lpx':'jd','XiaChuFang_remove_ads.lpx':'xiachufang',
         'Taobao_remove_ads.lpx':'taobao','FleaMarket_remove_ads.lpx':'goofish','RedPaper_remove_ads.lpx':'xhs',
         '12306_remove_ads.lpx':'12306','CoolApk_remove_ads.lpx':'coolapk','Amap_remove_ads.lpx':'amap',
         'LOL_Bible_remove_ads.lpx':'mlol','PuPuMall_remove_ads.lpx':'pupu','Google.lpx':'google',
         'XiaoHeiHe_remove_ads.lpx':'xiaoheihe'}

# Non-Kelee sources use checked-in public snapshots, not a personal configuration.
EXTERNAL_PLUGINS = {
    'ChinaUnicom.lpx': dict(name='中国联通去广告', slug='chinaunicom',
        source='https://loon.103516.xyz/Plugin/ChinaUnicom.lpx',
        snapshot='tools/upstream/ChinaUnicom.lpx', embedded_filter=True,
        qx_min_version='1.5.2-854'),
}

def write(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')

def remove_retired(out):
    for name in ['snippets/caiyun.snippet','lists/caiyun.list','js/ColorfulClouds/ColorfulClouds_remove_ads.js',
                 'snippets/ColorfulClouds_remove_ads.snippet','lists/ColorfulClouds_remove_ads.list',
                 'js/Bilibili/bilibili_json.js','lists/bilibili.list',
                 'base/httpdns.list','base/httpdns.snippet','base/advertisers.list','base/advertisers.snippet']:
        (out/name).unlink(missing_ok=True)
    directory=out/'js/ColorfulClouds'
    if directory.exists() and not any(directory.iterdir()):directory.rmdir()
    directory=out/'base'
    if directory.exists() and not any(directory.iterdir()):directory.rmdir()

def supplements():
    per_app={};reports={}
    for filename in S.PROFILES:
        _,report=S.select_shared(filename,Path(C.SRC,filename).read_text(encoding='utf-8'))
        reports[filename]=report
        for group in report['groups']:
            converted=C.convert(group['purpose'],filename,text='[Rule]\n'+'\n'.join(e['rule'] for e in group['entries'])+'\n')
            group['targets']=[S.TARGETS[app] for app in group['apps']]
            for slug in group['targets']:
                target=per_app.setdefault(slug,dict(rewrites=[],filters=[],notes=[],sources=[]))
                target['rewrites']+=converted['rewrites']
                target['filters']+=converted['filters']
                target['notes']+=converted['notes']
                target['sources'].append(dict(source=report['source'],purpose=group['purpose']))
    return per_app,reports

def emit(out,name,filename,slug,kind,raw,assets,supplement=None):
    if slug=='bilibili':
        from build_bilibili_kelee import emit as emit_bilibili
        return emit_bilibili(out,raw,assets,supplement)
    external=EXTERNAL_PLUGINS.get(filename)
    source_text=None
    if external:
        source_path=Path(__file__).resolve().parents[1]/external['snapshot']
        source_bytes=source_path.read_bytes()
        source_text=source_bytes.decode('utf-8')
    result=C.convert(name,filename,text=source_text) if filename else dict(rewrites=[],filters=[],notes=[],hosts=[],tasks=[])
    embedded=bool(external and external.get('embedded_filter')) or slug=='qqmusic'
    keep_alternative_list=slug=='qqmusic'
    qx_min_version=external['qx_min_version'] if external else '1.5.2-854'
    supplement=supplement or {}
    result['rewrites']=supplement.get('rewrites',[])+result['rewrites']
    result['filters']=list(dict.fromkeys(supplement.get('filters',[])+result['filters']))
    native=[]
    if slug=='qqmusic':
        # Import compatibility workaround: the domain-only snippet was rejected
        # as invalid by a user on QX 1.90 with resource parser disabled.
        # HTTP only, same already-rejected host. Identity header replacement:
        # no extra rejection, no forced DIRECT, no script and no MITM.
        if 'host, ad.tencentmusic.com, reject' not in result['filters']:
            raise ValueError('QQMusic compatibility host is no longer rejected; review upstream')
        native.append(r'^http:\/\/ad\.tencentmusic\.com\/ url request-header ^([\s\S]*)$ request-header $1')
    hosts=C.complete_hosts(result['rewrites'],result['hosts'])
    added=[h for h in hosts if h not in result['hosts']]
    notes=list(dict.fromkeys(supplement.get('notes',[])+result['notes']))
    if supplement:
        notes.append('已并入本 App 的广告/统计域名配套；来源和分配见 config/shared-scope.json。'
                     if slug=='qqmusic' else '已并入本 App 的 HTTPDNS/广告域名配套；来源和分配见 config/shared-scope.json。')
    if slug=='xiaoheihe':
        notes.append('原作者：可莉；忠实保留上游 jq 逻辑（删除大写 PROTOCOL，无外部 JS）。')
    if embedded:
        for rule in result['filters']:
            parts=[p.strip() for p in rule.split(',')]
            if len(parts)!=3 or parts[0] not in {'host','host-suffix'} or parts[2]!='reject':
                raise ValueError('Only explicit domain reject rules may be embedded: '+rule)
        if slug=='chinaunicom':
            notes.append('原作者：mist-whisper；源插件另注明 ddgksf2013 规则参考。')
            notes.append('QX 1.5.2(854)+ 合并资源；域名拦截与重写一起添加到 rewrite_remote，无外部 JS。')
            notes.append('钱包重叠处理依据 Loon 官方 rewrite_v2：同阶段所有匹配按序执行；QX 按最终效果转换。')
        elif slug=='qqmusic':
            notes.append('原作者：可莉；14 条域名拦截 + 1 条 HTTP 原样请求头占位，无脚本或 MitM。')
            notes.append('占位不再拒绝请求、不修改请求头，也不强制直连；原广告域名拒绝保持不变。')
            notes.append('纯域名版在用户 QX 1.90 中报内容无效；此混合资源为兼容修正版，待手机导入验证。')
            notes.append('添加到重写资源，关闭资源解析器；与 lists/qqmusic.list 二选一，不要重复订阅。')
    if added:notes.append('补齐 HTTPS 匹配主机：'+', '.join(added))
    body=[]
    for rx,stage,(action,arg),note in result['rewrites']:
        if action.startswith('script') and arg:
            prefix='https://kelee.one/Resource/JavaScript/'
            if arg.startswith(prefix):
                relative='js/'+arg[len(prefix):]
                source=Path(C.MIRROR)/'upstream/kelee.one/Resource/JavaScript'/arg[len(prefix):]
                if not source.is_file():raise ValueError('Missing script: '+str(source))
                original=source.read_text(encoding='utf-8')
                if '[mirror-stub]' in original:raise ValueError('Stub cannot be published: '+relative)
                adapted=C.adapt_script(original,relative)
                write(out/relative,adapted)
                assets[relative]={'source':arg,'upstream_sha256':hashlib.sha256(original.encode()).hexdigest(),
                                  'sha256':hashlib.sha256(adapted.encode()).hexdigest(),'adapted':True}
                arg=raw+'/'+relative
        body.append(C.fmt_rewrite([rx,stage,(action,arg),note])[0])
    body=list(dict.fromkeys(body+native))
    snippet=f'{kind}/{slug}.snippet' if body or (embedded and result['filters']) else None
    if snippet:
        header=([f"hostname = {', '.join(hosts)}"] if hosts else [])
        if slug=='qqmusic':
            header += ['#!name=QQ音乐去广告', '#!desc=可莉域名拦截及原有广告统计补充；无需 MitM',
                       '#!author=可莉[https://github.com/luestr/ProxyResource/blob/main/README.md]',
                       '#!icon=https://raw.githubusercontent.com/luestr/IconResource/main/App_icon/120px/QQMusic.png']
        header += [f'# {name}']
        if filename:
            source=external['source'] if external else f'https://kelee.one/Tool/Loon/Lpx/{filename}'
            header.append('# Source: '+source)
        if embedded:header.append('#!qx_version='+qx_min_version)
        header += ['# Shared source: '+s['source'] for s in supplement.get('sources',[])]
        header += ['# Generated by loon2qx. See README for compatibility limits.']
        header += ['# '+note for note in notes]
        resource_rules=(body+result['filters'] if slug=='qqmusic' else
                        (result['filters'] if embedded else [])+body)
        write(out/snippet,'\n'.join(header+resource_rules)+'\n')
    else:(out/kind/(slug+'.snippet')).unlink(missing_ok=True)
    listpath=None
    if result['filters'] and (not embedded or keep_alternative_list):
        listpath=f'lists/{slug}.list'
        header=f'# {name}：本 App 分流及已合并的公共配套\n'
        if supplement:header+='# 公共条目来源及分配见 config/shared-scope.json。\n'
        write(out/listpath,header+'\n'.join(result['filters'])+'\n')
    else:(out/'lists'/(slug+'.list')).unlink(missing_ok=True)
    row=dict(name=name,fname=filename,slug=slug,kind=kind,rewrite=len(body),filter=len(result['filters']),
             hosts=hosts,notes=notes,has_list=bool(listpath),snippet=snippet,list=listpath)
    if supplement:row['supplements']=supplement['sources']
    if keep_alternative_list:
        row.update(embedded_filter=True, qx_min_version=qx_min_version, alternative_list=True)
    if external:
        row.update(source=external['source'], snapshot=external['snapshot'],
                   upstream_sha256=hashlib.sha256(source_bytes).hexdigest(),
                   embedded_filter=embedded, qx_min_version=external['qx_min_version'])
    return row,body,result['filters'],result['tasks']

def build(out,raw=RAW):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    remove_retired(out)
    rows=[];assets={};rewrites=[];filters=[];tasks=[];hosts=[]
    per_app,scope=supplements()
    selected=[(n,f,SLUGS[f],'snippets') for n,f,_ in C.ENABLED]+[
        ('哔哩哔哩去广告','Bilibili_remove_ads.lpx','bilibili','snippets')]
    selected += [(meta['name'],filename,meta['slug'],'snippets') for filename,meta in EXTERNAL_PLUGINS.items()]
    emitted={slug for _,_,slug,_ in selected}
    if set(per_app)-emitted:raise ValueError('Shared rules have unassigned app targets: '+str(set(per_app)-emitted))
    seen_rewrites=set();seen_filters=set()
    for name,filename,slug,kind in selected:
        row,rw,ft,tk=emit(out,name,filename,slug,kind,raw,assets,per_app.get(slug))
        rows.append(row);hosts+=row['hosts']
        unique_rw=[line for line in rw if line not in seen_rewrites]
        unique_ft=[line for line in ft if line not in seen_filters]
        if unique_rw:rewrites+=['# '+name]+unique_rw
        if unique_ft:filters+=['# '+name]+unique_ft
        seen_rewrites.update(rw);seen_filters.update(ft)
        tasks += tk
    hosts=list(dict.fromkeys(hosts))
    for name in ['updatable.jq','search_poi_detail.jq']:
        source=Path(C.JQSRC)/'Amap'/name
        if not source.is_file():raise ValueError('Missing jq source: '+str(source))
        write(out/'jq'/name,source.read_text())
    rewrite_remote=['# 添加到 [rewrite_remote]；含 QQ 音乐混合资源兼容版，建议 QX 1.5.2(854)+。']
    filter_remote=['# 添加到 [filter_remote]；保留各文件自带策略，不统一强制 REJECT。']
    for row in rows:
        if row['snippet']:
            rewrite_remote.append(f"{raw}/{row['snippet']}, tag={row['name']}, update-interval=86400, opt-parser=false, enabled=true")
        if row['list'] and not row.get('alternative_list'):
            filter_remote.append(f"{raw}/{row['list']}, tag={row['name']}, update-interval=86400, opt-parser=false, enabled=true")
    write(out/'config/rewrite_remote.conf','\n'.join(rewrite_remote)+'\n')
    write(out/'config/filter_remote.conf','\n'.join(filter_remote)+'\n')
    write(out/'config/mitm.txt','hostname = '+', '.join(hosts)+'\n')
    write(out/'config/shared-scope.json',json.dumps(scope,ensure_ascii=False,indent=2)+'\n')
    unique=dict(rewrites=len(seen_rewrites),filters=len(seen_filters))
    deduped=dict(rewrites=sum(r['rewrite'] for r in rows)-unique['rewrites'],
                 filters=sum(r['filter'] for r in rows)-unique['filters'])
    info=dict(raw=raw,rows=rows,hosts=hosts,assets=assets,unique=unique,deduped=deduped,limitations=[
        '小红书 QUIC 处理由主配置承担；udp_drop_list = 443, STUN 可阻止常用 UDP 443 上的 QUIC，作用范围为全局，不保证覆盖其它端口。',
        '公共规则按所选服务收窄；共享端点仍可能被其它 App 使用，不能视作按进程隔离。',
        '本地模拟和语法检查不能代替手机 QX 实测。'])
    write(out/'build-info.json',json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    return info,rewrites,filters,tasks

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default=str(ROOT/'repo'))
    parser.add_argument('--raw-base',default=RAW)
    args=parser.parse_args()
    info,*_=build(args.out,args.raw_base.rstrip('/'))
    print(json.dumps({'plugins':len(info['rows']),'rewrites':sum(r['rewrite'] for r in info['rows']),
                      'filters':sum(r['filter'] for r in info['rows']),'hosts':len(info['hosts']),
                      'scripts':len(info['assets']),'output':str(Path(args.out).resolve())},ensure_ascii=False))

if __name__=='__main__':main()
