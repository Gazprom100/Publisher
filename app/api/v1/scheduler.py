from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime

from app.db.session import get_db
from app.services.scheduler.service import SchedulerService
from app.core.auth import get_current_user

router = APIRouter()

@router.post("/posts/{post_id}/schedule")
async def schedule_post(
    post_id: int,
    scheduled_time: datetime,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Schedule a post for publication."""
    scheduler = SchedulerService(db)
    result = await scheduler.schedule_post(post_id, scheduled_time)
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
        
    return result

@router.delete("/posts/{post_id}/schedule")
async def cancel_scheduled_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Cancel a scheduled post."""
    scheduler = SchedulerService(db)
    result = await scheduler.cancel_scheduled_post(post_id)
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
        
    return result

@router.put("/posts/{post_id}/schedule")
async def reschedule_post(
    post_id: int,
    new_time: datetime,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Reschedule a post to a new time."""
    scheduler = SchedulerService(db)
    result = await scheduler.reschedule_post(post_id, new_time)
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
        
    return result

@router.get("/posts/scheduled")
async def get_scheduled_posts(
    channel_id: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> List[Dict]:
    """Get list of scheduled posts."""
    scheduler = SchedulerService(db)
    return await scheduler.get_scheduled_posts(
        channel_id=channel_id,
        from_date=from_date,
        to_date=to_date
    )

@router.get("/channels/{channel_id}/optimal-schedule")
async def get_optimal_schedule(
    channel_id: int,
    posts_per_day: int = 3,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> List[datetime]:
    """Get optimal posting schedule for a channel."""
    scheduler = SchedulerService(db)
    try:
        return await scheduler.get_optimal_schedule(
            channel_id=channel_id,
            posts_per_day=posts_per_day,
            days=days
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/posts/{post_id}/retry")
async def retry_failed_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Retry publishing a failed post."""
    scheduler = SchedulerService(db)
    result = await scheduler.retry_failed_post(post_id)
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
        
    return result 