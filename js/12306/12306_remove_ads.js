// Generated QX adapter; original attribution retained below.
// Storage uses $prefs; empty/invalid responses pass through; only the first $done is emitted.
((__finish) => {
let __finished = false;
const $done = (...args) => { if (!__finished) { __finished = true; __finish(...args); } };
try {
if (typeof $response !== 'undefined' && !$response.body) { $done({}); return; }
/*
引用地址https://raw.githubusercontent.com/RuCu6/QuanX/main/Scripts/header.js
*/
// 2024-11-24 18:15

const url = $request.url;
const header = $request.headers;
const contype = header["content-type"];
const headopt = header["operation-type"];

if (url.includes("/mobile.12306.cn/otsmobile/app/mgs/")) {
  // 12306页面内容
  const list12306 = [
    // "com.cars.otsmobile.bangbangSafe.deciveInfo", // 设备序列号
    // "com.cars.otsmobile.checkLoginStatus", // 登录信息
    // "com.cars.otsmobile.city",
    // "com.cars.otsmobile.initCountry",
    // "com.cars.otsmobile.initNewSysCache",
    // "com.cars.otsmobile.initProvince",
    "com.cars.otsmobile.integration.activityBanner", // 活动横幅
    "com.cars.otsmobile.memberInfo.getMemberQa", // 铁路会员 常见问题
    // "com.cars.otsmobile.memberInfo.integrationHomeInit", // 铁路会员 会员信息
    // "com.cars.otsmobile.newHomePage.getWeatherByStationCode", // 天气信息
    "com.cars.otsmobile.newHomePage.initData", // 热门资讯
    "com.cars.otsmobile.newHomePageBussData", // 商品信息流
    // "com.cars.otsmobile.newHomePageRefresh",
    "com.cars.otsmobile.paySuccBuss.bussEntryShow" // 商业推广
    // "com.cars.otsmobile.travelPage.initData", // 出行服务
  ];
  if (list12306?.includes(headopt)) {
    $done();
  } else {
    $done({});
  }
} else if (url.includes("/mobilepaas.abchina.com.cn:441/mgw")) {
  // 中国农业银行开屏广告
  const listbankabc = [
    "com.bankabc.recommendcenter.homepage.gethpadverinfo",
    "com.abchina.mbank.common.homepage.getStartParam"
  ];
  if (listbankabc?.includes(headopt)) {
    $done();
  } else {
    $done({});
  }
} else if (url.includes("/sec.sginput.qq.com/q")) {
  // 搜狗输入法候选词推广
  if (contype === "application/octet-stream") {
    $done();
  } else {
    $done({});
  }
} else {
  $done({});
}

} catch (__error) {
console.log('[loon2qx] script passed through: ' + String(__error));
if (!__finished) $done({});
}
})($done);
