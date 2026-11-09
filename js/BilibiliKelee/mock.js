// Generated from Kelee Bilibili LPX; original author kokoryh.
// No network request, storage, subscription parameters or SponsorBlock.
(() => {
  const routes = [{"pattern":"^https://app\\.bilibili\\.com/x/v2/splash/list\\?","body":"{\"code\":0,\"message\":\"OK\",\"ttl\":1,\"data\":{\"max_time\":0,\"min_interval\":31536000,\"pull_interval\":31536000,\"keep_ids\":[],\"show\":[],\"list\":[{}],\"splash_request_id\":\"\"}}","binary":false,"grpc_status":false},{"pattern":"^https://api\\.bilibili\\.com/pgc/activity/deliver/material/receive\\?","body":"{\"code\":0,\"data\":{\"closeType\":\"close_win\",\"container\":[],\"showTime\":\"\"},\"message\":\"success\"}","binary":false,"grpc_status":false},{"pattern":"^https://ap[ip]\\.bilibili\\.com/x/(resource/(top/activity|patch/tab(/v2)?)|v2/search/square|vip/ads/materials)\\?","body":"{\"code\":-404,\"message\":\"-404\",\"ttl\":1,\"data\":null}","binary":false,"grpc_status":false},{"pattern":"^https://grpc\\.biliapi\\.net/bilibili\\.app\\.interface\\.v1\\.Teenagers/ModeStatus$","body":[0,0,0,0,19,10,17,8,2,18,9,116,101,101,110,97,103,101,114,115,32,2,42,0],"binary":true,"grpc_status":true},{"pattern":"^https://grpc\\.biliapi\\.net/bilibili\\.app\\.interface\\.v1\\.Search/DefaultWords$","body":[0,0,0,0,33,26,29,230,144,156,231,180,162,232,167,134,233,162,145,227,128,129,231,149,170,229,137,167,230,136,150,117,112,228,184,187,40,1],"binary":true,"grpc_status":true},{"pattern":"^https://grpc\\.biliapi\\.net/bilibili\\.app\\.(view\\.v1\\.View/TFInfo|viewunite\\.v1\\.View/(PlayPause|ViewEndPage))$","body":[0,0,0,0,0],"binary":true,"grpc_status":true}];
  const url = $request.url;
  const route = routes.find(item => new RegExp(item.pattern, "i").test(url));
  if (!route) { $done({}); return; }
  const response = {status: "HTTP/1.1 200 OK", headers: {"Content-Type": "text/plain; charset=utf-8"}};
  if (route.grpc_status) response.headers["grpc-status"] = "0";
  if (route.binary) {
    // The source base64 contains the ENTIRE five-byte-prefixed gRPC frame.
    const bytes = new Uint8Array(route.body);
    response.bodyBytes = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  } else response.body = route.body;
  $done(response);
})();
