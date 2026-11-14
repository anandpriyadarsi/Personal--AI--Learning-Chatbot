"""Versioned source and locator contracts. No I/O or provider authority."""
import hashlib
import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceCoverage:
    included: tuple = ()
    excluded: tuple = ()  # (opaque placement/location identity, reason)
    selected_cue_count: int = 0
    selected_frame_count: int = 0
    complete: bool = True
    requires_narrowing: bool = False

    def as_dict(self):
        return dict(included=list(self.included),excluded=[dict(locator_id=i,reason=r) for i,r in self.excluded],
                    selected_cue_count=self.selected_cue_count,selected_frame_count=self.selected_frame_count,
                    complete=self.complete,requires_narrowing=self.requires_narrowing)


@dataclass(frozen=True)
class EvidenceSelection:
    hits: tuple = ()
    coverage: EvidenceCoverage = EvidenceCoverage()
    considered_hits: tuple = ()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def source_ref(doc):
    return dict(owner='native_library',document_id=doc['id'],hash=doc['sha256'],
                generation=doc['generation'],revision=doc['metadata_revision'],course_id=doc.get('subject_id'))


def integer(value,low=0,high=86_400_000):
    if type(value) is not int or not low<=value<=high:raise ValueError('Invalid finite integer range')
    return value


def validate_locator(value):
    if not isinstance(value,dict):raise ValueError('Invalid locator')
    loc=dict(value);kind=loc.get('kind')
    fields={'pdf_page':{'page','bbox'},'pptx_slide':{'slide','asset_id'},
            'image':{'asset_id','bbox'},'transcript_cue':{'cue_id','start_ms','end_ms'},
            'video_frame':{'frame_pts_ms','asset_id','alignment','parent_source_ref','bbox'}}
    if kind not in fields or set(loc)-fields[kind]-{'kind','schema_version'}:raise ValueError('Unknown locator fields')
    if loc.get('schema_version',2)!=2:raise ValueError('Unsupported locator version')
    if kind=='pdf_page':integer(loc.get('page'),1,2500)
    if kind=='pptx_slide':integer(loc.get('slide'),1,2500)
    if kind=='transcript_cue':
        start=integer(loc.get('start_ms'));end=integer(loc.get('end_ms'))
        if end<=start:raise ValueError('Empty or reversed cue')
    if kind=='video_frame':
        integer(loc.get('frame_pts_ms'))
        if not isinstance(loc.get('parent_source_ref',''),str) or len(loc.get('parent_source_ref',''))>64:raise ValueError('Invalid parent source reference')
        if loc.get('alignment')!='user_supplied':raise ValueError('Frame alignment must be explicit')
    if 'bbox' in loc:
        box=loc['bbox']
        if (not isinstance(box,list) or len(box)!=4 or
            any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in box)
            or box[0]>=box[2] or box[1]>=box[3]):raise ValueError('Invalid normalized crop')
    loc['schema_version']=2
    return loc


def location_label(locator):
    kind=locator.get('kind')
    if kind=='pdf_page':label='Page '+str(locator['page'])
    elif kind=='pptx_slide':label='Slide '+str(locator['slide'])
    elif kind=='image':label='Selected image'
    elif kind=='transcript_cue':
        def clock(ms):return f'{ms//60000}:{(ms//1000)%60:02}.{ms%1000:03}'
        label='Cue '+clock(locator['start_ms'])+'–'+clock(locator['end_ms'])
    elif kind=='video_frame':label='Supplied frame at '+str(locator['frame_pts_ms'])+' ms'
    else:return 'Exact historical location unavailable'
    if locator.get('bbox'):label+=' · selected crop'
    return label
