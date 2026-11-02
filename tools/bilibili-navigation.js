// QX navigation compatibility for kokoryh's Bilibili enhancement.
// Keep the original Home / Following / Me entries, including their icons and URIs.
// Upstream uses the labels 首页/动态/我的; newer or localized labels may differ.
function qxBilibiliBottomTabs(tabs) {
  if (!Array.isArray(tabs)) return tabs;
  function kind(tab) {
    if (!tab || typeof tab !== "object") return null;
    const uri = String(tab.uri || "").toLowerCase();
    const tabId = String(tab.tab_id || "").toLowerCase();
    const name = String(tab.name || "").toLowerCase();
    if (/^bilibili:\/\/following\/home(?:[/?#]|$)/.test(uri) ||
        ["dynamic", "following"].includes(tabId) || Number(tab.id) === 179 ||
        ["动态", "動態", "关注", "關注", "following", "dynamic"].includes(name)) return "following";
    if (/^bilibili:\/\/main\/home(?:[/?#]|$)/.test(uri) || tabId === "home" ||
        Number(tab.id) === 177 || ["首页", "首頁", "home"].includes(name)) return "home";
    if (/^bilibili:\/\/user_center\/?(?:[?#].*)?$/.test(uri) ||
        ["我的bottom", "mine", "me"].includes(tabId) || Number(tab.id) === 181 ||
        ["我的", "me"].includes(name)) return "me";
    return null;
  }
  const classified = tabs.map(tab => ({tab, kind: kind(tab)}));
  // If the schema is unfamiliar, preserve the response instead of deleting a tab
  // we could not identify. Never fabricate a Following entry or change its route.
  if (!["home", "following", "me"].every(k => classified.some(item => item.kind === k))) return tabs;
  return classified.filter(item => item.kind !== null).map(item => item.tab);
}
