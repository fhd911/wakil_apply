from __future__ import annotations

from django import forms


class ImportExcelForm(forms.Form):
    IMPORT_MODE_CHOICES = [
        ("sync", "إضافة الجديد + تحديث الموجود"),
        ("create_only", "إضافة الجديد فقط"),
        ("update_only", "تحديث الموجود فقط"),
    ]

    applicants_file = forms.FileField(
        required=False,
        label="ملف المتقدمين (Applicants)",
    )
    schools_file = forms.FileField(
        required=False,
        label="ملف المدارس/الشواغر (Schools)",
    )
    import_mode = forms.ChoiceField(
        required=False,
        choices=IMPORT_MODE_CHOICES,
        initial="sync",
        label="وضع الاستيراد",
    )

    def clean(self):
        data = super().clean()

        a = data.get("applicants_file")
        s = data.get("schools_file")
        mode = (data.get("import_mode") or "sync").strip()

        if not a and not s:
            raise forms.ValidationError(
                "ارفع ملفًا واحدًا على الأقل (المتقدمين أو المدارس)."
            )

        for f in [a, s]:
            if f and not f.name.lower().endswith((".xlsx", ".xlsm")):
                raise forms.ValidationError(
                    "يجب أن يكون الملف بصيغة Excel (.xlsx أو .xlsm)."
                )

        allowed_modes = {"sync", "create_only", "update_only"}
        if mode not in allowed_modes:
            data["import_mode"] = "sync"

        return data