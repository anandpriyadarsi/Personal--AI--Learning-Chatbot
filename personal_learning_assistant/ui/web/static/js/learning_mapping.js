(() => {
  const root = document.getElementById('ls-mapping');
  const candidates = JSON.parse(document.getElementById('ls-candidates')?.textContent || '[]');
  const result = document.getElementById('ls-mapping-result');
  const apply = document.getElementById('ls-mapping-apply');
  if (!root || !result || !apply) return;
  apply.addEventListener('click', async () => {
    const choice = document.getElementById('ls-candidate');
    const index = Number(choice.value);
    if (choice.value === '' || !Number.isInteger(index) || !candidates[index] ||
        !document.getElementById('ls-mapping-confirm').checked) {
      result.textContent = 'Select a registered subject/topic and confirm the match.';
      return;
    }
    const confidence = Number(document.getElementById('ls-mapping-confidence').value);
    if (!Number.isFinite(confidence) || confidence < .9 || confidence > 1) {
      result.textContent = 'Choose a confidence between 0.90 and 1.00.'; return;
    }
    const candidate = candidates[index];
    const revision = Number(location.pathname.split('/').at(-2));
    if (!Number.isSafeInteger(revision) || revision < 1) {
      result.textContent = 'Invalid module revision; reopen this module.'; return;
    }
    apply.disabled = true;
    result.textContent = 'Checking this subject and preserving your original revision…';
    try {
      const response = await fetch(location.pathname, {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-Learning-CSRF':root.dataset.csrf},
        body:JSON.stringify({module_revision:revision+1, course_id:candidate.course_id,
          topic_id:candidate.topic_id, topic_name:candidate.topic_name, confidence, confirmed:true})
      });
      const data = await response.json();
      if (!response.ok) {
        result.textContent = data.error || 'Linking was not saved. Reopen the module to review.';
        return;
      }
      result.textContent = `Subject link staged in revision ${data.revision}. Review it before publishing. `;
      const link = document.createElement('a');
      link.href = root.dataset.previewUrl;
      link.textContent = 'Open staged revision';
      result.appendChild(link);
    } catch (_error) {
      result.textContent = 'Connection interrupted. Check Learning Studio before trying again; the stage may already exist.';
    } finally { apply.disabled = false; }
  });
})();
