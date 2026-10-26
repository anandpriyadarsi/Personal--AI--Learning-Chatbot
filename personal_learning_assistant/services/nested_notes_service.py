"""Additive mini-notes over the independent Notes store; no academic migration."""
from copy import deepcopy
from uuid import uuid4
import shutil

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    _serialized_write, _newer_version, AnvayaNotesNotFoundError,
    AnvayaNotesConflictError,
)
from .anvaya_notes_service import AnvayaNotesValidationError, _utc_now, _render_typed_body, _inline_asset_ids, _IMAGE_DIRECTIVE, AnvayaNotesService

ORIGINAL='original-content'

class NestedNotesService:
    def __init__(self, repository):
        self.repository=repository
        self.notes_path=repository.notes_path

    def _sections(self,note):
        sections=deepcopy(note.get('sections',[]))
        if note.get('body'):
            sections.insert(0,{'id':ORIGINAL,'title':'Original Content','body':note['body']})
        return sections

    def list(self,note_id,query=''):
        note=self.repository.get_note(note_id)
        query=str(query or '').casefold()[:300]
        return {'version':note['updated_at'],'sections':[
            {'id':s['id'],'title':s['title'],'preview':s.get('body','')[:90],
             'attachment_count':sum(1 for a in note.get('media',[]) if a.get('section_id','')==s['id'])}
            for s in self._sections(note) if query in (s['title']+' '+s.get('body','')).casefold()]}

    def read(self,note_id,section_id):
        note=self.repository.get_note(note_id)
        section=next((s for s in self._sections(note) if s['id']==section_id),None)
        if section is None: raise AnvayaNotesNotFoundError('Section was not found.')
        html,_=_render_typed_body(AnvayaNotesService(self.repository).renderer,note_id,section.get('body',''),note.get('assets',[]))
        return {**section,'html':str(html),'version':note['updated_at']}

    @_serialized_write
    def change(self,note_id,action,*,expected_updated_at,section_id='',title='',body='',order=None,target_note_id='',target_updated_at=''):
        note=self.repository.get_note(note_id)
        if note['updated_at']!=expected_updated_at: raise AnvayaNotesConflictError('Note changed. Reload before saving; keep your draft.')
        sections=deepcopy(note.get('sections',[]))
        section=next((s for s in self._sections(note) if s['id']==section_id),None)
        if action not in ('add','reorder') and section is None: raise AnvayaNotesNotFoundError('Section was not found.')
        created=''
        created_paths=[]
        if action in ('add','edit','rename'):
            clean=str(title or '').strip()
            if not clean or len(clean)>200: raise AnvayaNotesValidationError('Enter a section title up to 200 characters.')
            if len(str(body))>500000: raise AnvayaNotesValidationError('Section text must be under 500,000 characters.')
            if action=='add':
                if len(sections)>=200: raise AnvayaNotesValidationError('A main note supports up to 200 sections.')
                created=uuid4().hex; sections.append({'id':created,'title':clean,'body':str(body)})
            elif section_id==ORIGINAL:
                if action=='rename': raise AnvayaNotesValidationError('Original Content keeps its legacy title.')
                note['body']=str(body)
            else:
                section['title']=clean
                if action=='edit': section['body']=str(body)
                sections=[section if s['id']==section_id else s for s in sections]
        elif action=='duplicate':
            if len(sections)>=200: raise AnvayaNotesValidationError('A main note supports up to 200 sections.')
            created=uuid4().hex; sections.append({**section,'id':created,'title':(section['title']+' (copy)')[:200]})
            extra,created_paths=self._duplicate_media(note,section_id,created)
            note['media']=list(note.get('media',[]))+extra
            try:
                copied,paths,render_body=self._duplicate_inline(note,section.get('body',''))
                created_paths.extend(paths)
                note['assets']=list(note.get('assets',[]))+copied
                sections[-1]['body']=render_body
            except Exception:
                for path in created_paths: path.unlink(missing_ok=True)
                raise
        elif action=='reorder':
            ids=[s['id'] for s in sections]
            if not isinstance(order,list) or len(order)!=len(ids) or not all(isinstance(i,str) for i in order) or set(order)!=set(ids): raise AnvayaNotesValidationError('Reorder every section exactly once.')
            by_id={s['id']:s for s in sections};sections=[by_id[i] for i in order]
        elif action=='delete':
            if section_id==ORIGINAL: raise AnvayaNotesValidationError('Edit Original Content from Edit note; it cannot be deleted as a section.')
            sections=[s for s in sections if s['id']!=section_id]
            for asset in note.get('media',[]):
                if asset.get('section_id')==section_id: asset['section_id']=''
        elif action=='move':
            if section_id==ORIGINAL or target_note_id==note_id or '[[anvaya-image:' in section.get('body',''):
                raise AnvayaNotesValidationError('This section cannot be moved safely. Copy its text instead.')
            return self._move(note,section,target_note_id,target_updated_at)
        else: raise AnvayaNotesValidationError('Unknown section action.')
        note['sections']=sections
        note['updated_at']=_newer_version(_utc_now(),note['updated_at'])
        try:
            self.repository._save([note if r['id']==note_id else r for r in self.repository.list_notes()])
        except Exception:
            for path in created_paths: path.unlink(missing_ok=True)
            raise
        return {'version':note['updated_at'],'section_id':created or section_id}

    def _duplicate_inline(self,note,body):
        used=_inline_asset_ids(body,note.get('assets',[]))
        uploads=[];identities={}
        for asset_id in used:
            source=self.repository.read_asset(note['id'],asset_id)
            new_id=uuid4().hex;identities[asset_id]=new_id
            suffix='.'+source['stored_name'].rsplit('.',1)[-1]
            uploads.append({'id':new_id,'filename':source['filename'],'suffix':suffix,'bytes':source['bytes'],'mimetype':source['mimetype']})
        stored=self.repository._write_assets(note['id'],uploads)
        def remap(match):
            old=match.group('asset')
            return match.group(0).replace('anvaya-image:'+old,'anvaya-image:'+identities[old],1) if old in identities else match.group(0)
        return stored,[self.repository.assets_root/note['id']/a['stored_name'] for a in stored],_IMAGE_DIRECTIVE.sub(remap,body)

    def _duplicate_media(self,note,section_id,new_id):
        from .notes_media_service import NotesMediaStore
        media=NotesMediaStore(self.repository)
        copied=[];items=[]
        try:
            for asset in note.get('media',[]):
                if asset.get('section_id')!=section_id: continue
                source=media.resolve(note['id'],asset['id'])['path']
                identity=uuid4().hex
                dest=source.with_name(identity+source.suffix)
                copied.append(dest)
                with source.open('rb') as inp,dest.open('xb') as out: shutil.copyfileobj(inp,out,65536)
                items.append({**asset,'id':identity,'stored_name':dest.name,'section_id':new_id})
            return items,copied
        except Exception:
            for path in copied: path.unlink(missing_ok=True)
            raise

    def _move(self,note,section,target_id,target_version):
        from .notes_media_service import NotesMediaStore
        target=self.repository.get_note(target_id)
        if target['updated_at']!=target_version: raise AnvayaNotesConflictError('Destination changed. Refresh before moving.')
        if len(target.get('sections',[]))>=200: raise AnvayaNotesValidationError('Destination already has 200 sections.')
        media=NotesMediaStore(self.repository)
        attached=[a for a in note.get('media',[]) if a.get('section_id')==section['id']]
        copied=[]
        try:
            for a in attached:
                source=media.resolve(note['id'],a['id'])['path']
                dest=media._directory(target_id,create=True)/a['stored_name']
                copied.append(dest)
                with source.open('rb') as inp,dest.open('xb') as out: shutil.copyfileobj(inp,out,65536)
            target['sections']=list(target.get('sections',[]))+[section]
            target['media']=list(target.get('media',[]))+attached
            note['sections']=[s for s in note.get('sections',[]) if s['id']!=section['id']]
            note['media']=[a for a in note.get('media',[]) if a not in attached]
            for n in (note,target): n['updated_at']=_newer_version(_utc_now(),n['updated_at'])
            self.repository._save([note if r['id']==note['id'] else target if r['id']==target_id else r for r in self.repository.list_notes()])
        except Exception:
            for p in copied: p.unlink(missing_ok=True)
            raise
        for a in attached:
            try: media._path(note['id'],a).unlink(missing_ok=True)
            except OSError: pass
        return {'version':note['updated_at'],'section_id':section['id'],'target_note_id':target_id}
