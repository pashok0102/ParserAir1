from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FavoriteTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ticket_key', models.CharField(max_length=255)),
                ('source', models.CharField(max_length=50)),
                ('origin', models.CharField(max_length=16)),
                ('destination', models.CharField(max_length=16)),
                ('price', models.PositiveIntegerField()),
                ('airline', models.CharField(blank=True, max_length=120)),
                ('departure_at', models.CharField(blank=True, max_length=64)),
                ('transfers', models.IntegerField(default=0)),
                ('link', models.TextField(blank=True)),
                ('updated_at', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorite_tickets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'favorite_tickets',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='favoriteticket',
            constraint=models.UniqueConstraint(fields=('user', 'ticket_key'), name='unique_user_ticket_key'),
        ),
    ]
