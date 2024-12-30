import asyncio
import hashlib
import json
import os
import time
import traceback
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Query
import requests
from pydantic import BaseModel
from dotenv import load_dotenv

from postgres_salesmanago_requests import get_people_by_phone
from utils import repair_phone, round_to_thousands

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import phonenumbers
from phonenumbers import timezone
from datetime import datetime, timedelta
import pytz

load_dotenv()  # take environment variables from .env.

agents_per_country = {
    'UK': os.getenv('agent_id_UK'),
    'GB': os.getenv('agent_id_UK'),
    'US': os.getenv('agent_id_US'),
    'FR': os.getenv('agent_id_FR'),
    'DE': os.getenv('agent_id_DE'),
    'FI': os.getenv('agent_id_FI'),
}

phone_from_country = {
    'UK': os.getenv('phone_from_UK'),
    'GB': os.getenv('phone_from_UK'),
    'US': os.getenv('phone_from_US'),
    'FR': os.getenv('phone_from_FR'),
    'DE': os.getenv('phone_from_DE'),
    'FI': os.getenv('phone_from_FI'),
}


class SalesmanagoPayload(BaseModel):
    id: str
    name: str
    description: str
    contactId: str
    email: str
    phone: str
    company: str


from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)

# Allow specific domains
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.get("/")
async def read_root():
    return {"message": "Welcome to the API"}


# Prefetch Data Webhook (GET request)
@app.get("/prefetch_data_webhook")
async def prefetch_data(
        to: str,
        from_: str = Query(..., alias="from"),
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None
):
    print(f"from: {from_}, to: {to}, session_id: {session_id}, agent_id: {agent_id}")

    # Extract client phone number
    client_phone = from_
    print(f"client_phone = {client_phone}")

    # Query the database for the phone number
    response = get_people_by_phone(client_phone)
    print(f"response = {response}")

    # Handle empty response
    if not response:
        return {}

    # Simulate some prefetch data
    metadata = get_contact_name(response[0].get('Email'))
    print(f"metadata = {metadata}")

    result = {
        "metadata": {
                        "email": response[0].get('Email'),
                        "EmailAddress": response[0].get('Email'),
                        "name": response[0].get('Name')
                    } | metadata  # Merging metadata
    }
    print(f"prefetch result: {result}")
    return result


def insert(text, api_name):
    try:
        url_insert = f"{os.getenv('server_url')}/insert-data"
        payload_insert = json.dumps({
            "table_name": "millis_responses_poc",
            "data": [
                {
                    "column_name": "responses",
                    "column_data": text
                },
                {
                    "column_name": "api_name",
                    "column_data": api_name
                }
            ]
        })
        headers_insert = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

        response_insert = requests.request("POST", url_insert, headers=headers_insert, data=payload_insert)
        print(f'response_insert.text = {response_insert.text}')
    except:
        print(traceback.format_exc())
        print(f'Failed to store into DB')


# End-of-Call Webhook (POST request)
@app.post("/session_data_webhook")
async def end_of_call(request: Request):
    # Parse the incoming JSON payload
    payload = await request.json()
    print("Webhook Payload Received:", payload)

    insert(payload, api_name='end_of_call')

    booking = None
    booking_info = 'No info'
    call_status = payload.get('call_status', '')
    error_message = payload.get('error_message')

    tools_calling = payload.get('function_calls', [])
    for tool in tools_calling:
        if tool.get('name') == 'book_meeting_slot':
            result = tool.get('result', '')
            if 'Failed' in result:
                booking = 'Failed'
            else:
                booking = 'Success'
            booking_info = result

    engagement = 'ToBeFilled'

    tags = ['SEOSENSE_TALKED']
    if booking == 'Success':
        tags.append('SEOSENSE_MEETING')
    else:
        tags.append('SEOSENSE_MEETING_FAILED')
    tags.append(f'MILLIS_{call_status.upper()}')

    print(f"payload.get('call_analysis') = {payload.get('call_analysis')}")
    if payload.get('call_analysis', {}).get('opt_out_detection'):
        tags.append('MILLIS_DNC')

    try:
        email = payload.get('metadata', {}).get('email')
    except:
        email = None
    print(f'tags = {tags}, email = {email}')
    update_tag_salesmanago(email, tags)

    result = {
        "received_payload": payload,
        "stats": {
            "booking": booking,
            "booking_info": booking_info,
            "engagement": engagement,
            "call_status": call_status,
            "error_message": error_message,
            "recording_url": payload.get('recording', {}).get('recording_url', '')
        }
    }
    insert(result, api_name='end_of_call_structured')
    return result


def get_contact_name(contact_email):
    request_time = int(time.time() * 1000)

    payload = {
        'clientId': os.getenv('CLIENT_ID'),
        'apiKey': os.getenv('API_KEY'),
        'requestTime': request_time,
        'sha': os.getenv('sha'),
        'owner': os.getenv('OWNER_EMAIL'),
        'email': [contact_email]
    }

    print(f"payload = {payload}")

    try:
        response = requests.post(
            "https://app3.salesmanago.pl/api/contact/list",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        contact_data = response.json()
        print(f"contact_data = {contact_data}")

        data = response.json().get('contacts', [{}])[0]
        name = data.get('name')
        dct = data.get('properties', {})
        result = {item['name']: item['value'] for item in dct}
        traffic = round_to_thousands(result.get('traffic'))
        keywords = round_to_thousands(result.get('keywords'))
        package = round_to_thousands(result.get('package'))

        clients = round_to_thousands(result.get('clients'))
        package_short = round_to_thousands(result.get('package_short'))

        return {
            "Name": name,
            "CompanyName": data.get('company'),
            "traffic": traffic,
            "keywords": keywords,
            "package": package,
            "tags": [x.get('tag') for x in data.get('contactTags', [])],
            "clients": clients,
            "package_short": package_short
        }
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve contact details: {e}")


# Salesmanago sends API POST to endpoint below to initiate a call
@app.post("/api_input")
async def api_input(payload: SalesmanagoPayload):
    print(payload)
    if not payload.phone:
        raise HTTPException(status_code=400, detail="Phone number is required.")

    insert(payload.__dict__, api_name='api_input')
    metadata = get_contact_name(payload.email)
    tags = metadata.get('tags', [])

    agent = None
    phone_from = None
    for country in agents_per_country.keys():
        if f'SEOSENSE_{country}' in tags:
            agent = agents_per_country[country]
            phone_from = phone_from_country[country]
            break
    if agent is None:
        return {"message": f"No agent for country, tags: {tags}"}
    phone = repair_phone(payload.phone)
    if phone is None:
        phone = payload.phone
    millis_data = {
        "from_phone": phone_from,
        "to_phone": phone,
        "agent_id": agent,
        "metadata": {
            "email": payload.email,
            "EmailAddress": payload.email,
            'name': metadata.get('FirstName', '')
        },
        "include_metadata_in_prompt": True
    }
    millis_data['metadata'] |= metadata
    print(millis_data)
    insert(millis_data, api_name='millis_data')

    num = 1
    potential_failure_tag = f'SEOSENSE_MILLIS_FAILED_TO_CALL_{num}'
    while potential_failure_tag in tags:
        num += 1
        potential_failure_tag = f'SEOSENSE_MILLIS_FAILED_TO_CALL_{num}'
    if num == 5:
        potential_failure_tag = 'SEOSENSE_NOT_ANSWERED'

    try:
        response = requests.post(
            "https://api-west.millis.ai/start_outbound_call",
            json=millis_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": os.getenv('api_key')
            }
        )
        response.raise_for_status()
        update_tag_salesmanago(payload.email, ['SEOSENSE_MILLIS_CALLING'])

        try:
            await asyncio.sleep(60)
            session_id = response.json().get('session_id')
            update_tag_salesmanago(payload.email, tags=None, call_id=session_id)
            response_get_status = requests.get(
                f"https://api-west.millis.ai/call-logs/{session_id}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": os.getenv('api_key')
                }
            )
            response_get_status.raise_for_status()
            call_status = response_get_status.json().get('call_status')
            if call_status not in ['user-ended', 'in-progress']:  # e.g. busy, no_answer
                update_tag_salesmanago(payload.email, [potential_failure_tag])
            else:
                update_tag_salesmanago(payload.email, ['SEOSENSE_TALKED'])
        except:
            print(traceback.format_exc())
            update_tag_salesmanago(payload.email, [potential_failure_tag])
            print(f'Failed to get call by session_id')
    except requests.RequestException as e:
        print(traceback.format_exc())
        update_tag_salesmanago(payload.email, [potential_failure_tag])
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {e}")

    return {"message": "Call initiated successfully."}


def update_tag_salesmanago(email, tags, call_id=None):
    url = "https://app3.salesmanago.pl/api/contact/batchupsertv2"

    payload = {
        "clientId": os.getenv('CLIENT_ID'),
        "apiKey": os.getenv('API_KEY'),
        "requestTime": int(time.time()),  # Current Unix timestamp
        "sha": os.getenv('sha'),
        'owner': os.getenv('OWNER_EMAIL'),
        "upsertDetails": [
            {
                "contact": {
                    "email": email
                }
            }
        ],
    }

    if call_id is not None:
        payload["upsertDetails"][0]["properties"] = {
            "millis_call_id": call_id
        }

    if tags is not None:
        payload["upsertDetails"][0]["tags"] = tags

    try:
        # Send the POST request
        response = requests.post(url, json=payload)

        # Check for successful response
        if response.status_code == 200:
            print("Request was successful!")
            print("Response:", response.json())
        else:
            print(f"Failed with status code: {response.status_code}")
            print("Response content:", response.text)

    except requests.exceptions.RequestException as e:
        print("An error occurred:", e)


class PhoneNumberRequest(BaseModel):
    phone: str = Field(..., example="+1234567890")
    business_hours: str = Field(..., example="10-16")
    desired_call_time: int = Field(..., example=14, ge=0, le=23)

def get_timezone_from_phone(phone_number: str) -> list:
    """
    Takes a mobile phone number and returns the associated timezones.
    :param phone_number: Phone number in international format (e.g., '+1234567890')
    :return: A list of timezone names or an error message.
    """
    try:
        # Parse the phone number
        parsed_number = phonenumbers.parse(phone_number)

        # Validate the phone number
        if not phonenumbers.is_valid_number(parsed_number):
            return ["Invalid phone number"]

        # Get timezones for the phone number
        timezones = timezone.time_zones_for_number(parsed_number)

        return list(timezones)

    except Exception as e:
        return [f"Error: {str(e)}"]

def check_business_hours_and_wait(phone_number: str, business_hours: str, desired_call_time: int) -> tuple:
    """
    Checks if the current time is within business hours and calculates wait time for a desired call time.
    :param phone_number: Phone number in international format (e.g., '+1234567890')
    :param business_hours: Business hours in 'start-end' format (e.g., '10-16')
    :param desired_call_time: Desired hour to call (e.g., 14)
    :return: Tuple (is_now_business_hours, seconds_to_wait)
    """
    try:
        # Get timezone for the phone number
        timezones = get_timezone_from_phone(phone_number)
        if "Invalid phone number" in timezones or "Error" in timezones:
            raise ValueError("Invalid phone number")

        # Use the first timezone found
        tz = pytz.timezone(timezones[0])
        current_time = datetime.now(tz)

        # Parse business hours
        start_hour, end_hour = map(int, business_hours.split('-'))

        # Check if now is within business hours
        is_now_business_hours = start_hour <= current_time.hour < end_hour

        # Calculate seconds to wait until the desired time
        desired_time_today = current_time.replace(hour=desired_call_time, minute=0, second=0, microsecond=0)
        if current_time >= desired_time_today:
            # If desired time has passed, calculate for the next day
            desired_time_today += timedelta(days=1)

        seconds_to_wait = (desired_time_today - current_time).total_seconds()

        return is_now_business_hours, int(seconds_to_wait)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/check_business_hours")
async def check_business_hours(phone, business_hours="10-16", desired_call_time="15"):
    """
    API endpoint to check if the current time is within business hours and calculate wait time for a desired call time.
    """
    is_now, wait_seconds = check_business_hours_and_wait(
        phone_number=phone,
        business_hours=business_hours,
        desired_call_time=int(desired_call_time),
    )
    return {
        "is_now": is_now,
        "wait_seconds": wait_seconds
    }