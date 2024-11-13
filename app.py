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
            required_columns = ['Date', 'Product', 'Size', 'Quantity', 'Action', 'Category']
            if not all(col in data.columns for col in required_columns):
                st.error(f"Missing required columns in {sheet_name}. Required: {required_columns}")
                return pd.DataFrame()
            
            # Calculate total
            data = calculate_total(data)
        else:
            required_columns = ['PRODUCT', 'SPECIFICATION', 'QUANTITY']
            if not all(col in data.columns for col in required_columns):
                st.error(f"Missing required columns in {sheet_name}. Required: {required_columns}")
                return pd.DataFrame()
            data['QUANTITY'] = pd.to_numeric(data['QUANTITY'], errors='coerce').fillna(0).astype(int)
        
        return data
        
    except Exception as e:
        st.error(f"Error processing {sheet_name}: {str(e)}")
        import traceback
        st.error(f"Full traceback:\n{traceback.format_exc()}")
        return pd.DataFrame()

def calculate_total(data):
    """Calculate total for each product and size combination."""
    if data.empty:
        return data
    
    # Convert the Date column to datetime for proper sorting
    data['Date'] = pd.to_datetime(data['Date'])
    
    # Sort by date to ensure chronological order
    data = data.sort_values('Date')
    
    # Initialize Total column
    data['Total'] = 0
    
    # Calculate total for each product and size combination
    for (product, size) in data.groupby(['Product', 'Size']).groups:
        mask = (data['Product'] == product) & (data['Size'] == size)
        running_total = 0
        for idx in data[mask].index:
            quantity = data.loc[idx, 'Quantity']
            action = data.loc[idx, 'Action']
            
            # Update running total based on action
            if action == 'Add':
                running_total += quantity
            else:  # Remove
                running_total -= quantity
                
            data.loc[idx, 'Total'] = running_total
    
    # Convert Total to integer
    data['Total'] = data['Total'].astype(int)
    
    return data

def refresh():
    if conn is None:
        st.error("Failed to establish Google Sheets connection.")
    else:
        st.success("Google Sheets connection refreshed successfully.")
        time.sleep(1)
        st.rerun()

def log_inventory_change(product, size, quantity, action, sheet_name):
    try:
        # Load existing log data
        log_data = load_data("RECORDS")
        local_tz = pytz.timezone('Asia/Manila')
        
        # Create new log entry
        new_entry = pd.DataFrame({
            'Date': [datetime.now(local_tz).strftime("%Y-%m-%d %I:%M %p")],
            'Product': [product],
            'Size': [size],
            'Quantity': [quantity],
            'Action': [action],
            'Category': [sheet_name],
            'Total': [0]  # Placeholder, will be calculated
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
    st.title("HJM Sindangan Inventory")
    st.subheader("Inventory Management")
    
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

            # Get current quantity
            current_quantity = existing_data.loc[
                (existing_data['PRODUCT'] == selected_product_to_update) & 
                (existing_data['SPECIFICATION'] == selected_size_to_update), 
                'QUANTITY'
            ].values[0]

            st.write(f"Current quantity: {current_quantity}")

            # Select between Add or Remove
            action = st.radio("Choose action:", ("Add", "Remove"))

            # Input for quantity based on selected action
            if action == "Add":
                quantity = st.number_input("Quantity to Add:", min_value=0, value=0, step=1)
            else:  # Remove
                quantity = st.number_input("Quantity to Remove:", min_value=0, max_value=current_quantity, value=0, step=1)

            # Button to perform the selected action
            if st.button("Update Inventory"):
                if quantity > 0:
                    if action == "Add":
                        new_quantity = current_quantity + quantity
                        success_message = f"Added {quantity} to {selected_product_to_update} (Size: {selected_size_to_update}). New quantity: {new_quantity}"
                    else:  # Remove
                        new_quantity = current_quantity - quantity
                        success_message = f"Removed {quantity} from {selected_product_to_update} (Size: {selected_size_to_update}). New quantity: {new_quantity}"

                    mask = (existing_data['PRODUCT'] == selected_product_to_update) & (existing_data['SPECIFICATION'] == selected_size_to_update)
                    existing_data.loc[mask, 'QUANTITY'] = new_quantity
                    conn.update(worksheet=st.session_state.selected_sheet, data=existing_data)
                    
                    # Log the inventory change
                    log_inventory_change(
                        selected_product_to_update,
                        selected_size_to_update,
                        quantity,
                        action,
                        st.session_state.selected_sheet
                    )
                    
                    st.success(success_message)
                    st.cache_data.clear()
                    existing_data = load_data(st.session_state.selected_sheet)
                    filtered_data = existing_data.copy()
                    refresh()
                else:
                    st.warning("Please enter a quantity greater than 0.")
        else:
            st.error("No data available in the selected sheet")

# Main area
if st.session_state.view_log:
    st.title("Inventory Log (RECORDS)")
    log_data = load_data("RECORDS")
    
    if not log_data.empty:
        # Add filtering options for the log
        st.sidebar.subheader("Filter Log")
        
        # Get unique products and categories
        products = ['All'] + sorted(log_data['Product'].unique().tolist())
        categories = ['All'] + sorted(log_data['Category'].unique().tolist())
        
        # Filter selections
        selected_product = st.sidebar.selectbox("Filter by Product:", products)
        selected_category = st.sidebar.selectbox("Filter by Category:", categories)
        
        # Apply filters
        filtered_log = log_data.copy()
        if selected_product != 'All':
            filtered_log = filtered_log[filtered_log['Product'] == selected_product]
        if selected_category != 'All':
            filtered_log = filtered_log[filtered_log['Category'] == selected_category]
        
        # Display the filtered log
        st.dataframe(filtered_log, use_container_width=True, hide_index=True)
        
        # Display summary statistics
        if selected_product != 'All':
            st.subheader("Current Stock Level")
            # Get the latest total for each size of the selected product
            latest_totals = (filtered_log[filtered_log['Product'] == selected_product]
                           .sort_values('Date')
                           .groupby('Size')['Total']
                           .last()
                           .reset_index())
            
            # Create a clean summary table
            summary_df = pd.DataFrame({
                'Size': latest_totals['Size'],
                'Current Stock': latest_totals['Total']
            })
            
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else:
        st.info("No records available in the log.")
else:
    st.title(f"Current Inventory ({st.session_state.selected_sheet})")
    try:
        if 'filtered_data' in locals():
            st.dataframe(filtered_data, use_container_width=True, hide_index=True)
        else:
            # If filtered_data is not defined (first load), load the default sheet
            existing_data = load_data(st.session_state.selected_sheet)
            st.dataframe(existing_data, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error displaying data: {e}")