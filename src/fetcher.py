# ============================================================
# SSB CSV Fetcher Module
# Handles:
# - Main interface for fetching data from SSB
# - Combines API and Inspector functionalities
# ============================================================

import pandas as pd
import logging
from .api import SSBApi
from .inspector import SSBInspector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# SSBcsvFetcher Class
# ============================================================================

class SSBcsvFetcher:
    def __init__(self):
        self.api = SSBApi()
        self.inspector = SSBInspector(self.api)
    
    # ============================================================
    # Data Fetching Methods
    # ============================================================

    def fetch_pivot_table(self, table_id: str, time_period: str = 'top(1)',
                         filters: dict = None, lang: str = 'no') -> pd.DataFrame:
        return self.api.fetch_pivot_table(table_id, time_period, filters, lang)
    
    def fetch_clean_table(self, table_id: str, time_period: str = 'top(1)',
                         filters: dict = None, lang: str = 'no') -> pd.DataFrame:
        df = self.fetch_pivot_table(table_id, time_period, filters, lang)
        df_clean = df.copy(deep=True)

        # Only clean column names
        df_clean.columns = [col.split(' - ')[-1].strip() if ' - ' in col else col 
                            for col in df_clean.columns]

        return df_clean
    
    # ============================================================
    # Table Discovery and Inspection Methods
    # ============================================================

    # Delegate to inspector
    def search_tables(self, query: str, lang: str = 'no'):
        return self.inspector.search_tables(query, lang)
    
    def list_tables(self, pagesize: int = 10, pagenumber: int = 1, lang: str = 'no'):
        return self.inspector.list_tables(pagesize, pagenumber, lang)
    
    # ============================================================
    # Metadata Inspection Methods
    # ============================================================

    def inspect_table(self, table_id: str, lang: str = 'no'):
        return self.inspector.inspect_table(table_id, lang)
    
    def print_table_info(self, table_id: str, lang: str = 'no'):
        return self.inspector.print_table_info(table_id, lang)
    
    def get_dimensions(self, table_id: str, lang: str = 'no'):
        return self.inspector.get_dimensions(table_id, lang)
    
    def print_dimensions(self, table_id: str, lang: str = 'no'):
        return self.inspector.print_dimensions(table_id, lang)