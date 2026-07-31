import base64
import subprocess
import os
import tempfile
from django.conf import settings
from aip import AipFace

def get_face_client():
    return AipFace(settings.BAIDU_APP_ID, settings.BAIDU_API_KEY, settings.BAIDU_SECRET_KEY)


def compress_video(input_path, max_width=640, crf=30):
    """压缩视频：降低分辨率 + 码率，目标让1秒视频只有几百KB。
    如果ffmpeg不可用则返回None（调用方保留原文件）。"""
    try:
        import uuid
        output_path = os.path.join(tempfile.gettempdir(), f'compressed_{uuid.uuid4().hex[:8]}.mp4')
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', f'scale={max_width}:-2',  # 等比缩放，宽不超过max_width
            '-c:v', 'libx264', '-crf', str(crf),  # CRF越大文件越小（23=默认, 30=较小）
            '-preset', 'fast', '-movflags', '+faststart',
            '-c:a', 'aac', '-b:a', '64k',  # 音频降到64kbps
            '-maxrate', '500k', '-bufsize', '1M',  # 限制最大码率
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.getsize(output_path) > 0:
            return output_path
        return None
    except Exception:
        return None


try:
    from pypinyin import lazy_pinyin
    def pinyin_sort_key(name):
        """按拼音首字母排序的 key 函数"""
        py = lazy_pinyin(name)
        return ''.join(py).lower()
except ImportError:
    def pinyin_sort_key(name):
        return name.lower()


def get_sorted_names():
    """获取花名册所有姓名，按拼音排序（数据库Meta.ordering）"""
    from .models import PendingRegistration
    return list(PendingRegistration.objects.values_list('name', flat=True))


def save_video_file(uploaded_file):
    """保存上传的视频文件，尝试压缩。
    返回 (DjangoFile, is_compressed) 元组。"""
    from django.core.files import File as DJFile
    # 先存临时文件
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp4')
    try:
        with os.fdopen(tmp_fd, 'wb') as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
        compressed_path = compress_video(tmp_path)
        if compressed_path and os.path.getsize(compressed_path) < os.path.getsize(tmp_path):
            name = os.path.splitext(uploaded_file.name)[0] + '.mp4'
            return DJFile(open(compressed_path, 'rb'), name=name), True
        else:
            # 压缩失败或没变小，用原文件
            uploaded_file.seek(0)
            return uploaded_file, False
    except:
        uploaded_file.seek(0)
        return uploaded_file, False
    finally:
        # 清理临时文件（compressed_path 在调用方用完后清理）
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass


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


def log_activity(user_profile, action, detail, photo=None):
    """记录用户行为轨迹，可关联照片"""
    from .models import ActivityLog
    return ActivityLog.objects.create(
        user=user_profile, action=action, detail=detail, related_photo=photo
    )


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