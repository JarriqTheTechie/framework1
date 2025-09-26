import os

from app import app
from flask import render_template, abort, redirect, url_for, session, request
from framework1.core_services.Request import Request
from framework1.core_services.ViewProps import ViewProps
from framework1.service_container._Injector import injectable_route
from lib.handlers.users.forms.LoginForm import LoginForm
from lib.services.ADAuth import ADAuth


class AuthController:
    def __init__(self):
        pass

    @staticmethod
    @app.before_request
    def before_request():
        public_paths = ['/login', '/screen-client']
        public_substrings = ['/resources/', '/client-details/', "/static/"]

        # If request path is not in public paths and doesn't contain public substrings
        if (
                request.path not in public_paths and
                not any(sub in request.path for sub in public_substrings)
        ):
            # If user is not authenticated, redirect to login
            if not session.get(os.getenv("AUTH_IDENTITY_KEY")):
                return redirect(url_for('loginView'))

    @injectable_route(app, '/login', methods=['GET', 'POST'])
    def loginView(self, view_props: ViewProps):
        # Clear session if user is already authenticated
        session.pop(os.getenv("AUTH_IDENTITY_KEY"), None)

        login_form = (
            LoginForm(Request().all())
            .set_submit_button_class("btn btn-primary")
            .set_submit_button_text("Login")
            .set_method("POST")
        )

        if request.method == "POST" and login_form.validate():
            return ADAuth().raven_driver(
                login_form.data[os.getenv("AUTH_IDENTITY_KEY")],
                login_form.data['password']
            )

        return render_template('users/templates/login.html', **view_props.compact())

    @injectable_route(app, '/logout', methods=['GET', 'POST'])
    def logoutView(self, view_props: ViewProps):
        session.clear()  # Clears session regardless of its state
        return redirect(url_for('loginView'))
