from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


# =========================
# Abstract mixin: timestamps
# =========================
class TimeStampedModel(models.Model):
    """حقول عامة للتتبع."""
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


# =========================
# Portal Window (Open/Close + Phase)
# =========================
class PortalWindow(TimeStampedModel):
    """
    ضابط عام لفتح/إغلاق التقديم:
    - إغلاق/فتح يدوي (is_enabled)
    - أو نافذة زمنية opens_at / closes_at
    - مرحلة البوابة:
        * closed
        * official_only
        * new_only
        * all
    """

    PHASE_CLOSED = "closed"
    PHASE_OFFICIAL_ONLY = "official_only"
    PHASE_NEW_ONLY = "new_only"
    PHASE_ALL = "all"

    PHASES = [
        (PHASE_CLOSED, "مغلق"),
        (PHASE_OFFICIAL_ONLY, "الوكلاء الرسميون فقط"),
        (PHASE_NEW_ONLY, "المتقدمون الجدد فقط"),
        (PHASE_ALL, "الجميع (الوكلاء الرسميون + المتقدمون الجدد)"),
    ]

    is_enabled = models.BooleanField(default=True)

    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    phase = models.CharField(
        max_length=20,
        choices=PHASES,
        default=PHASE_CLOSED,
        db_index=True,
    )

    closed_message = models.CharField(
        max_length=255,
        blank=True,
        default="التقديم مغلق حالياً.",
    )

    official_only_message = models.CharField(
        max_length=255,
        blank=True,
        default="التقديم متاح حالياً للوكلاء الرسميين فقط.",
    )

    new_only_message = models.CharField(
        max_length=255,
        blank=True,
        default="التقديم متاح حالياً للمتقدمين الجدد فقط.",
    )

    all_message = models.CharField(
        max_length=255,
        blank=True,
        default="التقديم متاح حالياً للجميع.",
    )

    def is_within_time_window(self) -> bool:
        now = timezone.now()
        if self.opens_at and now < self.opens_at:
            return False
        if self.closes_at and now > self.closes_at:
            return False
        return True

    def is_open_now(self) -> bool:
        if not self.is_enabled:
            return False

        if self.phase == self.PHASE_CLOSED:
            return False

        return self.is_within_time_window()

    def allows_official(self) -> bool:
        return self.phase in {self.PHASE_OFFICIAL_ONLY, self.PHASE_ALL}

    def allows_new(self) -> bool:
        return self.phase in {self.PHASE_NEW_ONLY, self.PHASE_ALL}

    @classmethod
    def get(cls) -> "PortalWindow":
        obj = cls.objects.order_by("-id").first()
        if not obj:
            obj = cls.objects.create(is_enabled=True, phase=cls.PHASE_CLOSED)
        return obj

    def __str__(self) -> str:
        return f"Portal Window ({self.phase})"


class ImportBatch(TimeStampedModel):
    kind = models.CharField(
        max_length=20,
        choices=[("applicants", "Applicants"), ("schools", "Schools")],
    )
    file_name = models.CharField(max_length=255, blank=True, default="")

    def __str__(self) -> str:
        return f"{self.kind} #{self.id}"


class Applicant(TimeStampedModel):
    # ملف المتقدمين
    full_name = models.CharField(max_length=255, blank=True, default="")
    national_id = models.CharField(max_length=20, unique=True)
    mobile = models.CharField(max_length=30, blank=True, default="")
    gender = models.CharField(max_length=10, blank=True, default="")
    current_job = models.CharField(max_length=255, blank=True, default="")
    sector = models.CharField(max_length=255, blank=True, default="")
    rank = models.CharField(max_length=100, blank=True, default="")
    start_date = models.CharField(max_length=50, blank=True, default="")
    current_school = models.CharField(max_length=255, blank=True, default="")

    is_active = models.BooleanField(default=True)
    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["national_id"]),
            models.Index(fields=["sector", "gender"]),
            models.Index(fields=["full_name"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["current_job"]),
        ]

    def __str__(self) -> str:
        return f"{self.national_id} - {self.full_name}".strip()

    @property
    def is_official_agent(self) -> bool:
        """
        يعتمد على حقل العمل الحالي القادم من ملف الإكسل.
        أي نص يحتوي (وكيل) أو (وكيلة) يعتبر وكيلًا رسميًا.
        """
        txt = (self.current_job or "").strip()
        return ("وكيل" in txt) or ("وكيلة" in txt)

    @property
    def is_new_applicant(self) -> bool:
        return not self.is_official_agent


class SchoolVacancy(TimeStampedModel):
    # ملف المدارس/الشواغر
    ministry_no = models.CharField(max_length=50, blank=True, default="")
    school_name = models.CharField(max_length=255)
    stage = models.CharField(max_length=100, blank=True, default="")
    sector = models.CharField(max_length=255, blank=True, default="")
    establishment_status = models.CharField(max_length=100, blank=True, default="")
    gender = models.CharField(max_length=10, blank=True, default="")
    education_type = models.CharField(max_length=100, blank=True, default="")
    manager_national_id = models.CharField(max_length=20, blank=True, default="")
    manager_name = models.CharField(max_length=255, blank=True, default="")

    students_total = models.IntegerField(default=0)
    classes_total = models.IntegerField(default=0)
    students_metric = models.IntegerField(default=0)
    class_metric = models.IntegerField(default=0)
    stage_code = models.CharField(max_length=50, blank=True, default="")
    stage_metric = models.IntegerField(default=0)

    deputy_staff = models.IntegerField(default=0)
    deputy_existing = models.IntegerField(default=0)
    deputy_need = models.IntegerField(default=0)

    is_open = models.BooleanField(default=True)

    # يحجز الشاغر عند اعتماد وكيل رسمي عليه
    reserved_application = models.ForeignKey(
        "Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reserved_vacancies",
    )
    reserved_at = models.DateTimeField(null=True, blank=True)

    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["sector", "gender"]),
            models.Index(fields=["school_name"]),
            models.Index(fields=["ministry_no"]),
            models.Index(fields=["deputy_need"]),
            models.Index(fields=["is_open"]),
            models.Index(fields=["is_open", "sector", "gender"]),
            models.Index(fields=["reserved_application"]),
        ]

    def __str__(self) -> str:
        return self.school_name

    @property
    def is_reserved(self) -> bool:
        return self.reserved_application_id is not None

    @property
    def is_available_for_application(self) -> bool:
        return self.is_open and not self.is_reserved and self.deputy_need != 0


class Application(TimeStampedModel):
    STATUS = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("returned", "Returned"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    FALLBACK = [
        ("admin_assign", "توجيه من الإدارة"),
        ("stay_current", "البقاء في المدرسة الحالية"),
    ]

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
            models.CheckConstraint(
                name="achieved_requires_admin_approved",
                condition=Q(achieved_pref__isnull=True) | Q(admin_decision="approved"),
            ),
        ]

    def __str__(self) -> str:
        return f"طلب {self.id} - {self.applicant.national_id}"

    def save(self, *args, **kwargs):
        if self.achieved_pref_id and not self.achieved_at:
            self.achieved_at = timezone.now()

        if not self.achieved_pref_id:
            self.achieved_at = None
            self.achieved_by = None

        super().save(*args, **kwargs)

    @property
    def is_nominated_final(self) -> bool:
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