from datetime import datetime, timedelta
from sqlalchemy import func
from models import db, DownloadLog, Dataset, Keyword

def get_dashboard_summary():
    total_datasets = Dataset.query.count()
    total_downloads = db.session.query(func.sum(Dataset.download_count)).scalar() or 0
    total_keywords = Keyword.query.count()
    total_logs = DownloadLog.query.count()

    # 近7日下载走势
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=6)
    
    logs_by_date = db.session.query(
        func.date(DownloadLog.timestamp).label('date'),
        func.count(DownloadLog.id).label('cnt')
    ).filter(DownloadLog.timestamp >= seven_days_ago).group_by(func.date(DownloadLog.timestamp)).all()

    date_dict = {row.date: row.cnt for row in logs_by_date}
    trend_labels = []
    trend_values = []
    for i in range(7):
        day_str = (seven_days_ago + timedelta(days=i)).strftime('%Y-%m-%d')
        trend_labels.append(day_str)
        trend_values.append(date_dict.get(day_str, 0))

    # 用途分布 (Purpose)
    purposes = db.session.query(
        DownloadLog.purpose,
        func.count(DownloadLog.id)
    ).group_by(DownloadLog.purpose).all()
    purpose_data = [{'name': p or '未标注', 'value': c} for p, c in purposes]

    # 热门数据集 Top 5
    top_datasets = Dataset.query.order_by(Dataset.download_count.desc()).limit(5).all()

    # 最近下载审计日志
    recent_logs = DownloadLog.query.order_by(DownloadLog.timestamp.desc()).limit(15).all()

    return {
        'total_datasets': total_datasets,
        'total_downloads': total_downloads,
        'total_keywords': total_keywords,
        'total_logs': total_logs,
        'trend_labels': trend_labels,
        'trend_values': trend_values,
        'purpose_data': purpose_data,
        'top_datasets': top_datasets,
        'recent_logs': recent_logs
    }
