"""Explicit catalogue confirmation creates a new staged immutable module revision."""
import copy
from .validation import integer, require, shape, validate_mapping

class MappingReviewMixin:
    def mapping_candidates(self,module_id,revision):
        p=self.module(module_id,revision,staged=True)
        catalogue=self.catalogue_loader()
        candidates=[]
        if catalogue.get('available'):
            for course in catalogue.get('courses',[]):
                for topic in course.get('topics',[]):
                    if not topic.get('id'):continue
                    candidates.append({'course_id':course['id'],'course_name':course.get('name',course['id']),
                        'course_code':course.get('code',''),'topic_id':topic['id'],'topic_name':topic['name'],
                        'evidence':'Exact current registered course/topic; semantic fit requires explicit confirmation.'})
        require(len(candidates)<=5000,'Catalogue mapping candidates exceed the review limit.',413)
        return {'module_id':module_id,'revision':revision,'mapping_snapshot':p['mapping'],
            'available':bool(catalogue.get('available')),'candidates':candidates,
            'courses':[{'id':c['id'],'code':c.get('code',''),'name':c.get('name',c['id'])}
                       for c in catalogue.get('courses',[]) if c.get('id')],
            'authority':'catalogue-identities-only','automatic_mapping':False}

    def confirm_mapping(self,module_id,revision,payload):
        shape(payload,{'module_revision','course_id','topic_id','topic_name','confidence','confirmed'})
        require(payload['confirmed'] is True,'Canonical mapping requires explicit confirmation.')
        new_revision=integer(payload['module_revision'],1,1000000)
        require(new_revision>revision,'Mapping review must create a newer immutable module revision.',409)
        mapping={key:payload[key] for key in ('course_id','topic_id','topic_name','confidence')}
        mapping['reviewed']=True
        require(mapping['topic_id'] is not None,'Choose an exact registered topic ID.')
        validate_mapping(mapping,self.catalogue_loader())
        with self.store.connection() as con:
            row,p=self._row(con,module_id,revision,staged=True,include_source=True)
            assets={a['name']:a['bytes'] for a in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?',(module_id,revision))}
            # The original PDF of a portable Learning Studio module is owned
            # by its immutable snapshot, not the separate Knowledge registry.
            portable=p['source']['source_id']=='portable.'+p['source']['sha256']
            source_bytes=row['source_blob'] if portable else None
        derived=copy.deepcopy(p);derived['module_revision']=new_revision;derived['mapping']=mapping
        # Preserve the exact PDF and earlier attempt history. The new revision
        # must still pass catalogue/source validation before it is staged.
        return self.stage(derived,assets,source_bytes=source_bytes)
