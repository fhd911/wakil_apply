from __future__ import annotations

import os
import csv
from io import BytesIO
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Q,
    Count,
    OuterRef,
    Subquery,
    Value,
    CharField,
    Case,
    When,
    IntegerField,
)
from django.db.models.functions import Coalesce, Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST, require_GET

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from .forms import ImportExcelForm
from .forms_admin import ApplicantAdminForm, VacancyAdminForm
from .models import (
    Applicant,
    SchoolVacancy,
    Application,
    ApplicationPreference,
    PortalWindow,
)
from .services_import import import_applicants_xlsx, import_schools_xlsx


SESSION_KEY = "applicant_nid"


# =========================================================
# Helpers
# =========================================================
def _get_applicant(request):
    nid = request.session.get(SESSION_KEY)
    if not nid:
        return None
    return Applicant.objects.filter(national_id=nid, is_active=True).first()


def _portal_gate():
    """Return (open_now, msg, win)."""
    win = PortalWindow.get()
    open_now = win.is_open_now()
    msg = (win.closed_message or "التقديم مغلق حالياً.").strip()
    return open_now, msg, win


def _eligible_schools_for(applicant: Applicant):
    """
    المدارس المتاحة حسب الضوابط:
    - نفس القطاع
    - نفس الجنس
    - مفتوحة
    - الاحتياج: أي قيمة غير صفر
      (لأن نظامكم يعتمد الاحتياج بالسالب أيضًا مثل -1 و -2 ...)
    """
    return (
        SchoolVacancy.objects
        .filter(is_open=True, sector=applicant.sector, gender=applicant.gender)
        .exclude(deputy_need=0)
        .order_by("school_name")
    )


def _is_ajax(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _pct(cnt: int, total: int) -> int:
    if not total:
        return 0
    return int(round((cnt * 100) / total))


def _paginate(request, qs, per_page: int = 40):
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page") or 1
    return paginator.get_page(page_number)


def _set_admin_decision(app: Application, user, decision: str, note: str):
    """
    يثبت قرار الإدارة ويحدث حقول التدقيق.
    ✅ منطق قوي: إذا كان القرار (rejected/returned/فارغ) يتم إلغاء achieved_pref
       حتى لا يبقى “ترشيح نهائي” على طلب غير معتمد.
    """
    decision = (decision or "").strip()

    app.admin_decision = decision
    app.admin_note = (note or "").strip()
    app.admin_decided_by = user
    app.admin_decided_at = timezone.now()

    update_fields = ["admin_decision", "admin_note", "admin_decided_by", "admin_decided_at"]

    if decision in ("rejected", "returned", ""):
        if getattr(app, "achieved_pref_id", None):
            app.achieved_pref = None
            app.achieved_at = None
            app.achieved_by = None
            update_fields += ["achieved_pref", "achieved_at", "achieved_by"]

    app.save(update_fields=update_fields)


def _admin_base_qs():
    return (
        Application.objects
        .select_related("applicant", "achieved_pref__vacancy")
        .order_by("-submitted_at", "-id")
    )


def _admin_filters_from_request(request):
    status = (request.GET.get("status") or "").strip()
    sector = (request.GET.get("sector") or "").strip()
    gender = (request.GET.get("gender") or "").strip()
    return status, sector, gender


def _apply_admin_filters(qs, status: str, sector: str, gender: str):
    if status:
        qs = qs.filter(status=status)
    if sector:
        qs = qs.filter(applicant__sector__icontains=sector)
    if gender:
        qs = qs.filter(applicant__gender__icontains=gender)
    return qs


# =========================================================
# Report Helpers (Nominations)
# =========================================================
def _nominations_filters_from_request(request):
    q = (request.GET.get("q") or "").strip()
    sector = (request.GET.get("sector") or "").strip()
    gender = (request.GET.get("gender") or "").strip()
    school = (request.GET.get("school") or "").strip()
    from_date = (request.GET.get("from_date") or "").strip()
    to_date = (request.GET.get("to_date") or "").strip()
    return q, sector, gender, school, from_date, to_date


def _nominations_qs(request):
    q, sector, gender, school, from_date, to_date = _nominations_filters_from_request(request)

    qs = (
        Application.objects
        .select_related("applicant", "achieved_pref__vacancy", "achieved_by")
        .filter(achieved_pref__isnull=False)
        .order_by("-achieved_at", "-id")
    )

    if q:
        qs = qs.filter(
            Q(applicant__full_name__icontains=q)
            | Q(applicant__national_id__icontains=q)
            | Q(applicant__sector__icontains=q)
            | Q(applicant__gender__icontains=q)
            | Q(achieved_pref__vacancy__school_name__icontains=q)
            | Q(achieved_pref__vacancy__ministry_no__icontains=q)
            | Q(achieved_pref__vacancy__stage__icontains=q)
        )

    if sector:
        qs = qs.filter(applicant__sector__icontains=sector)

    if gender:
        qs = qs.filter(applicant__gender__icontains=gender)

    if school:
        qs = qs.filter(achieved_pref__vacancy__school_name__icontains=school)

    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            qs = qs.filter(achieved_at__date__gte=dt)
        except ValueError:
            pass

    if to_date:
        try:
            dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            qs = qs.filter(achieved_at__date__lte=dt)
        except ValueError:
            pass

    return qs


# =========================================================
# Portal: Closed Page
# =========================================================
@require_GET
def closed_view(request):
    open_now, msg, _win = _portal_gate()
    if open_now:
        return redirect("portal:login")
    return render(request, "portal/closed.html", {"msg": msg})


# =========================================================
# Applicant Portal
# =========================================================
@require_http_methods(["GET", "POST"])
def login_view(request):
    # ✅ GET يعرض صفحة الدخول (حتى لو مغلق)
    if request.method == "POST":
        open_now, _msg, _win = _portal_gate()
        if not open_now:
            return redirect("portal:closed")

        nid = (request.POST.get("national_id") or "").strip().replace(" ", "")

        if not nid:
            return render(request, "portal/login.html", {"error": "فضلاً أدخل السجل المدني"})

        if (not nid.isdigit()) or (len(nid) != 10):
            return render(request, "portal/login.html", {"error": "فضلاً أدخل السجل المدني بشكل صحيح"})

        applicant = Applicant.objects.filter(national_id=nid, is_active=True).first()
        if not applicant:
            return render(
                request,
                "portal/login.html",
                {"error": "لا يوجد بيانات. هذه الصفة لمن قدم من الوكلاء الرسميين على رابط الموارد البشرية"},
            )

        request.session[SESSION_KEY] = applicant.national_id
        return redirect("portal:confirm")

    return render(request, "portal/login.html")


def confirm_view(request):
    # ✅ redirect أنظف إذا مغلق
    open_now, _msg, _win = _portal_gate()
    if not open_now:
        return redirect("portal:closed")

    a = _get_applicant(request)
    if not a:
        return redirect("portal:login")

    def gv(attr: str, dash: str = "-"):
        v = getattr(a, attr, None)
        if v is None:
            return dash
        if isinstance(v, str):
            v = v.strip()
            return v if v else dash
        if hasattr(v, "strftime"):
            try:
                return v.strftime("%Y-%m-%d")
            except Exception:
                return str(v)
        return v

    fields = [
        {"label": "الاسم الرباعي", "value": gv("full_name")},
        {"label": "رقم الهوية", "value": gv("national_id")},
        {"label": "رقم الجوال", "value": gv("mobile")},
        {"label": "الجنس", "value": gv("gender")},
        {"label": "الرتبة", "value": gv("rank")},
        {"label": "القطاع", "value": gv("sector")},
        {"label": "العمل الحالي", "value": gv("current_job")},
        {"label": "المدرسة الحالية", "value": gv("current_school")},
        {"label": "تاريخ المباشرة", "value": gv("start_date")},
    ]

    if request.method == "POST":
        app, _ = Application.objects.get_or_create(applicant=a)
        app.confirmed_at = timezone.now()
        app.status = "draft"
        app.save(update_fields=["confirmed_at", "status"])
        return redirect("portal:preferences")

    return render(request, "portal/confirm.html", {"a": a, "fields": fields})


def preferences_view(request):
    # ✅ redirect أنظف إذا مغلق
    open_now, _msg, _win = _portal_gate()
    if not open_now:
        return redirect("portal:closed")

    a = _get_applicant(request)
    if not a:
        return redirect("portal:login")

    app, _ = Application.objects.get_or_create(applicant=a)

    if app.locked and app.status == "submitted":
        return redirect("portal:done")

    schools = _eligible_schools_for(a)
    return render(request, "portal/preferences.html", {"a": a, "app": app, "schools": schools, "closed_msg": ""})


@transaction.atomic
@require_POST
def submit_view(request):
    a = _get_applicant(request)
    if not a:
        return redirect("portal:login")

    app = get_object_or_404(Application, applicant=a)

    # ✅ حارس نهائي: redirect إلى closed + message
    open_now, msg, _win = _portal_gate()
    if not open_now:
        messages.error(request, msg)
        return redirect("portal:closed")

    ids = request.POST.getlist("vacancy_ids")
    fallback = (request.POST.get("fallback_choice") or "").strip()

    if fallback not in ("admin_assign", "stay_current"):
        schools = _eligible_schools_for(a)
        return render(
            request,
            "portal/preferences.html",
            {"a": a, "app": app, "schools": schools, "error": "اختر خيار الإقرار في حال عدم توفر فرصة"},
        )

    allowed_ids = set(_eligible_schools_for(a).values_list("id", flat=True))

    clean_ids: list[int] = []
    for x in ids:
        try:
            vid = int(x)
        except Exception:
            continue
        if vid in allowed_ids and vid not in clean_ids:
            clean_ids.append(vid)

    ApplicationPreference.objects.filter(application=app).delete()
    for idx, vid in enumerate(clean_ids, start=1):
        ApplicationPreference.objects.create(application=app, vacancy_id=vid, rank=idx)

    app.fallback_choice = fallback
    app.status = "submitted"
    app.locked = True
    app.submitted_at = timezone.now()
    app.save(update_fields=["fallback_choice", "status", "locked", "submitted_at"])

    return redirect("portal:done")


def done_view(request):
    a = _get_applicant(request)
    if not a:
        return redirect("portal:login")

    app = (
        Application.objects
        .select_related("applicant", "achieved_pref__vacancy")
        .prefetch_related("prefs", "prefs__vacancy")
        .filter(applicant=a)
        .first()
    )
    prefs = list(app.prefs.select_related("vacancy").all()) if app else []
    return render(request, "portal/done.html", {"a": a, "app": app, "prefs": prefs})


# =========================================================
# Admin: Portal Window (Open/Close)
# =========================================================
@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_portal_window_view(request):
    win = PortalWindow.get()

    if request.method == "POST":
        win.is_enabled = (request.POST.get("is_enabled") == "1")

        opens_at = (request.POST.get("opens_at") or "").strip()
        closes_at = (request.POST.get("closes_at") or "").strip()
        msg = (request.POST.get("closed_message") or "").strip()
        win.closed_message = msg or "التقديم مغلق حالياً."

        def parse_dt(v: str):
            if not v:
                return None
            try:
                naive = datetime.strptime(v, "%Y-%m-%dT%H:%M")
            except Exception:
                return None
            tz = timezone.get_current_timezone()
            return timezone.make_aware(naive, tz)

        win.opens_at = parse_dt(opens_at)
        win.closes_at = parse_dt(closes_at)
        win.save()

        messages.success(request, "تم حفظ إعدادات فترة التقديم.")
        return redirect("portal:admin_portal_window")

    return render(request, "portal/admin_portal_window.html", {"win": win})


# =========================================================
# Admin: Manage Applicants
# =========================================================
@staff_member_required
def admin_applicants_list(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()  # active / inactive / all

    qs = Applicant.objects.all().order_by("-id")

    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q)
            | Q(national_id__icontains=q)
            | Q(sector__icontains=q)
            | Q(mobile__icontains=q)
            | Q(current_school__icontains=q)
        )

    page_obj = _paginate(request, qs, per_page=40)

    return render(
        request,
        "portal/admin_applicants_list.html",
        {"rows": page_obj, "q": q, "status": status, "total": qs.count()},
    )


@staff_member_required
def admin_applicants_create(request):
    form = ApplicantAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة المتقدم.")
        return redirect("portal:admin_applicants_list")
    return render(request, "portal/admin_applicants_form.html", {"form": form, "mode": "create"})


@staff_member_required
def admin_applicants_edit(request, pk: int):
    obj = get_object_or_404(Applicant, pk=pk)
    form = ApplicantAdminForm(request.POST or None, instance=obj)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديل.")
        return redirect("portal:admin_applicants_list")

    apps_count = Application.objects.filter(applicant=obj).count()
    return render(
        request,
        "portal/admin_applicants_form.html",
        {"form": form, "mode": "edit", "obj": obj, "apps_count": apps_count},
    )


@staff_member_required
@require_POST
def admin_applicants_toggle(request, pk: int):
    obj = get_object_or_404(Applicant, pk=pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    messages.success(request, "تم تحديث حالة المتقدم.")
    return redirect("portal:admin_applicants_list")


@staff_member_required
@require_POST
def admin_applicants_delete(request, pk: int):
    if not request.user.is_superuser:
        messages.error(request, "غير مصرح بالحذف النهائي. استخدم التعطيل.")
        return redirect("portal:admin_applicants_list")

    obj = get_object_or_404(Applicant, pk=pk)

    if Application.objects.filter(applicant=obj).exists():
        messages.error(request, "لا يمكن الحذف النهائي: المتقدم لديه طلبات مرتبطة. استخدم التعطيل بدلًا من ذلك.")
        return redirect("portal:admin_applicants_list")

    obj.delete()
    messages.success(request, "تم حذف المتقدم نهائيًا.")
    return redirect("portal:admin_applicants_list")


# =========================================================
# Admin: Manage Vacancies + Counts
# =========================================================
@staff_member_required
def admin_vacancies_list(request):
    q = (request.GET.get("q") or "").strip()
    open_state = (request.GET.get("open") or "").strip()  # open / closed / all
    gender = (request.GET.get("gender") or "").strip()
    sector = (request.GET.get("sector") or "").strip()

    achieved_sq = (
        Application.objects
        .filter(achieved_pref__vacancy_id=OuterRef("pk"))
        .values("achieved_pref__vacancy_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )

    qs = (
        SchoolVacancy.objects
        .all()
        .annotate(
            # ✅ reverse الصحيح عندك حسب الخطأ: applicationpreference
            interested_total=Count("applicationpreference", distinct=True),
            interested_rank1=Count("applicationpreference", filter=Q(applicationpreference__rank=1), distinct=True),
            achieved_total=Coalesce(Subquery(achieved_sq, output_field=IntegerField()), Value(0)),
        )
        .order_by("-id")
    )

    if open_state == "open":
        qs = qs.filter(is_open=True)
    elif open_state == "closed":
        qs = qs.filter(is_open=False)

    if gender:
        qs = qs.filter(gender__icontains=gender)

    if sector:
        qs = qs.filter(sector__icontains=sector)

    if q:
        qs = qs.filter(
            Q(school_name__icontains=q)
            | Q(ministry_no__icontains=q)
            | Q(sector__icontains=q)
            | Q(manager_name__icontains=q)
            | Q(manager_national_id__icontains=q)
        )

    page_obj = _paginate(request, qs, per_page=40)

    return render(
        request,
        "portal/admin_vacancies_list.html",
        {"rows": page_obj, "q": q, "open": open_state, "gender": gender, "sector": sector, "total": qs.count()},
    )


@staff_member_required
def admin_vacancies_create(request):
    form = VacancyAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الشاغر/المدرسة.")
        return redirect("portal:admin_vacancies_list")
    return render(request, "portal/admin_vacancies_form.html", {"form": form, "mode": "create"})


@staff_member_required
def admin_vacancies_edit(request, pk: int):
    obj = get_object_or_404(SchoolVacancy, pk=pk)
    form = VacancyAdminForm(request.POST or None, instance=obj)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديل.")
        return redirect("portal:admin_vacancies_list")

    return render(request, "portal/admin_vacancies_form.html", {"form": form, "mode": "edit", "obj": obj})


@staff_member_required
@require_POST
def admin_vacancies_toggle(request, pk: int):
    obj = get_object_or_404(SchoolVacancy, pk=pk)
    obj.is_open = not obj.is_open
    obj.save(update_fields=["is_open"])
    messages.success(request, "تم تحديث حالة الشاغر.")
    return redirect("portal:admin_vacancies_list")


@staff_member_required
@require_POST
def admin_vacancies_delete(request, pk: int):
    if not request.user.is_superuser:
        messages.error(request, "غير مصرح بالحذف النهائي. استخدم الإغلاق بدلًا من ذلك.")
        return redirect("portal:admin_vacancies_list")

    obj = get_object_or_404(SchoolVacancy, pk=pk)

    if ApplicationPreference.objects.filter(vacancy=obj).exists():
        messages.error(request, "لا يمكن الحذف النهائي: يوجد رغبات مرتبطة بهذا الشاغر. استخدم (إغلاق) بدلًا من ذلك.")
        return redirect("portal:admin_vacancies_list")

    obj.delete()
    messages.success(request, "تم حذف الشاغر نهائيًا.")
    return redirect("portal:admin_vacancies_list")


# =========================================================
# Admin: Vacancies Pressure Report (Report + Print + CSV + Excel)
# =========================================================
def _vacancies_pressure_ctx(request):
    q = (request.GET.get("q") or "").strip()
    gender = (request.GET.get("gender") or "").strip()
    sector = (request.GET.get("sector") or "").strip()
    open_state = (request.GET.get("open") or "").strip()  # open/closed/all
    sort = (request.GET.get("sort") or "rank1").strip()   # total / rank1 / achieved / need
    top_raw = (request.GET.get("top") or "0").strip()
    try:
        top = int(top_raw) if top_raw else 0
    except Exception:
        top = 0

    achieved_sq = (
        Application.objects
        .filter(achieved_pref__vacancy_id=OuterRef("pk"))
        .values("achieved_pref__vacancy_id")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )

    qs = (
        SchoolVacancy.objects
        .all()
        .annotate(
            interested_total=Count("applicationpreference", distinct=True),
            interested_rank1=Count("applicationpreference", filter=Q(applicationpreference__rank=1), distinct=True),
            achieved_total=Coalesce(Subquery(achieved_sq, output_field=IntegerField()), Value(0)),
        )
    )

    if open_state == "open":
        qs = qs.filter(is_open=True)
    elif open_state == "closed":
        qs = qs.filter(is_open=False)

    if gender:
        qs = qs.filter(gender__icontains=gender)
    if sector:
        qs = qs.filter(sector__icontains=sector)
    if q:
        qs = qs.filter(
            Q(school_name__icontains=q)
            | Q(ministry_no__icontains=q)
            | Q(sector__icontains=q)
            | Q(manager_name__icontains=q)
        )

    if sort == "total":
        qs = qs.order_by("-interested_total", "-interested_rank1", "-achieved_total", "school_name")
    elif sort == "achieved":
        qs = qs.order_by("-achieved_total", "-interested_rank1", "-interested_total", "school_name")
    elif sort == "need":
        qs = qs.order_by("-deputy_need", "-interested_rank1", "-interested_total", "school_name")
    else:  # rank1
        qs = qs.order_by("-interested_rank1", "-interested_total", "-achieved_total", "school_name")

    rows = list(qs[:top] if top and top > 0 else qs[:5000])

    total_schools = qs.count()
    sum_total = sum(int(getattr(x, "interested_total", 0) or 0) for x in rows)
    sum_rank1 = sum(int(getattr(x, "interested_rank1", 0) or 0) for x in rows)
    sum_achieved = sum(int(getattr(x, "achieved_total", 0) or 0) for x in rows)

    return {
        "rows": rows,
        "total_schools": total_schools,
        "sum_total": sum_total,
        "sum_rank1": sum_rank1,
        "sum_achieved": sum_achieved,
        "now": timezone.localtime(),
        "f": {"q": q, "sector": sector, "gender": gender, "open": open_state, "sort": sort, "top": top},
    }


@staff_member_required
def admin_vacancies_pressure_report_view(request):
    return render(request, "portal/admin_vacancies_pressure_report.html", _vacancies_pressure_ctx(request))


@staff_member_required
def admin_vacancies_pressure_print_view(request):
    return render(request, "portal/admin_vacancies_pressure_print.html", _vacancies_pressure_ctx(request))


@staff_member_required
def admin_vacancies_pressure_csv_view(request):
    ctx = _vacancies_pressure_ctx(request)
    rows = ctx["rows"]

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="vacancies_pressure.csv"'
    resp.write("\ufeff")

    w = csv.writer(resp)
    w.writerow([
        "#",
        "المدرسة",
        "رقم الوزارة",
        "القطاع",
        "الجنس",
        "المرحلة",
        "الاحتياج",
        "الراغبون",
        "رغبة أولى",
        "ترشيحات نهائية",
        "الحالة",
    ])

    for i, v in enumerate(rows, start=1):
        w.writerow([
            i,
            v.school_name,
            v.ministry_no,
            v.sector,
            v.gender,
            v.stage,
            v.deputy_need,
            getattr(v, "interested_total", 0) or 0,
            getattr(v, "interested_rank1", 0) or 0,
            getattr(v, "achieved_total", 0) or 0,
            "مفتوح" if v.is_open else "مغلق",
        ])

    return resp


@staff_member_required
def admin_vacancies_pressure_excel_view(request):
    ctx = _vacancies_pressure_ctx(request)
    rows = ctx["rows"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Pressure"

    headers = [
        "#",
        "المدرسة",
        "رقم الوزارة",
        "القطاع",
        "الجنس",
        "المرحلة",
        "الاحتياج",
        "الراغبون",
        "رغبة أولى",
        "ترشيحات نهائية",
        "الحالة",
    ]
    ws.append(headers)

    header_font = Font(bold=True)
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    for i, v in enumerate(rows, start=1):
        ws.append([
            i,
            v.school_name,
            v.ministry_no,
            v.sector,
            v.gender,
            v.stage,
            v.deputy_need,
            getattr(v, "interested_total", 0) or 0,
            getattr(v, "interested_rank1", 0) or 0,
            getattr(v, "achieved_total", 0) or 0,
            "مفتوح" if v.is_open else "مغلق",
        ])

    widths = [5, 42, 14, 20, 10, 14, 10, 12, 12, 14, 10]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    filename = f"vacancies_pressure_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    resp = HttpResponse(
        bio.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# =========================================================
# Admin: Dashboard + Reading
# =========================================================
@staff_member_required
def admin_dashboard_view(request):
    status, sector, gender = _admin_filters_from_request(request)

    qs0 = _admin_base_qs()
    qs = _apply_admin_filters(qs0, status, sector, gender)

    pref_rank1 = (
        ApplicationPreference.objects
        .filter(application=OuterRef("pk"), rank=1)
        .select_related("vacancy")
        .order_by("id")
    )

    qs = qs.annotate(
        first_school=Subquery(pref_rank1.values("vacancy__school_name")[:1], output_field=CharField()),
        first_stage=Subquery(pref_rank1.values("vacancy__stage")[:1], output_field=CharField()),
    ).annotate(
        prefs_count=Count("prefs", distinct=True),
        first_pref_text=Case(
            When(first_school__isnull=True, then=Value("-")),
            default=Concat(
                Coalesce("first_school", Value("")),
                Value(" — "),
                Coalesce("first_stage", Value("")),
                output_field=CharField(),
            ),
            output_field=CharField(),
        ),
    )

    qs = qs.annotate(
        achieved_text=Case(
            When(achieved_pref__isnull=True, then=Value("")),
            default=Concat(
                Value("رغبة "),
                Coalesce("achieved_pref__rank", Value(0)),
                Value(" — "),
                Coalesce("achieved_pref__vacancy__school_name", Value("")),
                Value(" ("),
                Coalesce("achieved_pref__vacancy__stage", Value("")),
                Value(")"),
                output_field=CharField(),
            ),
            output_field=CharField(),
        )
    )

    rows = list(qs[:500])
    total_apps = qs.count()

    total_prefs = (
        ApplicationPreference.objects
        .filter(application__in=qs.values("id"))
        .count()
    )

    unique_sectors = (
        qs.values("applicant__sector")
        .exclude(applicant__sector__isnull=True)
        .exclude(applicant__sector__exact="")
        .distinct()
        .count()
    )

    status_counts = list(qs.values("status").annotate(c=Count("id")).order_by("-c"))
    for it in status_counts:
        it["label"] = (it.get("status") or "-")
        it["pct"] = _pct(int(it.get("c") or 0), total_apps)

    decision_counts = list(qs.values("admin_decision").annotate(c=Count("id")).order_by("-c"))
    for it in decision_counts:
        raw = (it.get("admin_decision") or "").strip() or "pending"
        it["label"] = raw
        it["pct"] = _pct(int(it.get("c") or 0), total_apps)

    count_submitted = qs.filter(status="submitted").count()
    count_draft = qs.filter(status="draft").count()
    nominated_count = qs.filter(achieved_pref__isnull=False).count()

    ctx = {
        "rows": rows,
        "total_apps": total_apps,
        "total_prefs": total_prefs,
        "unique_sectors": unique_sectors,
        "status_counts": status_counts,
        "decision_counts": decision_counts,
        "count_submitted": count_submitted,
        "count_draft": count_draft,
        "nominated_count": nominated_count,
        "f_status": status,
        "f_sector": sector,
        "f_gender": gender,
    }
    return render(request, "portal/admin_dashboard.html", ctx)


@staff_member_required
def admin_application_detail_view(request, app_id: int):
    app = get_object_or_404(
        Application.objects.select_related(
            "applicant",
            "achieved_by",
            "admin_decided_by",
            "achieved_pref__vacancy",
        ),
        id=app_id,
    )

    prefs = list(
        ApplicationPreference.objects
        .filter(application=app)
        .select_related("vacancy")
        .order_by("rank")
    )
    return render(request, "portal/admin_application_detail.html", {"app": app, "a": app.applicant, "prefs": prefs})


@staff_member_required
def admin_application_print_view(request, app_id: int):
    application = get_object_or_404(
        Application.objects.select_related(
            "applicant",
            "achieved_pref__vacancy",
            "achieved_by",
            "admin_decided_by",
        ),
        id=app_id,
    )

    selected_pref = application.achieved_pref if getattr(application, "achieved_pref_id", None) else None

    return render(
        request,
        "portal/admin_application_print.html",
        {"application": application, "selected_pref": selected_pref},
    )


@staff_member_required
def admin_application_detail_json_view(request, app_id: int):
    app = get_object_or_404(
        Application.objects.select_related("applicant", "achieved_pref__vacancy"),
        id=app_id,
    )

    prefs = list(
        ApplicationPreference.objects
        .filter(application=app)
        .select_related("vacancy")
        .order_by("rank")
    )

    achieved = None
    if getattr(app, "achieved_pref_id", None) and getattr(app, "achieved_pref", None):
        ap = app.achieved_pref
        if ap and getattr(ap, "vacancy", None):
            achieved = {
                "pref_id": ap.id,
                "rank": ap.rank,
                "label": f"{ap.vacancy.school_name} — {ap.vacancy.stage}",
            }

    data = {
        "id": app.id,
        "status": app.status,
        "submitted_at": app.submitted_at.strftime("%Y-%m-%d %H:%M") if app.submitted_at else "",
        "fallback_choice": getattr(app, "fallback_choice", "") or "",
        "admin_decision": getattr(app, "admin_decision", "") or "",
        "admin_note": getattr(app, "admin_note", "") or "",
        "admin_decided_at": app.admin_decided_at.strftime("%Y-%m-%d %H:%M") if getattr(app, "admin_decided_at", None) else "",
        "achieved": achieved,
        "applicant": {
            "national_id": app.applicant.national_id,
            "full_name": app.applicant.full_name,
            "sector": app.applicant.sector,
            "gender": app.applicant.gender,
        },
        "prefs": [{"id": p.id, "rank": p.rank, "label": f"{p.vacancy.school_name} — {p.vacancy.stage}"} for p in prefs],
    }
    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


# =========================================================
# Admin: Decision Actions
# =========================================================
@staff_member_required
@require_POST
def admin_decide_approve_view(request, app_id: int):
    app = get_object_or_404(Application, id=app_id)
    note = (request.POST.get("note") or "").strip()
    _set_admin_decision(app, request.user, "approved", note)

    if _is_ajax(request):
        return JsonResponse({"ok": True, "id": app.id, "admin_decision": "approved"}, json_dumps_params={"ensure_ascii": False})

    messages.success(request, f"تم اعتماد الطلب #{app.id}")
    return redirect("portal:admin_app_detail", app_id=app.id)


@staff_member_required
@require_POST
def admin_decide_reject_view(request, app_id: int):
    app = get_object_or_404(Application, id=app_id)
    note = (request.POST.get("note") or "").strip()
    if not note:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": "فضلاً اكتب سبب الرفض."}, status=400, json_dumps_params={"ensure_ascii": False})
        messages.error(request, "فضلاً اكتب سبب الرفض.")
        return redirect("portal:admin_app_detail", app_id=app.id)

    _set_admin_decision(app, request.user, "rejected", note)

    if _is_ajax(request):
        return JsonResponse({"ok": True, "id": app.id, "admin_decision": "rejected"}, json_dumps_params={"ensure_ascii": False})

    messages.success(request, f"تم رفض الطلب #{app.id}")
    return redirect("portal:admin_app_detail", app_id=app.id)


@staff_member_required
@require_POST
def admin_decide_unlock_view(request, app_id: int):
    app = get_object_or_404(Application, id=app_id)
    note = (request.POST.get("note") or "").strip()
    if not note:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": "فضلاً اكتب سبب الإرجاع للتعديل."}, status=400, json_dumps_params={"ensure_ascii": False})
        messages.error(request, "فضلاً اكتب سبب الإرجاع للتعديل.")
        return redirect("portal:admin_app_detail", app_id=app.id)

    app.locked = False
    app.status = "draft"
    app.save(update_fields=["locked", "status"])

    _set_admin_decision(app, request.user, "returned", note)

    if _is_ajax(request):
        return JsonResponse({"ok": True, "id": app.id, "admin_decision": "returned", "status": "draft"}, json_dumps_params={"ensure_ascii": False})

    messages.success(request, f"تم فتح التعديل للطلب #{app.id}")
    return redirect("portal:admin_app_detail", app_id=app.id)


# =========================================================
# Admin: Undo Last Decision (SERVER SIDE)
# =========================================================
@staff_member_required
@require_POST
def admin_undo_view(request, app_id: int):
    """
    Undo سريع:
    - يرجع status + locked للحالة السابقة
    - يرجع admin_decision/admin_note/admin_decided_* للوضع السابق إن أُرسل
      وإلا: يرجعها للوضع "pending" (فارغ)
    - يعيد achieved_pref إذا أُرسل achieved_pref_id وكان تابعًا لنفس الطلب
      (اختياري)
    """
    if not _is_ajax(request):
     return JsonResponse(
        {"ok": False, "error": "AJAX فقط."},
        status=400,
        json_dumps_params={"ensure_ascii": False},
    )

# =========================================================
# Admin: Bulk Decision
# =========================================================
@staff_member_required
@require_POST
def admin_decide_bulk_view(request):
    ids = request.POST.getlist("ids")
    action = (request.POST.get("action") or "").strip()
    note = (request.POST.get("note") or "").strip()

    clean_ids: list[int] = []
    for x in ids:
        try:
            clean_ids.append(int(x))
        except Exception:
            continue

    if not clean_ids:
        return JsonResponse({"ok": False, "error": "لا توجد طلبات محددة."}, status=400, json_dumps_params={"ensure_ascii": False})

    if action not in ("approve", "reject", "unlock"):
        return JsonResponse({"ok": False, "error": "إجراء غير صحيح."}, status=400, json_dumps_params={"ensure_ascii": False})

    if action in ("reject", "unlock") and not note:
        return JsonResponse({"ok": False, "error": "الملاحظة مطلوبة للرفض أو الإرجاع."}, status=400, json_dumps_params={"ensure_ascii": False})

    qs = Application.objects.filter(id__in=clean_ids)

    with transaction.atomic():
        updated = 0

        if action == "unlock":
            qs.update(locked=False, status="draft")
            for app in qs.select_for_update():
                _set_admin_decision(app, request.user, "returned", note)
                updated += 1

        elif action == "approve":
            for app in qs.select_for_update():
                _set_admin_decision(app, request.user, "approved", note)
                updated += 1

        else:
            for app in qs.select_for_update():
                _set_admin_decision(app, request.user, "rejected", note)
                updated += 1

    return JsonResponse({"ok": True, "updated": updated}, json_dumps_params={"ensure_ascii": False})


# =========================================================
# Admin: Reports (Print + CSV Visible)
# =========================================================
@staff_member_required
def admin_report_print_view(request):
    status, sector, gender = _admin_filters_from_request(request)

    qs0 = (
        Application.objects
        .select_related("applicant")
        .annotate(prefs_count=Count("prefs", distinct=True))
        .order_by("-submitted_at", "-id")
    )
    qs = _apply_admin_filters(qs0, status, sector, gender)
    rows = list(qs[:5000])

    ctx = {
        "rows": rows,
        "total": len(rows),
        "now": timezone.localtime(),
        "f": {"status": status, "sector": sector, "gender": gender},
    }
    return render(request, "portal/admin_report_print.html", ctx)


@staff_member_required
def admin_report_csv_visible_view(request):
    status, sector, gender = _admin_filters_from_request(request)

    ids = (request.GET.get("ids") or "").strip()
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]

    qs0 = (
        Application.objects
        .select_related("applicant")
        .annotate(prefs_count=Count("prefs", distinct=True))
        .order_by("-submitted_at", "-id")
    )
    qs = _apply_admin_filters(qs0, status, sector, gender)
    if id_list:
        qs = qs.filter(id__in=id_list)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="decision_visible.csv"'
    resp.write("\ufeff")

    w = csv.writer(resp)
    w.writerow([
        "رقم الطلب", "الاسم", "السجل المدني", "القطاع", "الجنس",
        "الحالة", "عدد الرغبات", "قرار الإدارة", "ملاحظة الإدارة", "تاريخ التقديم",
    ])

    for app in qs:
        p = app.applicant
        w.writerow([
            app.id,
            getattr(p, "full_name", "") or "",
            getattr(p, "national_id", "") or "",
            getattr(p, "sector", "") or "",
            getattr(p, "gender", "") or "",
            getattr(app, "status", "") or "",
            getattr(app, "prefs_count", 0) or 0,
            getattr(app, "admin_decision", "") or "",
            getattr(app, "admin_note", "") or "",
            timezone.localtime(app.submitted_at).strftime("%Y-%m-%d %H:%M") if getattr(app, "submitted_at", None) else "",
        ])

    return resp


# =========================================================
# Admin: Set Achieved
# =========================================================
@staff_member_required
@require_POST
def admin_set_achieved_view(request, app_id: int):
    app = get_object_or_404(Application, id=app_id)
    pref_id_raw = (request.POST.get("achieved_pref_id") or "").strip()

    if not pref_id_raw:
        app.achieved_pref = None
        app.achieved_at = None
        app.achieved_by = None
        app.save(update_fields=["achieved_pref", "achieved_at", "achieved_by"])
        messages.success(request, "تم إلغاء تحديد الرغبة المتحققة.")
        return redirect("portal:admin_app_detail", app_id=app.id)

    try:
        pref_id = int(pref_id_raw)
    except ValueError:
        messages.error(request, "قيمة غير صحيحة.")
        return redirect("portal:admin_app_detail", app_id=app.id)

    pref = (
        ApplicationPreference.objects
        .filter(id=pref_id, application=app)
        .select_related("vacancy")
        .first()
    )
    if not pref:
        messages.error(request, "الرغبة المحددة غير تابعة لهذا الطلب.")
        return redirect("portal:admin_app_detail", app_id=app.id)

    if (app.admin_decision or "").strip() != "approved":
        app.admin_decision = "approved"
        if not app.admin_decided_at:
            app.admin_decided_at = timezone.now()
            app.admin_decided_by = request.user
        else:
            if not app.admin_decided_by_id:
                app.admin_decided_by = request.user
        app.save(update_fields=["admin_decision", "admin_decided_at", "admin_decided_by"])

    app.achieved_pref = pref
    app.achieved_at = timezone.now()
    app.achieved_by = request.user
    app.save(update_fields=["achieved_pref", "achieved_at", "achieved_by"])

    messages.success(request, f"تم تحديد الرغبة المتحققة: رغبة #{pref.rank}")
    return redirect("portal:admin_app_detail", app_id=app.id)


# =========================================================
# Admin: Nominations Report + Print + CSV + Excel
# =========================================================
@staff_member_required
def admin_nominations_report_view(request):
    qs = _nominations_qs(request)

    total = qs.count()
    by_sector = list(qs.values("applicant__sector").annotate(c=Count("id")).order_by("-c")[:12])
    for it in by_sector:
        it["label"] = (it.get("applicant__sector") or "-")
        it["pct"] = _pct(int(it.get("c") or 0), total)

    ctx = {
        "rows": list(qs[:5000]),
        "total": total,
        "by_sector": by_sector,
        "q": request.GET.get("q", ""),
        "sector": request.GET.get("sector", ""),
        "gender": request.GET.get("gender", ""),
        "school": request.GET.get("school", ""),
        "from_date": request.GET.get("from_date", ""),
        "to_date": request.GET.get("to_date", ""),
    }
    return render(request, "portal/admin_nominations_report.html", ctx)


@staff_member_required
def admin_nominations_print_view(request):
    qs = _nominations_qs(request)
    ctx = {
        "rows": qs,
        "total": qs.count(),
        "now": timezone.localtime(),
        "q": request.GET.get("q", ""),
        "sector": request.GET.get("sector", ""),
        "gender": request.GET.get("gender", ""),
        "school": request.GET.get("school", ""),
        "from_date": request.GET.get("from_date", ""),
        "to_date": request.GET.get("to_date", ""),
    }
    return render(request, "portal/admin_nominations_print.html", ctx)


@staff_member_required
def admin_nominations_csv_view(request):
    qs = _nominations_qs(request)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="nominations.csv"'
    resp.write("\ufeff")

    w = csv.writer(resp)
    w.writerow([
        "#",
        "رقم الطلب",
        "الاسم",
        "السجل",
        "قطاع المتقدم",
        "جنس المتقدم",
        "الرغبة المتحققة",
        "مدرسة الترشيح",
        "رقم الوزارة",
        "مرحلة المدرسة",
        "قطاع المدرسة",
        "جنس المدرسة",
        "تاريخ الترشيح",
        "مرشح بواسطة",
        "قرار الإدارة",
        "ملاحظة الإدارة",
    ])

    for i, app in enumerate(qs, start=1):
        a = app.applicant
        vac = app.achieved_pref.vacancy if app.achieved_pref else None
        w.writerow([
            i,
            app.id,
            getattr(a, "full_name", "") or "",
            getattr(a, "national_id", "") or "",
            getattr(a, "sector", "") or "",
            getattr(a, "gender", "") or "",
            getattr(app.achieved_pref, "rank", "") if app.achieved_pref else "",
            getattr(vac, "school_name", "") if vac else "",
            getattr(vac, "ministry_no", "") if vac else "",
            getattr(vac, "stage", "") if vac else "",
            getattr(vac, "sector", "") if vac else "",
            getattr(vac, "gender", "") if vac else "",
            timezone.localtime(app.achieved_at).strftime("%Y-%m-%d %H:%M") if app.achieved_at else "",
            getattr(app.achieved_by, "username", "") if app.achieved_by else "",
            (app.admin_decision or "").strip(),
            (app.admin_note or "").strip(),
        ])

    return resp


@staff_member_required
def admin_nominations_excel_view(request):
    qs = _nominations_qs(request)

    wb = Workbook()
    ws = wb.active
    ws.title = "Nominations"

    headers = [
        "#",
        "رقم الطلب",
        "الاسم",
        "السجل",
        "قطاع المتقدم",
        "جنس المتقدم",
        "الرغبة المتحققة",
        "مدرسة الترشيح",
        "رقم الوزارة",
        "مرحلة المدرسة",
        "قطاع المدرسة",
        "جنس المدرسة",
        "تاريخ الترشيح",
        "مرشح بواسطة",
        "قرار الإدارة",
        "ملاحظة الإدارة",
    ]
    ws.append(headers)

    header_font = Font(bold=True)
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    for i, app in enumerate(qs, start=1):
        a = app.applicant
        vac = app.achieved_pref.vacancy if app.achieved_pref else None

        ws.append([
            i,
            app.id,
            getattr(a, "full_name", "") or "",
            getattr(a, "national_id", "") or "",
            getattr(a, "sector", "") or "",
            getattr(a, "gender", "") or "",
            getattr(app.achieved_pref, "rank", "") if app.achieved_pref else "",
            getattr(vac, "school_name", "") if vac else "",
            getattr(vac, "ministry_no", "") if vac else "",
            getattr(vac, "stage", "") if vac else "",
            getattr(vac, "sector", "") if vac else "",
            getattr(vac, "gender", "") if vac else "",
            timezone.localtime(app.achieved_at).strftime("%Y-%m-%d %H:%M") if app.achieved_at else "",
            getattr(app.achieved_by, "username", "") if app.achieved_by else "",
            (app.admin_decision or "").strip(),
            (app.admin_note or "").strip(),
        ])

    widths = [5, 10, 28, 16, 18, 12, 14, 32, 14, 16, 18, 12, 18, 14, 14, 40]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    filename = f"nominations_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    resp = HttpResponse(
        bio.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# =========================================================
# Admin: Export Excel (Applications)
# =========================================================
@staff_member_required
def admin_export_excel_view(request):
    status, sector, gender = _admin_filters_from_request(request)

    qs0 = (
        Application.objects
        .select_related("applicant", "achieved_pref__vacancy")
        .prefetch_related("prefs", "prefs__vacancy")
        .order_by("-submitted_at", "-id")
    )
    qs = _apply_admin_filters(qs0, status, sector, gender)

    wb = Workbook()
    ws = wb.active
    ws.title = "Applications"

    headers = [
        "ID", "National ID", "Full Name", "Sector", "Gender",
        "Status", "Submitted At", "Fallback Choice",
        "Admin Decision", "Admin Note", "Admin Decided At", "Achieved Pref",
    ]
    for i in range(1, 11):
        headers.append(f"Pref {i}")
    ws.append(headers)

    header_font = Font(bold=True)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for app in qs:
        prefs = sorted(list(app.prefs.all()), key=lambda p: p.rank)

        pref_names: list[str] = []
        for p in prefs[:10]:
            v = p.vacancy
            pref_names.append(f"{v.school_name} ({v.stage})")
        while len(pref_names) < 10:
            pref_names.append("")

        achieved_text = ""
        if getattr(app, "achieved_pref", None) and getattr(app.achieved_pref, "vacancy", None):
            achieved_text = f"Pref#{app.achieved_pref.rank} - {app.achieved_pref.vacancy.school_name}"

        row = [
            app.id,
            app.applicant.national_id,
            app.applicant.full_name,
            app.applicant.sector,
            app.applicant.gender,
            app.status,
            app.submitted_at.strftime("%Y-%m-%d %H:%M") if app.submitted_at else "",
            getattr(app, "fallback_choice", "") or "",
            getattr(app, "admin_decision", "") or "",
            getattr(app, "admin_note", "") or "",
            app.admin_decided_at.strftime("%Y-%m-%d %H:%M") if getattr(app, "admin_decided_at", None) else "",
            achieved_text,
        ] + pref_names

        ws.append(row)

    for col in range(1, ws.max_column + 1):
        max_len = 10
        for rowi in range(1, ws.max_row + 1):
            value = ws.cell(row=rowi, column=col).value
            if value is None:
                continue
            max_len = max(max_len, len(str(value)))
        ws.column_dimensions[get_column_letter(col)].width = min(max_len + 2, 60)

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    filename = f"applications_export_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    resp = HttpResponse(
        bio.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# =========================================================
# Admin: Import Excel
# =========================================================
@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_import_view(request):
    form = ImportExcelForm(request.POST or None, request.FILES or None)
    result = {}

    if request.method == "POST" and form.is_valid():
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

        applicants_file = form.cleaned_data.get("applicants_file")
        schools_file = form.cleaned_data.get("schools_file")

        if applicants_file:
            path = os.path.join(settings.MEDIA_ROOT, f"applicants__{applicants_file.name}")
            with open(path, "wb+") as out:
                for chunk in applicants_file.chunks():
                    out.write(chunk)

            batch, res = import_applicants_xlsx(path)
            result["applicants"] = {"batch": batch.id, "created": res.created, "updated": res.updated, "skipped": res.skipped}
            messages.success(request, f"تم استيراد المتقدمين بنجاح (Batch #{batch.id})")

        if schools_file:
            path = os.path.join(settings.MEDIA_ROOT, f"schools__{schools_file.name}")
            with open(path, "wb+") as out:
                for chunk in schools_file.chunks():
                    out.write(chunk)

            batch, res = import_schools_xlsx(path)
            result["schools"] = {"batch": batch.id, "created": res.created, "updated": res.updated, "skipped": res.skipped}
            messages.success(request, f"تم استيراد المدارس بنجاح (Batch #{batch.id})")

    return render(request, "portal/admin_import.html", {"form": form, "result": result})


# =========================================================
# Admin: Non Applicants (who didn't apply)
# =========================================================
@staff_member_required
def admin_non_applicants_view(request):
    q = (request.GET.get("q") or "").strip()
    mode = (request.GET.get("mode") or "not_submitted").strip()  # none / not_submitted / started

    qs = Applicant.objects.filter(is_active=True)

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q)
            | Q(national_id__icontains=q)
            | Q(sector__icontains=q)
            | Q(mobile__icontains=q)
            | Q(current_school__icontains=q)
        )

    if mode == "none":
        qs = qs.filter(application__isnull=True)
    elif mode == "started":
        qs = qs.filter(application__confirmed_at__isnull=False).exclude(application__status="submitted")
    else:
        qs = qs.filter(Q(application__isnull=True) | ~Q(application__status="submitted"))

    qs = qs.order_by("-id")
    page_obj = _paginate(request, qs, per_page=50)

    total_active = Applicant.objects.filter(is_active=True).count()
    total_submitted = Applicant.objects.filter(is_active=True, application__status="submitted").count()
    total_not_submitted = Applicant.objects.filter(is_active=True).filter(
        Q(application__isnull=True) | ~Q(application__status="submitted")
    ).count()

    ctx = {
        "rows": page_obj,
        "q": q,
        "mode": mode,
        "total": qs.count(),
        "kpi": {"active": total_active, "submitted": total_submitted, "not_submitted": total_not_submitted},
    }
    return render(request, "portal/admin_non_applicants.html", ctx)


@staff_member_required
def admin_non_applicants_csv_view(request):
    q = (request.GET.get("q") or "").strip()
    mode = (request.GET.get("mode") or "not_submitted").strip()

    qs = Applicant.objects.filter(is_active=True)

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q)
            | Q(national_id__icontains=q)
            | Q(sector__icontains=q)
            | Q(mobile__icontains=q)
            | Q(current_school__icontains=q)
        )

    if mode == "none":
        qs = qs.filter(application__isnull=True)
    elif mode == "started":
        qs = qs.filter(application__confirmed_at__isnull=False).exclude(application__status="submitted")
    else:
        qs = qs.filter(Q(application__isnull=True) | ~Q(application__status="submitted"))

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="non_applicants.csv"'
    resp.write("\ufeff")

    w = csv.writer(resp)
    w.writerow(["#", "الاسم", "السجل", "الجوال", "القطاع", "الجنس", "المدرسة الحالية", "لديه طلب؟", "حالة الطلب"])

    for i, a in enumerate(qs.order_by("-id"), start=1):
        app = Application.objects.filter(applicant=a).order_by("-id").first()
        has_app = "نعم" if app else "لا"
        status = getattr(app, "status", "") if app else ""
        w.writerow([i, a.full_name, a.national_id, a.mobile, a.sector, a.gender, a.current_school, has_app, status])

    return resp