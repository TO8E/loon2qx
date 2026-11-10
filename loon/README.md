# Loon 原生精简公共插件

基于可莉的 `Block_HTTPDNS.lpx` 和 `BlockAdvertisers.lpx`，按已选插件制定固定白名单。优先减少误杀，接受部分广告覆盖减少。原作者署名保留在各插件中。

## 安装与替换

在 Loon 主配置的 `[Plugin]` 中，用下面两行替换原版的两个公共插件地址，并移至该段最前面。保留其他插件、节点、DNS、策略和证书设置；不要同时启用原版和精简版。

```ini
https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/Block_HTTPDNS.lpx, pin=true, enabled=true
https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/BlockAdvertisers.lpx, pin=true, enabled=true
```

两行配置也保存为 [plugin.conf](plugin.conf)。首次替换后，后续只需刷新这两个订阅。

| 资源 | 分流规则 | 重写 / 脚本 / MITM |
|---|---:|---|
| [HTTPDNS 拦截器（精简版）](https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/Block_HTTPDNS.lpx) | 7 | 无 |
| [广告平台拦截器（精简版）](https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/BlockAdvertisers.lpx) | 4 | 无 |

这两个文件使用 Loon 原生语法，沿用上游标注的最低版本 `3.5.1(998)`，不经过 QX 转换。其他 App 插件可能仍有自己的 MITM、HTTP/2 等要求。

## 范围与逐条选择

仅考虑当前启用的可莉收录版本：QQ 音乐、B 站、酷安、淘宝、Google 搜索重定向、YouTube、小红书、12306、小黑盒、下厨房、朴朴。工具类插件不增加拦截规则；第三方来源的插件与停用插件不作为选取依据。

### HTTPDNS：162 条分流规则中保留 7 条

| 保留规则 | 关联与边界 |
|---|---|
| `DOMAIN, httpdns.bilivideo.com, REJECT` | B 站 HTTPDNS 精确域名 |
| `DOMAIN, httpdns.danuoyi.tbcache.com, REJECT` | 淘宝缓存体系关联解析域名 |
| `http://amdc.m.taobao.com/amdc/mobileDispatch` | 保留原版 URL 正则 |
| `http://47.246.103.9/amdc/mobileDispatch` | 保留原版 URL 正则，不封锁整个 IP |
| `http://47.246.103.10/amdc/mobileDispatch` | 同上 |
| `http://59.82.113.10/amdc/mobileDispatch` | 同上 |
| `http://59.82.113.219/amdc/mobileDispatch` | 同上 |

上述 URL 保持上游的 HTTP、主机和路径前缀匹配语义，不扩大到 HTTPS、其他主机或整个 IP。移除其他 155 条分流规则、全部 6 条重写及 MITM 声明，包括全局 HTTPDNS 关键词、UA、任意 IP URL 和阿里云共享解析网段拦截。

### 广告平台：346 条分流规则中保留 4 条

| 保留规则 | 关联与边界 |
|---|---|
| `DOMAIN, tmeadcomm.y.qq.com, REJECT` | QQ 音乐广告补充 |
| `DOMAIN, stat.y.qq.com, REJECT` | QQ 音乐统计补充 |
| `DOMAIN, stat6.y.qq.com, REJECT` | QQ 音乐统计补充 |
| `AND, ((DOMAIN-KEYWORD, adash), (DOMAIN-SUFFIX, ut.taobao.com)), REJECT` | 必须同时满足关键词和域名后缀边界 |

移除其他 342 条分流规则、全部 4 条重写及 MITM 声明。QQ 音乐原插件已覆盖的 `tmead`、`tmeadbak` 域名不重复添加。字节跳动、通用广告/统计 SDK、推送、登录服务与归属不明的共享规则不纳入；原字节相关 DIRECT 例外也移除，这些请求由现有主配置继续分流。

这些选择基于服务关联，**没有手机流量证据证明每一条都必需**。规则按域名和 URL 生效，不是按 App 进程隔离；其他 App 如果访问相同端点仍可能命中。某个 App 没有额外公共规则，也不代表已经证明它不需要任何公共依赖。

## 来源与维护

- [profile.json](profile.json)：人工审阅的白名单、每条规则的关联 App 和保留理由，以及所选可莉插件的公开来源和摘要。
- [upstream/](upstream/)：两个公共插件的原始字节快照，基准取自 2026-11-10，上游均标注 `2026-10-02 13:57:49`。快照只用于生成审计，不应作为订阅导入。
- [build-info.json](build-info.json)：输入与输出 SHA-256、原始行号、保留和移除数量。
- [生成器](../tools/build_loon_shared.py)：独立于历史 QX 工具，只生成 `loon/` 下的两个插件、两行订阅配置和审计清单。

在仓库根目录执行：

```sh
python3 tools/build_loon_shared.py
python3 tools/build_loon_shared.py --check
python3 -m unittest discover -s tests -p 'test_loon_shared.py' -v
```

生成器不访问网络、不读取个人配置。更新时先审查上游差异，再替换对应快照并更新 `profile.json` 的摘要；不要直接编辑生成后的插件。上游新增规则不会自动纳入；白名单条目消失、规则或动作变化、同一条件出现冲突动作，或快照摘要不符，均会报错。两个来源验证完成后才写入产物。

## 验证边界与手机对照

本地检查覆盖原始规则保留、域名边界、指定 IP 的路径约束、非目标 HTTPDNS/字节/SDK 请求不命中、上游变更保护以及产物可重复生成。Python 匹配检查不等同于 Loon 原生运行验证，也没有抓取实际抖音请求。

重点手机场景是抖音“不进入直播间，在外面观看直播预览”时卡顿。保持网络、节点、其他插件和主配置一致，在相近时间反复对照原版与精简版；切换时重新打开 App，避免沿用旧连接。一次结果不足以排除网络或直播源波动。同步检查常用 App 的登录、播放、购物和去广告效果。

若仍卡顿，保留具体时间、请求域名和 Loon 命中规则，再定位；**本次移除范围不能证明卡顿根因，也不保证已经解决**。其他现有资源仍可能命中同一请求。

需要回退时，将两条订阅恢复为 `https://kelee.one/Tool/Loon/Lpx/Block_HTTPDNS.lpx` 和 `https://kelee.one/Tool/Loon/Lpx/BlockAdvertisers.lpx`，保持其他条件一致。个人完整配置、节点、订阅凭据和证书不属于发布内容。
