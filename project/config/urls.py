"""
URL configuration for config project.
"""
from pathlib import Path

from django.contrib import admin
from django.http import FileResponse
from django.urls import include, path, re_path

from config import settings


def spa_serve(request, url=''):
    index_path = Path(settings.BASE_DIR) / 'project' / 'dist' / 'index.html'
    if not index_path.exists():
        from django.http import HttpResponse
        return HttpResponse('Frontend not built. Run: cd project/project && npm run build', status=200)
    return FileResponse(open(index_path, 'rb'))


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    re_path(r'^(?!/api/|/admin/|/static/).*', spa_serve, name='spa'),
]
