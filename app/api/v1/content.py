from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime
import os

from app.db.session import get_db
from app.services.content.service import ContentService
from app.core.auth import get_current_user
from app.core.config import settings

router = APIRouter()

@router.post("/posts")
async def create_post(
    channel_id: int = Form(...),
    text: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    scheduled_time: Optional[datetime] = Form(None),
    tags: Optional[List[str]] = Form(None),
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Create a new post."""
    content_service = ContentService(db)
    
    # Handle photo upload if provided
    photo_url = None
    if photo:
        # Save photo
        file_path = os.path.join(settings.MEDIA_FOLDER, photo.filename)
        with open(file_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)
            
        # Validate and optimize image
        validation = await content_service.validate_media(file_path)
        if not validation['valid']:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=validation['error'])
            
        # Optimize image
        try:
            optimized_path = await content_service.optimize_image(file_path)
            photo_url = os.path.relpath(optimized_path, settings.MEDIA_FOLDER)
        except Exception as e:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=str(e))
    
    try:
        post = await content_service.create_post(
            channel_id=channel_id,
            text=text,
            photo_url=photo_url,
            scheduled_time=scheduled_time,
            tags=tags
        )
        return post.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    text: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    scheduled_time: Optional[datetime] = Form(None),
    tags: Optional[List[str]] = Form(None),
    status: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Update an existing post."""
    content_service = ContentService(db)
    
    # Handle photo upload if provided
    photo_url = None
    if photo:
        # Save photo
        file_path = os.path.join(settings.MEDIA_FOLDER, photo.filename)
        with open(file_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)
            
        # Validate and optimize image
        validation = await content_service.validate_media(file_path)
        if not validation['valid']:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=validation['error'])
            
        # Optimize image
        try:
            optimized_path = await content_service.optimize_image(file_path)
            photo_url = os.path.relpath(optimized_path, settings.MEDIA_FOLDER)
        except Exception as e:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=str(e))
    
    try:
        post = await content_service.update_post(
            post_id=post_id,
            text=text,
            photo_url=photo_url,
            scheduled_time=scheduled_time,
            tags=tags,
            status=status
        )
        return post.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Delete a post."""
    content_service = ContentService(db)
    if await content_service.delete_post(post_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Post not found")

@router.get("/posts")
async def get_posts(
    channel_id: Optional[int] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> List[Dict]:
    """Get posts with filters."""
    content_service = ContentService(db)
    posts = await content_service.get_posts(
        channel_id=channel_id,
        status=status,
        tag=tag,
        from_date=from_date,
        to_date=to_date
    )
    return [post.dict() for post in posts]

@router.post("/templates")
async def create_template(
    name: str = Form(...),
    template_text: str = Form(...),
    description: Optional[str] = Form(None),
    variables: Optional[List[str]] = Form(None),
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Create a content template."""
    content_service = ContentService(db)
    try:
        template = await content_service.create_template(
            name=name,
            template_text=template_text,
            description=description,
            variables=variables
        )
        return template.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/templates/{template_id}/apply")
async def apply_template(
    template_id: int,
    variables: Dict[str, str],
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Apply variables to a template."""
    content_service = ContentService(db)
    try:
        text = await content_service.apply_template(
            template_id=template_id,
            variables=variables
        )
        return {"text": text}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/analyze")
async def analyze_content(
    text: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Analyze content quality and sentiment."""
    content_service = ContentService(db)
    return {
        'quality': await content_service.analyze_content_quality(text),
        'language': await content_service.detect_language(text),
        'sentiment': await content_service.analyze_sentiment(text)
    }

@router.post("/schedule/{post_id}")
async def schedule_post(
    post_id: int,
    scheduled_time: datetime = Form(...),
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Schedule a post for publication."""
    content_service = ContentService(db)
    try:
        post = await content_service.schedule_post(
            post_id=post_id,
            scheduled_time=scheduled_time
        )
        return post.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) 