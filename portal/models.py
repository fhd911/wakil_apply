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


class ApplicantDataIssue(TimeStampedModel):
    """
    ملاحظة يرفعها المتقدم عند وجود معلومة غير صحيحة في بياناته.
    المتقدم لا يعدّل البيانات مباشرة، وإنما يرسل بلاغًا موثقًا للإدارة.
    """

    FIELD_FULL_NAME = "full_name"
    FIELD_MOBILE = "mobile"
    FIELD_GENDER = "gender"
    FIELD_RANK = "rank"
    FIELD_SECTOR = "sector"
    FIELD_CURRENT_JOB = "current_job"
    FIELD_CURRENT_SCHOOL = "current_school"
    FIELD_START_DATE = "start_date"
    FIELD_OTHER = "other"

    FIELD_CHOICES = [
        (FIELD_FULL_NAME, "الاسم الرباعي"),
        (FIELD_MOBILE, "رقم الجوال"),
        (FIELD_GENDER, "الجنس"),
        (FIELD_RANK, "الرتبة"),
        (FIELD_SECTOR, "القطاع"),
        (FIELD_CURRENT_JOB, "العمل الحالي"),
        (FIELD_CURRENT_SCHOOL, "المدرسة الحالية"),
        (FIELD_START_DATE, "تاريخ المباشرة"),
        (FIELD_OTHER, "أخرى"),
    ]

    BLOCKING_FIELDS = {
        FIELD_GENDER,
        FIELD_RANK,
        FIELD_SECTOR,
        FIELD_CURRENT_JOB,
        FIELD_CURRENT_SCHOOL,
        FIELD_START_DATE,
    }

    STATUS_PENDING = "pending"
    STATUS_ALLOWED = "allowed"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CORRECTED = "corrected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "قيد المراجعة"),
        (STATUS_ALLOWED, "لا تؤثر على التقديم / سُمح بالمتابعة"),
        (STATUS_ACCEPTED, "مقبولة"),
        (STATUS_REJECTED, "مرفوضة"),
        (STATUS_CORRECTED, "تم التصحيح"),
    ]

    applicant = models.ForeignKey(
        "Applicant",
        on_delete=models.CASCADE,
        related_name="data_issues",
        verbose_name="المتقدم",
    )
    application = models.ForeignKey(
        "Application",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_issues",
        verbose_name="الطلب",
    )

    field_name = models.CharField(
        "الحقل محل الملاحظة",
        max_length=40,
        choices=FIELD_CHOICES,
        db_index=True,
    )
    current_value = models.CharField(
        "القيمة الحالية وقت البلاغ",
        max_length=255,
        blank=True,
        default="",
    )
    proposed_value = models.CharField(
        "التصحيح المقترح",
        max_length=255,
        blank=True,
        default="",
    )
    note = models.TextField("وصف الملاحظة", blank=True, default="")

    is_blocking = models.BooleanField(
        "توقف المتابعة لحين المراجعة",
        default=False,
        db_index=True,
        help_text="تُفعّل للحقول المؤثرة في الشواغر أو المفاضلة مثل القطاع والجنس والمدرسة الحالية.",
    )

    # =====================================================
    # Protected completion window / حفظ حق الاستكمال
    # =====================================================
    protects_followup_right = models.BooleanField(
        "يحفظ حق الاستكمال",
        default=False,
        db_index=True,
        help_text=(
            "يُفعّل عندما يرفع المتقدم ملاحظة مؤثرة أثناء فترة التقديم؛ "
            "بحيث لا يتضرر إذا تأخرت مراجعة الإدارة إلى ما بعد إغلاق البوابة."
        ),
    )
    protected_at = models.DateTimeField(
        "وقت حفظ حق الاستكمال",
        null=True,
        blank=True,
        db_index=True,
    )
    followup_window_granted_at = models.DateTimeField(
        "وقت فتح مهلة الاستكمال الخاصة",
        null=True,
        blank=True,
        db_index=True,
    )
    followup_window_expires_at = models.DateTimeField(
        "نهاية مهلة الاستكمال الخاصة",
        null=True,
        blank=True,
        db_index=True,
    )
    followup_window_granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_applicant_data_issue_followup_windows",
        verbose_name="فتح مهلة الاستكمال بواسطة",
    )
    followup_window_note = models.TextField(
        "ملاحظة مهلة الاستكمال",
        blank=True,
        default="",
    )

    status = models.CharField(
        "حالة المراجعة",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    applicant_snapshot = models.JSONField(
        "لقطة بيانات المتقدم وقت البلاغ",
        default=dict,
        blank=True,
    )
    source_ip = models.GenericIPAddressField("عنوان IP", null=True, blank=True)
    user_agent = models.TextField("المتصفح", blank=True, default="")

    reviewed_at = models.DateTimeField("تاريخ المراجعة", null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applicant_data_issues",
        verbose_name="راجع بواسطة",
    )
    admin_note = models.TextField("ملاحظة الإدارة", blank=True, default="")

    class Meta:
        verbose_name = "ملاحظة بيانات"
        verbose_name_plural = "ملاحظات البيانات"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "is_blocking"]),
            models.Index(fields=["applicant", "status"]),
            models.Index(fields=["field_name", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["protects_followup_right", "status"]),
            models.Index(fields=["followup_window_expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_field_name_display()} - {self.applicant} - {self.get_status_display()}"

    @property
    def blocks_followup(self) -> bool:
        return self.status == self.STATUS_PENDING and self.is_blocking

    @property
    def has_active_followup_window(self) -> bool:
        if not self.followup_window_expires_at:
            return False
        if self.status not in {self.STATUS_ALLOWED, self.STATUS_CORRECTED, self.STATUS_REJECTED}:
            return False
        return timezone.now() <= self.followup_window_expires_at

    @property
    def followup_window_is_expired(self) -> bool:
        if not self.followup_window_expires_at:
            return False
        return timezone.now() > self.followup_window_expires_at

    @property
    def followup_window_label(self) -> str:
        if self.has_active_followup_window:
            return "مهلة استكمال خاصة نشطة"
        if self.followup_window_is_expired:
            return "انتهت مهلة الاستكمال الخاصة"
        if self.protects_followup_right and self.status == self.STATUS_PENDING:
            return "حق الاستكمال محفوظ بانتظار المراجعة"
        if self.protects_followup_right:
            return "حق الاستكمال محفوظ"
        return "—"


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


    # =====================================================
    # Submission acknowledgements / إثباتات الإرسال
    # =====================================================
    PREFERENCES_ACK_TEXT_V1 = (
        "أقرّ بأن اختياري وترتيبي للرغبات لا يعني استحقاق التوجيه عليها أو تحققها، "
        "ولا يترتب عليه أي التزام بتوجيهي إلى أي منها في حال وجود مرشحين أعلى درجة "
        "أو أحق في المفاضلة، وأن التوجيه النهائي يكون وفق المصلحة التعليمية واحتياج "
        "الإدارة والضوابط المعتمدة ونتائج المفاضلة، وفي حدود الرغبات المحددة."
    )

    NO_PREFERENCES_ACK_TEXT_V1 = (
        "أقرّ بأنني اطلعت على الشواغر المتاحة خلال فترة التقديم، وأرغب في إرسال طلبي "
        "دون اختيار أي رغبة، وأتحمل ما يترتب على ذلك من عدم دخولي في الترشيح على "
        "الشواغر المتاحة."
    )

    SUBMISSION_POLICY_VERSION_V1 = "v1"

    preferences_acknowledged = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="أقر بسياسة الرغبات",
    )
    preferences_ack_text = models.TextField(
        blank=True,
        default="",
        verbose_name="نص إقرار سياسة الرغبات",
    )
    preferences_ack_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت إقرار سياسة الرغبات",
    )

    no_preferences_acknowledged = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="أقر بالإرسال دون رغبات",
    )
    no_preferences_ack_text = models.TextField(
        blank=True,
        default="",
        verbose_name="نص إقرار الإرسال دون رغبات",
    )
    no_preferences_ack_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت إقرار الإرسال دون رغبات",
    )

    submitted_prefs_count = models.PositiveIntegerField(
        default=0,
        verbose_name="عدد الرغبات وقت الإرسال",
    )

    submission_policy_version = models.CharField(
        max_length=50,
        blank=True,
        default=SUBMISSION_POLICY_VERSION_V1,
        verbose_name="إصدار سياسة الإقرار",
    )

    submission_snapshot = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="لقطة الإرسال",
    )

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
            models.Index(fields=["preferences_acknowledged"]),
            models.Index(fields=["no_preferences_acknowledged"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="achieved_requires_admin_approved",
                condition=Q(achieved_pref__isnull=True) | Q(admin_decision="approved"),
            ),
        ]

    def __str__(self) -> str:
        return f"طلب {self.id} - {self.applicant.national_id}"



    @property
    def submitted_with_preferences(self) -> bool:
        return self.status == "submitted" and int(self.submitted_prefs_count or 0) > 0

    @property
    def submitted_without_preferences(self) -> bool:
        return self.status == "submitted" and int(self.submitted_prefs_count or 0) == 0

    def build_submission_snapshot(self) -> dict:
        """
        يبني لقطة إثبات لحظة الإرسال.
        يستدعى من submit_view بعد حفظ ApplicationPreference وقبل app.save النهائي.
        """
        prefs = []
        try:
            qs = self.prefs.select_related("vacancy").order_by("rank", "id")
            for pref in qs:
                vacancy = getattr(pref, "vacancy", None)
                prefs.append({
                    "rank": pref.rank,
                    "vacancy_id": getattr(vacancy, "id", None),
                    "school_name": getattr(vacancy, "school_name", "") if vacancy else "",
                    "ministry_no": getattr(vacancy, "ministry_no", "") if vacancy else "",
                    "stage": getattr(vacancy, "stage", "") if vacancy else "",
                    "sector": getattr(vacancy, "sector", "") if vacancy else "",
                    "gender": getattr(vacancy, "gender", "") if vacancy else "",
                })
        except Exception:
            prefs = []

        applicant = getattr(self, "applicant", None)
        submitted_at = self.submitted_at or timezone.now()

        return {
            "application_id": self.id,
            "status": self.status,
            "locked": bool(self.locked),
            "submitted_at": timezone.localtime(submitted_at).isoformat() if submitted_at else "",
            "submitted_prefs_count": len(prefs),
            "submitted_without_preferences": len(prefs) == 0,
            "submission_policy_version": self.submission_policy_version or self.SUBMISSION_POLICY_VERSION_V1,
            "preferences_acknowledged": bool(self.preferences_acknowledged),
            "preferences_ack_text": self.preferences_ack_text or "",
            "preferences_ack_at": timezone.localtime(self.preferences_ack_at).isoformat() if self.preferences_ack_at else "",
            "no_preferences_acknowledged": bool(self.no_preferences_acknowledged),
            "no_preferences_ack_text": self.no_preferences_ack_text or "",
            "no_preferences_ack_at": timezone.localtime(self.no_preferences_ack_at).isoformat() if self.no_preferences_ack_at else "",
            "applicant": {
                "id": getattr(applicant, "id", None),
                "full_name": getattr(applicant, "full_name", "") if applicant else "",
                "national_id": getattr(applicant, "national_id", "") if applicant else "",
                "mobile": getattr(applicant, "mobile", "") if applicant else "",
                "sector": getattr(applicant, "sector", "") if applicant else "",
                "gender": getattr(applicant, "gender", "") if applicant else "",
                "current_job": getattr(applicant, "current_job", "") if applicant else "",
                "current_school": getattr(applicant, "current_school", "") if applicant else "",
            },
            "preferences": prefs,
        }

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