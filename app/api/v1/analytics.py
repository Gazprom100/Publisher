from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Optional

from app.db.session import get_db
from app.services.analytics.service import AnalyticsService
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/general")
async def get_general_stats(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get general statistics about posts and channels."""
    analytics = AnalyticsService(db)
    return await analytics.get_general_stats()

@router.get("/activity")
async def get_activity_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get post activity statistics."""
    analytics = AnalyticsService(db)
    return await analytics.get_activity_by_hour(days)

@router.get("/content-types")
async def get_content_types(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get content type distribution."""
    analytics = AnalyticsService(db)
    return await analytics.get_content_types()

@router.get("/channel/{channel_id}/growth")
async def get_channel_growth(
    channel_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get channel growth statistics."""
    analytics = AnalyticsService(db)
    return await analytics.get_channel_growth(channel_id, days)

@router.get("/engagement")
async def get_engagement_metrics(
    post_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get engagement metrics."""
    analytics = AnalyticsService(db)
    return await analytics.get_engagement_metrics(post_id)

@router.get("/optimal-times")
async def get_optimal_posting_times(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get optimal posting times analysis."""
    analytics = AnalyticsService(db)
    return await analytics.get_optimal_posting_times()

@router.get("/content-performance")
async def get_content_performance(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get content performance analysis."""
    analytics = AnalyticsService(db)
    return await analytics.get_content_performance()

@router.get("/dashboard")
async def get_dashboard_data(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
) -> Dict:
    """Get all analytics data for dashboard."""
    analytics = AnalyticsService(db)
    
    return {
        'general': await analytics.get_general_stats(),
        'activity': await analytics.get_activity_by_hour(),
        'content_types': await analytics.get_content_types(),
        'engagement': await analytics.get_engagement_metrics(),
        'optimal_times': await analytics.get_optimal_posting_times(),
        'content_performance': await analytics.get_content_performance()
    } 