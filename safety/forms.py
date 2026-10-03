import re

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import EmergencyContact, Profile, phone_validator


class BootstrapMixin:
    """Give every widget Bootstrap's form-control / form-select class."""

    def _style_widgets(self):
        for field in self.fields.values():
            widget = field.widget
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs["class"] = (widget.attrs.get("class", "") + " " + css).strip()


def clean_phone(value):
    """Remove spaces, dashes and brackets, then validate."""
    cleaned = re.sub(r"[\s\-()]", "", value or "")
    phone_validator(cleaned)
    return cleaned


class EmailAuthenticationForm(AuthenticationForm):
    """Login form where the username is the user's email address."""

    username = forms.CharField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class RegistrationForm(BootstrapMixin, forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone_number = forms.CharField(max_length=20)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    # Optional first emergency contact, entered at sign-up for convenience.
    contact_name = forms.CharField(max_length=100, required=False, label="Contact name")
    contact_relationship = forms.ChoiceField(
        choices=[("", "Select relationship")] + EmergencyContact.RELATIONSHIP_CHOICES,
        required=False, label="Relationship",
    )
    contact_phone = forms.CharField(max_length=20, required=False, label="Contact phone")
    contact_email = forms.EmailField(required=False, label="Contact email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_widgets()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone_number(self):
        return clean_phone(self.cleaned_data["phone_number"])

    def clean_contact_phone(self):
        value = self.cleaned_data.get("contact_phone")
        return clean_phone(value) if value else ""

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            candidate = User(
                username=data.get("email", ""), email=data.get("email", ""),
                first_name=data.get("full_name", ""),
            )
            try:
                password_validation.validate_password(p1, candidate)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)

        # If any contact field is filled, name, relationship and phone are required.
        contact_fields = ["contact_name", "contact_relationship", "contact_phone", "contact_email"]
        if any(data.get(f) for f in contact_fields):
            for field in ["contact_name", "contact_relationship", "contact_phone"]:
                if not data.get(field):
                    self.add_error(field, "Required when adding an emergency contact.")
        return data

    def save(self):
        data = self.cleaned_data
        parts = data["full_name"].strip().split(None, 1)
        user = User.objects.create_user(
            username=data["email"],
            email=data["email"],
            password=data["password1"],
            first_name=parts[0],
            last_name=parts[1] if len(parts) > 1 else "",
        )
        Profile.objects.create(user=user, phone_number=data["phone_number"])
        if data.get("contact_name"):
            EmergencyContact.objects.create(
                user=user,
                name=data["contact_name"],
                relationship=data["contact_relationship"],
                phone=data["contact_phone"],
                email=data.get("contact_email", ""),
                priority=1,
            )
        return user


class ProfileForm(BootstrapMixin, forms.Form):
    full_name = forms.CharField(max_length=150)
    phone_number = forms.CharField(max_length=20)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_widgets()

    def clean_phone_number(self):
        return clean_phone(self.cleaned_data["phone_number"])


class EmergencyContactForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = EmergencyContact
        fields = ["name", "relationship", "phone", "email", "priority"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_widgets()

    def clean_phone(self):
        return clean_phone(self.cleaned_data["phone"])

    def clean_priority(self):
        priority = self.cleaned_data["priority"]
        if not 1 <= priority <= 10:
            raise forms.ValidationError("Priority must be between 1 and 10.")
        return priority

    def clean(self):
        data = super().clean()
        if not data.get("email") and not data.get("phone"):
            raise forms.ValidationError("Provide at least a phone number or an email.")
        return data
