from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from memories import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('reset-password/', views.password_reset, name='password_reset'),
    path('logout/', views.user_logout, name='logout'),
    path('space/<str:display_name>/', views.space, name='space'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('album/create/', views.create_album, name='create_album'),
    path('album/<int:album_id>/', views.album_detail, name='album_detail'),
    path('album/<int:album_id>/delete/', views.album_delete, name='album_delete'),
    path('album/<int:album_id>/restore/', views.album_restore, name='album_restore'),
    path('photo/upload/', views.upload_photo, name='upload_photo'),
    path('timeline/', views.timeline, name='timeline'),
    path('timeline/create/', views.create_event, name='create_event'),
    path('timeline/<int:event_id>/', views.event_detail, name='event_detail'),
    path('timeline/<int:event_id>/upload/', views.upload_event_photo, name='upload_event_photo'),
    path('photo/<int:photo_id>/correction/', views.request_correction, name='request_correction'),
    path('profile/edit-bg/', views.edit_bg, name='edit_bg'),
    path('notifications/', views.notification_list, name='notifications'),
    path('notifications/<int:notif_id>/read/', views.notification_read, name='notification_read'),
    path('notifications/read-all/', views.notifications_read_all, name='notifications_read_all'),
    path('space/<str:display_name>/photos-from-others/', views.photos_by_others, name='photos_by_others'),
    path('space/<str:display_name>/photos-from/<str:uploader_name>/', views.photos_by_uploader, name='photos_by_uploader'),
    path('photo/<int:photo_id>/delete/', views.photo_delete, name='photo_delete'),
    path('comment/<int:comment_id>/delete/', views.comment_delete, name='comment_delete'),
    path('photo/<int:photo_id>/', views.photo_detail, name='photo_detail'),
    path('classmates/', views.classmates, name='classmates'),
    path('search/', views.search, name='search'),
    path('shared/', views.shared_albums, name='shared_albums'),
    path('shared/create/', views.shared_album_create, name='shared_album_create'),
    path('shared/<int:album_id>/', views.shared_album_detail, name='shared_album_detail'),
    path('shared/<int:album_id>/upload/', views.shared_album_upload, name='shared_album_upload'),
    path('export/', views.export_photos, name='export_photos'),
    path('auto-upload/', views.auto_upload, name='auto_upload'),
    path('auto-upload/<str:target_name>/', views.auto_upload, name='auto_upload_target'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)