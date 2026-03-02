from django.urls import path
from . import views

app_name = "portal"

urlpatterns = [
    # =========================
    # المتقدم
    # =========================
    path("", views.login_view, name="login"),
    path("confirm/", views.confirm_view, name="confirm"),
    path("preferences/", views.preferences_view, name="preferences"),
    path("submit/", views.submit_view, name="submit"),
    path("done/", views.done_view, name="done"),

    # =========================
    # الإدارة (لوحة القرار + أدوات)
    # =========================
    path("admin/import/", views.admin_import_view, name="admin_import"),
    path("admin/dashboard/", views.admin_dashboard_view, name="admin_dashboard"),

    # =========================
    # ✅ إدارة البيانات (المتقدمين + الشواغر/المدارس)
    # =========================
    # Applicants
    path("admin/applicants/", views.admin_applicants_list, name="admin_applicants_list"),
    path("admin/applicants/create/", views.admin_applicants_create, name="admin_applicants_create"),
    path("admin/applicants/<int:pk>/edit/", views.admin_applicants_edit, name="admin_applicants_edit"),
    path("admin/applicants/<int:pk>/toggle/", views.admin_applicants_toggle, name="admin_applicants_toggle"),
    path("admin/applicants/<int:pk>/delete/", views.admin_applicants_delete, name="admin_applicants_delete"),

    # Vacancies / Schools
    path("admin/vacancies/", views.admin_vacancies_list, name="admin_vacancies_list"),
    path("admin/vacancies/create/", views.admin_vacancies_create, name="admin_vacancies_create"),
    path("admin/vacancies/<int:pk>/edit/", views.admin_vacancies_edit, name="admin_vacancies_edit"),
    path("admin/vacancies/<int:pk>/toggle/", views.admin_vacancies_toggle, name="admin_vacancies_toggle"),
    path("admin/vacancies/<int:pk>/delete/", views.admin_vacancies_delete, name="admin_vacancies_delete"),

    # =========================
    # تفاصيل الطلب
    # =========================
    path("admin/app/<int:app_id>/", views.admin_application_detail_view, name="admin_app_detail"),

    # ✅ صفحة طباعة رغبات المرشح
    path("admin/application/<int:app_id>/print/", views.admin_application_print_view, name="admin_application_print"),

    # JSON للمعاينة
    path("admin/app/<int:app_id>/json/", views.admin_application_detail_json_view, name="admin_app_detail_json"),

    # =========================
    # أفعال القرار (قرار الإدارة)
    # =========================
    path("admin/app/<int:app_id>/approve/", views.admin_decide_approve_view, name="admin_approve"),
    path("admin/app/<int:app_id>/reject/", views.admin_decide_reject_view, name="admin_reject"),
    path("admin/app/<int:app_id>/unlock/", views.admin_decide_unlock_view, name="admin_unlock"),

    # =========================
    # ✅ قرار جماعي
    # =========================
    path("admin/decide/bulk/", views.admin_decide_bulk_view, name="admin_bulk_decide"),

    # =========================
    # ✅ تحديد / إلغاء الرغبة المتحققة (الترشيح النهائي)
    # =========================
    path("admin/app/<int:app_id>/achieved/", views.admin_set_achieved_view, name="admin_set_achieved"),

    # =========================
    # تصدير Excel (كل الطلبات)
    # =========================
    path("admin/export.xlsx", views.admin_export_excel_view, name="admin_export_excel"),

    # =========================
    # ✅ التقارير الحالية (طباعة + CSV)
    # =========================
    path("admin/report/print/", views.admin_report_print_view, name="admin_report_print"),
    path("admin/report/csv-visible/", views.admin_report_csv_visible_view, name="admin_report_csv_visible"),

    # =========================
    # ✅ تقرير المرشحين النهائيين (achieved_pref)
    # =========================
    path("admin/nominations/", views.admin_nominations_report_view, name="admin_nominations_report"),
    path("admin/nominations/print/", views.admin_nominations_print_view, name="admin_nominations_print"),
    path("admin/nominations/csv/", views.admin_nominations_csv_view, name="admin_nominations_csv"),
    path("admin/nominations/excel/", views.admin_nominations_excel_view, name="admin_nominations_excel"),
]