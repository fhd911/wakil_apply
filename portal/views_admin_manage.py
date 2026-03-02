# portal/views_admin_manage.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms_admin import ApplicantAdminForm, VacancyAdminForm
from .models import Applicant, SchoolVacancy, Application


def _paginate(request, qs, per_page=30):
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page") or 1
    return paginator.get_page(page_number)


# =========================
# Applicants (المتقدمين)
# =========================
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
        {
            "rows": page_obj,
            "q": q,
            "status": status,
            "total": qs.count(),
        },
    )


@staff_member_required
def admin_applicants_create(request):
    form = ApplicantAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة المتقدم.")
        return redirect("portal:admin_applicants_list")

    return render(
        request,
        "portal/admin_applicants_form.html",
        {"form": form, "mode": "create"},
    )


@staff_member_required
def admin_applicants_edit(request, pk: int):
    obj = get_object_or_404(Applicant, pk=pk)
    form = ApplicantAdminForm(request.POST or None, instance=obj)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديل.")
        return redirect("portal:admin_applicants_list")

    # معلومات مفيدة (بدون تعقيد)
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
    # حذف نهائي: superuser فقط
    if not request.user.is_superuser:
        messages.error(request, "غير مصرح بالحذف النهائي. استخدم التعطيل.")
        return redirect("portal:admin_applicants_list")

    obj = get_object_or_404(Applicant, pk=pk)

    # حماية إضافية: إذا له طلبات، الأفضل منع الحذف (حتى لا تخسر السجل)
    if Application.objects.filter(applicant=obj).exists():
        messages.error(request, "لا يمكن الحذف النهائي: المتقدم لديه طلبات مرتبطة. استخدم التعطيل بدلًا من ذلك.")
        return redirect("portal:admin_applicants_list")

    obj.delete()
    messages.success(request, "تم حذف المتقدم نهائيًا.")
    return redirect("portal:admin_applicants_list")


# =========================
# Vacancies / Schools (الشواغر)
# =========================
@staff_member_required
def admin_vacancies_list(request):
    q = (request.GET.get("q") or "").strip()
    open_state = (request.GET.get("open") or "").strip()  # open / closed / all
    gender = (request.GET.get("gender") or "").strip()
    sector = (request.GET.get("sector") or "").strip()

    qs = SchoolVacancy.objects.all().order_by("-id")

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
        {
            "rows": page_obj,
            "q": q,
            "open": open_state,
            "gender": gender,
            "sector": sector,
            "total": qs.count(),
        },
    )


@staff_member_required
def admin_vacancies_create(request):
    form = VacancyAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الشاغر/المدرسة.")
        return redirect("portal:admin_vacancies_list")

    return render(
        request,
        "portal/admin_vacancies_form.html",
        {"form": form, "mode": "create"},
    )


@staff_member_required
def admin_vacancies_edit(request, pk: int):
    obj = get_object_or_404(SchoolVacancy, pk=pk)
    form = VacancyAdminForm(request.POST or None, instance=obj)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التعديل.")
        return redirect("portal:admin_vacancies_list")

    return render(
        request,
        "portal/admin_vacancies_form.html",
        {"form": form, "mode": "edit", "obj": obj},
    )


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

    # حماية إضافية: منع الحذف إذا فيه رغبات مرتبطة
    if obj.applicationpreference_set.exists():
        messages.error(request, "لا يمكن الحذف النهائي: يوجد رغبات مرتبطة بهذا الشاغر. استخدم (إغلاق) بدلًا من ذلك.")
        return redirect("portal:admin_vacancies_list")

    obj.delete()
    messages.success(request, "تم حذف الشاغر نهائيًا.")
    return redirect("portal:admin_vacancies_list")