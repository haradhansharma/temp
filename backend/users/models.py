import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from common.models import TimeStampedModel, SoftDeleteModel

# Import custom manager (set on User below)
from .managers import CustomUserManager  # noqa: E402


# =============================================================================
# Choice Constants
# =============================================================================


# =============================================================================
# Choice Constants
# =============================================================================


class RoleChoices(models.TextChoices):
    """User role choices for SaaS multi-tenancy."""

    OWNER = "owner", _("Owner")
    ADMIN = "admin", _("Admin")
    MEMBER = "member", _("Member")


class TimezoneChoices(models.TextChoices):
    """Common IANA timezone choices."""

    # Americas
    UTC = "UTC", _("UTC")
    US_EASTERN = "America/New_York", _("Eastern Time (US)")
    US_CENTRAL = "America/Chicago", _("Central Time (US)")
    US_MOUNTAIN = "America/Denver", _("Mountain Time (US)")
    US_PACIFIC = "America/Los_Angeles", _("Pacific Time (US)")
    US_ALASKA = "America/Anchorage", _("Alaska Time (US)")
    US_HAWAII = "Pacific/Honolulu", _("Hawaii Time (US)")
    CA_EASTERN = "America/Toronto", _("Eastern Time (Canada)")
    CA_PACIFIC = "America/Vancouver", _("Pacific Time (Canada)")
    MX_CITY = "America/Mexico_City", _("Mexico City")
    SA_PAULO = "America/Sao_Paulo", _("Sao Paulo")
    AR_BUENOS = "America/Argentina/Buenos_Aires", _("Buenos Aires")
    CO_BOGOTA = "America/Bogota", _("Bogota")
    PE_LIMA = "America/Lima", _("Lima")
    CL_SANTIAGO = "America/Santiago", _("Santiago")

    # Europe
    GB_LONDON = "Europe/London", _("London")
    IE_DUBLIN = "Europe/Dublin", _("Dublin")
    FR_PARIS = "Europe/Paris", _("Paris")
    DE_BERLIN = "Europe/Berlin", _("Berlin")
    ES_MADRID = "Europe/Madrid", _("Madrid")
    IT_ROME = "Europe/Rome", _("Rome")
    NL_AMSTERDAM = "Europe/Amsterdam", _("Amsterdam")
    BE_BRUSSELS = "Europe/Brussels", _("Brussels")
    AT_VIENNA = "Europe/Vienna", _("Vienna")
    SE_STOCKHOLM = "Europe/Stockholm", _("Stockholm")
    NO_OSLO = "Europe/Oslo", _("Oslo")
    DK_COPENHAGEN = "Europe/Copenhagen", _("Copenhagen")
    FI_HELSINKI = "Europe/Helsinki", _("Helsinki")
    PL_WARSAW = "Europe/Warsaw", _("Warsaw")
    PT_LISBON = "Europe/Lisbon", _("Lisbon")
    GR_ATHENS = "Europe/Athens", _("Athens")
    CZ_PRAGUE = "Europe/Prague", _("Prague")
    HU_BUDAPEST = "Europe/Budapest", _("Budapest")
    RO_BUCHAREST = "Europe/Bucharest", _("Bucharest")

    # Asia
    AE_DUBAI = "Asia/Dubai", _("Dubai")
    SA_RIYADH = "Asia/Riyadh", _("Riyadh")
    IN_KOLKATA = "Asia/Kolkata", _("India Standard Time")
    PK_KARACHI = "Asia/Karachi", _("Karachi")
    BD_DHAKA = "Asia/Dhaka", _("Dhaka")
    LK_COLOMBO = "Asia/Colombo", _("Colombo")
    NP_KATHMANDU = "Asia/Kathmandu", _("Kathmandu")
    TH_BANGKOK = "Asia/Bangkok", _("Bangkok")
    VN_HO_CHI = "Asia/Ho_Chi_Minh", _("Ho Chi Minh City")
    ID_JAKARTA = "Asia/Jakarta", _("Jakarta")
    MY_KUALA = "Asia/Kuala_Lumpur", _("Kuala Lumpur")
    SG_SINGAPORE = "Asia/Singapore", _("Singapore")
    PH_MANILA = "Asia/Manila", _("Manila")
    CN_SHANGHAI = "Asia/Shanghai", _("Shanghai")
    HK_HONG = "Asia/Hong_Kong", _("Hong Kong")
    TW_TAIPEI = "Asia/Taipei", _("Taipei")
    KR_SEOUL = "Asia/Seoul", _("Seoul")
    JP_TOKYO = "Asia/Tokyo", _("Tokyo")

    # Oceania
    AU_SYDNEY = "Australia/Sydney", _("Sydney")
    AU_MELBOURNE = "Australia/Melbourne", _("Melbourne")
    AU_PERTH = "Australia/Perth", _("Perth")
    NZ_AUCKLAND = "Pacific/Auckland", _("Auckland")

    # Africa
    ZA_JOHANNESBURG = "Africa/Johannesburg", _("Johannesburg")
    KE_NAIROBI = "Africa/Nairobi", _("Nairobi")
    EG_CAIRO = "Africa/Cairo", _("Cairo")
    NG_LAGOS = "Africa/Lagos", _("Lagos")
    MA_CASABLANCA = "Africa/Casablanca", _("Casablanca")


class CurrencyChoices(models.TextChoices):
    """ISO 4217 currency codes for common currencies."""

    USD = "USD", _("US Dollar")
    EUR = "EUR", _("Euro")
    GBP = "GBP", _("British Pound")
    JPY = "JPY", _("Japanese Yen")
    CAD = "CAD", _("Canadian Dollar")
    AUD = "AUD", _("Australian Dollar")
    CHF = "CHF", _("Swiss Franc")
    CNY = "CNY", _("Chinese Yuan")
    HKD = "HKD", _("Hong Kong Dollar")
    NZD = "NZD", _("New Zealand Dollar")
    SEK = "SEK", _("Swedish Krona")
    KRW = "KRW", _("South Korean Won")
    SGD = "SGD", _("Singapore Dollar")
    INR = "INR", _("Indian Rupee")
    MXN = "MXN", _("Mexican Peso")
    BRL = "BRL", _("Brazilian Real")
    ZAR = "ZAR", _("South African Rand")
    RUB = "RUB", _("Russian Ruble")
    TRY = "TRY", _("Turkish Lira")
    AED = "AED", _("UAE Dirham")
    SAR = "SAR", _("Saudi Riyal")
    BDT = "BDT", _("Bangladeshi Taka")
    PKR = "PKR", _("Pakistani Rupee")
    PHP = "PHP", _("Philippine Peso")
    THB = "THB", _("Thai Baht")
    MYR = "MYR", _("Malaysian Ringgit")
    IDR = "IDR", _("Indonesian Rupiah")
    VND = "VND", _("Vietnamese Dong")
    NOK = "NOK", _("Norwegian Krone")
    DKK = "DKK", _("Danish Krone")
    PLN = "PLN", _("Polish Zloty")
    TWD = "TWD", _("Taiwan Dollar")
    NGN = "NGN", _("Nigerian Naira")
    EGP = "EGP", _("Egyptian Pound")
    KES = "KES", _("Kenyan Shilling")
    COP = "COP", _("Colombian Peso")
    CLP = "CLP", _("Chilean Peso")
    PEN = "PEN", _("Peruvian Sol")
    ARS = "ARS", _("Argentine Peso")


class LanguageChoices(models.TextChoices):
    """Common language codes (ISO 639-1)."""

    EN = "en", _("English")
    ES = "es", _("Spanish")
    FR = "fr", _("French")
    DE = "de", _("German")
    PT = "pt", _("Portuguese")
    IT = "it", _("Italian")
    NL = "nl", _("Dutch")
    RU = "ru", _("Russian")
    JA = "ja", _("Japanese")
    KO = "ko", _("Korean")
    ZH = "zh", _("Chinese")
    AR = "ar", _("Arabic")
    HI = "hi", _("Hindi")
    BN = "bn", _("Bengali")
    TR = "tr", _("Turkish")
    PL = "pl", _("Polish")
    SV = "sv", _("Swedish")
    DA = "da", _("Danish")
    NO = "no", _("Norwegian")
    FI = "fi", _("Finnish")
    TH = "th", _("Thai")
    VI = "vi", _("Vietnamese")
    ID = "id", _("Indonesian")
    MS = "ms", _("Malay")
    TL = "tl", _("Filipino")
    UK = "uk", _("Ukrainian")
    CS = "cs", _("Czech")
    HU = "hu", _("Hungarian")
    RO = "ro", _("Romanian")
    EL = "el", _("Greek")


class User(AbstractUser, TimeStampedModel, SoftDeleteModel):
    """Custom User model with email-based authentication.

    Designed for SaaS use with:
    - Email as primary identifier (USERNAME_FIELD)
    - Profile fields for personalization
    - Email verification tracking
    - Soft delete support (is_deleted)
    - TimestampedModel (created_at, updated_at)
    """

    username = models.CharField(
        max_length=150, null=True, blank=True, unique=False
    )  # Not used for auth
    slug = models.UUIDField(
        _("Slug"),
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        editable=False,
        help_text=_("Public unique identifier (UUID4). Used in URLs and references."),
    )
    email = models.EmailField(
        _("Email Address"),
        unique=True,
        db_index=True,
        max_length=255,
        error_messages={
            "unique": _("A user with this email address already exists."),
        },
    )

    # --- Profile ---
    first_name = models.CharField(_("First Name"), max_length=150, blank=True)
    last_name = models.CharField(_("Last Name"), max_length=150, blank=True)
    phone = models.CharField(_("Phone Number"), max_length=30, blank=True, default="")
    avatar = models.ImageField(
        _("Avatar"),
        upload_to="avatars/%Y/%m/",
        blank=True,
        null=True,
    )

    # --- Preferences ---
    # --- Preferences (ChoiceFields) ---
    timezone = models.CharField(
        _("Timezone"),
        max_length=50,
        choices=TimezoneChoices.choices,
        default=TimezoneChoices.UTC,
        db_index=True,
    )
    currency = models.CharField(
        _("Preferred Currency"),
        max_length=3,
        choices=CurrencyChoices.choices,
        default=CurrencyChoices.USD,
        db_index=True,
    )
    language = models.CharField(
        _("Language"),
        max_length=10,
        choices=LanguageChoices.choices,
        default=LanguageChoices.EN,
        db_index=True,
    )

    # --- Auth Status ---
    is_email_verified = models.BooleanField(
        _("Email Verified"), default=False, db_index=True
    )
    last_login_ip = models.GenericIPAddressField(
        _("Last Login IP"), null=True, blank=True
    )

    # --- SaaS / Tenant fields (foundation for future) ---
    # --- SaaS / Tenant fields (foundation for future) ---
    role = models.CharField(
        _("Role"),
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.MEMBER,
        db_index=True,
        help_text=_("User role: owner, admin, member"),
    )

    # --- Django config ---
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    objects = CustomUserManager()

    class Meta:
        db_table = "users_user"
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["-created_at"]

        constraints = []

    def __str__(self) -> str:
        return str(self.slug)

    @property
    def full_name(self) -> str:
        """Return the user's full name, or email if empty."""
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    @property
    def display_name(self) -> str:
        """Return the user's display name (first name or email prefix)."""
        return self.first_name.strip() or self.email.split("@")[0]


# =============================================================================
# Login History
# =============================================================================


class UserLoginHistory(models.Model):
    """Tracks user login events for security auditing and analytics.

    Each successful login creates a record with timestamp, IP address,
    and user agent. This model supplements Django's built-in `last_login`
    field by maintaining a full history rather than just the most recent value.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_history",
        db_index=True,
    )
    ip_address = models.GenericIPAddressField(
        _("IP Address"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("IP address from which the login originated."),
    )
    user_agent = models.TextField(
        _("User Agent"),
        blank=True,
        default="",
        help_text=_("Browser/client user agent string."),
    )
    created_at = models.DateTimeField(
        _("Login Time"),
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "users_login_history"
        verbose_name = _("Login History")
        verbose_name_plural = _("Login History")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Login({self.user.email}, {self.created_at})"
