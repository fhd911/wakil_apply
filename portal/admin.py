from django.contrib import admin
from .models import ImportBatch, Applicant, SchoolVacancy, Application, ApplicationPreference

admin.site.register(ImportBatch)
admin.site.register(Applicant)
admin.site.register(SchoolVacancy)
admin.site.register(Application)
admin.site.register(ApplicationPreference)