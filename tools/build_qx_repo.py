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

def write(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')

def remove_retired(out):
    for name in ['snippets/caiyun.snippet','lists/caiyun.list','js/ColorfulClouds/ColorfulClouds_remove_ads.js',
                 'snippets/ColorfulClouds_remove_ads.snippet','lists/ColorfulClouds_remove_ads.list','snippets/qqmusic.snippet',
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

def bili_navigation_asset(out,assets):
    tool_dir=Path(__file__).resolve().parent
    original=(tool_dir/'upstream/bilibili_json.js').read_text(encoding='utf-8')
    helper=(tool_dir/'bilibili-navigation.js').read_text(encoding='utf-8')
    old='const e=["首页","动态","我的"];i.data.bottom=i.data.bottom.filter((i=>e.includes(i.name)))'
    if original.count(old)!=1:raise ValueError('Bilibili upstream navigation changed; review patch before rebuilding')
    patched=original.replace(old,'i.data.bottom=qxBilibiliBottomTabs(i.data.bottom)')
    source='https://raw.githubusercontent.com/kokoryh/Script/master/js/bilibili_json.js'
    relative='js/Bilibili/bilibili_json.js'
    adapted=C.adapt_script('// Upstream: '+source+'\n'+helper+'\n'+patched,relative)
    write(out/relative,adapted)
    assets[relative]=dict(source=source,upstream_sha256=hashlib.sha256(original.encode()).hexdigest(),
                         sha256=hashlib.sha256(adapted.encode()).hexdigest(),adapted=True,
                         purpose='保留动态/关注底栏，兼容名称变化；未知底栏结构保留原样。')

def emit(out,name,filename,slug,kind,raw,assets,supplement=None):
    result=C.convert(name,filename) if filename else dict(rewrites=[],filters=[],notes=[],hosts=[],tasks=[])
    supplement=supplement or {}
    result['rewrites']=supplement.get('rewrites',[])+result['rewrites']
    result['filters']=list(dict.fromkeys(supplement.get('filters',[])+result['filters']))
    native=[]
    native_file={'bilibili':'bilibili-enhance.snippet'}.get(slug)
    if native_file:
        template=(Path(__file__).resolve().parent/native_file).read_text(encoding='utf-8')
        for line in template.splitlines():
            if line.startswith('hostname = '):result['hosts'] += [h.strip() for h in line.split('=',1)[1].split(',')]
            elif line.strip() and not line.startswith('#'):
                if ' url ' not in line:raise ValueError('Invalid native rewrite source: '+native_file)
                native.append(line.replace('__RAW_BASE__',raw))
    hosts=C.complete_hosts(result['rewrites'],result['hosts'])
    added=[h for h in hosts if h not in result['hosts']]
    notes=list(dict.fromkeys(supplement.get('notes',[])+result['notes']))
    if supplement:
        notes.append('已并入本 App 的 HTTPDNS/广告域名配套；来源和分配见 config/shared-scope.json。')
    if slug=='bilibili':
        notes.append('完整远程 B 站增强；启用后删除或停用旧的本地 B 站重写块，避免重复。')
        notes.append('来源：https://raw.githubusercontent.com/kokoryh/Script/master/Surge/module/bilibili.sgmodule')
    if slug=='xiaoheihe':
        notes.append('原作者：可莉；忠实保留上游 jq 逻辑（删除大写 PROTOCOL，无外部 JS）。')
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
    snippet=f'{kind}/{slug}.snippet' if body else None
    if snippet:
        header=([f"hostname = {', '.join(hosts)}"] if hosts else [])
        header += [f'# {name}']
        if filename:header.append(f'# Source: https://kelee.one/Tool/Loon/Lpx/{filename}')
        header += ['# Shared source: '+s['source'] for s in supplement.get('sources',[])]
        header += ['# Generated by loon2qx. See README for compatibility limits.']
        header += ['# '+note for note in notes]
        write(out/snippet,'\n'.join(header+body)+'\n')
    else:(out/kind/(slug+'.snippet')).unlink(missing_ok=True)
    listpath=None
    if result['filters']:
        listpath=f'lists/{slug}.list'
        header=f'# {name}：本 App 分流及已合并的公共配套\n'
        if supplement:header+='# 公共条目来源及分配见 config/shared-scope.json。\n'
        write(out/listpath,header+'\n'.join(result['filters'])+'\n')
    else:(out/'lists'/(slug+'.list')).unlink(missing_ok=True)
    row=dict(name=name,fname=filename,slug=slug,kind=kind,rewrite=len(body),filter=len(result['filters']),
             hosts=hosts,notes=notes,has_list=bool(listpath),snippet=snippet,list=listpath)
    if supplement:row['supplements']=supplement['sources']
    return row,body,result['filters'],result['tasks']

def build(out,raw=RAW):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    remove_retired(out)
    rows=[];assets={};rewrites=[];filters=[];tasks=[];hosts=[]
    per_app,scope=supplements()
    selected=[(n,f,SLUGS[f],'snippets') for n,f,_ in C.ENABLED]+[
        ('B站增强',None,'bilibili','snippets')]
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
    bili_navigation_asset(out,assets)
    for name in ['updatable.jq','search_poi_detail.jq']:
        source=Path(C.JQSRC)/'Amap'/name
        if not source.is_file():raise ValueError('Missing jq source: '+str(source))
        write(out/'jq'/name,source.read_text())
    rewrite_remote=['# 添加到 [rewrite_remote]；纯分流插件不生成空重写引用。']
    filter_remote=['# 添加到 [filter_remote]；保留各文件自带策略，不统一强制 REJECT。']
    for row in rows:
        if row['snippet']:
            rewrite_remote.append(f"{raw}/{row['snippet']}, tag={row['name']}, update-interval=86400, opt-parser=false, enabled=true")
        if row['list']:
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
