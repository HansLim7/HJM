import streamlit as st
import pandas as pd
from datetime import datetime
import time
from streamlit_gsheets import GSheetsConnection

# Initialize Google Sheets connection
conn = st.connection("gsheets", type=GSheetsConnection)

# List of available inventory sheets
INVENTORY_SHEETS = [
    "GEN MDSE",
    "BELTS",
    "TOOLS",
    "ELECTRICAL",
    "METALS",
    "HARDWARE",
    "PLUMBING",
    "PAINTS",
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
            required_columns = ['Date', 'Product', 'Size', 'Quantity(Pcs/Meter)', 'Quantity(Box/Roll)', 'Action', 'Category']
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
    """Calculate total for each product and size combination."""
    if data.empty:
        return data
    
    # Convert the Date column to datetime with flexible parsing
    try:
        # First try parsing with format='mixed' to handle different formats
        data['Date'] = pd.to_datetime(data['Date'], format='mixed').dt.date
    except Exception:
        try:
            # Fallback to specific format if mixed fails
            data['Date'] = pd.to_datetime(data['Date'], format='%Y-%m-%d').dt.date
        except Exception as e:
            st.error(f"Error processing dates: {str(e)}")
            return data
    
    # Sort by date to ensure chronological order
    data = data.sort_values('Date')
    
    # Initialize Total columns with zeros
    data['Total(Pcs/Meter)'] = 0
    data['Total(Box/Roll)'] = 0
    
    # Group by Product and Size and calculate running totals
    for (product, size), group in data.groupby(['Product', 'Size']):
        total_pcs = 0
        total_box = 0
        
        for idx in group.index:
            if group.loc[idx, 'Action'] == 'Add':
                total_pcs += group.loc[idx, 'Quantity(Pcs/Meter)']
                total_box += group.loc[idx, 'Quantity(Box/Roll)']
            else:  # Remove
                total_pcs -= group.loc[idx, 'Quantity(Pcs/Meter)']
                total_box -= group.loc[idx, 'Quantity(Box/Roll)']
            
            # Update the totals for this row
            data.loc[idx, 'Total(Pcs/Meter)'] = total_pcs
            data.loc[idx, 'Total(Box/Roll)'] = total_box
    
    return data

def refresh():
    conn = st.connection("gsheets", type=GSheetsConnection, ttl=5)
    if conn is None:
        st.error("Failed to establish Google Sheets connection.")
    else:
        st.success("Google Sheets connection refreshed successfully.")
        time.sleep(3)
        st.rerun()


def log_inventory_change(product, size, quantity_pcs, quantity_box, action, sheet_name):
    try:
        # Load existing log data
        log_data = load_data("RECORDS")
        
        # Format the current date as MM/DD/YYYY to match expected format
        current_date = datetime.now().strftime("%m/%d/%Y")
        
        # Create new log entry
        new_entry = pd.DataFrame({
            'Date': [current_date],
            'Product': [product],
            'Size': [size],
            'Quantity(Pcs/Meter)': [quantity_pcs],
            'Quantity(Box/Roll)': [quantity_box],
            'Action': [action],
            'Category': [sheet_name]
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

            # Button to perform the selected action
            if st.button("Update Inventory"):
                if quantity_pcs > 0 or quantity_box > 0:
                    if action == "Add":
                        new_quantity_pcs = current_quantity_pcs + quantity_pcs
                        new_quantity_box = current_quantity_box + quantity_box
                        success_message = f"Added {quantity_pcs} (Pcs/Meter) and {quantity_box} (Box/Roll) to {selected_product_to_update} (Size: {selected_size_to_update}). New quantities: {new_quantity_pcs} (Pcs/Meter), {new_quantity_box} (Box/Roll)"
                    else:  # Remove
                        new_quantity_pcs = current_quantity_pcs - quantity_pcs
                        new_quantity_box = current_quantity_box - quantity_box
                        success_message = f"Removed {quantity_pcs} (Pcs/Meter) and {quantity_box} (Box/Roll) from {selected_product_to_update} (Size: {selected_size_to_update}). New quantities: {new_quantity_pcs} (Pcs/Meter), {new_quantity_box} (Box/Roll)"

                    mask = (existing_data['PRODUCT'] == selected_product_to_update) & (existing_data['SPECIFICATION'] == selected_size_to_update)
                    existing_data.loc[mask, 'QUANTITY(PCS/METER)'] = new_quantity_pcs
                    existing_data.loc[mask, 'QUANTITY(BOX/ROLL)'] = new_quantity_box
                    conn.update(worksheet=st.session_state.selected_sheet, data=existing_data)
                    
                    # Log the inventory change
                    log_inventory_change(
                        selected_product_to_update,
                        selected_size_to_update,
                        quantity_pcs,
                        quantity_box,
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

        # Date range filter
        st.sidebar.subheader("Filter by Date Range")
        start_date = st.sidebar.date_input("Start Date", value=None)
        end_date = st.sidebar.date_input("End Date", value=None)

        # Apply filters
        filtered_log = log_data.copy()
        # Convert 'Date' column to datetime if it's not already
        filtered_log['Date'] = pd.to_datetime(filtered_log['Date'], errors='coerce')

        # Only filter by date if a date range is provided
        if start_date and end_date:
            filtered_log = filtered_log[
        (filtered_log['Date'] >= pd.to_datetime(start_date)) & 
        (filtered_log['Date'] <= pd.to_datetime(end_date))
]

        # Apply filters
        filtered_log = log_data.copy()
        if selected_product != 'All':
            filtered_log = filtered_log[filtered_log['Product'] == selected_product]
        if selected_category != 'All':
            filtered_log = filtered_log[filtered_log['Category'] == selected_category]
        
        # Convert 'Date' column to datetime if it's not already
        filtered_log['Date'] = pd.to_datetime(filtered_log['Date'], errors='coerce')

        # Filter by date range
        filtered_log = filtered_log[
            (filtered_log['Date'] >= pd.to_datetime(start_date)) & 
            (filtered_log['Date'] <= pd.to_datetime(end_date))
        ]
        
        # Add download buttons
        col1, col2 = st.columns([1, 3])
        with col1:
            # Download filtered data
            if not filtered_log.empty:
                csv_filtered = filtered_log.to_csv(index=False)
                st.download_button(
                    label="📥 Download Filtered Data",
                    data=csv_filtered,
                    file_name=f"inventory_log_filtered_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            # Download all data
            csv_all = log_data.to_csv(index=False)
            st.download_button(
                label="📥 Download Complete Log",
                data=csv_all,
                file_name=f"inventory_log_complete_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        # Display the filtered log
        st.subheader("Inventory Log")
        st.dataframe(filtered_log, use_container_width=True, hide_index=True)
        
        # Add refresh button
        if st.button("🔄 Refresh Data", key="refresh_log"):
            refresh()
        
        # Display summary statistics
        if selected_product != 'All':
            st.subheader("Current Stock Level")
            # Get the latest totals for each size and quantity type of the selected product
            latest_totals = (
                filtered_log[filtered_log['Product'] == selected_product]
                .sort_values('Date')
                .groupby(['Size'])[['Total(Pcs/Meter)', 'Total(Box/Roll)']]
                .last()
                .reset_index()
                )
            
            # Create a clean summary table
            summary_df = pd.DataFrame({
                'Size': latest_totals['Size'],
                'Quantity (Pcs/Meter)': latest_totals['Total(Pcs/Meter)'],
                'Quantity (Box/Roll)': latest_totals['Total(Box/Roll)']
            })
            
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            
            # Add download button for summary
            csv_summary = summary_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Summary",
                data=csv_summary,
                file_name=f"inventory_summary_{selected_product}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    else:
        st.info("No records available in the log.")
        
else:
    st.title(f"Current Inventory ({st.session_state.selected_sheet})")
    try:
        if 'filtered_data' in locals():
            # Add download button for current inventory view
            csv_current = filtered_data.to_csv(index=False)
            st.download_button(
                label="📥 Download Current Inventory",
                data=csv_current,
                file_name=f"current_inventory_{st.session_state.selected_sheet}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            st.dataframe(filtered_data, use_container_width=True, hide_index=True)
            
            # Add refresh button
            if st.button("🔄 Refresh Data", key="refresh_inventory"):
                refresh()
                
        else:
            # If filtered_data is not defined (first load), load the default sheet
            existing_data = load_data(st.session_state.selected_sheet)
            # Add download button for default view
            csv_default = existing_data.to_csv(index=False)
            st.download_button(
                label="📥 Download Current Inventory",
                data=csv_default,
                file_name=f"current_inventory_{st.session_state.selected_sheet}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            st.dataframe(existing_data, use_container_width=True, hide_index=True)
            
            # Add refresh button
            if st.button("🔄 Refresh Data", key="refresh_inventory_default"):
                refresh()
                
    except Exception as e:
        st.error(f"Error displaying data: {e}")