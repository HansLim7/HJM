import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import time
from streamlit_gsheets import GSheetsConnection

# Initialize Google Sheets connection
conn = st.connection("gsheets", type=GSheetsConnection)

# List of available inventory sheets
INVENTORY_SHEETS = [
    "GEN MDSE",
    "TOOLS",
    "ELECTRICAL",
    "METALS",
    "HARDWARE",
    "PLUMBING",
    "TREASURE ISLAND",
    "FISHING"
]

@st.cache_data(ttl=5)
def load_data(sheet_name):
    try:
        # Read the data from the specified worksheet
        data = conn.read(worksheet=sheet_name)
        
        # Common preprocessing
        data = data.dropna(how="all")
        data = data.loc[:, ~data.columns.str.contains('^Unnamed')]
        
        # Sheet-specific processing
        if sheet_name == "RECORDS":
            required_columns = ['Date', 'Product', 'Size', 'Quantity(Pcs/Meter)', 
                                'Quantity(Box/Roll)', 'Action', 'Category', 'Total']
            if not all(col in data.columns for col in required_columns):
                st.error(f"Missing required columns in {sheet_name}. Required: {required_columns}")
                return pd.DataFrame()
            
            # Calculate total
            data = calculate_total(data)
        else:
            required_columns = ['PRODUCT', 'SPECIFICATION', 'QUANTITY(PCS/METER)', 'QUANTITY(BOX/ROLL)']
            if not all(col in data.columns for col in required_columns):
                st.error(f"Missing required columns in {sheet_name}. Required: {required_columns}")
                return pd.DataFrame()
            data['QUANTITY(PCS/METER)'] = pd.to_numeric(data['QUANTITY(PCS/METER)'], errors='coerce').fillna(0).astype(int)
            data['QUANTITY(BOX/ROLL)'] = pd.to_numeric(data['QUANTITY(BOX/ROLL)'], errors='coerce').fillna(0).astype(int)
        
        return data
        
    except Exception as e:
        st.error(f"Error processing {sheet_name}: {str(e)}")
        import traceback
        st.error(f"Full traceback:\n{traceback.format_exc()}")
        return pd.DataFrame()

def calculate_total(data):
    """Calculate total for each product, size, and quantity type combination."""
    if data.empty:
        return data
    
    # Convert the Date column to datetime for proper sorting
    data['Date'] = pd.to_datetime(data['Date'])
    
    # Sort by date to ensure chronological order
    data = data.sort_values('Date')
    
    # Initialize Total columns
    data['Total(Pcs/Meter)'] = 0
    data['Total(Box/Roll)'] = 0
    
    # Calculate total for each product, size, and quantity type combination
    for (product, size, action) in data.groupby(['Product', 'Size', 'Action']).groups:
        mask = (data['Product'] == product) & (data['Size'] == size) & (data['Action'] == action)
        running_total = 0
        for idx in data[mask].index:
            quantity_pcs = data.loc[idx, 'Quantity(Pcs/Meter)']
            quantity_box = data.loc[idx, 'Quantity(Box/Roll)']
            action = data.loc[idx, 'Action']
            
            # Update running total based on action
            if action == 'Add':
                running_total += quantity_pcs
            else:  # Remove
                running_total -= quantity_pcs
                
            data.loc[idx, 'Total(Pcs/Meter)'] = running_total

            # Similarly update the total for Quantity(Box/Roll)
            if action == 'Add':
                running_total += quantity_box
            else:
                running_total -= quantity_box
                
            data.loc[idx, 'Total(Box/Roll)'] = running_total
    
    return data

def refresh():
    if conn is None:
        st.error("Failed to establish Google Sheets connection.")
    else:
        st.success("Google Sheets connection refreshed successfully.")
        time.sleep(1)
        st.rerun()

def log_inventory_change(product, size, quantity_pcs, quantity_box, action, sheet_name):
    try:
        # Load existing log data
        log_data = load_data("RECORDS")
        local_tz = pytz.timezone('Asia/Manila')
        
        # Create new log entry
        new_entry = pd.DataFrame({
            'Date': [datetime.now(local_tz).strftime("%Y-%m-%d %I:%M %p")],
            'Product': [product],
            'Size': [size],
            'Quantity(Pcs/Meter)': [quantity_pcs],
            'Quantity(Box/Roll)': [quantity_box],
            'Action': [action],
            'Category': [sheet_name],
            'Total(Pcs/Meter)': [0],  # Placeholder, will be calculated
            'Total(Box/Roll)': [0]  # Placeholder, will be calculated
        })
        
        # Concatenate new entry with existing log data
        updated_log_data = pd.concat([log_data, new_entry], ignore_index=True)
        
        # Recalculate totals
        updated_log_data = calculate_total(updated_log_data)
        
        # Update RECORDS sheet with the new log data
        conn.update(worksheet="RECORDS", data=updated_log_data)
    except Exception as e:
        st.error(f"Error logging inventory change: {e}")

# Initialize session state
if 'view_log' not in st.session_state:
    st.session_state.view_log = False
if 'selected_sheet' not in st.session_state:
    st.session_state.selected_sheet = INVENTORY_SHEETS[0]

# Sidebar
with st.sidebar:
    st.title("Inventory Management")
    
    # Toggle button for view
    if st.button("Toggle View (Inventory Log / Current Inventory)"):
        st.session_state.view_log = not st.session_state.view_log
    
    if not st.session_state.view_log:
        # Sheet selection
        st.session_state.selected_sheet = st.selectbox(
            "Select Category:",
            options=INVENTORY_SHEETS
        )

        # Load the data for the selected sheet
        existing_data = load_data(st.session_state.selected_sheet)
        
        # Check if data is loaded and has the required columns
        if not existing_data.empty:
            st.subheader("Filter Products")
            
            # Extract unique product names for filtering
            product_names = existing_data['PRODUCT'].unique()

            # Select a product to filter
            selected_product = st.selectbox(
                "Select a product to filter (or select 'All' to show all):", 
                options=['All'] + list(product_names)
            )

            # Filter data based on selected product if not 'All'
            if selected_product != 'All':
                filtered_data = existing_data[existing_data['PRODUCT'] == selected_product]
            else:
                filtered_data = existing_data.copy()

            # Extract unique sizes for the filtered data
            sizes = filtered_data['SPECIFICATION'].unique()

            # Select a size to filter
            selected_size = st.selectbox(
                "Select a size to filter (or select 'All' to show all):", 
                options=['All'] + list(sizes)
            )

            # Apply size filter based on the selected size if not 'All'
            if selected_size != 'All':
                filtered_data = filtered_data[filtered_data['SPECIFICATION'] == selected_size]
                
            st.divider()
            
            # Add or remove products
            st.subheader("Update Inventory")

            # Select a product and size to update
            selected_product_to_update = st.selectbox(
                "Select a product to update:", 
                options=existing_data['PRODUCT'].unique(), 
                key="product_update"
            )
            
            # Filter sizes based on selected product
            sizes_for_product = existing_data[existing_data['PRODUCT'] == selected_product_to_update]['SPECIFICATION'].unique()
            selected_size_to_update = st.selectbox(
                "Select a size to update:", 
                options=sizes_for_product, 
                key="size_update"
            )

            # Get current quantities
            current_quantity_pcs = existing_data.loc[
                (existing_data['PRODUCT'] == selected_product_to_update) & 
                (existing_data['SPECIFICATION'] == selected_size_to_update), 
                'QUANTITY(PCS/METER)'
            ].values[0]
            current_quantity_box = existing_data.loc[
                (existing_data['PRODUCT'] == selected_product_to_update) & 
                (existing_data['SPECIFICATION'] == selected_size_to_update), 
                'QUANTITY(BOX/ROLL)'
            ].values[0]

            st.write(f"Current quantity (Pcs/Meter): {current_quantity_pcs}")
            st.write(f"Current quantity (Box/Roll): {current_quantity_box}")

            # Select between Add or Remove
            action = st.radio("Choose action:", ("Add", "Remove"))

            # Input for quantity based on selected action
            if action == "Add":
                quantity_pcs = st.number_input("Quantity (Pcs/Meter) to Add:", min_value=0, value=0, step=1)
                quantity_box = st.number_input("Quantity (Box/Roll) to Add:", min_value=0, value=0, step=1)
            else:  # Remove
                quantity_pcs = st.number_input("Quantity (Pcs/Meter) to Remove:", min_value=0, max_value=current_quantity_pcs, value=0, step=1)
                quantity_box = st.number_input("Quantity (Box/Roll) to Remove:", min_value=0, max_value=current_quantity_box, value=0, step=1)

            # Add/Remove products button
            if st.button(f"{action} Products"):
                try:
                    if action == "Add":
                        new_quantity_pcs = current_quantity_pcs + quantity_pcs
                        new_quantity_box = current_quantity_box + quantity_box
                    else:  # Remove
                        new_quantity_pcs = current_quantity_pcs - quantity_pcs
                        new_quantity_box = current_quantity_box - quantity_box
                    
                    # Update the data in Google Sheets
                    updated_data = existing_data.copy()
                    updated_data.loc[
                        (updated_data['PRODUCT'] == selected_product_to_update) & 
                        (updated_data['SPECIFICATION'] == selected_size_to_update), 
                        ['QUANTITY(PCS/METER)', 'QUANTITY(BOX/ROLL)']
                    ] = [new_quantity_pcs, new_quantity_box]
                    conn.update(worksheet=st.session_state.selected_sheet, data=updated_data)

                    # Log the change in the records sheet
                    log_inventory_change(selected_product_to_update, selected_size_to_update, 
                                         quantity_pcs, quantity_box, action, st.session_state.selected_sheet)
                    
                    st.success(f"Successfully {action.lower()}ed products.")
                except Exception as e:
                    st.error(f"Error updating inventory: {e}")

        # Display filtered data
        if not filtered_data.empty:
            st.subheader("Current Inventory Data")
            st.dataframe(filtered_data)

# Inventory log view
if st.session_state.view_log:
    st.title("Inventory Log")
    log_data = load_data("RECORDS")
    if not log_data.empty:
        st.dataframe(log_data)
