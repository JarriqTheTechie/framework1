import os

from framework1.database.QueryBuilder import QueryBuilder
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.Form import Form
from framework1.dsl.FormDSL.TextField import TextField

from lib.handlers.users.models.User import User
from lib.services.ClientDatabase import ClientDatabase


def user_exists(AUTH_IDENTITY_KEY):
    user = User().where(os.getenv("AUTH_DB_IDENTITY_COLUMN"), "=", AUTH_IDENTITY_KEY).first()
    if not user:
        return False
    return True


class LoginForm(Form):
    def schema(self):
        return [
            FieldGroup(
                "Login to your account",
                fields=[
                    TextField('username').set_label("Username").set_class(
                        "form-control ps-1").is_required("Username is required").add_validation(
                        user_exists, "User does not exist or is not permitted to use this application"
                    ),
                    TextField('password').set_label("Password").set_class(
                        "form-control ps-1").set_field_type("password").is_required("Password is required"),
                ]
            ).set_field_container_class("row mb-3").set_title_class("h6 fw-bold ps-0").set_class("col-lg-12 px-4 mt-3"),

        ]
