# Populate pinyin_key for existing roster entries

from django.db import migrations


def populate_keys(apps, schema_editor):
    PendingRegistration = apps.get_model('memories', 'PendingRegistration')
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        # pypinyin not available, use name as-is
        for p in PendingRegistration.objects.all():
            p.pinyin_key = p.name.lower()
            p.save()
        return
    for p in PendingRegistration.objects.all():
        p.pinyin_key = ''.join(lazy_pinyin(p.name)).lower()
        p.save()


class Migration(migrations.Migration):

    dependencies = [
        ('memories', '0024_alter_pendingregistration_options_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_keys, migrations.RunPython.noop),
    ]
