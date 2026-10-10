"""Unit tests for agent tools and utilities using standard library unittest."""

import unittest
from unittest.mock import patch, MagicMock
from src.backend import calculator
from src.mcp_server import stock_price
import asyncio


class TestAgentTools(unittest.TestCase):
    def test_calculator_addition(self):
        result = calculator.invoke({"first_no": 10, "second_no": 5, "operation": "add"})
        self.assertEqual(result, "15.0")

    def test_calculator_subtraction(self):
        result = calculator.invoke({"first_no": 10, "second_no": 4, "operation": "sub"})
        self.assertEqual(result, "6.0")

    def test_calculator_multiplication(self):
        result = calculator.invoke({"first_no": 3, "second_no": 7, "operation": "mul"})
        self.assertEqual(result, "21.0")

    def test_calculator_division(self):
        result = calculator.invoke({"first_no": 20, "second_no": 4, "operation": "div"})
        self.assertEqual(result, "5.0")

    def test_calculator_division_by_zero(self):
        result = calculator.invoke({"first_no": 10, "second_no": 0, "operation": "div"})
        self.assertIn("Division by zero is undefined", result)

    def test_calculator_invalid_operation(self):
        result = calculator.invoke({"first_no": 10, "second_no": 2, "operation": "mod"})
        self.assertIn("Unsupported operation", result)

    def test_stock_price_mcp_mock(self):
        mock_response = {
            "Global Quote": {
                "01. symbol": "AAPL",
                "05. price": "224.50",
                "09. change": "+1.25",
                "10. change percent": "0.56%",
                "07. latest trading day": "2026-10-10",
                "06. volume": "50000000",
            }
        }

        with patch("requests.get") as mock_get:
            mock_obj = MagicMock()
            mock_obj.status_code = 200
            mock_obj.json.return_value = mock_response
            mock_get.return_value = mock_obj

            loop = asyncio.new_event_loop()
            try:
                data = loop.run_until_complete(stock_price("AAPL"))
            finally:
                loop.close()

            self.assertEqual(data["status"], "success")
            self.assertEqual(data["symbol"], "AAPL")
            self.assertEqual(data["price"], "224.50")


if __name__ == "__main__":
    unittest.main()
