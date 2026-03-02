# portal/forms_admin.py
from __future__ import annotations

from django import forms

from .models import Applicant, SchoolVacancy


class ApplicantAdminForm(forms.ModelForm):
    class Meta:
        model = Applicant
        fields = [
            "full_name",
            "national_id",
            "mobile",
            "gender",
            "current_job",
            "sector",
            "rank",
            "start_date",
            "current_school",
            "is_active",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "inp", "placeholder": "الاسم الكامل"}),
            "national_id": forms.TextInput(attrs={"class": "inp", "placeholder": "السجل المدني"}),
            "mobile": forms.TextInput(attrs={"class": "inp", "placeholder": "الجوال"}),
            "gender": forms.TextInput(attrs={"class": "inp", "placeholder": "بنين/بنات"}),
            "current_job": forms.TextInput(attrs={"class": "inp", "placeholder": "العمل الحالي"}),
            "sector": forms.TextInput(attrs={"class": "inp", "placeholder": "القطاع"}),
            "rank": forms.TextInput(attrs={"class": "inp", "placeholder": "الرتبة"}),
            "start_date": forms.TextInput(attrs={"class": "inp", "placeholder": "تاريخ المباشرة"}),
            "current_school": forms.TextInput(attrs={"class": "inp", "placeholder": "المدرسة الحالية"}),
        }


class VacancyAdminForm(forms.ModelForm):
    class Meta:
        model = SchoolVacancy
        fields = [
            "ministry_no",
            "school_name",
            "stage",
            "sector",
            "establishment_status",
            "gender",
            "education_type",
            "manager_national_id",
            "manager_name",
            "students_total",
            "classes_total",
            "students_metric",
            "class_metric",
            "stage_code",
            "stage_metric",
            "deputy_staff",
            "deputy_existing",
            "deputy_need",
            "is_open",
        ]
        widgets = {
            "ministry_no": forms.TextInput(attrs={"class": "inp", "placeholder": "رقم الوزارة"}),
            "school_name": forms.TextInput(attrs={"class": "inp", "placeholder": "اسم المدرسة"}),
            "stage": forms.TextInput(attrs={"class": "inp", "placeholder": "المرحلة"}),
            "sector": forms.TextInput(attrs={"class": "inp", "placeholder": "القطاع"}),
            "establishment_status": forms.TextInput(attrs={"class": "inp", "placeholder": "حالة المدرسة"}),
            "gender": forms.TextInput(attrs={"class": "inp", "placeholder": "بنين/بنات"}),
            "education_type": forms.TextInput(attrs={"class": "inp", "placeholder": "نوع التعليم"}),
            "manager_national_id": forms.TextInput(attrs={"class": "inp", "placeholder": "سجل المدير"}),
            "manager_name": forms.TextInput(attrs={"class": "inp", "placeholder": "اسم المدير"}),
            "stage_code": forms.TextInput(attrs={"class": "inp", "placeholder": "كود المرحلة"}),
        }