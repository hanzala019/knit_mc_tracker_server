from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from pywebpush import webpush, WebPushException
import os
import json
from dotenv import load_dotenv
from model import Database
from pprint import pprint
from datetime import date
from collections import defaultdict
load_dotenv()
app = Flask(__name__)
CORS(app)

db = Database()

def get_reason_description(reason_id, reasons):
    for r_id, description in reasons:
        if r_id == reason_id:
            return description
    return None


# @app.route("/api/login", methods=["POST"])
# def login():

@app.route("/api/mc-log", methods=["GET"])
def home():
    current_date =  date.today()
    reasons = db.get_all("SELECT * FROM lib_knit_mc_cause")
    # pprint(reasons[0][1])
    logs = db.get_all("SELECT * FROM `current_mc_status` WHERE DATE(status_time) = %s ORDER BY current_mc_status.mc_no ASC, current_mc_status.id ASC", (current_date,))

    result = {
    "complete": [],
    "incomplete": []
    }
    current_group = {
        "statuses": set(),
        "timeTaken": 0,
        "btnDelay": 0,
        "data": [
            {"id": None, "status": "Machine Off", "machine": None, "reason_id": None, "timestamp": None},
            {"id": None, "status": "Button Pressed", "machine": None, "reason_id": None, "timestamp": None},
            {"id": None, "status": "Machine On", "machine": None, "reason_id": None, "timestamp": None},
        ]
    }
    current_machine = None  # Temporary variable to track the current machine
    if logs:
        for row in logs:
            if row is not None:
                id, status, machine, reason_id, timestamp = row

                # Check if the machine has changed
                if machine != current_machine:
                    # storing the incomplete previous machine status
                    if len(current_group["statuses"]) > 0 and len(current_group["statuses"]) < 3:
                        result["incomplete"].append(current_group["data"])

                
                    # Update the current machine
                    current_machine = machine  
                    result["incomplete"].append({
                        "id": id,
                        "status": status,
                        "machine": machine,
                        "reason_id": reason_id,
                        "timestamp": timestamp
                    })

                    # Reset current group
                    current_group = {
                        "statuses": set(),
                        "timeTaken": 0,
                        "btnDelay": 0,
                        "data": [
                            {"id": None, "status": "Machine Off", "machine": None, "reason_id": None, "timestamp": None},
                            {"id": None, "status": "Button Pressed", "machine": None, "reason_id": None, "timestamp": None},
                            {"id": None, "status": "Machine On", "machine": None, "reason_id": None, "timestamp": None},
                        ]
                    }
                    continue
                if status in ["Machine On", "Button Pressed", "Machine Off"]:
                    if status not in current_group["statuses"]:
                        reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None

                        if status == "Machine Off":
                            current_group["data"][0] = {"id": id, "status": status, "machine": machine, "reason_id": reason_name, "timestamp": timestamp}
                        elif status == "Button Pressed":
                            current_group["data"][1] = {"id": id, "status": status, "machine": machine, "reason_id": reason_name, "timestamp": timestamp}
                        elif status == "Machine On":
                            current_group["data"][2] = {"id": id, "status": status, "machine": machine, "reason_id": reason_name, "timestamp": timestamp}

                        current_group["statuses"].add(status)

                        # Complete group handling
                        if len(current_group["statuses"]) == 3:
                            if current_group["data"][0]["timestamp"] and current_group["data"][2]["timestamp"]:
                                if current_group["data"][2]["timestamp"] >= current_group["data"][0]["timestamp"]:
                                    current_group["timeTaken"] = (current_group["data"][2]["timestamp"] - current_group["data"][0]["timestamp"]).total_seconds()
                                else:
                                    current_group["timeTaken"] = None  # Invalid sequence

                            if current_group["data"][1]["timestamp"]:
                                current_group["btnDelay"] = (current_group["data"][1]["timestamp"] - current_group["data"][0]["timestamp"]).total_seconds()

                            result["complete"].append({
                                "statuses": current_group["data"],
                                "timeTaken": current_group["timeTaken"],
                                "btnDelay": current_group["btnDelay"]
                            })

                            # Reset current group
                            current_group = {
                                "statuses": set(),
                                "timeTaken": 0,
                                "btnDelay": 0,
                                "data": [
                                    {"id": None, "status": "Machine Off", "machine": None, "reason_id": None, "timestamp": None},
                                    {"id": None, "status": "Button Pressed", "machine": None, "reason_id": None, "timestamp": None},
                                    {"id": None, "status": "Machine On", "machine": None, "reason_id": None, "timestamp": None},
                                ]
                            }

                    # Handle invalid sequence (Machine Off after On)
                    elif status == "Machine Off" and "Machine On" in current_group["statuses"]:
                        if current_group["data"][0]["timestamp"] and current_group["data"][2]["timestamp"]:
                            if current_group["data"][2]["timestamp"] >= current_group["data"][0]["timestamp"]:
                                current_group["timeTaken"] = (current_group["data"][2]["timestamp"] - current_group["data"][0]["timestamp"]).total_seconds()
                            else:
                                current_group["timeTaken"] = None  # Invalid sequence
                        result["complete"].append({
                            "statuses": current_group["data"],
                            "timeTaken": current_group["timeTaken"],
                            "btnDelay": current_group["btnDelay"]
                        })

                        # Reset group with new Off
                        current_group = {
                            "statuses": {"Machine Off"},
                            "timeTaken": 0,
                            "btnDelay": 0,
                            "data": [
                                {"id": id, "status": status, "machine": machine, "reason_id": reason_name, "timestamp": timestamp},
                                {"id": None, "status": "Button Pressed", "machine": None, "reason_id": None, "timestamp": None},
                                {"id": None, "status": "Machine On", "machine": None, "reason_id": None, "timestamp": None},
                            ]
                        }

        # Handle any leftover incomplete groups
        if any(item["timestamp"] for item in current_group["data"]):
            result["incomplete"].append(current_group["data"])
    
        
        # pprint(result)
    if result["complete"]:
        return jsonify({"success":True, "result":result})
    else :
        return jsonify({"success":False, "result":[]})


@app.route("/api/mc-graph", methods=["GET"])
def graph():
    machines = defaultdict(list)
    current_date = date.today()  # Get current date in 'YYYY-MM-DD' format
    reasons = db.get_all("SELECT * FROM lib_knit_mc_cause")
    allMachines = db.get_all("SELECT DISTINCT mc_no FROM `current_mc_status`")
  
    allMc = [mc[0] for mc in allMachines]  # Get all machine numbers
    # Fetch logs for current date
    logs = db.get_all("SELECT * FROM `current_mc_status` WHERE DATE(status_time) = %s ORDER BY current_mc_status.mc_no ASC, current_mc_status.id ASC", (current_date,))

    # Filter logs by machine
    if logs:
        for row in logs:
            if row is not None:
                id, status, machine, reason_id, timestamp = row
                reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
                machines[machine].append({
                    'id': id,
                    'status': status,
                    'reason': reason_name,
                    'timestamp': timestamp
                })

        # Convert defaultdict to a regular dictionary if needed
        machines = dict(machines)

    else:
        machines = {}  # Initialize empty machines if no logs are returned
        

    return jsonify({"success": True, "result": machines, "machines": allMc})

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))   # Use PORT from environment or default to 5000
    app.run(host="0.0.0.0", port=port)




    # machines = defaultdict(list)

    # # Filter logs by machine
    # for row in logs:
    #     id, status, machine, reason_id, timestamp = row
    #     machines[machine].append({
    #         'id': id,
    #         'status': status,
    #         'reason_id': reason_id,
    #         'timestamp': timestamp
    #     })

    # # Convert defaultdict to a regular dictionary if needed
    # machines = dict(machines)
    # pprint(machines)
    # # Print the result
    # for machine, machine_logs in machines.items():
    #     print(f"Machine: {machine}")
    #     for log in machine_logs[:10]:

    #         print(f"  Log: {log}")

        
    # result = {
    #     "complete": [],
    #     "incomplete": []
    # }

    # # Initialize state for grouping
    # current_group = {"statuses": set(), "data": [], "machine": None}

    # for row in logs:
    #     id, status, machine, reason_id, timestamp = row
        
    #     # Reset the group if a new machine starts
    #     if current_group["machine"] != machine:
    #         # Save the incomplete group if not empty
    #         if current_group["data"]:
    #             result["incomplete"].append(current_group["data"])
    #         current_group = {"statuses": set(), "data": [], "machine": machine}
        
    #     if status in ["Machine On", "Button Pressed", "Machine Off"]:
    #         # Avoid duplicate statuses in the current group
    #         if status not in current_group["statuses"]:
    #             reason_name = (
    #                 get_reason_description(reason_id, reasons)
    #                 if status == "Button Pressed"
    #                 else None
    #             )

    #             # Check for invalid sequence: Off after On
    #             if status == "Machine Off" and "Machine On" in current_group["statuses"]:
    #                 # Invalidate prior Button Pressed
    #                 for item in current_group["data"]:
    #                     if item["status"] == "Button Pressed":
    #                         item["reason_id"] = None
    #                 # Finalize the current group as complete and start a new one
    #                 result["complete"].append(current_group["data"])
    #                 current_group = {"statuses": set(), "data": [], "machine": machine}
                
    #             # Add the current row to the group
    #             current_group["data"].append(
    #                 {"id": id, "status": status, "machine": machine, "reason_id": reason_name, "timestamp": timestamp}
    #             )
    #             current_group["statuses"].add(status)

    #             # Finalize the group if all statuses are collected
    #             if len(current_group["statuses"]) == 3:
    #                 result["complete"].append(current_group["data"])
    #                 current_group = {"statuses": set(), "data": [], "machine": machine}

    # # Handle the final incomplete group
    # if current_group["data"]:
    #     result["incomplete"].append(current_group["data"])

    # pprint(result)
