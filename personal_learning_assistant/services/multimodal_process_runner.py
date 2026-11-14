"""Killable selected-scope parser, bounded output and decoded pixels."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def display_crop_to_pdf_clip(page, bbox):
    """Map normalized upright display coordinates to unrotated PDF space.

    Page.rect already accounts for rotation and CropBox. Text extraction uses
    the unrotated page frame, while pixmaps use the displayed frame.
    """
    import fitz
    from personal_learning_assistant.domain.multimodal_models import validate_locator
    box=validate_locator(dict(kind='pdf_page',page=1,bbox=bbox))['bbox']
    r=page.rect
    display=fitz.Rect(r.x0+box[0]*r.width,r.y0+box[1]*r.height,
                      r.x0+box[2]*r.width,r.y0+box[3]*r.height)
    return display * page.derotation_matrix


def inspect_original(path,kind,locator,cancelled=lambda:False,*,timeout=120):
    with tempfile.TemporaryDirectory(prefix='anvaya-mm-') as temp:
        output=Path(temp)/'result.json'
        process=subprocess.Popen([sys.executable,'-m','personal_learning_assistant.services.multimodal_process_runner',
                                  str(path),kind,json.dumps(locator),str(output)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+timeout
        try:
            while process.poll() is None:
                if cancelled() or time.monotonic()>deadline:raise ValueError('Local inspection cancelled or timed out')
                time.sleep(.04)
            if process.returncode or not output.is_file() or output.stat().st_size>12_000_000:raise ValueError('Local inspection unavailable')
            return json.loads(output.read_text())
        finally:
            if process.poll() is None:process.kill()
            process.wait()


def _image_payload(image,loc):
    from PIL import ImageOps
    from io import BytesIO
    import base64
    image=ImageOps.exif_transpose(image).convert('RGB')
    if loc.get('bbox'):
        x0,y0,x1,y1=loc['bbox'];w,h=image.size
        image=image.crop((int(x0*w),int(y0*h),max(int(x1*w),int(x0*w)+1),max(int(y1*h),int(y0*h)+1)))
    image.thumbnail((2048,2048))
    stream=BytesIO();image.save(stream,format='PNG')
    if stream.tell()>8_000_000:raise ValueError('Selected image exceeds provider payload limit')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


def _inspect(path,kind,loc):
    # POSIX gets OS memory/CPU/file bounds; Windows gets process timeout,
    # byte/pixel/page bounds. No shell, child media decoders or remote protocols.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU,(115,115))
        resource.setrlimit(resource.RLIMIT_FSIZE,(12*1024**2,12*1024**2))
    except (ImportError,ValueError):pass
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=20_000_000
    if kind=='pdf':
        import fitz
        with fitz.open(path) as pdf:
            page=loc['page']
            if not 1<=page<=len(pdf):raise ValueError('Page out of range')
            p=pdf[page-1]
            clip=None
            if loc.get('bbox'):
                clip=display_crop_to_pdf_clip(p,loc['bbox'])
            text=p.get_text(clip=clip)[:16000]
            scale=min(2,2048/max(p.rect.width,p.rect.height))
            pix=p.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            return dict(text=text,kind='embedded_text',uncertain=[] if text.strip() else ['Scanned page requires review.'],image=_image_payload(image,loc))
    if kind=='pptx':
        from .native_document_extraction import _slides
        selected=next((t for i,t in _slides(path,lambda:False) if i==loc['slide']),None)
        if selected is None:raise ValueError('Slide out of range')
        return dict(text=selected[:16000],kind='embedded_text',uncertain=[] if selected.strip() else ['Image-only slide; supply an exported slide image.'])
    with Image.open(path) as image:
        if getattr(image,'n_frames',1)!=1 or image.width*image.height>20_000_000:raise ValueError('Static image pixel limit exceeded')
        image.load();image=ImageOps.exif_transpose(image)
        # No fabricated visual interpretation from image headers. User review
        # supplies math until a separately authorized vision adapter is active.
        return dict(text='',kind='visual_observation',uncertain=['Critical symbols have not been transcribed.'],image=_image_payload(image,loc))

if __name__=='__main__':
    path,kind,loc,output=sys.argv[1:]
    Path(output).write_text(json.dumps(_inspect(Path(path),kind,json.loads(loc))))
