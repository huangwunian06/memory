from django.contrib import admin
from django.db.models.functions import Round
from django.template.response import TemplateResponse
from .models import Profile, InviteCode, PendingRegistration, ClassPhoto, FaceHotzone, Album, Photo, PhotoFaceMapping, TimelineEvent, EventPhoto, CorrectionRequest, SiteSetting, Notification, ActivityLog, Comment, FaceTrainingPhoto

# 重写 admin 首页加磁盘用量
_original_index = admin.site.index
def index_with_storage(request, extra_context=None):
    if extra_context is None:
        extra_context = {}
    try:
        import os, shutil
        from django.conf import settings
        media_path = settings.MEDIA_ROOT if settings.MEDIA_ROOT else os.path.join(settings.BASE_DIR, 'media')
        if os.path.exists(media_path):
            usage = shutil.disk_usage(media_path)
            total = usage.total
            used = usage.used
            extra_context['storage_pct'] = used / total * 100
            extra_context['storage_mb'] = used / (1024**2)
        extra_context['photo_count'] = Photo.objects.count()
    except:
        extra_context['storage_pct'] = 0
        extra_context['storage_mb'] = 0
        extra_context['photo_count'] = 0
    return _original_index(request, extra_context=extra_context)
admin.site.index = index_with_storage


# ========== 个人档案 ==========
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'face_status', 'created_at')
    search_fields = ('display_name', 'user__username')
    readonly_fields = ('face_token',)

    @admin.display(description='人脸数据')
    def face_status(self, obj):
        if obj.face_token:
            return '✅ 已注册'
        return '⬜ 未注册'


# ========== 邀请码 ==========
@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    """
    邀请码管理 —— 生成和管理注册邀请码。
    注册时用户必须输入有效邀请码，且姓名必须在花名册中。
    创建邀请码后，将 code 分发给同学即可注册。
    """
    list_display = ('code', 'is_active', 'used_count', 'max_uses', 'created_at', 'expires_at')
    list_editable = ('is_active', 'max_uses')
    list_filter = ('is_active',)
    search_fields = ('code',)
    fieldsets = (
        ('邀请码设置', {
            'fields': ('code', 'is_active', 'max_uses'),
            'description': 'code=邀请码字符串（如 Class2024）；is_active=是否启用；max_uses=该码最多可被几人使用'
        }),
        ('使用情况（只读）', {'fields': ('used_count', 'created_at', 'expires_at')}),
    )
    readonly_fields = ('used_count', 'created_at')


# ========== 花名册 ==========
@admin.register(PendingRegistration)
class PendingRegistrationAdmin(admin.ModelAdmin):
    """
    花名册管理 —— 班级所有同学的姓名名单。
    注册时用户必须从此列表中选择自己的姓名。is_taken 标记该姓名是否已被注册。
    """
    list_display = ('name', 'is_taken')
    list_editable = ('is_taken',)
    list_filter = ('is_taken',)
    search_fields = ('name',)
    fieldsets = (
        ('花名册条目', {
            'fields': ('name', 'is_taken'),
            'description': 'name=同学姓名；is_taken=勾选后该姓名将不可被新用户注册'
        }),
    )


# ========== 班级合照（含人脸热区内联） ==========
from django import forms

class FaceHotzoneForm(forms.ModelForm):
    class Meta:
        model = FaceHotzone
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 获取当前合照中已被其他热区选用的人名
        photo = self.instance.photo_id
        used_names = set()
        if photo:
            used_names = set(
                FaceHotzone.objects.filter(photo_id=photo)
                .exclude(profile__isnull=True)
                .values_list('profile__name', flat=True)
            )
        # 如果是编辑已有热区，从"已选"中排除自身（避免把自己也算进去）
        if self.instance.pk and self.instance.profile:
            used_names.discard(self.instance.profile.name)

        # 构建分组选项
        all_names = PendingRegistration.objects.all().order_by('name')
        chosen_opts = []
        unchosen_opts = []
        for p in all_names:
            label = f'{p.name}  ✅已选' if p.name in used_names else f'{p.name}  ⬜未选'
            option = (p.pk, label)
            if p.name in used_names:
                chosen_opts.append(option)
            else:
                unchosen_opts.append(option)

        # 设置 optgroup
        choices = []
        if unchosen_opts:
            choices.append(('── ⬜ 尚未被选用 ──', unchosen_opts))
        if chosen_opts:
            choices.append(('── ✅ 已被其他热区选用 ──', chosen_opts))

        self.fields['profile'].widget.choices = [('', '---------')] + choices
        self.fields['profile'].label = '关联同学'


class FaceHotzoneInline(admin.TabularInline):
    model = FaceHotzone
    form = FaceHotzoneForm
    extra = 1
    fields = ('profile', 'x', 'y', 'width', 'height')
    verbose_name = '人脸热区'
    verbose_name_plural = '👇 人脸热区列表（按从上到下、从左到右排列，底部有空行可手动添加）'
    can_delete = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(y_int=Round('y')).order_by('y_int', 'x')


@admin.register(ClassPhoto)
class ClassPhotoAdmin(admin.ModelAdmin):
    """
    班级合照管理 —— 首页展示的班级大合照。
    ★ 上传/保存照片时会自动调用百度人脸检测，生成人脸热区。
    ★ 百度API免费版最多检测约45人。如合照人数超过此数，请在下方热区列表中手动添加。
    ★ 手动添加方法：拉到热区列表最底部，在空白行填入 x/y/宽度/高度（百分比值），保存即可。
    ★ 将热区的"关联同学"字段选择对应的人，首页点击即可跳转个人空间。
    ★ 拖动 order 数字可调整首页展示顺序（数字越小越靠前）。
    """
    list_display = ('title', 'order', 'hotzone_count', 'created_at')
    list_editable = ('order',)
    inlines = [FaceHotzoneInline]
    fieldsets = (
        ('合照信息', {
            'fields': ('title', 'image', 'description', 'order'),
            'description': '★ 上传或重新保存图片时会自动调用百度人脸检测生成热区（约45人上限）。★ 手动添加热区：在下方的热区列表中，底部空白行填入坐标即可。x=水平位置%(左起), y=垂直位置%(顶起), 宽度%, 高度%。例如人脸在图片正中：x=40, y=30, width=20, height=25。'
        }),
    )

    @admin.display(description='热区数量')
    def hotzone_count(self, obj):
        return obj.hotzones.count()

    class Media:
        js = ('memories/admin_hotzone.js',)


# ========== 人脸热区 ==========
@admin.register(FaceHotzone)
class FaceHotzoneAdmin(admin.ModelAdmin):
    """
    人脸热区管理 —— 班级合照中每个被检测到的人脸区域。
    每行代表合照中的一个人脸框，可手动将 profile 关联到具体同学。
    ★ 关联后，首页点击该热区可跳转到该同学的个人空间。
    """
    list_display = ('photo', 'profile', 'x', 'y', 'width', 'height')
    list_filter = ('photo',)
    search_fields = ('profile__display_name', 'photo__title')
    autocomplete_fields = ('profile',)


# ========== 相册 ==========
@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    """
    相册管理 —— 用户创建的个人相册或共同相册。
    """
    list_display = ('name', 'owner', 'album_type', 'is_public', 'photo_count', 'created_at')
    list_filter = ('album_type', 'is_public')
    search_fields = ('name', 'owner__display_name')
    fieldsets = (
        ('相册信息', {
            'fields': ('owner', 'name', 'description', 'is_public'),
            'description': 'is_public=勾选后该相册的照片会出现在个人空间的"公共分享板"中，其他同学可见'
        }),
    )

    @admin.display(description='照片数量')
    def photo_count(self, obj):
        return obj.photos.count()


# ========== 照片/视频 ==========
@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    """
    照片/视频管理 —— 用户上传的所有媒体文件。
    包含相册照片、视频，以及人脸检测匹配结果。
    ★ 每张照片上传时会自动调用百度人脸检测 + 搜索匹配。
    """
    list_display = ('id', 'media_type', 'uploaded_by', 'album', 'uploaded_at')
    list_filter = ('uploaded_by', 'album')
    search_fields = ('caption', 'uploaded_by__display_name')
    fieldsets = (
        ('媒体信息', {
            'fields': ('uploaded_by', 'album', 'caption'),
            'description': '上传者、所属相册、描述文字'
        }),
        ('文件', {
            'fields': ('image', 'video'),
            'description': 'image=图片文件；video=视频文件。每条记录二选一，不会同时存在。'
        }),
    )

    @admin.display(description='类型')
    def media_type(self, obj):
        return '🎬 视频' if obj.video else '🖼️ 图片'


# ========== 照片人脸映射 ==========
@admin.register(PhotoFaceMapping)
class PhotoFaceMappingAdmin(admin.ModelAdmin):
    """
    照片人脸映射 —— 用户上传照片中被检测到的人脸。
    每行代表照片中的一个人脸框。is_auto_matched 表示是否由百度AI自动匹配成功。
    ★ 未匹配的可以手动关联 profile，帮助修正识别结果。
    """
    list_display = ('photo', 'profile', 'is_auto_matched', 'x', 'y', 'width', 'height')
    list_filter = ('is_auto_matched',)
    search_fields = ('profile__display_name',)


# ========== 时间线事件 ==========
@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    """
    时间线事件管理 —— 全班可见的班级大事件。
    任何人可以创建事件并上传照片/视频。按 event_date 倒序展示在时间线页面。
    """
    list_display = ('title', 'event_date', 'created_by', 'is_approved', 'created_at')
    list_filter = ('is_approved',)
    search_fields = ('title', 'description', 'created_by__display_name')
    fieldsets = (
        ('事件信息', {
            'fields': ('title', 'description', 'event_date', 'created_by'),
            'description': '事件标题、描述、发生日期、创建者'
        }),
        ('审核状态', {
            'fields': ('is_approved',),
            'description': '当前策略为直接生效（默认勾选）。取消勾选则隐藏该事件。'
        }),
    )


# ========== 事件照片/视频 ==========
@admin.register(EventPhoto)
class EventPhotoAdmin(admin.ModelAdmin):
    """
    事件照片/视频管理 —— 时间线事件中上传的媒体文件。
    支持图片和视频两种格式。
    """
    list_display = ('id', 'media_type', 'event', 'uploaded_by', 'uploaded_at')
    list_filter = ('event', 'uploaded_by')
    fieldsets = (
        ('媒体信息', {
            'fields': ('event', 'uploaded_by', 'caption'),
            'description': '所属事件、上传者、描述'
        }),
        ('文件', {
            'fields': ('image', 'video'),
            'description': 'image=图片文件；video=视频文件。每条记录二选一。'
        }),
    )

    @admin.display(description='类型')
    def media_type(self, obj):
        return '🎬 视频' if obj.video else '🖼️ 图片'


# ========== 修正请求 ==========
@admin.register(CorrectionRequest)
class CorrectionRequestAdmin(admin.ModelAdmin):
    """
    修正请求管理 —— 用户提交的人脸识别修正。
    ★ 审核后可一键确认并自动更新人脸映射。
    """
    list_display = ('photo', 'requested_by', 'current_assigned_to', 'suggested_profile', 'is_resolved', 'created_at')
    list_filter = ('is_resolved',)
    search_fields = ('requested_by__display_name', 'suggested_profile__display_name')
    actions = ['approve_corrections']
    fieldsets = (
        ('修正请求详情', {
            'fields': ('photo', 'requested_by', 'current_assigned_to', 'suggested_profile', 'is_resolved'),
        }),
    )

    @admin.action(description='✅ 确认修正并更新人脸映射')
    def approve_corrections(self, request, queryset):
        for cr in queryset.filter(is_resolved=False):
            cr.is_resolved = True
            cr.save()
            # 更新对应的人脸映射
            from .models import PhotoFaceMapping
            PhotoFaceMapping.objects.filter(photo=cr.photo, profile=cr.current_assigned_to).update(profile=cr.suggested_profile)
        self.message_user(request, f'已处理 {queryset.count()} 条修正请求')


# ========== 站点设置 ==========
@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    """
    站点设置 —— 全站级别的配置项。
    当前用于设置首页背景图：key 填入 home_bg，上传背景图片即可。
    ★ 首页会自动读取 key=home_bg 的记录作为背景图。
    """
    list_display = ('key', 'value', 'image')
    search_fields = ('key', 'value')
    fieldsets = (
        ('设置项', {
            'fields': ('key', 'value', 'image'),
            'description': 'key=设置项名称（如 home_bg 为首页背景）；value=文本值（可选）；image=图片值（可选）'
        }),
    )


# ========== 通知 ==========
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    通知管理 —— 系统自动生成的站内通知记录。
    当有人提交修正请求、上传公开照片、人脸匹配成功等事件发生时自动创建。
    用户导航栏铃铛可查看未读通知。此处可查看全部通知历史。
    """
    list_display = ('title', 'recipient', 'sender', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'message', 'recipient__username')
    fieldsets = (
        ('通知内容', {
            'fields': ('recipient', 'sender', 'notification_type', 'title', 'message', 'related_url'),
            'description': 'recipient=接收者；sender=触发者；related_url=点击"查看"后跳转的链接'
        }),
        ('状态', {'fields': ('is_read',)}),
    )
    readonly_fields = ('created_at',)


# ========== 共同相册管理 ==========
@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('photo', 'author', 'content_preview', 'created_at')
    search_fields = ('author__display_name', 'content')

    @admin.display(description='内容')
    def content_preview(self, obj):
        return obj.content[:50]


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'detail', 'created_at')
    list_filter = ('action',)
    search_fields = ('user__display_name', 'detail')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('日志详情', {'fields': ('user', 'action', 'detail', 'created_at')}),
    )
    readonly_fields = ('user', 'action', 'detail', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(FaceTrainingPhoto)
class FaceTrainingPhotoAdmin(admin.ModelAdmin):
    """
    人脸训练库 —— 管理每位同学的人脸识别训练数据。
    上传照片后自动注册到百度人脸库 class_group。
    """
    list_display = ('profile', 'image_preview', 'is_registered', 'uploaded_at')
    list_filter = ('is_registered', 'profile')
    search_fields = ('profile__display_name',)

    @admin.display(description='预览')
    def image_preview(self, obj):
        if obj.image:
            return f'📷 {obj.image.name.split("/")[-1]}'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.image and obj.profile.user:
            from .utils import get_face_client, log_activity
            import base64
            try:
                client = get_face_client()
                with open(obj.image.path, 'rb') as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                result = client.addUser(img_b64, 'BASE64', 'class_group', f'user{obj.profile.user.id}')
                err_code = result.get('error_code', -1)
                err_msg = result.get('error_msg', '未知')
                if err_code == 0:
                    obj.is_registered = True
                    obj.profile.face_token = result['result'].get('face_token', obj.profile.face_token or '')
                    obj.profile.save()
                    obj.save()
                    self.message_user(request, f'✅ {obj.profile.display_name} 人脸注册成功！', level='success')
                    log_activity(obj.profile, '人脸注册', f'训练照注册成功')
                else:
                    self.message_user(request, f'❌ 人脸注册失败: [{err_code}] {err_msg}', level='error')
                    log_activity(obj.profile, '人脸注册失败', f'错误码{err_code}: {err_msg}')
            except Exception as e:
                self.message_user(request, f'❌ 异常: {str(e)}', level='error')
                log_activity(obj.profile, '人脸注册异常', str(e))