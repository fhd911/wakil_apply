from __future__ import annotations
from django import forms


class ImportExcelForm(forms.Form):
    applicants_file = forms.FileField(required=False, label="ملف المتقدمين (Applicants)")
    schools_file = forms.FileField(required=False, label="ملف المدارس/الشواغر (Schools)")

    def clean(self):
        data = super().clean()
        a = data.get("applicants_file")
        s = data.get("schools_file")
        if not a and not s:
            raise forms.ValidationError("ارفع ملفًا واحدًا على الأقل (المتقدمين أو المدارس).")
        for f in [a, s]:
            if f and not f.name.lower().endswith((".xlsx", ".xlsm")):
                raise forms.ValidationError("يجب أن يكون الملف بصيغة Excel (.xlsx أو .xlsm).")
        return data