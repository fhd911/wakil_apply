from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "portal"

urlpatterns = [
    # =========================
    # المتقدم
    # =========================
    path("", views.login_view, name="login"),
    path("closed/", views.closed_view, name="closed"),
    path("confirm/", views.confirm_view, name="confirm"),
    path("preferences/", views.preferences_view, name="preferences"),
    path("submit/", views.submit_view, name="submit"),
    path("done/", views.done_view, name="done"),

    # =========================
    # الإدارة
    # =========================
    path(
        "admin/",
        RedirectView.as_view(pattern_name="portal:admin_dashboard", permanent=False),
        name="admin_root",
    ),
    path("admin/import/", views.admin_import_view, name="admin_import"),
    path("admin/import/new-applicants/", views.admin_import_new_applicants_view, name="admin_import_new_applicants"),
    path("admin/import/schools/", views.admin_import_schools_view, name="admin_import_schools"),
    path("admin/dashboard/", views.admin_dashboard_view, name="admin_dashboard"),

    # =========================
    # فرز المتقدمين الجدد
    # =========================
    path("admin/sorting/new-applicants/", views.admin_new_applicants_sorting_view, name="admin_new_applicants_sorting"),
    path("admin/sorting/new-applicants/run/", views.admin_run_new_applicants_sorting_view, name="admin_run_new_applicants_sorting"),

    # =========================
    # شاشة الطلبات المعتمدة / الموافقات النهائية
    # =========================
    path("admin/final-approvals/", views.admin_final_approvals_view, name="admin_final_approvals"),
    path("admin/final-approvals/print/", views.admin_final_approvals_print_view, name="admin_final_approvals_print"),
    path("admin/final-approvals/excel/", views.admin_final_approvals_excel_view, name="admin_final_approvals_excel"),
    path(
        "admin/final-approvals/to-dashboard/",
        views.admin_final_approvals_to_dashboard_view,
        name="admin_final_approvals_to_dashboard",
    ),

    # =========================
    # ضابط فترة التقديم
    # =========================
    path("admin/portal-window/", views.admin_portal_window_view, name="admin_portal_window"),

    # =========================
    # غير المتقدمين
    # =========================
    path("admin/non-applicants/", views.admin_non_applicants_view, name="admin_non_applicants"),
    path("admin/non-applicants.csv", views.admin_non_applicants_csv_view, name="admin_non_applicants_csv"),

    # =========================
    # تقرير ضغط/إقبال المدارس
    # =========================
    path("admin/vacancies/pressure/", views.admin_vacancies_pressure_report_view, name="admin_vacancies_pressure"),
    path("admin/vacancies/pressure/print/", views.admin_vacancies_pressure_print_view, name="admin_vacancies_pressure_print"),
    path("admin/vacancies/pressure/csv/", views.admin_vacancies_pressure_csv_view, name="admin_vacancies_pressure_csv"),
    path("admin/vacancies/pressure/excel/", views.admin_vacancies_pressure_excel_view, name="admin_vacancies_pressure_excel"),

    # =========================
    # إدارة المتقدمين
    # =========================
    path("admin/applicants/", views.admin_applicants_list, name="admin_applicants_list"),
    path("admin/applicants/create/", views.admin_applicants_create, name="admin_applicants_create"),
    path("admin/applicants/disable-all/", views.admin_applicants_disable_all_view, name="admin_applicants_disable_all"),
    path("admin/applicants/enable-all/", views.admin_applicants_enable_all_view, name="admin_applicants_enable_all"),
    path("admin/applicants/<int:pk>/edit/", views.admin_applicants_edit, name="admin_applicants_edit"),
    path("admin/applicants/<int:pk>/toggle/", views.admin_applicants_toggle, name="admin_applicants_toggle"),
    path("admin/applicants/<int:pk>/delete/", views.admin_applicants_delete, name="admin_applicants_delete"),

    # =========================
    # إدارة الشواغر / المدارس
    # =========================
    path("admin/vacancies/", views.admin_vacancies_list, name="admin_vacancies_list"),
    path("admin/vacancies/create/", views.admin_vacancies_create, name="admin_vacancies_create"),
    path("admin/vacancies/disable-all/", views.admin_vacancies_disable_all_view, name="admin_vacancies_disable_all"),
    path("admin/vacancies/enable-all/", views.admin_vacancies_enable_all_view, name="admin_vacancies_enable_all"),
    path("admin/vacancies/<int:pk>/edit/", views.admin_vacancies_edit, name="admin_vacancies_edit"),
    path("admin/vacancies/<int:pk>/toggle/", views.admin_vacancies_toggle, name="admin_vacancies_toggle"),
    path("admin/vacancies/<int:pk>/delete/", views.admin_vacancies_delete, name="admin_vacancies_delete"),

    # =========================
    # تفاصيل الطلب
    # =========================
    path("admin/app/<int:app_id>/", views.admin_application_detail_view, name="admin_app_detail"),
    path("admin/application/<int:app_id>/print/", views.admin_application_print_view, name="admin_application_print"),
    path("admin/app/<int:app_id>/json/", views.admin_application_detail_json_view, name="admin_app_detail_json"),

    # =========================
    # قرارات الإدارة
    # =========================
    path("admin/app/<int:app_id>/approve/", views.admin_decide_approve_view, name="admin_approve"),
    path("admin/app/<int:app_id>/reject/", views.admin_decide_reject_view, name="admin_reject"),
    path("admin/app/<int:app_id>/unlock/", views.admin_decide_unlock_view, name="admin_unlock"),
    path("admin/app/<int:app_id>/undo/", views.admin_undo_view, name="admin_undo"),

    # =========================
    # قرار جماعي
    # =========================
    path("admin/decide/bulk/", views.admin_decide_bulk_view, name="admin_bulk_decide"),

    # =========================
    # تحديد الرغبة المتحققة
    # =========================
    path("admin/app/<int:app_id>/achieved/", views.admin_set_achieved_view, name="admin_set_achieved"),

    # =========================
    # تصدير Excel
    # =========================
    path("admin/export.xlsx", views.admin_export_excel_view, name="admin_export_excel"),

    # =========================
    # تقارير عامة
    # =========================
    path("admin/report/print/", views.admin_report_print_view, name="admin_report_print"),
    path("admin/report/csv-visible/", views.admin_report_csv_visible_view, name="admin_report_csv_visible"),

    # =========================
    # تقرير المرشحين النهائيين
    # =========================
    path("admin/nominations/", views.admin_nominations_report_view, name="admin_nominations_report"),
    path("admin/nominations/print/", views.admin_nominations_print_view, name="admin_nominations_print"),
    path("admin/nominations/csv/", views.admin_nominations_csv_view, name="admin_nominations_csv"),
    path("admin/nominations/excel/", views.admin_nominations_excel_view, name="admin_nominations_excel"),
]