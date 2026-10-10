"""Model Context Protocol (MCP) Server for Real-Time Financial Market Data.

Exposes a stdio-based FastMCP tool interface for querying real-time stock quotes
using AlphaVantage API.
"""

import os
import requests
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

# Initialize FastMCP Server
mcp = FastMCP("stock_price_server")

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "demo")


@mcp.tool()
async def stock_price(company_symbol: str) -> dict:
    """Retrieve real-time stock price quote for a given company ticker symbol.

    Args:
        company_symbol: Ticker symbol of the target company (e.g., 'AAPL', 'TSLA', 'MSFT', 'GOOGL').

    Returns:
        A dictionary containing price, change percentage, volume, and trading day information.
    """
    clean_symbol = company_symbol.strip().upper()
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE&symbol={clean_symbol}&apikey={ALPHAVANTAGE_API_KEY}"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        quote = data.get("Global Quote", {})
        if not quote:
            # Handle rate limiting or invalid ticker messages from AlphaVantage
            note = data.get("Note") or data.get("Information")
            if note:
                return {
                    "symbol": clean_symbol,
                    "status": "rate_limited",
                    "message": "AlphaVantage standard API rate limit reached. Please retry in 60 seconds.",
                }
            return {
                "symbol": clean_symbol,
                "status": "not_found",
                "message": f"No market quote found for ticker '{clean_symbol}'.",
            }

        return {
            "symbol": quote.get("01. symbol", clean_symbol),
            "price": quote.get("05. price"),
            "change": quote.get("09. change"),
            "change_percent": quote.get("10. change percent"),
            "latest_trading_day": quote.get("07. latest trading day"),
            "volume": quote.get("06. volume"),
            "status": "success",
        }
    except requests.RequestException as exc:
        return {
            "symbol": clean_symbol,
            "status": "error",
            "message": f"Failed to connect to market data provider: {str(exc)}",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
