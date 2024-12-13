import re


def repair_phone(phone):
    """
    Repairs a phone number string to match the expected format: +380660132486.

    Parameters:
        phone (str): The input phone number as a string.

    Returns:
        str: The repaired phone number or None if input is invalid.
    """
    if not isinstance(phone, str):
        return None  # Return None if the input is not a string

    # Remove all non-digit characters except the '+' at the start
    phone = re.sub(r'[^\d+]', '', phone)

    # Add '+' at the beginning if it's missing
    if not phone.startswith('+'):
        phone = '+' + phone

    # Validate the result: Ensure it starts with '+' and only contains digits afterward
    if not re.fullmatch(r'\+\d+', phone):
        return None  # Invalid phone number format

    return phone


def round_to_thousands(value):
    try:
        # Attempt to convert to float
        num = float(value)
        if num > 1000:
            return round(num, -3)  # Round to nearest thousand
        return num
    except (ValueError, TypeError):
        # If conversion fails, return the original value
        return value
