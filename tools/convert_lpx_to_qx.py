#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loon .lpx  ->  Quantumult X 原生写法
------------------------------------
输入: mirror/upstream/kelee.one/Tool/Loon/Lpx/<file>.lpx (hub.kelee.one 原始插件)
输出: qx/ 目录

映射规则(均以 QX sample.conf 为准, 不在 filter 里臆造 url-regex):
  [Rule] DOMAIN / DOMAIN-SUFFIX / DOMAIN-KEYWORD / IP-CIDR  ->  [filter_local] host / host-suffix / host-keyword / ip-cidr
  [Rule] URL-REGEX ... REJECT                               ->  [rewrite_local] ^... url reject      (QX filter 无 url-regex)
  [Rewrite] request|response ... then reject_dict(200)      ->  ^... url reject-dict                 (200 + {})
  [Rewrite] ... reject_img(200)                             ->  ^... url reject-img                  (200 + 1px gif)
  [Rewrite] ... reject(404)                                 ->  ^... url reject                      (QX reject 即 404)
  [Rewrite] ... response.json.delete(p)                     ->  jsonjq-response-body 'del(p)'
  [Rewrite] ... response.json.jq("X")                       ->  jsonjq-response-body 'X'
  [Rewrite] ... response.json.jq_file(url)                  ->  jsonjq-response-body '<内联 jq>'
  [Rewrite] ... response.json.replace(p, v)                 ->  jsonjq-response-body 'p = v'
  [Rewrite] ... redirect(307,"u")                           ->  url 307 u
  [Script] request ... requires_body=true                   ->  script-request-body  <script>
  [Script] request ... (无 requires_body)                    ->  script-request-header
  [Script] response ...                                     ->  script-response-body
  cron ... then script(...)                                 ->  [task_local] 行
  [MitM] hostname=a, b                                      ->  [mitm] hostname = a, b

同一 URL(regex+阶段) 的多条 response.json.* 按文件顺序合并成一条 jq 程序 —— QX 同一 URL 只执行首条重写。

用法:  python3 scripts/convert_lpx_to_qx.py [--script-base URL]
"""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "mirror/upstream/kelee.one/Tool/Loon/Lpx")
JQSRC = os.path.join(ROOT, "mirror/upstream/kelee.one/Resource/JQLang")
MIRROR = os.path.join(ROOT, "mirror")
QX = os.path.join(ROOT, "qx")
for d in ("snippets", "lists", "merged", "jq"):
    os.makedirs(os.path.join(QX, d), exist_ok=True)

BASE = open(os.path.join(ROOT, "build/base.txt")).read().strip() \
    if os.path.exists(os.path.join(ROOT, "build/base.txt")) else ""
SCRIPT_BASE = ""      # --script-base 时把 kelee 脚本地址换成自建镜像

POLICY = {"REJECT": "reject", "DIRECT": "direct", "PROXY": "兜底后备"}

# ── 已启用的、来自 hub.kelee.one 的插件 ────────────────────────────────
# (显示名, 插件文件, 说明)
ENABLED = [
    ("QQ音乐去广告", "QQMusic_remove_ads.lpx", "纯域名拦截"),
    ("京东去广告", "JD_remove_ads.lpx", "URL-REGEX + jsonjq + 响应脚本"),
    ("下厨房去广告", "XiaChuFang_remove_ads.lpx", "reject-dict + jsonjq"),
    ("淘宝去广告", "Taobao_remove_ads.lpx", "域名拦截 + reject-dict + 响应脚本"),
    ("闲鱼去广告", "FleaMarket_remove_ads.lpx", "纯 jsonjq"),
    ("小红书去广告", "RedPaper_remove_ads.lpx", "reject-img/dict + jsonjq + 响应脚本"),
    ("彩云天气去广告", "ColorfulClouds_remove_ads.lpx", "域名拦截 + reject-dict + 响应脚本"),
    ("12306去广告", "12306_remove_ads.lpx", "直连规则 + jsonjq + 请求头脚本"),
    ("酷安去广告", "CoolApk_remove_ads.lpx", "纯 jsonjq"),
    ("高德地图去广告", "Amap_remove_ads.lpx", "大量 jsonjq + 2 个 jq_file"),
    ("掌上英雄联盟去广告", "LOL_Bible_remove_ads.lpx", "纯 reject-dict"),
    ("朴朴超市去广告", "PuPuMall_remove_ads.lpx", "reject(404) + 响应脚本"),
    ("Google搜索重定向", "Google.lpx", "redirect -> 307/302"),
]

# 已启用但按规则跳过(原生 QX / 无 kelee 对应 / Loon 专属)
SKIPPED = {
    "YouTube去广告": ("YouTube_remove_ads.lpx",
                   "kelee 版是 Loon 专属 JS（binary_body_mode + $argument 参数注入），QX 无等价；保留你现有的 ddgksf2013 原生 conf"),
    "BoxJS": ("BoxJs.lpx", "kelee 插件只是 chavyleung chavy.boxjs.js 的 Loon 外壳；QX 官方 boxjs.rewrite.quanx.conf 即原生"),
    "Sub-Store": ("Sub-Store.lpx", "kelee 插件只是官方 JS 的 Loon 外壳；QX 官方 QX.snippet 即原生"),
    "Script-Hub": ("Script-Hub.lpx", "kelee 插件只是官方 script-hub.js 的 Loon 外壳；QX 官方 script-hub.qx.conf 即原生"),
    "中国联通去广告": (None, "kelee 无对应插件（你用的是 ddgksf2013 原生）"),
    "一汽大众去广告": (None, "kelee 无对应插件（zirawell 原生）"),
    "AdGuard": (None, "kelee 无对应插件（yfamilys 原生）"),
    "哔哩哔哩增强": (None, "你已用 kokoryh 原生改写到 rewrite_local；kelee 的 B 站插件是另一套规则，未启用"),
    "小黑盒去广告": (None, "你用的是 wxs0625 Loon 插件转换版，非 kelee 源"),
    "平安好车主去广告": (None, "配置中 enabled=false"),
    "拼多多去广告": (None, "配置中 enabled=false"),
    "Speedtest-备选": (None, "配置中 enabled=false"),
    "YouTube备选-仅信息流": (None, "配置中 enabled=false"),
    "途虎签到 / PingMe签到": (None, "配置中 enabled=false"),
}

PAT = r"/(?P<re>(?:\\.|[^/\\])*)/(?P<flag>[a-z]*)"
REWRITE_RE = re.compile(
    r"^\s*(?P<stage>request|response)\s+if\s+\$\{url\}\s*~=\s*" + PAT +
    r"\s+then\s+(?P<body>.+?)\s*$")
SCRIPT_RE = re.compile(
    r"^\s*(?P<stage>request|response)\s+if\s+\$\{url\}\s*~=\s*" + PAT +
    r"\s+then\s+script\(\"(?P<url>[^\"]+)\"(?P<args>[^)]*)\)\s*(?:with\s+(?P<opts>.*))?$")
CRON_RE = re.compile(r"^\s*cron\s+(?P<expr>.+?)\s+then\s+script\(\"(?P<url>[^\"]+)\"(?P<args>[^)]*)\)\s*(?:with\s+(?P<opts>.*))?$")
RULE_RE = re.compile(r"^\s*(?P<type>[A-Za-z0-9-]+)\s*,\s*(?P<rest>.+?)\s*$")


def read(path):
    return open(path, encoding="utf-8", errors="replace").read()


def sections(text):
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^\[(\w+)\]$", line.strip())
        if m:
            if cur:
                out.setdefault(cur, []).extend(buf)
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur:
        out.setdefault(cur, []).extend(buf)
    return out


IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def jq_path(p):
    """data.foo.920bar -> .data.foo."920bar"（jq 要求非标识符字段加引号）"""
    p = p.strip()
    if p.startswith("$"):
        p = p[1:]
    p = p.lstrip(".")
    out = ""
    for seg in [x for x in p.split(".") if x != ""]:
        out += ("." + seg) if IDENT.match(seg) else ('["' + seg.replace('"', '\\"') + '"]')
    return out or "."


def split_args(s):
    """把 "a", "b" 或 [..],[..] 拆开(处理字符串与嵌套括号)"""
    parts, buf, depth, inq, esc = [], "", 0, False, False
    for ch in s:
        if inq:
            buf += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                inq = False
            continue
        if ch == '"':
            inq = True
            buf += ch
        elif ch == "[":
            depth += 1
            buf += ch
        elif ch == "]":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    return parts


def unq(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s


def as_jq_value(v):
    v = unq(v)
    if v in ("{}", "[]", "true", "false", "null"):
        return v
    if re.fullmatch(r"-?\d+(\.\d+)?", v):
        return v
    if v.startswith("[") or v.startswith("{"):
        return v
    return json.dumps(unq(v), ensure_ascii=False)


def jq_comment_strip(expr):
    """去掉 jq 里的 # 注释并压成单行(QX 配置文件是逐行的)"""
    out, inq, esc, i = [], False, False, 0
    while i < len(expr):
        c = expr[i]
        if inq:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                inq = False
            i += 1
            continue
        if c == '"':
            inq = True
            out.append(c)
            i += 1
            continue
        if c == "#":
            while i < len(expr) and expr[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def local_jq(url):
    """把 kelee 的 jq_file 从镜像里取出来内联"""
    host, _, rest = url.split("://", 1)[1].partition("/")
    path = os.path.join(MIRROR, "upstream", host, rest)
    if not os.path.exists(path):
        return None, None
    body = jq_comment_strip(read(path))
    return body, path


def parse_and(line):
    """拆 Loon 的 AND, ((KIND, v), (KIND, v), ...), POLICY"""
    m = re.match(r"^AND,\s*(.*),\s*([A-Z-]+)\s*$", line.strip(), re.S)
    if not m:
        return dict(kws=[], sufs=[], protos=[], uas=[], urls=[], policy="REJECT")
    body, policy = m.group(1), m.group(2)
    get = lambda kind: re.findall(r"\(\s*" + kind + r"\s*,\s*([^)]+?)\s*\)", body)   # noqa: E731
    return dict(kws=get("DOMAIN-KEYWORD"),
                sufs=get("DOMAIN-SUFFIX") + get("DOMAIN"),
                protos=get("PROTOCOL"), uas=get("USER-AGENT"),
                urls=get("URL-REGEX"), policy=policy)


def map_policy(p):
    return POLICY.get(p.strip().upper(), p.strip())


def convert(show, fname):
    text = read(os.path.join(SRC, fname))
    sec = sections(text)
    filters, rewrites, tasks, hosts, notes = [], [], [], [], []
    jq_files = {}

    # ---- [Rule] ----
    for line in sec.get("Rule", []):
        if not line.strip() or line.strip().startswith("#") or line.strip().startswith(";"):
            continue
        if line.strip().upper().startswith("AND,"):
            a = parse_and(line)
            pol = map_policy(a["policy"])
            if a["protos"]:
                notes.append("原 AND 规则含 PROTOCOL 条件，QX 无协议匹配；"
                             "等价做法是在 [general] 加 `udp_drop_list = 443, STUN, QUIC`"
                             f"（你已有 443, STUN）— 原规则: {line.strip()[:70]}…")
            elif a["sufs"] and a["kws"]:
                for k in a["kws"]:
                    for sfx in a["sufs"]:
                        filters.append(f"host-wildcard, *{k}*{sfx}, {pol}")
                notes.append(f"AND(关键字+后缀) → host-wildcard 近似: "
                             f"*{'/'.join(a['kws'])}*.{'/'.join(a['sufs'])}")
            elif a["kws"]:
                k = max(a["kws"], key=len)
                filters.append(f"host-keyword, {k}, {pol}")
                notes.append(f"AND(多关键字) → 取最长关键字 host-keyword {k} 近似")
            elif a["uas"]:
                filters.append(f"user-agent, {a['uas'][0]}, {pol}")
                notes.append(f"AND(URL+UA) → 用 user-agent {a['uas'][0]} 近似")
            else:
                notes.append(f"无法等价: `{line.strip()[:80]}`")
            continue
        m = RULE_RE.match(line)
        if not m:
            notes.append(f"未识别的规则: {line.strip()}")
            continue
        typ, rest = m.group("type").upper(), m.group("rest")
        parts = [p.strip() for p in rest.split(",")]
        value = parts[0]
        flags = [f for f in parts[1:] if f.lower() in ("no-resolve", "force-remote-dns", "pre-matching")]
        cand = [f for f in parts[1:] if f.lower() not in ("no-resolve", "force-remote-dns", "pre-matching")]
        policy = map_policy(cand[-1] if cand else "REJECT")
        if flags:
            notes.append("QX 无 " + "/".join(flags) + " 参数，已省略（ip-cidr 直接匹配目的 IP，不影响结果）")
        if typ == "DOMAIN":
            filters.append(f"host, {value}, {policy}")
        elif typ == "DOMAIN-SUFFIX":
            filters.append(f"host-suffix, {value}, {policy}")
        elif typ == "DOMAIN-KEYWORD":
            filters.append(f"host-keyword, {value}, {policy}")
        elif typ == "IP-CIDR":
            filters.append(f"ip-cidr, {value}, {policy}")
        elif typ in ("IP-CIDR6", "IP6-CIDR"):
            filters.append(f"ip6-cidr, {value}, {policy}")
        elif typ == "IP-ASN":
            filters.append(f"ip-asn, {value}, {policy}")
        elif typ == "GEOIP":
            filters.append(f"geoip, {value}, {policy}")
        elif typ == "USER-AGENT":
            filters.append(f"user-agent, {value.strip(chr(34))}, {policy}")
            notes.append(f"USER-AGENT 规则 → QX user-agent filter（{value.strip(chr(34))}）")
        elif typ == "URL-REGEX":
            rewrites.append([value.strip('"'), "response", ("reject", None),
                             "URL-REGEX REJECT → QX 无 url-regex filter，改用 rewrite reject(404)"])
        else:
            notes.append(f"未映射的规则类型 {typ}: {line.strip()}")

    # ---- [Rewrite] ----
    body_ops = {}       # (stage, re) -> [jq 片段]
    for line in sec.get("Rewrite", []):
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = REWRITE_RE.match(line)
        if not m:
            notes.append(f"未识别的 rewrite: {line.strip()[:90]}")
            continue
        stage, rx, body = m.group("stage"), m.group("re"), m.group("body").strip()
        m2 = re.match(r"^([\w.]+)\((.*)\)$", body, re.S)
        if not m2:
            notes.append(f"未识别的动作: {body[:60]}")
            continue
        act, arg = m2.group(1), m2.group(2).strip()

        if act == "reject_dict":
            rewrites.append([rx, stage, ("reject-dict", None), f"reject_dict({arg}) → reject-dict"])
        elif act == "reject_img":
            rewrites.append([rx, stage, ("reject-img", None), "reject_img → reject-img"])
        elif act == "reject":
            code = arg or "404"
            t = "reject" if code in ("404", "") else ("reject-200" if code == "200" else "reject")
            rewrites.append([rx, stage, (t, None), f"reject({code}) → {t}"])
        elif act == "redirect":
            mm = re.match(r"(\d{3})\s*,\s*\"(.*)\"", arg)
            if mm:
                code, target = mm.group(1), mm.group(2)
                # Loon 的 redirect 会自动带原 path/query；QX 必须显式 $1
                if "$1" not in target:
                    rx2 = rx.rstrip("$") if rx.endswith("$") else rx
                    rx2 = re.sub(r"\((?!\?)", "(?:", rx2)          # 原有捕获组改非捕获，避免抢 $1
                    rx2 = rx2 + "(.*)" + ("$" if rx.endswith("$") else "")
                    target = target + "$1"
                    rx, note = rx2, (f"redirect({code}) → {code}；已补 (.*) \$1 保留原路径"
                                     "（Loon 隐式携带，QX 需显式）")
                else:
                    note = f"redirect({code}) → {code}"
                rewrites.append([rx, stage, (code, target), note])
            else:
                notes.append(f"未识别的 redirect: {body[:60]}")
        elif act == "response.json.delete":
            paths = split_args(arg)
            if len(paths) == 1 and paths[0].startswith("["):
                paths = split_args(paths[0][1:-1])
            js = "del(" + ", ".join(jq_path(unq(p)) for p in paths) + ")"
            body_ops.setdefault((stage, rx), []).append(js)
        elif act == "response.json.jq":
            expr = unq(arg)
            body_ops.setdefault((stage, rx), []).append(expr.strip())
        elif act == "response.json.jq_file":
            url = unq(arg)
            body, path = local_jq(url)
            if body is None:
                notes.append(f"jq_file 未落地: {url}")
                continue
            key = os.path.basename(path)
            jq_files[key] = body
            body_ops.setdefault((stage, rx), []).append(body)
        elif act == "response.json.replace":
            a, v = split_args(arg)
            ps = split_args(a[1:-1]) if a.startswith("[") else [a]
            vs = split_args(v[1:-1]) if v.startswith("[") else [v]
            frag = " | ".join(f"{jq_path(unq(p))} = {as_jq_value(x)}"
                              for p, x in zip(ps, vs))
            body_ops.setdefault((stage, rx), []).append(frag)
        else:
            notes.append(f"未映射的动作: {act}")

    for (stage, rx), frags in body_ops.items():
        prog = " | ".join(f"({f})" for f in frags) if len(frags) > 1 else frags[0]
        if "'" in prog:
            notes.append(f"jq 内含单引号，需手工处理: {rx[:50]}")
        note = (f"{len(frags)} 条 json 操作合并为 1 条 jq（QX 同 URL 只执行首条重写）"
                if len(frags) > 1 else "json 操作 → jsonjq")
        rewrites.append([rx, stage, ("jsonjq-" + stage + "-body", "'" + prog + "'"), note])

    # ---- [Script] ----
    for line in sec.get("Script", []):
        if not line.strip() or line.strip().startswith("#"):
            continue
        cm = CRON_RE.match(line)
        if cm:
            opts = cm.group("opts") or ""
            tag = re.search(r'tag="([^"]*)"', opts)
            enabled = "false" if re.search(r"enabled\s*=\s*false", opts) else "true"
            tasks.append(f"{cm.group('expr')} {cm.group('url')}, tag={tag.group(1) if tag else 'task'}, enabled={enabled}")
            continue
        sm = SCRIPT_RE.match(line)
        if not sm:
            notes.append(f"未识别的 script: {line.strip()[:90]}")
            continue
        stage, rx, url = sm.group("stage"), sm.group("re"), sm.group("url")
        opts = sm.group("opts") or ""
        requires_body = bool(re.search(r"requires[_ ]?body\s*=\s*(true|1)", opts))
        if sm.group("args").strip() and sm.group("args").strip() != "":
            notes.append(f"该脚本带内联参数 {{…}}，QX rewrite 不支持，需改用 $prefs/BoxJs: {url}")
        if stage == "request":
            kind = "script-request-body" if requires_body else "script-request-header"
        else:
            kind = "script-response-body"
        tag = re.search(r'tag="([^"]*)"', opts)
        rewrites.append([rx, stage, (kind, url), f"脚本 {tag.group(1) if tag else ''}".strip()])

    # ---- [MitM] ----
    for line in sec.get("MitM", []):
        m = re.match(r"^\s*hostname\s*=\s*(.+)$", line)
        if m:
            hosts += [h.strip() for h in m.group(1).split(",") if h.strip()]

    seen, uniq = set(), []
    for n in notes:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return dict(filters=filters, rewrites=rewrites, tasks=tasks, hosts=hosts,
                notes=uniq, jq=jq_files)


def fmt_rewrite(rw):
    rx, stage, (kind, arg), note = rw
    line = f"{rx} url {kind}" + (f" {arg}" if arg and kind not in ("reject", "reject-200",
                                                                  "reject-img", "reject-dict",
                                                                  "reject-array", "302", "307") else "")
    if kind in ("302", "307"):
        line = f"{rx} url {kind} {arg}"
    return line, note


def jq_ok(prog):
    r = subprocess.run(["jq", "-e", prog, "/dev/null"], capture_output=True, text=True)
    err = r.stderr.strip()
    return ("compile error" not in err and "syntax error" not in err), err.splitlines()[:2]


def main():
    global SCRIPT_BASE
    if "--script-base" in sys.argv:
        SCRIPT_BASE = sys.argv[sys.argv.index("--script-base") + 1]

    summary, all_rw, all_ft, all_tk, all_host, problems = [], [], [], [], [], []
    for show, fname, desc in ENABLED:
        r = convert(show, fname)
        rw_lines, notes, shown = [], list(r["notes"]), set()
        for rw in r["rewrites"]:
            line, note = fmt_rewrite(rw)
            rx, stage, (kind, arg), _ = rw
            if SCRIPT_BASE and arg and str(arg).startswith("https://kelee.one/") and kind.startswith("script"):
                rest = arg[len("https://kelee.one/"):]
                line = f"{rx} url {kind} {SCRIPT_BASE}/upstream/kelee.one/{rest}"
            if kind.startswith("jsonjq"):
                ok, err = jq_ok(arg[1:-1] if arg.startswith("'") else arg)
                if not ok:
                    problems.append((show, arg[:60], err))
            if note and note not in shown and any(
                    k in note for k in ("合并", "脚本", "URL-REGEX", "redirect", "reject(")):
                rw_lines.append(f"# {note}")
                shown.add(note)
            rw_lines.append(line)
        # 校验正则
        for rw in r["rewrites"]:
            try:
                re.compile(rw[0])
            except re.error as e:
                problems.append((show, "regex " + rw[0][:50], str(e)))

        slug = re.sub(r"[^\w]+", "_", fname.replace(".lpx", ""))
        # 单插件 snippet: [rewrite_local] + [mitm]
        snip = [f"# {show} ← hub.kelee.one/Tool/Loon/Lpx/{fname}",
                f"# 由 scripts/convert_lpx_to_qx.py 直译；{desc}",
                "", "[rewrite_local]"]
        snip += [l for l in rw_lines]
        if r["hosts"]:
            snip += ["", "[mitm]", "hostname = " + ", ".join(dict.fromkeys(r["hosts"]))]
        if notes:
            snip += ["", "# 注意"] + [f"# - {n}" for n in notes]
        open(os.path.join(QX, "snippets", slug + ".snippet"), "w", encoding="utf-8").write("\n".join(snip) + "\n")

        if r["filters"]:
            open(os.path.join(QX, "lists", slug + ".list"), "w", encoding="utf-8").write(
                "\n".join(r["filters"]) + "\n")
        for k, v in r["jq"].items():
            open(os.path.join(QX, "jq", f"{slug}__{k}"), "w", encoding="utf-8").write(v + "\n")

        all_rw += [f"# ── {show} ({fname})"] + [l for l in rw_lines]
        if r["filters"]:
            all_ft += [f"# {show}"] + r["filters"]
        if r["tasks"]:
            all_tk += [f"# {show}"] + r["tasks"]
        all_host += r["hosts"]
        for n in notes:
            print(f"    ! {show}: {n}")
        n_rw = sum(1 for l in rw_lines if not l.startswith("#"))
        summary.append(dict(name=show, file=fname, desc=desc,
                            rewrite=n_rw, filter=len(r["filters"]),
                            task=len(r["tasks"]), hosts=r["hosts"], notes=notes))

    open(os.path.join(QX, "merged", "rewrite_local.conf"), "w", encoding="utf-8").write(
        "# 全部已启用 kelee 插件的 QX 原生重写 —— 粘进 [rewrite_local]\n" + "\n".join(all_rw) + "\n")
    open(os.path.join(QX, "merged", "filter_local.conf"), "w", encoding="utf-8").write(
        "# 全部已启用 kelee 插件的 QX 原生分流 —— 粘进 [filter_local]（放在你现有规则之前）\n"
        + "\n".join(all_ft) + "\n")
    open(os.path.join(QX, "merged", "task_local.conf"), "w", encoding="utf-8").write(
        "\n".join(all_tk) + ("\n" if all_tk else "# 本批插件无 task\n"))
    open(os.path.join(QX, "merged", "mitm.hostname.txt"), "w", encoding="utf-8").write(
        ", ".join(dict.fromkeys(all_host)) + "\n")
    json.dump(dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), summary=summary,
                   skipped=SKIPPED, problems=problems),
              open(os.path.join(QX, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"{'插件':22s} {'重写':>4s} {'分流':>4s} {'任务':>4s}  MITM")
    for s in summary:
        print(f"{s['name']:22s} {s['rewrite']:4d} {s['filter']:4d} {s['task']:4d}  {len(s['hosts'])}")
    print(f"\n合计: 重写 {len([l for l in all_rw if not l.startswith('#')])} 条, "
          f"分流 {len([l for l in all_ft if not l.startswith('#')])} 条, "
          f"hostname {len(dict.fromkeys(all_host))} 个")
    if problems:
        print(f"\n!! 校验问题 {len(problems)} 条")
        for p in problems[:10]:
            print("  ", p)


if __name__ == "__main__":
    main()
