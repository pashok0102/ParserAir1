from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_searchhistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchhistory',
            name='saved_to',
            field=models.CharField(blank=True, max_length=512),
        ),
    ]
