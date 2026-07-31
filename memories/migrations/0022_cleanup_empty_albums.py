# Clean up empty albums

from django.db import migrations


def cleanup_empty_albums(apps, schema_editor):
    Album = apps.get_model('memories', 'Album')
    count = 0
    for album in Album.objects.all():
        if not album.photos.exists():
            album.delete()
            count += 1
    if count:
        print(f'  Cleaned {count} empty albums')


class Migration(migrations.Migration):

    dependencies = [
        ('memories', '0021_activitylog_related_photo'),
    ]

    operations = [
        migrations.RunPython(cleanup_empty_albums, migrations.RunPython.noop),
    ]
