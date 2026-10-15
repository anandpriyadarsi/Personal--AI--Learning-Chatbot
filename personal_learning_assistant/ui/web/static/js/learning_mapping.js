(() => {
  const root=document.getElementById('ls-mapping');
  const candidates=JSON.parse(document.getElementById('ls-candidates').textContent);
  const result=document.getElementById('ls-mapping-result');
  document.getElementById('ls-mapping-apply').addEventListener('click',async () => {
    const value=document.getElementById('ls-candidate').value;
    if (!value || !document.getElementById('ls-mapping-confirm').checked) { result.textContent='Choose an exact candidate and confirm its semantic fit.';return; }
    const candidate=candidates[Number(value)];const revision=Number(location.pathname.split('/').at(-2));
    try {
      const response=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json','X-Learning-CSRF':root.dataset.csrf},body:JSON.stringify({module_revision:revision+1,course_id:candidate.course_id,topic_id:candidate.topic_id,topic_name:candidate.topic_name,confidence:Number(document.getElementById('ls-mapping-confidence').value),confirmed:true})});
      const data=await response.json();result.textContent=response.ok ? `Revision ${data.revision} staged. Open the staged preview in Learning Studio to review and publish.` : data.error;
    } catch (_) {result.textContent='Connection interrupted. Reopen Learning Studio to check whether a revision was staged.';}
  });
})();
