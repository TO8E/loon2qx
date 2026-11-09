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
import itertools, json, os, re, sre_parse, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = next((p for p in (os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE)))
             if os.path.isdir(os.path.join(p, "mirror"))), os.path.dirname(HERE))
SRC = os.path.join(ROOT, "mirror/upstream/kelee.one/Tool/Loon/Lpx")
JQSRC = os.path.join(ROOT, "mirror/upstream/kelee.one/Resource/JQLang")
MIRROR = os.path.join(ROOT, "mirror")
QX = os.path.join(ROOT, "qx")

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
    ("12306去广告", "12306_remove_ads.lpx", "直连规则 + jsonjq + 请求头脚本"),
    ("酷安去广告", "CoolApk_remove_ads.lpx", "纯 jsonjq"),
    ("高德地图去广告", "Amap_remove_ads.lpx", "大量 jsonjq + 2 个 jq_file"),
    ("掌上英雄联盟去广告", "LOL_Bible_remove_ads.lpx", "纯 reject-dict"),
    ("朴朴超市去广告", "PuPuMall_remove_ads.lpx", "reject(404) + 响应脚本"),
    ("Google搜索重定向", "Google.lpx", "redirect -> 307/302"),
    ("小黑盒去广告", "XiaoHeiHe_remove_ads.lpx", "reject-dict + jsonjq；可莉原版逻辑"),
]

# 已启用但按规则跳过(原生 QX / 无 kelee 对应 / Loon 专属)
SKIPPED = {
    "YouTube去广告": ("YouTube_remove_ads.lpx",
                   "不在本次转换范围；binary_body_mode 和参数需要单独验证，不能仅凭字段名认定 QX 不支持；保留现有 QX 方案"),
    "BoxJS": ("BoxJs.lpx", "kelee 插件只是 chavyleung chavy.boxjs.js 的 Loon 外壳；QX 官方 boxjs.rewrite.quanx.conf 即原生"),
    "Sub-Store": ("Sub-Store.lpx", "kelee 插件只是官方 JS 的 Loon 外壳；QX 官方 QX.snippet 即原生"),
    "Script-Hub": ("Script-Hub.lpx", "kelee 插件只是官方 script-hub.js 的 Loon 外壳；QX 官方 script-hub.qx.conf 即原生"),
    "一汽大众去广告": (None, "kelee 无对应插件（zirawell 原生）"),
    "AdGuard": (None, "kelee 无对应插件（yfamilys 原生）"),
    "哔哩哔哩增强": (None, "已有 kokoryh 本地转换版，非作者官方 QX 配置；本批不重复转换"),
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
    with open(path, encoding="utf-8", errors="replace") as stream:
        return stream.read()


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
        elif ch in "[({":
            depth += 1
            buf += ch
        elif ch in "])}":
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
        return json.loads(s)
    return s


def as_jq_value(v):
    v = v.strip()
    if v.startswith('"'):
        return json.dumps(unq(v), ensure_ascii=False)
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
    # Only collapse whitespace outside quoted strings.
    text = "".join(out)
    return " ".join(re.findall(r'"(?:\\.|[^"\\])*"|[^\s"]+', text)).strip()


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


def regex_flags(pattern, flags):
    if set(flags) - set("ims"):
        raise ValueError("Unsupported regular-expression flags: " + flags)
    return ("(?" + "".join(c for c in "ims" if c in flags) + ")" if flags else "") + pattern


def and_domain_filters(a, policy):
    """Exact glob forms for the conjunctions used by this source set."""
    kws, sufs = a["kws"], a["sufs"]
    if sufs and len(kws) == 1:
        key = kws[0]
        out = []
        for suffix in sufs:
            if key in suffix:
                out.append(f"host-suffix, {suffix}, {policy}")
            else:
                out.append(f"host-wildcard, *{key}*.{suffix}, {policy}")
        return out
    if not sufs and len(kws) == 2:
        first, second = kws
        if first in second or second in first:
            return [f"host-keyword, {max(kws, key=len)}, {policy}"]
        if any(x.endswith(y[:i]) for x,y in [(first,second),(second,first)]
               for i in range(1,min(len(first),len(second)))):
            raise ValueError("Overlapping keyword conjunction requires explicit conversion")
        return [f"host-wildcard, *{a}*{b}*, {policy}" for a,b in itertools.permutations(kws)]
    raise ValueError("Unsupported domain conjunction")


def adapt_script(text, relative_path):
    """Keep upstream logic, map storage, and finish QX callbacks exactly once."""
    storage = ""
    if "$persistentStore" in text:
        storage = """const $persistentStore = {
  read: key => $prefs.valueForKey(key) ?? null,
  write: (value, key) => value == null ? $prefs.removeValueForKey(key) : $prefs.setValueForKey(value, key)
};
"""
    return ("// Generated QX adapter; original attribution retained below.\n"
            "// Storage uses $prefs; empty/invalid responses pass through; only the first $done is emitted.\n"
            "((__finish) => {\nlet __finished = false;\n"
            "const $done = (...args) => { if (!__finished) { __finished = true; __finish(...args); } };\n"
            + storage + "try {\n"
            "if (typeof $response !== 'undefined' && !$response.body) { $done({}); return; }\n"
            + text + "\n} catch (__error) {\n"
            "console.log('[loon2qx] script passed through: ' + String(__error));\n"
            "if (!__finished) $done({});\n}\n})($done);\n")


def translated_script(url, raw_base="https://raw.githubusercontent.com/TO8E/loon2qx/main"):
    prefix = "https://kelee.one/Resource/JavaScript/"
    return raw_base.rstrip("/") + "/js/" + url[len(prefix):] if url.startswith(prefix) else url


def complete_hosts(rewrites, initial):
    def expand(tokens):
        result = [""]
        for op, value in tokens:
            if op == sre_parse.LITERAL: choices = [chr(value)]
            elif op == sre_parse.SUBPATTERN: choices = expand(value[3])
            elif op == sre_parse.BRANCH: choices = [s for branch in value[1] for s in expand(branch)]
            elif op == sre_parse.MAX_REPEAT and value[1] <= 1: choices = ([""] if value[0] == 0 else []) + expand(value[2])
            elif op == sre_parse.IN:
                choices = []
                for kind, val in value:
                    if kind == sre_parse.LITERAL: choices.append(chr(val))
                    elif kind == sre_parse.RANGE: choices += [chr(x) for x in range(val[0],val[1]+1)]
                    elif kind == sre_parse.CATEGORY and val == sre_parse.CATEGORY_DIGIT: choices += list("0123456789")
                    else: raise ValueError("Unbounded hostname class")
            elif op == sre_parse.AT: continue
            else: raise ValueError("Unbounded hostname regex")
            result = [a+b for a in result for b in choices]
            if len(result)>128: raise ValueError("Hostname expansion too large")
        return result
    hosts = list(dict.fromkeys(initial))
    for rx,stage,action,note in rewrites:
        rx = re.sub(r'^\(\?[ims]+\)', '', rx).replace(r'\/', '/')
        match = re.match(r'^\^https\??://([^/]+)', rx)
        if not match: continue
        authority = match.group(1).split('(?=',1)[0]
        try: names = expand(sre_parse.parse(authority))
        except (ValueError,re.error): continue
        for name in names:
            if re.fullmatch(r'[a-zA-Z0-9_.-]+',name) and '.' in name and name not in hosts: hosts.append(name)
    return hosts


def convert(show, fname, text=None):
    if text is None:
        text = read(os.path.join(SRC, fname))
    sec = sections(text)
    filters, rewrites, tasks, hosts, notes = [], [], [], [], []
    jq_files = {}
    exceptions = []

    # ---- [Rule] ----
    for line in sec.get("Rule", []):
        if not line.strip() or line.strip().startswith("#") or line.strip().startswith(";"):
            continue
        if line.strip().upper().startswith("AND,"):
            a = parse_and(line)
            pol = map_policy(a["policy"])
            if a["protos"]:
                notes.append("QUIC 处理交由 QX 主配置：已有 udp_drop_list = 443, STUN 时，常用 UDP 443 上的 QUIC 已被阻止，"
                             "支持回退的请求可改走 TCP 以配合重写。它作用于所有经 QX 处理的 UDP 443 流量，"
                             "范围不同于原域名条件；不保证覆盖其它端口的 QUIC。本插件不修改 general。")
            elif a["sufs"] and a["kws"]:
                filters.extend(and_domain_filters(a, pol))
            elif a["kws"]:
                filters.extend(and_domain_filters(a, pol))
            elif a["uas"] and a["urls"] and pol == "direct":
                exceptions.extend((unq(url), unq(ua)) for url in a["urls"] for ua in a["uas"])
                notes.append("URL+UA 放行只豁免指定 HTTPDNS 请求的重写拦截，不再把整个 App 设为直连；"
                             "QX 不支持按 URL 指定 DIRECT，这些例外的线路继续遵循主配置分流。")
            else:
                notes.append(f"无法等价: `{line.strip()[:80]}`")
            continue
        m = RULE_RE.match(line)
        if not m:
            notes.append(f"未识别的规则: {line.strip()}")
            continue
        typ, rest = m.group("type").upper(), m.group("rest")
        parts = split_args(rest)
        value = parts[0].strip()
        # Rule values quote regexes literally (\w, \d, ...), not as JSON strings.
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        flags = [f for f in parts[1:] if f.lower() in ("no-resolve", "force-remote-dns", "pre-matching")]
        cand = [f for f in parts[1:] if f.lower() not in ("no-resolve", "force-remote-dns", "pre-matching")]
        policy = map_policy(cand[-1] if cand else "REJECT")
        if flags:
            notes.append("省略无法直接映射的 " + "/".join(flags) + "；QX 的解析/匹配流程不保证与 Loon 相同。")
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
            if policy != "reject":
                raise ValueError("URL-REGEX policy cannot be represented as a QX filter: " + policy)
            rewrites.append([value, "request", ("reject", None),
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
        stage, rx, body = m.group("stage"), regex_flags(m.group("re"), m.group("flag")), m.group("body").strip()
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
                # Preserve the intended Google path/query explicitly; do not assume
                # identical redirect substitution behavior across clients.
                if "$1" not in target:
                    rx2 = rx.rstrip("$") if rx.endswith("$") else rx
                    rx2 = re.sub(r"\((?!\?)", "(?:", rx2)          # 原有捕获组改非捕获，避免抢 $1
                    rx2 = rx2 + r"(?=[/?#]|$)(.*)$"
                    target = target + "$1"
                    rx, note = rx2, (f"redirect({code}) → {code}；显式保留路径/查询并限制域名边界")
                    if fname == "Google.lpx":
                        rx = rx.replace("www.", r"www\.").replace("maps).google", r"maps)\.google")
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
            if fname == "CoolApk_remove_ads.lpx":
                corrected = expr.replace('([8639,29349,33006,32557] | index(.entityId) | not)',
                                         '(.entityId | IN(8639,29349,33006,32557) | not)')
                corrected = corrected.replace('.entityId? | [944,945,6390] | index(.) | not',
                                               '.entityId? | IN(944,945,6390) | not')
                if corrected != expr:
                    notes.append('修正上游酷安 JQ 数组上下文错误；仅过滤目标 entityId，保留普通内容。')
                expr = corrected
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
            multi = a.startswith("[")
            ps = split_args(a[1:-1]) if multi else [a]
            vs = split_args(v[1:-1]) if multi and v.startswith("[") else [v]
            if len(ps)!=len(vs):raise ValueError("JSON replacement path/value counts differ")
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
            enabled = "false" if re.search(r"enable(?:d)?\s*=\s*false", opts) else "true"
            tasks.append(f"{unq(cm.group('expr'))} {cm.group('url')}, tag={tag.group(1) if tag else 'task'}, enabled={enabled}")
            continue
        sm = SCRIPT_RE.match(line)
        if not sm:
            notes.append(f"未识别的 script: {line.strip()[:90]}")
            continue
        stage, rx, url = sm.group("stage"), regex_flags(sm.group("re"), sm.group("flag")), sm.group("url")
        opts = sm.group("opts") or ""
        if re.search(r"enable(?:d)?\s*=\s*false", opts):
            notes.append("已停用脚本未输出为有效重写：" + url)
            continue
        requires_body = bool(re.search(r"requires[_ -]?body\s*=\s*(true|1)", opts))
        if sm.group("args").strip() and sm.group("args").strip() != "":
            raise ValueError("Script parameters need an explicit QX adapter: " + url)
        if stage == "request":
            kind = "script-request-body" if requires_body else "script-request-header"
        else:
            kind = "script-response-body" if requires_body else "script-response-header"
        tag = re.search(r'tag="([^"]*)"', opts)
        rewrites.append([rx, stage, (kind, url), f"脚本 {tag.group(1) if tag else ''}".strip()])

    # A user-agent filter cannot represent a URL+UA DIRECT exception. Narrow
    # the catch-all HTTPDNS reject, then reject the two URLs only for other UAs.
    if exceptions:
        exclusions = "|".join("(?:" + rx.lstrip("^") + ")" for rx, ua in exceptions)
        for item in rewrites:
            if item[2][0] == "reject" and any(re.search(item[0], re.sub(r"\\(.)", r"\1", rx).lstrip("^").replace(r"\?", "?")) for rx,ua in exceptions):
                item[0] = "^(?!(?:" + exclusions + "))" + item[0].lstrip("^")
        for rx, ua in exceptions:
            ua_regex = re.escape(ua).replace(r"\*", ".*").replace(r"\?", ".")
            header = r"(?is)^(?!.*(?:^|\r\n)User-Agent:\s*" + ua_regex + r"(?:\r\n|$))"
            rewrites.append([rx + " " + header, "request", ("reject", None), "URL+UA 精确排除其它 User-Agent"])

    if fname == 'ChinaUnicom.lpx':
        # Loon rewrite_v2 executes ALL matching rewrites in source order.
        # QX uses the first match. The later broad wallet rule overwrites data,
        # including when the earlier payShowFlag action fails on non-objects.
        narrow = r'(?i)^https:\/\/m\.client\.10010\.com\/clientMyPage\/v1\/api\/myWallet'
        broad = r'(?i)^https?:\/\/m\.client\.10010\.com\/clientMyPage\/v\d\/api\/(myWallet|myPoints|myColorfulRingtone|newUserInfo|getDeviceInfo)'
        narrow_rows = [r for r in rewrites if r[0] == narrow and r[1] == 'response']
        broad_rows = [r for r in rewrites if r[0] == broad and r[1] == 'response']
        if (len(narrow_rows) != 1 or len(broad_rows) != 1
                or narrow_rows[0][2] != ('jsonjq-response-body', "'.data.payShowFlag = false'")
                or broad_rows[0][2] != ('jsonjq-response-body', "'.data={}'")
                or rewrites.index(narrow_rows[0]) >= rewrites.index(broad_rows[0])):
            raise ValueError('ChinaUnicom wallet overlap changed; review sequential Loon semantics')
        narrow_rows[0][2] = ('jsonjq-response-body', "'.data={}'")
        narrow_rows[0][3] = '合并后续钱包清空操作，保留 Loon 多条匹配按序执行的最终效果'
        notes.append('钱包重叠规则已合并最终效果：HTTPS v1 myWallet 先设标志后被后续规则清空，QX 直接令 data={}。')

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
    unexpected = [n for n in uniq if n.startswith(("未识别", "未映射", "jq_file 未落地", "无法等价"))]
    if unexpected:
        raise ValueError(fname + ": " + " / ".join(unexpected))
    return dict(filters=list(dict.fromkeys(filters)), rewrites=rewrites, tasks=tasks, hosts=hosts,
                notes=uniq, jq=jq_files)


def fmt_rewrite(rw):
    rx, stage, (kind, arg), note = rw
    operator = "url-and-header" if " " in rx else "url"
    line = f"{rx} {operator} {kind}" + (f" {arg}" if arg and kind not in ("reject", "reject-200",
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
    from pathlib import Path
    sys.path.insert(0, HERE)
    import build_qx_repo as builder
    raw = builder.RAW
    if "--script-base" in sys.argv:
        raw = sys.argv[sys.argv.index("--script-base") + 1].rstrip("/")
    info, rw, ft, tk = builder.build(QX, raw)
    # Retire only files produced by the old long-name generator.
    retired = [f.removesuffix(".lpx") for _,f,_ in ENABLED] + ["ColorfulClouds_remove_ads"]
    for name in retired:
        if name.casefold() in {slug.casefold() for slug in builder.SLUGS.values()}:
            continue  # Google.snippet and google.snippet are the same on default macOS filesystems.
        for directory,ext in [("snippets",".snippet"),("lists",".list")]:
            (Path(QX)/directory/(name+ext)).unlink(missing_ok=True)
    for p in (Path(QX)/"jq").glob("*__*.jq"):
        p.unlink()
    builder.write(Path(QX)/"merged/rewrite_local.conf", "# 粘贴到 [rewrite_local]；勿与对应远程重写重复启用。\n"+"\n".join(rw)+"\n")
    builder.write(Path(QX)/"merged/filter_local.conf", "# 粘贴到 [filter_local]\n"+"\n".join(ft)+"\n")
    builder.write(Path(QX)/"merged/task_local.conf", "\n".join(tk)+("\n" if tk else "# 本批无任务\n"))
    builder.write(Path(QX)/"merged/mitm.hostname.txt", ", ".join(info["hosts"])+"\n")
    builder.write(Path(QX)/"merged/mitm.add.txt", "hostname = "+", ".join(info["hosts"])+"\n")
    report = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), summary=info["rows"], skipped=SKIPPED,
                  problems=[], limitations=info["limitations"])
    builder.write(Path(QX)/"report.json", json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"plugins":len(info["rows"]),"rewrites":sum(r["rewrite"] for r in info["rows"]),"output":QX},ensure_ascii=False))


if __name__ == "__main__":
    main()
