import base64
from django.conf import settings
from aip import AipFace

def get_face_client():
    return AipFace(settings.BAIDU_APP_ID, settings.BAIDU_API_KEY, settings.BAIDU_SECRET_KEY)

def detect_faces_in_photo(image_path):
    """检测照片中的所有人脸，返回百分比坐标列表"""
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    client = get_face_client()
    result = client.detect(image_data, 'BASE64', options={
        'face_field': 'location',
        'max_face_num': 100
    })
    if result['error_code'] != 0:
        raise Exception(f"人脸检测失败: {result['error_msg']}")
    faces = []
    from PIL import Image
    img = Image.open(image_path)
    img_w, img_h = img.size
    for item in result['result']['face_list']:
        loc = item['location']
        left = loc['left']
        top = loc['top']
        width = loc['width']
        height = loc['height']
        faces.append({
            'x': round(left / img_w * 100, 2),
            'y': round(top / img_h * 100, 2),
            'width': round(width / img_w * 100, 2),
            'height': round(height / img_h * 100, 2),
        })
    return faces


def log_activity(user_profile, action, detail):
    """记录用户行为轨迹"""
    from .models import ActivityLog
    return ActivityLog.objects.create(user=user_profile, action=action, detail=detail)


def create_notification(recipient_user, sender_profile, title, message, related_url='', notification_type='photo_upload'):
    """创建站内通知"""
    from .models import Notification
    return Notification.objects.create(
        recipient=recipient_user,
        sender=sender_profile,
        title=title,
        message=message,
        related_url=related_url,
        notification_type=notification_type,
    )