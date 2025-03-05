import pandas as pd
import matplotlib.pyplot as plt
import os
import glob

# Recursively find all 'envLog.csv' files
def find_csv_files(root_dir):
    return glob.glob(os.path.join(root_dir, '**', '*envLog.csv'), recursive=True)

# Read and combine all CSV files into one DataFrame
def load_and_combine_csv(files):
    all_data = []
    for file in files:
        df = pd.read_csv(file, header=None, 
                         names=['datetime', 'outer_pressure', 'outer_temperature', 
                                'outer_humidity', 'inner_temperature', 'inner_humidity'])
        df['datetime'] = pd.to_datetime(df['datetime'])  # Convert to datetime format
        all_data.append(df)
    
    if all_data:
        combined_df = pd.concat(all_data).sort_values('datetime').reset_index(drop=True)
        return combined_df
    else:
        return None

# Plot the data
def plot_data(df):
    plt.figure(figsize=(10, 5))
    plt.plot(df['datetime'], df['outer_temperature'], label='Outer Temperature (°C)', color='red')
    plt.plot(df['datetime'], df['inner_temperature'], label='Inner Temperature (°C)', color='blue')
    plt.xlabel('Time')
    plt.ylabel('Temperature (°C)')
    plt.title('Temperature Trends Over Time')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

# Main execution
if __name__ == "__main__":
    root_directory = input("Enter the root directory to search: ").strip()
    
    if not os.path.exists(root_directory):
        print("Error: Directory does not exist. Please enter a valid path.")
    else:
        csv_files = find_csv_files(root_directory)
        
        if csv_files:
            combined_df = load_and_combine_csv(csv_files)
            print(f"Loaded {len(combined_df)} rows from {len(csv_files)} files.")
            
            plot_data(combined_df)
        else:
            print("No 'envLog.csv' files found.")
