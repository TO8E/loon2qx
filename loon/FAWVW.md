# 一汽大众去广告（Loon）

[插件订阅](https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/FAWVW_remove_ads.lpx) · [原 QuanX 规则](https://raw.githubusercontent.com/zirawell/R-Store/main/Rule/QuanX/Adblock/App/Y/%E4%B8%80%E6%B1%BD%E5%A4%A7%E4%BC%97/rewrite/fawvw.conf)

在 Loon 插件列表添加上述订阅，或在主配置的 `[Plugin]` 中添加：

```ini
https://raw.githubusercontent.com/TO8E/loon2qx/main/loon/plugins/FAWVW_remove_ads.lpx, enabled=true
```

按 [Loon 官方新版重写语法](https://nsloon.app/docs/Rewrite/rewrite_v2/) 转换，要求 Loon `3.5.1(978)` 或更新版本。包含 7 条内联 `response.json.jq`，无需外部脚本；仅声明 `oneapp-api.faw-vw.com` 的 MitM，需开启重写和 MitM 并安装、信任证书。

保留上游的 URL 正则、顺序和 jq 表达式，覆盖集合列表、搜索提示、权益卡片、首页浮标、开屏/汽车学院、首页横幅/金刚区及部分内容流。首条返回 `data: {}`，其余返回 `data: []`，均保留 `returnStatus: "SUCCEED"` 和 `hasMore: false`。

上游提示 App 存在代理检测，建议使用 TUN 模式；**此提示及本版效果均未做手机实测确认**。本地仅核对转换内容、正则匹配样例和 jq 输出，不代表 Loon 原生导入或 App 实际效果已验证。

原作者为 zirawell，2026-11-10 转换为 Loon 语法，按上游 GPL-3.0 许可发布；[原始快照](upstream/fawvw.conf) 与 [许可证全文](upstream/R-Store-LICENSE) 随仓库保留。此插件独立维护，不由公共插件生成器生成，也未加入仅用于替换两个公共插件的 `plugin.conf`。
