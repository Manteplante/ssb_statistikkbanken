# ============================================================
# SSB KLASS API Module
# Handles classification data (region codes, names, etc.)
# KLASS is SSB's classification system for administrative divisions for example
# ============================================================

import requests
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class SSBKlassApi:
    
    BASE_URL = "https://data.ssb.no/api/klass/v1"
    
    # Classification IDs for different administrative divisions
    CLASSIFICATIONS = {
        'municipalities_2026': '131',  # Kommuneinndeling 2026
        'counties_2026': '104',        # Fylkesinndeling 2026
    }
    
    def __init__(self):
        pass
    
    # Fetch a classification from KLASS API.

    def get_classification(self, classification_id: str, version: str = None) -> pd.DataFrame:

        try:
            # Use /codes endpoint to get the classification codes and names
            url = f"{self.BASE_URL}/classifications/{classification_id}/codes"
            
            params = {
                'language': 'no',
                'format': 'json'
            }
            
            if version:
                params['version'] = version
            
            logger.info(f"Fetching classification {classification_id} from KLASS API")
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract classification items from the codes list
            items = []
            if 'codes' in data:
                for item in data['codes']:
                    items.append({
                        'code': item.get('code'),
                        'name': item.get('name'),
                        'validFrom': item.get('validFrom'),
                        'validTo': item.get('validTo')
                    })
            
            df = pd.DataFrame(items)
            logger.info(f"Successfully fetched {len(df)} items from classification {classification_id}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching classification {classification_id}: {e}")
            raise
    
    # Get all Norwegian counties (fylker) for 2026
    def get_counties_2026(self) -> pd.DataFrame:
        
        return self.get_classification('104')
    
    # Get all Norwegian municipalities (kommuner) for 2026
    def get_municipalities_2026(self) -> pd.DataFrame:
        return self.get_classification('131')
    
    # Get list of all county codes for 2026
    def get_county_codes(self) -> list:
        df = self.get_counties_2026()
        return df['code'].tolist()
    
    # Get dictionary mapping code -> name for counties
    def get_county_mapping(self) -> dict:
        df = self.get_counties_2026()
        return dict(zip(df['code'], df['name']))
    
    # Get list of all municipality codes for 2026
    def get_municipality_codes(self) -> list:
        df = self.get_municipalities_2026()
        return df['code'].tolist()
    
    # Get dictionary mapping code -> name for municipalities
    def get_municipality_mapping(self) -> dict:
        df = self.get_municipalities_2026()
        return dict(zip(df['code'], df['name']))