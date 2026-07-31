import os
import threading
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

# 线程局部变量：用于 signal 中获取当前操作用户
_thread_locals = threading.local()

def get_current_user():
    """获取当前请求的用户（在 signal 中使用）"""
    return getattr(_thread_locals, 'user', None)

def set_current_user(user):
    _thread_locals.user = user

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name='用户账号')
    display_name = models.CharField(max_length=50, unique=True, verbose_name='显示名称')
    birthday = models.DateField(null=True, blank=True, verbose_name='生日')
    bio = models.TextField(max_length=500, blank=True, verbose_name='个人简介')
    face_token = models.CharField(max_length=100, blank=True, verbose_name='人脸标识')
    bg_image = models.ImageField(upload_to='user_bg/', blank=True, null=True, verbose_name='个人空间背景')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    global_bg = models.ImageField(upload_to='user_bg/', blank=True, null=True, verbose_name='全站背景')

    class Meta:
        verbose_name = '个人档案'
        verbose_name_plural = '个人档案'

    @property
    def name(self):
        """别名，与 PendingRegistration.name 统一"""
        return self.display_name

    def __str__(self):
        return self.display_name


class InviteCode(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='邀请码')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    max_uses = models.PositiveIntegerField(default=1, verbose_name='最大使用次数')
    used_count = models.PositiveIntegerField(default=0, verbose_name='已使用次数')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')

    class Meta:
        verbose_name = '邀请码'
        verbose_name_plural = '邀请码'

    def is_valid(self):
        if not self.is_active:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def __str__(self):
        return f"邀请码: {self.code} ({self.used_count}/{self.max_uses})"


class PendingRegistration(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='姓名')
    is_taken = models.BooleanField(default=False, verbose_name='是否已注册')
    pinyin_key = models.CharField(max_length=100, blank=True, db_index=True, verbose_name='拼音排序键')

    class Meta:
        verbose_name = '花名册'
        verbose_name_plural = '花名册'
        ordering = ['pinyin_key']

    def save(self, *args, **kwargs):
        try:
            from pypinyin import lazy_pinyin
            self.pinyin_key = ''.join(lazy_pinyin(self.name)).lower()
        except ImportError:
            self.pinyin_key = self.name.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} {'(已注册)' if self.is_taken else '(可用)'}"


class ClassPhoto(models.Model):
    title = models.CharField(max_length=100, verbose_name='标题')
    image = models.ImageField(upload_to='class_photos/', verbose_name='合照图片')
    description = models.TextField(blank=True, verbose_name='描述')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '班级合照'
        verbose_name_plural = '班级合照'
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

class FaceHotzone(models.Model):
    photo = models.ForeignKey(ClassPhoto, on_delete=models.CASCADE, related_name='hotzones', verbose_name='所属合照')
    profile = models.ForeignKey('PendingRegistration', on_delete=models.SET_NULL, related_name='hotzones', null=True, blank=True, verbose_name='关联同学')
    x = models.FloatField(help_text='X 坐标（百分比）', verbose_name='X坐标%')
    y = models.FloatField(help_text='Y 坐标（百分比）', verbose_name='Y坐标%')
    width = models.FloatField(help_text='宽度（百分比）', verbose_name='宽度%')
    height = models.FloatField(help_text='高度（百分比）', verbose_name='高度%')

    class Meta:
        verbose_name = '人脸热区'
        verbose_name_plural = '人脸热区'
        ordering = ['y', 'x']

    def __str__(self):
        name = self.profile.name if self.profile else '未识别'
        return f'{name} @ {self.photo.title}'


@receiver(post_save, sender=ClassPhoto)
def auto_create_hotzones(sender, instance, created, **kwargs):
    if not instance.image:
        return
    # 如果已有手动分配的热区（profile不为空），跳过自动生成，保护手动编辑
    if not created and instance.hotzones.exclude(profile__isnull=True).exists():
        return
    # 清除旧热区（仅当全部为自动生成的未分配热区时才重生成）
    from PIL import Image as PILImage
    import io as sio
    try:
        img = PILImage.open(instance.image.path)
        if img.width > 2560 or img.height > 2560:
            img.thumbnail((2560, 2560), PILImage.LANCZOS)
            out = sio.BytesIO()
            img.save(out, format='JPEG', quality=85)
            with open(instance.image.path, 'wb') as f:
                f.write(out.getvalue())
    except: pass
    from .utils import detect_faces_in_photo
    try:
        faces = detect_faces_in_photo(instance.image.path)
        # 清除旧热区（针对更新时重新生成的情况）
        if not created:
            instance.hotzones.all().delete()
        for face in faces:
            # 覆盖头部+上半身：以人脸为基准向下放大
            # 百度返回的人脸框仅覆盖面部，需大幅扩展
            cx = face['x'] + face['width'] / 2
            cy = face['y'] + face['height'] / 2 + face['height'] * 0.8  # 中心下移，覆盖身体
            w2 = min(face['width'] * 3.0, 28)   # 3倍宽，覆盖肩膀
            h2 = min(face['height'] * 4.0, 40)   # 4倍高，覆盖头到胸部
            FaceHotzone.objects.create(
                photo=instance, profile=None,
                x=max(0, cx - w2 / 2), y=max(0, cy - h2 / 2),
                width=min(w2, 100 - max(0, cx - w2 / 2)),
                height=min(h2, 100 - max(0, cy - h2 / 2))
            )
    except Exception as e:
        print(f"自动生成热区失败: {e}")


# ========== 新增：个人相册与照片 ==========
class Album(models.Model):
    ALBUM_TYPES = [('personal', '个人相册'), ('shared', '共同相册')]
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='albums', verbose_name='所有者')
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='created_albums', null=True, blank=True, verbose_name='创建者')
    name = models.CharField(max_length=100, verbose_name='相册名称')
    description = models.TextField(blank=True, verbose_name='描述')
    is_public = models.BooleanField(default=False, verbose_name='是否公开到公共板块')
    album_type = models.CharField(max_length=10, choices=ALBUM_TYPES, default='personal', verbose_name='相册类型')
    is_deleted = models.BooleanField(default=False, verbose_name='已删除（软删除）')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '相册'
        verbose_name_plural = '相册'

    def __str__(self):
        return f"{self.owner.display_name} - {self.name}"


class Photo(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='photos', null=True, blank=True, verbose_name='所属相册')
    uploaded_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='uploaded_photos', verbose_name='上传者')
    image = models.ImageField(upload_to='user_photos/', blank=True, null=True, verbose_name='图片')
    video = models.FileField(upload_to='user_videos/', blank=True, null=True, verbose_name='视频')
    caption = models.CharField(max_length=200, blank=True, verbose_name='描述')
    VISIBILITY_CHOICES = [('all', '全部人可见'), ('target', '仅对方可见'), ('selected', '部分人可见')]
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='all', verbose_name='可见范围')
    visible_to = models.ManyToManyField('Profile', blank=True, related_name='visible_photos', verbose_name='指定可见的人')
    description = models.TextField(max_length=1000, blank=True, verbose_name='详细描述（可被搜索）')
    message = models.CharField(max_length=500, blank=True, verbose_name='留言')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')
    view_count = models.PositiveIntegerField(default=0, verbose_name='浏览次数')

    class Meta:
        verbose_name = '照片/视频'
        verbose_name_plural = '照片/视频'

    @property
    def media_type(self):
        return 'video' if self.video else 'image'

    @property
    def media_url(self):
        return self.video.url if self.video else self.image.url if self.image else ''

    def __str__(self):
        return f"Photo by {self.uploaded_by.display_name}"


class PhotoFaceMapping(models.Model):
    """记录照片中检测到的人脸与 Profile 的关联"""
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name='face_mappings', verbose_name='照片')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='face_mappings', null=True, blank=True, verbose_name='匹配同学')
    x = models.FloatField(verbose_name='X坐标%')
    y = models.FloatField(verbose_name='Y坐标%')
    width = models.FloatField(verbose_name='宽度%')
    height = models.FloatField(verbose_name='高度%')
    is_auto_matched = models.BooleanField(default=False, verbose_name='是否自动匹配')

    class Meta:
        verbose_name = '照片人脸映射'
        verbose_name_plural = '照片人脸映射'

    def __str__(self):
        name = self.profile.display_name if self.profile else '未知'
        return f"{name} in {self.photo.id}"


# ========== 新增：时间线 ==========
class TimelineEvent(models.Model):
    title = models.CharField(max_length=100, verbose_name='标题')
    description = models.TextField(blank=True, verbose_name='描述')
    event_date = models.DateField(verbose_name='事件日期')
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    is_approved = models.BooleanField(default=True, verbose_name='已审核')  # 当前策略：直接生效

    class Meta:
        verbose_name = '时间线事件'
        verbose_name_plural = '时间线事件'
        ordering = ['-event_date', '-created_at']

    def __str__(self):
        return self.title


class EventPhoto(models.Model):
    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name='photos', verbose_name='所属事件')
    image = models.ImageField(upload_to='event_photos/', blank=True, null=True, verbose_name='图片')
    video = models.FileField(upload_to='event_videos/', blank=True, null=True, verbose_name='视频')
    uploaded_by = models.ForeignKey(Profile, on_delete=models.CASCADE, verbose_name='上传者')
    caption = models.CharField(max_length=200, blank=True, verbose_name='描述')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')

    class Meta:
        verbose_name = '事件照片/视频'
        verbose_name_plural = '事件照片/视频'

    @property
    def media_type(self):
        return 'video' if self.video else 'image'

    @property
    def media_url(self):
        return self.video.url if self.video else self.image.url if self.image else ''

    def __str__(self):
        return f"EventPhoto for {self.event.title}"


# ========== 新增：修正记录 ==========
class CorrectionRequest(models.Model):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name='corrections', verbose_name='目标照片')
    requested_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='corrections', verbose_name='发起人')
    current_assigned_to = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, related_name='pending_corrections', verbose_name='当前归属')
    suggested_profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, related_name='suggested_corrections', verbose_name='建议改为')
    is_resolved = models.BooleanField(default=False, verbose_name='是否已处理')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '修正请求'
        verbose_name_plural = '修正请求'

    def __str__(self):
        return f"修正: {self.photo.id} -> {self.suggested_profile}"
# ========== 照片评论 ==========
class Comment(models.Model):
    photo = models.ForeignKey('Photo', on_delete=models.CASCADE, related_name='comments', verbose_name='照片')
    author = models.ForeignKey('Profile', on_delete=models.CASCADE, verbose_name='评论者')
    content = models.TextField(max_length=500, verbose_name='评论内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='评论时间')

    class Meta:
        verbose_name = '照片评论'
        verbose_name_plural = '照片评论'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author.display_name}: {self.content[:30]}'


# ========== 人脸训练数据 ==========
class FaceTrainingPhoto(models.Model):
    roster = models.ForeignKey('PendingRegistration', on_delete=models.CASCADE, related_name='training_photos', verbose_name='所属同学')
    image = models.ImageField(upload_to='face_training/', verbose_name='训练照片')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')
    is_registered = models.BooleanField(default=False, verbose_name='已注册到百度')

    class Meta:
        verbose_name = '人脸训练库'
        verbose_name_plural = '人脸训练库'

    def __str__(self):
        return f'{self.roster.name} 训练照 #{self.id}'


# ========== 行为日志 ==========
class ActivityLog(models.Model):
    user = models.ForeignKey(Profile, on_delete=models.CASCADE, verbose_name='用户')
    action = models.CharField(max_length=50, verbose_name='操作类型')
    detail = models.CharField(max_length=500, verbose_name='详情')
    related_photo = models.ForeignKey('Photo', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联照片')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='时间')

    class Meta:
        verbose_name = '行为日志'
        verbose_name_plural = '行为日志'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.display_name} {self.action} @ {self.created_at.strftime("%m-%d %H:%M")}'

    def thumbnail_url(self):
        if self.related_photo:
            if self.related_photo.image:
                return self.related_photo.image.url
            if self.related_photo.video:
                return None  # video, no thumbnail
        return None


class SiteSetting(models.Model):
    key = models.CharField(max_length=50, unique=True, verbose_name='设置键名')
    value = models.CharField(max_length=255, blank=True, verbose_name='文本值')
    image = models.ImageField(upload_to='site/', blank=True, null=True, verbose_name='图片值')

    class Meta:
        verbose_name = '站点设置'
        verbose_name_plural = '站点设置'

    def __str__(self):
        return self.key


# ========== 留言板 ==========
class Message(models.Model):
    MSG_TYPES = [('free', '自由留言'), ('feedback', '问题反馈')]
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='messages', verbose_name='留言者')
    msg_type = models.CharField(max_length=10, choices=MSG_TYPES, default='free', verbose_name='留言类型')
    content = models.TextField(max_length=2000, verbose_name='内容')
    image = models.ImageField(upload_to='messages/', blank=True, null=True, verbose_name='附图')
    STATUS_CHOICES = [('open', '待处理'), ('resolved', '已解决')]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', verbose_name='状态')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies', verbose_name='回复目标')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='发布时间')

    class Meta:
        verbose_name = '留言板'
        verbose_name_plural = '留言板'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.get_msg_type_display()}] {self.author.display_name}: {self.content[:40]}'


# ========== 通知系统 ==========
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('correction', '修正请求'),
        ('face_match', '人脸匹配'),
        ('event_photo', '事件新照片'),
        ('public_photo', '公开照片'),
        ('event_created', '新事件'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name='接收者')
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True, verbose_name='发送者')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, verbose_name='通知类型')
    title = models.CharField(max_length=200, verbose_name='标题')
    message = models.TextField(verbose_name='内容')
    related_url = models.CharField(max_length=500, blank=True, verbose_name='关联链接')
    is_read = models.BooleanField(default=False, verbose_name='是否已读')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '通知'
        verbose_name_plural = '通知'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{'已读' if self.is_read else '未读'}] {self.title} -> {self.recipient.username}"


# ========== 全局操作日志信号 ==========
MODEL_VERBOSE = {
    'ClassPhoto': '班级合照', 'FaceHotzone': '人脸热区', 'Album': '相册',
    'Photo': '照片', 'EventPhoto': '事件照片', 'TimelineEvent': '时间线事件',
    'Comment': '评论', 'Message': '留言', 'PendingRegistration': '花名册',
    'FaceTrainingPhoto': '人脸训练', 'CorrectionRequest': '修正请求',
    'Notification': '通知', 'InviteCode': '邀请码', 'Profile': '档案',
    'SiteSetting': '站点设置',
}

def _log_model_action(instance, action, user=None):
    """自动记录模型变更到 ActivityLog"""
    model_name = type(instance).__name__
    label = MODEL_VERBOSE.get(model_name, model_name)
    obj_repr = str(instance)[:100]
    actor = user or get_current_user()
    if not actor:
        return
    ActivityLog.objects.create(
        user=actor,
        action=action,
        detail=f'{action} [{label}] {obj_repr}'
    )


@receiver(post_save)
def auto_log_save(sender, instance, created, **kwargs):
    if sender.__name__ not in MODEL_VERBOSE:
        return
    if sender.__name__ == 'ActivityLog':
        return  # 不记录日志本身
    action = '新增' if created else '修改'
    # 避免在 auto_create_hotzones 信号中为每个热区单独记录
    if sender.__name__ == 'FaceHotzone' and not created:
        return
    _log_model_action(instance, action)


@receiver(post_delete)
def auto_log_delete(sender, instance, **kwargs):
    if sender.__name__ not in MODEL_VERBOSE:
        return
    if sender.__name__ == 'ActivityLog':
        return
    _log_model_action(instance, '删除')