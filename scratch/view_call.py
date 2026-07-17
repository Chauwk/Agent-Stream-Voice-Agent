import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mongo_manager import mongo_db

async def main():
    call_id = "cdc7d03dc1bb4a46bbfcdbba29683d1d@10.0.8.62"
    call = await mongo_db.db.call_logs.find_one({"call_id": call_id})
    if call:
        print("Call Found!")
        print("Duration:", call.get("duration_seconds"))
        print("To Phone:", call.get("to_number"))
        print("Transcript:")
        for idx, msg in enumerate(call.get("transcript", [])):
            print(f" {idx}. {msg.get('role')}: {msg.get('msg')}")
    else:
        print(f"Call {call_id} not found in MongoDB.")

if __name__ == "__main__":
    asyncio.run(main())
