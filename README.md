# loon2qx

将 [可莉插件中心](https://hub.kelee.one/) 中本次迁移使用的 12 个应用/工具插件转换为 Quantumult X 配置。
HTTPDNS、广告域名配套已并入各 App；另外提供 B 站增强所需的分流配套，沿用原有 B 站增强重写。
原始作者信息保留在资源说明及脚本内。彩云天气的误转换已移除；不处理原配置里的彩云 Pro。

独立 App 文件合计 126 条重写、77 条分流；去重后仍为 116 条重写、45 条分流。
共 31 个 MITM 主机和 5 个带 QX 兼容层的脚本。
这些数字描述文件内容，**不代表已经在手机验证所有 App 的实际效果**。

## 导入

- 将 `config/rewrite_remote.conf` 添加到主配置的 `[rewrite_remote]`。
- 将 `config/filter_remote.conf` 添加到 `[filter_remote]`，保留各资源本来的策略。12306 含广告域名 DIRECT 配套规则，不能给所有资源统一指定 `force-policy=reject`。
- 远程重写使用裸规则及 `hostname = …`，不含配置段头。其主机由 QX 合并；`config/mitm.txt` 是供本地合并时使用的清单。
- 生成并信任自己的 MITM 证书，启用重写。相同 App 不要同时启用旧版本或其他作者的重写。
- QQ 音乐只有域名分流，不生成或订阅空的重写文件。
- 同一 App 的 `.snippet` 和 `.list` 配套启停；QX 原生订阅将重写与分流分开读取，不能把 IP/域名分流直接塞进重写文件。
- B 站只新增 `lists/bilibili.list` 配套，继续启用原来的 B 站增强。

不再生成或订阅 `base/httpdns.*`、`base/advertisers.*`。更新旧配置时删除这些公共订阅，按下表补上相关 App 的分流。
各 App 原有规则保持完整，公共补充直接写入它自己的文件。
阿里系共有项分别随淘宝、闲鱼、高德提供，单独启用任一 App 时不依赖其它 App 的开关。
同时启用时会有少量同动作规则重复；每个文件内部去重，本地 `merged/` 合并版也去重，不增加新的拦截范围。

## 公共部分的范围

按用户已有插件清单及服务归属选取，逐条来源和原文件行号记录在 `config/shared-scope.json`。

| 关联应用 | 保留用途 | 原规则数 |
|---|---|---:|
| 京东 | 京东解析服务 | 3 |
| 淘宝, 闲鱼, 高德 | 阿里系共享解析服务及淘宝调度接口 | 10 |
| 哔哩哔哩 | B 站解析服务 | 1 |
| QQ音乐 | QQ 音乐广告与统计补充 | 3 |
| 京东 | 京东广告与统计补充 | 4 |
| 淘宝, 闲鱼, 高德 | 阿里系广告、统计与百川服务补充 | 11 |

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
| QQ音乐去广告 | — | `lists/qqmusic.list` | 0 | 14 |
| 京东去广告 | `snippets/jd.snippet` | `lists/jd.list` | 4 | 7 |
| 下厨房去广告 | `snippets/xiachufang.snippet` | — | 7 | 0 |
| 淘宝去广告 | `snippets/taobao.snippet` | `lists/taobao.list` | 18 | 22 |
| 闲鱼去广告 | `snippets/goofish.snippet` | `lists/goofish.list` | 28 | 16 |
| 小红书去广告 | `snippets/xhs.snippet` | — | 21 | 0 |
| 12306去广告 | `snippets/12306.snippet` | `lists/12306.list` | 2 | 1 |
| 酷安去广告 | `snippets/coolapk.snippet` | — | 7 | 0 |
| 高德地图去广告 | `snippets/amap.snippet` | `lists/amap.list` | 23 | 16 |
| 掌上英雄联盟去广告 | `snippets/mlol.snippet` | — | 6 | 0 |
| 朴朴超市去广告 | `snippets/pupu.snippet` | — | 8 | 0 |
| Google搜索重定向 | `snippets/google.snippet` | — | 2 | 0 |
| B站增强分流配套 | — | `lists/bilibili.list` | 0 | 1 |

`js/` 不是上游的逐字节副本：生成时加入 QX 存储适配及回调保护。
`build-info.json` 记录脚本来源、上游摘要和生成后摘要；每次构建刷新脚本，避免继续使用旧文件。
`jq/` 保存内联使用的原文，`tools/` 为生成/检查工具，`tests/` 为行为回归用例。

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
```

在镜像工作区运行 `python3 scripts/convert_lpx_to_qx.py` 会使用同一个生成器重建 `qx/`；
其中 `snippets/`、`lists/`、`js/`、`jq/`、`config/` 与 GitHub 发布目录采用相同内容。
`qx/conf/quantumultx.conf` 是本地个人配置，不上传到本仓库。公共规则选择清单在 `tools/shared_scope.py`，
构建先筛选再转换；上游新增无关规则不会自动扩大范围，已选规则消失或策略变化则构建失败。
