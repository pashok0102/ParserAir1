from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_searchhistory_saved_to'),
    ]

    operations = [
        migrations.AddField(
            model_name='favoriteticket',
            name='baggage_info',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='favoriteticket',
            name='estimated_price',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='favoriteticket',
            name='hot_discount_percent',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='favoriteticket',
            name='hot_expires_at',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='favoriteticket',
            name='original_price',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='favoriteticket',
            name='special_offer_label',
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
