# Remove specific roster names

from django.db import migrations


def remove_roster_names(apps, schema_editor):
    PendingRegistration = apps.get_model('memories', 'PendingRegistration')
    names = ['丁朵', '杨凤科', '胡红伟', '刘兴旺', '杨庆科', '许土一', '贠涛']
    for name in names:
        PendingRegistration.objects.filter(name=name).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('memories', '0019_add_roster_batch2'),
    ]

    operations = [
        migrations.RunPython(remove_roster_names, migrations.RunPython.noop),
    ]
