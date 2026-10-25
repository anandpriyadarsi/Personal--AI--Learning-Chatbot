(() => {
  if (!document.querySelector('.learning-reader')) return;
  const dialog = document.createElement('dialog');
  dialog.id = 'ls-media-dialog'; dialog.className = 'ls-media-dialog';
  dialog.setAttribute('aria-label','Expanded learning figure');
  const controls = document.createElement('div'); controls.className = 'ls-media-controls';
  const close = document.createElement('button'); close.id='ls-media-close'; close.type='button'; close.textContent='Close figure';
  const zoom = document.createElement('button'); zoom.id='ls-media-zoom'; zoom.type='button'; zoom.textContent='Zoom to original';
  const frame = document.createElement('div'); frame.className='ls-media-frame'; frame.tabIndex=0;
  const large = document.createElement('img');
  const caption = document.createElement('p');
  controls.append(close,zoom); frame.append(large); dialog.append(controls,frame,caption); document.body.append(dialog);
  let trigger = null;
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>trigger?.focus());
  zoom.addEventListener('click',()=>{
    const enabled = dialog.classList.toggle('is-zoomed');
    zoom.textContent = enabled ? 'Fit screen' : 'Zoom to original';
  });
  document.querySelectorAll('.ls-block-image img,.ls-source-peek img,.ls-source-page img,.ls-selected-original img').forEach(image=>{
    // All of these URLs were generated for owned raster assets by Flask.
    const source = new URL(image.src,location.href);
    if (source.origin !== location.origin || !/^\/learning\/modules\/[^/]+\/\d+\/assets\//.test(source.pathname)) return;
    image.tabIndex=0; image.setAttribute('role','button'); image.setAttribute('aria-haspopup','dialog');
    image.setAttribute('aria-label',`Expand figure: ${image.alt}`);
    const open = ()=>{
      trigger=image; large.src=image.src; large.alt=image.alt;
      caption.textContent=image.closest('figure')?.querySelector('figcaption')?.textContent || image.alt;
      dialog.classList.remove('is-zoomed'); zoom.textContent='Zoom to original';
      dialog.showModal(); close.focus();
    };
    image.addEventListener('click',open);
    image.addEventListener('keydown',event=>{
      if (event.key==='Enter' || event.key===' ') {event.preventDefault();open();}
    });
  });
})();
