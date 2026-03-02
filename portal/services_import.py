from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from openpyxl import load_workbook

from .models import Applicant, SchoolVacancy, ImportBatch


# =========================
# Result Object
# =========================
@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0


# =========================
# Normalizers (مهم جداً)
# =========================
def norm_text(s: str) -> str:
    s = (s or "").strip()
    s = " ".join(s.split())  # إزالة المسافات الزائدة
    return s


def norm_gender(g: str) -> str:
    g = norm_text(g)
    mapping = {
        # ذكور / أولاد
        "ذكور": "بنين",
        "ذكر": "بنين",
        "اولاد": "بنين",
        "أولاد": "بنين",
        "بنين": "بنين",
        # إناث / بنات
        "إناث": "بنات",
        "اناث": "بنات",
        "أناث": "بنات",
        "انثى": "بنات",
        "بنات": "بنات",
    }
    return mapping.get(g, g)


def _to_int(v) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


# =========================
# Import Applicants (A..I)
# =========================
def import_applicants_xlsx(path: str) -> Tuple[ImportBatch, ImportResult]:
    wb = load_workbook(path)
    ws = wb.active

    batch = ImportBatch.objects.create(kind="applicants", file_name=path)
    res = ImportResult()

    for row in ws.iter_rows(min_row=2, values_only=True):
        # A..I
        full_name = norm_text(row[0] or "")
        national_id = norm_text(str(row[1] or ""))
        mobile = norm_text(str(row[2] or ""))
        gender = norm_gender(row[3] or "")
        current_job = norm_text(row[4] or "")
        sector = norm_text(row[5] or "")
        rank = norm_text(row[6] or "")
        start_date = norm_text(str(row[7] or ""))
        current_school = norm_text(row[8] or "")

        if not national_id:
            res.skipped += 1
            continue

        _, was_created = Applicant.objects.update_or_create(
            national_id=national_id,
            defaults=dict(
                full_name=full_name,
                mobile=mobile,
                gender=gender,
                current_job=current_job,
                sector=sector,
                rank=rank,
                start_date=start_date,
                current_school=current_school,
                batch=batch,
                is_active=True,
            ),
        )
        if was_created:
            res.created += 1
        else:
            res.updated += 1

    return batch, res


# =========================
# Import Schools/Vacancies (A..R)
# =========================
def import_schools_xlsx(path: str) -> Tuple[ImportBatch, ImportResult]:
    wb = load_workbook(path)
    ws = wb.active

    batch = ImportBatch.objects.create(kind="schools", file_name=path)
    res = ImportResult()

    for row in ws.iter_rows(min_row=2, values_only=True):
        # A..R (0..17)
        ministry_no = norm_text(str(row[0] or ""))
        school_name = norm_text(row[1] or "")
        stage = norm_text(row[2] or "")
        sector = norm_text(row[3] or "")
        establishment_status = norm_text(row[4] or "")
        gender = norm_gender(row[5] or "")
        education_type = norm_text(row[6] or "")
        manager_national_id = norm_text(str(row[7] or ""))
        manager_name = norm_text(row[8] or "")

        students_total = _to_int(row[9])
        classes_total = _to_int(row[10])
        students_metric = _to_int(row[11])
        class_metric = _to_int(row[12])
        stage_code = norm_text(str(row[13] or ""))
        stage_metric = _to_int(row[14])

        deputy_staff = _to_int(row[15])
        deputy_existing = _to_int(row[16])
        deputy_need = _to_int(row[17])

        if not school_name:
            res.skipped += 1
            continue

        # مفتاح تحديث: الرقم الوزاري إن وجد، وإلا اسم المدرسة
        key = ministry_no or school_name

        _, was_created = SchoolVacancy.objects.update_or_create(
            ministry_no=key,
            defaults=dict(
                ministry_no=key,
                school_name=school_name,
                stage=stage,
                sector=sector,
                establishment_status=establishment_status,
                gender=gender,
                education_type=education_type,
                manager_national_id=manager_national_id,
                manager_name=manager_name,
                students_total=students_total,
                classes_total=classes_total,
                students_metric=students_metric,
                class_metric=class_metric,
                stage_code=stage_code,
                stage_metric=stage_metric,
                deputy_staff=deputy_staff,
                deputy_existing=deputy_existing,
                deputy_need=deputy_need,
                is_open=True,
                batch=batch,
            ),
        )
        if was_created:
            res.created += 1
        else:
            res.updated += 1

    return batch, res