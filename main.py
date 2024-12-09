import asyncio
import hashlib
import json
import os
import time
import traceback

from fastapi import FastAPI, Request, HTTPException
import requests
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.


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

app = FastAPI()

# Allow specific domains
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.get("/")
async def read_root():
    return {"message": "Welcome to the API"}


# Prefetch Data Webhook (GET request)
@app.get("/prefetch_data_webhook")
async def prefetch_data():
    # Simulate some prefetch data
    return {
        "message": "Prefetch data received successfully!",
        "status": "ok",
        "data": {"key": "value"}
    }


def insert(text, api_name):
    try:
        url_insert = f"{os.getenv('server_url')}/insert-data"
        payload_insert = json.dumps({
            "table_name": "millis_raw_response2",
            "data": [
                {
                    "column_name": "responses",
                    "column_data": str(text)
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

    insert(json.dumps(payload), api_name='end_of_call')

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

    email = payload.get('metadata', {}).get('email', None)
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
    insert(json.dumps(result), api_name='end_of_call_structured')
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
        traffic = result.get('traffic')
        keywords = result.get('keywords')
        package = result.get('package')

        return {
            "Name": name,
            "CompanyName": data.get('company'),
            "traffic": traffic,
            "keywords": keywords,
            "package": package,
            "tags": [x.get('tag') for x in data.get('contactTags', [])]
        }
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve contact details: {e}")


# Salesmanago sends API POST to endpoint below to initiate a call
@app.post("/api_input")
async def api_input(payload: SalesmanagoPayload):
    print(payload)
    if not payload.phone:
        raise HTTPException(status_code=400, detail="Phone number is required.")

    insert(json.dumps(payload.__dict__), api_name='api_input')
    metadata = get_contact_name(payload.email)
    tags = metadata.get('tags', [])
    millis_data = {
        "from_phone": os.getenv('phone_from'),
        "to_phone": payload.phone,
        "agent_id": os.getenv('agent_id'),
        "metadata": {
            "email": payload.email,
            "EmailAddress": payload.email,
            'name': metadata.get('FirstName', '')
        },
        "include_metadata_in_prompt": True
    }
    millis_data['metadata'] |= metadata
    print(millis_data)
    insert(json.dumps(millis_data), api_name='millis_data')

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
            response_get_status = requests.get(
                f"https://api-west.millis.ai/call-logs/{session_id}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": os.getenv('api_key')
                }
            )
            response_get_status.raise_for_status()
            call_status = response_get_status.json().get('call_status')
            if call_status != 'user-ended': # e.g. busy, no_answer
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


def update_tag_salesmanago(email, tags):
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
                    "email": email,
                },
                "tags": tags
            }
        ],
    }

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
