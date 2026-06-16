from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SearchHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('route', models.CharField(max_length=255)),
                ('anywhere', models.BooleanField(default=False)),
                ('date', models.CharField(blank=True, max_length=32)),
                ('return_date', models.CharField(blank=True, max_length=32)),
                ('price_from', models.IntegerField(blank=True, null=True)),
                ('price_to', models.IntegerField(blank=True, null=True)),
                ('airline_code', models.CharField(blank=True, max_length=32)),
                ('source', models.CharField(max_length=50)),
                ('result_count', models.PositiveIntegerField(default=0)),
                ('server_time', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='search_history', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'search_history',
                'ordering': ['-created_at'],
            },
        ),
    ]
