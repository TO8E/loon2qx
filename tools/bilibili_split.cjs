'use strict';
// Build-only AST pruning of this exact, reviewed protobuf snapshot. No runtime deps.
// Node's bundled Acorn requires --expose-internals; unknown source fails closed.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const acorn=require('internal/deps/acorn/acorn/dist/acorn');
const walk=require('internal/deps/acorn/acorn-walk/dist/walk');
const [coreFile,runtimeFile,outDir]=process.argv.slice(2);
assert(coreFile&&runtimeFile&&outDir,'Usage: node --expose-internals bilibili_split.cjs core runtime out');
const core=fs.readFileSync(coreFile,'utf8'),runtime=fs.readFileSync(runtimeFile,'utf8');
assert.equal(crypto.createHash('sha256').update(core).digest('hex'),
 '0f416d54c2cd49cd030cef19325a9b73d293b2c3f8c488ef306305eefc283198',
 'Reviewed protobuf core changed: re-audit constructors/initializers before pruning');
const rt=acorn.parse(runtime,{ecmaVersion:'latest'});
const routesNode=rt.body.flatMap(n=>n.declarations||[]).find(d=>d.id.name==='QX_ROUTES').init;
const routes=Object.fromEntries(routesNode.properties.map(p=>[p.key.value,p.value.name]));
const groups={reply:{},video:{}};
for(const [route,handler] of Object.entries(routes)){
 if(route.includes('.Reply/'))groups.reply[route]=handler;
 else if(/\.view(?:unite)?\./.test(route))groups.video[route]=handler;
}
assert.equal(Object.keys(groups.reply).length,1);assert.equal(Object.keys(groups.video).length,7);
const ast=acorn.parse(core,{ecmaVersion:'latest'}),units=[];
for(const n of ast.body){
 if(n.type==='VariableDeclaration')for(const d of n.declarations){
  assert.equal(d.id.type,'Identifier');units.push({name:d.id.name,node:d,code:n.kind+' '+core.slice(d.start,d.end)+';',init:d.init});
 }else units.push({name:n.id?.name,node:n,code:core.slice(n.start,n.end)});
}
const start=units.findIndex(u=>u.name==='Ce');assert(start>0);
const base=units.slice(0,start),rest=units.slice(start);
const byName=new Map(units.filter(u=>u.name).map(u=>[u.name,u]));
// Use every identifier as a dependency superset, including closures/shadowed locals.
// Over-retention is intentional: never risk dropping a reference for better size.
for(const u of units){u.deps=new Set();walk.full(u.node,n=>{
 if(n.type==='Identifier'&&byName.has(n.name)&&n.name!==u.name)u.deps.add(n.name);
});}
const classes=new Set(rest.filter(u=>u.init?.type==='ClassExpression').map(u=>u.name));
for(const u of rest){
 assert(u.name,'Unexpected standalone side effect in descriptors');const n=u.init;
 if(n?.type==='ClassExpression'){
  assert.equal(n.superClass?.name,'m');
  for(const method of n.body.body){assert.equal(method.type,'MethodDefinition');assert(!method.static&&!method.computed);}
  const c=n.body.body.find(m=>m.kind==='constructor');assert.equal(c.value.body.body.length,1);
  const call=c.value.body.body[0].expression;assert.equal(call.type,'CallExpression');assert.equal(call.callee.type,'Super');
 }else if(n?.type==='NewExpression'){assert(classes.has(n.callee.name));assert.equal(n.arguments.length,0);}
 else assert(!n||['ArrowFunctionExpression','CallExpression'].includes(n.type),'Unknown initializer');
}
// The pinned base constructor uses Ii.value=this immediately before Object.create
// copies that property descriptor into each instance's own prototype. No later
// read depends on the final Ii value. Enum IIFEs modify only their own enum object;
// other post-base initializers are functions. Hash lock covers this manual audit.
fs.mkdirSync(outDir,{recursive:true});const report={};
for(const [group,table]of Object.entries(groups)){
 const needed=new Set(base.filter(u=>u.name).map(u=>u.name));
 const add=name=>{if(needed.has(name))return;needed.add(name);for(const d of byName.get(name).deps)add(d);};
 Object.values(table).forEach(add);
 const selected=units.filter(u=>!u.name||needed.has(u.name));
 const filteredRuntime=runtime.slice(0,routesNode.start)+'{'+Object.entries(table).map(([k,v])=>JSON.stringify(k)+':'+v).join(',')+'}'+runtime.slice(routesNode.end);
 fs.writeFileSync(path.join(outDir,group+'.js'),selected.map(u=>u.code).join('\n')+'\n'+filteredRuntime);
 report[group]={routes:Object.keys(table),retained_descriptors:selected.filter(u=>u.init?.type==='NewExpression'&&classes.has(u.init.callee.name)).length};
}
process.stdout.write(JSON.stringify(report));
