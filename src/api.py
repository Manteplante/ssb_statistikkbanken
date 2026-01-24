import pandas as pd
import requests
import logging
import io
from urllib.parse import quote

logger = logging.getLogger(__name__)

class SSBApi:

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
    
    # Fetch complete table data as CSV

    def fetch_table(self, table_id: str, lang: str = 'no') -> pd.DataFrame:
        url = f"{self.BASE_URL}/tables/{table_id}/data?lang={lang}&outputformat=csv&SeparatorSemicolon"
        return self.fetch_csv(url, separator=';')

    # Fetch table as pivot-friendly format (rows x columns structure)

    def fetch_pivot_table(self, table_id: str, time_period: str = 'top(1)', filters: dict = None, lang: str = 'no') -> pd.DataFrame:
        url = f"{self.BASE_URL}/tables/{table_id}/data?lang={lang}"
        url += "&outputformat=csv"
        url += "&outputformatparams=separatorsemicolon,usecodesandtexts"
        url += "&stub=Tid"
        url += "&heading=statistikkvariabel"

        url += f"&valuecodes[Tid]={quote(time_period, safe='')}"

        dimensions = self.get_dimensions(table_id, lang)
        
        if filters:
            for dimension, value in filters.items():
                url += f"&valuecodes[{dimension}]={quote(str(value), safe='')}"
            
            for dim_id in dimensions.keys():
                if dim_id not in ['Tid', 'statistikkvariabel'] and dim_id not in filters:
                    url += f"&valuecodes[{dim_id}]=*"
        else:
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
        