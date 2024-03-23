from django.core.exceptions import ValidationError

from allauth.core import context
from allauth.headless.restkit import inputs
from allauth.socialaccount.adapter import (
    get_adapter,
    get_adapter as get_socialaccount_adapter,
)
from allauth.socialaccount.forms import SignupForm
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.base.constants import AuthProcess


class SignupInput(SignupForm, inputs.Input):
    pass


class DeleteProviderAccountInput(inputs.Input):
    provider = inputs.CharField()
    account = inputs.CharField()

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        uid = cleaned_data.get("account")
        provider_id = cleaned_data.get("provider")
        if uid and provider_id:
            accounts = SocialAccount.objects.filter(user=self.user)
            account = accounts.filter(
                uid=uid,
                provider=provider_id,
            ).first()
            if not account:
                raise inputs.ValidationError("Unknown account.")
            get_socialaccount_adapter().validate_disconnect(account, accounts)
            self.cleaned_data["account"] = account
        return cleaned_data


class ProviderTokenInput(inputs.Input):
    provider = inputs.CharField()
    process = inputs.ChoiceField(
        choices=[
            (AuthProcess.LOGIN, AuthProcess.LOGIN),
            (AuthProcess.CONNECT, AuthProcess.CONNECT),
        ]
    )
    token = inputs.Field()

    def clean_provider(self):
        provider_id = self.cleaned_data["provider"]
        provider = get_adapter().get_provider(context.request, provider_id)
        if not provider.supports_token_authentication:
            raise inputs.ValidationError(
                "Provider does not support token authentication.", code="invalid"
            )
        return provider

    def clean(self):
        cleaned_data = super().clean()
        token = self.data.get("token")
        if not isinstance(token, dict):
            self.add_error(
                "token", inputs.ValidationError("Invalid `token`.", code="invalid")
            )
            token = None
        provider = cleaned_data.get("provider")
        if provider and token:
            client_id = token.get("client_id")
            if provider.app.client_id != client_id:
                self.add_error(
                    "token",
                    inputs.ValidationError(
                        "Provider does not match `client_id`.", code="invalid"
                    ),
                )
            else:
                id_token = token.get("id_token")
                access_token = token.get("access_token")
                if (
                    (id_token is not None and not isinstance(id_token, str))
                    or (access_token is not None and not isinstance(access_token, str))
                    or (not id_token and not access_token)
                ):
                    self.add_error(
                        "token",
                        inputs.ValidationError(
                            "`id_token` and/or `access_token` required.",
                            code="required",
                        ),
                    )
        if not self.errors:
            try:
                login = provider.verify_token(context.request, token)
                login.state["process"] = cleaned_data["process"]
                cleaned_data["sociallogin"] = login
            except ValidationError as e:
                self.add_error("token", e)
        return cleaned_data
