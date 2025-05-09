import streamlit as st
import pandas as pd
import numpy as np
from pyDOE2 import fullfact
import datetime
import uuid
import json

if 'respondent_id' not in st.session_state:
    st.session_state.respondent_id = str(uuid.uuid4())

def update_respondents_data():

    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1eANKzGeVJRh1kQoJwoj1mejcfb5JzQydslkKhK6SGKI")  # your sheet ID
        respondents_sheet = sheet.worksheet("Respondents_Data")

        # Fetch all data from the "Final_Responses" sheet
        final_sheet = sheet.worksheet("Final_Responses")
        all_data = final_sheet.get_all_records()

        unique_respondents = {}
        for row in all_data:
            respondent_id = row.get("Respondent_id")
            vehicle_kind = row.get("Ownership_Type")
            if respondent_id and respondent_id not in unique_respondents:
                unique_respondents[respondent_id] = vehicle_kind

        total_respondents = len(unique_respondents)
        private_vehicle_respondents = sum(1 for v in unique_respondents.values() if 'Private' in v)
        commercial_vehicle_respondents = sum(1 for v in unique_respondents.values() if 'Commercial' in v)
        no_vehicle_respondents = total_respondents - private_vehicle_respondents - commercial_vehicle_respondents

        # Update the Respondents_Data sheet
        respondents_sheet.update(range_name ='A2', values = [[total_respondents]])
        respondents_sheet.update(range_name ='B2', values = [[private_vehicle_respondents]])
        respondents_sheet.update(range_name ='C2', values = [[commercial_vehicle_respondents]])
        respondents_sheet.update(range_name='D2', values=[[no_vehicle_respondents]])
        
        print("Respondents data successfully updated.")

    except Exception as e:
        print(f"Error while updating Respondents_Data: {e}")


def submit_to_google_sheets():
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key("1eANKzGeVJRh1kQoJwoj1mejcfb5JzQydslkKhK6SGKI")  # your sheet ID
        final_sheet = sheet.worksheet("Final_Responses")

        df_profiles = st.session_state.df_profiles
        responses = sorted(st.session_state.responses, key=lambda x: x["Task"])

        rows_to_append = []

        for response in responses:
            task = response["Task"]
            chosen_profile_letter = response["Choice"]

            for profile_letter in ["A", "B", "C"]:
                chosen = 1 if profile_letter == chosen_profile_letter else 0
                profile = df_profiles[(df_profiles["Task"] == task) & (df_profiles["Profile"] == profile_letter)].iloc[0]

                row = []

                # Respondent ID, Task, Profile Letter
                row.append(st.session_state.demographics.get("Respondent id", ""))
                row.append(task)
                row.append(profile_letter)

                # Add attribute values
                for attr in attributes.keys():  # Maintain consistent attribute order
                    row.append(profile[attr])

                # Add choice flag
                row.append(chosen)

                # Add demographic and vehicle info
                row.extend([st.session_state.demographics.get(k, "") for k in [
                    "Age", "Gender", "Education", "Location", "Family Status", "Family Annual Income", "Top Add-ons"
                ]])
                row.extend(st.session_state.vehicle_info.values())

                rows_to_append.append(row)

        # ✅ Send all rows in one batch
        final_sheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')

        print("Data successfully added to Google Sheets!")

        update_respondents_data()

    except Exception as e:
        print(f"Error while submitting to Google Sheets: {e}")

# --------------------------- 1. Conjoint Setup ---------------------------

attributes = {
    "Annual Premium Price": ["₹500", "₹1000", "₹2000", "₹3000"],
    "Voluntary Deductible": ["0", "₹1000", "₹2000", "₹5000"],
    "Key Coverage Feature": [
        "Covers all repair costs",
        "Daily compensation or transport if vehicle in repair",
        "Emergency Roadside assistance",
        "Support for theft/damage of belongings in vehicle",
        "Medical expense coverage for vehicle occupants"
    ],
    "Spare parts used during repairs": [
        "Only OEM (original) parts",
        "Mix of OEM (original) & Non-OEM (aftermarket) parts",
        "Non – OEM (aftermarket) parts",
    ],
    "Claims Experience": [
        "Quick return of vehicle",
        "Regular updates & transparency",
        "Cashless claims at garage",
        "Convenient pick-up and drop of vehicle",
        "Repair at home for minor damages"
    ]
}

def generate_profiles():
    levels = [len(v) for v in attributes.values()]
    factorial = fullfact(levels)
    df_full = pd.DataFrame(factorial, columns=attributes.keys()).astype(int)

    for attr in attributes:
        df_full[attr] = df_full[attr].apply(lambda x: attributes[attr][x])

    def sample_with_full_coverage(df_full, attributes, n_profiles=24, max_tries=100):
        levels_needed = {attr: list(set(df_full[attr])) for attr in attributes.keys()}
        
        for attempt in range(max_tries):
            df_sampled = df_full.sample(n=n_profiles).reset_index(drop=True)
            full_coverage = True
            for attr, levels in levels_needed.items():
                observed_levels = df_sampled[attr].unique()
                if not all(level in observed_levels for level in levels):
                    full_coverage = False
                    break
            if full_coverage:
                return df_sampled
        return df_sampled  # fallback

    df_sampled = sample_with_full_coverage(df_full, attributes)
    df_sampled['Task'] = df_sampled.index // 3 + 1
    df_sampled['Profile'] = df_sampled.groupby('Task').cumcount().apply(lambda x: chr(65 + x))
    df_profiles = df_sampled[['Task', 'Profile'] + list(attributes.keys())]
    return df_profiles

# --------------------------- 2. Streamlit App Setup ---------------------------

st.set_page_config(page_title="Motor Insurance Preference Survey", layout="wide")

# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "intro"
    st.session_state.responses = []
    st.session_state.demographics = {}
    st.session_state.vehicle_info = {}
    st.session_state.task_index = 0
    st.session_state.df_profiles = generate_profiles()  # <-- VERY IMPORTANT!

# --------------------------- 3. Page Functions ---------------------------

def intro():
    st.title("Welcome to the Survey!")
    st.markdown("""
    We want to understand your preferences when choosing motor insurance. This survey will only take 10 - 12 minutes to fill.
    
    (Please note that all responses will be kept anonymous and used only for research purposes.)
    """)
    
    if st.button("I Consent and Continue"):
        # Move to instructions with a single click
        st.session_state.page = "instructions"
        st.rerun()  # Ensures page rerun

def instructions():
    st.title("Instructions")
    st.markdown("""
    In this survey, you'll be shown different insurance plans and you will have to compare them.   
    You will have to perform 8 tasks, each showing **3 plans (Profile A, B, and C)** — select the one you prefer most.
    
    **Definition of some terms**

    **Voluntary Deductible** - The amount of money that insurance holder agrees to pay voluntarily in case of a claim, before the insurance company covers the remaining costs. Eg - If your voluntary deductible is ₹1000 and your repair cost is ₹5000, you will pay ₹1000, and the insurance company will pay ₹4000.
    (Choosing a higher deductible means lower premium payments, but you'll pay more if something happens and choosing a lower deductible means higher premiums, but you'll pay less during a claim.)

    
    **Please Note:**  
    All plans include **standard insurance coverage**. This standard coverage typically includes protection for:
    - Third-party injury or property damage (Basic legal liability cover)
    - Accidental damage to your own vehicle
    - Theft or total loss of the vehicle

    Each plan emphasizes **one key feature** to highlight what it does best. 
     
    """)
    
    if st.button("Start Survey"):
        # Start the survey on button click
        st.session_state.page = "survey"
        st.rerun()  # Ensure the page reloads for survey

def survey():
    df_profiles = st.session_state.df_profiles
    task_num = st.session_state.task_index + 1

    st.header(f"Task {task_num}")

    task_df = df_profiles[df_profiles['Task'] == task_num].reset_index(drop=True)

    st.markdown("### Please compare the profiles below:")

    # Build comparison table
    comparison_data = {attr: [] for attr in attributes.keys()}
    for attr in attributes.keys():
        for _, row in task_df.iterrows():
            comparison_data[attr].append(row[attr])

    profile_labels = [f"Profile {p}" for p in task_df['Profile']]
    comparison_df = pd.DataFrame.from_dict(comparison_data, orient='index', columns=profile_labels)
    comparison_df.index.name = "Attribute"

    st.table(comparison_df)

    # Form for user input
    with st.form(f"task_form_{task_num}"):
        choice = st.radio("Your choice:", profile_labels, index=None, horizontal=True, key=f"choice_{task_num}")
        submitted = st.form_submit_button("Next")

    if submitted:

      if choice is None:
        st.warning("Please select an option to proceed.")
      else:
        # Update session state inside the submission block
        st.session_state.responses.append({
            "Task": task_num,
            "Choice": choice[-1]
        })
        st.session_state.task_index += 1

        if st.session_state.task_index >= st.session_state.df_profiles['Task'].nunique():
            # Move to demographics once the tasks are completed
            st.session_state.page = "demographics"
            st.rerun()  # Ensure the page reloads after the last task
        else:
            # Move to next task
            st.session_state.page = "survey"
            st.rerun()  # Ensure the page reruns to load next task

def demographics():
    st.header("Some Additional Details")
    with st.form("demographics_form"):
        age = st.number_input("Age:", min_value=0, max_value=100, step=1)
        gender = st.radio("Gender:", ['Male', 'Female', 'Others'], index = None)
        education = st.radio("Education:", ['Below 10th', '10th Pass', '12th Pass', 'Graduate', 'Post Graduate'], index = None)
        location = st.radio("Location:", ['Tier 1 City', 'Tier 2 City', 'Tier 3 City', 'Rural'], index = None)
        family_status = st.radio("Family Status:", ['Unmarried', 'Married', 'Married with children'], index = None)
        income = st.radio("Family Annual Income:", ['Less than ₹5 Lakhs', '₹5 Lakhs – ₹9.99 Lakhs', '₹10 Lakhs – ₹19.99 Lakhs', '₹20 Lakhs – ₹50 Lakhs', 'More than 50 Lakhs', 'Prefer not to say'], index = None)
        st.markdown("Choose your top 3 preferred insurance add-ons:")
        addons = [
            "Zero Depreciation Cover : Ensures that the insurance company will pay the full cost to repair or replace damaged parts of your car, without reducing the amount based on how old the parts are",
            "Roadside Assistance : Emergency help if your car breaks down — towing, fuel delivery, flat tire fix, emergency hotel accommodation etc.",
            "Engine Protection : Covers damage to the engine due to water ingress, oil leakage, etc. — not usually included in base policies",
            "Personal Accident Cover (for Driver & Occupants) : Covers injuries or death of the driver and passengers in an accident",
            "Consumables Cover : Covers small but essential items like engine oil, nuts & bolts, AC gas, etc., used during repairs",
            "No Claim Bonus (NCB) Protection : Lets you keep your No Claim Bonus (a discount of 20% to 50% on your premium for not making claims) even if you file a claim during the policy year",
            "Tyre Protection : Covers repair or replacement costs of tyres damaged by accidents, cuts, or bursts",
            "Key Replacement : Covers the cost of replacing lost, stolen, or damaged car keys, including reprogramming if needed",
            "Loss of personal belongings : Covers the loss or damage of personal items inside the car, such as electronics, bags, or valuables, due to theft or an accident",
            "Battery Protection : Covers the cost of repairing or replacing your car’s battery if it gets damaged due to electrical faults or accidents",
            "Garage Cash : Provides a daily allowance to cover your transportation costs if your car is being repaired at a garage after an accident or breakdown",
            "Misfueling : Covers the costs associated with repairing damage caused by putting the wrong type of fuel in a vehicle"
        ]
        
        st.markdown(" ")

        selected_addons = []
        checkbox_states = {}

        for addon in addons:
           checkbox_states[addon] = st.checkbox(addon, key=addon)

        # Count selected checkboxes
        selected_addons = [addon for addon, checked in checkbox_states.items() if checked]

        if len(selected_addons) > 3:
           st.warning("You have selected more than 3 add-ons. Please deselect to proceed.")
        
        
        submitted = st.form_submit_button("Next")
        if submitted:
           if not age or gender is None or education is None or location is None or family_status is None or income is None or len(selected_addons) != 3 :
                st.warning("Please fill in all the fields and exactly 3 add ons to continue.")
           else:
               st.session_state.demographics = {
                 "Respondent id" :st.session_state.respondent_id,
                 "Age": age,
                 "Gender": gender,
                 "Education": education,
                 "Location": location,
                 "Family Status": family_status,
                 "Family Annual Income": income,
                 "Top Add-ons": ", ".join(selected_addons)
              }
               st.session_state.page = "vehicle_ownership"
               st.rerun()  # Refresh to move to vehicle ownership page

def vehicle_ownership():
    st.header("Do you own a vehicle?")
    own_vehicle = st.radio("Vehicle Ownership", ['Yes', 'No'], index = None, label_visibility="collapsed")

    if st.button("Next"):
        if own_vehicle is None:
            st.warning("Please select whether you own a vehicle to proceed.")
        elif own_vehicle == "No":
            st.session_state.vehicle_info["Ownership"] = "No Vehicle"
            with st.spinner("Submitting your response..."):
               submit_to_google_sheets()
            st.session_state.page = "thankyou"
            st.rerun()
        else:
            st.session_state.vehicle_info["Ownership"] = "Own Vehicle"
            st.session_state.page = "vehicle_type"
            st.rerun()

def vehicle_type():
    st.header("Vehicle Details")
    
    vehicle_kind = st.radio("What type of vehicle do you own?", ["Private", "Commercial"], index=None)

    if vehicle_kind == "Private":
        st.markdown("""
Please provide details for the **latest vehicle you have purchased**.  
(If you own more than one vehicle, consider only the most recently acquired one for this survey.)
""")
        vtype = st.radio("Vehicle Type:", ['2 wheeler', '4 wheeler', 'EV 2 Wheeler', 'EV 4 Wheeler'], index=None)
        v_age = st.text_input("Age of Vehicle (in years):")
        cost = st.radio("Cost of Vehicle:", ['Less than ₹1 Lakh', '₹1 Lakh – ₹2.99 Lakhs', '₹3 Lakhs – ₹4.99 Lakhs', '₹5 Lakhs – ₹9.99 Lakhs', '₹10 Lakhs – ₹20 Lakhs', 'More than 20 Lakhs'], index=None)
        usage = st.radio("Usage:", ['Heavy (daily use)', 'Moderate (3-5 times/week)', 'Light (1-2 times/week)', 'Minimal (Emergency use only)'], index=None)
        driver = st.radio("Driven mostly by:", ['Self', 'Family Members', 'Driver', 'Others'], index=None)
        insurance = st.radio("Insurance Type:", ['Third Party Liability Plan Only', 'Comprehensive Plan', 'Comprehensive Plan + Add-ons', "Don't remember", "No Insurance"], index=None)
        trust = st.radio("What builds your trust the most when choosing an insurance policy?", ['Brand Value', 'Helpful/Known Agent', 'Family/Friend Recommendation', 'Transparency in Terms and Conditions', 'Simple/Clear Communication'], index=None)

        if st.button("Submit Survey"):
            if (vtype is None or not v_age or cost is None or usage is None or driver is None or
                insurance is None or trust is None):
                st.warning("Please complete all vehicle details before submitting.")
            else:
                with st.spinner("Submitting your response..."):
                    st.session_state.vehicle_info.update({
                        "Vehicle Kind": "Private",
                        "Vehicle Type": vtype,
                        "Vehicle Age": v_age,
                        "Vehicle Cost": cost,
                        "Usage": usage,
                        "Driven By": driver,
                        "Insurance": insurance,
                        "Trust Factor": trust
                    })

                    submit_to_google_sheets()
                    st.session_state.page = "thankyou"
                    st.rerun()

    elif vehicle_kind == "Commercial":
        businesstype = st.radio("Business Type:", ['Goods transport', 'Passenger transport', 'Construction or heavy equipment transport','Others'], index=None)
        num_vehicles = st.text_input("How many vehicles do you own?")
        vtype = st.radio("Type:", ['3-wheeler', 'Light Commercial Vehicle', 'Taxi/Cab', 'Minibus/Bus', 'Trucks','Others'], index=None)
        driver = st.radio("Driven By:",['Self', 'Driver', 'Others'], index = None)
        insurance = st.radio("Insurance Type:",['Third Party Liability Plan Only', 'Comprehensive Plan', 'Comprehensive Plan + Add ons', "Don't Know/ Don't Remember"], index = None)
        trust = st.radio("What builds your trust the most when choosing an insurance policy?",['Brand Value', 'Helpful/Known agent', 'Friend/family recommendation', 'Transparency in Terms and Conditions', 'Simple/Clear communication'],index = None)
        if st.button("Submit Survey"):
            if (businesstype is None or not num_vehicles or  vtype is None or driver is None or
                insurance is None or trust is None):
                st.warning("Please complete all vehicle details before submitting.")
            else:
                with st.spinner("Submitting your response..."):
                    st.session_state.vehicle_info["Vehicle Kind"] = "Commercial"
                    st.session_state.vehicle_info["Business Type"] = businesstype
                    st.session_state.vehicle_info["How many vehicles do you own?"] = num_vehicles
                    st.session_state.vehicle_info["Type"] = vtype
                    st.session_state.vehicle_info["Driven By"] = driver
                    st.session_state.vehicle_info["Insurance Type"] = insurance
                    st.session_state.vehicle_info["Trust Factor"] = trust
                
                    submit_to_google_sheets()
                
                    st.session_state.page = "thankyou"
                    st.rerun()
                
                

# --------------------------- 4. Final Page ---------------------------

def thankyou():
    st.title("Thank You!")
    st.markdown("""Thank you for taking the time to complete our survey. Your responses have been recorded successfully. We truly appreciate your input. Have a great day!""")
    
# --------------------------- 5. Page Navigation ---------------------------

page_dict = {
    "intro": intro,
    "instructions": instructions,
    "survey": survey,
    "demographics": demographics,
    "vehicle_ownership": vehicle_ownership,
    "vehicle_type": vehicle_type,
    "thankyou": thankyou
}

# Render current page
page_dict[st.session_state.page]()