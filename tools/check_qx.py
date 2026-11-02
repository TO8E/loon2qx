#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 qx/ 产物：QX 语法合规、jq 可编译、正则可编译、无 Loon 残留。"""
import glob, hashlib, json, os, re, subprocess, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QX = os.path.join(ROOT, "qx")
if "--dir" in sys.argv:
    QX = os.path.abspath(sys.argv[sys.argv.index("--dir") + 1])
TYPES = {"reject", "reject-200", "reject-img", "reject-dict", "reject-array",
         "302", "307", "jsonjq-response-body", "jsonjq-request-body",
         "script-request-header", "script-request-body",
         "script-response-header", "script-response-body",
         "script-echo-response", "echo-response"}
FILTER_TYPES = {"host", "host-suffix", "host-keyword", "host-wildcard", "ip-cidr",
                "ip6-cidr", "geoip", "ip-asn", "user-agent"}
LOON_LEFTOVER = ["${url}", "script(", "reject_dict", "reject_img", "response.json.",
                 "jq_file(", "redirect(", "#!name=", "[MitM]", "DOMAIN-SUFFIX,"]
bad, counts = [], dict(rewrite=0, filter=0, jqhdr=0)


def jq_ok(prog):
    r = subprocess.run(["jq", "-n", "if false then ("+prog+") else null end"], capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip().splitlines()[:1]


def check_rewrite(path, line, no):
    global counts
    if line.lower().startswith(("hostname", "hostname =")):
        return                       # 远程 rewrite 源首行 hostname 声明
    marker = ' url-and-header ' if ' url-and-header ' in line else ' url '
    if marker not in line:
        bad.append(f"{path}:{no} 缺少 ' url ' 分隔: {line[:70]}")
        return
    pat, rest = line.split(marker, 1)
    kind, _, arg = rest.partition(" ")
    kind, arg = kind.strip(), arg.strip()
    counts["rewrite"] += 1
    if kind not in TYPES:
        bad.append(f"{path}:{no} 未知重写类型 {kind}")
    try:
        for pattern in (pat.split(' ',1) if marker==' url-and-header ' else [pat]):
            re.compile(pattern)
    except re.error as e:
        bad.append(f"{path}:{no} 正则不合法: {e}")
    if kind.startswith("jsonjq"):
        if not (arg.startswith("'") and arg.endswith("'")) and not arg.startswith('"'):
            bad.append(f"{path}:{no} jq 未加引号")
        prog = arg[1:-1] if arg[:1] == arg[-1:] and arg[:1] in "'\"" else arg
        ok, err = jq_ok(prog)
        counts["jqhdr"] += 1
        if not ok:
            bad.append(f"{path}:{no} jq 编译失败: {err}")
    if kind in ("302", "307") and not arg.startswith("http"):
        bad.append(f"{path}:{no} 重定向目标异常: {arg[:50]}")
    if kind.startswith("script") and not arg.startswith("http"):
        bad.append(f"{path}:{no} 脚本地址异常: {arg[:50]}")


def check_file(path, sectioned=True):
    if "[rewrite_local]" not in open(path, encoding="utf-8").read():
        sectioned = False           # 裸行格式的远程 rewrite 源
    sec, no = None, 0
    for raw in open(path, encoding="utf-8"):
        no += 1
        line = raw.rstrip("\n")
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        m = re.match(r"^\[(\w+)\]$", s)
        if m:
            sec = m.group(1)
            continue
        if sectioned and sec == "rewrite_local":
            check_rewrite(os.path.basename(path), s, no)
        elif sectioned and sec == "filter_local":
            parts = [p.strip() for p in s.split(",")]
            counts["filter"] += 1
            if len(parts) < 3:
                bad.append(f"{path}:{no} filter 行字段不足: {s}")
            elif parts[0] not in FILTER_TYPES and parts[0] != "final":
                bad.append(f"{path}:{no} 未知 filter 类型 {parts[0]}")
        elif not sectioned:
            check_rewrite(os.path.basename(path), s, no)
        for k in LOON_LEFTOVER:
            if k in s:
                bad.append(f"{path}:{no} 残留 Loon 语法 {k}")


def main():
    snips = glob.glob(os.path.join(QX, "snippets/*.snippet")) + \
        glob.glob(os.path.join(QX, "base/*.snippet"))
    if os.path.exists(os.path.join(QX, "build-info.json")):     # 仓库产物：远程源必须裸行
        for f in snips:
            body = open(f, encoding="utf-8").read()
            for hdr in ("[rewrite_local]", "[mitm]", "[filter_local]"):
                if hdr in body:
                    bad.append(f"{os.path.basename(f)} 含段头 {hdr}，QX 远程源会报 invalid line")
    for f in sorted(snips):
        check_file(f, True)
    info_path = os.path.join(QX,'build-info.json')
    if os.path.exists(info_path):
        info=json.load(open(info_path,encoding='utf-8'))
        for rel,meta in info.get('assets',{}).items():
            path=os.path.join(QX,rel)
            if not os.path.isfile(path):
                bad.append('缺少脚本 '+rel);continue
            raw=open(path,'rb').read()
            if '[mirror-stub]' in raw.decode('utf-8',errors='replace'):
                bad.append('脚本是占位文件 '+rel)
            if hashlib.sha256(raw).hexdigest()!=meta['sha256']:
                bad.append('脚本与构建记录不一致 '+rel)
            checked=subprocess.run(['node','--check',path],capture_output=True,text=True)
            if checked.returncode:bad.append('JS 语法错误 '+rel)
        for file in snips:
            for no,line in enumerate(open(file,encoding='utf-8'),1):
                if line.lstrip().startswith('#'):continue
                for url in re.findall(r'https?://[^\s]+',line):
                    if not url.startswith(info['raw']+'/'):continue
                    rel=urllib.parse.unquote(url[len(info['raw'])+1:])
                    if not os.path.isfile(os.path.join(QX,rel)):bad.append(f'{file}:{no} 依赖不存在 {rel}')
        for filename in ['rewrite_remote.conf','filter_remote.conf']:
            for no,line in enumerate(open(os.path.join(QX,'config',filename),encoding='utf-8'),1):
                if not line.strip() or line.startswith('#'):continue
                url=line.split(',',1)[0]
                rel=urllib.parse.unquote(url[len(info['raw'])+1:])
                path=os.path.join(QX,rel)
                if not os.path.isfile(path):bad.append(f'{filename}:{no} 资源不存在 {rel}')
                elif filename=='rewrite_remote.conf' and not re.search(r'\surl(?:-and-header)?\s',open(path,encoding='utf-8').read()):
                    bad.append(f'{filename}:{no} 空重写资源 {rel}')
    for f in sorted(glob.glob(os.path.join(QX, "lists/*.list")) +
                    glob.glob(os.path.join(QX, "base/*.list"))):   # 纯 filter 行, 无段头
        for no, line in enumerate(open(f, encoding="utf-8"), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = [p.strip() for p in s.split(",")]
            counts["filter"] += 1
            if len(parts) < 3 or parts[0] not in FILTER_TYPES:
                bad.append(f"{os.path.basename(f)}:{no} filter 行异常: {s}")
    for f in sorted(glob.glob(os.path.join(QX, "merged/*.conf"))):
        if os.path.basename(f)=='rewrite_local.conf':check_file(f,False)
        elif os.path.basename(f)=='filter_local.conf':
            for no,line in enumerate(open(f,encoding='utf-8'),1):
                if line.strip() and not line.startswith('#'):
                    parts=[x.strip() for x in line.split(',')]
                    if len(parts)<3 or parts[0] not in FILTER_TYPES:bad.append(f'{f}:{no} 无效分流')

    repf = os.path.join(QX, "report.json")
    if os.path.exists(repf):
        rep = json.load(open(repf, encoding="utf-8"))
        n = len(rep["summary"])
    else:
        rep = json.load(open(os.path.join(QX, "build-info.json"), encoding="utf-8"))
        n = len(rep["rows"])
    print(f"插件 {n} 个 | 重写行 {counts['rewrite']} | filter 行 {counts['filter']} "
          f"| jq 程序 {counts['jqhdr']}")
    hostfile = next((f for f in (os.path.join(QX, "merged/mitm.hostname.txt"),
                                 os.path.join(QX, "config/mitm.txt")) if os.path.exists(f)), None)
    if hostfile:
        hosts = open(hostfile, encoding="utf-8").read().split("=", 1)[-1]
        print(f"MITM hostname: {len([h for h in hosts.split(',') if h.strip()])} 个")
    print(f"问题 {len(bad)} 条")
    for b in bad[:25]:
        print("  -", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
