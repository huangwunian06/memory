import base64
import io
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout
from django.conf import settings
from .models import InviteCode, PendingRegistration, Profile, ClassPhoto, FaceHotzone, Album, Photo, TimelineEvent, EventPhoto, CorrectionRequest, SiteSetting, Notification, Comment
from .utils import get_face_client, log_activity


# ========== 注册 ==========
def register(request):
    # 第一步：验证邀请码
    invite_verified = request.session.get('invite_verified', False)
    invite_code = request.session.get('invite_code', '')

    if not invite_verified:
        if request.method == 'POST' and request.POST.get('step') == 'verify':
            code = request.POST.get('invite_code')
            try:
                code_obj = InviteCode.objects.get(code=code)
                if code_obj.is_valid():
                    request.session['invite_verified'] = True
                    request.session['invite_code'] = code
                    invite_verified = True
                    invite_code = code
                else:
                    messages.error(request, '邀请码已失效或过期')
            except InviteCode.DoesNotExist:
                messages.error(request, '邀请码不存在')
        if not invite_verified:
            return render(request, 'memories/register.html', {'step': 'verify'})

    # 第二步：填写信息
    if request.method == 'POST' and request.POST.get('step') == 'register':
        username = request.POST.get('username')
        password = request.POST.get('password')
        display_name = request.POST.get('display_name')

        try:
            code_obj = InviteCode.objects.get(code=invite_code)
        except InviteCode.DoesNotExist:
            messages.error(request, '邀请码无效')
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, '用户名已被使用')
            return render(request, 'memories/register.html', {'step': 'info', 'available_names': PendingRegistration.objects.filter(is_taken=False)})

        try:
            name_entry = PendingRegistration.objects.get(name=display_name)
            if name_entry.is_taken:
                messages.error(request, '该姓名已被注册')
                return render(request, 'memories/register.html', {'step': 'info', 'available_names': PendingRegistration.objects.filter(is_taken=False)})
        except PendingRegistration.DoesNotExist:
            messages.error(request, '姓名不在班级名单中')
            return render(request, 'memories/register.html', {'step': 'info', 'available_names': PendingRegistration.objects.filter(is_taken=False)})

        user = User.objects.create_user(username=username, password=password)
        profile = Profile.objects.create(user=user, display_name=display_name)
        name_entry.is_taken = True
        name_entry.save()
        code_obj.used_count += 1
        code_obj.save()

        face_photo = request.FILES.get('face_photo')
        if face_photo:
            try:
                from .models import FaceTrainingPhoto
                tp = FaceTrainingPhoto.objects.create(profile=profile, image=face_photo)
                client = get_face_client()
                face_photo.seek(0)
                img_b64 = base64.b64encode(face_photo.read()).decode()
                result = client.addUser(img_b64, 'BASE64', 'class_group', f'user{user.id}')
                err_code = result.get('error_code', -1)
                if err_code == 0:
                    profile.face_token = result['result'].get('face_token', '')
                    profile.save()
                    tp.is_registered = True
                    tp.save()
                    log_activity(profile, '人脸注册成功', '基准照已录入百度人脸库')
                else:
                    log_activity(profile, '人脸注册失败', f'错误码{err_code}: {result.get("error_msg","")}')
                    messages.warning(request, f'人脸注册失败(错误码{err_code})，管理员后续可补传')
            except Exception as e:
                log_activity(profile, '人脸注册异常', str(e))
                messages.warning(request, f'人脸注册异常，管理员后续可补传')
        else:
            messages.warning(request, '未上传基准照，人脸识别功能将无法使用，后续可补传')

        messages.success(request, '注册成功！请登录。')
        log_activity(profile, '注册账号', f'{display_name} 注册了账号')
        return redirect('login')

    available_names = PendingRegistration.objects.filter(is_taken=False)
    return render(request, 'memories/register.html', {'step': 'info', 'available_names': available_names})


# ========== 忘记密码 ==========
def password_reset(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        display_name = request.POST.get('display_name')
        new_password = request.POST.get('new_password')
        try:
            user = User.objects.get(username=username)
            profile = Profile.objects.get(user=user)
            if profile.display_name != display_name:
                messages.error(request, '姓名不匹配，无法验证身份')
                return redirect('password_reset')
            user.set_password(new_password)
            user.save()
            messages.success(request, '密码已重置，请登录')
            log_activity(profile, '重置密码', f'{display_name} 重置了密码')
            return redirect('login')
        except User.DoesNotExist:
            messages.error(request, '用户名不存在')
        except Profile.DoesNotExist:
            messages.error(request, '账号异常，请联系管理员')
    return render(request, 'memories/reset_password.html')


# ========== 登录 / 退出 ==========
def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, '登录成功！')
            return redirect('home')
        else:
            messages.error(request, '用户名或密码错误')
    return render(request, 'memories/login.html')


@login_required
def home(request):
    if not hasattr(request.user, 'profile'):
        Profile.objects.create(user=request.user, display_name=request.user.username)

    photos = ClassPhoto.objects.all().prefetch_related(
        'hotzones__profile'
    )[:5]
    bg_setting = SiteSetting.objects.filter(key='home_bg').first()
    bg_image = bg_setting.image.url if bg_setting and bg_setting.image else None
    # 随机背景：无设置背景时随机选一张照片
    random_bg = None
    if not bg_image:
        rand_photo = Photo.objects.order_by('?').first()
        if rand_photo:
            random_bg = rand_photo.image.url if rand_photo.image else (rand_photo.video.url if rand_photo.video else None)

    # 收集热区中关联的花名册姓名，查找对应的已注册 Profile
    roster_names = set()
    for photo in photos:
        for zone in photo.hotzones.all():
            if zone.profile:
                roster_names.add(zone.profile.name)

    profiles_data = {}
    if roster_names:
        registered = Profile.objects.filter(display_name__in=roster_names)
        registered_map = {p.display_name: p for p in registered}

        for name in roster_names:
            p = registered_map.get(name)
            if p:
                p_albums = p.albums.filter(is_public=True).prefetch_related('photos')
                albums_info = []
                for album in p_albums[:3]:
                    cover = album.photos.first()
                    albums_info.append({
                        'id': album.id, 'name': album.name,
                        'cover': cover.image.url if cover and cover.image else (cover.video.url if cover and cover.video else ''),
                        'count': album.photos.count(),
                    })
                other_qs = Photo.objects.filter(album__owner=p, album__is_public=True).exclude(uploaded_by=p).select_related('uploaded_by')[:6]
                other_previews = [{'url': op.image.url if op.image else (op.video.url if op.video else ''), 'caption': op.caption, 'is_video': bool(op.video), 'uploader': op.uploaded_by.display_name} for op in other_qs]

                profiles_data[name] = {'name': name, 'bio': p.bio, 'registered': True, 'albums': albums_info, 'other_photos': other_previews, 'total_albums': p_albums.count(), 'total_other': other_qs.count()}
            else:
                profiles_data[name] = {'name': name, 'bio': '', 'registered': False, 'albums': [], 'other_photos': [], 'total_albums': 0, 'total_other': 0}

    import json
    return render(request, 'memories/home.html', {
        'display_name': request.user.profile.display_name,
        'photos': photos,
        'bg_image': bg_image,
        'random_bg': random_bg,
        'profiles_json': json.dumps(profiles_data, ensure_ascii=False),
        'current_user_name': request.user.profile.display_name,
    })


def user_logout(request):
    auth_logout(request)
    messages.success(request, '已退出登录')
    return redirect('login')


# ========== 个人空间 ==========
@login_required
def space(request, display_name):
    profile = Profile.objects.filter(display_name=display_name).first()
    roster = PendingRegistration.objects.filter(name=display_name).first()
    is_registered = profile is not None
    is_owner = is_registered and (request.user.profile == profile)

    if is_registered:
        if is_owner:
            albums = profile.albums.filter(album_type='personal')
        else:
            albums = profile.albums.filter(is_public=True, album_type='personal')
        public_photos = Photo.objects.filter(
            album__owner=profile, album__is_public=True
        ).exclude(uploaded_by=profile).select_related('uploaded_by').order_by('-uploaded_at')
        own_photos = Photo.objects.filter(uploaded_by=profile).select_related('album').order_by('-uploaded_at') if is_owner else Photo.objects.none()
    else:
        albums = Album.objects.filter(is_public=True, name__icontains=display_name)
        public_photos = Photo.objects.filter(
            album__in=albums
        ).exclude(uploaded_by__display_name=display_name).select_related('uploaded_by').order_by('-uploaded_at')
        own_photos = Photo.objects.none()
        profile = roster

    return render(request, 'memories/space.html', {
        'profile': profile,
        'albums': albums,
        'own_photos': own_photos,
        'public_photos': public_photos,
        'is_owner': is_owner,
        'is_registered': is_registered,
    })


# ========== 相册管理 ==========
@login_required
def create_album(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        is_public = request.POST.get('is_public') == 'on'
        Album.objects.create(
            owner=request.user.profile,
            name=name,
            description=description,
            is_public=is_public
        )
        messages.success(request, '相册创建成功')
        log_activity(request.user.profile, '创建相册', f'创建了相册「{name}」')
        return redirect('space', display_name=request.user.profile.display_name)
    return render(request, 'memories/create_album.html')


@login_required
def album_detail(request, album_id):
    album = get_object_or_404(Album, id=album_id)
    photos = album.photos.all().order_by('-uploaded_at')
    return render(request, 'memories/album_detail.html', {'album': album, 'photos': photos})


# ========== 照片上传（含人脸检测与匹配） ==========
@login_required
def upload_photo(request):
    VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}
    target_name = request.GET.get('target', '')
    if request.method == 'POST':
        album_id = request.POST.get('album_id')
        caption = request.POST.get('caption', '')
        description = request.POST.get('description', '')
        message = request.POST.get('message', '')
        files = request.FILES.getlist('images') + request.FILES.getlist('videos')
        album = None
        if album_id:
            album = get_object_or_404(Album, id=album_id)
            if album.owner != request.user.profile and not album.is_public:
                messages.error(request, '你没有权限上传到此相册')
                return redirect('upload_photo')
        elif target_name and target_name != request.user.profile.display_name:
            album_name = f'{request.user.profile.display_name}为{target_name}上传的相册'
            target_p = Profile.objects.filter(display_name=target_name).first()
            if target_p:
                album, _ = Album.objects.get_or_create(owner=target_p, name=album_name, defaults={'is_public': True, 'album_type': 'personal'})
            else:
                album = Album.objects.create(owner=request.user.profile, name=album_name, is_public=True, album_type='personal')
        else:
            # 无相册也无target → 自动创建默认相册
            album, _ = Album.objects.get_or_create(owner=request.user.profile, name='我的照片', defaults={'is_public': True, 'album_type': 'personal'})
        img_count = 0
        vid_count = 0
        from PIL import Image as PILImage
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                try:
                    im = PILImage.open(f); im.thumbnail((1920, 1920), PILImage.LANCZOS)
                    out = io.BytesIO(); im.save(out, format='JPEG', quality=85)
                    f.file = out; f.size = out.tell()
                except: pass
            if ext in VIDEO_EXTS:
                Photo.objects.create(
                    album=album, uploaded_by=request.user.profile,
                    video=f, caption=caption, description=description, message=message
                )
                vid_count += 1
            else:
                photo = Photo.objects.create(
                    album=album, uploaded_by=request.user.profile,
                    image=f, caption=caption, description=description, message=message
                )
                img_count += 1
        parts = []
        if img_count: parts.append(f'{img_count} 张照片')
        if vid_count: parts.append(f'{vid_count} 个视频')
        messages.success(request, f'成功上传 {"、".join(parts)}')
        log_activity(request.user.profile, '上传文件', f'上传了 {"、".join(parts)}' + (f' 到「{album.name}」' if album else ''))
        # 通知公开相册所有者
        if album and album.is_public and album.owner.user != request.user:
            from .utils import create_notification
            create_notification(
                recipient_user=album.owner.user,
                sender_profile=request.user.profile,
                title='你的公开相册有新内容',
                message=f'{request.user.profile.display_name} 在你的公开相册 "{album.name}" 中上传了新内容',
                related_url=f'/album/{album.id}/',
                notification_type='public_photo'
            )
        if album:
            return redirect('album_detail', album_id=album.id)
        return redirect('space', display_name=request.user.profile.display_name)
    # 有 target 时：只显示「上传者为该目标创建的相册」
    my_albums = request.user.profile.albums.all()
    target_albums = []
    if target_name and target_name != request.user.profile.display_name:
        uploader_name = request.user.profile.display_name
        target_albums = Album.objects.filter(
            is_public=True, name__icontains=uploader_name
        ).filter(name__icontains=target_name)
    return render(request, 'memories/upload_photo.html', {
        'albums': my_albums,
        'target_name': target_name,
        'target_albums': target_albums,
    })

@login_required
def create_event(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        event_date = request.POST.get('event_date')
        TimelineEvent.objects.create(
            title=title,
            description=description,
            event_date=event_date,
            created_by=request.user.profile
        )
        log_activity(request.user.profile, '创建事件', f'创建了时间线事件「{title}」')
        messages.success(request, '时间线节点创建成功')
        return redirect('timeline')
    return render(request, 'memories/create_event.html')


@login_required
def event_detail(request, event_id):
    event = get_object_or_404(TimelineEvent, id=event_id)
    photos = event.photos.all().order_by('-uploaded_at')
    return render(request, 'memories/event_detail.html', {'event': event, 'photos': photos})


@login_required
def upload_event_photo(request, event_id):
    VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}
    event = get_object_or_404(TimelineEvent, id=event_id)
    if request.method == 'POST':
        files = request.FILES.getlist('images') + request.FILES.getlist('videos')
        caption = request.POST.get('caption', '')
        img_count = 0
        vid_count = 0
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext in VIDEO_EXTS:
                EventPhoto.objects.create(
                    event=event,
                    uploaded_by=request.user.profile,
                    video=f,
                    caption=caption
                )
                vid_count += 1
            else:
                EventPhoto.objects.create(
                    event=event,
                    uploaded_by=request.user.profile,
                    image=f,
                    caption=caption
                )
                img_count += 1
        parts = []
        if img_count: parts.append(f'{img_count} 张照片')
        if vid_count: parts.append(f'{vid_count} 个视频')
        messages.success(request, f'成功上传 {"、".join(parts)} 到活动')
        # 通知事件创建者
        if event.created_by.user != request.user:
            from .utils import create_notification
            create_notification(
                recipient_user=event.created_by.user,
                sender_profile=request.user.profile,
                title='你的活动有新内容',
                message=f'{request.user.profile.display_name} 在活动 "{event.title}" 中上传了新内容',
                related_url=f'/timeline/{event.id}/',
                notification_type='event_photo'
            )
        return redirect('event_detail', event_id=event.id)
    return render(request, 'memories/upload_event_photo.html', {'event': event})


# ========== 修正请求 ==========
@login_required
def request_correction(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id)
    if request.method == 'POST':
        suggested_username = request.POST.get('suggested_username')
        try:
            suggested = Profile.objects.get(display_name=suggested_username)
            CorrectionRequest.objects.create(
                photo=photo,
                requested_by=request.user.profile,
                current_assigned_to=photo.uploaded_by,
                suggested_profile=suggested
            )
            # 通知照片上传者
            from .utils import create_notification
            create_notification(
                recipient_user=photo.uploaded_by.user,
                sender_profile=request.user.profile,
                title='新的修正请求',
                message=f'{request.user.profile.display_name} 建议将照片 #{photo.id} 中的人物归属修正为 {suggested.display_name}',
                related_url='',
                notification_type='correction'
            )
            messages.success(request, '修正请求已提交')
        except Profile.DoesNotExist:
            messages.error(request, '找不到该同学')
        return redirect('space', display_name=request.user.profile.display_name)
    return render(request, 'memories/request_correction.html', {'photo': photo})
@login_required
def edit_profile(request):
    profile = request.user.profile
    if request.method == 'POST':
        profile.bio = request.POST.get('bio', '')
        birthday_str = request.POST.get('birthday')
        profile.birthday = birthday_str if birthday_str else None
        profile.save()
        messages.success(request, '个人信息已更新')
        return redirect('space', display_name=profile.display_name)
    return render(request, 'memories/edit_profile.html', {'profile': profile})
@login_required
def timeline(request):
    events = TimelineEvent.objects.all().order_by('-event_date', '-created_at')
    import json as jmod
    events_json = jmod.dumps([{
        'id': e.id, 'title': e.title, 'description': e.description,
        'event_date': str(e.event_date), 'created_by': e.created_by.display_name
    } for e in events], ensure_ascii=False)
    return render(request, 'memories/timeline.html', {'events': events, 'events_json': events_json})
@login_required
def edit_bg(request):
    profile = request.user.profile
    if request.method == 'POST':
        if request.FILES.get('bg_image'):
            profile.bg_image = request.FILES['bg_image']
        if request.FILES.get('global_bg'):
            profile.global_bg = request.FILES['global_bg']
        profile.save()
        messages.success(request, '背景已更新')
        return redirect('space', display_name=profile.display_name)
    return render(request, 'memories/edit_bg.html', {'profile': profile})


# ========== 通知 ==========
@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:50]
    return render(request, 'memories/notifications.html', {'notifications': notifications})


@login_required
def notification_read(request, notif_id):
    notification = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    if notification.related_url:
        return redirect(notification.related_url)
    return redirect('notifications')


@login_required
def notifications_read_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    messages.success(request, '所有通知已标记为已读')
    return redirect('notifications')


# ========== 他人上传的照片浏览 ==========
@login_required
def photos_by_others(request, display_name):
    """按上传者分组展示他人为TA上传的照片"""
    target = get_object_or_404(Profile, display_name=display_name)
    photos = Photo.objects.filter(
        album__owner=target, album__is_public=True
    ).exclude(uploaded_by=target).select_related('uploaded_by').order_by('-uploaded_at')

    # 按上传者分组
    groups = {}
    for p in photos:
        name = p.uploaded_by.display_name
        if name not in groups:
            groups[name] = []
        groups[name].append(p)

    # 每组取前4张预览
    previews = {}
    for name, items in groups.items():
        previews[name] = {'photos': items[:4], 'total': len(items), 'uploader': items[0].uploaded_by}

    return render(request, 'memories/photos_by_others.html', {
        'target': target,
        'groups': previews,
    })


@login_required
def photos_by_uploader(request, display_name, uploader_name):
    """展示某人为TA上传的全部照片（含大小、时间、留言）"""
    target = get_object_or_404(Profile, display_name=display_name)
    uploader = get_object_or_404(Profile, display_name=uploader_name)
    photos = Photo.objects.filter(
        album__owner=target, album__is_public=True, uploaded_by=uploader
    ).order_by('-uploaded_at')

    # 计算文件大小
    import os
    for p in photos:
        if p.image:
            try:
                size = p.image.size
            except Exception:
                size = 0
            if size >= 1024 * 1024:
                p.file_size = f'{size / (1024*1024):.1f} MB'
            elif size >= 1024:
                p.file_size = f'{size / 1024:.0f} KB'
            else:
                p.file_size = f'{size} B'
        elif p.video:
            try:
                size = p.video.size
            except Exception:
                size = 0
            if size >= 1024 * 1024:
                p.file_size = f'{size / (1024*1024):.1f} MB'
            else:
                p.file_size = f'{size / 1024:.0f} KB'
        else:
            p.file_size = '未知'

    return render(request, 'memories/photos_by_uploader.html', {
        'target': target,
        'uploader': uploader,
        'photos': photos,
    })


# ========== 照片删除 ==========
@login_required
def photo_delete(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id)
    # 只有上传者本人可删；他人为TA上传的照片，接收者不可删
    if photo.uploaded_by != request.user.profile:
        messages.error(request, '你没有权限删除这张照片')
        return redirect('space', display_name=request.user.profile.display_name)
    album_id = photo.album.id if photo.album else None
    photo.image.delete(save=False)
    if photo.video: photo.video.delete(save=False)
    photo.delete()
    log_activity(request.user.profile, '删除文件', f'删除了 1 张照片')
    messages.success(request, '已删除')
    if album_id: return redirect('album_detail', album_id=album_id)
    return redirect('space', display_name=request.user.profile.display_name)


# ========== 照片详情（浏览计数 + 评论） ==========
@login_required
def photo_detail(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id)
    photo.view_count += 1
    photo.save(update_fields=['view_count'])
    comments = photo.comments.all().select_related('author')
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if content:
            from .models import Comment
            Comment.objects.create(photo=photo, author=request.user.profile, content=content)
            log_activity(request.user.profile, '发表评论', f'在照片#{photo.id}下发表评论')
            messages.success(request, '评论已发表')
        return redirect('photo_detail', photo_id=photo.id)
    return render(request, 'memories/photo_detail.html', {'photo': photo, 'comments': comments})


@login_required
def comment_delete(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author != request.user.profile:
        messages.error(request, '只能删除自己的评论')
        return redirect('photo_detail', photo_id=comment.photo.id)
    pid = comment.photo.id
    comment.delete()
    messages.success(request, '评论已删除')
    return redirect('photo_detail', photo_id=pid)


# ========== 搜索 ==========
@login_required
def search(request):
    q = request.GET.get('q', '').strip()
    ctx = {'q': q, 'results_people': [], 'results_photos': [], 'results_events': [], 'results_albums': [], 'results_uploaders': []}
    if q:
        # 人名
        ctx['results_people'] = list(Profile.objects.filter(display_name__icontains=q)[:8])
        registered_names = {p.display_name for p in ctx['results_people']}
        roster_matches = PendingRegistration.objects.filter(name__icontains=q).exclude(name__in=registered_names)[:5]
        for r in roster_matches:
            ctx['results_people'].append(type('V', (), {'display_name': r.name, 'bio': '', 'is_registered': False})())
        # 照片描述
        ctx['results_photos'] = Photo.objects.filter(
            Q(caption__icontains=q) | Q(description__icontains=q) | Q(message__icontains=q)
        ).select_related('uploaded_by', 'album__owner')[:15]
        # 时间线事件
        ctx['results_events'] = TimelineEvent.objects.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )[:10]
        # 相册
        ctx['results_albums'] = Album.objects.filter(name__icontains=q).select_related('owner')[:8]
        # 上传者（搜某人上传的所有照片）
        uploader_profile = Profile.objects.filter(display_name__icontains=q).first()
        if uploader_profile:
            ctx['results_uploaders'] = Photo.objects.filter(uploaded_by=uploader_profile).select_related('album')[:10]
            ctx['uploader_name'] = uploader_profile.display_name
    return render(request, 'memories/search.html', ctx)


# ========== 共同相册 ==========
@login_required
def shared_albums(request):
    albums = Album.objects.filter(album_type='shared').order_by('-created_at')
    return render(request, 'memories/shared_albums.html', {'albums': albums})

@login_required
def shared_album_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        Album.objects.create(owner=request.user.profile, name=name, description=description, album_type='shared', is_public=True)
        log_activity(request.user.profile, '创建共同相册', f'创建了共同相册「{name}」')
        messages.success(request, f'共同相册「{name}」已创建')
        return redirect('shared_albums')
    return render(request, 'memories/shared_album_create.html')

@login_required
def shared_album_detail(request, album_id):
    album = get_object_or_404(Album, id=album_id, album_type='shared')
    photos = album.photos.all().order_by('-uploaded_at')
    return render(request, 'memories/shared_album_detail.html', {'album': album, 'photos': photos})

@login_required
def shared_album_upload(request, album_id):
    album = get_object_or_404(Album, id=album_id, album_type='shared')
    if request.method == 'POST':
        files = request.FILES.getlist('images') + request.FILES.getlist('videos')
        caption = request.POST.get('caption', '')
        VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.webm', '.mkv'}
        count = 0
        from PIL import Image as PILImage
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                try:
                    im = PILImage.open(f); im.thumbnail((1920, 1920), PILImage.LANCZOS)
                    out = io.BytesIO(); im.save(out, format='JPEG', quality=85)
                    f.file = out; f.size = out.tell()
                except: pass
            Photo.objects.create(album=album, uploaded_by=request.user.profile,
                image=f if ext not in VIDEO_EXTS else None,
                video=f if ext in VIDEO_EXTS else None, caption=caption)
            count += 1
        messages.success(request, f'已上传 {count} 张到「{album.name}」')
        return redirect('shared_album_detail', album_id=album.id)
    return render(request, 'memories/shared_album_upload.html', {'album': album})


# ========== 导出（管理员） ==========
@login_required
def export_photos(request):
    if not request.user.is_staff:
        messages.error(request, '仅管理员可导出')
        return redirect('home')
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 收集要导出的照片
        photo_ids = request.GET.get('ids', '')
        album_id = request.GET.get('album_id', '')
        from_user = request.GET.get('from_user', '')
        to_user = request.GET.get('to_user', '')
        photos = Photo.objects.all()
        if photo_ids:
            photos = photos.filter(id__in=[int(x) for x in photo_ids.split(',') if x.strip().isdigit()])
        elif album_id and album_id.isdigit():
            photos = photos.filter(album_id=int(album_id))
        elif from_user and to_user:
            photos = photos.filter(uploaded_by__display_name=from_user, album__owner__display_name=to_user, album__is_public=True)
        else:
            photos = photos[:100]
        for p in photos:
            fname = f'{p.uploaded_by.display_name}/{p.uploaded_at.strftime("%Y%m%d_%H%M")}_{p.id}'
            if p.image and p.image.path:
                try:
                    zf.write(p.image.path, fname + os.path.splitext(p.image.path)[1])
                except: pass
            if p.video and p.video.path:
                try:
                    zf.write(p.video.path, fname + os.path.splitext(p.video.path)[1])
                except: pass
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="class_memories_export.zip"'
    return response


# ========== 自动上传（首页入口，人脸检测自动分流到各人相册） ==========
@login_required
def auto_upload(request, target_name=None):
    target = Profile.objects.filter(display_name=target_name).first() if target_name else None
    if request.method == 'POST':
        action = request.POST.get('action', 'upload')
        uploader = request.user.profile

        # 手动分配归属
        if action == 'assign':
            photo_id = request.POST.get('photo_id')
            assign_to = request.POST.get('assign_to')
            photo = get_object_or_404(Photo, id=photo_id, uploaded_by=uploader, album__isnull=True)
            album_name = f'{uploader.display_name}为{assign_to}自动上传的相册'
            t = Profile.objects.filter(display_name=assign_to).first()
            if not t:
                t = uploader
            album, _ = Album.objects.get_or_create(owner=t, name=album_name, defaults={'is_public': True, 'album_type': 'personal'})
            photo.album = album
            photo.save()
            log_activity(uploader, '手动分配归属', f'{photo.id} 分配给 {assign_to}')
            messages.success(request, f'已分配到 {assign_to}')
            return redirect('auto_upload')

        # 上传流程
        files = request.FILES.getlist('images')
        caption = request.POST.get('caption', '')
        message = request.POST.get('message', '')
        from PIL import Image as PILImage
        results = []
        for f in files:
            try:
                ext = os.path.splitext(f.name)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    try:
                        img = PILImage.open(f); img.thumbnail((1920, 1920), PILImage.LANCZOS)
                        out = io.BytesIO(); img.save(out, format='JPEG', quality=85)
                        from django.core.files.base import ContentFile
                        f = ContentFile(out.getvalue(), name=f.name)
                    except: pass
                is_video = ext in {'.mp4', '.mov', '.avi', '.webm', '.mkv'}
                targets = [target] if target else []
                search_log = ''
                if not targets and not is_video:
                    try:
                        f.seek(0)
                        client = get_face_client()
                        img_b64 = base64.b64encode(f.read()).decode(); f.seek(0)
                        sr = client.search(img_b64, 'BASE64', 'class_group', options={'max_user_num': 3})
                        if sr['error_code'] == 0:
                            for u in sr['result'].get('user_list', []):
                                uid_num = u['user_id'].replace('user', '')
                                p = Profile.objects.filter(user__id=uid_num).first() if uid_num.isdigit() else None
                                if p and p not in targets: targets.append(p)
                            if not targets:
                                search_log = '百度搜索成功但无匹配'
                        else:
                            search_log = '搜索失败:' + str(sr.get('error_code', ''))
                    except Exception as e:
                        search_log = f'搜索异常:{str(e)[:100]}'
                    finally:
                        try: f.seek(0)
                        except: pass

                if targets:
                    for t in targets:
                        f.seek(0)
                        album_name = f'{uploader.display_name}为{t.display_name}自动上传的相册'
                        album, _ = Album.objects.get_or_create(owner=t, name=album_name, defaults={'is_public': True, 'album_type': 'personal'})
                        photo = Photo.objects.create(album=album, uploaded_by=uploader,
                            image=f if not is_video else None, video=f if is_video else None,
                            caption=caption, message=message)
                        if t.user and t != uploader:
                            from .utils import create_notification
                            create_notification(recipient_user=t.user, sender_profile=uploader,
                                title='有人为你自动上传了照片', message=f'{uploader.display_name} 为你上传了照片到「{album_name}」',
                                related_url=f'/album/{album.id}/', notification_type='public_photo')
                    log_activity(uploader, '自动上传匹配', f'{f.name}/{",".join([t.display_name for t in targets])}')
                    results.append({'file': f.name, 'targets': [t.display_name for t in targets], 'is_video': is_video, 'photo_id': photo.id, 'pending': False})
                else:
                    photo = Photo.objects.create(album=None, uploaded_by=uploader,
                        image=f if not is_video else None, video=f if is_video else None,
                        caption=caption, message=message)
                    detail = f'{f.name}:{search_log}' if search_log else f'{f.name}:未检测到人脸'
                    log_activity(uploader, '自动上传未匹配', detail)
                    results.append({'file': f.name, 'targets': [], 'is_video': is_video, 'photo_id': photo.id, 'pending': True})
            except Exception as e:
                log_activity(uploader, '自动上传异常', f'{f.name}:{str(e)[:200]}')
                results.append({'file': f.name, 'targets': [], 'is_video': False, 'photo_id': None, 'pending': True})

        from memories.models import PendingRegistration
        all_names = list(PendingRegistration.objects.all().order_by('name').values_list('name', flat=True))
        return render(request, 'memories/auto_upload_confirm.html', {
            'results': results, 'uploader_name': uploader.display_name, 'all_names': all_names
        })

    # GET: 显示上传页，同时显示待处理照片
    pending = Photo.objects.filter(uploaded_by=request.user.profile, album__isnull=True).order_by('-uploaded_at')
    from memories.models import PendingRegistration
    all_names = list(PendingRegistration.objects.all().order_by('name').values_list('name', flat=True))
    return render(request, 'memories/auto_upload.html', {'target': target, 'pending': pending, 'all_names': all_names})