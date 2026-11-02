"""Select shared rules for this migration profile before converting them to QX."""
from convert_lpx_to_qx import split_args

TARGETS = {'京东':'jd', '淘宝':'taobao', '闲鱼':'goofish', '高德':'amap',
           'QQ音乐':'qqmusic', '哔哩哔哩':'bilibili'}


def domains(*values):
    return [('DOMAIN', value) for value in values]


# Explicit service-level selection, not a claim that every listed app calls every
# endpoint. Shared Alibaba services can also be used by apps outside this profile.
PROFILES = {
    'Block_HTTPDNS.lpx': [
        dict(apps=['京东'], purpose='京东解析服务',
             basis='原公共插件中 dns.jd.com 及相邻的京东解析地址；不纳入归属不明确的其它 IP。',
             rules=domains('dns.jd.com') + [
                 ('IP-CIDR', '101.124.19.122/32'),
                 ('IP-CIDR6', '2402:db40:5100:1011::5/128')]),
        dict(apps=['淘宝', '闲鱼', '高德'], purpose='阿里系共享解析服务及淘宝调度接口',
             basis='按阿里系服务保留；公共解析端点也可能被其它 App 使用，不是按进程隔离。',
             rules=domains('httpdns.alicdn.com', 'httpdns-api.aliyuncs.com',
                           'httpdns-sc.aliyuncs.com', 'httpdns.danuoyi.tbcache.com') + [
                 ('IP-CIDR', '203.107.1.0/24'),
                 *[('URL-REGEX', r'^http:\/\/' + host + r'\/amdc\/mobileDispatch') for host in [
                     r'amdc\.m\.taobao\.com', r'47\.246\.103\.9', r'47\.246\.103\.10',
                     r'59\.82\.113\.10', r'59\.82\.113\.219']]]),
        dict(apps=['哔哩哔哩'], purpose='B 站解析服务',
             basis='用户已有 B 站增强；仅保留明确的 bilivideo HTTPDNS 域名，不替换其重写。',
             rules=domains('httpdns.bilivideo.com')),
    ],
    'BlockAdvertisers.lpx': [
        dict(apps=['QQ音乐'], purpose='QQ 音乐广告与统计补充',
             basis='只保留 y.qq.com 下的业务域名；tmead/tmeadbak 已在 QQ 音乐自身列表中。',
             rules=domains('tmeadcomm.y.qq.com', 'stat.y.qq.com', 'stat6.y.qq.com')),
        dict(apps=['京东'], purpose='京东广告与统计补充',
             basis='原公共插件中明确位于 jd.com 下的业务域名。',
             rules=domains('dsp-x.jd.com', 'im-x.jd.com', 'xlog.jd.com', 'janapi.jd.com')),
        dict(apps=['淘宝', '闲鱼', '高德'], purpose='阿里系广告、统计与百川服务补充',
             basis='按阿里系共享服务保留；App 自身已有规则不重复搬入，未泛化为所有广告 SDK。',
             rules=domains('et.tanx.com', 'df.tanx.com', 'opehs.tanx.com',
                           'beacon-api.aliyuncs.com', 'adash.man.aliyuncs.com',
                           'atoken.m.taobao.com', 'baichuan-sdk.alicdn.com',
                           'acs4baichuan.m.taobao.com', 'nbsdk-baichuan.alicdn.com',
                           'retcode.alicdn.com', 'arms-retcode.aliyuncs.com')),
    ],
}


def select_shared(filename, text):
    """Return only explicitly selected source rules, with reviewable provenance.

    A changed/missing selected rule fails the build. Unrelated upstream additions
    do not silently expand the migrated profile.
    """
    groups = PROFILES[filename]
    available = {}
    section = ''
    total = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            continue
        if section != 'Rule' or not line or line.startswith(('#', ';')):
            continue
        total += 1
        fields = split_args(line)
        if len(fields) >= 3:
            key = (fields[0].upper(), fields[1].strip('"'))
            available.setdefault(key, (line, number, fields[2].upper()))
    selected = []
    inventory = []
    for group in groups:
        entries = []
        for key in group['rules']:
            if key not in available:
                raise ValueError(f'{filename}: selected shared rule missing: {key}')
            line, number, policy = available[key]
            if policy != 'REJECT':
                raise ValueError(f'{filename}:{number}: selected policy changed: {policy}')
            if line not in selected:
                selected.append(line)
            entries.append(dict(line=number, rule=line))
        inventory.append({k: v for k, v in group.items() if k != 'rules'} | {'entries': entries})
    report = dict(source='https://kelee.one/Tool/Loon/Lpx/' + filename,
                  selected_rules=len(selected), upstream_rule_count=total, groups=inventory)
    return '[Rule]\n' + '\n'.join(selected) + '\n', report
