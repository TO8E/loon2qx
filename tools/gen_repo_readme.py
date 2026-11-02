#!/usr/bin/env python3
"""Render documentation from the generated inventory; do not claim device validation."""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
info=json.loads((root/'build-info.json').read_text());rows=info['rows']
table='\n'.join('| '+r['name']+' | '+('`'+r['snippet']+'`' if r['snippet'] else '—')+' | '
                +('`'+r['list']+'`' if r['list'] else '—')+f" | {r['rewrite']} | {r['filter']} |" for r in rows)
scope=json.loads((root/'config/shared-scope.json').read_text())
scope_table='\n'.join('| '+', '.join(g['apps'])+' | '+g['purpose']+' | '+str(len(g['entries']))+' |'
                      for source in scope.values() for g in source['groups'])
text=f'''# loon2qx

将 [可莉插件中心](https://hub.kelee.one/) 中本次迁移使用的 12 个应用/工具插件转换为 Quantumult X 配置。
HTTPDNS、广告域名配套已并入各 App；B 站增强和小黑盒原本地重写也已移为远程资源。
原始作者信息保留在资源说明及脚本内。彩云天气的误转换已移除；不处理原配置里的彩云 Pro。

独立 App 文件合计 {sum(r['rewrite'] for r in rows)} 条重写、{sum(r['filter'] for r in rows)} 条分流；去重后仍为 {info['unique']['rewrites']} 条重写、{info['unique']['filters']} 条分流。
共 {len(info['hosts'])} 个 MITM 主机和 {len(info['assets'])} 个带 QX 兼容层的脚本。
这些数字描述文件内容，**不代表已经在手机验证所有 App 的实际效果**。

## 导入

- 将 `config/rewrite_remote.conf` 添加到主配置的 `[rewrite_remote]`。
- 将 `config/filter_remote.conf` 添加到 `[filter_remote]`，保留各资源本来的策略。12306 含广告域名 DIRECT 配套规则，不能给所有资源统一指定 `force-policy=reject`。
- 远程重写使用裸规则及 `hostname = …`，不含配置段头。其主机由 QX 合并；`config/mitm.txt` 是供本地合并时使用的清单。
- 生成并信任自己的 MITM 证书，启用重写。相同 App 不要同时启用旧版本或其他作者的重写。
- QQ 音乐只有域名分流，不生成或订阅空的重写文件。
- 同一 App 的 `.snippet` 和 `.list` 配套启停；QX 原生订阅将重写与分流分开读取，不能把 IP/域名分流直接塞进重写文件。
- B 站使用 `snippets/bilibili.snippet` + `lists/bilibili.list`；小黑盒使用 `snippets/xiaoheihe.snippet`。
- 从旧配置迁移时，删除 `[rewrite_local]` 中 `BEGIN BILIBILI_KOKORYH_QX` 到 `END BILIBILI_KOKORYH_QX` 的整块，以及两条小黑盒重写，再添加相应远程订阅。只需迁移一次，无须覆盖整份主配置。

不再生成或订阅 `base/httpdns.*`、`base/advertisers.*`。更新旧配置时删除这些公共订阅，按下表补上相关 App 的分流。
各 App 原有规则保持完整，公共补充直接写入它自己的文件。
阿里系共有项分别随淘宝、闲鱼、高德提供，单独启用任一 App 时不依赖其它 App 的开关。
同时启用时会有少量同动作规则重复；每个文件内部去重，本地 `merged/` 合并版也去重，不增加新的拦截范围。

## 公共部分的范围

按用户已有插件清单及服务归属选取，逐条来源和原文件行号记录在 `config/shared-scope.json`。

| 关联应用 | 保留用途 | 原规则数 |
|---|---|---:|
{scope_table}

不迁移嘀嗒出行的 URL + UA 直连例外，也不保留需要它兜底的全 IP 通用 HTTPDNS URL 拦截。
同时移除未选应用的专用服务、全局 `httpdns` 关键词/UA 拦截，以及拼多多等未启用项目的公共重写。
因此本配置不再存在“嘀嗒请求只放行但不强制直连”的转换差异。

这里按服务筛选，不是按 App 进程隔离：阿里系等共享端点仍可能被其他 App 使用。
域名归属和上游分组也不证明每个 App 当前都会访问全部端点；未确认的第三方 SDK 不因厂商相同就整包搬入。
这是现有资料支持的迁移子集，未通过手机流量证明去广告覆盖完整；实际出现遗漏时再按具体请求补充。
用户原有 AdGuard 等通用资源保持独立，不宣称这份定向补充替代它们。

## 资源

| 应用/工具 | 重写文件 | 分流文件 | 重写行 | 分流行 |
|---|---|---|---:|---:|
{table}

`js/` 不是上游的逐字节副本：生成时加入 QX 存储适配及回调保护。
`build-info.json` 记录脚本来源、上游摘要和生成后摘要；每次构建刷新脚本，避免继续使用旧文件。
`jq/` 保存内联使用的原文，`tools/` 为生成/检查工具，`tests/` 为行为回归用例。

## B 站增强底栏修正

`snippets/bilibili.snippet` 提供完整 kokoryh Bilibili 增强重写，其中 JSON 处理使用 `js/Bilibili/bilibili_json.js` 适配版。
原作者的底栏筛选只认“首页、动态、我的”，会丢弃名称改为“关注”或其它语言的入口。
适配版同时识别入口 URI、tab_id、已知 id 和名称，保留原入口的路由、图标和顺序；
遇到无法确认的底栏结构则保留原样。其它 JSON 处理逻辑沿用作者快照。
它没有现成的 BoxJS 设置页，本修正默认启用，不需要额外开关。

原脚本快照保存在 `tools/upstream/bilibili_json.js`，修正逻辑在 `tools/bilibili-navigation.js`；
构建只替换底栏筛选，更新上游后匹配不到原逻辑会停止构建，要求重新核对。
其余 protobuf、皮肤脚本继续使用原来的来源。不要同时加载旧本地 B 站规则和本远程订阅。

## 后续如何更新

插件内容更新后，不需要重新导入完整配置。QX 主界面长按右下角风车/圆形按钮，再点击左侧刷新按钮，更新外部资源。
也可进入重写资源列表，选择对应资源进行更新；脚本使用缓存时同时更新它引用的脚本。
完整步骤参考 [QX 订阅更新说明](https://t.me/s/QuanXNews?before=278&q=%23Tutorials) 和 [BoxJS 的 QX 脚本更新说明](https://docs.boxjs.app/base/upgrade)。
配置中的远程资源设置为 86400 秒更新周期；不代表每次请求都会实时下载 JS。
节点参数、策略组等写在主配置内的内容不属于这些远程资源，修改它们时仍需编辑对应配置段。

## 已处理的兼容问题

- 保留 Loon 正则的 `/i` 等标志；多个同 URL、同阶段的 JSON 操作顺序合并。
- 保留 JSON 字符串和数字的区别，以及 jq 字符串内部的空白。
- 小红书的 `$persistentStore` 映射到 QX `$prefs`；不存在的缓存读为 null。
- 每次脚本运行仅提交第一次 `$done`；空正文或异常正文按原请求/响应放行。
- AND 关键词与后缀保留域名边界，多关键词保留全部条件，不只取最长关键词。
- Google 重定向保留路径和查询参数，并限制匹配域名边界。
- 补齐能从有限域名正则推导出的 MITM 主机；空重写和占位脚本不作为有效资源发布。
- 修正酷安上游 JQ 的数组上下文错误，防止正常条目被清空或处理报错。
- 遇到未知动作或未适配的脚本参数，构建失败，不静默丢弃。

## 已知差异

1. **小红书的 QUIC 处理由主配置承担。** 原规则的目的是阻止 QUIC，让支持回退的请求改走 TCP HTTPS，以配合重写。QX 主配置已有 `[general]` 下的 `udp_drop_list = 443, STUN` 时，常用 UDP 443 上的 QUIC 已被阻止，无需再添加同用途规则。这作用于所有经 QX 处理的 UDP 443 流量，范围比原域名条件更广，也不保证覆盖其它端口的 QUIC。QX 另支持在该列表中加入 `QUIC`，但它同样全局生效，本项目不自动添加。参见 [QX 官方参数说明](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)。
2. **公共规则按服务选取，不按进程隔离。** 共享端点仍可能被其它 App 使用；未搬入与本次迁移无关的路由例外和通用拦截。
3. `no-resolve`、部分超时参数没有直接映射，DNS/超时流程可能有差异。
4. 高德的 jq 内联为较长的一行；对返回结构的假设沿用上游，App 更新后仍可能失效。
5. 未进行手机 QX 原生导入、实际网络抓包或各 App 实测。正则/jq 编译和模拟请求只验证对应场景。

## 构建与检查

需要 Python 3.9+、Node.js、jq。构建还需要本地原始镜像，查找位置为当前仓库或父目录的
`mirror/upstream/kelee.one/`；公共仓库不包含个人完整配置、节点或订阅。

```sh
python3 tools/build_qx_repo.py --out .
python3 tools/gen_repo_readme.py .
python3 tools/check_qx.py --dir .
python3 -m unittest discover -s tests -p 'test_*.py' -v
node tests/runtime.cjs
node tests/bilibili-navigation.cjs
```

在镜像工作区运行 `python3 scripts/convert_lpx_to_qx.py` 会使用同一个生成器重建 `qx/`；
其中 `snippets/`、`lists/`、`js/`、`jq/`、`config/` 与 GitHub 发布目录采用相同内容。
`qx/conf/quantumultx.conf` 是本地个人配置，不上传到本仓库。公共规则选择清单在 `tools/shared_scope.py`，
构建先筛选再转换；上游新增无关规则不会自动扩大范围，已选规则消失或策略变化则构建失败。
'''
(root/'README.md').write_text(text)
print('README generated:',root/'README.md')
