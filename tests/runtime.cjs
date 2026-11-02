const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');let checks=0;
function run(file,url,body,store=new Map(),headers={}){
 const calls=[];
 const context={$request:{url,headers},$response:body===undefined?undefined:{body:typeof body==='string'?body:JSON.stringify(body)},
  $prefs:{valueForKey:k=>store.has(k)?store.get(k):null,setValueForKey:(v,k)=>(store.set(k,v),true),removeValueForKey:k=>store.delete(k)},
  $task:{fetch(){throw Error('unexpected network call');}},$done:(...args)=>calls.push(args),console:{log(){},error(){},warn(){}}};
 vm.runInNewContext(fs.readFileSync(path.join(root,file),'utf8'),context,{timeout:1500,codeGeneration:{strings:false,wasm:false}});
 assert.equal(calls.length,1,file+' must finish once');checks++;
 return {args:calls[0],body:calls[0][0]?.body?JSON.parse(calls[0][0].body):body};
}
const store=new Map();
const xhs='js/RedPaper/RedPaper_remove_ads.js';
run(xhs,'https://edith.xiaohongshu.com/api/sns/v1/note/imagefeed',
 {data:[{note_list:[{images_list:[{live_photo_file_id:'fixture',live_photo:{media:{video_id:'sample',stream:{h265:[{master_url:'https://media.example.test/original.mp4'}]}}}}]}]}]},store);
assert.ok(store.has('redBookLivePhoto'));checks++;
let result=run(xhs,'https://edith.xiaohongshu.com/api/sns/v1/note/live_photo/save',
 {data:{datas:[{file_id:'fixture',url:'https://media.example.test/watermark.mp4'}]}},store);
assert.equal(result.body.data.datas[0].url,'https://media.example.test/original.mp4');checks++;
result=run(xhs,'https://edith.xiaohongshu.com/api/sns/v1/note/live_photo/save',{data:{datas:[]}},new Map());
assert.equal(result.body.data.datas,null);checks++;
result=run(xhs,'https://edith.xiaohongshu.com/api/sns/v1/system_service/config',{data:{splash:{ad:1},app_theme:{},keep:1}});
assert.deepEqual(result.body,{data:{keep:1}});checks++;
result=run('js/JD/JD_remove_ads.js','https://api.m.jd.com/client.action?functionId=start',{images:[{ad:1}],showTimesDaily:3,keep:1});
assert.equal(result.body.images.length,0);assert.equal(result.body.keep,1);checks++;
result=run('js/Taobao/Taobao_remove_ads.js','https://guide-acs.m.taobao.com/gw/mtop.taobao.cloudvideo.video.query',{data:{duration:'5',resources:[{}],caches:[{}],keep:1}});
assert.equal(result.body.data.duration,'0');assert.equal(result.body.data.resources.length,0);checks++;
result=run('js/PuPuMall/PuPuMall_remove_ads.js','https://j1.pupuapi.com/client/marketing/advertisement/v1',{data:[{region_code:30},{region_code:2,positions:[{component_code:890},{component_code:123}]}]});
assert.deepEqual(result.body.data,[{region_code:2,positions:[{component_code:123}]}]);checks++;
const train='js/12306/12306_remove_ads.js',trainUrl='https://mobile.12306.cn/otsmobile/app/mgs/mgw.htm';
assert.equal(run(train,trainUrl,undefined,new Map(),{'operation-type':'com.cars.otsmobile.newHomePage.initData'}).args.length,0);checks++;
assert.equal(run(train,trainUrl,undefined,new Map(),{'operation-type':'com.cars.otsmobile.checkLoginStatus'}).args.length,1);checks++;
for(const file of [xhs,'js/JD/JD_remove_ads.js','js/Taobao/Taobao_remove_ads.js','js/PuPuMall/PuPuMall_remove_ads.js']){
 assert.equal(Object.keys(run(file,'https://fixture.test/', '').args[0]).length,0);checks++;
 const response=run(file,'https://fixture.test/', '<html>upstream error</html>');
 assert.ok(response.args[0].body===undefined || response.args[0].body==='<html>upstream error</html>');checks++;
}
console.log(JSON.stringify({checks,networkRequests:0,phoneTested:false}));
