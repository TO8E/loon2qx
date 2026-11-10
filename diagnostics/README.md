# 临时诊断资源（不要作为正式订阅）

> 2026-11-10：正式 `snippets/bilibili.snippet` 已采用 `bilibili-formal-without-grpc.snippet` 的生效规则和主机范围。日常使用请停用诊断资源，启用并刷新[正式订阅](https://raw.githubusercontent.com/TO8E/loon2qx/main/snippets/bilibili.snippet)。下方记录的是历次对照；早期正式版曾包含 grpc 解密，目前正式版已不再声明它。不要同时启用正式版和诊断版。

## B站最近观看慢：隔离 MitM 与响应处理

`bilibili-mitm-only.snippet` 仅用于手机 A/B 测试，不在任何默认配置中订阅。

基线：`ebe1886`。用户 QX 1.90 对比 Loon 原插件时，“头像 → 最近观看”加载慢；在 QX 内仅关闭 MitM 后明显变快。这只能定位到解密及依赖解密的处理链，不能单独证明 TLS/H2 根因。

测试步骤：
1. 恢复 QX 的 MitM 开关为开启。
2. 停用原 `snippets/bilibili.snippet`，仅启用本诊断资源；资源解析器关闭。
3. 保持节点、DNS和其他配置不变，断开再连接 QX，彻底结束 B站后台后重新打开相同页面。
4. 记录耗时变化。测试后删除本诊断资源、恢复正式 B站资源。

本诊断文件与基线正式资源具有逐条一致的8条域名规则和5个MitM主机，但没有针对真实B站请求的URL改写、jq、脚本或mock。保留一条仅匹配保留域名 `qx-bilibili-diagnostic.invalid` 的HTTP拒绝占位，以避免纯域名重写资源曾出现的导入识别问题；它不匹配任何B站地址，也不发起网络请求。

- 若依然慢、而关闭MitM时快：更支持连接/解密处理差异，但仍需网络记录确认。
- 若恢复速度：继续定位响应处理或页面依赖请求；不能归因为纯TLS。

测试期间本资源不执行开屏/推荐/评论/个人页净化，域名层拦截保留。如果还有其他B站资源或本地B站URL规则同时启用，此实验无法有效隔离。

本次仅发布测试副本，未改变正式订阅、域名范围、脚本设置或QX设备配置。公开API静态匹配不等于用户手机真实请求抓包。

## 第二阶段：逐个缩小主机范围

用户在首轮报告：关闭MitM明显变快；恢复MitM、只启用基线诊断版仍慢。下一轮使用 `bilibili-mitm-without-grpc.snippet`，只从上面的诊断基线删去 `grpc.biliapi.net` 的hostname，其余4主机、8域名规则和导入占位逐字节一致，不增加DIRECT或URL跳过规则。

保持MitM开启，停用正式版和第一份诊断，只启用本轮诊断；其它配置不变，重连QX、结束B站后台重开后测试。不要同时启用多份诊断资源。

**遗漏一个hostname不等于覆盖其它来源。**若之前把 `config/mitm.txt` 手工合入主配置，或其他资源含 `grpc.biliapi.net`、`*.biliapi.net` 等匹配通配，该主机仍可能被解密。需确认生效的MitM主机列表中没有这些重复来源；不要只删除远程订阅一处后就声称已排除解密。

本实验没有访问用户历史记录或自动修改设备配置；公开的History RPC说明只用于选择首个测试主机，并非用户真实抓包。结果用于继续定位，不预先认定grpc主机一定是原因。

### 再排除 app 主机

用户报告上一轮仅移除 `grpc.biliapi.net` 后仍慢。这表明仅排除该主机不足以恢复速度，不能据此判定它完全无关。

下一轮使用 `bilibili-mitm-without-grpc-app.snippet`：在上一轮基础上再删去 `app.bilibili.com`，保留 `api.bilibili.com`、`api.live.bilibili.com`、`line3-h5-mobile-api.biligame.com`；8条域名规则和导入占位不变。

MitM仍开启，停用正式资源和前两份诊断，只启用本轮诊断；重连QX并彻底退出B站后测试同一个入口。确认没有其他生效的本地/远程hostname规则包含 `grpc.biliapi.net`、`app.bilibili.com`，或能匹配它们的通配（例如 `*.biliapi.net`、`*.bilibili.com`）。否则应将结果记为无法隔离，而非已证实排除这两个主机。

本轮仍不修改正式版。若明显变快，再恢复 app 主机复测或查看请求日志，才能进一步确认其关联；若仍慢，则需要检查余下主机或重复解密来源。

### 再排除 api 主机（本阶段最后一轮基于公开接口的排除）

用户反馈同时移除 grpc/app 后仍慢。使用 `bilibili-mitm-without-grpc-app-api.snippet`，在上一轮基础上只再移除 `api.bilibili.com`，仍保留直播与游戏两个主机、原8条域名规则和相同占位；不修改正式版。

此域名有公开历史JSON接口，但未确认用户实际调用。保持MitM开启，停用其它B站诊断和正式资源，仅启用本轮；重连QX、彻底退出App后测试。确认本地主机列表、其它订阅或 `*.bilibili.com`/`*.biliapi.net` 通配没有重新纳入前三个主机。

若本轮仍慢，停止继续凭公开URL推测，优先查看实际慢请求的域名/状态/耗时及最终生效的MitM来源。不要把连续“仍慢”直接解释成这些主机都完全无关。若发截图，仅需主机、路径、耗时、状态和命中策略，勿含Cookie、Authorization、完整查询参数或观看记录内容。

## 2026-11-10：确认本地重复声明后，恢复正式规则对照

用户提供的手机主配置仍直接声明 `grpc.biliapi.net`、`app.bilibili.com`、`api.bilibili.com`，因此之前只删除诊断资源中的这些声明，不能认为已排除对应域名的解密。

按同一份 `bilibili-mitm-without-grpc-app-api.snippet` 做前后对照：从主配置移除上述三个域名后，用户反馈“请求速度恢复了。很快。”；随后恢复 `app.bilibili.com` 和 `api.bilibili.com`，继续排除 `grpc.biliapi.net`，用户反馈“仍然快”。这是用户实机反馈，无精确计时或流量记录；说明当前测试中排除 grpc 解密、保留 app/api 解密可以恢复速度，尚未证明具体 TLS/HTTP 协议根因。

下一份 `bilibili-formal-without-grpc.snippet` 用于恢复正式重写后的对照：

- 基线为 `ebe1886` 正式资源，保留全部 23 条重写、8 条域名规则及原脚本地址，仅从 hostname 去掉 `grpc.biliapi.net`；无请求重放。
- 停用正式资源和其他 B 站诊断，仅启用这一份；保持 MitM 开启。主配置保留 app/api 等原有域名，但不包含 grpc；其他生效资源也不得通过精确域名或通配重新纳入 grpc 解密。
- 节点、DNS、分流保持不变；重连 QX、彻底退出并重开 B 站，检查最近观看和视频详情/评论的加载速度，并观察实际去广告变化。
- **它不是功能完整的修复。** 发往 `grpc.biliapi.net` 的评论、相关推荐、动态、热门、搜索、播放器等响应不再执行净化，三个仅匹配 grpc 的提前响应规则也不会生效。对应双主机 RPC 规则仍保留 app 主机分支，但不代表 App 会自动改走该主机；完整排除 grpc 后的真实请求路由尚未确认。
- 开屏、底栏、我的页面等 app/api 上的 JSON 规则及直播处理仍保留；最近观看速度已有下述手机反馈，去广告覆盖完整性尚未验收。
- 当前切换方式：停用本诊断资源，启用并刷新正式订阅；正式版现已采用相同的不含 grpc 主机范围。插件自带主机名，无须恢复旧本地 grpc 声明。

本诊断不在默认订阅中，不改变正式资源、生成器或个人配置；测试结果不能视为已接受永久放弃 grpc 净化。

### 正确配置下的速度反馈

用户发现主配置一行曾被误拼接为重复的 `hostname =`，主机名列表也显示了含此前缀的无效条目。修正后，用户明确确认使用 `bilibili-formal-without-grpc.snippet`、本地保留 app/api/live 而不含 grpc 的组合“速度很快”。这确认当前组合的最近观看速度已恢复，但没有精确计时，也不能将一次组合修正归结为已证明全部底层协议根因。

远程资源自带的 hostname 会参与 MitM，无须在主配置重复填写。编辑主配置时应替换整条 hostname 配置；在“添加主机名”界面只输入域名，不能粘贴 `hostname =` 前缀。此处不自动修改用户手机配置。

### 独立的 gRPC 模拟响应类型修正

核查时发现三类二进制 gRPC 模拟响应被标为 `text/plain; charset=utf-8`，现改为 `application/grpc`，符合 [gRPC 响应协议](https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md#responses)。正文、状态、路由、MitM 范围与其它 JSON 模拟响应保持不变，长度和编码继续由 QX 处理。抓包中一个响应的 61 字节压缩长度与 38 字节解压正文相符，属于正常 gzip，不作为长度错误修复。

27 项相关回归测试及资源静态检查通过。上面的速度恢复反馈发生在该脚本修正发布之前，不能归功于这项修正；它也不补足 HTTP/2 传输能力。响应类型修正本身没有改变解密范围；后续正式发布采用了已验证的排除 grpc 方案。
