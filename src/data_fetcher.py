import yfinance as yf
import pandas as pd

def fetch_data(ticker, start_date, end_date):
    """
    Fetches historical data for a given ticker from start_date to end_date.
    
    Args:
        ticker (str): The stock ticker symbol (e.g., "IVV").
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
        
    Returns:
        pd.DataFrame: Historical data with Date as index.
    """
    print(f"Fetching data for {ticker} from {start_date} to {end_date}...")
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if data.empty:
        print(f"No data found for {ticker}.")
        return None
    
    # Ensure Date is the index
    if 'Date' in data.columns:
        data.set_index('Date', inplace=True)

    # Flatten MultiIndex columns if present
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
        
    return data

if __name__ == "__main__":
    # Test the function
    df = fetch_data("IVV", "2020-01-01", "2020-12-31")
    if df is not None:
        print(df.head())
