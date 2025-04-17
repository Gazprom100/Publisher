from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

from app.db.models.content import Post, Channel, PostAnalytics, ChannelAnalytics
from app.core.config import settings

class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    async def get_general_stats(self) -> Dict:
        """Get general statistics about posts and channels."""
        total_posts = self.db.query(Post).count()
        active_channels = self.db.query(Channel).filter(Channel.is_active == True).count()
        total_reach = self.db.query(func.sum(PostAnalytics.reach)).scalar() or 0
        
        # Posts today
        today = datetime.utcnow().date()
        posts_today = self.db.query(Post).filter(
            func.date(Post.published_time) == today
        ).count()
        
        return {
            "total_posts": total_posts,
            "posts_today": posts_today,
            "active_channels": active_channels,
            "total_reach": total_reach
        }

    async def get_activity_by_hour(self, days: int = 7) -> Dict:
        """Get post activity statistics by hour."""
        start_date = datetime.utcnow() - timedelta(days=days)
        posts = self.db.query(Post).filter(
            Post.published_time >= start_date
        ).all()
        
        # Convert to pandas for easier analysis
        df = pd.DataFrame([{
            'hour': p.published_time.hour,
            'count': 1
        } for p in posts if p.published_time])
        
        hourly_stats = df.groupby('hour')['count'].sum().reindex(
            range(24), fill_value=0
        ).to_dict()
        
        return {
            'hours': list(range(24)),
            'counts': [hourly_stats[h] for h in range(24)]
        }

    async def get_content_types(self) -> Dict:
        """Analyze content types distribution."""
        total = self.db.query(Post).count()
        with_photo = self.db.query(Post).filter(Post.photo_url.isnot(None)).count()
        
        return {
            'with_photo': with_photo,
            'without_photo': total - with_photo
        }

    async def get_channel_growth(self, channel_id: int, days: int = 30) -> Dict:
        """Analyze channel growth over time."""
        start_date = datetime.utcnow() - timedelta(days=days)
        analytics = self.db.query(ChannelAnalytics).filter(
            ChannelAnalytics.channel_id == channel_id,
            ChannelAnalytics.date >= start_date
        ).order_by(ChannelAnalytics.date).all()
        
        dates = []
        members = []
        for a in analytics:
            dates.append(a.date.strftime('%Y-%m-%d'))
            members.append(a.member_count)
            
        # Predict future growth
        if len(members) > 1:
            X = np.array(range(len(members))).reshape(-1, 1)
            y = np.array(members)
            model = LinearRegression()
            model.fit(X, y)
            
            # Predict next 7 days
            future_days = np.array(range(len(members), len(members) + 7)).reshape(-1, 1)
            predictions = model.predict(future_days)
            
            return {
                'dates': dates,
                'members': members,
                'prediction_dates': [
                    (datetime.utcnow() + timedelta(days=i)).strftime('%Y-%m-%d')
                    for i in range(1, 8)
                ],
                'predictions': predictions.tolist()
            }
        
        return {
            'dates': dates,
            'members': members,
            'prediction_dates': [],
            'predictions': []
        }

    async def get_engagement_metrics(self, post_id: Optional[int] = None) -> Dict:
        """Calculate engagement metrics for posts."""
        query = self.db.query(PostAnalytics)
        if post_id:
            query = query.filter(PostAnalytics.post_id == post_id)
            
        analytics = query.all()
        total_views = sum(a.views for a in analytics)
        total_shares = sum(a.shares for a in analytics)
        total_reactions = sum(len(a.reactions or {}) for a in analytics)
        
        if analytics:
            engagement_rate = (total_shares + total_reactions) / total_views * 100 if total_views > 0 else 0
        else:
            engagement_rate = 0
            
        return {
            'total_views': total_views,
            'total_shares': total_shares,
            'total_reactions': total_reactions,
            'engagement_rate': round(engagement_rate, 2)
        }

    async def get_optimal_posting_times(self) -> Dict:
        """Analyze and determine optimal posting times."""
        # Get posts with analytics
        posts = self.db.query(Post, PostAnalytics).join(
            PostAnalytics
        ).filter(
            Post.published_time.isnot(None)
        ).all()
        
        # Convert to pandas for analysis
        df = pd.DataFrame([{
            'hour': p.published_time.hour,
            'day': p.published_time.weekday(),
            'engagement': (a.shares + len(a.reactions or {})) / a.views * 100 if a.views > 0 else 0
        } for p, a in posts if p.published_time])
        
        if df.empty:
            return {
                'best_hours': [],
                'best_days': [],
                'heatmap': [[0] * 24 for _ in range(7)]
            }
            
        # Calculate average engagement by hour and day
        hourly_engagement = df.groupby('hour')['engagement'].mean()
        daily_engagement = df.groupby('day')['engagement'].mean()
        
        # Create heatmap data
        heatmap = df.pivot_table(
            values='engagement',
            index='day',
            columns='hour',
            aggfunc='mean',
            fill_value=0
        ).values.tolist()
        
        return {
            'best_hours': hourly_engagement.nlargest(5).index.tolist(),
            'best_days': daily_engagement.nlargest(3).index.tolist(),
            'heatmap': heatmap
        }

    async def get_content_performance(self) -> Dict:
        """Analyze content performance by type and length."""
        posts = self.db.query(Post, PostAnalytics).join(
            PostAnalytics
        ).all()
        
        performance = {
            'with_photo': {'count': 0, 'avg_engagement': 0},
            'without_photo': {'count': 0, 'avg_engagement': 0},
            'length_performance': {
                'short': {'count': 0, 'avg_engagement': 0},  # < 100 chars
                'medium': {'count': 0, 'avg_engagement': 0}, # 100-500 chars
                'long': {'count': 0, 'avg_engagement': 0}    # > 500 chars
            }
        }
        
        for post, analytics in posts:
            engagement = (analytics.shares + len(analytics.reactions or {})) / analytics.views * 100 if analytics.views > 0 else 0
            
            # Photo analysis
            if post.photo_url:
                performance['with_photo']['count'] += 1
                performance['with_photo']['avg_engagement'] += engagement
            else:
                performance['without_photo']['count'] += 1
                performance['without_photo']['avg_engagement'] += engagement
                
            # Length analysis
            text_length = len(post.text or '')
            if text_length < 100:
                category = 'short'
            elif text_length < 500:
                category = 'medium'
            else:
                category = 'long'
                
            performance['length_performance'][category]['count'] += 1
            performance['length_performance'][category]['avg_engagement'] += engagement
            
        # Calculate averages
        for category in ['with_photo', 'without_photo']:
            if performance[category]['count'] > 0:
                performance[category]['avg_engagement'] /= performance[category]['count']
                
        for category in performance['length_performance']:
            if performance['length_performance'][category]['count'] > 0:
                performance['length_performance'][category]['avg_engagement'] /= performance['length_performance'][category]['count']
                
        return performance 