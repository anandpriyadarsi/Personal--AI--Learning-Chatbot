/* Original-file manager: no external network, no inline scripts or HTML injection. */
(() => {
  'use strict';
  const root=document.querySelector('.native-files'); if(!root)return;
  try { const saved=localStorage.getItem('anvaya.mobile.theme'); if(['light','dark'].includes(saved))document.documentElement.dataset.theme=saved; } catch {}
  const message=root.querySelector('#files-message');
  const csrf=root.dataset.csrf;
  let upload=null, zoom=100;
  const say=text=>{message.textContent=text;};
  async function api(path, method='GET', body) {
    const response=await fetch(path,{method,headers:body===undefined?{}:{'Content-Type':'application/json','X-Library-CSRF':csrf},body:body===undefined?undefined:JSON.stringify(body),credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Library action failed.');return data;
  }
  const refresh=()=>location.reload();
  const show=id=>document.getElementById(id).showModal();
  const close=el=>el.closest('dialog').close();
  const path=id=>'/library/files/'+encodeURIComponent(id);
  const folders=JSON.parse(document.getElementById('folder-data')?.dataset.folders||'[]');
  root.addEventListener('click',async event=>{
    const button=event.target.closest('[data-action]');if(!button)return;
    const action=button.dataset.action,id=button.dataset.id;
    try {
      if(action==='upload-dialog')show('upload-dialog');
      if(action==='close-dialog')close(button);
      if(action==='upload-cancel'){if(upload){upload.abort();upload=null;say('Upload cancelled. Reload to check whether storage completed.');}close(button);}
      if(action==='toggle-view'){const grid=document.getElementById('file-list').classList.toggle('grid');button.setAttribute('aria-pressed',String(grid));}
      if(action==='rename'||action==='move-course'){
        const d=(await api(path(id))).document;
        const form=document.getElementById(action==='rename'?'rename-form':'course-form');
        form.elements.id.value=id;
        if(action==='rename')form.elements.display_name.value=d.display_name;
        else {
          const input=form.elements.subject_id;
          if(d.subject_id&&!Array.from(input.options).some(o=>o.value===d.subject_id))input.add(new Option('Assigned course (unavailable)',d.subject_id));
          input.value=d.subject_id||'';
        }
        show(action==='rename'?'rename-dialog':'course-dialog');
      }
      if(action==='edit'){
        const d=(await api(path(id))).document, form=document.getElementById('edit-form');
        for(const key of ['id','display_name','folder_id','subject_id','topic']){
          const input=form.elements[key];
          if(key==='subject_id'&&d[key]&&!Array.from(input.options).some(o=>o.value===d[key])){input.add(new Option('Assigned subject (unavailable)',d[key]));}
          input.value=d[key]||'';
        }
        form.elements.tags.value=d.tags.join(', ');
        document.getElementById('document-details').textContent=`Original: ${d.original_name}\nType: ${d.mime}\nSize: ${d.size} bytes\nSHA-256: ${d.sha256}\nStored: ${d.created_at}\n${d.status_label}\n${d.status_detail}\n${d.storage_location}`;
        show('edit-dialog');
      }
      if(action==='delete'&&confirm('Permanently delete this document and its search index? Other copies remain.')){await api(path(id),'DELETE',{confirm:true});refresh();}
      if(action==='copy'){await api(path(id)+'/copy','POST',{});refresh();}
      if(action==='retry'){await api(path(id)+'/index','POST',{rebuild:true});refresh();}
      if(action==='index-toggle'){await api(path(id)+'/index','POST',{enabled:button.dataset.enabled==='true'});refresh();}
      if(action==='ocr'&&confirm('Run optional local English OCR? This can take time and use battery. Original PDF stays unchanged.')){await api(path(id)+'/index','POST',{rebuild:true,ocr:true});refresh();}
      if(action==='rebuild-all'&&confirm('Rebuild private content search for documents with indexing enabled? Originals stay unchanged.')){await api('/library/files/rebuild','POST',{});refresh();}
      if(action==='folder-new'||action==='folder-edit'){
        const form=document.getElementById('folder-form'),folder=action==='folder-edit'?folders.find(f=>f.id===root.dataset.folder):null;
        form.elements.id.value=folder?.id||'';form.elements.name.value=folder?.name||'';
        form.elements.parent_id.value=folder?(folder.parent_id||''):(root.dataset.folder||'');
        form.querySelector('[data-action=folder-delete]').hidden=!folder;show('folder-dialog');
      }
      if(action==='folder-delete'&&confirm('Delete this empty folder?')){const id=document.getElementById('folder-form').elements.id.value;await api('/library/files/folders/'+id,'DELETE',{confirm:true});location.href='/library/files';}
      if(action==='fullscreen'){
        if(root.classList.contains('reader-focus')){root.classList.remove('reader-focus');button.textContent='Fullscreen';}
        else if(document.fullscreenElement){await document.exitFullscreen();}
        else {try{await root.requestFullscreen();}catch{root.classList.add('reader-focus');}button.textContent='Exit fullscreen';}
      }
      if(action==='zoom-in'||action==='zoom-out'){zoom=Math.max(50,Math.min(300,zoom+(action==='zoom-in'?25:-25)));document.getElementById('pdf-page').style.width=zoom+'%';}
      if(action==='share-original'){
        // A real anchor tap carries the gesture into the native intent policy.
        if(/; wv\)/.test(navigator.userAgent)||/\bwv\b/.test(navigator.userAgent))return;
        event.preventDefault();
        const identity=id||root.dataset.document;
        const metadata=(await api(path(identity))).document;
        if(metadata.size>30*1024*1024)throw new Error('For files above 30 MiB, use Save / Export and share through your file manager.');
        const response=await fetch(path(identity)+'/original?download=1');if(!response.ok)throw new Error('Original unavailable.');
        const file=new File([await response.blob()],metadata.filename,{type:metadata.mime});
        if(navigator.canShare?.({files:[file]})){await navigator.share({files:[file],title:metadata.display_name});}
        else say('This browser cannot share files directly. Use Save / Export, then share through your file manager.');
      }
    }catch(error){say(error.message);}
  });
  document.getElementById('upload-form')?.addEventListener('submit',event=>{
    event.preventDefault();if(upload)return;
    const form=event.target,data=new FormData(form);data.set('indexing',String(form.elements.indexing.checked));
    const progress=document.getElementById('upload-progress');progress.hidden=false;
    upload=new XMLHttpRequest();upload.open('POST','/library/files/upload');upload.setRequestHeader('X-Library-CSRF',csrf);
    upload.upload.onprogress=e=>{if(e.lengthComputable)progress.value=Math.round(100*e.loaded/e.total);};
    upload.onload=()=>{const request=upload;upload=null;try{const data=JSON.parse(request.responseText);if(request.status>=400)throw new Error(data.error||'Upload failed.');location.href='/library/files?folder_id='+encodeURIComponent(root.dataset.folder||'');}catch(e){say(e.message);document.getElementById('upload-dialog').close();}};
    upload.onerror=()=>{upload=null;say('Upload interrupted. Retry the original document.');document.getElementById('upload-dialog').close();};
    upload.send(data);
  });
  for(const [formId,field] of [['rename-form','display_name'],['course-form','subject_id']]){
    document.getElementById(formId)?.addEventListener('submit',async event=>{
      event.preventDefault();const form=event.target;
      try{await api(path(form.elements.id.value),'PATCH',{[field]:form.elements[field].value||null});refresh();}
      catch(e){say(e.message);close(form);}
    });
  }
  document.getElementById('edit-form')?.addEventListener('submit',async event=>{
    event.preventDefault();const form=event.target;
    try{await api(path(form.elements.id.value),'PATCH',{display_name:form.elements.display_name.value,folder_id:form.elements.folder_id.value||null,subject_id:form.elements.subject_id.value||null,topic:form.elements.topic.value,tags:form.elements.tags.value.split(',').map(t=>t.trim()).filter(Boolean)});refresh();}catch(e){say(e.message);close(form);}
  });
  document.getElementById('folder-form')?.addEventListener('submit',async event=>{
    event.preventDefault();const form=event.target,id=form.elements.id.value;
    try{await api('/library/files/folders'+(id?'/'+id:''),id?'PATCH':'POST',{name:form.elements.name.value,parent_id:form.elements.parent_id.value||null});refresh();}catch(e){say(e.message);close(form);}
  });
  async function withinMatches(q,offset=0) {
    const results=document.getElementById('within-results');
    const data=await api('/library/files/search?document_id='+root.dataset.document+'&q='+encodeURIComponent(q)+'&offset='+offset);
    if(offset===0)results.replaceChildren();
    results.querySelector('button')?.remove();
    for(const hit of data.matches){
      const link=document.createElement('a');link.href=hit.open_url;
      link.textContent=(hit.kind==='pdf'?'Page ':'Slide ')+hit.position+' — '+hit.snippet;
      const p=document.createElement('p');p.append(link);results.append(p);
    }
    if(data.matches.length===50){
      const more=document.createElement('button');more.type='button';more.textContent='More matches';
      more.addEventListener('click',async()=>{more.disabled=true;try{await withinMatches(q,offset+50);}catch(e){more.disabled=false;say(e.message);}});
      results.append(more);
    }else if(!data.matches.length&&offset===0){results.textContent='No indexed matches. Check the search status in Library.';}
  }
  document.getElementById('within-search')?.addEventListener('submit',async event=>{
    event.preventDefault();try{await withinMatches(event.target.elements.q.value);}catch(e){say(e.message);}
  });
  document.querySelector('.browser-pdf')?.addEventListener('toggle',event=>{if(event.target.open){const frame=document.getElementById('original-pdf');if(!frame.src)frame.src=frame.dataset.src;}});
  document.getElementById('pdf-page')?.addEventListener('error',()=>say('Visual preview unavailable on this device. Use Open in document app or Browser PDF viewer.'));
  const rows=Array.from(document.querySelectorAll('[data-document-id]'));
  if(rows.length){const timer=setInterval(async()=>{if(document.hidden)return;try{const data=await api('/library/files/status?ids='+rows.map(r=>r.dataset.documentId).join(','));let pending=false;for(const d of data.documents){const row=rows.find(r=>r.dataset.documentId===d.id);row.querySelector('[data-status]').textContent=d.status_label;pending ||= ['stored','indexing'].includes(d.status);}if(!pending)clearInterval(timer);}catch{clearInterval(timer);}},2500);}
})();
