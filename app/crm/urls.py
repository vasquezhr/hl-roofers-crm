"""The address of every page. The name on the right is how templates and views refer to a page."""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import import_views, views
from .forms import LoginForm

urlpatterns = [
    # signing in and out
    path("login/", auth_views.LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # the office
    path("", views.home, name="home"),
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/new/", views.account_new, name="account_new"),
    path("accounts/<int:pk>/", views.account, name="account"),
    path("accounts/<int:pk>/edit/", views.account_edit, name="account_edit"),
    path("accounts/<int:pk>/contacts/new/", views.contact_new, name="contact_new"),
    path("contacts/<int:pk>/edit/", views.contact_edit, name="contact_edit"),
    path("accounts/<int:pk>/properties/new/", views.property_new, name="property_new"),
    path("properties/<int:pk>/edit/", views.property_edit, name="property_edit"),
    path("accounts/<int:pk>/notes/new/", views.note_new, name="note_new"),
    path("accounts/<int:pk>/opportunities/new/", views.opp_new, name="opp_new"),

    path("opportunities/", views.opps, name="opps"),
    path("opportunities/<str:number>/", views.opp, name="opp"),
    path("opportunities/<str:number>/inspection/", views.opp_inspection, name="opp_inspection"),
    path("opportunities/<str:number>/proposal/", views.opp_proposal, name="opp_proposal"),
    path("opportunities/<str:number>/sign/", views.opp_sign, name="opp_sign"),
    path("opportunities/<str:number>/lost/", views.opp_lost, name="opp_lost"),

    # jobs: the office sees all of them, a crew only its own
    path("jobs/", views.jobs, name="jobs"),
    path("jobs/<str:number>/", views.job, name="job"),
    path("jobs/<str:number>/schedule/", views.job_schedule, name="job_schedule"),
    path("jobs/<str:number>/stage/", views.job_stage, name="job_stage"),
    path("jobs/<str:number>/number/", views.job_ref, name="job_ref"),
    path("jobs/<str:number>/warranty/", views.job_warranty, name="job_warranty"),
    path("jobs/<str:number>/note/", views.job_note, name="job_note"),
    path("my-jobs/", views.my_jobs, name="my_jobs"),

    # everyone
    path("search/", views.search, name="search"),
    path("touch/", views.touch, name="touch"),

    # the administrator: the Apple Notes import
    path("imports/", import_views.imports, name="imports"),
    path("imports/queue/", import_views.import_queue, name="import_queue"),
    path("imports/note/<int:pk>/", import_views.import_note, name="import_note"),
]
