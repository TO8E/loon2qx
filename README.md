# loon2qx

将 [可莉插件中心](https://hub.kelee.one/) 中本次迁移使用的 14 个应用/工具插件转换为 Quantumult X 配置。
另提供 loon.103516.xyz 中国联通插件转换版。
HTTPDNS、广告域名配套已并入各 App；小黑盒和 B 站已切换为可莉插件转换版。
原始作者信息保留在资源说明及脚本内。彩云天气的误转换已移除；不处理原配置里的彩云 Pro。

独立 App 文件合计 160 条重写、85 条分流；去重后仍为 150 条重写、53 条分流。
共 39 个 MITM 主机和 9 个带 QX 兼容层的脚本。
这些数字描述文件内容，**不代表已经在手机验证所有 App 的实际效果**。

## 导入

- 将 `config/rewrite_remote.conf` 添加到主配置的 `[rewrite_remote]`。
- 将 `config/filter_remote.conf` 添加到 `[filter_remote]`，保留各资源本来的策略。12306 含广告域名 DIRECT 配套规则，不能给所有资源统一指定 `force-policy=reject`。
- 远程重写使用裸规则及 `hostname = …`，不含配置段头。其主机由 QX 合并；`config/mitm.txt` 是供本地合并时使用的清单。
- 生成并信任自己的 MITM 证书，启用重写。相同 App 不要同时启用旧版本或其他作者的重写。
- QQ 音乐默认使用 `snippets/qqmusic.snippet`：14 条域名拦截 + 1 条域名加 `1` 的 HTTP 拒绝占位，无脚本或 MitM；纯域名旧版收到用户导入失败反馈，当前修正版待手机验证。与旧 `lists/qqmusic.list` **二选一**，不要重复订阅。
- 除 QQ 音乐的两种替代格式外，同一 App 若同时提供 `.snippet` 和 `.list`，应配套启停。新版 QX 的重写资源支持域名规则；中国联通和 QQ 音乐各用一个文件即可（建议 QX 1.5.2(854)+），其余应用保持原结构。
- B 站只使用 `snippets/bilibili.snippet`，内含对应域名/HTTPDNS 配套；停用原 `lists/bilibili.list` 与其它 B 站重写。小黑盒使用 `snippets/xiaoheihe.snippet`。
- 从旧配置迁移时，删除 `[rewrite_local]` 中 `BEGIN BILIBILI_KOKORYH_QX` 到 `END BILIBILI_KOKORYH_QX` 的整块，以及两条小黑盒重写，再添加相应远程订阅。只需迁移一次，无须覆盖整份主配置。

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
| QQ音乐去广告 | `snippets/qqmusic.snippet` | `lists/qqmusic.list` | 1 | 14 |
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
| 哔哩哔哩去广告 | `snippets/bilibili.snippet` | — | 22 | 8 |
| 小黑盒去广告 | `snippets/xiaoheihe.snippet` | — | 2 | 0 |
| 中国联通去广告 | `snippets/chinaunicom.snippet` | — | 9 | 1 |

`js/` 不是上游的逐字节副本：生成时加入 QX 存储适配及回调保护。
`build-info.json` 记录脚本来源、上游摘要和生成后摘要；每次构建刷新脚本，避免继续使用旧文件。
`jq/` 保存内联使用的原文，`tools/` 为生成/检查工具，`tests/` 为行为回归用例。

## 中国联通合并版

来源：[loon.103516.xyz/Plugin/ChinaUnicom.lpx](https://loon.103516.xyz/Plugin/ChinaUnicom.lpx)，原作者标注为 mist-whisper，源文件另列 ddgksf2013 参考。
原插件标注更新于 2026-11-02 21:00；原文快照和 SHA-256 记录于 `tools/upstream/ChinaUnicom.lpx` 与 `build-info.json`。
只添加 `snippets/chinaunicom.snippet` 到重写资源：**1 条精确域名拒绝 + 3 条 URL 拦截 + 6 条内联 jq 响应修改**，无外部 JS 或额外分流订阅。
混合分流/重写在 [QX 1.5.2(844) 公告](https://t.me/QuanXNews/294) 中加入，内联 jq 在 [845 公告](https://t.me/QuanXNews/296) 中加入；本资源保守建议 QX 1.5.2(854) 或更新版。
开启重写和 MitM、信任证书；域名为 `m.client.10010.com`、`img.client.10010.com`。请勿同时启用 Zirawell、ddgksf2013 等其他联通规则。

覆盖搜索框推广、浮窗、钱包模块、广告推送、新人专享、我的页面部分推广和首页瀑布流。
保留原正则 `/i` 和协议范围。钱包接口在 Loon 中会先设置 `payShowFlag=false`，再命中后续规则清空 `.data`；QX 只执行首条，因此已将窄钱包规则转换为最终的 `.data={}`，避免逐行照搬造成漏处理。
执行顺序依据 [Loon 官方新版重写文档](https://nsloon.app/docs/Rewrite/rewrite_v2/#多条-rewrite)：同阶段所有匹配按配置顺序执行，失败的 Action 跳过并继续；规则结构变化会让转换报错，要求复核。
上游正则没有补加路径结尾或其他边界。本地测试核对规则匹配和 JSON 输出，未进行 Loon/QX 手机端实测。

## QQ 音乐插件版（与旧分流版二选一）

`snippets/qqmusic.snippet` 为**重写资源兼容修正版**，关闭资源解析器；不需要脚本、`hostname` 或 MitM。
保留可莉原插件的 11 个精确广告域名，加原有 3 个广告/统计补充域名（来自 `BlockAdvertisers.lpx`），合计 14 条域名拒绝。
2026-11-09 用户报告纯域名旧版在 **QX 1.90、解析器关闭**时提示“内容无效”。官方只明确支持重写资源附带分流，不能据此保证纯分流片段也能导入；此前的保证已撤回。
按用户要求恢复简单的 `url reject` 占位，并在域名末尾加 `1`：`^http:\/\/ad\.tencentmusic\.com1\/ url reject`，置于域名规则前。
占位只匹配 `http://ad.tencentmusic.com1/`，**不会匹配真实的 `ad.tencentmusic.com` 地址**；原 14 条域名拒绝及旧列表完全不变。移除请求头替换，不强制 DIRECT，无外部 JS 或 HTTPS 解密。
加 `1` 是为了避开真实请求，并不使正则在逻辑上恒不匹配：如果人为请求这个 `.com1` 地址仍会命中。本地测试覆盖真实域名不命中、占位边界和生成一致性，不能代替 QX 原生导入/执行测试。
这是一项针对疑似资源类型识别问题的兼容修复，**尚未在用户手机确认导入成功，未确证 QX 内部拒绝原因**。
旧 `lists/qqmusic.list` 继续保留，14 条域名规则与新版相同，依然可作为分流资源使用。**两种格式二选一**；不要叠加启用。
默认清单使用插件版，不重复订阅旧列表。统计包含新增 1 条兼容重写，不重复计入替代列表中的域名。
本地语法/生成/正则测试并非 QX 原生导入测试；校验器现在保守要求发布到重写订阅的资源确实具有 URL 重写，避免再次凭域名非空判断可导入。

## 小黑盒可莉版

`snippets/xiaoheihe.snippet` 由可莉的 `XiaoHeiHe_remove_ads.lpx` 转换，替换先前 wxs0625 来源的版本，订阅 URL 不变。
原作者：可莉；来源：https://kelee.one/Tool/Loon/Lpx/XiaoHeiHe_remove_ads.lpx 。
源文件快照位于 `tools/upstream/XiaoHeiHe_remove_ads.lpx`，标注更新时间为 2026-10-02 13:57:49。
保留 HTTPS 匹配和 `/i` 标志：开屏 `get_ads_info_v2` 返回空 JSON 对象，信息流使用 QX 内联 jq，无外部 JS。
信息流仅清除 `content_type == 27` 条目的 13 个指定字段（包括大写 `PROTOCOL`，不删除小写 `protocol`），不删除整个条目。
为忠实保留可莉原版逻辑，未沿用旧模板的数组/对象检查；返回结构异常时 jq 可能报错，未做手机实测。
已订阅此仓库版本的用户刷新原资源即可；不要与 Zirawell 或其它小黑盒重写同时启用。
完整构建时，将最新源放入本地镜像的 `Tool/Loon/Lpx/XiaoHeiHe_remove_ads.lpx`；回归测试使用仓库中的源快照。

## B 站：只保留可莉版固定配置

来源：[Bilibili_remove_ads.lpx](https://kelee.one/Tool/Loon/Lpx/Bilibili_remove_ads.lpx)，原作者 kokoryh，可莉收录，上游标注 2026-10-02。
沿用 `snippets/bilibili.snippet` 订阅地址，删除旧增强模板及对应旧 JSON/皮肤外链，**不是同时启用两套**。

固定选项，无用户参数、BoxJS 或持久设置覆盖：

| 选项 | 值 |
|---|---|
| 动态“最常访问” `displayUpList` | `hide` |
| 移除评论区置顶广告 `purifyComment` | `true` |
| 优化评论区加载异常 `optimizeRequest` | `true`（QX 兼容条件与限制见下） |
| 空降助手 `sponsorBlock` | `false`，相关请求与外连不迁移 |
| 日志 `logLevel` | `off` |

选择新版的依据：旧 `bilibili.protobuf.js` 只清除评论 `cm`，没有这版的置顶评论净化/请求优化入口；旧动态默认按直播状态显示，无法直接满足固定 `hide`。
新版还覆盖更完整的直播入口、统一播放器/相关推荐接口，配置可固定并随仓库发布。旧版原生 QX 二进制接口的做法作为适配参考，但不混入旧皮肤 DIY 和旧频道接口规则。
新版底栏 jq 原本就固定保留 **首页、动态、我的**（动态 URI 为 `bilibili://following/home/`），不会再按中文标题筛掉“关注”；无需叠加旧底栏补丁。
其它 UI 处理维持上游默认，包括“我的”中的个性装扮、会员购；上游会员展示字段改写**不代表真实会员权益**。

### 公共拦截范围

- `Block_HTTPDNS.lpx` 仅取第 93 行 `httpdns.bilivideo.com`，与 B 站自身 4 条精确拒绝和 3 条有界 `chat.bilibili.com` 通配一起合并。
- `BlockAdvertisers.lpx` 未找到明确对应 B 站的条目，**不搬入任何条目**，不使用通用广告/HTTPDNS 关键词或其他 App 规则。
- 原 AND+OR 精确展开成 `*stun*.chat.bilibili.com`、`*tracker*.chat.bilibili.com`、`*p2p*.chat.bilibili.com`，不扩大为整个 chat 后缀。
- 不迁移 `bsbsb.top` PROXY 或空降专属 `DmSegMobile`；构建产物禁止出现空降接口/参数入口。

### QX 适配与验证边界

两个 jq 文件已内联。原 `response.body.mock` 按 Loon 的提前响应语义转换为 QX `script-echo-response`，二进制值保留完整 gRPC 5 字节帧头，并合并后续 `grpc-status: 0`；不是先访问上游再改响应。
脚本使用 QX `bodyBytes`/`ArrayBuffer`，固定配置且异常数据保护；下载依赖全部托管到本仓库，运行时无脚本下载或空降服务调用。
评论加载优化采用 **best-effort 请求重放**：QX 1.5.0(824) 起的更新记录支持请求脚本带 `status` 提前响应（[保存的 TestFlight 日志](https://github.com/ddgksf2013/Profile/blob/994fc5a4bea3a58d47bad735f6a470143c42b98d/QX_TestFlight_Update.log#L76-L84)，不是手机验证）。仅在原请求具备支持的二进制帧和 `x-bili-moss-engine-type: 1` 时尝试；收到明确 `grpc-status: 0` 后净化并返回。
QX 没有查到与 Loon 强制 `alpn=h2` / `h2_trailers` 等价的公开接口；没有可靠状态时保留原请求流程，**不能承诺修复所有评论加载问题或完整复现 Loon**。原站失败可能尝试另一 B 站域名，最终放行可能再发一次请求；不使用不能取消网络的 JS 超时并发重试，不承诺网络发送次数始终为一次。
响应仅处理 unary 单帧 gRPC；流式、多帧、未知压缩、非法正文保留原响应，不猜测 Protobuf 字段。gzip 解压依赖 fflate 0.8.2 已内联，GPL-3.0/MIT 许可和原始来源保留在源快照目录。
基础要求：开启 QX 重写和 MitM、安装并信任证书，关闭资源解析器。请求优化关闭自动 Cookie 的选项要求 **QX build 934+**（推荐当前新版，目标用户为 1.90）；旧版本可能忽略该选项，不保证相同重放行为。不能把 Loon 的 `MitM-over-HTTP/2` 开关原样当作 QX 选项。
**未在手机 QX 1.90 上验证实际 HTTP/2、gRPC、证书及评论页面效果；本地协议样例和参数测试不等于手机实测。**
旧 `lists/bilibili.list` 已移除，升级时删除其分流订阅；只刷新稳定的 B 站重写资源及仓库脚本。

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

需要 Python 3.9+、Node.js、jq、esbuild（B 站脚本的离线打包依赖）。构建还需要本地原始镜像，查找位置为当前仓库或父目录的
`mirror/upstream/kelee.one/`；公共仓库不包含个人完整配置、节点或订阅。

```sh
python3 tools/build_qx_repo.py --out .
python3 tools/gen_repo_readme.py .
python3 tools/check_qx.py --dir .
python3 -m unittest discover -s tests -p 'test_*.py' -v
node tests/runtime.cjs
node tests/bilibili-kelee.cjs
```

在镜像工作区运行 `python3 scripts/convert_lpx_to_qx.py` 会使用同一个生成器重建 `qx/`；
其中 `snippets/`、`lists/`、`js/`、`jq/`、`config/` 与 GitHub 发布目录采用相同内容。
`qx/conf/quantumultx.conf` 是本地个人配置，不上传到本仓库。公共规则选择清单在 `tools/shared_scope.py`，
构建先筛选再转换；上游新增无关规则不会自动扩大范围，已选规则消失或策略变化则构建失败。
