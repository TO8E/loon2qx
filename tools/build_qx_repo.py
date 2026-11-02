#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 TO8E/loon2qx 仓库内容
  base/      HTTPDNS拦截器 / 广告平台拦截器 → QX 公共依赖(filter 列表)
  lists/     每个插件的分流
  snippets/  每个插件的 [rewrite_local] + [mitm]，脚本走本仓库 raw 地址
  js/ jq/    被引用的脚本 / jq 原文
  config/    可直接粘进 QX 配置的三段(rewrite_remote / filter_remote / mitm)

用法: python3 scripts/build_qx_repo.py --out repo [--raw-base https://raw.githubusercontent.com/TO8E/loon2qx/main]
"""
import glob, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import convert_lpx_to_qx as C           # noqa: E402

MIRROR = os.path.join(ROOT, "mirror")
SRC = os.path.join(MIRROR, "upstream/kelee.one/Tool/Loon/Lpx")
RAW = "https://raw.githubusercontent.com/TO8E/loon2qx/main"

# 公共依赖(所有去广告脚本都默认这两个拦截器已生效)
BASE = [
    ("HTTPDNS拦截器", "Block_HTTPDNS.lpx", "拦截 HTTPDNS 明文解析，保证去广告请求走代理 DNS"),
    ("广告平台拦截器", "BlockAdvertisers.lpx", "拦截穿山甲/巨量/腾讯广告等投放域名"),
]
ENABLED = [
    ("QQ音乐去广告", "QQMusic_remove_ads.lpx", "qqmusic"),
    ("京东去广告", "JD_remove_ads.lpx", "jd"),
    ("下厨房去广告", "XiaChuFang_remove_ads.lpx", "xiachufang"),
    ("淘宝去广告", "Taobao_remove_ads.lpx", "taobao"),
    ("闲鱼去广告", "FleaMarket_remove_ads.lpx", "goofish"),
    ("小红书去广告", "RedPaper_remove_ads.lpx", "xhs"),
    ("彩云天气去广告", "ColorfulClouds_remove_ads.lpx", "caiyun"),
    ("12306去广告", "12306_remove_ads.lpx", "12306"),
    ("酷安去广告", "CoolApk_remove_ads.lpx", "coolapk"),
    ("高德地图去广告", "Amap_remove_ads.lpx", "amap"),
    ("掌上英雄联盟去广告", "LOL_Bible_remove_ads.lpx", "mlol"),
    ("朴朴超市去广告", "PuPuMall_remove_ads.lpx", "pupu"),
    ("Google搜索重定向", "Google.lpx", "google"),
]


def expand_alt(rx):
    """把 (?:a|b) 展开成具体模式，用来反推 HTTPS 重写真正会命中的主机名"""
    out = [rx]
    for _ in range(4):
        new, changed = [], False
        for p in out:
            m = re.search(r"\(\?:([A-Za-z0-9_.|-]+)\)(\?)?", p)
            if not m:
                new.append(p)
                continue
            changed = True
            tail = m.end()
            for a in m.group(1).split("|") + ([""] if m.group(2) else []):
                new.append(p[:m.start()] + a + p[tail:])
        out = new
        if not changed or len(out) > 24:
            break
    return out[:24]


def script_to_raw(url):
    """kelee 脚本 -> 本仓库 raw 路径"""
    for pre in ("https://kelee.one/Resource/JavaScript/", "http://kelee.one/Resource/JavaScript/"):
        if url.startswith(pre):
            return f"{RAW}/js/{url[len(pre):]}"
    return url


def jq_to_repo(url):
    for pre in ("https://kelee.one/Resource/JQLang/", "http://kelee.one/Resource/JQLang/"):
        if url.startswith(pre):
            return f"jq/{url[len(pre):]}"
    return None


def emit(outdir, name, fname, slug, kind, desc):
    r = C.convert(name, fname)
    rw, notes, shown = [], list(r["notes"]), set()
    for rwitem in r["rewrites"]:
        line, note = C.fmt_rewrite(rwitem)
        rx, stage, (typ, arg), _ = rwitem
        if typ.startswith("script") and arg:
            line = f"{rx} url {typ} {script_to_raw(arg)}"
        if note and note not in shown and any(
                k in note for k in ("合并", "脚本", "URL-REGEX", "redirect", "reject(")):
            rw.append(f"# {note}")
            shown.add(note)
        rw.append(line)

    hosts = list(dict.fromkeys(r["hosts"]))
    # 插件 [MitM] 常漏掉 https 重写用到的主机（漏了规则就永远不触发），这里从 URL 补齐
    added = []
    for rwitem in r["rewrites"]:
        rx = rwitem[0].replace("\\/", "/").replace("\\.", ".")
        for variant in expand_alt(rx):
            m = re.match(r"\^?https\??://([A-Za-z0-9.-]+)(?=[\\(/$?])", variant)
            if m:
                h = m.group(1)
                if "." in h and h not in hosts:
                    hosts.append(h)
                    added.append(h)
    if added:
        notes.append("原插件 [MitM] 漏了这些主机，已补: " + ", ".join(added) +
                     "（否则对应 https 重写不会触发）")

    # QX 的远程 rewrite 源只接受裸行（不带 [rewrite_local] / [mitm] 段头），
    # 段头会被 QX 当成无效行报 "invalid line"；hostname 统一写在主配置 [mitm]。
    # QX 远程 rewrite 源：第一行裸 `hostname = …` 才会被合并进 MITM（BoxJS / Sub-Store /
    # Script-Hub 官方文件都是这个写法）；写成 [mitm] 段会被当无效行。
    head = [f"hostname = {', '.join(hosts)}"] if hosts else []
    head += [f"# {name} ← hub.kelee.one/Tool/Loon/Lpx/{fname}",
             f"# {desc}",
             "# 由 loon2qx 自动直译，勿手改（改了源插件就重跑 scripts/build_qx_repo.py）"]
    if notes:
        head.append("# 说明: " + " / ".join(notes))
    body = rw if rw else ["# 本插件无重写"]
    os.makedirs(os.path.join(outdir, kind), exist_ok=True)
    path = os.path.join(outdir, kind, f"{slug}.snippet")
    open(path, "w", encoding="utf-8").write("\n".join(head + body) + "\n")

    lst = None
    if r["filters"]:
        ldir = "base" if kind == "base" else "lists"
        lst = os.path.join(outdir, ldir, f"{slug}.list")
        os.makedirs(os.path.join(outdir, ldir), exist_ok=True)
        open(lst, "w", encoding="utf-8").write(
            f"# {name} 分流（来自 Loon 插件 [Rule] 段）\n" + "\n".join(r["filters"]) + "\n")

    # 收集脚本与 jq
    for rwitem in r["rewrites"]:
        typ, arg = rwitem[2]
        if typ.startswith("script") and arg and "kelee.one" in arg:
            rel = "js/" + arg.split("/Resource/JavaScript/", 1)[1]
            src = os.path.join(MIRROR, "upstream/kelee.one/Resource/JavaScript/",
                               arg.split("/Resource/JavaScript/", 1)[1])
            if os.path.exists(src):
                dst = os.path.join(outdir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
    return dict(name=name, fname=fname, slug=slug, kind=kind,
                rewrite=sum(1 for l in rw if " url " in l),
                filter=len(r["filters"]), hosts=hosts, notes=notes,
                has_list=bool(lst))


def main():
    outdir = os.path.join(ROOT, "repo")
    if "--out" in sys.argv:
        outdir = sys.argv[sys.argv.index("--out") + 1]
    os.makedirs(outdir, exist_ok=True)

    rows = []
    for name, fname, desc in BASE:
        slug = "httpdns" if "HTTPDNS" in name else "advertisers"
        rows.append(emit(outdir, name, fname, slug, "base", desc))
    for name, fname, slug in ENABLED:
        rows.append(emit(outdir, name, fname, slug, "snippets", "由 Loon 插件直译"))

    # 公共规则只留在 base/，插件列表里重复的行剔掉（避免同一域名两处维护）
    base_lines = set()
    for f in ("base/httpdns.list", "base/advertisers.list"):
        fp = os.path.join(outdir, f)
        if os.path.exists(fp):
            base_lines |= {l.strip() for l in open(fp, encoding="utf-8")
                           if l.strip() and not l.startswith("#")}
    dropped = {}
    for lf in sorted(glob.glob(os.path.join(outdir, "lists/*.list"))):
        keep, cut = [], []
        for line in open(lf, encoding="utf-8").read().splitlines():
            if line.strip() and not line.startswith("#") and line.strip() in base_lines:
                cut.append(line.strip())
            else:
                keep.append(line)
        if cut:
            dropped[os.path.basename(lf)] = cut
            slug = os.path.basename(lf)[:-5]
            for r in rows:
                if r["slug"] == slug:
                    r["filter"] -= len(cut)
            keep.insert(1, f"# 与 base/ 公共规则重复的 {len(cut)} 行已剔除: " + "; ".join(cut))
            open(lf, "w", encoding="utf-8").write("\n".join(keep) + "\n")

    # 复制 jq 原文（内联用，仓库留档）
    for f in ("Amap/updatable.jq", "Amap/search_poi_detail.jq"):
        src = os.path.join(MIRROR, "upstream/kelee.one/Resource/JQLang", f)
        if os.path.exists(src):
            dst = os.path.join(outdir, "jq", os.path.basename(f))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    # QX 配置片段
    rw_lines, ft_lines, hosts = [], [], []
    rw_lines.append("# ── 公共依赖（先加载）")
    for r in rows:
        if r["kind"] != "base":
            continue
        rw_lines.append(f"{RAW}/base/{r['slug']}.snippet, tag={r['name']}, "
                        "update-interval=86400, opt-parser=false, enabled=true")
    rw_lines.append("")
    rw_lines.append("# ── 各插件")
    for r in rows:
        if r["kind"] == "base":
            continue
        line = (f"{RAW}/snippets/{r['slug']}.snippet, tag={r['name']}, "
                "update-interval=86400, opt-parser=false, enabled=true")
        if r["slug"] == "caiyun":
            line = ("# 留档未启用（你侧本来就用 ishowshu 原生 caiyun.snippet）: " + line)
        rw_lines.append(line)

    ft_lines.append("# ── 公共依赖（必须开，否则脚本拿不到 httpdns / 广告域名拦截）")
    for r in rows:
        if r["kind"] == "base" and r["has_list"]:
            ft_lines.append(f"{RAW}/base/{r['slug']}.list, tag={r['name']}, "
                            "update-interval=86400, opt-parser=false, enabled=true")
    ft_lines.append("")
    ft_lines.append("# ── 各插件分流")
    for r in rows:
        if r["kind"] != "base" and r["has_list"]:
            line = (f"{RAW}/lists/{r['slug']}.list, tag={r['name']}, "
                    "update-interval=86400, opt-parser=false, enabled=true")
            if r["slug"] == "caiyun":
                line = "# 留档未启用（同上）: " + line
            ft_lines.append(line)

    for r in rows:
        hosts += r["hosts"]
    hosts = list(dict.fromkeys(hosts))

    os.makedirs(os.path.join(outdir, "config"), exist_ok=True)
    open(os.path.join(outdir, "config/rewrite_remote.conf"), "w", encoding="utf-8").write(
        "# 整段替换你现有 [rewrite_remote] 里对应的 13 个 kelee 条目\n" +
        "\n".join(rw_lines) + "\n")
    open(os.path.join(outdir, "config/filter_remote.conf"), "w", encoding="utf-8").write(
        "# 整段替换你现有 [filter_remote] 里对应的 kelee 条目（公共依赖排最前）\n" +
        "\n".join(ft_lines) + "\n")
    open(os.path.join(outdir, "config/mitm.txt"), "w", encoding="utf-8").write(
        "hostname = " + ", ".join(hosts) + "\n")

    json.dump(dict(raw=RAW, rows=rows, hosts=hosts, deduped=dropped),
              open(os.path.join(outdir, "build-info.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"{'插件':22s} {'重写':>4s} {'分流':>4s} {'MITM':>4s}")
    for r in rows:
        print(f"{r['name']:22s} {r['rewrite']:4d} {r['filter']:4d} {len(r['hosts']):4d}")
    print(f"\n重写 {sum(r['rewrite'] for r in rows)} | 分流 {sum(r['filter'] for r in rows)} "
          f"| hostname {len(hosts)}")
    print(f"输出目录: {outdir}")


if __name__ == "__main__":
    main()
