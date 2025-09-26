import pprint
from enum import Enum

import pythoncom
import win32com.client
from dataclasses import dataclass


@dataclass
class TMessage:
    Subject: str
    SenderName: str
    SenderEmail: str
    Body: str
    ReceivedTime: str


class OutlookCOMProperty(Enum):
    ReceivedTime = "[ReceivedTime]"
    SentOn = "[SentOn]"
    CreationTime = "[CreationTime]"
    LastModificationTime = "[LastModificationTime]"
    EntryID = "[EntryID]"
    MessageClass = "[MessageClass]"
    SenderEmailAddress = "[SenderEmailAddress]"
    SenderEmailType = "[SenderEmailType]"
    SenderName = "[SenderName]"
    Subject = "[Subject]"
    Size = "[Size]"
    Attachments = "[Attachments]"
    Importance = "[Importance]"
    Sensitivity = "[Sensitivity]"
    FlagStatus = "[FlagStatus]"
    Unread = "[Unread]"
    FlagIcon = "[FlagIcon]"
    To = "[To]"
    Cc = "[Cc]"
    Bcc = "[Bcc]"
    Categories = "[Categories]"


class OutlookCOMSortOrder(Enum):
    Ascending = False
    Descending = True


class OutlookCOM:
    """
    A class to interact with Outlook using the win32com library.

    example:
        Getting messages from the Inbox folder of a mailbox:
        mail = OutlookCOM().get_folder("johndoe@example.com").get_messages()

    """

    def __init__(self):
        try:
            self.outlook = win32com.client.GetActiveObject("Outlook.Application", pythoncom.CoInitialize())
        except:
            self.outlook = win32com.client.Dispatch("Outlook.Application", pythoncom.CoInitialize())
        self.mapi = self.outlook.GetNamespace("MAPI")
        self.session = self.outlook.Session


class Mailbox(OutlookCOM):
    def __init__(self):
        super().__init__()
        self.store = None
        self.mailbox = None
        self.inbox = None

    def using(self, mailbox: str):
        self.mailbox = mailbox
        self.store = self.mapi.Stores(mailbox)
        return self


class Message(Mailbox):
    def __init__(self):
        super().__init__()
        self.messages = None
        self.sort_by = "[ReceivedTime]"
        self.sort_order = True
        self.filter_builder: str | None = None

    def folder(self, folder_name: str = "Inbox"):
        if folder_name == "Inbox":
            self.inbox = self.store.GetDefaultFolder(6)
            self.messages = self.inbox.Items
            return self

        if "." in folder_name:
            nested_folder_current_index = 0
            folder_name = folder_name.split(".")
            self.inbox = self.store.GetDefaultFolder(6)
            for folder in folder_name:
                if nested_folder_current_index == 0 and folder == "Inbox":
                    nested_folder_current_index += 1
                    continue
                self.inbox = self.inbox.Folders[folder]
                self.messages = self.inbox.Items
            return self

        self.inbox = self.store.GetDefaultFolder(6).Folders[folder_name]
        self.messages = self.inbox.Items
        return self

    def sort(self, sort_type: OutlookCOMProperty = OutlookCOMProperty.ReceivedTime,
             sort_order: OutlookCOMSortOrder = OutlookCOMSortOrder.Descending):
        self.sort_by = sort_type.value
        self.sort_order = sort_order.value
        return self

    def fetch(self, limit=1_000_000) -> list[TMessage]:
        self.compile_filter()
        returnable: list[TMessage] = []
        # Limit the number of messages to return
        for msg in self.messages:
            if len(returnable) < limit:
                returnable.append(
                    TMessage(
                        msg.Subject,
                        msg.SenderName,
                        self.resolve_message_sender(msg),
                        msg.Body,
                        msg.ReceivedTime
                    )
                )
            else:
                break
        return returnable

    def first(self) -> TMessage:
        self.compile_filter()
        first_message = self.messages.GetFirst()
        return TMessage(
            first_message.Subject,
            first_message.SenderName,
            self.resolve_message_sender(first_message),
            first_message.Body,
            first_message.ReceivedTime
        )

    def last(self) -> TMessage:
        self.compile_filter()
        last_message = self.messages.GetLast()
        return TMessage(
            last_message.Subject,
            last_message.SenderName,
            self.resolve_message_sender(last_message),
            last_message.Body,
            last_message.ReceivedTime
        )

    def where(self, property: OutlookCOMProperty, value, operator="="):
        if self.filter_builder:
            self.filter_builder += f" AND {property.value} {operator} '{value}'"
        else:
            self.filter_builder = f"{property.value} {operator} '{value}'"
        return self

    def or_where(self, property: OutlookCOMProperty, value, operator="="):
        if self.filter_builder:
            self.filter_builder += f" OR {property.value} {operator} '{value}'"
        else:
            self.filter_builder = f"{property.value} {operator} '{value}'"
        return self

    def where_date(self, value):
        if self.filter_builder:
            self.filter_builder += f" AND ([ReceivedTime] >= '{value} 12:00 AM' AND [ReceivedTime] < '{value} 11:59 PM')"
        else:
            self.filter_builder = f"([ReceivedTime] >= '{value} 12:00 AM' AND [ReceivedTime] < '{value} 11:59 PM')"
        return self

    def or_where_date(self, value):
        if self.filter_builder:
            self.filter_builder += f" OR ([ReceivedTime] >= '{value} 12:00 AM' OR [ReceivedTime] < '{value} 11:59 PM')"
        else:
            self.filter_builder = f"([ReceivedTime] >= '{value} 12:00 AM' OR [ReceivedTime] < '{value} 11:59 PM')"
        return self

    def where_date_between(self, start, end):
        if self.filter_builder:
            self.filter_builder += f" AND ([ReceivedTime] >= '{start} 12:00 AM' AND [ReceivedTime] < '{end} 11:59 PM')"
        else:
            self.filter_builder = f"([ReceivedTime] >= '{start} 12:00 AM' AND [ReceivedTime] < '{end} 11:59 PM')"
        return self

    def or_where_date_between(self, start, end):
        if self.filter_builder:
            self.filter_builder += f" OR ([ReceivedTime] >= '{start} 12:00 AM' OR [ReceivedTime] < '{end} 11:59 PM')"
        else:
            self.filter_builder = f"([ReceivedTime] >= '{start} 12:00 AM' OR [ReceivedTime] < '{end} 11:59 PM')"
        return self

    def compile_filter(self):
        if self.filter_builder:
            self.messages = self.messages.Restrict(self.filter_builder)
        #pprint.pp(self.__dict__)
        return self

    @classmethod
    def resolve_message_sender(cls, message):
        sender = message.Sender
        if message.SenderEmailType == "EX":  # If it's an Exchange address
            exch_user = sender.GetExchangeUser()
            if exch_user:
                email_address = exch_user.PrimarySmtpAddress
            else:
                email_address = "Unable to resolve Exchange user"
        else:
            email_address = message.SenderEmailAddress  # External addresses (SMTP)
        return email_address

    def resolve_email_address_to_exchange_user(self, email_address):
        exchange_user = self.session.CreateRecipient(email_address).AddressEntry.GetExchangeUser()
        return exchange_user

    def message(self, subject: str, body, recipient: str, attachments: list[str] = None, CC: str = None):
        if isinstance(recipient, list):
            recipient = ";".join(recipient)
        mailItem = self.outlook.CreateItem(0)
        mailItem.Display()
        mailItem.SentOnBehalfOfName = self.mailbox

        mailItem.Subject = subject
        mailItem.HTMLbody = body
        mailItem.To = recipient
        mailItem.CC = CC if CC else ""
        if attachments:
            for attachment in attachments:
                mailItem.Attachments.Add(attachment)


        try:
            mailItem.Send()
        except Exception as e:
            if "You do not have the permission to send the message on behalf of the specified user." in str(e):
                raise ValueError("You do not have the permission to send the message on behalf of the specified user.")
            raise e



# mail = Message().using("johndoe@example.com").folder().where(
#     OutlookCOMProperty.Subject, "ONLINE ACCESS"
# ).fetch()
# print(mail)
