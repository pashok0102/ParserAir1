from django.conf import settings
from django.db import models


class FavoriteTicket(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_tickets')
    ticket_key = models.CharField(max_length=255)
    source = models.CharField(max_length=50)
    origin = models.CharField(max_length=16)
    destination = models.CharField(max_length=16)
    price = models.PositiveIntegerField()
    airline = models.CharField(max_length=120, blank=True)
    departure_at = models.CharField(max_length=64, blank=True)
    transfers = models.IntegerField(default=0)
    link = models.TextField(blank=True)
    updated_at = models.CharField(max_length=64, blank=True)
    original_price = models.PositiveIntegerField(null=True, blank=True)
    hot_discount_percent = models.IntegerField(null=True, blank=True)
    hot_expires_at = models.CharField(max_length=64, blank=True)
    special_offer_label = models.CharField(max_length=128, blank=True)
    estimated_price = models.BooleanField(default=False)
    baggage_info = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorite_tickets'
        constraints = [
            models.UniqueConstraint(fields=['user', 'ticket_key'], name='unique_user_ticket_key'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id}:{self.source}:{self.origin}-{self.destination}:{self.price}'


class SearchHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='search_history')
    route = models.CharField(max_length=255)
    anywhere = models.BooleanField(default=False)
    date = models.CharField(max_length=32, blank=True)
    return_date = models.CharField(max_length=32, blank=True)
    price_from = models.IntegerField(null=True, blank=True)
    price_to = models.IntegerField(null=True, blank=True)
    airline_code = models.CharField(max_length=32, blank=True)
    source = models.CharField(max_length=50)
    result_count = models.PositiveIntegerField(default=0)
    saved_to = models.CharField(max_length=512, blank=True)
    server_time = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'search_history'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id}:{self.source}:{self.route}:{self.created_at.isoformat()}'
