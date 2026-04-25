from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slack', '0007_slacklog_message_blank'),
    ]

    operations = [
        migrations.AddField(
            model_name='slacklog',
            name='blocks',
            field=models.JSONField(blank=True, null=True, verbose_name='Slack Blocks'),
        ),
    ]
