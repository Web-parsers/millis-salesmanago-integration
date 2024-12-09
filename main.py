import hashlib
import os
import time
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


# Prefetch Data Webhook (GET request)
@app.get("/prefetch_data_webhook")
async def prefetch_data():
    # Simulate some prefetch data
    return {
        "message": "Prefetch data received successfully!",
        "status": "ok",
        "data": {"key": "value"}
    }


# End-of-Call Webhook (POST request)
@app.post("/session_data_webhook")
async def end_of_call(request: Request):
    # Parse the incoming JSON payload
    payload = await request.json()
    print("Webhook Payload Received:", payload)

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

    tags = []
    if booking == 'Success':
        tags.append('MILLIS_MEETING')
    else:
        tags.append('MILLIS_MEETING_FAILED')
    tags.append(f'MILLIS_{call_status.upper()}')

    email = payload.get('metadata', {}).get('email', None)
    print(f'tags = {tags}, email = {email}')
    update_tag_salesmanago(email, tags)

    return {
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
            "package": package
        }
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve contact details: {e}")


# Salesmanago sends API POST to endpoint below to initiate a call
@app.post("/api_input")
async def api_input(payload: SalesmanagoPayload):
    print(payload)
    if not payload.phone:
        raise HTTPException(status_code=400, detail="Phone number is required.")

    metadata = get_contact_name(payload.email)

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
    except requests.RequestException as e:
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
