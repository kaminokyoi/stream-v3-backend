import io
import base64
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from users.models import User
from payments.models import Subscription, Order
from products.models import Account
from core.models import Review

def get_base64_chart(fig):
    """Convert matplotlib figure to base64 string"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', transparent=True, dpi=300)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return image_base64

def collect_report_data(period_days=30):
    """
    Collects analytics data for the specified period.
    Returns a dictionary with data and base64 charts.
    """
    now = timezone.now()
    start_date = now - timedelta(days=period_days)
    prev_start_date = start_date - timedelta(days=period_days)

    # 1. Users
    total_users = User.objects.filter(is_superuser=False).count()
    new_users = User.objects.filter(is_superuser=False, date_joined__gte=start_date).count()
    prev_new_users = User.objects.filter(is_superuser=False, date_joined__gte=prev_start_date, date_joined__lt=start_date).count()
    
    user_growth = 0
    if prev_new_users > 0:
        user_growth = ((new_users - prev_new_users) / prev_new_users) * 100

    # 2. Subscriptions
    active_subs = Subscription.objects.filter(status='active').count()
    new_subs = Subscription.objects.filter(order__purchase_date__gte=start_date).count()
    
    # 3. Orders & Conversion
    orders_period = Order.objects.filter(purchase_date__gte=start_date)
    total_orders = orders_period.count()
    completed_orders = orders_period.filter(status='completed').count()
    conversion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0

    # 4. Revenues (approximated from completed orders in period)
    revenue = sum([order.price for order in orders_period.filter(status='completed')])

    # 5. Platforms (completed orders in period)
    platforms_data = orders_period.filter(status='completed').values('platform').annotate(count=Count('id')).order_by('-count')
    platforms_list = list(platforms_data)
    
    # 6. Reviews
    recent_reviews = Review.objects.filter(create_at__gte=start_date).select_related('user').order_by('-create_at')[:10]
    avg_stars_period = 0
    if recent_reviews:
        avg_stars_period = sum([r.stars for r in recent_reviews]) / len(recent_reviews)
    
    all_reviews_avg = 0
    all_reviews = Review.objects.all()
    if all_reviews.exists():
        all_reviews_avg = sum([r.stars for r in all_reviews]) / all_reviews.count()

    # --- Generate Charts ---
    charts = {}
    
    # Chart 1: Platform Distribution (Pie Chart)
    if platforms_list:
        fig1, ax1 = plt.subplots(figsize=(6, 6))
        labels = [p['platform'] for p in platforms_list]
        sizes = [p['count'] for p in platforms_list]
        colors = ['#2A9D8F', '#E9C46A', '#F4A261', '#E76F51', '#264653', '#8AB17D']
        # use colors up to length
        colors = colors * (len(labels) // len(colors) + 1)
        
        ax1.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors, textprops={'color':"w"})
        ax1.axis('equal')
        fig1.patch.set_facecolor('none')
        charts['platforms_pie'] = get_base64_chart(fig1)

    # Chart 2: Order Status Funnel/Bar
    fig2, ax2 = plt.subplots(figsize=(7, 4))
    status_counts = orders_period.values('status').annotate(count=Count('id'))
    status_dict = {item['status']: item['count'] for item in status_counts}
    
    stages = ['pending_payment', 'pending_validation', 'completed', 'failed']
    stage_labels = ['En attente', 'Validation', 'Complété', 'Échoué']
    counts = [status_dict.get(s, 0) for s in stages]
    
    ax2.bar(stage_labels, counts, color=['#F4A261', '#E9C46A', '#2A9D8F', '#E76F51'])
    ax2.set_ylabel('Commandes', color='white')
    ax2.tick_params(colors='white')
    # hide spines
    for spine in ax2.spines.values():
        spine.set_edgecolor('white')
        spine.set_alpha(0.3)
    charts['orders_bar'] = get_base64_chart(fig2)

    return {
        'period_days': period_days,
        'start_date': start_date,
        'end_date': now,
        'total_users': total_users,
        'new_users': new_users,
        'user_growth': user_growth,
        'active_subs': active_subs,
        'new_subs': new_subs,
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'conversion_rate': conversion_rate,
        'revenue': revenue,
        'platforms_list': platforms_list[:5], # top 5
        'recent_reviews': recent_reviews,
        'avg_stars_period': avg_stars_period,
        'all_reviews_avg': all_reviews_avg,
        'charts': charts
    }
