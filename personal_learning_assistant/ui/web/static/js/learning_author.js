/* Local author controls. No document text or credentials are transmitted here. */
(() => {
  'use strict';
  const form=document.querySelector('[data-lecture-author]');
  if(!form)return;
  const course=form.elements.course_id,topics=form.elements.topic_id;
  function scopeTopics(){
    const available=[];
    for(const option of topics.options){
      const allowed=option.dataset.course===course.value;
      option.hidden=!allowed;option.disabled=!allowed;
      if(allowed)available.push(option);
    }
    if(!available.some(option=>option.selected)&&available.length)topics.value=available[0].value;
  }
  course.addEventListener('change',scopeTopics);scopeTopics();
})();
