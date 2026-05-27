from django.contrib import admin
from .models import Organization, OrganizationMembership

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    search_fields = ['name', 'slug']

@admin.register(OrganizationMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'org', 'role', 'created_at']
    list_filter = ['role', 'org']
