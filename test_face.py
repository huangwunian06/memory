import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'highschool_memories.settings')
django.setup()

from memories.utils import detect_faces_in_photo
from memories.models import ClassPhoto

photo = ClassPhoto.objects.first()
if not photo or not photo.image:
    print("还没有上传合照。请先在后台上传一张 ClassPhoto 再运行此脚本。")
else:
    path = photo.image.path
    print(f"正在检测: {path}")
    try:
        faces = detect_faces_in_photo(path)
        print(f"检测到 {len(faces)} 张人脸，坐标如下：")
        for i, f in enumerate(faces):
            print(f"  人脸{i+1}: x={f['x']}, y={f['y']}, w={f['width']}, h={f['height']}")
    except Exception as e:
        print(f"检测失败: {e}")