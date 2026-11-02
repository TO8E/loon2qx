# loon2qx

将 [可莉插件中心](https://hub.kelee.one/) 中选定的 12 个应用/工具插件和 2 个基础拦截器转换为 Quantumult X 配置。
原始作者信息保留在资源说明及脚本内。彩云天气的误转换已移除；不处理原配置里的彩云 Pro。

当前生成 139 条重写、496 条分流、50 个 MITM 主机和 5 个带 QX 兼容层的脚本。
这些数字描述文件内容，**不代表已经在手机验证所有 App 的实际效果**。

## 导入

- 将 `config/rewrite_remote.conf` 添加到主配置的 `[rewrite_remote]`。
- 将 `config/filter_remote.conf` 添加到 `[filter_remote]`，保留各资源本来的策略。基础文件同时包含 DIRECT 和 REJECT，不能统一指定 `force-policy=reject`。
- 远程重写使用裸规则及 `hostname = …`，不含配置段头。其主机由 QX 合并；`config/mitm.txt` 是供本地合并时使用的清单。
- 生成并信任自己的 MITM 证书，启用重写。相同 App 不要同时启用旧版本或其他作者的重写。
- QQ 音乐只有域名分流，不生成或订阅空的重写文件。

`base/` 的两个基础拦截器沿用原插件的公共拦截逻辑，导入片段默认启用。它们不是 JS 执行器的依赖。
各 App 自己的原始域名规则保留完整，不再为了去重从独立列表中删除。

## 资源

| 应用/工具 | 主要文件 | 重写 | 分流 |
|---|---|---:|---:|
| HTTPDNS拦截器 | `base/httpdns.snippet` | 24 | 141 |
| 广告平台拦截器 | `base/advertisers.snippet` | 4 | 337 |
| QQ音乐去广告 | `lists/qqmusic.list` | 0 | 11 |
| 京东去广告 | `snippets/jd.snippet` | 4 | 0 |
| 下厨房去广告 | `snippets/xiachufang.snippet` | 7 | 0 |
| 淘宝去广告 | `snippets/taobao.snippet` | 13 | 6 |
| 闲鱼去广告 | `snippets/goofish.snippet` | 23 | 0 |
| 小红书去广告 | `snippets/xhs.snippet` | 21 | 0 |
| 12306去广告 | `snippets/12306.snippet` | 2 | 1 |
| 酷安去广告 | `snippets/coolapk.snippet` | 7 | 0 |
| 高德地图去广告 | `snippets/amap.snippet` | 18 | 0 |
| 掌上英雄联盟去广告 | `snippets/mlol.snippet` | 6 | 0 |
| 朴朴超市去广告 | `snippets/pupu.snippet` | 8 | 0 |
| Google搜索重定向 | `snippets/google.snippet` | 2 | 0 |

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

1. **小红书按域名限定的 QUIC 拦截未等价转换。** 全局 `udp_drop_list=QUIC` 会影响所有应用，不能称作等价替代。本项目不修改主配置的全局 UDP 设置。
2. **HTTPDNS 的 URL + User-Agent 例外**通过限定重写保留“不拦截”的效果；QX 无法用该条件直接指定路由，例外请求继续遵循主配置分流，不将整个 App 设成 DIRECT。
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
其中 `base/`、`snippets/`、`lists/`、`js/`、`jq/`、`config/` 与 GitHub 发布目录采用相同内容。
`qx/conf/quantumultx.conf` 是本地个人配置，不上传到本仓库。
