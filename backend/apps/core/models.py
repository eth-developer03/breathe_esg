import uuid
from django.db import models
from django.contrib.auth.models import User


class Organization(models.Model):
    """
    Root multi-tenancy entity. Every piece of data is scoped to an org.
    We use slug for URL-safe references and client-facing identifiers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # plant_lookup: maps plant codes to human-readable names/locations.
    # Stored at the org level because codes like "1000" or "PLNT_MCR" are
    # meaningless without context and differ per client.
    plant_lookup = models.JSONField(default=dict, blank=True)
    # cost_center_lookup: maps SAP/Concur cost centers to departments/facilities
    cost_center_lookup = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def resolve_plant(self, code: str) -> str:
        return self.plant_lookup.get(str(code), code)

    def resolve_cost_center(self, code: str) -> str:
        return self.cost_center_lookup.get(str(code), code)


class OrganizationMembership(models.Model):
    ROLE_ADMIN = 'admin'
    ROLE_ANALYST = 'analyst'
    ROLE_VIEWER = 'viewer'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_ANALYST, 'Analyst'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('org', 'user')

    def __str__(self):
        return f"{self.user.username} @ {self.org.name} ({self.role})"
