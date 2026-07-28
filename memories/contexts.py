def notification_count(request):
    """全局注入未读通知数量，供导航栏铃铛使用"""
    if request.user.is_authenticated:
        count = request.user.notifications.filter(is_read=False).count()
        return {'unread_count': count}
    return {'unread_count': 0}
