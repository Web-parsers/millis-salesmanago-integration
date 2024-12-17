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
    str_value = str(value).strip().lower()

    # Check if ends with 'k'
    if str_value.endswith('k'):
        # Remove 'k', parse as float and multiply by 1000
        num_str = str_value[:-1]
        num = float(num_str) * 1000
        # Convert to int and format with commas
        return f"{int(num):,}"

    # Check if ends with '+'
    if str_value.endswith('+'):
        # Remove '+', parse the number, then restore '+'
        num_str = str_value[:-1]
        num = float(num_str)
        # Just format with commas and re-append '+', no rounding
        if num.is_integer():
            return f"{int(num):,}+"
        else:
            return f"{num:,}+"

    # For regular numbers
    try:
        num = float(str_value)
        if num > 1000:
            # Round to nearest thousand
            rounded = round(num, -3)
            return f"{int(rounded):,}"
        # If 1000 or less, return as is
        return num if not num.is_integer() else int(num)
    except ValueError:
        # If it's not a valid number, return the original value
        return value


