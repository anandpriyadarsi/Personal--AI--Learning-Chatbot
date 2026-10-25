/* Only expanded sections fetch/render content; drafts remain visible after errors. */
(() => {
  'use strict';
  const root=document.getElementById('nested-notes'); if(!root)return;
  const list=root.querySelector('#section-list'), status=root.querySelector('#section-status');
  const search=root.querySelector('#section-search'), multiple=root.querySelector('#section-multiple');
  const editor=root.querySelector('#section-editor'), title=root.querySelector('#section-title'), body=root.querySelector('#section-body');
  const base=root.dataset.sectionsUrl; let version='', rows=[], editing=null, editVersion='', busy=false, generation=0, timer;
  // Focus Reading must expose the entire note without editing/upload controls.
  // Save the reader's pre-focus state so exiting focus restores normal editing.
  const keyPoints=document.querySelector('.anvaya-native-reader-header .reader-summary');
  let focusSnapshot=null;
  function syncFocusReading(){
    if(document.body.classList.contains('workspace-focus')){
      if(!focusSnapshot){
        focusSnapshot={
          multiple:multiple.checked,
          open:new Set(Array.from(list.querySelectorAll('.mini-note[open]'),item=>item.id)),
          search:search.value,
          keyPointsOpen:keyPoints?keyPoints.open:false
        };
        if(search.value){
          search.value='';clearTimeout(timer);
          load().catch(e=>tell(e.message));
          return;
        }
      }
      multiple.checked=true;
      if(keyPoints)keyPoints.open=true;
      list.querySelectorAll('.mini-note').forEach(item=>{item.open=true;});
    }else if(focusSnapshot){
      const previous=focusSnapshot;focusSnapshot=null;
      multiple.checked=previous.multiple;
      if(keyPoints)keyPoints.open=previous.keyPointsOpen;
      list.querySelectorAll('.mini-note').forEach(item=>{item.open=previous.open.has(item.id);});
      if(search.value!==previous.search){
        search.value=previous.search;clearTimeout(timer);
        load().catch(e=>tell(e.message));
      }
    }
  }
  new MutationObserver(syncFocusReading).observe(document.body,{attributes:true,attributeFilter:['class']});
  const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const tell=(text)=>{status.textContent=text;};
  async function request(url,options={}) {const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});const value=await r.json();if(!r.ok)throw new Error(value.error||'Request failed. Keep your draft and retry.');return value;}
  async function mutate(action,values={},expected=version){
    if(busy)return null;busy=true;root.setAttribute('aria-busy','true');
    try {const value=await request(base,{method:'POST',headers:{'Content-Type':'application/json','X-Notes-CSRF':root.dataset.csrf},body:JSON.stringify({action,expected_updated_at:expected,...values})});await load();tell('Saved.');return value;}
    catch(e){tell(e.message);return null;}finally{busy=false;root.setAttribute('aria-busy','false');}
  }
  function edit(section,readVersion){editing=section.id||'';editVersion=readVersion;title.value=section.title||'';body.value=section.body||'';editor.hidden=false;title.focus();editor.scrollIntoView({block:'nearest',behavior:'auto'});}
  function action(label,fn){const b=node('button',label);b.type='button';b.addEventListener('click',fn);return b;}
  async function expand(details,section){
    const content=details.querySelector('.mini-note-content'); if(content.dataset.loaded)return;
    content.textContent='Loading section…';
    try {const data=await request(`${base}/${section.id}`);if(!details.isConnected)return;
      const article=node('article');article.className='anvaya-native-rendered-note';article.innerHTML=data.html;
      // The server renders using the existing sanitized Markdown boundary.
      article.querySelectorAll('li').forEach(li=>{const text=li.firstChild;if(text&&text.nodeType===3&&/^\[[ xX]\] /.test(text.textContent)){const checked=/^\[[xX]\]/.test(text.textContent);text.textContent=text.textContent.slice(4);const box=node('input');box.type='checkbox';box.checked=checked;box.disabled=true;li.prepend(box);}});
      const tools=node('div');tools.className='mini-note-actions';
      tools.append(action('Edit',()=>edit(data,data.version)),action('Duplicate',()=>mutate('duplicate',{section_id:section.id})));
      tools.append(action('Attach file',()=>{const picker=document.getElementById('media-section');if(picker){picker.value=section.id;document.getElementById('notes-media').scrollIntoView({block:'start'});}}));
      if(section.id!=='original-content'){
        const index=rows.filter(s=>s.id!=='original-content').findIndex(s=>s.id===section.id);
        ['Move up','Move down'].forEach((label,offset)=>tools.append(action(label,()=>{if(search.value){tell('Clear search before reordering.');return;}const order=rows.filter(s=>s.id!=='original-content').map(s=>s.id);const next=index+(offset?1:-1);if(next<0||next>=order.length)return;[order[index],order[next]]=[order[next],order[index]];mutate('reorder',{order});})));
        tools.append(action('Move to main note',async()=>{
          try {const result=await request(base+'/destinations');const dialog=node('form');const select=node('select');select.setAttribute('aria-label','Destination main note');result.notes.forEach(n=>{const o=node('option',n.title);o.value=n.id;o.dataset.version=n.version;select.append(o);});if(!select.options.length){tell('Create another main note first.');return;}dialog.append(select,action('Move section',async()=>{const o=select.selectedOptions[0];await mutate('move',{section_id:section.id,target_note_id:o.value,target_updated_at:o.dataset.version});}),action('Cancel',()=>dialog.remove()));tools.append(dialog);}catch(e){tell(e.message);}
        }));
        tools.append(action('Delete',()=>{if(confirm(`Delete “${section.title}”? Its attachments will remain on the main note.`))mutate('delete',{section_id:section.id});}));
      }
      const extra=node('details');extra.className='mini-note-more';extra.append(node('summary','More actions'));
      Array.from(tools.children).filter(b=>!['Edit','Attach file'].includes(b.textContent)).forEach(b=>extra.append(b));tools.append(extra);
      const files=node('div');files.className='mini-note-files';
      const attachments=await request(document.getElementById('notes-media').dataset.url);
      attachments.attachments.filter(a=>a.section_id===section.id).forEach(a=>{const link=node('a',a.filename);link.href=a.open_url;files.append(link);});
      content.replaceChildren(article,files,tools);content.dataset.loaded='1';
    }catch(e){content.textContent=e.message;}
  }
  async function load(){
    const sequence=++generation;const value=await request(base+'?q='+encodeURIComponent(search.value));if(sequence!==generation)return;
    version=value.version;rows=value.sections;list.replaceChildren();
    rows.forEach(section=>{const d=node('details');d.className='mini-note';d.id='mini-'+section.id;
      const summary=node('summary',section.title+(section.attachment_count?` · ${section.attachment_count} files`:''));const content=node('div');content.className='mini-note-content';d.append(summary,content);
      d.addEventListener('toggle',()=>{if(d.open){if(!multiple.checked)list.querySelectorAll('.mini-note[open]').forEach(other=>{if(other!==d)other.open=false;});expand(d,section);}});list.append(d);
    });
    tell(rows.length?`${rows.length} sections`:'No sections found. Add one below.');
    // Attachment scope is populated independently of search so an active filter
    // cannot silently reset a section-specific upload to the main note.
    const all=search.value?await request(base):value;const select=document.getElementById('media-section');if(select){const selected=select.value;select.replaceChildren(new Option('Main note',''));all.sections.forEach(s=>select.add(new Option(s.title,s.id)));select.value=selected;}
    syncFocusReading();
  }
  root.querySelector('#section-add').addEventListener('click',()=>edit({},version));
  root.querySelector('#section-cancel').addEventListener('click',()=>{editor.hidden=true;});
  editor.addEventListener('submit',async e=>{e.preventDefault();const result=await mutate(editing?'edit':'add',{section_id:editing,title:title.value,body:body.value},editVersion);if(result)editor.hidden=true;});
  root.querySelector('#sections-collapse').addEventListener('click',()=>list.querySelectorAll('.mini-note').forEach(d=>d.open=false));
  root.querySelector('#sections-expand').addEventListener('click',()=>{multiple.checked=true;list.querySelectorAll('.mini-note').forEach(d=>d.open=true);});
  search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>load().catch(e=>tell(e.message)),200);});
  document.addEventListener('notes-media-changed',()=>{if(editor.hidden)load().catch(e=>tell(e.message));});
  load().catch(e=>tell(e.message));
})();
