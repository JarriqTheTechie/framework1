from flask import session, flash, redirect, url_for

from framework1.dsl.FormDSL.Form import Form


class FormHandler:
    @staticmethod
    def validate_and_redirect(form, request, redirect_view, **kwargs):
        """
        Validate the form. If errors exist, store them in session and redirect.
        Otherwise, return True to proceed with form submission.
        """
        if not form.validate():
            session[f'{form.__class__.__name__}_form_errors'] = form.errors
            session[f'{form.__class__.__name__}_form_data'] = request.all()
            return redirect(url_for(redirect_view, **kwargs))
        return True

    @staticmethod
    def restore_form(form_class: Form, default_data=None):
        """
        Restore form data and errors from session.
        """
        form_data = session.pop(f'{form_class.__class__.__name__}_form_data', default_data or {})
        form_errors = session.pop(f'{form_class.__class__.__name__}_form_errors', None)

        form = form_class.set_data(form_data)
        if form_errors:
            form.errors = form_errors  # Inject stored errors

        return form
