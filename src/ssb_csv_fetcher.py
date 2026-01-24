# SSB (Statistisk sentralbyrå) Data Fetcher Module
# Focused on CSV method for fetching data from Statistics Norway

import pandas as pd
import requests
import logging
from urllib.parse import quote
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple class for fetching CSV data from SSB

class SSBcsvFetcher:

    BASE_URL = "https://data.ssb.no/api/pxwebapi/v2"

    # Initialize SSBcsvFetcher
    def __init__(self):
        pass
    
    def fetch_csv(self, csv_url: str, separator: str = ';') -> pd.DataFrame:
        try:
            logger.info(f"Fetching CSV from: {csv_url}")
            df = pd.read_csv(csv_url, sep=separator, encoding='iso-8859-1')
            logger.info(f"Successfully fetched {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise
    
    # List all available SSB tables

    def list_tables(self, pagesize: int = 10, pagenumber: int = 1, lang: str = 'no') -> pd.DataFrame:
        
        try:
            url = f"{self.BASE_URL}/tables?pagesize={pagesize}&pagenumber={pagenumber}&lang={lang}"
            logger.info(f"Fetching table list (page {pagenumber})")
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Extract tables into DataFrame
            tables = data.get('tables', [])
            df = pd.DataFrame(tables)
            logger.info(f"Found {len(df)} tables")
            return df
        except Exception as e:
            logger.error(f"Error fetching table list: {e}")
            raise
    
    # Search for SSB tables by keyword

    def search_tables(self, query: str, lang: str = 'no') -> pd.DataFrame:

        try:
            url = f"{self.BASE_URL}/tables?query={query}&lang={lang}"
            logger.info(f"Searching for tables: {query}")
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            tables = data.get('tables', [])
            df = pd.DataFrame(tables)
            logger.info(f"Found {len(df)} matching tables")
            return df
        except Exception as e:
            logger.error(f"Error searching tables: {e}")
            raise
    
    #  Get basic information about a table

    def get_table_info(self, table_id: str, lang: str = 'no') -> dict:

        try:
            url = f"{self.BASE_URL}/tables/{table_id}?lang={lang}"
            logger.info(f"Fetching info for table {table_id}")
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching table info: {e}")
            raise
    
    def print_table_info(self, table_id: str, lang: str = 'no') -> None:
 
        # Print table information in a human-readable format

        try:
            info = self.get_table_info(table_id, lang)
            
            print(f"\n{'='*70}")
            print(f"Table ID: {info.get('id')}")
            print(f"{'='*70}")
            print(f"Title: {info.get('label')}")
            print(f"\nVariables: {', '.join(info.get('variableNames', []))}")
            print(f"Time Unit: {info.get('timeUnit')}")
            print(f"Period: {info.get('firstPeriod')} - {info.get('lastPeriod')}")
            print(f"Last Updated: {info.get('updated')}")
            print(f"Source: {info.get('source')}")
            print(f"{'='*70}\n")
            
        except Exception as e:
            logger.error(f"Error printing table info: {e}")
            raise

    # Fetch complete table data as CSV

    def fetch_table(self, table_id: str, lang: str = 'no') -> pd.DataFrame:
        url = f"{self.BASE_URL}/tables/{table_id}/data?lang={lang}&outputformat=csv&SeparatorSemicolon"
        return self.fetch_csv(url, separator=';')

    # Fetch table as pivot-friendly format (rows x columns structure)

    def fetch_pivot_table(self, table_id: str, time_period: str = 'top(1)',
                         filters: dict = None, lang: str = 'no') -> pd.DataFrame:
        url = f"{self.BASE_URL}/tables/{table_id}/data?lang={lang}"
        url += "&outputformat=csv"
        url += "&outputformatparams=separatorsemicolon,usecodesandtexts"
        url += "&stub=Tid"
        url += "&heading=statistikkvariabel"

        url += f"&valuecodes[Tid]={quote(time_period, safe='')}"

        if filters:
            for dimension, value in filters.items():
                url += f"&valuecodes[{dimension}]={quote(str(value), safe='')}"
        else:
            dimensions = self.get_dimensions(table_id, lang)
            for dim_id in dimensions.keys():
                if dim_id not in ['Tid', 'statistikkvariabel']:
                    url += f"&valuecodes[{dim_id}]=*"

        try:
            logger.info(f"Fetching pivot table {table_id}")
            logger.info(f"URL: {url}")
            response = requests.get(url)
            response.raise_for_status()
            df = pd.read_csv(io.BytesIO(response.content), sep=';', encoding='iso-8859-1')
            logger.info(f"Successfully fetched {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error fetching pivot table: {e}")
            raise
    
    def fetch_clean_table(self, table_id: str, time_period: str = 'top(1)',
                         filters: dict = None, lang: str = 'no') -> pd.DataFrame:
        df = self.fetch_pivot_table(table_id, time_period, filters, lang)

        df_clean = df.copy()

        for col in df_clean.columns:
            if ' - ' in col:
                df_clean[col] = df_clean[col].astype(str).str.split(' - ').str[-1].str.strip()

        df_clean.columns = [col.split(' - ')[-1].strip() if ' - ' in col else col 
                            for col in df_clean.columns]

        return df_clean

    def get_dimensions(self, table_id: str, lang: str = 'no') -> dict:
        try:
            url = f"{self.BASE_URL}/tables/{table_id}/metadata?lang={lang}"
            logger.info(f"Fetching dimensions for table {table_id}")
            response = requests.get(url)
            response.raise_for_status()
            metadata = response.json()

            dimensions = {}
            for dim_id, dim_data in metadata.get('dimension', {}).items():
                label = dim_data.get('label', dim_id)
                values = dim_data.get('category', {}).get('label', {})
                dimensions[dim_id] = {
                    'label': label,
                    'values': values
                }

            return dimensions
        except Exception as e:
            logger.error(f"Error fetching dimensions: {e}")
            raise

    def print_dimensions(self, table_id: str, lang: str = 'no') -> None:
        try:
            dimensions = self.get_dimensions(table_id, lang)

            print(f"\nAvailable filters for table {table_id}:")
            print("="*70)

            for dim_id, dim_info in dimensions.items():
                print(f"\n{dim_info['label']} ({dim_id}):")
                values = dim_info['values']

                if len(values) > 10:
                    print(f"  {list(values.keys())[:10]}")
                    print(f"  ... and {len(values)-10} more")
                else:
                    for code, name in values.items():
                        print(f"  {code}: {name}")

            print(f"\n{'='*70}\n")

        except Exception as e:
            logger.error(f"Error printing dimensions: {e}")
            raise