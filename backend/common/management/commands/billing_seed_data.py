"""Django management command to seed billing dummy data.

Creates sample Products, Plans, Access Entries, and Service Domains
for local development and testing. Uses ``get_or_create`` so it is
safe to run multiple times — existing records are skipped.

Usage::

    python manage.py billing_seed_data
    python manage.py billing_seed_data --clear   # wipe and re-seed
    python manage.py billing_seed_data --verbose  # show every creation

Options:

    ``--clear``    Delete all billing data before seeding (irreversible).
    ``--verbose``  Print one line per created record.
"""

import logging
from datetime import timedelta
from django.utils import timezone

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from billing.models import (
    Product,
    Plan,
    AccessEntry,
    ServiceDomain,
    Subscription,
    SubscriptionStatus,
    BillingCycle,
    AccessValueType,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# =============================================================================
# Seed Data Definitions
# =============================================================================
# Each product is defined with its plans, service domains, and per-plan
# access entries.  Add or modify products here to expand the seed data.
# =============================================================================


SEED_DATA = [
    # -------------------------------------------------------------------------
    # Satta Finance
    # -------------------------------------------------------------------------
    {
        "product": {
            "name": "Satta Finance",
            "slug": "finance",
            "description": (
                "Personal finance management — track expenses, manage budgets, "
                "generate financial reports, and connect bank accounts."
            ),
            "home_url": "https://finance.sattabase.tld",
        },
        "domains": [
            {
                "domain": "finance.sattabase.tld",
                "is_primary": True,
            },
        ],
        "plans": [
            {
                "name": "Free",
                "slug": "free",
                "description": "Basic finance tracking for individuals.",
                "price_cents": 0,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 0,
                "sort_order": 0,
                "is_featured": False,
                "features": {
                    "expense_tracking": "Basic",
                    "budget_categories": "3 categories",
                    "reports": "None",
                    "bank_accounts": "1 linked account",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "expense_tracking",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track income and expenses",
                    },
                    {
                        "key": "budget_categories",
                        "value": "3",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum budget categories",
                    },
                    {
                        "key": "reports",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Generate financial reports",
                    },
                    {
                        "key": "export_pdf",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "api_access",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access",
                    },
                    {
                        "key": "max_bank_accounts",
                        "value": "1",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum connected bank accounts",
                    },
                    {
                        "key": "max_team_members",
                        "value": "1",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum team collaborators",
                    },
                    {
                        "key": "priority_support",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Priority customer support",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "30",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Historical data retention in days",
                    },
                ],
            },
            {
                "name": "Standard",
                "slug": "standard",
                "description": "Full finance suite for power users.",
                "price_cents": 900,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 14,
                "sort_order": 1,
                "is_featured": True,
                "features": {
                    "expense_tracking": "Advanced",
                    "budget_categories": "Unlimited",
                    "reports": "Advanced",
                    "bank_accounts": "5 linked accounts",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "expense_tracking",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track income and expenses",
                    },
                    {
                        "key": "budget_categories",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited budget categories (0 = unlimited)",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Generate financial reports",
                    },
                    {
                        "key": "export_pdf",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "api_access",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access",
                    },
                    {
                        "key": "max_bank_accounts",
                        "value": "5",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum connected bank accounts",
                    },
                    {
                        "key": "max_team_members",
                        "value": "3",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum team collaborators",
                    },
                    {
                        "key": "priority_support",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Priority customer support",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "365",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Historical data retention in days",
                    },
                ],
            },
            {
                "name": "Pro",
                "slug": "pro",
                "description": "Enterprise finance for teams and businesses.",
                "price_cents": 2900,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 30,
                "sort_order": 2,
                "is_featured": False,
                "features": {
                    "expense_tracking": "Advanced + AI",
                    "budget_categories": "Unlimited",
                    "reports": "Advanced + AI insights",
                    "bank_accounts": "Unlimited",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "expense_tracking",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track income and expenses with AI categorization",
                    },
                    {
                        "key": "budget_categories",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited budget categories (0 = unlimited)",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Generate financial reports with AI insights",
                    },
                    {
                        "key": "export_pdf",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "api_access",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access with higher rate limits",
                    },
                    {
                        "key": "max_bank_accounts",
                        "value": "50",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum connected bank accounts",
                    },
                    {
                        "key": "max_team_members",
                        "value": "25",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum team collaborators",
                    },
                    {
                        "key": "priority_support",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Priority customer support",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited data retention (0 = forever)",
                    },
                    {
                        "key": "white_label",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "White-label reports with custom branding",
                    },
                    {
                        "key": "audit_log",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Full audit log of all financial actions",
                    },
                ],
            },
        ],
    },
    # -------------------------------------------------------------------------
    # Satta Analytics
    # -------------------------------------------------------------------------
    {
        "product": {
            "name": "Satta Analytics",
            "slug": "analytics",
            "description": (
                "Business analytics dashboard — track KPIs, build dashboards, "
                "and get real-time insights from your data sources."
            ),
            "home_url": "https://analytics.sattabase.tld",
        },
        "domains": [
            {
                "domain": "analytics.sattabase.tld",
                "is_primary": True,
            },
        ],
        "plans": [
            {
                "name": "Free",
                "slug": "free",
                "description": "Basic analytics for personal projects.",
                "price_cents": 0,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 0,
                "sort_order": 0,
                "is_featured": False,
                "features": {
                    "dashboards": "Up to 2",
                    "data_sources": "1",
                    "real_time": "No",
                    "data_retention": "7 days",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "reports",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Generate analytical reports",
                    },
                    {
                        "key": "real_time_data",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Real-time data streaming",
                    },
                    {
                        "key": "max_dashboards",
                        "value": "2",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of dashboards",
                    },
                    {
                        "key": "max_data_sources",
                        "value": "1",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum connected data sources",
                    },
                    {
                        "key": "api_access",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access",
                    },
                    {
                        "key": "export_csv",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export data as CSV",
                    },
                    {
                        "key": "export_pdf",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "team_collaboration",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Share dashboards with team members",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "7",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Historical data retention in days",
                    },
                ],
            },
            {
                "name": "Growth",
                "slug": "growth",
                "description": "Powerful analytics for growing businesses.",
                "price_cents": 1900,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 14,
                "sort_order": 1,
                "is_featured": True,
                "features": {
                    "dashboards": "Unlimited",
                    "data_sources": "10",
                    "real_time": "Yes",
                    "data_retention": "1 year",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Generate analytical reports",
                    },
                    {
                        "key": "real_time_data",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Real-time data streaming",
                    },
                    {
                        "key": "max_dashboards",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited dashboards (0 = unlimited)",
                    },
                    {
                        "key": "max_data_sources",
                        "value": "10",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum connected data sources",
                    },
                    {
                        "key": "api_access",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access",
                    },
                    {
                        "key": "export_csv",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export data as CSV",
                    },
                    {
                        "key": "export_pdf",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "team_collaboration",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Share dashboards with team members",
                    },
                    {
                        "key": "max_team_members",
                        "value": "10",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum team collaborators",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "365",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Historical data retention in days",
                    },
                    {
                        "key": "custom_widgets",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Build custom chart widgets",
                    },
                ],
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "description": "Full-featured analytics for large organizations.",
                "price_cents": 9900,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 30,
                "sort_order": 2,
                "is_featured": False,
                "features": {
                    "dashboards": "Unlimited",
                    "data_sources": "Unlimited",
                    "real_time": "Yes",
                    "data_retention": "Unlimited",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Generate analytical reports",
                    },
                    {
                        "key": "real_time_data",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Real-time data streaming",
                    },
                    {
                        "key": "max_dashboards",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited dashboards (0 = unlimited)",
                    },
                    {
                        "key": "max_data_sources",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited data sources (0 = unlimited)",
                    },
                    {
                        "key": "api_access",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access with highest rate limits",
                    },
                    {
                        "key": "export_csv",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export data as CSV",
                    },
                    {
                        "key": "export_pdf",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "team_collaboration",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Share dashboards with team members",
                    },
                    {
                        "key": "max_team_members",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited team collaborators (0 = unlimited)",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited data retention (0 = forever)",
                    },
                    {
                        "key": "custom_widgets",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Build custom chart widgets",
                    },
                    {
                        "key": "white_label",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "White-label dashboards with custom branding",
                    },
                    {
                        "key": "sso_integration",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "SSO/SAML integration",
                    },
                    {
                        "key": "dedicated_support",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Dedicated account manager",
                    },
                    {
                        "key": "audit_log",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Full audit log of all actions",
                    },
                ],
            },
        ],
    },
    # -------------------------------------------------------------------------
    # Satta Ledger
    # -------------------------------------------------------------------------
    {
        "product": {
            "name": "Satta Ledger",
            "slug": "ledger",
            "description": (
                "Personal ledger and financial management — track transactions, "
                "manage budgets, bills, debts, savings goals, investments, insurance, "
                "invoices, and document vault."
            ),
            "home_url": "https://ledger.sattaspace.com",
        },
        "domains": [
            {
                "domain": "ledger.sattaspace.com",
                "is_primary": True,
            },
            {
                "domain": "localhost:4322",
                "is_primary": False,
            },
        ],
        "plans": [
            {
                "name": "Free",
                "slug": "free",
                "description": "Basic ledger tracking for individuals.",
                "price_cents": 0,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 0,
                "sort_order": 0,
                "is_featured": False,
                "features": {
                    "transactions": "Unlimited",
                    "accounts": "Up to 3",
                    "budgets": "1 budget",
                    "bills": "Track bills",
                    "goals": "1 savings goal",
                    "reports": "Basic",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "transactions",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage transactions",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "View basic financial reports",
                    },
                    {
                        "key": "budgets",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage budgets",
                    },
                    {
                        "key": "goals",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage savings goals",
                    },
                    {
                        "key": "cards",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Manage credit/debit cards",
                    },
                    {
                        "key": "debts",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track borrowed and lent money",
                    },
                    {
                        "key": "accounts",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage accounts",
                    },
                    {
                        "key": "institutions",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Manage financial institutions",
                    },
                    {
                        "key": "categories",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage categories",
                    },
                    {
                        "key": "tags",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage tags",
                    },
                    {
                        "key": "bills",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track bills and subscriptions",
                    },
                    {
                        "key": "investments",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Portfolio and investment tracking",
                    },
                    {
                        "key": "insurance",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Insurance policy management",
                    },
                    {
                        "key": "invoices",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage invoices",
                    },
                    {
                        "key": "vault",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Document vault for financial files",
                    },
                    {
                        "key": "max_accounts",
                        "value": "3",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of accounts",
                    },
                    {
                        "key": "max_budgets",
                        "value": "1",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of budgets",
                    },
                    {
                        "key": "max_goals",
                        "value": "1",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of savings goals",
                    },
                    {
                        "key": "max_institutions",
                        "value": "3",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of institutions (0 = unlimited)",
                    },
                    {
                        "key": "max_categories",
                        "value": "10",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of categories (0 = unlimited)",
                    },
                    {
                        "key": "max_transactions",
                        "value": "50",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of transactions (0 = unlimited)",
                    },
                    {
                        "key": "max_tags",
                        "value": "20",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of tags (0 = unlimited)",
                    },
                    {
                        "key": "max_bills",
                        "value": "5",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of bills (0 = unlimited)",
                    },
                    {
                        "key": "max_cards",
                        "value": "3",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of cards (0 = unlimited)",
                    },
                    {
                        "key": "max_debts",
                        "value": "5",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of debts (0 = unlimited)",
                    },
                    {
                        "key": "max_investments",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Not available (feature disabled on Free plan)",
                    },
                    {
                        "key": "max_insurance",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Not available (feature disabled on Free plan)",
                    },
                    {
                        "key": "max_invoices",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Not available (feature disabled on Free plan)",
                    },
                    {
                        "key": "max_vault_documents",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Not available (feature disabled on Free plan)",
                    },
                    {
                        "key": "export_pdf",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "api_access",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access",
                    },
                    {
                        "key": "priority_support",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Priority customer support",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "90",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Historical data retention in days",
                    },
                ],
            },
            {
                "name": "Standard",
                "slug": "standard",
                "description": "Full ledger suite for power users.",
                "price_cents": 900,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 14,
                "sort_order": 1,
                "is_featured": True,
                "features": {
                    "transactions": "Unlimited",
                    "accounts": "Unlimited",
                    "budgets": "Unlimited",
                    "bills": "Track bills + reminders",
                    "goals": "Unlimited goals",
                    "investments": "Portfolio tracking",
                    "insurance": "Policy management",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "transactions",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage transactions",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "View advanced financial reports",
                    },
                    {
                        "key": "budgets",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage budgets",
                    },
                    {
                        "key": "goals",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage savings goals",
                    },
                    {
                        "key": "cards",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Manage credit/debit cards",
                    },
                    {
                        "key": "debts",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track borrowed and lent money",
                    },
                    {
                        "key": "accounts",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage accounts",
                    },
                    {
                        "key": "institutions",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Manage financial institutions",
                    },
                    {
                        "key": "categories",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage categories",
                    },
                    {
                        "key": "tags",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage tags",
                    },
                    {
                        "key": "bills",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track bills and subscriptions",
                    },
                    {
                        "key": "investments",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Portfolio and investment tracking",
                    },
                    {
                        "key": "insurance",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Insurance policy management",
                    },
                    {
                        "key": "invoices",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage invoices",
                    },
                    {
                        "key": "vault",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Document vault for financial files",
                    },
                    {
                        "key": "max_accounts",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited accounts (0 = unlimited)",
                    },
                    {
                        "key": "max_budgets",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited budgets (0 = unlimited)",
                    },
                    {
                        "key": "max_goals",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited savings goals (0 = unlimited)",
                    },
                    {
                        "key": "max_institutions",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited institutions (0 = unlimited)",
                    },
                    {
                        "key": "max_categories",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited categories (0 = unlimited)",
                    },
                    {
                        "key": "max_transactions",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited transactions (0 = unlimited)",
                    },
                    {
                        "key": "max_tags",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited tags (0 = unlimited)",
                    },
                    {
                        "key": "max_bills",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited bills (0 = unlimited)",
                    },
                    {
                        "key": "max_cards",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited cards (0 = unlimited)",
                    },
                    {
                        "key": "max_debts",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited debts (0 = unlimited)",
                    },
                    {
                        "key": "max_investments",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited investments (0 = unlimited)",
                    },
                    {
                        "key": "max_insurance",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited insurance policies (0 = unlimited)",
                    },
                    {
                        "key": "max_invoices",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited invoices (0 = unlimited)",
                    },
                    {
                        "key": "max_vault_documents",
                        "value": "5",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Maximum number of vault documents",
                    },
                    {
                        "key": "export_pdf",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "api_access",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access",
                    },
                    {
                        "key": "priority_support",
                        "value": "false",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Priority customer support",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "365",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Historical data retention in days",
                    },
                ],
            },
            {
                "name": "Pro",
                "slug": "pro",
                "description": "Enterprise ledger for teams and businesses.",
                "price_cents": 2900,
                "currency": "USD",
                "billing_cycle": BillingCycle.MONTHLY,
                "trial_days": 30,
                "sort_order": 2,
                "is_featured": False,
                "features": {
                    "transactions": "Unlimited + AI categorization",
                    "accounts": "Unlimited",
                    "budgets": "Unlimited + AI insights",
                    "bills": "Auto-pay + reminders",
                    "goals": "Unlimited goals",
                    "investments": "AI-powered portfolio",
                    "insurance": "Claims tracking",
                },
                "access_entries": [
                    {
                        "key": "dashboard",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Access to main dashboard",
                    },
                    {
                        "key": "transactions",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage transactions with AI categorization",
                    },
                    {
                        "key": "reports",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "View advanced financial reports with AI insights",
                    },
                    {
                        "key": "budgets",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage budgets with AI recommendations",
                    },
                    {
                        "key": "goals",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage savings goals",
                    },
                    {
                        "key": "cards",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Manage credit/debit cards",
                    },
                    {
                        "key": "debts",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track borrowed and lent money",
                    },
                    {
                        "key": "accounts",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage accounts",
                    },
                    {
                        "key": "institutions",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Manage financial institutions",
                    },
                    {
                        "key": "categories",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage categories",
                    },
                    {
                        "key": "tags",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage tags",
                    },
                    {
                        "key": "bills",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Track bills and subscriptions",
                    },
                    {
                        "key": "investments",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "AI-powered portfolio and investment tracking",
                    },
                    {
                        "key": "insurance",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Insurance policy and claims management",
                    },
                    {
                        "key": "invoices",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Create and manage invoices",
                    },
                    {
                        "key": "vault",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Document vault for financial files",
                    },
                    {
                        "key": "max_accounts",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited accounts (0 = unlimited)",
                    },
                    {
                        "key": "max_budgets",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited budgets (0 = unlimited)",
                    },
                    {
                        "key": "max_goals",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited savings goals (0 = unlimited)",
                    },
                    {
                        "key": "max_institutions",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited institutions (0 = unlimited)",
                    },
                    {
                        "key": "max_categories",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited categories (0 = unlimited)",
                    },
                    {
                        "key": "max_transactions",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited transactions (0 = unlimited)",
                    },
                    {
                        "key": "max_tags",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited tags (0 = unlimited)",
                    },
                    {
                        "key": "max_bills",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited bills (0 = unlimited)",
                    },
                    {
                        "key": "max_cards",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited cards (0 = unlimited)",
                    },
                    {
                        "key": "max_debts",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited debts (0 = unlimited)",
                    },
                    {
                        "key": "max_investments",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited investments (0 = unlimited)",
                    },
                    {
                        "key": "max_insurance",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited insurance policies (0 = unlimited)",
                    },
                    {
                        "key": "max_invoices",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited invoices (0 = unlimited)",
                    },
                    {
                        "key": "max_vault_documents",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited vault documents (0 = unlimited)",
                    },
                    {
                        "key": "export_pdf",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Export reports as PDF",
                    },
                    {
                        "key": "api_access",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "REST API access with higher rate limits",
                    },
                    {
                        "key": "priority_support",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Priority customer support",
                    },
                    {
                        "key": "data_retention_days",
                        "value": "0",
                        "value_type": AccessValueType.INTEGER,
                        "description": "Unlimited data retention (0 = forever)",
                    },
                    {
                        "key": "white_label",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "White-label reports with custom branding",
                    },
                    {
                        "key": "audit_log",
                        "value": "true",
                        "value_type": AccessValueType.BOOLEAN,
                        "description": "Full audit log of all financial actions",
                    },
                ],
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed billing app with sample products, plans, access entries, and service domains."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing billing data before seeding (irreversible).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print one line per created record.",
        )

    def handle(self, *args, **options):
        self.verbose = options["verbose"]
        self.created_counts = {
            "products": 0,
            "plans": 0,
            "access_entries": 0,
            "domains": 0,
            "subscriptions": 0,
        }

        if options["clear"]:
            self._clear_all()

        self._seed_all()

        # Print summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("--- Seed Complete ---"))
        self.stdout.write(f"  Products:          {self.created_counts['products']}")
        self.stdout.write(f"  Plans:             {self.created_counts['plans']}")
        self.stdout.write(
            f"  Access Entries:    {self.created_counts['access_entries']}"
        )
        self.stdout.write(f"  Service Domains:   {self.created_counts['domains']}")
        self.stdout.write(
            f"  Subscriptions:     {self.created_counts['subscriptions']}"
        )

    # =========================================================================
    # Clear
    # =========================================================================

    def _clear_all(self):
        """Wipe all billing data in the correct order (respect FKs)."""
        self.stdout.write(self.style.WARNING("Clearing all billing data..."))

        Subscription.objects.all().delete()
        self._log("Subscriptions cleared")

        AccessEntry.objects.all().delete()
        self._log("Access entries cleared")

        Plan.objects.all().delete()
        self._log("Plans cleared")

        ServiceDomain.objects.all().delete()
        self._log("Service domains cleared")

        Product.objects.all().delete()
        self._log("Products cleared")

        self.stdout.write(self.style.WARNING("All billing data deleted."))

    # =========================================================================
    # Seed
    # =========================================================================

    def _seed_all(self):
        """Iterate over SEED_DATA and create all records."""
        self.stdout.write("Seeding billing data...")

        for product_data in SEED_DATA:
            product = self._seed_product(product_data["product"])
            self._seed_domains(product, product_data.get("domains", []))
            self._seed_plans(product, product_data.get("plans", []))

        # Create sample subscriptions for existing users
        self._seed_subscriptions()

    def _seed_product(self, data: dict) -> Product:
        """Create or retrieve a product."""
        product, created = Product.objects.get_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "description": data.get("description", ""),
                "home_url": data.get("home_url", ""),
                "is_active": True,
            },
        )
        if created:
            self.created_counts["products"] += 1
            self._log(f"  Product: {product.name} ({product.slug})")
        return product

    def _seed_domains(self, product: Product, domains: list[dict]) -> None:
        """Create service domains for a product."""
        for domain_data in domains:
            domain, created = ServiceDomain.objects.get_or_create(
                domain=domain_data["domain"],
                defaults={
                    "product": product,
                    "is_primary": domain_data.get("is_primary", False),
                    "is_active": True,
                },
            )
            if created:
                self.created_counts["domains"] += 1
                self._log(f"    Domain: {domain.domain} (primary={domain.is_primary})")

    def _seed_plans(self, product: Product, plans: list[dict]) -> None:
        """Create plans and their access entries for a product."""
        for plan_data in plans:
            plan, created = Plan.objects.get_or_create(
                product=product,
                slug=plan_data["slug"],
                defaults={
                    "name": plan_data["name"],
                    "description": plan_data.get("description", ""),
                    "price_cents": plan_data["price_cents"],
                    "currency": plan_data.get("currency", "USD"),
                    "billing_cycle": plan_data.get(
                        "billing_cycle", BillingCycle.MONTHLY
                    ),
                    "trial_days": plan_data.get("trial_days", 0),
                    "features": plan_data.get("features", {}),
                    "sort_order": plan_data.get("sort_order", 0),
                    "is_active": True,
                    "is_featured": plan_data.get("is_featured", False),
                },
            )
            if created:
                self.created_counts["plans"] += 1
                self._log(f"    Plan: {plan.name} ({plan.display_price})")

            # Seed access entries for this plan
            for entry_data in plan_data.get("access_entries", []):
                entry, created = AccessEntry.objects.get_or_create(
                    plan=plan,
                    key=entry_data["key"],
                    defaults={
                        "value": entry_data["value"],
                        "value_type": entry_data.get(
                            "value_type", AccessValueType.STRING
                        ),
                        "description": entry_data.get("description", ""),
                    },
                )
                if created:
                    self.created_counts["access_entries"] += 1
                    self._log(f"      Access: {entry.key} = {entry.value}")

    def _seed_subscriptions(self) -> None:
        """Create free-plan subscriptions for all existing active users.

        Skips users who already have a subscription for a product.
        This simulates what the ``get_or_create_free_subscription``
        service method does at runtime.
        """
        users = User.objects.filter(is_active=True, is_deleted=False)
        user_count = users.count()

        if user_count == 0:
            self._log("  No active users found — skipping subscription seeding.")
            return

        self._log(
            f"  Found {user_count} active user(s). Creating free subscriptions..."
        )

        products = Product.objects.filter(is_active=True)
        for user in users:
            for product in products:
                sub, created = Subscription.objects.get_or_create(
                    user=user,
                    product=product,
                    defaults={
                        "plan": product.get_free_plan(),
                        "status": SubscriptionStatus.ACTIVE,
                    },
                )
                if created and sub.plan:
                    self.created_counts["subscriptions"] += 1
                    self._log(
                        f"    Subscription: {user.email} → {product.slug}/{sub.plan.slug}"
                    )
                elif created and not sub.plan:
                    self._log(
                        f"    WARNING: No free plan for '{product.slug}' — "
                        f"skipping subscription for {user.email}"
                    )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _log(self, message: str) -> None:
        """Print message only in verbose mode."""
        if self.verbose:
            self.stdout.write(f"  {message}")
