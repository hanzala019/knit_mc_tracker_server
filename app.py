from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from pywebpush import webpush, WebPushException
import os
import json
from dotenv import load_dotenv
from model import Database
from pprint import pprint
from datetime import date, timedelta, datetime
import random
from collections import defaultdict
load_dotenv()
app = Flask(__name__)
CORS(app)

db = Database()


def filter_machine_states(machine_data):
    filtered_data = {}
    # Get current date
    today = date.today()

    # Set time to start of the day
    startOfToday = datetime.combine(today, datetime.min.time())

    for machine, states in machine_data.items():
        # print(states)
        if not states:
            continue  # Skip empty entries

        if len(states) == 1: 
            if states[0]["status"] != "Button Pressed":
                filtered_data[machine] = states  # Keep it if not "Button Pressed"
            continue  # Skip to next machine

        # Sorting states by timestamp to ensure correct order
        states = sorted(states, key=lambda x: x["timestamp"])

        # Process the last two states only
        s1, s2 = states[-2], states[-1]  # Take the last two states

        # Apply filtering logic
        if s1["status"] == "Machine Off" and s2["status"] == "Machine On":
            s2["timestamp"] = startOfToday
            filtered_data[machine] = [s2]  # Keep "On" only

        elif s1["status"] == "Machine On" and s2["status"] == "Machine Off":
             s2["timestamp"] = startOfToday
             filtered_data[machine] = [s2]  # Keep "Off" only

        elif s1["status"] == "Button Pressed" and s2["status"] == "Machine On":
             s2["timestamp"] = startOfToday
             filtered_data[machine] = [s2]  # Keep "On" only

        elif s1["status"] == "Machine Off" and s2["status"] == "Button Pressed":
             s2["timestamp"] = startOfToday
             s1["timestamp"] = startOfToday
             filtered_data[machine] = [s1, s2]  # Keep both

        elif s1["status"] == "Button Pressed" and s2["status"] == "Machine Off":
             s2["timestamp"] = startOfToday
             filtered_data[machine] = [s2]  # Keep "Off" only

        elif s1["status"] == s2["status"]:
             s2["timestamp"] = startOfToday
             s1["timestamp"] = startOfToday
             # If both states are the same, keep the one with the higher ID (most recent)
             filtered_data[machine] = [max(s1, s2, key=lambda x: x["id"])]

    return filtered_data

def process_machine_logs(logs, reasons):
    if logs:
        logs = sorted(logs, key=lambda x: (x[2], x[0]))

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
    
    current_machine = None

    if not logs:
        return result

    for row in logs:
        if row is None:
            continue

        id, status, machine, reason_id, timestamp = row

        # Handle machine change
        if machine != current_machine:
            # Store incomplete status of previous machine
            if len(current_group["statuses"]) > 0 and len(current_group["statuses"]) < 3:
                result["incomplete"].append(current_group["data"])
            
            # Update current machine
            current_machine = machine
            
            # Start new group with current status if it's Machine Off
            if status == "Machine Off":
                reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
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
            else:
                # Add single status to incomplete for non-Machine Off status
                result["incomplete"].append({
                    "id": id,
                    "status": status,
                    "machine": machine,
                    "reason_id": reason_id,
                    "timestamp": timestamp
                })
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

        # Process status for current machine
        if status in ["Machine On", "Button Pressed", "Machine Off"]:
            # Check if status not in current group or if it's a new Machine Off after Machine On
            if status not in current_group["statuses"] or (status == "Machine Off" and "Machine On" in current_group["statuses"]):
                # Handle new Machine Off after Machine On
                if status == "Machine Off" and "Machine On" in current_group["statuses"]:
                    # Complete current group if valid
                    if current_group["data"][0]["timestamp"] and current_group["data"][2]["timestamp"]:
                        if current_group["data"][2]["id"] > current_group["data"][0]["id"]:
                            current_group["timeTaken"] = (current_group["data"][2]["timestamp"] - current_group["data"][0]["timestamp"]).total_seconds()
                        else:
                            current_group["timeTaken"] = None
                    result["complete"].append({
                        "statuses": current_group["data"],
                        "timeTaken": current_group["timeTaken"],
                        "btnDelay": current_group["btnDelay"]
                    })
                    # Start new group with current Machine Off
                    reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
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
                    continue

                # Validate sequence based on status
                valid_sequence = True
                if status == "Button Pressed":
                    if current_group["data"][0]["id"] is not None:
                        valid_sequence = id > current_group["data"][0]["id"]
                elif status == "Machine On":
                    if current_group["data"][0]["id"] is not None and current_group["data"][1]["id"] is not None:
                        valid_sequence = (id > current_group["data"][0]["id"] and id > current_group["data"][1]["id"])

                if valid_sequence:
                    # Add to current group
                    reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
                    status_index = {"Machine Off": 0, "Button Pressed": 1, "Machine On": 2}[status]
                    current_group["data"][status_index] = {
                        "id": id,
                        "status": status,
                        "machine": machine,
                        "reason_id": reason_name,
                        "timestamp": timestamp
                    }
                    current_group["statuses"].add(status)

                    # Handle complete group
                    if len(current_group["statuses"]) == 3:
                        if current_group["data"][0]["timestamp"] and current_group["data"][2]["timestamp"]:
                            current_group["timeTaken"] = (current_group["data"][2]["timestamp"] - current_group["data"][0]["timestamp"]).total_seconds()
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
                else:
                    # Handle invalid sequence
                    if any(item["timestamp"] for item in current_group["data"]):
                        result["incomplete"].append(current_group["data"])
                    if status == "Machine Off":
                        # Start new group with current Machine Off
                        reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
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
                    else:
                        # Reset group for invalid Button Press or Machine On
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

    # Handle any remaining incomplete group
    if any(item["timestamp"] for item in current_group["data"]):
        result["incomplete"].append(current_group["data"])

    return result

def get_reason_description(reason_id, reasons):
    # print(reason_id)
    for r_id, description, a,b,c,d,e in reasons:
        # print(r_id, reason_id)
        if r_id == reason_id:
            print
            return description
    return None

def generate_custom_string(name):
    random_number = random.randint(1000000, 9999999)  # Generates a random 7-digit number
    return f"{name}-{random_number}"

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    print(data)
    email = data.get("email")
    password = data.get("password")
    user = db.get_one("SELECT * FROM users WHERE email = %s AND password = %s", (email,password,))
    print(user)
    if user is not None:
        return jsonify({"status": "success", "user": user})
    else:
        return jsonify({"status": "Failed"})

@app.route("/api/users", methods=["POST"])
def users():
    data = request.json
    print(data)
    reason = data.get("reason")
    company = data.get("company", None)

    # handling get request logic
    if data is not None and reason == "get":
        
        users = db.get_all("SELECT userId, username, company, email, password, access FROM users WHERE company = %s AND userType = %s", (company, "employee",))
        print(users)
        keys = ['id', 'name', 'company', 'email', 'password', 'access']
        array_of_dicts = []
        if users is not None:
            # Convert data into an array of dictionaries
            for d in users :
                data_dict = {key: value for key, value in zip(keys, d)}
                array_of_dicts.append(data_dict)
            print(array_of_dicts)
            return jsonify({"status": "success", "users": array_of_dicts})
        else:
            return jsonify({"status": "failed", "msg": "no users found"})

    # handling post request logic
    elif  reason == "update":
        name = data.get("name")
        password = data.get("password")
        email = data.get("email")
        access = data.get("access")
        id = data.get("id")
        db.update("UPDATE users SET username = %s, email = %s, password = %s, access = %s WHERE userId = %s", (name,email,password,access, id,))
        if data is not None:    
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "Failed","msg": "failed to update", "data": data})

    # handling put request logic
    elif  reason == "add":
        name = data.get("name")
        print(data)
        password = data.get("password")
        email = data.get("email")
        access = data.get("access")
        id = generate_custom_string(company)
        db.insert("INSERT INTO `users`(`userId`, `username`, `userType`, `company`, `password`, `email`, `access`) VALUES (%s, %s, 'employee',%s,%s,%s,%s)", (id, name,company,password,email,access,))
        if data is not None:    
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "Failed", "msg": "failed to add", "data": data})
    
    # handling delete request logic
    elif  reason == "delete":
        id = data.get("id")
        db.delete("DELETE FROM users WHERE userId = %s", (id,))
        if data is not None:    
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "Failed","msg": "failed to delete", "data": data})


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
            query += " ORDER BY mc_no ASC, id desc"

            # Execute query with parameters
            logs = db.get_all(query, params)
            print(query,params)
            # print(logs)



        
    else:
        current_date =  date.today()
        
        
        # pprint(reasons[0][1])
        logs = db.get_all("SELECT * FROM `current_mc_status` WHERE DATE(status_time) = %s ORDER BY current_mc_status.mc_no ASC, current_mc_status.id desc", (current_date,))

        
    result = process_machine_logs(logs, reasons)

    allMachines = db.get_all("SELECT DISTINCT mc_no FROM `current_mc_status`")
    allMc = []
    if allMachines is not None:
        allMc = [mc[0] for mc in allMachines if mc and mc[0] is not None] # Get all machine numbers

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
    allMc = []
    if allMachines is not None:
        allMc = [mc[0] for mc in allMachines if mc and mc[0] is not None] # Get all machine numbers
    # Fetch logs for current date
    logs = db.get_all("SELECT * FROM `current_mc_status` WHERE DATE(status_time) = %s ORDER BY current_mc_status.mc_no ASC, current_mc_status.id ASC", (current_date,))
    
    previous_day_query = """
                    SELECT *
                    FROM current_mc_status c
                    JOIN (
                        SELECT MAX(id) AS max_id
                        FROM current_mc_status
                        WHERE mc_no = %s
                        AND DATE(status_time) < %s
                        GROUP BY status_text
                    ) latest ON c.id = latest.max_id
                    ORDER BY c.id DESC
                    LIMIT 2;
        """
    # previous_entries = {}  # {machine: [entry1, entry2]}
    
    for machine in allMc:
        previous_rows = db.get_all(previous_day_query, (machine,current_date,))
        # pprint(previous_rows)
        mc = []
        if previous_rows is not None:
            for row in previous_rows:
                print(row)
                id, status, machine_num, reason_id, timestamp, max_id = row
                reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
                mc.append({
                    'id': id,
                    'status': status,
                    'reason': reason_name,
                    'timestamp': timestamp,
                    'startTime': timestamp
                })
            machines[machine] = mc

    # pprint(machines)
    
    machines = filter_machine_states(machines)
    # pprint(machines)
    print("------------------------------------------------------------------------------------------------------------------------")
    # print(latest_data_list)
    # Filter logs by machine
    if logs:
        for row in logs:
            if row is not None:
                id,  status, machine, reason_id, timestamp = row
                # print(id, status, machine, reason_id, timestamp)         
                reason_name = get_reason_description(reason_id, reasons) if status == "Button Pressed" else None
                machines[machine].append({
                    'id': id,
                    'status': status,
                    'reason': reason_name,
                    'timestamp': timestamp,
                    'startTime': timestamp
                })

    if machines:
        machines = dict(machines)
        # pprint(machines)
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
