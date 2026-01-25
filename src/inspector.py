
# ============================================================
# SSB Inspector Module
# Handles:
# - Table discovery (listing and searching)
# - Metadata inspection (table info, dimensions)
# - Human-readable output formatting
# ============================================================

import logging
import requests
import pandas as pd
from .api import SSBApi

logger = logging.getLogger(__name__)

# ============================================================
# SSBInspector Class
# ============================================================

class SSBInspector:
    def __init__(self, api: SSBApi):
        self.api = api

    # ============================================================
    # Table Discovery Methods
    # ============================================================

    def list_tables(self, pagesize: int = 10, pagenumber: int = 1, lang: str = 'no') -> pd.DataFrame:
        
        try:
            url = f"{self.api.BASE_URL}/tables?pagesize={pagesize}&pagenumber={pagenumber}&lang={lang}"
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
            url = f"{self.api.BASE_URL}/tables?query={query}&lang={lang}"
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
    

    # ============================================================
    # Table Inspection Methods
    # ============================================================


    #  Get basic information about a table

    def get_table_info(self, table_id: str, lang: str = 'no') -> dict:

        try:
            url = f"{self.api.BASE_URL}/tables/{table_id}?lang={lang}"
            logger.info(f"Fetching info for table {table_id}")
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching table info: {e}")
            raise
    
    # Delegate to API to get dimensions
    def get_dimensions(self, table_id: str, lang: str = 'no'):
        return self.api.get_dimensions(table_id, lang)

    # ============================================================
    # Display/Formatting Methods
    # ============================================================

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
    
    def inspect_table(self, table_id: str, filters: dict = None, lang: str = 'no') -> None:
        print(f"\n{'='*70}")
        print(f"TABLE: {table_id}")
        print(f"{'='*70}\n")
        
        self.print_table_info(table_id, lang)
        
        print("AVAILABLE FILTERS (use these codes):")
        print("=" * 70)
        dimensions = self.get_dimensions(table_id, lang)
        
        for dim_id, dim_info in dimensions.items():
            print(f"\n{dim_info['label']} → parameter: '{dim_id}'")
            values = dim_info['values']
            
            for code, name in values.items():
                print(f"  '{code}' = {name}")
        
        print(f"\n{'='*70}")
        print("HOW TO FETCH:")
        print("-" * 70)
        print(f"df = fetcher.fetch_clean_table('{table_id}')")
        print(f"df = fetcher.fetch_clean_table('{table_id}', filters={{'Kjonn': '1'}})")
        print(f"df = fetcher.fetch_clean_table('{table_id}', time_period='*')  # all data")
        print(f"{'='*70}\n")



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