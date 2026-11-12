"""The address of every page. The name on the right is how templates and views refer to a page."""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import admin_views, import_views, lead_views, money_views, price_views, report_views, schedule_views, views
from .forms import LoginForm

urlpatterns = [
    # signing in and out
    path("login/", auth_views.LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # the office
    path("", views.home, name="home"),
    path("start/", report_views.start, name="start"),
    path("dashboard/", report_views.dashboard, name="dashboard"),
    path("reports/", report_views.report_list, name="reports"),
    path("reports/<slug:key>/", report_views.report, name="report"),
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

    # leads: requests from the website
    path("leads/", lead_views.leads, name="leads"),
    path("leads/new/", lead_views.lead_new, name="lead_new"),
    path("leads/in/", lead_views.lead_in, name="lead_in"),                      # the website's form sends requests here
    path("leads/<int:pk>/", lead_views.lead, name="lead"),
    path("leads/<int:pk>/convert/", lead_views.lead_convert, name="lead_convert"),
    path("leads/<int:pk>/not-a-fit/", lead_views.lead_unfit, name="lead_unfit"),

    path("opportunities/", views.opps, name="opps"),
    path("opportunities/<str:number>/", views.opp, name="opp"),
    path("opportunities/<str:number>/inspection/", views.opp_inspection, name="opp_inspection"),
    path("opportunities/<str:number>/proposal/", money_views.opp_proposal, name="opp_proposal"),
    path("opportunities/<str:number>/proposal/view/", money_views.opp_document, name="opp_document"),
    path("opportunities/<str:number>/proposal/send/", money_views.opp_send, name="opp_send"),
    path("opportunities/<str:number>/sign/", views.opp_sign, name="opp_sign"),
    path("opportunities/<str:number>/lost/", views.opp_lost, name="opp_lost"),
    path("opportunities/<str:number>/take/", admin_views.take_inspection, name="take_inspection"),

    # jobs: the office sees all of them, a crew only its own
    path("jobs/", views.jobs, name="jobs"),
    path("jobs/<str:number>/", views.job, name="job"),
    path("jobs/<str:number>/schedule/", views.job_schedule, name="job_schedule"),
    path("jobs/<str:number>/stage/", views.job_stage, name="job_stage"),
    path("jobs/<str:number>/number/", views.job_ref, name="job_ref"),
    path("jobs/<str:number>/warranty/", views.job_warranty, name="job_warranty"),
    path("jobs/<str:number>/note/", views.job_note, name="job_note"),
    path("jobs/<str:number>/proposal/", money_views.job_proposal, name="job_proposal"),
    path("jobs/<str:number>/change-orders/new/", money_views.change_order_new, name="change_order_new"),
    path("jobs/<str:number>/change-orders/<int:n>/", money_views.change_order, name="change_order"),
    path("jobs/<str:number>/change-orders/<int:n>/send/", money_views.change_order_send, name="change_order_send"),
    path("jobs/<str:number>/payment/", money_views.payment_new, name="payment_new"),
    path("jobs/<str:number>/payments/<int:pk>/remove/", money_views.payment_remove, name="payment_remove"),
    path("jobs/<str:number>/payments/<int:pk>/receipt/", money_views.receipt, name="receipt"),
    path("jobs/<str:number>/payments/<int:pk>/receipt/send/", money_views.receipt_send, name="receipt_send"),
    path("jobs/<str:number>/invoice/", money_views.invoice, name="invoice"),
    path("jobs/<str:number>/invoice/send/", money_views.invoice_send, name="invoice_send"),
    path("jobs/<str:number>/got-it/", schedule_views.job_seen, name="job_seen"),
    path("jobs/<str:number>/workers/", schedule_views.job_worker, name="job_worker"),
    path("my-jobs/", views.my_jobs, name="my_jobs"),
    path("my-day/", schedule_views.my_day, name="my_day"),

    # the schedule
    path("schedule/", schedule_views.schedule, name="schedule"),
    path("schedule/book/", schedule_views.book, name="book"),
    path("schedule/calendar-address/", schedule_views.calendar_reset, name="calendar_reset"),
    path("calendar/<str:token>.ics", schedule_views.calendar_feed, name="calendar_feed"),      # no login: the long random word is the key

    # deleting, for a login with the "Delete records" permission, and the Recycle Bin
    path("delete/<str:kind>/<str:ident>/", admin_views.record_delete, name="record_delete"),
    path("recycle-bin/", admin_views.recycle_bin, name="recycle_bin"),
    path("recycle-bin/<int:pk>/restore/", admin_views.bin_restore, name="bin_restore"),
    path("recycle-bin/<int:pk>/delete/", admin_views.bin_purge, name="bin_purge"),

    # everyone
    path("search/", views.search, name="search"),
    path("touch/", views.touch, name="touch"),

    # the customer's own pages, opened from an email. No login: the long random word in the address is the key.
    path("p/<str:token>/", money_views.accept_proposal, name="accept_proposal"),
    path("c/<str:token>/", money_views.accept_change, name="accept_change"),

    # the administrator
    path("manage/", price_views.admin_home, name="admin_home"),
    path("manage/company/", price_views.company_details, name="company_details"),
    path("manage/history/", price_views.admin_history, name="admin_history"),
    path("manage/editor/", admin_views.editor, name="editor"),
    path("manage/editor/<int:pk>/undo/", admin_views.editor_undo, name="editor_undo"),
    path("manage/status/", admin_views.system_status, name="status"),
    path("manage/automations/", admin_views.automation_list, name="automations"),
    path("manage/automations/switch/", admin_views.automation_switch, name="automation_switch"),
    path("manage/users/", admin_views.users, name="users"),
    path("manage/users/new/", admin_views.user_new, name="user_new"),
    path("manage/users/<int:pk>/", admin_views.user_edit, name="user_edit"),
    path("manage/prices/", price_views.pricebook_list, name="pricebook"),
    path("manage/prices/new/", price_views.price_item_new, name="price_item_new"),
    path("manage/prices/upload/", price_views.price_upload, name="price_upload"),
    path("manage/prices/review/", price_views.price_review, name="price_review"),
    path("manage/prices/blank-file/", price_views.price_blank_file, name="price_blank_file"),
    path("manage/prices/<int:pk>/", price_views.price_item, name="price_item"),
    path("manage/prices/uploads/<int:pk>/roll-back/", price_views.price_rollback, name="price_rollback"),
    path("imports/", import_views.imports, name="imports"),
    path("imports/queue/", import_views.import_queue, name="import_queue"),
    path("imports/note/<int:pk>/", import_views.import_note, name="import_note"),
]
