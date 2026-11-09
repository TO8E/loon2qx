'use strict';
// Correctness regression for CPU/memory changes; not a phone/network benchmark.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const runtime=fs.readFileSync(path.join(root,'tools/bilibili_kelee_runtime.js'),'utf8');
const start=runtime.indexOf('let qxCRCTable;'),end=runtime.indexOf('function qxGunzip(');
assert(start>=0&&end>start);
const ctx=vm.createContext({Uint32Array});vm.runInContext(runtime.slice(start,end),ctx);
const fast=ctx.qxCRC;
function reference(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;for(let j=0;j<8;j++)crc=(crc>>>1)^(crc&1?0xedb88320:0);}return(crc^0xffffffff)>>>0;}
assert.equal(fast(Buffer.alloc(0)),0);assert.equal(fast(Buffer.from('123456789')),0xcbf43926);
let seed=1,checks=2;
for(const size of [1,2,3,15,255,256,257,1024,4096,65536,131072])for(let trial=0;trial<5;trial++){
 const data=Buffer.alloc(size+14);for(let i=0;i<data.length;i++){seed=(Math.imul(seed,1664525)+1013904223)|0;data[i]=seed>>>24;}
 const part=data.subarray(5,size+5);assert.equal(fast(part),reference(part));checks++;
}
const frameStart=runtime.indexOf('function qxFrame('),frameEnd=runtime.indexOf('function qxCleanHeaders(');
const fctx=vm.createContext({Uint8Array,DataView});vm.runInContext(runtime.slice(frameStart,frameEnd),fctx);
for(const length of [0,1,19,1024,65536]){
 const src=new Uint8Array(length+30);src.fill(0xad);const slice=src.subarray(13,13+length);slice.fill(0x42);
 const result=fctx.qxFrame(slice);assert(result instanceof ArrayBuffer);assert.equal(result.byteLength,length+5);const bytes=new Uint8Array(result);assert.equal(bytes[0],0);assert.equal(new DataView(result).getUint32(1),length);assert.deepEqual(Array.from(bytes.subarray(5)),Array.from(slice));
 if(length){slice[0]=0;assert.equal(bytes[5],0x42);}checks++;
}
for(const [name,bound]of [['reply',55000],['video',72000]]){
 const source=fs.readFileSync(path.join(root,'js/BilibiliKelee',name+'.js'),'utf8');
 assert(Buffer.byteLength(source)<bound,name+' bundle grew; review dependency pruning');checks++;
}
console.log(JSON.stringify({checks,crc_vectors_match:true,frame_slices_preserved:true,phone_tested:false}));
