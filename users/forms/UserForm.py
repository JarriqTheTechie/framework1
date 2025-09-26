from typing import List

from framework1.dsl.FormDSL.BaseField import BaseField
from framework1.dsl.FormDSL.DateField import DateField
from framework1.dsl.FormDSL.FieldGroup import FieldGroup
from framework1.dsl.FormDSL.Form import Form
from framework1.dsl.FormDSL.SelectField import SelectField
from framework1.dsl.FormDSL.TextField import TextField



class UserForm(Form):
    def __init__(self, data):
        from lib.handlers.users.UserController import UserController
        super().__init__(data)
        controller: UserController = UserController()
        self.set_submit_button_class("btn btn-dark mt-3").set_submit_button_style(
            "border-radius: 0 !important;").set_class("row border-bottom pb-3 border-top pt-3").detect_form_action(data, controller.UserStore, controller.UserUpdate)

    def schema(self) -> List[BaseField | FieldGroup]:
        return [
            FieldGroup(
                "User Information",
                fields=[
                    
                ]
            ).set_field_container_class("row mb-3").set_title_class("h6 fw-bold ps-0")
            .set_class("col-lg-3 px-4 mt-3"),
        ]


    