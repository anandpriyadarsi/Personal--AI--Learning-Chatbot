const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../personal_learning_assistant/ui/web/static/js/mobile-sw.js'), 'utf8');

function worker() {
  const events = {}, stores = new Map();
  const scope = { location: {origin:'https://private.invalid'}, addEventListener:(type,fn)=>events[type]=fn };
  const caches = {
    open:async name=> {
      if (!stores.has(name)) stores.set(name,new Map());
      const data=stores.get(name);
      return {put:async(key,response)=>data.set(key,response),match:async key=>data.get(key)};
    },
    keys:async()=>[...stores.keys()], delete:async name=>stores.delete(name)
  };
  const fetch = async req=> {
    if (typeof req !== 'string' && req.fail) throw new Error('host unavailable');
    return {ok:true,url:'https://private.invalid'+req};
  };
  vm.runInNewContext(source, {self:scope,caches,fetch,URL,Response});
  return {events,stores};
}

async function install(w) {
  let done;
  w.events.install({waitUntil:p=>done=p}); await done;
}

function request(w, pathname, {method='GET',mode='cors',fail=false}={}) {
  let promise;
  w.events.fetch({request:{url:'https://private.invalid'+pathname,method,mode,fail},respondWith:p=>promise=p});
  return promise;
}

test('worker installs only reviewed generic shell assets', async()=> {
  const w=worker();await install(w);
  const paths=[...w.stores.values()][0];
  assert.deepEqual([...paths.keys()].sort(), ['/mobile/offline','/static/css/mobile_v1.css','/static/js/mobile_v1.js',
    '/static/brand/anvaya-mobile-192.png','/static/brand/anvaya-mobile-512.png'].sort());
});

test('academic API responses and query-string assets never enter runtime cache', async()=> {
  const w=worker();await install(w);const paths=[...w.stores.values()][0];
  for (const url of ['/agent/sessions/private','/assessments/private/state','/static/js/mobile_v1.js?private=secret']) {
    assert.equal(request(w,url),undefined);
    assert.equal(paths.has(url),false);
  }
  assert.equal(paths.size,5);
});

test('mutations are left to native network failure handling and never queued or cached', async()=> {
  const w=worker();await install(w);
  assert.equal(request(w,'/agent/sessions/private/ask',{method:'POST',fail:true}),undefined);
  assert.equal([...w.stores.values()][0].size,5);
});

test('offline navigation returns generic fallback without private data', async()=> {
  const w=worker();await install(w);
  const response=await request(w,'/learning/private',{mode:'navigate',fail:true});
  assert.equal(response.url,'https://private.invalid/mobile/offline');
  assert.equal([...w.stores.values()][0].has('/learning/private'),false);
});

test('activation deletes only old mobile cache namespaces', async()=> {
  const w=worker();await install(w);
  w.stores.set('anvaya-mobile-v1-old',new Map());w.stores.set('unrelated',new Map());
  let done;w.events.activate({waitUntil:p=>done=p});await done;
  assert.equal(w.stores.has('anvaya-mobile-v1-old'),false);
  assert.equal(w.stores.has('unrelated'),true);
});
