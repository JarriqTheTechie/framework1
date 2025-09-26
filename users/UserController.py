from app import app
from flask import render_template, abort
from framework1.core_services.Request import Request
from framework1.core_services.ViewProps import ViewProps
from framework1.service_container._Injector import injectable_route
from lib.handlers.users.forms.UserForm import UserForm
from lib.handlers.users.tables.UserTable import UserTable
from lib.handlers.users.models.User import User
from flask import redirect, url_for

class UserController:
    def __init__(self):
        pass
    
    def GetNavigation(self):
        return [
            dict(
                title="Users",
                url=url_for('UserIndex'),
                icon="ri-question-line",
                weight=0,
                visible=True,
                group=None,
                group_icon=None,
            )
        ]

    @injectable_route(app, '/users', methods=['GET'])
    def UserIndex(self, view_props: ViewProps, request: Request):
        page_title = "Users"
        table = UserTable().paginate(per_page=10)
        return render_template('users/templates/index.html', **view_props.compact())

    @injectable_route(app, '/users/<id>', methods=['GET'])
    def UserDetails(self, id: int,view_props: ViewProps, request: Request):
        page_title = "User Details"
        resource = User().find(id)
        form = UserForm(resource.to_dict())
        return render_template('users/templates/details.html', **view_props.compact())                

    @injectable_route(app, '/users/create', methods=['GET'])
    def UserCreate(self, view_props: ViewProps, request: Request):
        page_title = "Create User"
        form = UserForm(request.all())
        return render_template('users/templates/create.html', **view_props.compact())

    @injectable_route(app, '/users/create', methods=['POST'])
    def UserStore(self, view_props: ViewProps, request: Request):
        resource = User().create(**request.all())
        return redirect(url_for('UserDetails', id=resource.id))

    @injectable_route(app, '/users/<id>/update', methods=['GET'])
    def UserEdit(self, view_props: ViewProps, request: Request):
        page_title = "Edit User"
        form = UserForm(request.all())
        return render_template('users/templates/edit.html', **view_props.compact())

    @injectable_route(app, '/users/<id>/update', methods=['POST'])
    def UserUpdate(self, id: int,view_props: ViewProps, request: Request):
        resource = User().find(id)
        resource.update(request.all())
        return redirect(url_for('UserDetails', id=resource.id))


