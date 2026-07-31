# Fill created_by for existing albums (default to owner)

from django.db import migrations
from django.db.models import F


def fill_created_by(apps, schema_editor):
    Album = apps.get_model('memories', 'Album')
    updated = Album.objects.filter(created_by__isnull=True).update(created_by=F('owner'))
    if updated:
        print(f'  Filled created_by for {updated} albums')


class Migration(migrations.Migration):

    dependencies = [
        ('memories', '0026_album_created_by'),
    ]

    operations = [
        migrations.RunPython(fill_created_by, migrations.RunPython.noop),
    ]
