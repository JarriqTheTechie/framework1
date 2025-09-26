import os
import pprint
import socket

import pywintypes
import win32api
import win32con
import win32security
from flask import session, request, redirect, url_for, abort

from framework1.database.QueryBuilder import QueryBuilder
from framework1.utilities.DataKlass import DataKlass

from lib.handlers.users.models.User import User
from lib.services.ClientDatabase import ClientDatabase


class Impersonate:
    def __init__(self, login, password, domain):
        self.domain = domain
        self.login = login
        self.password = password

    def logon(self):
        self.handle = win32security.LogonUser(self.login, self.domain, self.password,
                                              win32con.LOGON32_LOGON_INTERACTIVE, win32con.LOGON32_PROVIDER_DEFAULT)
        win32security.ImpersonateLoggedOnUser(self.handle)

    def logoff(self):
        win32security.RevertToSelf()  # terminates impersonation
        self.handle.Close()  # guarantees cleanup


def tenant_resolver(user) -> str:
    match user.Department:
        case _:
            return "YOUR TENANT ID HERE"


class ADAuth:
    @staticmethod
    def raven_driver(username, password):
        username = username.lower()
        domain = os.environ.get("AUTH_LDAP_DOMAIN")

        # Get user IP Address
        try:
            ip = str(socket.gethostbyaddr(request.remote_addr)[0])
        except socket.herror:
            ip = 'Unresolved'
        try:
            token = win32security.LogonUser(
                username,
                domain,
                password,
                win32security.LOGON32_LOGON_NETWORK,
                win32security.LOGON32_PROVIDER_DEFAULT)
            authenticated = bool(token)
            if authenticated:
                session[os.getenv("AUTH_IDENTITY_KEY")] = username
                impersonator = Impersonate(username, password, domain)

                # Get Username by impersonating user
                impersonator.logon()
                fullname = win32api.GetUserNameEx(3)
                impersonator.logoff()
                session['FullName'] = fullname
                try:
                    primacy_user = DataKlass(User().where("UserId", "=", username).first().to_dict())
                except IndexError:
                    abort(403)

                session['Role'] = primacy_user.Role
                session['TenantId'] = tenant_resolver(primacy_user)
                session[os.getenv('AUTH_DB_IDENTITY_COLUMN')] = primacy_user.UserId
                session['Email'] = primacy_user.UserId + f"@{os.getenv('MAIL_FROM_DOMAIN')}"
                session['BusinessPartyId'] = primacy_user.BusinessPartyId
                return redirect(url_for(os.getenv('AUTH_LOGIN_REDIRECT_VIEW')))
        except pywintypes.error:
            # rollbar.report_message(f"Login Failed for {username} on IP: {ip}", "error")
            return redirect(url_for('loginView'))
