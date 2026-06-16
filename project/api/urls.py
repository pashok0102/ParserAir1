from django.urls import path

from .views import (
    auth_login,
    auth_logout,
    auth_me,
    auth_register,
    favorites_add,
    favorites_list,
    favorites_remove,
    health,
    history_list,
    history_remove,
    history_tickets,
    live_prices,
    search,
)

urlpatterns = [
    path('health', health, name='api-health'),
    path('search', search, name='api-search'),
    path('find-tickets', search, name='api-find-tickets'),
    path('auth/me', auth_me, name='api-auth-me'),
    path('auth/register', auth_register, name='api-auth-register'),
    path('auth/login', auth_login, name='api-auth-login'),
    path('auth/logout', auth_logout, name='api-auth-logout'),
    path('favorites', favorites_list, name='api-favorites-list'),
    path('favorites/add', favorites_add, name='api-favorites-add'),
    path('favorites/remove', favorites_remove, name='api-favorites-remove'),
    path('history', history_list, name='api-history-list'),
    path('history/tickets', history_tickets, name='api-history-tickets'),
    path('history/remove', history_remove, name='api-history-remove'),
    path('live-prices', live_prices, name='api-live-prices'),
]
