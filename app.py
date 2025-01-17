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
@app.route("/api/mc-status", methods=["POST"])
def getStatus():
    data = request.json
    print(data)
    # Access mc_no and other fields
    mc_no =  data.get('mc_no', 1)
    status_text = data.get('state')
    timestamp = data.get('timestamp')
    reason_id = data.get('reason_id')

    if data is not None:
        db.insert("INSERT INTO `current_mc_status`( `status_text`, `mc_no`, `reason_id`, `status_time`) VALUES (%s,%s,%s,%s)", (status_text,mc_no,reason_id,timestamp,))
        return jsonify({"status": "success", "data": data})
    else:
        return jsonify({"status": "Failed", "data": data})


@app.route("/api/mc-log", methods=["GET", "POST"])
def home():
    
    reasons = db.get_all("SELECT * FROM lib_knit_mc_cause")
    # checking for post request
    if request.method == 'POST':
        
            data = request.json
            print(data)
            dateFrom = data.get('dateFrom')
            dateTo = data.get('dateTo')
            mc_no = data.get('mc_no')
            reason = data.get('reason')
            

            # Base query with parameterized values
            query = "SELECT * FROM current_mc_status WHERE status_time BETWEEN %s AND %s"
            params = [dateFrom, dateTo]

            # Build conditions list and parameters
            conditions = []
            
            if mc_no is not None:
                conditions.append("mc_no = %s")
                params.append(mc_no)
                
            if reason is not None:
                # Safely get reason_id using parameterized query
                reason_query = "SELECT id FROM lib_knit_mc_cause WHERE name = %s"
                reason_id = db.get_one(reason_query, [reason])
                if reason_id:
                    conditions.append("reason_id = %s")
                    params.append(reason_id)

            # Add conditions to query if they exist
            if conditions:
                query += " AND " + " AND ".join(conditions)
                
            # Add ordering
            query += " ORDER BY mc_no ASC, id ASC"

            # Execute query with parameters
            logs = db.get_all(query, params)
            print(query,params)
            print(logs)



        
    else:
        current_date =  date.today()
        
        
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
        # print(result)

    allMachines = db.get_all("SELECT DISTINCT mc_no FROM `current_mc_status`")

    allMc = [mc[0] for mc in allMachines if mc[0] is not None]
        # pprint(result)
    if result and result["complete"]:
        return jsonify({"success":True, "result":result, "machines": allMc})
    else :
        return jsonify({"success":False, "result":[], "machines": allMc})


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
        
    if machines:
        return jsonify({"success": True, "result": machines, "machines": allMc})
    else:
        return jsonify({"success": False, "result": machines, "machines": allMc})

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))   # Use PORT from environment or default to 5000
    app.run(host="0.0.0.0", port=port)




#     @app.route("/api/mc-log", methods=["GET"])
# def home():
#     current_date =  date.today()
#     # reasons = db.get_all("SELECT * FROM lib_knit_mc_cause")
#     # pprint(reasons[0][1])
#     logs = db.get_all("SELECT * FROM `machine_off_durations2`WHERE DATE(offTime) = %s", (current_date,))
#     results = []
     
#     for record in logs:
#         results.append({
#             "id": record[0],
#             "machine": record[1],
#             "on_time": record[2].strftime("%Y-%m-%d %H:%M:%S") if record[2] else None,
#             "off_time": record[3].strftime("%Y-%m-%d %H:%M:%S") if record[3] else None,
#             "duration": record[4].total_seconds() if record[4] else None,
#             "reason": record[5],
#             "button_delay": record[6].total_seconds() if record[6] else None,
#         })
    
#     if logs:
#         return jsonify({"success":True, "result":results})
#     else :
#         return jsonify({"success":False, "result":[]})
