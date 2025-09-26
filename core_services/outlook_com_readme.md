# OutlookCOM

A thin, chainable wrapper around **Microsoft Outlook** (via `pywin32`) for reading, filtering, and sending email from Python on Windows. It exposes a small, fluent API focused on:

- Selecting a mailbox and folders (including nested paths)
- Building Outlook `Items.Restrict` filters with AND/OR and date helpers
- Fetching messages or just the first/last item
- Resolving Exchange senders to SMTP
- Composing and sending messages (including on‑behalf‑of and attachments)

> **Scope:** This README documents only the methods and types defined in `OutlookCOM.py`. It does not assume any other helpers.

---

## Requirements

- Windows with Microsoft Outlook installed and configured (MAPI profile)
- Python 3.10+
- `pywin32` (installs `pythoncom` and `win32com`)

```bash
pip install pywin32
```

> **Note:** Outlook bitness (32‑bit vs 64‑bit) should match your Python interpreter for best compatibility.

---

## Installation & Import

Place `OutlookCOM.py` in your project and import the types you need:

```python
from OutlookCOM import Message, OutlookCOMProperty, OutlookCOMSortOrder, TMessage
```

---

## Quick start

Fetch the most recent 10 messages from your Inbox:

```python
from OutlookCOM import Message, OutlookCOMProperty

messages = (
    Message()
        .using("your.mailbox@company.com")
        .folder("Inbox")
        .where(OutlookCOMProperty.Unread, "False")  # strings are quoted internally
        .fetch(limit=10)
)

for m in messages:
    print(m.ReceivedTime, m.SenderEmail, m.Subject)
```

Send a basic email (on behalf of the selected mailbox), with an attachment:

```python
(
    Message()
        .using("your.mailbox@company.com")
        .message(
            subject="Daily report",
            body="<p>Please find today’s report attached.</p>",
            recipient=["ops@company.com", "team@company.com"],
            attachments=[r"C:\\Reports\\daily.pdf"],
            CC="lead@company.com",
        )
)
```

---

## Core types

### `TMessage`

A plain dataclass returned by fetchers:

```python
@dataclass
class TMessage:
    Subject: str
    SenderName: str
    SenderEmail: str
    Body: str
    ReceivedTime: str
```

### `OutlookCOMProperty` (selected)

Properties usable in `.where()`/`.or_where()`:

- `ReceivedTime`, `SentOn`, `CreationTime`, `LastModificationTime`
- `EntryID`, `MessageClass`
- `SenderEmailAddress`, `SenderEmailType`, `SenderName`
- `Subject`, `Size`, `Attachments`, `Importance`, `Sensitivity`
- `FlagStatus`, `Unread`, `FlagIcon`
- `To`, `Cc`, `Bcc`, `Categories`

### `OutlookCOMSortOrder`

- `Ascending`, `Descending`

> Sorting options are recorded by `.sort()` (see details below), but the current implementation does not apply them to the Outlook `Items` collection.

---

## API reference (fluent chain)

All chains begin with `Message()` and then:

### `.using(mailbox: str)` → `Message`

Selects the mailbox store by display name or SMTP address (as configured in Outlook).

```python
mail = Message().using("your.mailbox@company.com")
```

### `.folder(folder_name: str = "Inbox")` → `Message`

Selects a folder within the chosen mailbox. Supports:

- Default Inbox: `.folder()` or `.folder("Inbox")`
- Direct child: `.folder("Processed")`
- Nested path using dots (rooted at Inbox): `.folder("Inbox.Archive.2025")`

```python
mail = Message().using("your.mailbox@company.com").folder("Inbox.Reports.Daily")
```

### `.where(property: OutlookCOMProperty, value, operator: str = "=")` → `Message`

Adds an **AND** condition to the filter.

```python
mail = (
    Message().using("your.mailbox@company.com").folder()
        .where(OutlookCOMProperty.Subject, "Invoice")
        .where(OutlookCOMProperty.Unread, "True")  # pass strings; values are quoted
)
```

### `.or_where(property, value, operator: str = "=")` → `Message`

Adds an **OR** condition to the filter.

```python
mail = (
    Message().using("your.mailbox@company.com").folder()
        .where(OutlookCOMProperty.Subject, "Invoice")
        .or_where(OutlookCOMProperty.Subject, "Receipt")
)
```

> **Operators:** Values are interpolated into Outlook’s Restrict filter as `… <op> 'value'`. Use operators supported by Outlook (e.g., `=`, `<>`). If you attempt `LIKE`/wildcards, behavior depends on Outlook filter semantics and may not work—prefer exact matches or date helpers below.

### Date helpers

All helpers filter by the `ReceivedTime` property and **append** to the active filter:

- `.where_date(value: str)` – same‑day window: `12:00 AM` to `< 11:59 PM`
- `.or_where_date(value: str)` – OR a same‑day window
- `.where_date_between(start: str, end: str)` – inclusive start, **exclusive** end at `11:59 PM`
- `.or_where_date_between(start: str, end: str)` – OR a date range

```python
mail = (
    Message().using("your.mailbox@company.com").folder()
        .where_date("08/01/2025")
        .or_where_date("08/02/2025")
)
```

> **Date format:** Pass dates in your Windows/Outlook locale (commonly `MM/DD/YYYY`). The library concatenates strings like `"08/10/2025 12:00 AM"`.

### `.sort(sort_type: OutlookCOMProperty = ReceivedTime, sort_order: OutlookCOMSortOrder = Descending)` → `Message`

Stores sort intent (property + order). **Current limitation:** sorting is not applied to `Items`; `GetFirst()`/`GetLast()` therefore reflect Outlook’s current folder view sort, not the `.sort()` call.

### `.fetch(limit: int = 1_000_000)` → `list[TMessage]`

Compiles the filter (if any) with `Items.Restrict(...)` and returns up to `limit` messages as `TMessage` objects.

```python
latest_20 = (
    Message().using("your.mailbox@company.com").folder("Inbox.Processing")
        .where_date_between("08/01/2025", "08/10/2025")
        .fetch(limit=20)
)
```

### `.first()` / `.last()` → `TMessage`

Compiles the filter (if any) and returns the first/last item from the (possibly restricted) `Items` collection.

```python
first_today = (
    Message().using("your.mailbox@company.com").folder().where_date("08/10/2025").first()
)

last_today = (
    Message().using("your.mailbox@company.com").folder().where_date("08/10/2025").last()
)
```

### `.resolve_email_address_to_exchange_user(email_address: str)` → `ExchangeUser | None`

Looks up an Exchange recipient in the current session and returns its `ExchangeUser` COM object (or `None` if resolution fails).

```python
ex_user = Message().using("your.mailbox@company.com").resolve_email_address_to_exchange_user("colleague@company.com")
if ex_user:
    print(ex_user.PrimarySmtpAddress)
```

> The library also resolves senders automatically in fetchers: if the sender is type `EX`, it maps to `PrimarySmtpAddress`; otherwise it uses `SenderEmailAddress`.

### `.message(subject: str, body, recipient: str | list[str], attachments: list[str] | None = None, CC: str | None = None)` → `None`

Creates, **displays**, and sends an Outlook mail item **on behalf of** the selected mailbox.

- `recipient` may be a string or a list; lists are joined with semicolons
- `body` is assigned to `HTMLBody`
- `SentOnBehalfOfName` is set to the mailbox from `.using(...)`
- Each path in `attachments` is added to the item
- If Outlook denies on‑behalf‑of rights, a `ValueError` is raised with a relevant message

```python
Message().using("shared.box@company.com").message(
    subject="Access request",
    body="<p>Kindly review.</p>",
    recipient="security@company.com",
    attachments=[r"C:\\temp\\evidence.png"],
)
```

> **Automation note:** The current implementation calls `mailItem.Display()` before sending, which opens a window. This is convenient for review but not ideal for unattended scripts.

---

## Usage patterns & best practices

1. **Always select a mailbox before anything else**

   ```python
   chain = Message().using("your.mailbox@company.com")
   ```

2. **Use dot‑notation for nested folders under Inbox**

   ```python
   chain.folder("Inbox.Clients.Acorn")
   ```

3. **Prefer exact matches in **`` Outlook’s `Restrict` is precise; do not rely on wildcard behavior unless you’ve validated it.

4. **Quote handling** Since values are injected as `'value'`, escape single quotes in your inputs:

   ```python
   subject_value = "O'Brien invoice".replace("'", "''")
   chain.where(OutlookCOMProperty.Subject, subject_value)
   ```

5. **Booleans as strings** Pass `'True'`/`'False'` (strings) to match the library’s quoting behavior:

   ```python
   chain.where(OutlookCOMProperty.Unread, "True")
   ```

6. **Date inputs in local format** Use `MM/DD/YYYY` (typical on Windows) to avoid locale parsing surprises.

7. **Restrict early, then limit** Build filters before `.fetch(limit=...)` to let Outlook reduce the result set efficiently.

8. **Expect UI on send** `.message(...)` opens the inspector window; plan for interactive execution.

---

## Cookbook

### Get the latest 5 invoices from a nested folder (this week)

```python
from datetime import date, timedelta
from OutlookCOM import Message, OutlookCOMProperty

start = (date.today() - timedelta(days=6)).strftime("%m/%d/%Y")
end   = date.today().strftime("%m/%d/%Y")

invoices = (
    Message()
        .using("ap@company.com")
        .folder("Inbox.Invoices.Vendors")
        .where(OutlookCOMProperty.Subject, "Invoice")
        .where_date_between(start, end)
        .fetch(limit=5)
)
```

### Combine AND/OR subject filters

```python
ap = (
    Message()
        .using("ap@company.com").folder()
        .where(OutlookCOMProperty.Subject, "Invoice")
        .or_where(OutlookCOMProperty.Subject, "Receipt")
        .fetch(limit=50)
)
```

### First and last today

```python
m = Message().using("ops@company.com").folder().where_date("08/10/2025")
first_msg = m.first()
last_msg  = m.last()
```

### Resolve an Exchange user for a given SMTP address

```python
m = Message().using("ops@company.com")
user = m.resolve_email_address_to_exchange_user("anyone@company.com")
if user:
    print(user.Name, user.PrimarySmtpAddress)
```

### Send an email with multiple recipients and CC

```python
Message().using("ops@company.com").message(
    subject="Outage notice",
    body="<p>We are investigating the issue.</p>",
    recipient=["team@company.com", "it@company.com"],
    CC="lead@company.com"
)
```

---

## Edge cases & gotchas

- **Sorting is not enforced** `.sort(...)` records your intent but does not call Outlook’s `Items.Sort`. Consequently, `.first()`/`.last()` reflect the folder’s current view sort, not your `.sort()` call.

- **Date OR helpers broaden results** `.or_where_date(...)` and `.or_where_date_between(...)` internally use `OR` within the date range expression, which can return a much larger set than expected. Prefer `.where_date(...)` / `.where_date_between(...)` for tight windows, or combine with additional `.where(...)` clauses.

- **End‑of‑day exclusivity** Date range helpers end at `< 11:59 PM`. Messages with timestamps between `11:59:00 PM` and `11:59:59 PM` may be excluded. If that matters, run an additional `.or_where_date(next_day)`.

- **Locale‑sensitive date parsing** Outlook parses the date strings using your system locale. Mismatched formats (e.g., `YYYY‑MM‑DD`) may silently return zero results.

- **Quoted values** All values are wrapped in single quotes. For numeric or boolean comparisons, Outlook might accept the quoted literal, but behavior can vary. When in doubt, pass strings like `'True'`/`'False'` and exact string numbers.

- **On‑behalf‑of permissions** Sending sets `SentOnBehalfOfName` to the mailbox provided to `.using(...)`. If you lack delegate rights, a `ValueError` is raised with a clear message.

- **Interactive send** `.message(...)` calls `Display()` before `Send()`, opening a window.

- **Attachment paths** Ensure absolute paths exist; Outlook will raise if a file is missing.

- **Mailbox name must match Outlook** `.using(...)` looks up `self.mapi.Stores(mailbox)`. The argument must match a configured store’s display name/SMTP address.

---

## Troubleshooting

- **No results from **``

  - Verify the folder path and mailbox name.
  - Simplify filters (try only `.folder().fetch(1)`).
  - Check date format/locale.

- **Wrong sender address on Exchange** The library already resolves Exchange (`EX`) senders to `PrimarySmtpAddress`. If you still see unusual values, the original item may lack a resolvable Exchange user.

- **Permission error when sending** Confirm delegate or send‑as rights to the target mailbox.

---

## FAQ

**Q: Can I search subfolders recursively?**\
A: Not with the current API. Select one folder at a time (dot notation is supported).

**Q: Can I paginate?**\
A: Use `.fetch(limit=...)` and manage offsets manually by adjusting filters (e.g., ReceivedTime windows).

**Q: Can I change the sort order?**\
A: `.sort(...)` stores your preference but is not applied internally yet; `.first()`/`.last()` follow the folder’s current view.

---

## Copyright & License

This documentation covers `OutlookCOM.py` as provided. License is determined by your project; include one if needed.

