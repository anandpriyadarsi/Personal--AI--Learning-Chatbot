"""Conservative reading diagnostics, separate from who supplied the reading.

Observed means supplied/readable evidence, never verified mathematics. This
small marker check complements structured unresolved spans; it is not OCR or
proof that an embedded text layer represents all visible mathematical content.
"""
import re


def assess_reading(text, *, origin, declared_uncertain, review_complete=False):
    if not isinstance(text,str) or len(text)>16000:raise ValueError('Invalid bounded reading')
    if not isinstance(origin,str) or not origin:raise ValueError('Reading origin required')
    if type(review_complete) is not bool:raise ValueError('Review completion must be explicit boolean')
    if (not isinstance(declared_uncertain,list) or len(declared_uncertain)>50 or
        any(not isinstance(x,str) or not x.strip() or len(x)>500 for x in declared_uncertain)):
        raise ValueError('Invalid unresolved spans')
    uncertain=list(dict.fromkeys(x.strip() for x in declared_uncertain))
    # Quoted program strings are data, not a mathematical uncertainty marker.
    clean=re.sub(r'''(?s)(["'])(?:\\.|(?!\1).)*?\1''','',text)
    diagnostics=[]
    if origin=='user_transcription' and not review_complete:
        diagnostics.append('Review incomplete: explicitly confirm critical symbols or correct the listed unresolved entries.')
    if re.search(r'\[[^\]]*\?[^\]]*\]|\bentry\s*[=:]?\s*\?',clean,re.I):
        diagnostics.append('Matrix/entry contains an unresolved ? symbol; identify the row and column.')
    if re.search(r'\[[^\]]*(?:\+\s*/\s*-|-\s*/\s*\+)[^\]]*\]|[\^_]\s*\{?\?|/\s*\?',clean):
        diagnostics.append('Critical sign, exponent or denominator remains unresolved; correct the selected reading.')
    if re.search(r'(?<!\w)(?:0\s*/\s*O|1\s*/\s*l)(?!\w)',clean):
        diagnostics.append('Symbol alternatives 0/O or 1/l remain unresolved.')
    critical=r'(?:matrix|entry|symbol|sign|row|fraction|denominator|exponent|superscript|visual content)'
    ambiguous=r'(?:unknown|unclear|ambiguous|missing|illegible|unreadable|cropped)'
    if re.search(rf'\b{critical}\b[^.\n]{{0,70}}\b{ambiguous}\b|\b{ambiguous}\b[^.\n]{{0,70}}\b{critical}\b',clean,re.I):
        diagnostics.append('Critical source content is explicitly unclear: '+clean.strip()[:300])
    if not text.strip():diagnostics.append('No readable source text; supply a reading or clearer image.')
    for diagnostic in diagnostics:
        if diagnostic not in uncertain:uncertain.append(diagnostic)
    return dict(status='unknown' if uncertain else 'observed',uncertain=uncertain[:50],
                origin=origin,review_complete=review_complete)


def unclear_reading(hit):
    """Reassess old ambiguous artifacts without changing immutable history."""
    loc=hit.locator
    if not loc.get('mm_locator'):return []
    result=assess_reading(hit.text,origin=loc.get('mm_kind','embedded_text'),
                          declared_uncertain=list(loc.get('mm_uncertain') or []),
                          review_complete=str(loc.get('mm_recipe','')).endswith(':review-complete'))
    reasons=result['uncertain']
    if loc.get('mm_status')=='unknown' and not reasons:reasons=['Reading has unresolved critical symbols; review the source again.']
    return reasons


def clarification_for_plan(plan):
    details=[]
    selection=getattr(plan,'evidence_selection',None)
    considered=selection.considered_hits if selection else plan.hits
    labels={h.chunk_id:'S'+str(n) for n,h in enumerate(plan.hits,1)}
    for number,hit in enumerate(considered,1):
        reasons=unclear_reading(hit)
        label='['+labels[hit.chunk_id]+']' if hit.chunk_id in labels else 'Omitted source '+str(hit.locator.get('filename','selected evidence'))
        if reasons:details.append(label+' '+ '; '.join(reasons))
    if details:
        return 'Critical symbols or visual content are unclear/unknown in the selected source. '+ ' '.join(details)+ ' Supply a clearer image or correct the named entry before calculating. An approval alone cannot resolve it.'
    if selection and selection.coverage.requires_narrowing:
        return 'Please narrow the selected evidence before answering. Some selected readings exceed the 10-item or context budget; no partial matrix or omitted frame was treated as understood. Select a smaller crop or shorter interval.'
    if (selection and selection.coverage.selected_cue_count and
        not any(h.locator.get('mm_artifact_id') for h in selection.hits) and
        re.search(r'\b(board|frame|diagram|shown|visible|picture|visual)\b',plan.question,re.I)):
        return 'Board/visual content is not visible in selected evidence. The supplied transcript alone cannot establish the board content. Supply a readable frame and review its transcription, or ask about the transcript only.'
    return ''
