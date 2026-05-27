from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Organization, OrganizationMembership


class UserSerializer(serializers.ModelSerializer):
    org_id = serializers.SerializerMethodField()
    org_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'org_id', 'org_name', 'role']

    def _get_membership(self, obj):
        try:
            return obj.memberships.select_related('org').first()
        except Exception:
            return None

    def get_org_id(self, obj):
        m = self._get_membership(obj)
        return str(m.org.id) if m else None

    def get_org_name(self, obj):
        m = self._get_membership(obj)
        return m.org.name if m else None

    def get_role(self, obj):
        m = self._get_membership(obj)
        return m.role if m else None


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'created_at', 'plant_lookup', 'cost_center_lookup']
