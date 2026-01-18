# framework1/dsl/EmailDSL.py
# ================================================================
# Email DSL for Framework1 — Declarative HTML Email Builder
# ================================================================

import os
import webbrowser
from typing import List, Any, Self

from framework1.core_services.OutlookCOM import Message
from reportlab.platypus import Paragraph


# ================================================================
# BASE CLASSES
# ================================================================

class Mailable:
    """
    Base class for all emails.
    Each subclass must implement a schema() method that returns DSL elements.
    """

    def __init__(self, data: dict = None, **kwargs):
        self.message: Message = Message()
        self.data = data or {}
        self.from_ = ""
        self.to_ = []
        self.body = ""
        self.cc = []
        self.attachments = []

    subject: str = ""

    def render(self) -> str:
        body = "".join(
            component.render() if hasattr(component, "render") else str(component)
            for component in self.schema()
        )
        return self._wrap(body)

    def _wrap(self, body: str) -> str:
        """Standard responsive, inline-safe email wrapper."""
        return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <title>{self.subject}</title>
  </head>
  <body style="margin:0;padding:0;background-color:#f8fafc;font-family:'Segoe UI', Helvetica, Arial, sans-serif;color:#333;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc;">
      <tr>
        <td align="center" style="padding:30px 15px;">
          <table cellpadding="0" cellspacing="0" width="640" style="max-width:640px;background:#fff;border-radius:8px;padding:32px;box-shadow:0 2px 6px rgba(0,0,0,0.05);">
            {body}
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

    # ------------------------------------------------------------
    # Email Sending Helpers
    # ------------------------------------------------------------

    def send_as(self, email: str) -> Self:
        self.from_ = email
        return self

    def add_recipient(self, email: str) -> Self:
        self.to_.append(email)
        return self

    def add_cc(self, email: str) -> Self:
        self.cc.append(email)
        return self

    def add_attachment(self, file_path: str) -> Self:
        self.attachments.append(file_path)
        return self

    def send(self) -> bool:
        """Send via Outlook COM."""
        self.body = self.render()
        self.message.using(self.from_).message(
            subject=self.subject,
            recipient=self.to_,
            CC=";".join(self.cc) if self.cc else None,
            body=self.body,
            attachments=self.attachments
        )
        return True

    # ------------------------------------------------------------
    # Template Preview Utility
    # ------------------------------------------------------------

    def preview(self, file_name: str = None, auto_open: bool = True) -> str:
        """
        Renders the email and saves it as an HTML file for quick visual inspection.

        Args:
            file_name (str): Optional custom filename (defaults to subject + .html)
            auto_open (bool): Automatically open the file in a web browser

        Returns:
            str: Path to the generated HTML preview file
        """
        html = self.render()
        if (file_name and file_name.lower().endswith(".html")) or (file_name and file_name.lower().endswith(".htm")):
            pass
        else:
            file_name = f"{file_name}.html" if file_name else None
        safe_title = (file_name or f"{self.subject or 'email_preview'}.html").replace(" ", "_")
        preview_path = os.path.join(os.getcwd(), safe_title)
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)
        if auto_open:
            webbrowser.open(f"file://{preview_path}")
        return preview_path



# ================================================================
# LAYOUT ELEMENTS
# ================================================================

class Email:
    """Top-level container grouping Header, Body, and Footer blocks."""

    def __init__(self, children: List[Any]):
        self.children = children

    def render(self) -> str:
        return "".join(child.render() for child in self.children)


class Header:
    def __init__(self, title: str, logo: "Logo" = None, align: str = "center", color: str = "#0066cc"):
        self.title = title
        self.logo = logo
        self.align = align
        self.color = color

    def render(self) -> str:
        logo_html = self.logo.render() if self.logo else ""
        return f"""
        <tr>
          <td align="{self.align}" style="border-bottom:2px solid {self.color};padding-bottom:16px;margin-bottom:24px;">
            {logo_html}
            <h1 style="color:{self.color};margin:12px 0 0 0;font-size:22px;">{self.title}</h1>
          </td>
        </tr>"""


class Body:
    def __init__(self, children: List[Any]):
        self.children = children

    def render(self) -> str:
        inner = "".join(child.render() for child in self.children)
        return f"""
        <tr>
          <td style="padding-top:24px;line-height:1.6;font-size:15px;color:#333;">
            {inner}
          </td>
        </tr>"""


class Footer:
    def __init__(self, text: str):
        self.text = text

    def render(self) -> str:
        return f"""
        <tr>
          <td align="center" style="font-size:12px;color:#777;padding-top:32px;border-top:1px solid #eee;">
            {self.text}
          </td>
        </tr>"""


# ================================================================
# CONTENT ELEMENTS
# ================================================================

class Paragraph:
    def __init__(self, text: str):
        self.text = text

    def render(self) -> str:
        return f'<p style="margin:0 0 16px 0;line-height:1.6;font-size:15px;color:#333;">{self.text}</p>'


class LoginBox:
    """Styled info box for login details or credentials."""

    def __init__(self, authentication_email: str):
        self.authentication_email = authentication_email

    def render(self) -> str:
        return f"""
        <table cellpadding="0" cellspacing="0" width="100%" style="background-color:#f1f5f9;border-left:4px solid #0066cc;padding:12px 16px;border-radius:6px;margin:20px 0;">
          <tr>
            <td>
              <p style="margin:0 0 8px 0;"><strong>Login Instructions:</strong></p>
              <p style="margin:0 0 4px 0;">Please login using the following credentials:</p>
              <ul style="padding-left:18px;margin:8px 0;">
                <li><strong>Authentication Email:</strong>
                  <a href="mailto:{self.authentication_email}" style="color:#0066cc;text-decoration:none;">
                    {self.authentication_email}
                  </a>
                </li>
                <li><strong>Password:</strong> Your workstation user account password</li>
              </ul>
            </td>
          </tr>
        </table>"""


class Divider:
    def __init__(self, color="#eee", margin="24px 0"):
        self.color = color
        self.margin = margin

    def render(self):
        return f'<hr style="border:none;border-top:1px solid {self.color};margin:{self.margin};" />'


class Button:
    """Bulletproof responsive email button (Outlook + Gmail safe)."""
    def __init__(self, text: str, href: str = "#", color: str = "#2b3138"):
        self.text = text
        self.href = href
        self.color = color

    def render(self) -> str:
        return f"""
        <!--Button-->
        <center>
          <table align="center" cellspacing="0" cellpadding="0" width="100%">
            <tr>
              <td align="center" style="padding: 10px;">
                <table border="0" class="mobile-button" cellspacing="0" cellpadding="0">
                  <tr>
                    <td align="center" bgcolor="{self.color}"
                        style="background-color: {self.color}; margin: auto; max-width: 600px;
                               -webkit-border-radius: 27px; -moz-border-radius: 27px; border-radius: 27px;
                               padding: 15px 20px;" width="100%">
                      <!--[if mso]>&nbsp;<![endif]-->
                      <a href="{self.href}" target="_blank"
                         style="font-size:16px; font-family: Helvetica, Arial, sans-serif;
                                color:#ffffff; font-weight:normal; text-align:center;
                                background-color:{self.color}; text-decoration:none;
                                border:none; -webkit-border-radius:27px; -moz-border-radius:27px;
                                border-radius:27px; display:inline-block; text-decoration: none;">
                        <span style="font-size:16px; font-family: Helvetica, Arial, sans-serif;
                                     color:#ffffff; font-weight:normal; line-height:1.5em;
                                     text-align:center;">{self.text}</span>
                      </a>
                      <!--[if mso]>&nbsp;<![endif]-->
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </center>
        """



class RawHTML:
    """Allows raw HTML insertion inside EmailDSL content lists."""

    def __init__(self, html: str):
        self.html = html

    def render(self) -> str:
        return self.html


# ================================================================
# BRANDING ELEMENTS
# ================================================================

class Logo:
    """Displays a company logo image at the top of the email."""

    def __init__(self, src: str, alt: str = "Company Logo", width: int = 120, display: str = "block"):
        self.src = src
        self.alt = alt
        self.width = width
        self.display = display

    def render(self) -> str:
        return f'<img src="{self.src}" alt="{self.alt}" width="{self.width}" style="display:{self.display};margin:0 auto 8px auto;" />'


class Signature:
    """Standardized sign-off block."""

    def __init__(self, name: str, title: str, company: str = None):
        self.name = name
        self.title = title
        self.company = company

    def render(self) -> str:
        company_line = f"<br>{self.company}" if self.company else ""
        return f"""
        <p style="margin-top:16px;margin-bottom:0;line-height:1.6;">
            Best regards,<br>
            <strong>{self.name}</strong><br>
            {self.title}{company_line}
        </p>"""


# ================================================================
# EXAMPLE IMPLEMENTATION
# ================================================================

class QuantiosOnboardingEmail(Mailable):
    """
    EBBL/ETBL Quantios Onboarding Email
    Reproduces the inline-HTML onboarding template using the Email DSL.
    """

    subject = "EBBL/ETBL Quantios Onboarding"

    def __init__(self, data: dict):
        self.data = data

    def schema(self):
        name = self.data.get("full_name", "User")
        email = self.data.get("authentication_email", "user@example.com")
        year = self.data.get("current_year", 2025)

        return [
            Email([
                Header(
                    "EBBL/ETBL Quantios Onboarding",
                    logo=Logo(
                        "https://equitybanksslacct.com/images/Equity-Logo.png",
                        alt="Equity Bank Bahamas Logo",
                        width=100
                    ),
                ),
                Body([
                    Paragraph(f"Dear {name},"),
                    Paragraph(
                        "Welcome aboard! Your account has been successfully created, and you can now access the <strong>Quantios Core</strong> platform to manage your operations efficiently."
                    ),
                    LoginBox(email),
                    Button(
                        "Go to Quantios Core",
                        "https://businesscentral.dynamics.com/d68c0ffa-00b3-4181-b8cb-f31e68f88de6/Production?company=Equity%20Trust%20Bahamas%20Limited"
                    ),
                    Paragraph(
                        'If you encounter any issues signing in, please contact the IT team at '
                        '<a href="mailto:it@equitybahamas.com" style="color:#0066cc;text-decoration:none;">it@equitybahamas.com</a>.'
                    ),
                    Paragraph("We are excited to have you on board!"),
                    Signature(
                        name="The Equity IT Team",
                        title="Information Technology Department",
                        company="Equity Bank Bahamas Limited"
                    ),
                ]),
                Footer(f"{year} EBBL/ETBL. All rights reserved."),
            ])
        ]


# ================================================================
# USAGE EXAMPLE
# ================================================================

if __name__ == "__main__":
    data = {
        "full_name": "Jarriq Rolle",
        "authentication_email": "jrolle@equitybahamas.com",
        "current_year": 2025,
    }

    email = QuantiosOnboardingEmail(data)
    html = email.render()
    print(html)
