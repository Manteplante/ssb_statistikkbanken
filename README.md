# SSB Data Fetcher

A Python library for fetching statistical data from Statistics Norway (Statistisk sentralbyrå - SSB) using their PxWebApi v2.

## Features

- **Simple CSV fetching** from SSB's statistical tables
- **Table discovery** - search and list available tables
- **Metadata inspection** - view available filters and dimensions
- **Data cleaning** - automatically strip codes from headers and values for human-readable output
- **Flexible filtering** - filter by any dimension (gender, age, region, etc.)
- **Time period control** - fetch all data, last N periods, or data from a specific year forward

## Installation

requirements.txt

### Quick-start

from src.fetcher import SSBcsvFetcher

<pre>
# Initialize fetcher
fetcher = SSBcsvFetcher()

# Search for tables
fetcher.search_tables('befolkning')

# Inspect available filters
fetcher.inspect_table('05810')

# Fetch clean data
df = fetcher.fetch_clean_table('05810', filters={'Kjonn': '0'})
</pre>

# Usage

### Discover tables

<pre>

# List all available tables (paginated)
fetcher.list_tables(pagesize=10, pagenumber=1)

# Search for specific tables
fetcher.search_tables('inntekt')

# Get table info
fetcher.print_table_info('05810')

</pre>

### Inspect Dimensions

<pre>
# Show all available filters with codes
fetcher.inspect_table('05810')

# Or just print dimensions
fetcher.print_dimensions('05810')
</pre>

### Fetch Data

<pre>

# Basic fetch (returns cleaned data)
df = fetcher.fetch_clean_table('05810')

# With filters
df = fetcher.fetch_clean_table('05810', filters={'Kjonn': '1', 'Alder': '16-44'})

# All time periods
df = fetcher.fetch_clean_table('05810', time_period='*')

# Last 10 periods
df = fetcher.fetch_clean_table('05810', time_period='top(10)')

# From specific year forward
df = fetcher.fetch_clean_table('05810', time_period='from(2020)')

</pre>

# Architecture

<pre>

The library is organized into three modules:

api.py - Low-level API Client
Handles HTTP communication with SSB's PxWebApi v2:

fetch_csv() - Fetch raw CSV from URL
fetch_table() - Fetch complete table
fetch_pivot_table() - Fetch with custom filters
get_dimensions() - Get available filters and codes
inspector.py - Table Discovery & Metadata
Provides human-friendly table exploration:

list_tables() - List all tables
search_tables() - Search by keyword
print_table_info() - Display table metadata
print_dimensions() - Show available filters
inspect_table() - Comprehensive inspection
fetcher.py - Main Orchestrator
Clean interface combining both modules:

fetch_pivot_table() - Raw data fetching
fetch_clean_table() - Clean data fetching
All inspector methods for discovery

</pre>

# Parameters

time_period == control time periods
filters == all other

<pre>

# Get female population by age group, all years
df = fetcher.fetch_clean_table('05810', time_period='*', filters={'Kjonn': '0'})

# Get male population, ages 16-44, last 5 years
df = fetcher.fetch_clean_table(
    '05810',
    time_period='top(5)',
    filters={'Kjonn': '1', 'Alder': '16-44'}
)

</pre>

# Notes

- SSB uses ISO-8859-1 encoding for CSV responses
- The Tid dimension is handled separately via time_period parameter
- All other dimensions use the filters parameter
- Dimension codes are case-sensitive (e.g., 'Kjonn' not 'kjonn')
- Use inspect_table() to see exact codes for your filters

# License

MIT

# References

https://www.ssb.no/en/omssb/tjenester-og-verktoy/api
https://data.ssb.no/api/pxwebapi/v2/