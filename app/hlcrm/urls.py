"""Web addresses for the whole project. The CRM's own pages are listed in crm/urls.py."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),             # Django's built-in admin site: users, crews and raw data (administrator only)
    path("i18n/", include("django.conf.urls.i18n")),     # the English / Spanish switch
    path("", include("crm.urls")),
]
