"""
Management command: seed demo org, user, and data sources.
Run: python manage.py seed_demo
Creates:
  - Org: "Acme Manufacturing Ltd"
  - User: admin / admin123 (admin role)
  - User: analyst / analyst123 (analyst role)
  - 3 DataSources (SAP, UTILITY, TRAVEL)
  - Loads emission factors fixture
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.management import call_command
from apps.core.models import Organization, OrganizationMembership
from apps.ingestion.models import DataSource


class Command(BaseCommand):
    help = 'Seed demo organization and users'

    def handle(self, *args, **options):
        self.stdout.write('Loading emission factors...')
        call_command('loaddata', 'emission_factors')

        org, created = Organization.objects.get_or_create(
            slug='acme-manufacturing',
            defaults={
                'name': 'Acme Manufacturing Ltd',
                'plant_lookup': {
                    '1000': 'Manchester Plant (UK)',
                    '2000': 'Birmingham Distribution Centre',
                    '3000': 'Leeds Warehouse',
                    'PLNT_MAN': 'Manchester Plant (UK)',
                    'PLNT_BHM': 'Birmingham Distribution Centre',
                },
                'cost_center_lookup': {
                    'CC-OPS': 'Operations',
                    'CC-SALES': 'Sales & Marketing',
                    'CC-ADMIN': 'Administration',
                    'CC-EXEC': 'Executive',
                    'CC-IT': 'Information Technology',
                },
            }
        )
        if created:
            self.stdout.write(f'Created org: {org.name}')

        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@acme.example', 'is_staff': True, 'is_superuser': True,
                      'first_name': 'Admin', 'last_name': 'User'}
        )
        admin_user.set_password('admin123')
        admin_user.save()
        OrganizationMembership.objects.get_or_create(
            org=org, user=admin_user,
            defaults={'role': OrganizationMembership.ROLE_ADMIN}
        )

        analyst_user, _ = User.objects.get_or_create(
            username='analyst',
            defaults={'email': 'analyst@acme.example', 'first_name': 'Sarah', 'last_name': 'Chen'}
        )
        analyst_user.set_password('analyst123')
        analyst_user.save()
        OrganizationMembership.objects.get_or_create(
            org=org, user=analyst_user,
            defaults={'role': OrganizationMembership.ROLE_ANALYST}
        )

        DataSource.objects.get_or_create(
            org=org, source_type=DataSource.SOURCE_SAP,
            defaults={
                'name': 'SAP MB51 — Fuel Movements',
                'description': (
                    'Tab-delimited export from SAP transaction MB51 (Material Document List). '
                    'Covers fuel goods issues from plants 1000 and 2000. '
                    'Movement types 201 (cost centre issue) and 261 (production order issue).'
                ),
                'config': {
                    'plant_filter': ['1000', '2000', '3000'],
                    'movement_types': ['201', '261', '291'],
                    'encoding': 'utf-8',
                },
                'created_by': admin_user,
            }
        )

        DataSource.objects.get_or_create(
            org=org, source_type=DataSource.SOURCE_UTILITY,
            defaults={
                'name': 'National Grid — Electricity Portal Export',
                'description': (
                    'CSV downloaded from National Grid customer portal. '
                    'Covers meters MTR-A102, MTR-B205, MTR-C301 across the Manchester site. '
                    'Billing periods typically run 18th to 17th of month.'
                ),
                'config': {
                    'account_numbers': ['ACC-78234', 'ACC-78235'],
                    'utility_name': 'National Grid',
                    'country': 'GB',
                },
                'created_by': admin_user,
            }
        )

        DataSource.objects.get_or_create(
            org=org, source_type=DataSource.SOURCE_TRAVEL,
            defaults={
                'name': 'Concur — Expense Report Export',
                'description': (
                    'CSV from SAP Concur "Analyze" report builder, custom template "ESG Travel Report". '
                    'Covers all approved expense reports with travel expense types. '
                    'Fields: Report Name, Employee ID, Department, Expense Type, '
                    'Transaction Date, Vendor, Amount USD, Flight From/To, Class, Nights.'
                ),
                'config': {
                    'cost_centers': ['CC-OPS', 'CC-SALES', 'CC-ADMIN', 'CC-EXEC', 'CC-IT'],
                    'expense_types': ['Airfare', 'Hotel', 'Car Rental', 'Taxi/Rideshare', 'Train'],
                },
                'created_by': admin_user,
            }
        )

        self.stdout.write(self.style.SUCCESS(
            '\nDemo data seeded successfully.\n'
            '  Admin login:   username=admin    password=admin123\n'
            '  Analyst login: username=analyst  password=analyst123\n'
            '  Upload sample_data/ files via the Upload page to populate records.\n'
        ))
