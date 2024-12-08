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


app = FastAPI()


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

    # Respond to the webhook request
    return {
        "message": "End-of-call webhook processed successfully!",
        "received_payload": payload
    }


# This should do call analysis and return a report that will further be sent to CRM for next steps + DB for investigation
@app.post("/call_analysis")
async def call_analysis(request: Request):
    # Parse the incoming JSON payload
    payload = await request.json()
    print("Webhook Payload Received:", payload)

    # TODO: I might do Openai Call analysis here
    # Respond to the webhook request
    return {
        "message": "End-of-call-analysis webhook processed successfully!",
        "received_payload": payload
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
            "FirstName": name,
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
