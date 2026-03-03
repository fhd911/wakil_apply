from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


# =========================
# Abstract mixin: timestamps
# =========================
class TimeStampedModel(models.Model):
    """حقول عامة للتتبع (مفيدة للطباعة والتقارير)."""
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class ImportBatch(TimeStampedModel):
    kind = models.CharField(
        max_length=20,
        choices=[("applicants", "Applicants"), ("schools", "Schools")],
    )
    file_name = models.CharField(max_length=255, blank=True, default="")

    def __str__(self) -> str:
        return f"{self.kind} #{self.id}"


class Applicant(TimeStampedModel):
    # ملف المتقدمين (A..I) — الإدارة ترى الكل، المتقدم يرى B-C-D فقط
    full_name = models.CharField(max_length=255, blank=True, default="")       # A
    national_id = models.CharField(max_length=20, unique=True)                 # B
    mobile = models.CharField(max_length=30, blank=True, default="")           # C
    gender = models.CharField(max_length=10, blank=True, default="")           # D
    current_job = models.CharField(max_length=255, blank=True, default="")     # E
    sector = models.CharField(max_length=255, blank=True, default="")          # F
    rank = models.CharField(max_length=100, blank=True, default="")            # G
    start_date = models.CharField(max_length=50, blank=True, default="")       # H
    current_school = models.CharField(max_length=255, blank=True, default="")  # I

    is_active = models.BooleanField(default=True)
    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["national_id"]),
            models.Index(fields=["sector", "gender"]),
            models.Index(fields=["full_name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.national_id} - {self.full_name}".strip()


class SchoolVacancy(TimeStampedModel):
    # ملف المدارس/الشواغر (A..R)
    ministry_no = models.CharField(max_length=50, blank=True, default="")      # A
    school_name = models.CharField(max_length=255)                             # B
    stage = models.CharField(max_length=100, blank=True, default="")           # C
    sector = models.CharField(max_length=255, blank=True, default="")          # D
    establishment_status = models.CharField(max_length=100, blank=True, default="")  # E
    gender = models.CharField(max_length=10, blank=True, default="")           # F
    education_type = models.CharField(max_length=100, blank=True, default="")  # G
    manager_national_id = models.CharField(max_length=20, blank=True, default="")    # H
    manager_name = models.CharField(max_length=255, blank=True, default="")          # I

    students_total = models.IntegerField(default=0)                            # J
    classes_total = models.IntegerField(default=0)                             # K
    students_metric = models.IntegerField(default=0)                           # L
    class_metric = models.IntegerField(default=0)                              # M
    stage_code = models.CharField(max_length=50, blank=True, default="")       # N
    stage_metric = models.IntegerField(default=0)                              # O

    deputy_staff = models.IntegerField(default=0)                              # P
    deputy_existing = models.IntegerField(default=0)                           # Q
    deputy_need = models.IntegerField(default=0)                               # R (الاحتياج وكيل)

    is_open = models.BooleanField(default=True)
    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["sector", "gender"]),
            models.Index(fields=["school_name"]),
            models.Index(fields=["ministry_no"]),
            models.Index(fields=["deputy_need"]),
            models.Index(fields=["is_open"]),
            models.Index(fields=["is_open", "sector", "gender"]),
        ]

    def __str__(self) -> str:
        return self.school_name


class Application(TimeStampedModel):
    STATUS = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("returned", "Returned"),   # للتوافق
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    FALLBACK = [
        ("admin_assign", "توجيه من الإدارة"),
        ("stay_current", "البقاء في المدرسة الحالية"),
    ]

    # قرار الإدارة (منفصل عن status)
    ADMIN_DECISION = [
        ("", "—"),
        ("approved", "معتمد"),
        ("rejected", "مرفوض"),
        ("returned", "مُعاد للتعديل"),
    ]

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    fallback_choice = models.CharField(max_length=20, choices=FALLBACK, blank=True, default="")

    confirmed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    locked = models.BooleanField(default=False)

    # ✅ حقول قرارات الإدارة
    admin_decision = models.CharField(
        max_length=20,
        choices=ADMIN_DECISION,
        blank=True,
        default="",
    )
    admin_note = models.TextField(blank=True, default="")
    admin_decided_at = models.DateTimeField(null=True, blank=True)
    admin_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wakil_admin_decisions",
    )

    # ✅ الرغبة المتحققة — الترشيح النهائي
    achieved_pref = models.ForeignKey(
        "ApplicationPreference",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="achieved_for_apps",
    )
    achieved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    achieved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wakil_achieved_choices",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["admin_decision"]),
            models.Index(fields=["submitted_at"]),
            models.Index(fields=["achieved_at"]),
            models.Index(fields=["admin_decided_at"]),
            models.Index(fields=["admin_decision", "achieved_at"]),
        ]
        constraints = [
            # ✅ إذا تحقق ترشيح نهائي achieved_pref لازم يكون قرار الإدارة approved
            models.CheckConstraint(
                name="achieved_requires_admin_approved",
                condition=Q(achieved_pref__isnull=True) | Q(admin_decision="approved"),
            ),
        ]

    def __str__(self) -> str:
        return f"طلب {self.id} - {self.applicant.national_id}"

    # =========================
    # Integrity: ensure achieved_at is set when achieved_pref exists
    # =========================
    def save(self, *args, **kwargs):
        # إذا تم وضع achieved_pref ولم يتم تحديد achieved_at → عيّنه تلقائيًا
        if self.achieved_pref_id and not self.achieved_at:
            self.achieved_at = timezone.now()

        # إذا تم إزالة achieved_pref → نظف بيانات الترشيح النهائي
        if not self.achieved_pref_id:
            self.achieved_at = None
            self.achieved_by = None

        super().save(*args, **kwargs)

    # =========================
    # Helpers for reports
    # =========================
    @property
    def is_nominated_final(self) -> bool:
        """مرشح نهائيًا = لديه achieved_pref"""
        return self.achieved_pref_id is not None

    @property
    def achieved_rank(self) -> int | None:
        return getattr(self.achieved_pref, "rank", None) if self.achieved_pref else None

    @property
    def achieved_school_name(self) -> str:
        if not self.achieved_pref:
            return ""
        v = getattr(self.achieved_pref, "vacancy", None)
        return getattr(v, "school_name", "") if v else ""

    @property
    def achieved_sector(self) -> str:
        if not self.achieved_pref:
            return ""
        v = getattr(self.achieved_pref, "vacancy", None)
        return getattr(v, "sector", "") if v else ""

    @property
    def achieved_gender(self) -> str:
        if not self.achieved_pref:
            return ""
        v = getattr(self.achieved_pref, "vacancy", None)
        return getattr(v, "gender", "") if v else ""


class ApplicationPreference(TimeStampedModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="prefs")
    vacancy = models.ForeignKey(SchoolVacancy, on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["application", "rank"], name="uniq_app_rank"),
            models.UniqueConstraint(fields=["application", "vacancy"], name="uniq_app_vacancy"),
        ]
        ordering = ["rank"]
        indexes = [
            models.Index(fields=["rank"]),
            models.Index(fields=["vacancy"]),
            models.Index(fields=["application", "rank"]),
        ]

    def __str__(self) -> str:
        return f"App#{self.application_id} Pref#{self.rank}"