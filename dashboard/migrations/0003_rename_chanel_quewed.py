# Generated for dashboard rename: chanel -> channel, quewed -> queued

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_alter_message_chanel_alter_notification_chanel'),
    ]

    operations = [
        migrations.RenameField(
            model_name='notification',
            old_name='chanel',
            new_name='channel',
        ),
        migrations.RenameField(
            model_name='notification',
            old_name='quewed',
            new_name='queued',
        ),
        migrations.RenameField(
            model_name='message',
            old_name='chanel',
            new_name='channel',
        ),
        migrations.RenameField(
            model_name='message',
            old_name='quewed',
            new_name='queued',
        ),
    ]
