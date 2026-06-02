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
    # Credit management models
    BankSettings,
    CreditPool,
    CreditInvoice,
    CreditTransaction,
    CreditPurchaseRequest,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# =============================================================================
# Bank Settings Seed Data
# =============================================================================
# Admin-configured bank accounts where users can transfer money for credits.
# =============================================================================


BANK_SETTINGS_SEED_DATA = [
    {
        "bank_name": "First National Bank",
        "account_holder_name": "SattaBase Technologies Inc.",
        "account_number": "1234567890",
        "routing_number": "021000021",
        "is_active": True,
    },
    {
        "bank_name": "International Business Bank",
        "account_holder_name": "SattaBase Technologies Inc.",
        "account_number": "9876543210",
        "routing_number": "SWIFT: INTLUS33",
        "is_active": True,
    },
    {
        "bank_name": "Legacy Savings Bank (Inactive)",
        "account_holder_name": "SattaBase Old Account",
        "account_number": "5555555555",
        "routing_number": "021000089",
        "is_active": False,
    },
]


# =============================================================================
# Credit Seed Data Definitions
# =============================================================================
# Sample credit pools, requests, and transactions for testing.
# These are created per-user when users exist in the system.
# =============================================================================


CREDIT_SEED_DATA = {
    # Sample pending credit purchase requests (will be created for test users)
    "pending_requests": [
        {
            "product_slug": "ledger",
            "plan_slug": "standard",
            "amount_cents": 900,  # $9.00 for 1 month
            "currency": "USD",
            "bank_name": "User Personal Bank",
            "account_holder_name": "Test User",
            "account_number": "****1234",
            "routing_number": "021000021",
            "transaction_reference": "TXN-PENDING-001",
            "payment_proof_note": "Payment sent via mobile banking app",
        },
        {
            "product_slug": "analytics",
            "plan_slug": "growth",
            "amount_cents": 5700,  # $57.00 for 3 months
            "currency": "USD",
            "bank_name": "Business Bank Corp",
            "account_holder_name": "Test Business",
            "account_number": "****5678",
            "routing_number": "SWIFT: BBKCUS33",
            "transaction_reference": "TXN-PENDING-002",
            "payment_proof_note": "Wire transfer from business account",
        },
    ],
    # Sample active credit pools (already approved)
    "active_pools": [
        {
            "product_slug": "ledger",
            "plan_slug": "standard",
            "amount_cents": 2700,  # $27.00 for 3 months
            "currency": "USD",
            "credit_periods": 3,
            "source": "bank_transfer",
            "payment_reference": "BANK-TRANSFER-2024-001",
        },
        {
            "product_slug": "finance",
            "plan_slug": "pro",
            "amount_cents": 2900,  # $29.00 for 1 month pro
            "currency": "USD",
            "credit_periods": 1,
            "source": "manual",
            "payment_reference": "ADMIN-MANUAL-001",
        },
    ],
}


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
                    "budget_categories": 3,
                    "reports": False,
                    "bank_accounts": 1,
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
                    "budget_categories": 0,
                    "reports": True,
                    "bank_accounts": 5,
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
                    "budget_categories": 0,
                    "reports": True,
                    "bank_accounts": 0,
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
                    "dashboards": 2,
                    "data_sources": 1,
                    "real_time": False,
                    "data_retention": 7,
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
                    "dashboards": 0,
                    "data_sources": 10,
                    "real_time": True,
                    "data_retention": 365,
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
                    "dashboards": 0,
                    "data_sources": 0,
                    "real_time": True,
                    "data_retention": 0,
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
                    "transactions": 50,
                    "accounts": 3,
                    "budgets": 1,
                    "bills": 5,
                    "goals": 1,
                    "investments": False,
                    "insurance": False,
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
                    "transactions": 0,
                    "accounts": 0,
                    "budgets": 0,
                    "bills": 0,
                    "goals": 0,
                    "investments": True,
                    "insurance": True,
                    "reports": "Advanced",
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
                    "transactions": 0,
                    "accounts": 0,
                    "budgets": 0,
                    "bills": 0,
                    "goals": 0,
                    "investments": True,
                    "insurance": True,
                    "reports": "Advanced + AI insights",
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
            "bank_settings": 0,
            "credit_pools": 0,
            "credit_requests": 0,
            "credit_invoices": 0,
            "credit_transactions": 0,
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
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("--- Credit Data ---"))
        self.stdout.write(f"  Bank Settings:     {self.created_counts['bank_settings']}")
        self.stdout.write(f"  Credit Pools:      {self.created_counts['credit_pools']}")
        self.stdout.write(f"  Credit Requests:   {self.created_counts['credit_requests']}")
        self.stdout.write(f"  Credit Invoices:   {self.created_counts['credit_invoices']}")
        self.stdout.write(
            f"  Credit Transactions: {self.created_counts['credit_transactions']}"
        )

    # =========================================================================
    # Clear
    # =========================================================================

    def _clear_all(self):
        """Wipe all billing data in the correct order (respect FKs)."""
        self.stdout.write(self.style.WARNING("Clearing all billing data..."))

        CreditTransaction.objects.all().delete()
        self._log("Credit transactions cleared")

        CreditInvoice.objects.all().delete()
        self._log("Credit invoices cleared")

        CreditPool.objects.all().delete()
        self._log("Credit pools cleared")

        CreditPurchaseRequest.objects.all().delete()
        self._log("Credit purchase requests cleared")

        BankSettings.objects.all().delete()
        self._log("Bank settings cleared")

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

        # Seed credit management data
        self._seed_bank_settings()
        self._seed_credit_data()

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
    # Bank Settings
    # =========================================================================

    def _seed_bank_settings(self) -> None:
        """Seed bank account settings for manual credit purchases."""
        self.stdout.write("Seeding bank settings...")

        for bank_data in BANK_SETTINGS_SEED_DATA:
            bank, created = BankSettings.objects.get_or_create(
                bank_name=bank_data["bank_name"],
                account_number=bank_data["account_number"],
                defaults={
                    "account_holder_name": bank_data["account_holder_name"],
                    "routing_number": bank_data.get("routing_number", ""),
                    "is_active": bank_data.get("is_active", True),
                },
            )
            if created:
                self.created_counts["bank_settings"] += 1
                status = "active" if bank.is_active else "inactive"
                self._log(f"  Bank: {bank.bank_name} ({status})")

    # =========================================================================
    # Credit Data
    # =========================================================================

    def _seed_credit_data(self) -> None:
        """Seed credit pools, requests, invoices, and transactions."""
        self.stdout.write("Seeding credit data...")

        users = list(User.objects.filter(is_active=True, is_deleted=False))
        if not users:
            self._log("  No active users found — skipping credit seeding.")
            return

        # Get a superuser/admin for created_by field
        admin_user = (
            User.objects.filter(is_superuser=True).first() or users[0]
        )

        # Seed pending credit purchase requests
        self._seed_credit_requests(users)

        # Seed active credit pools (with invoices and transactions)
        self._seed_credit_pools(users, admin_user)

    def _seed_credit_requests(self, users: list) -> None:
        """Create pending credit purchase requests for testing."""
        pending_data = CREDIT_SEED_DATA.get("pending_requests", [])

        if not pending_data:
            return

        self._log(f"  Creating {len(pending_data)} pending credit request(s)...")

        for idx, req_data in enumerate(pending_data):
            # Get product and plan
            try:
                product = Product.objects.get(slug=req_data["product_slug"])
                plan = Plan.objects.get(
                    product=product, slug=req_data["plan_slug"]
                )
            except (Product.DoesNotExist, Plan.DoesNotExist):
                self._log(
                    f"    WARNING: Product/Plan not found for request {idx + 1}"
                )
                continue

            # Assign to a user (cycle through available users)
            user = users[idx % len(users)]

            # Check if similar request already exists
            existing = CreditPurchaseRequest.objects.filter(
                user=user,
                product=product,
                transaction_reference=req_data["transaction_reference"],
            ).exists()

            if existing:
                continue

            request = CreditPurchaseRequest.objects.create(
                user=user,
                product=product,
                plan=plan,
                amount_cents=req_data["amount_cents"],
                currency=req_data.get("currency", "USD"),
                bank_name=req_data["bank_name"],
                account_holder_name=req_data["account_holder_name"],
                account_number=req_data["account_number"],
                routing_number=req_data.get("routing_number", ""),
                transaction_reference=req_data["transaction_reference"],
                payment_proof_note=req_data.get("payment_proof_note", ""),
                status=CreditPurchaseRequest.RequestStatus.PENDING,
            )
            self.created_counts["credit_requests"] += 1
            self._log(
                f"    Credit Request: {user.email} → {product.slug}/{plan.slug} "
                f"(${request.amount_cents / 100:.2f})"
            )

    def _seed_credit_pools(self, users: list, admin_user) -> None:
        """Create active credit pools with invoices and transactions."""
        active_pools_data = CREDIT_SEED_DATA.get("active_pools", [])

        if not active_pools_data:
            return

        self._log(f"  Creating {len(active_pools_data)} active credit pool(s)...")

        invoice_counter = 1

        for idx, pool_data in enumerate(active_pools_data):
            # Get product and plan
            try:
                product = Product.objects.get(slug=pool_data["product_slug"])
                plan = Plan.objects.get(
                    product=product, slug=pool_data["plan_slug"]
                )
            except (Product.DoesNotExist, Plan.DoesNotExist):
                self._log(
                    f"    WARNING: Product/Plan not found for pool {idx + 1}"
                )
                continue

            # Assign to a user (cycle through available users)
            user = users[idx % len(users)]

            # Check if similar pool already exists
            existing = CreditPool.objects.filter(
                user=user,
                product=product,
                payment_reference=pool_data["payment_reference"],
            ).exists()

            if existing:
                continue

            # Create credit pool
            pool = CreditPool.objects.create(
                user=user,
                product=product,
                plan=plan,
                amount_cents=pool_data["amount_cents"],
                currency=pool_data.get("currency", "USD"),
                credit_periods=pool_data["credit_periods"],
                periods_consumed=0,
                source=pool_data.get("source", "manual"),
                payment_reference=pool_data["payment_reference"],
                created_by=admin_user,
                status=CreditPool.CreditPoolStatus.ACTIVE,
            )
            self.created_counts["credit_pools"] += 1
            self._log(
                f"    Credit Pool: {user.email} → {product.slug}/{plan.slug} "
                f"({pool.credit_periods} periods, ${pool.amount_cents / 100:.2f})"
            )

            # Create invoice for this pool
            invoice_number = f"SB-CRED-{invoice_counter:05d}"
            invoice_counter += 1

            invoice = CreditInvoice.objects.create(
                credit_pool=pool,
                user=user,
                product=product,
                plan=plan,
                invoice_number=invoice_number,
                status=CreditInvoice.CreditInvoiceStatus.PAID,
                amount_cents=pool.amount_cents,
                currency=pool.currency,
                tax_cents=0,
                total_cents=pool.amount_cents,
            )
            self.created_counts["credit_invoices"] += 1
            self._log(f"      Invoice: {invoice_number}")

            # Create purchase transaction
            transaction = CreditTransaction.objects.create(
                credit_pool=pool,
                invoice=invoice,
                action=CreditTransaction.TransactionType.PURCHASE,
                periods_delta=pool.credit_periods,
                amount_cents_delta=pool.amount_cents,
                periods_balance=pool.credit_periods,
                reason=f"Initial purchase via {pool.get_source_display()}",
                created_by=admin_user,
            )
            self.created_counts["credit_transactions"] += 1
            self._log(
                f"      Transaction: PURCHASE (+{pool.credit_periods} periods)"
            )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _log(self, message: str) -> None:
        """Print message only in verbose mode."""
        if self.verbose:
            self.stdout.write(f"  {message}")
