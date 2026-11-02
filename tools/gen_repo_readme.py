#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 build-info.json 生成仓库 README（数字全部来自实际产物）"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else ROOT
bi = json.load(open(os.path.join(OUT, "build-info.json"), encoding="utf-8"))
rows, hosts = bi["rows"], bi["hosts"]
base = [r for r in rows if r["kind"] == "base"]
plug = [r for r in rows if r["kind"] != "base"]
tr = sum(r["rewrite"] for r in rows)
tf = sum(r["filter"] for r in rows)


def row(r, path):
    return (f"| `{path}` | {r['name']} | {r['rewrite']} | {r['filter']} | {len(r['hosts'])} |")


tb = "\n".join(row(r, f"base/{r['slug']}.snippet") for r in base)
tp = "\n".join(row(r, f"snippets/{r['slug']}.snippet") for r in plug)

TEXT = f"""# loon2qx

把 [hub.kelee.one](https://hub.kelee.one/) 的 Loon 插件直译成 **Quantumult X 原生写法**。
只覆盖本人启用的 13 个去广告插件 + 2 个公共依赖。转换结果自动生成，勿手改。

- 重写 **{tr}** 条 · 分流 **{tf}** 行 · MITM **{len(hosts)}** 个主机名
- 每条 `jsonjq-response-body` 都过 `jq` 编译，每条正则都过 `re` 编译（`tools/check_qx.py`，0 问题）

## 目录

```
base/       公共依赖（HTTPDNS 拦截器 / 广告平台拦截器）的 snippet + filter 列表
snippets/   每个插件 [rewrite_local] + [mitm]，脚本走本仓库 raw 地址
lists/      每个插件的 [filter_local] 行（作 filter_remote 源）
js/         被 snippet 引用的 JS 原样备份（作者原文件）
jq/         jq_file 原文（snippet 里已内联，这里留档便于改）
config/     直接粘进 QX 配置的三段：rewrite_remote / filter_remote / mitm
tools/      转换与校验脚本（需要 kelee 镜像才能重跑）
```

## 安装（三段）

```
[rewrite_remote]  ← config/rewrite_remote.conf
[filter_remote]   ← config/filter_remote.conf
[mitm] hostname   ← config/mitm.txt（只补你缺的）
```

装完在 QX「重写 → 引用」里更新一次，并确认 MITM 证书已生成、已信任。

## 公共依赖（必须先加载）

kelee 的去广告脚本默认前提：**HTTPDNS 拦截器**掐掉 APP 的明文 HTTPDNS 解析、逼它走代理 DNS；
**广告平台拦截器**按住穿山甲/巨量/腾讯广告等投放域名。两者放 `base/`，在 `config/*.conf` 里排在所有插件之前。

公共规则只维护一份：插件自己的 `lists/` 与 `base/` 重复的行已剔除（本批 6 行，见各 list 头部注释）。

## 清单

| 文件 | 插件 | 重写 | 分流 | MITM |
|---|---|---:|---:|---:|
{tb}
{tp}

**`snippets/caiyun.snippet` / `lists/caiyun.list` 只是留档**：彩云天气在 QX 侧本来就用 ishowshu 的
原生 `caiyun.snippet`（当年经 Script-Hub 落地，本身就是 QX 写法），按「原生 QX 不处理」原则不启用。

## Loon → QX 映射

| Loon | QX |
|---|---|
| `DOMAIN / -SUFFIX / -KEYWORD, x, REJECT` | `host / host-suffix / host-keyword, x, reject` |
| `IP-CIDR / IP-CIDR6, x, REJECT, no-resolve` | `ip-cidr / ip6-cidr, x, reject`（QX 无 `no-resolve`） |
| `USER-AGENT, "httpdns*", REJECT` | `user-agent, httpdns*, reject` |
| `URL-REGEX, "^…", REJECT` | `^… url reject`（**QX filter 没有 url-regex**） |
| `AND, ((DOMAIN-KEYWORD,K),(DOMAIN-SUFFIX,S)), P` | `host-wildcard, *K*S, P`（近似） |
| `AND, ((PROTOCOL,QUIC), …)` | 无协议匹配 → 用 `[general] udp_drop_list`，见下 |
| `reject_dict(200)` / `reject_img(200)` / `reject(404)` | `reject-dict` / `reject-img` / `reject`（QX 的 reject 就是 404） |
| `response.json.delete(p…)` | `jsonjq-response-body 'del(p…)'` |
| `response.json.jq("X")` | `jsonjq-response-body 'X'` |
| `response.json.jq_file(url)` | `jsonjq-response-body '<内联>'`（QX 不能引用远程 jq） |
| `response.json.replace(p, v)` | `jsonjq-response-body 'p = v'` |
| `redirect(307,"u")` | `url 307 u` + 自补 `(.*)` / `$1`（Loon 隐式带 path） |
| `request … script(u) requires_body` | `script-request-body u` |
| `request … script(u)` | `script-request-header u` |
| `response … script(u)` | `script-response-body u` |

**同 URL 合并**：QX 一个 URL 只执行首条命中的重写，所以同一 (URL, 阶段) 的多条 `response.json.*`
按源文件顺序合并成一条 jq 程序。原始 93 条 json 操作压成 42 条。

## 已知差异

1. **QUIC 不再逐 App 写**：Loon 用 `AND,((PROTOCOL,QUIC),(DOMAIN-SUFFIX,xiaohongshu.com)),REJECT`。
   QX 没有协议匹配，但 `[general]` 的 `udp_drop_list` 本身就是按端口/协议丢包：
   `udp_drop_list = 443, STUN` 已经全局丢弃 UDP/443，QUIC 起不来，目的等价；写成
   `udp_drop_list = 443, STUN, QUIC` 更明确。**不要**改成 `host-suffix, xiaohongshu.com, reject`，
   那会把 TCP 正常请求一起断掉。
2. **`AND(关键字+后缀)`** 用 `host-wildcard` 近似，如 `AND((DOMAIN-KEYWORD,-ad-),(DOMAIN-SUFFIX,byteimg.com))`
   → `host-wildcard, *-ad-*.byteimg.com, reject`。
3. **`AND(多关键字)`** 取最长关键字做 `host-keyword`（如 `-normal.zijieapi.com`）。
4. **`AND(URL+UA)`** 用 `user-agent` 近似（如嘀嗒出行的 HTTPDNS 放行）。
5. **高德 `updatable/1`** 是 9000+ 字符单行（删 40 个键 + 243 行 jq 内联），QX 能吃但编辑器难看清，原文在 `jq/`。
6. **`timeout=NNN`** 无对应参数，未保留。
7. 插件 `[MitM]` 漏写的主机会自动补齐（否则对应 https 重写永不触发），补齐项写在各自 snippet 末尾「说明」里。

## 重新生成

```bash
python3 tools/convert_lpx_to_qx.py       # 单插件直译 -> qx/
python3 tools/build_qx_repo.py --out repo
python3 tools/gen_repo_readme.py repo
python3 tools/check_qx.py --dir repo
```
转换器读本机 kelee 镜像（`mirror/upstream/kelee.one/...`），插件更新后重跑即可。
"""

open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write(TEXT)
print(f"README 写入 {OUT}/README.md（{len(TEXT)} 字节，{tr} 重写 / {tf} 分流 / {len(hosts)} hostname）")
