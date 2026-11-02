#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 qx/ 产物：QX 语法合规、jq 可编译、正则可编译、无 Loon 残留。"""
import glob, json, os, re, subprocess, sys

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
    r = subprocess.run(["jq", "-e", prog, "/dev/null"], capture_output=True, text=True)
    return "error" not in r.stderr.lower(), r.stderr.strip().splitlines()[:1]


def check_rewrite(path, line, no):
    global counts
    if line.lower().startswith(("hostname", "hostname =")):
        return                       # 远程 rewrite 源首行 hostname 声明
    if " url " not in line:
        bad.append(f"{path}:{no} 缺少 ' url ' 分隔: {line[:70]}")
        return
    pat, rest = line.split(" url ", 1)
    kind, _, arg = rest.partition(" ")
    kind, arg = kind.strip(), arg.strip()
    counts["rewrite"] += 1
    if kind not in TYPES:
        bad.append(f"{path}:{no} 未知重写类型 {kind}")
    try:
        re.compile(pat)
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
        check_file(f, True)

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
