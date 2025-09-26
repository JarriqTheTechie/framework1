RULES = {}


def register_rule(name):
    def wrapper(fn):
        RULES[name] = fn
        return fn

    return wrapper


@register_rule("required")
def required_rule(field, value):
    if value in (None, "", [], {}):
        return f"{field} is required"


@register_rule("email")
def email_rule(field, value):
    import re
    if value and not re.match(r"^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$", str(value)):
        return f"{field} must be a valid email address"


def min_length_rule(length):
    @register_rule(f"min_length:{length}")
    def rule(field, value):
        if value and len(str(value)) < length:
            return f"{field} must be at least {length} characters"

    return rule


@register_rule("numeric")
def numeric_rule(field, value):
    try:
        float(value)
    except (ValueError, TypeError):
        return f"{field} must be numeric"


def confirmed_rule(matching_field):
    @register_rule(f"confirmed:{matching_field}")
    def rule(field, value, all_data=None):
        if all_data and value != all_data.get(matching_field):
            return f"{field} must match {matching_field}"

    return rule


def get_rule(name):
    if name in RULES:
        return RULES[name]
    elif name.startswith("min_length:"):
        return min_length_rule(int(name.split(":")[1]))
    elif name.startswith("confirmed:"):
        return confirmed_rule(name.split(":")[1])
    return None
